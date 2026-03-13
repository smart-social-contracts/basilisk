"""
Basilisk OS — Core entities for task/process management.

These entity definitions run inside the canister and depend on ic-python-db.
They are the canonical Basilisk OS definitions; realms imports from here.

Entities:
    Codex         — Stores executable Python code on the persistent filesystem.
    Call          — Links a Codex to a TaskStep for execution (sync or async).
    Task          — A unit of work that can be scheduled and executed.
    TaskStep      — A single step in a multi-step task workflow.
    TaskSchedule  — Schedule for running a Task at specified intervals.
    TaskExecution — Record of a single task execution attempt.
"""

from ic_python_db import (
    Boolean,
    Entity,
    Integer,
    ManyToOne,
    OneToMany,
    OneToOne,
    String,
    TimestampedMixin,
)
from ic_python_logging import get_logger

from .status import TaskExecutionStatus

logger = get_logger("basilisk.os.entities")


# ---------------------------------------------------------------------------
# Codex — executable code stored on the persistent filesystem
# ---------------------------------------------------------------------------

class Codex(Entity, TimestampedMixin):
    """
    Stores executable Python code on the canister's persistent filesystem.

    Code is persisted as a file at ``/<name>`` using the in-memory filesystem
    (memfs).  The ``code`` property transparently reads/writes this file.

    This is the base Codex entity for Basilisk OS.  Applications (e.g. Realms)
    may subclass or extend it with additional relationships.
    """

    name = String()
    url = String()  # Optional URL for downloadable code
    checksum = String()  # Optional SHA-256 checksum for verification
    calls = OneToMany("Call", "codex")
    __alias__ = "name"

    @property
    def code(self):
        """Read codex content from the persistent filesystem."""
        # Return pending code if name hasn't been set yet
        pending = getattr(self, '_pending_code', None)
        if pending is not None:
            return pending
        if self.name:
            try:
                with open(f"/{self.name}", "r") as f:
                    return f.read()
            except (FileNotFoundError, OSError):
                pass
        return None

    @code.setter
    def code(self, value):
        """Write codex content to the persistent filesystem."""
        if value is not None:
            if self.name:
                try:
                    with open(f"/{self.name}", "w") as f:
                        f.write(str(value))
                except OSError as e:
                    logger.error(f"Failed to write codex '{self.name}' to filesystem: {e}")
                # Clear any pending code
                if hasattr(self, '_pending_code'):
                    del self._pending_code
            else:
                # Name not set yet — store temporarily until _save() flushes it
                self._pending_code = value

    def _save(self):
        """Override to flush pending code to filesystem after all properties are set."""
        pending = getattr(self, '_pending_code', None)
        if pending is not None and self.name:
            try:
                with open(f"/{self.name}", "w") as f:
                    f.write(str(pending))
            except OSError as e:
                logger.error(f"Failed to write codex '{self.name}' to filesystem: {e}")
            del self._pending_code
        return super()._save()


# ---------------------------------------------------------------------------
# Call — links Codex code to a TaskStep for execution
# ---------------------------------------------------------------------------

class Call(Entity, TimestampedMixin):
    """
    Represents a code execution call, either sync or async.

    Links a Codex (code) to a TaskStep for execution.
    """

    is_async = Boolean()
    codex = ManyToOne("Codex", "calls")
    task_step = OneToOne("TaskStep", "call")

    def _function(self, task_execution: "TaskExecution"):
        if not self.codex or not self.codex.code:
            raise ValueError("Call has no codex or codex has no code")

        try:
            from .execution import run_code
        except ImportError:
            run_code = None

        if self.is_async:
            def async_wrapper():
                result = run_code(self.codex.code, task_execution=task_execution)

                if not result.get("success"):
                    raise ValueError(f"Async codex execution failed: {result.get('error')}")

                # Re-exec to get the async_task function reference
                exec_logger = task_execution.logger()
                namespace = {"logger": exec_logger}

                # Try to import canister-specific modules
                try:
                    import _cdk as basilisk
                    from _cdk import ic
                    namespace["basilisk"] = basilisk
                    namespace["ic"] = ic
                except ImportError:
                    pass

                exec(self.codex.code, namespace, namespace)

                async_task_fn = namespace.get("async_task")
                if async_task_fn is None:
                    raise ValueError("Async codex must define 'async_task()' function")

                call_result = async_task_fn()

                # If async_task is a generator, iterate it so its body executes
                if hasattr(call_result, '__next__'):
                    try:
                        while True:
                            next(call_result)
                    except StopIteration as e:
                        return e.value
                return call_result

            return async_wrapper
        else:
            def sync_wrapper():
                return run_code(self.codex.code, task_execution=task_execution)

            return sync_wrapper


# ---------------------------------------------------------------------------
# TaskExecution — execution record
# ---------------------------------------------------------------------------

class TaskExecution(Entity, TimestampedMixin):
    """Record of a single task execution attempt."""

    __alias__ = "name"
    name = String(max_length=256)
    task = ManyToOne("Task", "executions")
    status = String(max_length=50)  # "completed", "failed", "running"
    result = String(max_length=5000)

    def _logger_name(self):
        return "task_%s_%s" % (self.task._id, self._id)

    def logger(self):
        return get_logger(self._logger_name())

    def __repr__(self) -> str:
        return (
            f"TaskExecution(\n"
            f"  name={self.name}\n"
            f"  task={self.task}\n"
            f"  status={self.status}\n"
            f"  logger_name={self._logger_name()}\n"
            f"  result={self.result}\n"
            f")"
        )


# ---------------------------------------------------------------------------
# TaskStep — single step in a multi-step workflow
# ---------------------------------------------------------------------------

class TaskStep(Entity, TimestampedMixin):
    """
    Represents a single step in a task execution.

    ICP canisters cannot mix sync and async in the same function.
    TaskSteps solve this by allowing:
      - Step 1 (Sync): Local computation
      - Step 2 (Async): Inter-canister call with yield
      - Step 3 (Sync): Process results
    """

    call = OneToOne("Call", "task_step")
    status = String(max_length=32, default="pending")
    run_next_after = Integer(default=0)  # seconds to wait before next step
    timer_id = Integer()
    task = ManyToOne("Task", "steps")


# ---------------------------------------------------------------------------
# TaskSchedule — when and how often to run
# ---------------------------------------------------------------------------

class TaskSchedule(Entity, TimestampedMixin):
    """Schedule for running a Task at specified intervals."""

    __alias__ = "name"
    name = String(max_length=256)
    disabled = Boolean()
    task = ManyToOne("Task", "schedules")
    run_at = Integer()
    repeat_every = Integer()
    last_run_at = Integer()

    def serialize(self):
        """Convert TaskSchedule to dictionary for JSON serialization."""
        return {
            "_id": str(self._id),
            "_type": "TaskSchedule",
            "name": self.name,
            "task_id": (
                str(self.task._id) if hasattr(self, "task") and self.task else None
            ),
            "disabled": self.disabled,
            "run_at": self.run_at,
            "repeat_every": self.repeat_every,
            "last_run_at": self.last_run_at,
        }

    def __json__(self):
        """Make TaskSchedule JSON serializable."""
        return self.serialize()

    def __str__(self):
        return (
            f"TaskSchedule(name={self.name}, "
            f"run_at={self.run_at}, "
            f"repeat_every={self.repeat_every})"
        )


# ---------------------------------------------------------------------------
# Task — the primary work unit
# ---------------------------------------------------------------------------

class Task(Entity, TimestampedMixin):
    """
    Task entity — represents a unit of work that can be scheduled and executed.
    """

    __alias__ = "name"
    name = String(max_length=256)
    metadata = String(max_length=256)
    status = String(max_length=32, default="pending")
    step_to_execute = Integer(default=0)
    # Relationships
    steps = OneToMany("TaskStep", "task")
    schedules = OneToMany("TaskSchedule", "task")
    executions = OneToMany("TaskExecution", "task")

    def new_task_execution(self) -> TaskExecution:
        execution_name = "taskexec_%s_%s" % (self._id, self._id)
        execution = TaskExecution(
            name=execution_name,
            task=self,
            status=TaskExecutionStatus.IDLE,
            result="",
        )
        return execution
