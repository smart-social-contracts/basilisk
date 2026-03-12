"""
Basilisk OS — Code execution environment.

Provides safe code execution with stdout/stderr capture, task-scoped entities,
and codex lazy loading for canister-resident Python code.

Functions:
    run_code                  — Execute Python code with optional task context.
    create_task_entity_class  — Create a namespaced entity base for task-scoped data.
    _ensure_codex_lazy_loading — Patch wasi-stub modules for on-demand codex loading.
"""

import sys
from typing import TYPE_CHECKING, Optional

try:
    import io
except ImportError:
    io = None

try:
    import traceback
except ImportError:
    traceback = None

try:
    from contextlib import redirect_stderr, redirect_stdout
except ImportError:
    class _NullRedirect:
        """No-op context manager for WASI where contextlib is unavailable."""
        def __init__(self, target):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    redirect_stdout = redirect_stderr = _NullRedirect

from ic_python_logging import get_logger, get_logs

if TYPE_CHECKING:
    from .entities import TaskExecution, Task

logger = get_logger("basilisk.os.execution")

_codex_lazy_loading_installed = False


def _ensure_codex_lazy_loading():
    """Patch wasi-stub modules with __getattr__ so codex source loads on first use.

    Modules placed by basilisk as empty stubs (with __file__ == '<wasi-stub>')
    get a __getattr__ that, on first attribute access, finds the matching Codex
    entity and exec's its source into the module dict.  After that first load
    __getattr__ is never called again for cached attributes.

    This is idempotent — safe to call on every run_code / execute_code_shell
    invocation; the actual patching only happens once.
    """
    global _codex_lazy_loading_installed
    if _codex_lazy_loading_installed:
        return
    _codex_lazy_loading_installed = True

    # Stdlib modules that basilisk stubs as wasi-stub but should never be
    # treated as codex modules.
    _SKIP_MODULES = frozenset({
        'ast', 'json', 'traceback', 'io', 'sys', 'os', 'math', 'time',
        'datetime', 'collections', 'functools', 'itertools', 'operator',
        'copy', 'types', 'abc', 'enum', 're', 'string', 'textwrap',
        'struct', 'hashlib', 'hmac', 'base64', 'binascii', 'logging',
        'warnings', 'contextlib', 'inspect', 'dis', 'token', 'tokenize',
        'keyword', 'pprint', 'decimal', 'fractions', 'random', 'statistics',
        'pathlib', 'posixpath', 'ntpath', 'genericpath', 'fnmatch', 'glob',
        'shutil', 'tempfile', 'csv', 'configparser', 'argparse', 'getopt',
        'unittest', 'doctest', 'pdb', 'profile', 'cProfile', 'timeit',
        'pickle', 'shelve', 'marshal', 'copyreg', 'socket', 'select',
        'selectors', 'signal', 'errno', 'ctypes', 'threading', 'queue',
        'multiprocessing', 'subprocess', 'sched', 'http', 'urllib',
        'email', 'html', 'xml', 'webbrowser', 'cgi', 'cgitb',
    })

    for name, mod in list(sys.modules.items()):
        # Check __dict__ directly to avoid triggering _LazyMod.__getattr__
        if mod.__dict__.get('__file__') != '<wasi-stub>':
            continue
        if '__getattr__' in mod.__dict__:
            continue
        # Skip stdlib modules that are wasi-stubs but not codex modules
        if name in _SKIP_MODULES or name.split('.')[0] in _SKIP_MODULES:
            continue

        def _lazy_codex_getattr(attr, _mod=mod):
            from .entities import Codex
            for c in Codex.instances():
                if c.name == _mod.__name__ and c.code:
                    exec(compile(c.code, _mod.__name__ + '.py', 'exec'), _mod.__dict__)
                    if attr in _mod.__dict__:
                        return _mod.__dict__[attr]
                    break
            raise AttributeError(f"module '{_mod.__name__}' has no attribute '{attr}'")

        mod.__getattr__ = _lazy_codex_getattr


def create_task_entity_class(task_name):
    """Create a TaskEntity base class that automatically uses task name as namespace.

    Args:
        task_name: Name of the task to use as namespace prefix

    Returns:
        A class that can be used as base for entities with automatic namespacing
    """
    from ic_python_db import Entity, TimestampedMixin

    class TaskEntity(Entity, TimestampedMixin):
        """Base class for task-scoped entities with automatic namespacing.

        Usage in codex:
            class MyState(TaskEntity):
                key = String()
                value = String()

        The entity will be stored with namespace: task_{task_name}::MyState
        """

        __namespace__ = f"task_{task_name}"

    return TaskEntity


def run_code(source_code, locals={}, task: Optional["Task"] = None, task_execution: Optional["TaskExecution"] = None):
    """Execute Python code with optional task-scoped entity support.

    Args:
        source_code: Python source code string to execute.
        locals: Optional dict of local variables to inject.
        task: Optional Task entity for context.
        task_execution: Optional TaskExecution for logging and namespacing.

    Returns:
        Dict with keys: success, result, logs, stdout_content, stderr_content,
        and optionally 'error' on failure.
    """

    logger.info("run_code start")
    _ensure_codex_lazy_loading()

    # Use current globals to ensure built-ins and proper scope
    safe_globals = globals().copy()

    # Import canister-specific modules (optional — may not be available in tests)
    try:
        import _cdk as basilisk
        from _cdk import ic
        safe_globals["basilisk"] = basilisk
        safe_globals["ic"] = ic
    except ImportError:
        pass

    # Try to import the application's entity module (ggg for realms, or basilisk.os)
    try:
        import ggg
        safe_globals["ggg"] = ggg
    except ImportError:
        pass

    # Create specific logger if task_execution is provided
    if task_execution:
        execution_logger = task_execution.logger()
    else:
        try:
            from _cdk import ic as _ic
            execution_logger = get_logger(f"execution_{_ic.time()}")
        except ImportError:
            execution_logger = get_logger("execution")

    # Add task-specific logger
    safe_globals["logger"] = execution_logger

    # Add TaskEntity if task_execution is provided
    if task_execution:
        task_name = task_execution.task.name
        safe_globals["TaskEntity"] = create_task_entity_class(task_name)
        logger.info(f"TaskEntity class added with namespace: task_{task_name}")

    safe_locals = {}
    safe_locals.update(locals)

    # Capture stdout and stderr during execution
    if io is not None:
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
    else:
        # WASI fallback: no io module, use no-op captures
        class _DummyIO:
            def getvalue(self):
                return ""
        stdout_capture = _DummyIO()
        stderr_capture = _DummyIO()

    try:
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            execution_logger.info("Execution started")
            # Redirect any get_logger() calls in exec'd code to the execution logger
            # so codex log output is captured under the task execution's logger name
            import ic_python_logging as _ipl
            _original_get_logger = _ipl.get_logger
            _ipl.get_logger = lambda name=None: execution_logger
            safe_globals["get_logger"] = lambda name=None: execution_logger
            try:
                # Execute with globals as locals to ensure functions can call each other
                exec(source_code, safe_globals, safe_globals)
            finally:
                _ipl.get_logger = _original_get_logger

        # Collect captured output
        logs = []
        stdout_content = stdout_capture.getvalue().strip()
        stderr_content = stderr_capture.getvalue().strip()

        if stdout_content:
            execution_logger.info("stdout: %s" % stdout_content)
        if stderr_content:
            execution_logger.warning("stderr: %s" % stderr_content)
        execution_logger.info("Execution completed successfully")

        if stdout_content:
            logs.extend(stdout_content.split("\n"))
        if stderr_content:
            logs.extend(stderr_content.split("\n"))

        result = {
            "success": True,
            "result": safe_globals.get("result"),
            "logs": get_logs(logger_name=execution_logger.name),
            "stdout_content": stdout_content,
            "stderr_content": stderr_content
        }

    except Exception:
        stack_trace = traceback.format_exc() if traceback else str(sys.exc_info()[1])

        # Still capture any output that occurred before the exception
        logs = []
        stdout_content = stdout_capture.getvalue().strip()
        stderr_content = stderr_capture.getvalue().strip()

        if stdout_content:
            logs.extend(stdout_content.split("\n"))
        if stderr_content:
            logs.extend(stderr_content.split("\n"))

        execution_logger.error("Execution failed: %s" % stack_trace)
        if stdout_content:
            execution_logger.info("stdout: %s" % stdout_content)
        if stderr_content:
            execution_logger.warning("stderr: %s" % stderr_content)

        result = {
            "success": False,
            "error": stack_trace,
            "result": None,
            "logs": get_logs(logger_name=execution_logger.name),
            "stdout_content": stdout_content,
            "stderr_content": stderr_content
        }

    return result
