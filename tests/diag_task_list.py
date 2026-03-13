#!/usr/bin/env python3
"""Diagnostic script to debug task list empty-string issue in CI."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from basilisk.bosh import canister_exec, _TASK_RESOLVE

c = os.environ["BOSH_TEST_CANISTER"]
n = os.environ["BOSH_TEST_NETWORK"]

# Ensure entities are defined
canister_exec(_TASK_RESOLVE + "print('resolve_ok')", c, n)

# Key diagnostic: check max_id vs count vs instances
r = canister_exec(
    "try:\n"
    "    _mid = Task.max_id()\n"
    "    _cnt = Task.count()\n"
    "    _insts = Task.instances()\n"
    "    print(f'max_id={_mid} count={_cnt} instances_len={len(_insts)}')\n"
    "    # Try loading by ID directly\n"
    "    for i in range(1, _mid + 1):\n"
    "        _e = Task.load(str(i))\n"
    "        print(f'  load({i}): {_e}')\n"
    "    # Check db keys directly\n"
    "    _db = Task.db()\n"
    "    _tn = Task.get_full_type_name()\n"
    "    print(f'type_name={_tn!r}')\n"
    "    print(f'db._system/Task_id={_db.load(\"_system\", \"Task_id\")!r}')\n"
    "    print(f'db._system/Task_count={_db.load(\"_system\", \"Task_count\")!r}')\n"
    "    # Check what's stored at Task/1\n"
    "    print(f'db.load(Task,1)={_db.load(\"Task\", \"1\")!r}')\n"
    "    print(f'db.load(Task,0)={_db.load(\"Task\", \"0\")!r}')\n"
    "    # Check entity_types registry\n"
    "    print(f'entity_types_keys={list(_db._entity_types.keys())[:20]}')\n"
    "except Exception as e:\n"
    "    import traceback; traceback.print_exc()\n"
    "    print(f'ERROR: {e}')\n",
    c, n)
print(f"[DIAG] {r}")
