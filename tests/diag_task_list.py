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

# 4) Run full _task_list_code via canister_exec
code = _task_list_code()
print(f"[DIAG4] code length: {len(code)}")
r4 = canister_exec(code, c, n)
print(f"[DIAG4] canister_exec result: {r4!r}")

# 5) Run simplified list code (without _FMT_NS/_LAST_EXEC_TS helpers)
simple_list = (
    _TASK_RESOLVE +
    "if 'Task' not in dir():\n"
    "    print('TASK_NOT_AVAILABLE')\n"
    "else:\n"
    "    _cnt = Task.count()\n"
    "    print(f'TASK_COUNT={_cnt}')\n"
    "    for _t in Task.instances():\n"
    "        print(f'  TASK: id={_t._id} name={_t.name} status={_t.status}')\n"
    "    if _cnt == 0:\n"
    "        print('No tasks.')\n"
)
r5 = canister_exec(simple_list, c, n)
print(f"[DIAG5] simplified list: {r5!r}")

# 6) Test _FMT_NS and _LAST_EXEC_TS in isolation
from basilisk.bosh import _handle_magic
r6 = _handle_magic("%ps", c, n)
print(f"[DIAG6] _handle_magic %%ps: {r6!r}")
