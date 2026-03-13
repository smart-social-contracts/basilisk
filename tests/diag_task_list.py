#!/usr/bin/env python3
"""Diagnostic script to debug task list empty-string issue in CI."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from basilisk.bosh import canister_exec, _TASK_RESOLVE, _task_list_code, _parse_candid

c = os.environ["BOSH_TEST_CANISTER"]
n = os.environ["BOSH_TEST_NETWORK"]

# 1) What's in the namespace?
r1 = canister_exec("print('Task' in dir(), 'Codex' in dir())", c, n)
print(f"[DIAG1] namespace check: {r1!r}")

# 2) Run _TASK_RESOLVE alone
r2 = canister_exec(_TASK_RESOLVE + "print('AFTER_RESOLVE:', 'Task' in dir(), 'Codex' in dir())", c, n)
print(f"[DIAG2] after resolve: {r2!r}")

# 3) Try simple Task.count()
r3 = canister_exec("print('count=', Task.count() if 'Task' in dir() else 'N/A')", c, n)
print(f"[DIAG3] count: {r3!r}")

# 4) Run full _task_list_code — capture RAW dfx output
from basilisk.bosh import _run_dfx_with_retries, _FMT_NS, _LAST_EXEC_TS
code = _task_list_code()
escaped = code.replace('"', '\\"').replace("\n", "\\n")
cmd = ["dfx", "canister", "call", "--network", n, c, "execute_code_shell", f'("{escaped}")']
r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
print(f"[DIAG4] code length: {len(code)}, escaped length: {len(escaped)}")
print(f"[DIAG4] dfx returncode: {r.returncode}")
print(f"[DIAG4] dfx stdout (raw, first 500): {r.stdout[:500]!r}")
print(f"[DIAG4] dfx stderr (raw, first 500): {r.stderr[:500]!r}")
print(f"[DIAG4] parsed: {_parse_candid(r.stdout)!r}")

# 5) Incremental: _TASK_RESOLVE + _FMT_NS only + simple print
r5a = canister_exec(
    _TASK_RESOLVE + _FMT_NS + "print('FMT_NS_OK')\n", c, n)
print(f"[DIAG5a] resolve+fmt_ns: {r5a!r}")

# 6) Incremental: + _LAST_EXEC_TS
r5b = canister_exec(
    _TASK_RESOLVE + _FMT_NS + _LAST_EXEC_TS + "print('HELPERS_OK')\n", c, n)
print(f"[DIAG5b] resolve+fmt_ns+last_exec: {r5b!r}")

# 7) Incremental: + iterate with schedules access
r5c = canister_exec(
    _TASK_RESOLVE + _FMT_NS + _LAST_EXEC_TS +
    "if 'Task' in dir():\n"
    "    for _t in Task.instances():\n"
    "        _scheds = list(_t.schedules)\n"
    "        print(f'TASK {_t._id}: {_t.name} scheds={len(_scheds)}')\n"
    "    if Task.count() == 0: print('No tasks.')\n",
    c, n)
print(f"[DIAG5c] with schedules: {r5c!r}")

# 8) Incremental: full format line
r5d = canister_exec(
    _TASK_RESOLVE + _FMT_NS + _LAST_EXEC_TS +
    "if 'Task' in dir():\n"
    "    for _t in Task.instances():\n"
    "        _scheds = list(_t.schedules)\n"
    "        _s = _scheds[0] if _scheds else None\n"
    "        _rep = f'every {_s.repeat_every}s' if _s and _s.repeat_every else '     -'\n"
    "        _dis = 'disabled' if (_s and _s.disabled) else 'enabled ' if _s else '   -   '\n"
    "        _last = _last_exec_ts(_t)\n"
    "        _last_str = f' | last={_last}' if _last else ''\n"
    "        print(f'{str(_t._id):>3} | {_t.status:<10} | repeat={_rep} | {_dis} | {_t.name}{_last_str}')\n"
    "    if Task.count() == 0: print('No tasks.')\n",
    c, n)
print(f"[DIAG5d] full format: {r5d!r}")
