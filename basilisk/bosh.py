#!/usr/bin/env python3
"""
bosh — Basilisk OS Shell

A shell interpreter for IC canisters running basilisk.
Commands are executed inside the canister via execute_code_shell.

Usage:
    bosh --canister <id> [--network <net>]           Interactive mode
    bosh --canister <id> [--network <net>] -c "code" One-shot mode
    bosh --canister <id> [--network <net>] script.py  File mode
    echo "print(42)" | bosh --canister <id>           Pipe mode

Shell commands:
    %ls [path]    List canister filesystem
    %cat <file>   Show file contents on canister
    %mkdir <path> Create directory on canister
    %task         Task management (create, start, stop, etc.)
    %run <file>   Read a local file and execute it on the canister
    %who          List variables in the remote namespace
    %db dump      Dump the canister database as JSON
    %db clear     Clear the canister database
    %db count     Count total entities in the database
    %cycles       Show canister cycle balance
    !<cmd>        Run a local OS command (e.g. !ls, !cat file.py)
    :q / exit     Quit the shell
    :help         Show this help
"""

import argparse
import ast
import os
import re
import subprocess
import sys
import time as _time


# ---------------------------------------------------------------------------
# Candid parsing
# ---------------------------------------------------------------------------

def _parse_candid(output: str) -> str:
    """Parse a Candid-encoded string response from dfx into plain text."""
    output = output.strip()
    m = re.search(r'\(\s*"(.*)"\s*,?\s*\)', output, re.DOTALL)
    if m:
        try:
            return ast.literal_eval(f'"{m.group(1)}"')
        except (SyntaxError, ValueError):
            return m.group(1).replace("\\n", "\n").replace('\\"', '"')
    return output


# ---------------------------------------------------------------------------
# Canister communication
# ---------------------------------------------------------------------------

def canister_exec(code: str, canister: str, network: str = None) -> str:
    """Send Python code to the canister and return the output."""
    escaped = code.replace('"', '\\"').replace("\n", "\\n")
    cmd = ["dfx", "canister", "call"]
    if network:
        cmd.extend(["--network", network])
    cmd.extend([canister, "execute_code_shell", f'("{escaped}")'])

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            return f"[dfx error] {r.stderr.strip()}"
        return _parse_candid(r.stdout)
    except subprocess.TimeoutExpired:
        return "[error] canister call timed out (120s)"
    except FileNotFoundError:
        return "[error] dfx not found — install the DFINITY SDK"


# ---------------------------------------------------------------------------
# Magic commands
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Code preamble that resolves the Task entity class at runtime.
# Priority: 1) already in namespace, 2) bos module, 3) ggg module,
#           4) define from ic_python_db on the fly, 5) unavailable.
# ---------------------------------------------------------------------------
_TASK_RESOLVE = (
    "if 'Codex' not in dir() or 'Task' not in dir():\n"
    "    _Task = None\n"
    "    for _mod in ('bos', 'ggg'):\n"
    "        try:\n"
    "            _m = __import__(_mod)\n"
    "            _Task = getattr(_m, 'Task', None)\n"
    "            if _Task and not getattr(_m, 'Codex', None): _Task = None\n"
    "            if _Task: break\n"
    "        except (ImportError, AttributeError):\n"
    "            pass\n"
    "    if _Task is None:\n"
    "        try:\n"
    "            from ic_python_db import Entity, String, Integer, Boolean, OneToMany, ManyToOne, OneToOne, TimestampedMixin\n"
    "            class Codex(Entity, TimestampedMixin):\n"
    "                __alias__ = 'name'\n"
    "                name = String()\n"
    "                url = String()\n"
    "                checksum = String()\n"
    "                calls = OneToMany('Call', 'codex')\n"
    "                @property\n"
    "                def code(self):\n"
    "                    pending = getattr(self, '_pending_code', None)\n"
    "                    if pending is not None: return pending\n"
    "                    if self.name:\n"
    "                        try:\n"
    "                            with open(f'/{self.name}', 'r') as f: return f.read()\n"
    "                        except (FileNotFoundError, OSError): pass\n"
    "                    return None\n"
    "                @code.setter\n"
    "                def code(self, value):\n"
    "                    if value is not None:\n"
    "                        if self.name:\n"
    "                            try:\n"
    "                                with open(f'/{self.name}', 'w') as f: f.write(str(value))\n"
    "                            except OSError: pass\n"
    "                            if hasattr(self, '_pending_code'): del self._pending_code\n"
    "                        else: self._pending_code = value\n"
    "                def _save(self):\n"
    "                    pending = getattr(self, '_pending_code', None)\n"
    "                    if pending is not None and self.name:\n"
    "                        try:\n"
    "                            with open(f'/{self.name}', 'w') as f: f.write(str(pending))\n"
    "                        except OSError: pass\n"
    "                        del self._pending_code\n"
    "                    return super()._save()\n"
    "            class Call(Entity, TimestampedMixin):\n"
    "                is_async = Boolean()\n"
    "                codex = ManyToOne('Codex', 'calls')\n"
    "                task_step = OneToOne('TaskStep', 'call')\n"
    "            class TaskExecution(Entity, TimestampedMixin):\n"
    "                __alias__ = 'name'\n"
    "                name = String(max_length=256)\n"
    "                task = ManyToOne('Task', 'executions')\n"
    "                status = String(max_length=50, default='idle')\n"
    "                result = String(max_length=5000)\n"
    "            class TaskStep(Entity, TimestampedMixin):\n"
    "                call = OneToOne('Call', 'task_step')\n"
    "                status = String(max_length=32, default='pending')\n"
    "                run_next_after = Integer(default=0)\n"
    "                timer_id = Integer()\n"
    "                task = ManyToOne('Task', 'steps')\n"
    "            class TaskSchedule(Entity, TimestampedMixin):\n"
    "                __alias__ = 'name'\n"
    "                name = String(max_length=256)\n"
    "                disabled = Boolean()\n"
    "                task = ManyToOne('Task', 'schedules')\n"
    "                run_at = Integer()\n"
    "                repeat_every = Integer()\n"
    "                last_run_at = Integer()\n"
    "            class Task(Entity, TimestampedMixin):\n"
    "                __alias__ = 'name'\n"
    "                name = String(max_length=256)\n"
    "                metadata = String(max_length=256)\n"
    "                status = String(max_length=32, default='pending')\n"
    "                step_to_execute = Integer(default=0)\n"
    "                steps = OneToMany('TaskStep', 'task')\n"
    "                schedules = OneToMany('TaskSchedule', 'task')\n"
    "                executions = OneToMany('TaskExecution', 'task')\n"
    "            _Task = Task\n"
    "        except ImportError:\n"
    "            pass\n"
    "    if _Task is not None:\n"
    "        Task = _Task\n"
    "        globals()['Task'] = _Task\n"
    "        for _cls in (Codex, Call, TaskExecution, TaskStep, TaskSchedule, Task):\n"
    "            globals()[_cls.__name__] = _cls\n"
)

_TASK_UNAVAILABLE = (
    "if 'Task' not in dir():\n"
    "    print('No task system available (ic_python_db not found).')\n"
)

_MAGIC_MAP = {
    "%who": "print([k for k in dir() if not k.startswith('_')])",
    "%db dump": "from ic_python_db import Database; print(Database.get_instance().dump_json(pretty=True))",
    "%db clear": "from ic_python_db import Database; Database.get_instance().clear(); print('Database cleared.')",
    "%db count": (
        "from ic_python_db import Database; db = Database.get_instance(); "
        "print(f'{sum(1 for k in db._db_storage.keys() if not k.startswith(\"_\"))} entries')"
    ),
    "%cycles": "print(f'{ic.canister_balance():,} cycles')",
}


def _fs_ls_code(path: str) -> str:
    """Code for: %ls [path]"""
    path = path or "/"
    esc = path.replace("'", "\\'")
    return (
        "import os\n"
        f"_p = '{esc}'\n"
        "try:\n"
        "    for _name in sorted(os.listdir(_p)):\n"
        "        _full = _p.rstrip('/') + '/' + _name\n"
        "        try:\n"
        "            _s = os.stat(_full)\n"
        "            import stat as _st\n"
        "            _type = 'd' if _st.S_ISDIR(_s.st_mode) else '-'\n"
        "            print(f'{_type} {_s.st_size:>8}  {_name}')\n"
        "        except Exception:\n"
        "            print(f'? {0:>8}  {_name}')\n"
        "except FileNotFoundError:\n"
        f"    print('ls: {esc}: No such file or directory')\n"
    )


def _fs_cat_code(path: str) -> str:
    """Code for: %cat <file>"""
    esc = path.replace("'", "\\'")
    return (
        "try:\n"
        f"    print(open('{esc}').read(), end='')\n"
        "except FileNotFoundError:\n"
        f"    print('cat: {esc}: No such file or directory')\n"
    )


def _fs_mkdir_code(path: str) -> str:
    """Code for: %mkdir <path>"""
    esc = path.replace("'", "\\'")
    return (
        "import os\n"
        f"os.makedirs('{esc}', exist_ok=True)\n"
        f"print('Created: {esc}')\n"
    )


# ---------------------------------------------------------------------------
# %task subcommand handlers — each returns Python code to exec on canister
# ---------------------------------------------------------------------------

# Helper snippet: convert IC nanosecond timestamp to UTC string.
_FMT_NS = (
    "def _fmt_ns(ns):\n"
    "    if not ns: return ''\n"
    "    s = ns // 1_000_000_000\n"
    "    d = s // 86400; r = s % 86400\n"
    "    h = r // 3600; r %= 3600\n"
    "    m = r // 60; sec = r % 60\n"
    "    y = 1970; md = [31,28,31,30,31,30,31,31,30,31,30,31]\n"
    "    while True:\n"
    "        yd = 366 if (y%4==0 and (y%100!=0 or y%400==0)) else 365\n"
    "        if d < yd: break\n"
    "        d -= yd; y += 1\n"
    "    md[1] = 29 if (y%4==0 and (y%100!=0 or y%400==0)) else 28\n"
    "    mo = 0\n"
    "    while mo < 12 and d >= md[mo]: d -= md[mo]; mo += 1\n"
    "    return f'{y:04}-{mo+1:02}-{d+1:02} {h:02}:{m:02}:{sec:02} UTC'\n"
)

# Helper snippet: get latest execution timestamp for a task.
_LAST_EXEC_TS = (
    "def _last_exec_ts(_task):\n"
    "    _exs = list(_task.executions)\n"
    "    if not _exs: return ''\n"
    "    _latest = max((getattr(e, '_timestamp_created', 0) or 0) for e in _exs)\n"
    "    return _fmt_ns(_latest)\n"
)

# Helper snippet: resolve a task by ID or name.
# Usage: insert _TASK_FIND.format(tid=...) then check `_t` is not None.
_TASK_FIND = (
    "    _t = Task.load('{tid}')\n"
    "    if not _t:\n"
    "        for _candidate in Task.instances():\n"
    "            if _candidate.name == '{tid}':\n"
    "                if _t is None or _candidate._id > _t._id:\n"
    "                    _t = _candidate\n"
)


def _task_list_code() -> str:
    """Code for: %task list  (also %task, %ps)"""
    return (
        _TASK_RESOLVE + _TASK_UNAVAILABLE +
        _FMT_NS + _LAST_EXEC_TS +
        "if 'Task' in dir():\n"
        "    for _t in Task.instances():\n"
        "        _scheds = list(_t.schedules)\n"
        "        _s = _scheds[0] if _scheds else None\n"
        "        _rep = f'{_s.repeat_every:>6}s' if _s and _s.repeat_every else '     -'\n"
        "        _dis = 'disabled' if (_s and _s.disabled) else 'enabled ' if _s else '   -   '\n"
        "        _last = _last_exec_ts(_t)\n"
        "        _last_str = f' | last={_last}' if _last else ''\n"
        "        print(f'{str(_t._id):>3} | {_t.status:<10} | repeat={_rep} | {_dis} | {_t.name}{_last_str}')\n"
        "    if Task.count() == 0: print('No tasks.')\n"
    )


def _task_create_code(rest: str) -> str:
    """Code for: %task create <name> [every <N>s] [--code "..."] [--file <path>]

    When --code or --file is supplied the full execution chain is created:
      Task → Codex (code stored on memfs) → Call → TaskStep
    --file reads code from a file on the canister's filesystem.
    Without --code/--file only a bare Task (+ optional schedule) is created.
    """
    # Parse --file <path>
    file_match = re.search(r'--file\s+(\S+)', rest)
    task_file = None
    if file_match:
        task_file = file_match.group(1)
        rest = rest[:file_match.start()] + rest[file_match.end():]

    # Parse --code "..." (supports single or double quotes)
    code_match = re.search(r"""--code\s+(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')""", rest)
    task_code = None
    if code_match:
        task_code = code_match.group(1) if code_match.group(1) is not None else code_match.group(2)
        # Unescape
        task_code = task_code.replace('\\"', '"').replace("\\'", "'")
        rest = rest[:code_match.start()] + rest[code_match.end():]

    # --file generates an exec(open(...).read()) wrapper
    if task_file and not task_code:
        esc_file = task_file.replace("'", "\\'")
        task_code = f"exec(open('{esc_file}').read())"

    # Parse "every <N>s"
    every_match = re.search(r'every\s+(\d+)s?', rest)
    interval = int(every_match.group(1)) if every_match else None
    name = re.sub(r'\s*every\s+\d+s?', '', rest).strip()

    if not name:
        return None  # signal usage error

    esc_name = name.replace("'", "\\'")

    code = (
        _TASK_RESOLVE + _TASK_UNAVAILABLE +
        "if 'Task' in dir():\n"
        f"    _t = Task(name='{esc_name}', status='pending')\n"
    )

    # Create the full execution chain if code was supplied.
    # Encode the task code as base64 to avoid escaping issues with
    # Candid text encoding (which interprets backslashes as escapes).
    if task_code is not None:
        import base64
        b64 = base64.b64encode(task_code.encode()).decode()
        code += "    import base64 as _b64\n"
        code += f"    _code_bytes = _b64.b64decode('{b64}')\n"
        code += "    _code_str = _code_bytes.decode()\n"
        code += f"    _codex = Codex(name='codex_{esc_name}')\n"
        code += "    _codex.code = _code_str\n"
        code += f"    _call = Call(codex=_codex)\n"
        code += f"    _step = TaskStep(call=_call, task=_t, status='pending')\n"

    if interval is not None:
        code += f"    _s = TaskSchedule(name='{esc_name}-schedule', task=_t, repeat_every={interval})\n"

    # Build confirmation message
    parts = []
    if task_code is not None:
        parts.append("with code")
    if interval is not None:
        parts.append(f"every {interval}s")
    suffix = f" ({', '.join(parts)})" if parts else ""
    code += f"    print(f'Created task {{_t._id}}: {esc_name}{suffix}')\n"
    return code


def _task_info_code(tid: str) -> str:
    """Code for: %task info <id|name>"""
    esc_tid = tid.replace("'", "\\'")
    return (
        _TASK_RESOLVE + _TASK_UNAVAILABLE +
        _FMT_NS + _LAST_EXEC_TS +
        "if 'Task' in dir():\n"
        + _TASK_FIND.format(tid=esc_tid) +
        "    if not _t:\n"
        f"        print('Task not found: {esc_tid}')\n"
        "    else:\n"
        "        print(f'Task {_t._id}: {_t.name}')\n"
        "        print(f'  Status: {_t.status}')\n"
        "        if _t.metadata: print(f'  Metadata: {_t.metadata}')\n"
        "        _scheds = list(_t.schedules)\n"
        "        if _scheds:\n"
        "            for _s in _scheds:\n"
        "                _rep = f'every {_s.repeat_every}s' if _s.repeat_every else 'once'\n"
        "                _st = 'disabled' if _s.disabled else 'enabled'\n"
        "                print(f'  Schedule: {_s.name} ({_rep}, {_st})')\n"
        "        else:\n"
        "            print('  Schedules: none')\n"
        "        _steps = list(_t.steps)\n"
        "        print(f'  Steps: {len(_steps)}')\n"
        "        for _i, _step in enumerate(_steps):\n"
        "            _has = 'no code'\n"
        "            if _step.call and _step.call.codex and _step.call.codex.code:\n"
        "                _snippet = _step.call.codex.code[:60].replace(chr(10), ' ')\n"
        "                _has = f'{_snippet}...'\n"
        "            print(f'    [{_i}] {_step.status} — {_has}')\n"
        "        _execs = list(_t.executions)\n"
        "        _last = _last_exec_ts(_t)\n"
        "        _last_str = f' (last: {_last})' if _last else ''\n"
        "        print(f'  Executions: {len(_execs)}{_last_str}')\n"
    )


def _task_log_code(tid: str) -> str:
    """Code for: %task log <id|name>"""
    esc_tid = tid.replace("'", "\\'")
    return (
        _TASK_RESOLVE + _TASK_UNAVAILABLE +
        _FMT_NS +
        "if 'Task' in dir():\n"
        + _TASK_FIND.format(tid=esc_tid) +
        "    if not _t:\n"
        f"        print('Task not found: {esc_tid}')\n"
        "    else:\n"
        "        _execs = list(_t.executions)\n"
        "        if not _execs:\n"
        "            print(f'Task {_t._id}: {_t.name} — no executions')\n"
        "        else:\n"
        "            _shown = _execs[-10:]\n"
        "            _hidden = len(_execs) - len(_shown)\n"
        "            print(f'Task {_t._id}: {_t.name} — {len(_execs)} execution(s)')\n"
        "            if _hidden > 0: print(f'  (showing last {len(_shown)}, {_hidden} older omitted)')\n"
        "            print()\n"
        "            for _e in _shown:\n"
        "                _res = (_e.result or '')[:200]\n"
        "                if len(_e.result or '') > 200: _res += '...'\n"
        "                _ts = getattr(_e, '_timestamp_created', None) or getattr(_e, '_timestamp_updated', None)\n"
        "                _dt = _fmt_ns(_ts)\n"
        '                print(f\'  #{_e._id} | {_e.status or "idle":<10} | {_dt} | {_e.name}\')\n'
        "                if _res: print(f'    {_res}')\n"
    )


def _task_run_code(tid: str) -> str:
    """Code for: %task run <id|name>

    Executes the task's code synchronously inline during this canister call.
    No timers needed — the code runs immediately and the result is recorded
    in a TaskExecution entity. Handles multi-step tasks sequentially.
    Works reliably on any canister with ic_python_db.
    """
    esc_tid = tid.replace("'", "\\'")
    return (
        _TASK_RESOLVE + _TASK_UNAVAILABLE +
        "if 'Task' in dir():\n"
        + _TASK_FIND.format(tid=esc_tid) +
        "    if not _t:\n"
        f"        print('Task not found: {esc_tid}')\n"
        "    else:\n"
        "        _steps = list(_t.steps)\n"
        "        if not _steps or not (_steps[0].call and _steps[0].call.codex and _steps[0].call.codex.code):\n"
        "            print(f'Task {_t._id}: {_t.name} — no executable code')\n"
        "        else:\n"
        "            import io, sys, traceback\n"
        "            _t.status = 'running'\n"
        "            _all_ok = True\n"
        "            for _si, _cur in enumerate(_steps):\n"
        "                _code_str = _cur.call.codex.code if _cur.call and _cur.call.codex else None\n"
        "                _exec_name = f'taskexec_{_t._id}_{_si}'\n"
        "                _te = TaskExecution(name=_exec_name, task=_t, status='running', result='')\n"
        "                _te._timestamp_created = ic.time()\n"
        "                if not _code_str:\n"
        "                    _te.status = 'failed'\n"
        "                    _te.result = 'No code to execute'\n"
        "                    _cur.status = 'failed'\n"
        "                    _all_ok = False\n"
        "                    break\n"
        "                _stdout = io.StringIO()\n"
        "                _old_stdout = sys.stdout\n"
        "                sys.stdout = _stdout\n"
        "                try:\n"
        "                    exec(_code_str)\n"
        "                    sys.stdout = _old_stdout\n"
        "                    _te.status = 'completed'\n"
        "                    _te.result = _stdout.getvalue()[:4999]\n"
        "                    _cur.status = 'completed'\n"
        "                except Exception:\n"
        "                    sys.stdout = _old_stdout\n"
        "                    _te.status = 'failed'\n"
        "                    _te.result = traceback.format_exc()[:4999]\n"
        "                    _cur.status = 'failed'\n"
        "                    _all_ok = False\n"
        "                    break\n"
        "            _t.status = 'completed' if _all_ok else 'failed'\n"
        "            _t.step_to_execute = 0\n"
        "            for _s in _steps: _s.status = 'pending'\n"
        "            _n_execs = len(list(_t.executions))\n"
        "            print(f'Ran task {_t._id}: {_t.name} — {_t.status} ({_n_execs} execution(s))')\n"
    )


def _task_start_code(tid: str) -> str:
    """Code for: %task start <id|name>  (also %start)

    If the task has steps with code (Codex → Call → TaskStep), sets up a real
    ic.set_timer() callback that executes the code and records the result.
    For recurring tasks the callback self-reschedules.
    """
    esc_tid = tid.replace("'", "\\'")
    return (
        _TASK_RESOLVE + _TASK_UNAVAILABLE +
        "if 'Task' in dir():\n"
        + _TASK_FIND.format(tid=esc_tid) +
        "    if not _t:\n"
        f"        print('Task not found: {esc_tid}')\n"
        "    else:\n"
        "        _t.status = 'pending'\n"
        "        _t.step_to_execute = 0\n"
        "        for _step in _t.steps: _step.status = 'pending'\n"
        "        for _s in _t.schedules: _s.disabled = False\n"
        #
        # Check if there are executable steps — if so, wire up real timers
        #
        "        _steps = list(_t.steps)\n"
        "        _has_code = False\n"
        "        if _steps:\n"
        "            _step0 = _steps[0]\n"
        "            if _step0.call and _step0.call.codex and _step0.call.codex.code:\n"
        "                _has_code = True\n"
        "        if _has_code:\n"
        "            _tid = str(_t._id)\n"
        "            def _bosh_exec_task():\n"
        "                import io, sys, traceback\n"
        "                _task = Task.load(_tid)\n"
        "                if not _task or _task.status == 'cancelled':\n"
        "                    return\n"
        "                _task.status = 'running'\n"
        "                _si = _task.step_to_execute\n"
        "                _all_steps = list(_task.steps)\n"
        "                if _si >= len(_all_steps):\n"
        "                    _si = 0\n"
        "                _cur = _all_steps[_si]\n"
        "                _code_str = _cur.call.codex.code if _cur.call and _cur.call.codex else None\n"
        "                _exec_name = f'taskexec_{_tid}_{_si}'\n"
        "                _te = TaskExecution(name=_exec_name, task=_task, status='running', result='')\n"
        "                _te._timestamp_created = ic.time()\n"
        "                if _code_str:\n"
        "                    _stdout = io.StringIO()\n"
        "                    _old_stdout = sys.stdout\n"
        "                    sys.stdout = _stdout\n"
        "                    try:\n"
        "                        exec(_code_str)\n"
        "                        sys.stdout = _old_stdout\n"
        "                        _te.status = 'completed'\n"
        "                        _te.result = _stdout.getvalue()[:4999]\n"
        "                        _cur.status = 'completed'\n"
        "                    except Exception:\n"
        "                        sys.stdout = _old_stdout\n"
        "                        _te.status = 'failed'\n"
        "                        _te.result = traceback.format_exc()[:4999]\n"
        "                        _cur.status = 'failed'\n"
        "                        _task.status = 'failed'\n"
        "                        return\n"
        "                else:\n"
        "                    _te.status = 'failed'\n"
        "                    _te.result = 'No code to execute'\n"
        "                    _cur.status = 'failed'\n"
        "                    _task.status = 'failed'\n"
        "                    return\n"
        "                _task.step_to_execute = _si + 1\n"
        "                if _task.step_to_execute < len(_all_steps):\n"
        "                    _next = _all_steps[_task.step_to_execute]\n"
        "                    _delay = _next.run_next_after or 0\n"
        "                    ic.set_timer(_delay, _bosh_exec_task)\n"
        "                else:\n"
        "                    _task.status = 'completed'\n"
        "                    _task.step_to_execute = 0\n"
        "                    for _s2 in _all_steps: _s2.status = 'pending'\n"
        "                    for _sched in _task.schedules:\n"
        "                        if _sched.repeat_every and _sched.repeat_every > 0 and not _sched.disabled:\n"
        "                            _task.status = 'pending'\n"
        "                            ic.set_timer(_sched.repeat_every, _bosh_exec_task)\n"
        "                            break\n"
        "            ic.set_timer(0, _bosh_exec_task)\n"
        "            print(f'Started: {_t.name} ({_t._id}) — timer scheduled')\n"
        "        else:\n"
        "            print(f'Started: {_t.name} ({_t._id})')\n"
    )


def _task_stop_code(tid: str) -> str:
    """Code for: %task stop <id|name>  (also %kill)"""
    esc_tid = tid.replace("'", "\\'")
    return (
        _TASK_RESOLVE + _TASK_UNAVAILABLE +
        "if 'Task' in dir():\n"
        + _TASK_FIND.format(tid=esc_tid) +
        "    if not _t:\n"
        f"        print('Task not found: {esc_tid}')\n"
        "    else:\n"
        "        _t.status = 'cancelled'\n"
        "        for _s in _t.schedules: _s.disabled = True\n"
        "        print(f'Stopped: {_t.name} ({_t._id})')\n"
    )


def _task_delete_code(tid: str) -> str:
    """Code for: %task delete <id|name>"""
    esc_tid = tid.replace("'", "\\'")
    return (
        _TASK_RESOLVE + _TASK_UNAVAILABLE +
        "if 'Task' in dir():\n"
        + _TASK_FIND.format(tid=esc_tid) +
        "    if not _t:\n"
        f"        print('Task not found: {esc_tid}')\n"
        "    else:\n"
        "        _name = _t.name\n"
        "        _tid = _t._id\n"
        "        for _s in list(_t.schedules): _s.delete()\n"
        "        for _step in list(_t.steps):\n"
        "            if _step.call:\n"
        "                if _step.call.codex: _step.call.codex.delete()\n"
        "                _step.call.delete()\n"
        "            _step.delete()\n"
        "        for _e in list(_t.executions): _e.delete()\n"
        "        _t.delete()\n"
        "        print(f'Deleted: {_name} ({_tid})')\n"
    )


_TASK_USAGE = (
    "Usage:\n"
    '  %task                                                    List all tasks\n'
    '  %task list                                               List all tasks\n'
    '  %task create <name> [every Ns] [--code "..."|--file <f>] Create a task\n'
    '  %task info <id|name>                                     Show task details\n'
    '  %task log <id|name> [--follow|-f]                        Show execution history\n'
    '  %task run <id|name>                                      Execute task code now\n'
    '  %task start <id|name>                                    Start via timer\n'
    '  %task stop <id|name>                                     Stop a task\n'
    '  %task delete <id|name>                                   Delete task and records'
)


def _task_log_follow_query(tid: str) -> str:
    """Canister code that returns JSON lines of recent executions for polling."""
    esc_tid = tid.replace("'", "\\'")
    return (
        _TASK_RESOLVE + _TASK_UNAVAILABLE +
        _FMT_NS +
        "if 'Task' in dir():\n"
        + _TASK_FIND.format(tid=esc_tid) +
        "    if not _t:\n"
        f"        print('__FOLLOW_ERR__Task not found: {esc_tid}')\n"
        "    else:\n"
        "        _execs = list(_t.executions)\n"
        "        for _e in _execs:\n"
        "            _ts = getattr(_e, '_timestamp_created', None) or getattr(_e, '_timestamp_updated', None)\n"
        "            _dt = _fmt_ns(_ts)\n"
        "            _res = (_e.result or '').replace(chr(10), '\\\\n')[:200]\n"
        "            print(f'__FOLLOW__{_e._id}|{_e.status or \"idle\"}|{_dt}|{_e.name}|{_res}')\n"
        "        print(f'__FOLLOW_TASK__{_t.status}')\n"
    )


def _task_log_follow(tid: str, canister: str, network: str):
    """Client-side polling loop for %task log --follow. Prints new executions as they appear."""
    print(f"Following task log for '{tid}' (Ctrl+C to stop)...")
    sys.stdout.flush()
    seen_ids = set()
    poll_interval = 3  # seconds

    try:
        while True:
            raw = canister_exec(_task_log_follow_query(tid), canister, network)
            if not raw:
                _time.sleep(poll_interval)
                continue

            task_status = None
            for line in raw.strip().split("\n"):
                if line.startswith("__FOLLOW_ERR__"):
                    print(line[len("__FOLLOW_ERR__"):])
                    return
                if line.startswith("__FOLLOW_TASK__"):
                    task_status = line[len("__FOLLOW_TASK__"):]
                    continue
                if not line.startswith("__FOLLOW__"):
                    continue
                parts = line[len("__FOLLOW__"):].split("|", 4)
                if len(parts) < 5:
                    continue
                eid, status, dt, name, result = parts
                if eid in seen_ids:
                    continue
                seen_ids.add(eid)
                result_display = result.replace("\\\\n", "\n").strip()
                print(f"  #{eid} | {status:<10} | {dt} | {name}")
                if result_display:
                    print(f"    {result_display}")
                sys.stdout.flush()

            if task_status in ("cancelled", "failed"):
                print(f"\nTask status: {task_status}")
                return

            _time.sleep(poll_interval)
    except KeyboardInterrupt:
        print("\nStopped following.")


def _handle_task(args: str, canister: str, network: str) -> str:
    """Dispatch %task subcommands. Returns canister output string."""
    parts = args.strip().split(None, 1)
    subcmd = parts[0] if parts else "list"
    rest = parts[1].strip() if len(parts) > 1 else ""

    if subcmd in ("list", "ls"):
        return canister_exec(_task_list_code(), canister, network)

    if subcmd == "create":
        if not rest:
            return _TASK_USAGE
        code = _task_create_code(rest)
        if code is None:
            return _TASK_USAGE
        return canister_exec(code, canister, network)

    if subcmd == "info":
        if not rest:
            return "Usage: %task info <id>"
        return canister_exec(_task_info_code(rest), canister, network)

    if subcmd == "log":
        if not rest:
            return "Usage: %task log <id|name> [--follow|-f]"
        # Detect --follow / -f flag
        follow = False
        tid_rest = rest
        for flag in ('--follow', '-f'):
            if flag in tid_rest:
                follow = True
                tid_rest = tid_rest.replace(flag, '').strip()
        if not tid_rest:
            return "Usage: %task log <id|name> [--follow|-f]"
        if follow:
            _task_log_follow(tid_rest, canister, network)
            return ""
        return canister_exec(_task_log_code(tid_rest), canister, network)

    if subcmd == "run":
        if not rest:
            return "Usage: %task run <id>"
        return canister_exec(_task_run_code(rest), canister, network)

    if subcmd == "start":
        if not rest:
            return "Usage: %task start <id>"
        return canister_exec(_task_start_code(rest), canister, network)

    if subcmd in ("stop", "kill"):
        if not rest:
            return "Usage: %task stop <id>"
        return canister_exec(_task_stop_code(rest), canister, network)

    if subcmd in ("delete", "del", "rm"):
        if not rest:
            return "Usage: %task delete <id>"
        return canister_exec(_task_delete_code(rest), canister, network)

    return _TASK_USAGE


def _handle_magic(line: str, canister: str, network: str) -> str:
    """Handle % magic commands. Returns output or None if not a magic command."""
    stripped = line.strip()

    # %run <file> — read local file, exec on canister
    if stripped.startswith("%run "):
        filepath = stripped[5:].strip()
        try:
            code = open(filepath).read()
            return canister_exec(code, canister, network)
        except FileNotFoundError:
            return f"[error] file not found: {filepath}"

    # Filesystem commands — operate on canister's memfs
    if stripped == "%ls" or stripped.startswith("%ls "):
        path = stripped[3:].strip() or "/"
        return canister_exec(_fs_ls_code(path), canister, network)
    if stripped.startswith("%cat "):
        path = stripped[5:].strip()
        if not path:
            return "Usage: %cat <file>"
        return canister_exec(_fs_cat_code(path), canister, network)
    if stripped.startswith("%mkdir "):
        path = stripped[7:].strip()
        if not path:
            return "Usage: %mkdir <path>"
        return canister_exec(_fs_mkdir_code(path), canister, network)

    # %task subcommand system
    if stripped == "%task" or stripped.startswith("%task "):
        args = stripped[5:].strip()
        return _handle_task(args, canister, network)

    # Shortcut aliases for backwards compatibility
    if stripped == "%ps" or stripped == "%tasks":
        return canister_exec(_task_list_code(), canister, network)
    if stripped.startswith("%start "):
        return canister_exec(_task_start_code(stripped[7:].strip()), canister, network)
    if stripped.startswith("%kill "):
        return canister_exec(_task_stop_code(stripped[6:].strip()), canister, network)

    # Lookup table magics
    if stripped in _MAGIC_MAP:
        return canister_exec(_MAGIC_MAP[stripped], canister, network)

    return None


# ---------------------------------------------------------------------------
# Shell modes
# ---------------------------------------------------------------------------

def _is_interactive():
    """Check if stdin is a terminal (not a pipe/redirect)."""
    return sys.stdin.isatty()


def _print_output(text: str):
    """Print canister output, stripping trailing whitespace."""
    if text:
        text = text.rstrip()
        if text:
            print(text)
    sys.stdout.flush()


def _welcome_banner(canister: str, network: str):
    """Generate a comprehensive welcome banner by querying the canister."""
    net_label = network or "local"

    print("=" * 60)
    print("  bosh — Basilisk OS Shell")
    print("=" * 60)
    print(f"  Canister : {canister}")
    print(f"  Network  : {net_label}")
    print()

    # Query canister for system info in one call
    info_code = r"""
import json, sys, time as _time
_info = {}

# Caller identity
_info['principal'] = str(ic.caller())

# Cycle balance
_info['cycles'] = f'{ic.canister_balance():,}'

# Timestamp
_ts = ic.time()
_info['ic_time'] = _ts

# Entity types and counts
try:
    from ic_python_db import Database as _DB
    _db = _DB.get_instance()
    _types = {}
    _enums = []
    for _et in _db._entity_types.values():
        _name = _et.__name__
        if hasattr(_et, 'count'):
            try:
                _types[_name] = _et.count()
            except Exception:
                _types[_name] = 0
        else:
            _enums.append(_name)
    _info['entity_types'] = _types
    _info['enum_types'] = _enums
    _info['total_entries'] = sum(1 for k in _db._db_storage.keys() if not k.startswith('_'))
except Exception as _e:
    _info['entity_types'] = {}
    _info['db_error'] = str(_e)

# Available libraries
_libs = []
try:
    import ggg
    _libs.append('ggg')
except: pass
try:
    import _cdk
    _libs.append('basilisk (_cdk)')
except: pass
try:
    import ic_python_db
    _libs.append('ic_python_db')
except: pass
try:
    import ic_python_logging
    _libs.append('ic_python_logging')
except: pass
_info['libraries'] = _libs

# Installed extensions
try:
    _exts = []
    from ic_python_db import Database as _DB2
    _db2 = _DB2.get_instance()
    for _k in _db2._db_storage.keys():
        if _k.startswith('Extension:'):
            _exts.append(_k.split(':',1)[1])
    _info['extensions'] = _exts
except:
    _info['extensions'] = []

print('__BOSH_INFO__' + json.dumps(_info))
"""
    result = canister_exec(info_code, canister, network)

    # Parse the info JSON from the output
    info = {}
    for line in (result or "").split("\n"):
        if line.startswith("__BOSH_INFO__"):
            try:
                import json
                info = json.loads(line[len("__BOSH_INFO__"):])
            except Exception:
                pass
            break

    if info:
        # Identity
        principal = info.get("principal", "unknown")
        short_principal = principal[:12] + "..." + principal[-6:] if len(principal) > 20 else principal
        print(f"  Principal: {short_principal}")
        print(f"  Cycles   : {info.get('cycles', 'unknown')}")
        print()

        # Libraries
        libs = info.get("libraries", [])
        if libs:
            print(f"  Libraries: {', '.join(libs)}")

        # Extensions
        exts = info.get("extensions", [])
        if exts:
            print(f"  Extensions: {', '.join(exts)}")

        if libs or exts:
            print()

        # Entity types
        entity_types = info.get("entity_types", {})
        if entity_types:
            total = info.get("total_entries", "?")
            print(f"  Database: {total} entries, {len(entity_types)} entity types")

            # Group by count: non-empty first
            non_empty = {k: v for k, v in sorted(entity_types.items()) if v > 0}
            empty = sorted(k for k, v in entity_types.items() if v == 0)

            if non_empty:
                print()
                print("  Entity            Count")
                print("  " + "-" * 30)
                for name, count in sorted(non_empty.items(), key=lambda x: -x[1]):
                    print(f"  {name:<20}{count:>5}")

            if empty:
                print()
                print(f"  Empty types: {', '.join(empty)}")
            print()
    else:
        # Fallback if introspection failed
        if result and result.strip():
            print(f"  (introspection returned: {result.strip()[:200]})")
        print()

    # Commands help
    print("  Shell commands:")
    print("    %ls [path]                List canister filesystem")
    print("    %cat <file>               Show file contents")
    print("    %mkdir <path>             Create directory")
    print("    %task                     List tasks (also %ps)")
    print('    %task create <name> [every Ns] [--code "..."|--file <f>]')
    print("    %task info|log|start|stop|delete <id|name>")
    print("    %who                      List namespace variables")
    print("    %cycles                   Show cycle balance")
    print("    %db count|dump|clear      Database operations")
    print("    %run <file>               Execute local file on canister")
    print("    !<cmd>                    Run a local OS command")
    print("    :help                     Full help    :q  Quit")
    print("=" * 60)
    print()


def run_interactive(canister: str, network: str):
    """Interactive REPL mode — like bash."""
    _welcome_banner(canister, network)

    # Try to use readline for history if available
    try:
        import readline  # noqa: F401 — enables arrow keys and history
    except ImportError:
        pass

    buffer = []

    while True:
        try:
            prompt = "bosh>>> " if not buffer else "...     "
            line = input(prompt)
        except (EOFError, KeyboardInterrupt):
            print()
            break

        # Meta commands
        stripped = line.strip()
        if stripped in (":q", "exit", "quit"):
            break
        if stripped == ":help":
            print(__doc__)
            continue

        # Local OS commands
        if stripped.startswith("!"):
            os.system(stripped[1:])
            continue

        # Magic commands
        magic_result = _handle_magic(stripped, canister, network)
        if magic_result is not None:
            _print_output(magic_result)
            continue

        # Multiline: collect lines ending with : or inside a block
        buffer.append(line)
        if stripped.endswith(":") or stripped.endswith("\\"):
            continue
        if stripped == "" and len(buffer) > 1:
            # Empty line ends a block
            code = "\n".join(buffer)
            buffer = []
            _print_output(canister_exec(code, canister, network))
            continue
        if len(buffer) > 1 and stripped != "":
            # Still inside a block (indented line)
            if line.startswith((" ", "\t")):
                continue

        # Single line or end of block
        code = "\n".join(buffer)
        buffer = []
        if code.strip():
            _print_output(canister_exec(code, canister, network))


def run_oneshot(code: str, canister: str, network: str):
    """One-shot mode: execute code string and exit."""
    # Handle magic commands and ! commands in one-shot mode too
    stripped = code.strip()
    if stripped.startswith("!"):
        os.system(stripped[1:])
        return
    magic_result = _handle_magic(stripped, canister, network)
    if magic_result is not None:
        _print_output(magic_result)
        return
    _print_output(canister_exec(code, canister, network))


def run_file(filepath: str, canister: str, network: str):
    """File mode: execute a script file on the canister."""
    try:
        code = open(filepath).read()
    except FileNotFoundError:
        print(f"bosh: {filepath}: No such file", file=sys.stderr)
        sys.exit(1)
    _print_output(canister_exec(code, canister, network))


def run_pipe(canister: str, network: str):
    """Pipe mode: read all stdin and execute as one block."""
    code = sys.stdin.read()
    if code.strip():
        _print_output(canister_exec(code, canister, network))


def run_watch(canister: str, network: str, inbox: str, outbox: str):
    """Watch mode: read commands from inbox file, write results to outbox.

    Protocol:
        1. Caller writes Python code to <inbox>
        2. bosh executes it on the canister
        3. bosh writes result + READY marker to <outbox>
        4. Caller reads <outbox>, waits for READY marker, repeats
    """
    READY = "---READY---"

    # Initialize
    with open(inbox, "w") as f:
        f.write("")
    with open(outbox, "w") as f:
        f.write(f"{READY}\n")

    net_label = network or "local"
    print(f"bosh watch mode started", file=sys.stderr)
    print(f"  Canister: {canister}", file=sys.stderr)
    print(f"  Network:  {net_label}", file=sys.stderr)
    print(f"  Inbox:    {inbox}", file=sys.stderr)
    print(f"  Outbox:   {outbox}", file=sys.stderr)
    sys.stderr.flush()

    last_mtime = os.path.getmtime(inbox)

    while True:
        try:
            import time
            time.sleep(0.3)
            current_mtime = os.path.getmtime(inbox)
            if current_mtime <= last_mtime:
                continue
            last_mtime = current_mtime

            with open(inbox, "r") as f:
                code = f.read().strip()
            if not code:
                continue
            if code in (":q", "exit", "quit"):
                with open(outbox, "w") as f:
                    f.write(f"Session ended.\n{READY}\n")
                break

            # Handle magic/local commands
            stripped = code.strip()
            if stripped.startswith("!"):
                import io, contextlib
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    os.system(stripped[1:])
                result = buf.getvalue()
            else:
                magic_result = _handle_magic(stripped, canister, network)
                result = magic_result if magic_result is not None else canister_exec(code, canister, network)

            with open(outbox, "w") as f:
                if result and result.strip():
                    f.write(result.rstrip() + "\n")
                f.write(f"{READY}\n")

        except KeyboardInterrupt:
            break
        except Exception as e:
            with open(outbox, "w") as f:
                f.write(f"[bosh error] {e}\n{READY}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="bosh",
        description="Basilisk OS Shell — a shell interpreter for IC canisters",
        add_help=False,
    )
    parser.add_argument("--canister", required=True, help="Canister name or ID")
    parser.add_argument("--network", default=None, help="Network: local, ic, or URL")
    parser.add_argument("-c", dest="code", default=None, help="Execute code string")
    parser.add_argument("--watch", default=None, metavar="INBOX",
                        help="Watch mode: read commands from INBOX file")
    parser.add_argument("--outbox", default="/tmp/bosh_out",
                        help="Output file for watch mode (default: /tmp/bosh_out)")
    parser.add_argument("--login", action="store_true",
                        help="Force interactive mode (used by bosh-sshd)")
    parser.add_argument("file", nargs="?", default=None, help="Script file to execute")
    parser.add_argument("-h", "--help", action="store_true", help="Show help")

    args = parser.parse_args()

    if args.help:
        print(__doc__.strip())
        return

    if args.watch:
        run_watch(args.canister, args.network, args.watch, args.outbox)
    elif args.code:
        run_oneshot(args.code, args.canister, args.network)
    elif args.file:
        run_file(args.file, args.canister, args.network)
    elif args.login or _is_interactive():
        run_interactive(args.canister, args.network)
    else:
        run_pipe(args.canister, args.network)


if __name__ == "__main__":
    main()
