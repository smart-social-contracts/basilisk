#!/usr/bin/env python3
"""
Basilisk Shell

A shell interpreter for IC canisters running basilisk.
Commands are executed inside the canister via execute_code_shell.

Usage:
    basilisk shell --canister <id> [--network <net>]           Interactive mode
    basilisk shell --canister <id> [--network <net>] -c "code" One-shot mode
    basilisk shell --canister <id> [--network <net>] script.py  File mode
    echo "print(42)" | basilisk shell --canister <id>           Pipe mode

Shell commands:
    %ls [path]    List canister filesystem
    %cat <file>   Show file contents on canister
    %mkdir <path> Create directory on canister
    %wget <url> <dest>  Download a URL into canister filesystem
    %task         Task management (create, add-step, start, stop, etc.)
    %run <file>   Execute a file from canister filesystem
    %get <remote> [local]  Download file from canister
    %put <local> [remote]  Upload file to canister
    %who          List variables in the remote namespace
    %db types     List entity types with counts
    %db list <Type> [N]  List instances (default 20)
    %db show <Type> <id> Show full entity as JSON
    %db search <Type> <field>=<value>  Search entities
    %db export <Type> [file.json]  Export entities as JSON
    %db import <file.json>  Import entities from JSON (upsert)
    %db delete <Type> <id>  Delete a single entity
    %db count|dump|clear    Count / dump / clear database
    %wallet <token> balance       Check canister token balance
    %wallet <token> deposit       Show deposit address
    %wallet <token> transfer <amount> <to>  Transfer tokens from canister
    %wallet result                Check last transfer result
    %vetkey pubkey [--scope <s>]  Get vetKD public key
    %vetkey derive <tpk_hex> [--scope <s>] [--input <s>]  Derive encrypted vetKey
    %vetkey encrypt <file|text>   Encrypt file or text with vetKeys
    %vetkey decrypt <file|text>   Decrypt file or text with vetKeys
    %vetkey result                Check last vetkey result
    %info         Show canister info (principal, cycles, status, deploy)
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
# Version / git info (client-side)
# ---------------------------------------------------------------------------

def _get_basilisk_version() -> str:
    """Return the installed basilisk package version."""
    try:
        from basilisk import __version__
        return __version__
    except Exception:
        return "unknown"


def _get_git_info() -> dict:
    """Return commit hash and datetime from the basilisk package source."""
    info = {}
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    repo_dir = os.path.dirname(pkg_dir)  # parent of basilisk/
    try:
        r = subprocess.run(
            ["git", "log", "-1", "--format=%H %aI"],
            capture_output=True, text=True, timeout=5,
            cwd=repo_dir,
        )
        if r.returncode == 0:
            parts = r.stdout.strip().split(" ", 1)
            if len(parts) == 2:
                info["commit"] = parts[0][:8]
                info["commit_date"] = parts[1]
    except Exception:
        pass
    return info


# ---------------------------------------------------------------------------
# Candid parsing
# ---------------------------------------------------------------------------

def _parse_candid(output: str) -> str:
    """Parse a Candid-encoded string response from icp into plain text."""
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

def _is_transient_icp_error(stderr: str) -> bool:
    s = (stderr or "").lower()
    transient_markers = [
        "temporary failure in name resolution",
        "failed to lookup address information",
        "dns error",
        "client error (connect)",
        "an error happened during communication with the replica",
        "error sending request for url",
        "timed out",
        "timeout",
        "connection refused",
        "network is unreachable",
        "service unavailable",
        "gateway timeout",
    ]
    return any(m in s for m in transient_markers)


def _run_icp_with_retries(
    cmd: list[str],
    *,
    timeout_s: int,
    attempts: int = 5,
) -> subprocess.CompletedProcess:
    last: subprocess.CompletedProcess | None = None
    for attempt in range(attempts):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            if attempt >= attempts - 1:
                raise
            _time.sleep(min(2**attempt, 8))
            continue

        last = r
        if r.returncode == 0:
            return r
        if not _is_transient_icp_error(r.stderr):
            return r
        if attempt >= attempts - 1:
            return r
        _time.sleep(min(2**attempt, 8))

    return last  # type: ignore[return-value]

def canister_exec(code: str, canister: str, network: str = None) -> str:
    """Send Python code to the canister and return the output."""
    escaped = code.replace('"', '\\"').replace("\n", "\\n")
    cmd = ["icp", "canister", "call"]
    if network:
        cmd.extend(["--network", network])
    cmd.extend([canister, "execute_code_shell", f'("{escaped}")'])

    try:
        r = _run_icp_with_retries(cmd, timeout_s=120)
        if r.returncode != 0:
            return f"[icp error] {r.stderr.strip()}"
        return _parse_candid(r.stdout)
    except subprocess.TimeoutExpired:
        return "[error] canister call timed out (120s)"
    except FileNotFoundError:
        return "[error] icp not found — install the ICP CLI: npm install -g @icp-sdk/icp-cli"


# ---------------------------------------------------------------------------
# Magic commands
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Code preamble that resolves the Task entity class at runtime.
# Priority: 1) already in namespace (injected by downstream app),
#           2) define from ic_python_db on the fly, 3) unavailable.
# ---------------------------------------------------------------------------
_TASK_RESOLVE = (
    "if 'Codex' not in dir() or 'Task' not in dir():\n"
    "    _Task = None\n"
    "    try:\n"
    "        from ic_python_db import Entity, String, Integer, Boolean, OneToMany, ManyToOne, OneToOne, TimestampedMixin\n"
    "        class Codex(Entity, TimestampedMixin):\n"
    "            __alias__ = 'name'\n"
    "            name = String()\n"
    "            url = String()\n"
    "            checksum = String()\n"
    "            calls = OneToMany('Call', 'codex')\n"
    "            @property\n"
    "            def code(self):\n"
    "                pending = getattr(self, '_pending_code', None)\n"
    "                if pending is not None: return pending\n"
    "                if self.name:\n"
    "                    try:\n"
    "                        with open(f'/{self.name}', 'r') as f: return f.read()\n"
    "                    except (FileNotFoundError, OSError): pass\n"
    "                return None\n"
    "            @code.setter\n"
    "            def code(self, value):\n"
    "                if value is not None:\n"
    "                    if self.name:\n"
    "                        try:\n"
    "                            with open(f'/{self.name}', 'w') as f: f.write(str(value))\n"
    "                        except OSError: pass\n"
    "                        if hasattr(self, '_pending_code'): del self._pending_code\n"
    "                    else: self._pending_code = value\n"
    "            def _save(self):\n"
    "                pending = getattr(self, '_pending_code', None)\n"
    "                if pending is not None and self.name:\n"
    "                    try:\n"
    "                        with open(f'/{self.name}', 'w') as f: f.write(str(pending))\n"
    "                    except OSError: pass\n"
    "                    del self._pending_code\n"
    "                return super()._save()\n"
    "        class Call(Entity, TimestampedMixin):\n"
    "            is_async = Boolean()\n"
    "            codex = ManyToOne('Codex', 'calls')\n"
    "            task_step = OneToOne('TaskStep', 'call')\n"
    "        class TaskExecution(Entity, TimestampedMixin):\n"
    "            __alias__ = 'name'\n"
    "            name = String(max_length=256)\n"
    "            task = ManyToOne('Task', 'executions')\n"
    "            status = String(max_length=50, default='idle')\n"
    "            result = String(max_length=5000)\n"
    "        class TaskStep(Entity, TimestampedMixin):\n"
    "            call = OneToOne('Call', 'task_step')\n"
    "            status = String(max_length=32, default='pending')\n"
    "            run_next_after = Integer(default=0)\n"
    "            timer_id = Integer()\n"
    "            task = ManyToOne('Task', 'steps')\n"
    "        class TaskSchedule(Entity, TimestampedMixin):\n"
    "            __alias__ = 'name'\n"
    "            name = String(max_length=256)\n"
    "            disabled = Boolean()\n"
    "            task = ManyToOne('Task', 'schedules')\n"
    "            run_at = Integer()\n"
    "            repeat_every = Integer()\n"
    "            last_run_at = Integer()\n"
    "        class Task(Entity, TimestampedMixin):\n"
    "            __alias__ = 'name'\n"
    "            name = String(max_length=256)\n"
    "            metadata = String(max_length=256)\n"
    "            status = String(max_length=32, default='pending')\n"
    "            step_to_execute = Integer(default=0)\n"
    "            steps = OneToMany('TaskStep', 'task')\n"
    "            schedules = OneToMany('TaskSchedule', 'task')\n"
    "            executions = OneToMany('TaskExecution', 'task')\n"
    "        _Task = Task\n"
    "    except ImportError:\n"
    "        pass\n"
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
}


# ---------------------------------------------------------------------------
# %db subcommand handlers
# ---------------------------------------------------------------------------

_DB_USAGE = (
    "Usage:\n"
    "  %db types                         List entity types with counts\n"
    "  %db list <Type> [N]               List instances (default 20)\n"
    "  %db show <Type> <id>              Show full entity as JSON\n"
    "  %db search <Type> <field>=<val>   Search entities by field value\n"
    "  %db export <Type> [file.json]     Export entities as JSON\n"
    "  %db import <file.json>            Import entities from JSON (upsert)\n"
    "  %db delete <Type> <id>            Delete a single entity\n"
    "  %db count                         Count total entries\n"
    "  %db dump                          Dump entire database as JSON\n"
    "  %db clear                         Clear entire database\n"
)


def _db_types_code() -> str:
    """Generate on-canister code for %db types."""
    return (
        "import json as _json\n"
        "from ic_python_db import Database as _DB\n"
        "_db = _DB.get_instance()\n"
        "_types = {}\n"
        "_seen = set()\n"
        "for _et in _db._entity_types.values():\n"
        "    _name = _et.__name__\n"
        "    if _name in _seen:\n"
        "        continue\n"
        "    _seen.add(_name)\n"
        "    if hasattr(_et, 'count'):\n"
        "        try:\n"
        "            _types[_name] = _et.count()\n"
        "        except Exception:\n"
        "            _types[_name] = 0\n"
        "_sorted = sorted(_types.items(), key=lambda x: -x[1])\n"
        "_hdr = '  ' + 'Entity'.ljust(20) + 'Count'.rjust(6)\n"
        "print(_hdr)\n"
        "print('  ' + '-' * 28)\n"
        "for _n, _c in _sorted:\n"
        "    print('  ' + _n.ljust(20) + str(_c).rjust(6))\n"
        "_tot = sum(_types.values())\n"
        "_nt = len(_types)\n"
        "print()\n"
        "print('  Total: ' + str(_tot) + ' entities across ' + str(_nt) + ' types')\n"
    )


def _db_list_code(entity_type: str, limit: int = 20) -> str:
    """Generate on-canister code for %db list <Type> [N]."""
    esc_type = entity_type.replace("'", "\\'")
    return (
        "import json as _json\n"
        "from ic_python_db import Database as _DB\n"
        "_db = _DB.get_instance()\n"
        f"_type_name = '{esc_type}'\n"
        "_cls = None\n"
        "for _tn, _tc in _db._entity_types.items():\n"
        "    if _tc.__name__ == _type_name or _tn == _type_name:\n"
        "        _cls = _tc\n"
        "        break\n"
        "if _cls is None:\n"
        f"    print('Unknown entity type: {esc_type}')\n"
        "else:\n"
        f"    _limit = {limit}\n"
        "    _instances = _cls.instances()\n"
        "    _total = len(_instances)\n"
        "    _shown = _instances[:_limit]\n"
        "    _alias = getattr(_cls, '__alias__', None)\n"
        "    for _e in _shown:\n"
        "        _s = _e.serialize()\n"
        "        _id = _s.get('_id', '?')\n"
        "        _alias_val = ''\n"
        "        if _alias and _alias in _s:\n"
        "            _alias_val = str(_s[_alias])[:40]\n"
        "        _fields = []\n"
        "        for _k, _v in _s.items():\n"
        "            if _k.startswith('_') or _k == _alias:\n"
        "                continue\n"
        "            _sv = str(_v)[:30]\n"
        "            _fields.append(f'{_k}={_sv}')\n"
        "            if len(_fields) >= 3:\n"
        "                break\n"
        "        _fstr = '  '.join(_fields)\n"
        "        if _alias_val:\n"
        "            print(f'  #{_id:<5}  {_alias_val:<40}  {_fstr}')\n"
        "        else:\n"
        "            print(f'  #{_id:<5}  {_fstr}')\n"
        "    if _total > _limit:\n"
        f"        print(f'  ... and {{_total - _limit}} more ({{_total}} total)')\n"
        "    elif _total == 0:\n"
        f"        print('No {esc_type} entities found.')\n"
        "    else:\n"
        "        print(f'  ({{_total}} total)')\n"
    )


def _db_show_code(entity_type: str, entity_id: str) -> str:
    """Generate on-canister code for %db show <Type> <id>."""
    esc_type = entity_type.replace("'", "\\'")
    esc_id = entity_id.replace("'", "\\'")
    return (
        "import json as _json\n"
        "from ic_python_db import Database as _DB\n"
        "_db = _DB.get_instance()\n"
        f"_type_name = '{esc_type}'\n"
        f"_eid = '{esc_id}'\n"
        "_cls = None\n"
        "for _tn, _tc in _db._entity_types.items():\n"
        "    if _tc.__name__ == _type_name or _tn == _type_name:\n"
        "        _cls = _tc\n"
        "        break\n"
        "if _cls is None:\n"
        f"    print('Unknown entity type: {esc_type}')\n"
        "else:\n"
        "    _e = _cls[_eid]\n"
        "    if _e is None:\n"
        f"        print('{esc_type}#{esc_id} not found.')\n"
        "    else:\n"
        "        _s = _e.serialize()\n"
        "        print(_json.dumps(_s, indent=2, default=str))\n"
    )


def _db_search_code(entity_type: str, field: str, value: str) -> str:
    """Generate on-canister code for %db search <Type> <field>=<value>."""
    esc_type = entity_type.replace("'", "\\'")
    esc_field = field.replace("'", "\\'")
    esc_value = value.replace("'", "\\'")
    return (
        "import json as _json\n"
        "from ic_python_db import Database as _DB\n"
        "_db = _DB.get_instance()\n"
        f"_type_name = '{esc_type}'\n"
        f"_field = '{esc_field}'\n"
        f"_value = '{esc_value}'\n"
        "_cls = None\n"
        "for _tn, _tc in _db._entity_types.items():\n"
        "    if _tc.__name__ == _type_name or _tn == _type_name:\n"
        "        _cls = _tc\n"
        "        break\n"
        "if _cls is None:\n"
        f"    print('Unknown entity type: {esc_type}')\n"
        "else:\n"
        "    _results = []\n"
        "    for _e in _cls.instances():\n"
        "        _s = _e.serialize()\n"
        "        _fv = str(_s.get(_field, ''))\n"
        "        if _fv == _value or _value.lower() in _fv.lower():\n"
        "            _results.append(_s)\n"
        "    if not _results:\n"
        f"        print('No {esc_type} entities matching {esc_field}={esc_value}')\n"
        "    else:\n"
        "        print(f'Found {{len(_results)}} match(es):')\n"
        "        for _s in _results:\n"
        "            _id = _s.get('_id', '?')\n"
        "            _fields = [f'{_k}={str(_v)[:30]}' for _k, _v in _s.items() if not _k.startswith('_')][:4]\n"
        "            print(f'  #{_id}  {\"  \".join(_fields)}')\n"
    )


def _db_export_code(entity_type: str) -> str:
    """Generate on-canister code for %db export <Type>."""
    esc_type = entity_type.replace("'", "\\'")
    return (
        "import json as _json\n"
        "from ic_python_db import Database as _DB, Entity as _Entity\n"
        "_db = _DB.get_instance()\n"
        f"_type_name = '{esc_type}'\n"
        "_cls = None\n"
        "for _tn, _tc in _db._entity_types.items():\n"
        "    if _tc.__name__ == _type_name or _tn == _type_name:\n"
        "        _cls = _tc\n"
        "        break\n"
        "if _cls is None:\n"
        f"    print('Unknown entity type: {esc_type}')\n"
        "else:\n"
        "    _all = [_e.serialize() for _e in _cls.instances()]\n"
        "    import base64 as _b64\n"
        "    _payload = _json.dumps(_all, default=str)\n"
        "    print('__DB_EXPORT__' + _b64.b64encode(_payload.encode()).decode())\n"
    )


def _db_import_code(b64_data: str) -> str:
    """Generate on-canister code for %db import. Data is base64-encoded JSON."""
    return (
        "import json as _json, base64 as _b64\n"
        "from ic_python_db import Entity as _Entity\n"
        f"_raw = _b64.b64decode('{b64_data}').decode()\n"
        "_records = _json.loads(_raw)\n"
        "if not isinstance(_records, list):\n"
        "    _records = [_records]\n"
        "_ok = 0\n"
        "_fail = 0\n"
        "_errors = []\n"
        "for _rec in _records:\n"
        "    try:\n"
        "        _Entity.deserialize(_rec, level=1)\n"
        "        _ok += 1\n"
        "    except Exception as _e:\n"
        "        _fail += 1\n"
        "        _errors.append(f'{_rec.get(\"_type\",\"?\")}#{_rec.get(\"_id\",\"?\")}: {_e}')\n"
        "_Entity._context.clear()\n"
        "print(f'Imported {_ok} entities ({_fail} failed)')\n"
        "if _errors:\n"
        "    for _err in _errors[:10]:\n"
        "        print(f'  ERROR: {_err}')\n"
    )


def _db_delete_code(entity_type: str, entity_id: str) -> str:
    """Generate on-canister code for %db delete <Type> <id>."""
    esc_type = entity_type.replace("'", "\\'")
    esc_id = entity_id.replace("'", "\\'")
    return (
        "from ic_python_db import Database as _DB\n"
        "_db = _DB.get_instance()\n"
        f"_type_name = '{esc_type}'\n"
        f"_eid = '{esc_id}'\n"
        "_cls = None\n"
        "for _tn, _tc in _db._entity_types.items():\n"
        "    if _tc.__name__ == _type_name or _tn == _type_name:\n"
        "        _cls = _tc\n"
        "        break\n"
        "if _cls is None:\n"
        f"    print('Unknown entity type: {esc_type}')\n"
        "else:\n"
        "    _e = _cls[_eid]\n"
        "    if _e is None:\n"
        f"        print('{esc_type}#{esc_id} not found.')\n"
        "    else:\n"
        "        _e.delete()\n"
        f"        print('Deleted {esc_type}#{esc_id}')\n"
    )


def _handle_db(args: str, canister: str, network: str) -> str:
    """Dispatch %db subcommands. Returns canister output string."""
    parts = args.strip().split(None, 2)
    subcmd = parts[0] if parts else "help"
    rest = parts[1].strip() if len(parts) > 1 else ""
    rest2 = parts[2].strip() if len(parts) > 2 else ""

    if subcmd == "help":
        return _DB_USAGE

    if subcmd == "types":
        return canister_exec(_db_types_code(), canister, network)

    if subcmd == "count":
        code = (
            "from ic_python_db import Database; db = Database.get_instance(); "
            "print(f'{sum(1 for k in db._db_storage.keys() if not k.startswith(\"_\"))} entries')"
        )
        return canister_exec(code, canister, network)

    if subcmd == "dump":
        code = "from ic_python_db import Database; print(Database.get_instance().dump_json(pretty=True))"
        return canister_exec(code, canister, network)

    if subcmd == "clear":
        code = "from ic_python_db import Database; Database.get_instance().clear(); print('Database cleared.')"
        return canister_exec(code, canister, network)

    if subcmd == "list":
        if not rest:
            return "Usage: %db list <Type> [N]"
        # rest could be "User 20" or just "User"
        list_parts = rest.split(None, 1)
        if rest2:
            list_parts = [rest, rest2]
        entity_type = list_parts[0]
        limit = 20
        if len(list_parts) > 1:
            try:
                limit = int(list_parts[1])
            except ValueError:
                pass
        return canister_exec(_db_list_code(entity_type, limit), canister, network)

    if subcmd == "show":
        if not rest:
            return "Usage: %db show <Type> <id>"
        show_parts = rest.split(None, 1)
        if rest2:
            show_parts = [rest, rest2]
        if len(show_parts) < 2:
            return "Usage: %db show <Type> <id>"
        return canister_exec(_db_show_code(show_parts[0], show_parts[1]), canister, network)

    if subcmd == "search":
        if not rest:
            return "Usage: %db search <Type> <field>=<value>"
        # Parse: "User name=Alice"
        search_parts = rest.split(None, 1)
        if rest2:
            search_parts = [rest, rest2]
        if len(search_parts) < 2 or "=" not in search_parts[1]:
            return "Usage: %db search <Type> <field>=<value>"
        entity_type = search_parts[0]
        field, _, value = search_parts[1].partition("=")
        return canister_exec(_db_search_code(entity_type, field.strip(), value.strip()), canister, network)

    if subcmd == "export":
        if not rest:
            return "Usage: %db export <Type> [file.json]"
        export_parts = rest.split(None, 1)
        if rest2:
            export_parts = [rest, rest2]
        entity_type = export_parts[0]
        out_file = export_parts[1] if len(export_parts) > 1 else None

        result = canister_exec(_db_export_code(entity_type), canister, network)
        if result is None:
            return "[error] no response from canister"

        # Parse the export marker
        for line in result.strip().split("\n"):
            if line.startswith("__DB_EXPORT__"):
                import base64
                import json
                payload = base64.b64decode(line[len("__DB_EXPORT__"):]).decode()
                records = json.loads(payload)

                if out_file:
                    os.makedirs(os.path.dirname(out_file) or ".", exist_ok=True)
                    with open(out_file, "w") as f:
                        json.dump(records, f, indent=2, default=str)
                    return f"Exported {len(records)} {entity_type} entities -> {out_file}"
                else:
                    return json.dumps(records, indent=2, default=str)

        # No marker found — return raw output (likely an error message)
        return result

    if subcmd == "import":
        if not rest:
            return "Usage: %db import <file.json>"
        import_file = rest
        if rest2:
            import_file = rest  # first arg is the file

        try:
            with open(import_file, "r") as f:
                data = f.read()
        except FileNotFoundError:
            return f"[error] file not found: {import_file}"

        # Validate JSON
        import json
        try:
            records = json.loads(data)
        except json.JSONDecodeError as e:
            return f"[error] invalid JSON: {e}"

        if not isinstance(records, list):
            records = [records]

        # Import in batches to avoid message size limits
        batch_size = 50
        total_ok = 0
        total_fail = 0
        all_errors = []

        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            import base64
            b64 = base64.b64encode(json.dumps(batch, default=str).encode()).decode()
            result = canister_exec(_db_import_code(b64), canister, network)
            if result:
                for line in result.strip().split("\n"):
                    if line.startswith("Imported "):
                        # Parse "Imported N entities (M failed)"
                        import re as _re
                        m = _re.match(r"Imported (\d+) entities \((\d+) failed\)", line)
                        if m:
                            total_ok += int(m.group(1))
                            total_fail += int(m.group(2))
                    elif line.strip().startswith("ERROR:"):
                        all_errors.append(line.strip())

        summary = f"Imported {total_ok} entities ({total_fail} failed) from {import_file}"
        if all_errors:
            summary += "\n" + "\n".join(all_errors[:10])
        return summary

    if subcmd == "delete":
        if not rest:
            return "Usage: %db delete <Type> <id>"
        del_parts = rest.split(None, 1)
        if rest2:
            del_parts = [rest, rest2]
        if len(del_parts) < 2:
            return "Usage: %db delete <Type> <id>"
        return canister_exec(_db_delete_code(del_parts[0], del_parts[1]), canister, network)

    return f"Unknown db command: {subcmd}\n\n" + _DB_USAGE


def _canister_info(canister: str, network: str) -> str:
    """Gather comprehensive canister information from on-canister data + icp."""
    lines = []

    # 1) On-canister info: principal, cycles, IC time
    on_canister_code = (
        "import json as _json\n"
        "_d = {}\n"
        "_d['principal'] = str(ic.caller())\n"
        "_d['cycles'] = ic.canister_balance()\n"
        "_d['ic_time'] = ic.time()\n"
        "print('__INFO__' + _json.dumps(_d))\n"
    )
    result = canister_exec(on_canister_code, canister, network)
    info = {}
    for ln in (result or "").split("\n"):
        if ln.startswith("__INFO__"):
            try:
                import json
                info = json.loads(ln[len("__INFO__"):])
            except Exception:
                pass
            break

    lines.append(f"  Canister  : {canister}")
    lines.append(f"  Network   : {network or 'local'}")
    lines.append(f"  Principal : {info.get('principal', 'unknown')}")
    cycles = info.get("cycles")
    if cycles is not None:
        lines.append(f"  Cycles    : {cycles:,}")

    # 2) icp canister info — module hash, controllers
    cmd_info = ["icp", "canister", "info"]
    if network:
        cmd_info.extend(["--network", network])
    cmd_info.append(canister)
    try:
        r = subprocess.run(cmd_info, capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            for sline in (r.stdout + r.stderr).splitlines():
                lo = sline.strip().lower()
                val = sline.strip().split(":", 1)[1].strip() if ":" in sline else ""
                if lo.startswith("controllers:"):
                    lines.append(f"  Controllers: {val}")
                elif lo.startswith("module hash:"):
                    lines.append(f"  Module    : {val}")
    except Exception:
        pass

    # 3) icp canister status — status, memory, idle burn
    cmd_status = ["icp", "canister", "status"]
    if network:
        cmd_status.extend(["--network", network])
    cmd_status.append(canister)
    try:
        r2 = subprocess.run(cmd_status, capture_output=True, text=True, timeout=30)
        if r2.returncode == 0:
            for sline in (r2.stdout + r2.stderr).splitlines():
                lo = sline.strip().lower()
                val = sline.strip().split(":", 1)[1].strip() if ":" in sline else ""
                if lo.startswith("status:"):
                    lines.append(f"  Status    : {val}")
                elif lo.startswith("memory size:"):
                    lines.append(f"  Memory    : {val}")
                elif lo.startswith("idle cycles burned per day:"):
                    lines.append(f"  Idle burn : {val}")
    except Exception:
        pass

    return "\n".join(lines)


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

# Helper snippet: convert seconds timestamp to UTC string.
_FMT_S = (
    "def _fmt_s(s):\n"
    "    if not s: return ''\n"
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
        "    _any = False\n"
        "    for _t in Task.instances():\n"
        "        _any = True\n"
        "        _scheds = list(_t.schedules)\n"
        "        _s = _scheds[0] if _scheds else None\n"
        "        _rep = f'every {_s.repeat_every}s' if _s and _s.repeat_every else '     -'\n"
        "        _dis = 'disabled' if (_s and _s.disabled) else 'enabled ' if _s else '   -   '\n"
        "        _last = _last_exec_ts(_t)\n"
        "        _last_str = f' | last={_last}' if _last else ''\n"
        "        print(f'{str(_t._id):>3} | {_t.status:<10} | repeat={_rep} | {_dis} | {_t.name}{_last_str}')\n"
        "    if not _any: print('No tasks.')\n"
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


def _command_to_code(cmd: str):
    """Translate a simple shell-like command into (code_str, is_async).

    Supported commands:
        wget <url> <dest>   → async step that downloads url to /dest
        run <path>          → sync step that executes /path

    Returns ``(code_string, is_async)`` or ``None`` if the command is
    not recognised.
    """
    parts = cmd.strip().split()
    if not parts:
        return None
    verb = parts[0].lower()

    if verb == "wget" and len(parts) == 3:
        url = parts[1]
        dest = parts[2]
        if not dest.startswith("/"):
            dest = "/" + dest
        esc_url = url.replace("'", "\\'")
        esc_dest = dest.replace("'", "\\'")
        code = (
            "def async_task():\n"
            f"    yield from wget('{esc_url}', '{esc_dest}')\n"
        )
        return code, True

    if verb == "run" and len(parts) == 2:
        path = parts[1]
        if not path.startswith("/"):
            path = "/" + path
        esc_path = path.replace("'", "\\'")
        code = f"run('{esc_path}')"
        return code, False

    return None


def _task_add_step_code(rest: str) -> str:
    """Code for: %task add-step <id|name> [--code "..."|--file <path>|--command "..."] [--delay Ns] [--async]

    Adds a new step to an existing task: Codex → Call → TaskStep.
    --async marks the step for async execution (code must define async_task()).
    --delay N inserts a wait of N seconds before this step runs.
    --command translates a simple command (wget, run) into the appropriate code.
    """
    # Parse --async flag
    is_async = '--async' in rest
    if is_async:
        rest = rest.replace('--async', '', 1).strip()

    # Parse --delay N
    delay_match = re.search(r'--delay\s+(\d+)', rest)
    delay = int(delay_match.group(1)) if delay_match else 0
    if delay_match:
        rest = rest[:delay_match.start()] + rest[delay_match.end():]

    # Parse --file <path>
    file_match = re.search(r'--file\s+(\S+)', rest)
    task_file = None
    if file_match:
        task_file = file_match.group(1)
        rest = rest[:file_match.start()] + rest[file_match.end():]

    # Parse --command "..." (supports single or double quotes)
    cmd_match = re.search(r"""--command\s+(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')""", rest)
    task_command = None
    if cmd_match:
        task_command = cmd_match.group(1) if cmd_match.group(1) is not None else cmd_match.group(2)
        rest = rest[:cmd_match.start()] + rest[cmd_match.end():]

    # Parse --code "..." (supports single or double quotes)
    code_match = re.search(r"""--code\s+(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')""", rest)
    task_code = None
    if code_match:
        task_code = code_match.group(1) if code_match.group(1) is not None else code_match.group(2)
        task_code = task_code.replace('\\"', '"').replace("\\'", "'")
        rest = rest[:code_match.start()] + rest[code_match.end():]

    # --command translates a simple command into code + async flag
    if task_command and not task_code:
        result = _command_to_code(task_command)
        if result is None:
            return None  # unrecognised command
        task_code, cmd_is_async = result
        # Command determines async-ness unless --async was explicit
        if not is_async:
            is_async = cmd_is_async

    # --file generates an exec(open(...).read()) wrapper
    if task_file and not task_code:
        esc_file = task_file.replace("'", "\\'")
        task_code = f"exec(open('{esc_file}').read())"

    tid = rest.strip()
    if not tid or task_code is None:
        return None  # signal usage error

    esc_tid = tid.replace("'", "\\'")

    import base64
    b64 = base64.b64encode(task_code.encode()).decode()
    code = (
        _TASK_RESOLVE + _TASK_UNAVAILABLE +
        "if 'Task' in dir():\n"
        + _TASK_FIND.format(tid=esc_tid) +
        "    if not _t:\n"
        f"        print('Task not found: {esc_tid}')\n"
        "    else:\n"
        "        import base64 as _b64\n"
        f"        _code_bytes = _b64.b64decode('{b64}')\n"
        "        _code_str = _code_bytes.decode()\n"
        "        _step_n = len(list(_t.steps))\n"
        "        _codex = Codex(name=f'codex_{_t.name}_step{_step_n}')\n"
        "        _codex.code = _code_str\n"
        f"        _call = Call(codex=_codex, is_async={'True' if is_async else 'False'})\n"
        f"        _step = TaskStep(call=_call, task=_t, status='pending', run_next_after={delay})\n"
        "        _kind = 'async' if _call.is_async else 'sync'\n"
        "        print(f'Added step {_step_n} ({_kind}) to task {_t._id}: {_t.name}')\n"
    )
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
        _FMT_NS + _FMT_S +
        "if 'Task' in dir():\n"
        + _TASK_FIND.format(tid=esc_tid) +
        "    if not _t:\n"
        f"        print('Task not found: {esc_tid}')\n"
        "    else:\n"
        "        try:\n"
        "            from ic_python_logging import get_logs as _get_logs\n"
        "        except ImportError:\n"
        "            _get_logs = None\n"
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
        "                _sa = getattr(_e, 'started_at', 0) or 0\n"
        "                _dt = _fmt_s(_sa) if _sa else _fmt_ns(getattr(_e, '_timestamp_created', None) or getattr(_e, '_timestamp_updated', None))\n"
        '                print(f\'  #{_e._id} | {_e.status or "idle":<10} | {_dt} | {_e.name}\')\n'
        "                if _res: print(f'    {_res}')\n"
        "                if _get_logs:\n"
        "                    _log_name = 'task_%s_%s' % (_e.task._id, _e._id)\n"
        "                    _logs = _get_logs(logger_name=_log_name)\n"
        "                    if _logs:\n"
        "                        for _l in _logs[-5:]:\n"
        "                            _msg = _l.get('message', '') if isinstance(_l, dict) else str(_l)\n"
        "                            _lvl = _l.get('level', '') if isinstance(_l, dict) else ''\n"
        "                            print(f'      [{_lvl}] {_msg}')\n"
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
        "                _is_async = _cur.call.is_async if _cur.call else False\n"
        "                if _is_async:\n"
        "                    print(f'Step {_si} is async — use %task start for async steps')\n"
        "                    _all_ok = False\n"
        "                    break\n"
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
    Supports both sync and async steps — async steps define async_task()
    which returns a generator driven by the IC runtime (HTTP outcalls, etc.).
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
        #
        # Factory function — creates an isolated closure scope per task so
        # multiple concurrent tasks don't overwrite each other's callbacks.
        #
        "            def _make_task_cbs(_task_id):\n"
        #
        # Helper: advance to next step or complete the task
        #
        "                def _chain_next(_task, _si, _all_steps):\n"
        "                    if _task.status == 'failed':\n"
        "                        return\n"
        "                    _task.step_to_execute = _si + 1\n"
        "                    if _task.step_to_execute < len(_all_steps):\n"
        "                        _next = _all_steps[_task.step_to_execute]\n"
        "                        _delay = _next.run_next_after or 0\n"
        "                        _next_async = _next.call.is_async if _next.call else False\n"
        "                        if _next_async:\n"
        "                            ic.set_timer(_delay, _exec_async)\n"
        "                        else:\n"
        "                            ic.set_timer(_delay, _exec_sync)\n"
        "                    else:\n"
        "                        _task.status = 'completed'\n"
        "                        _task.step_to_execute = 0\n"
        "                        for _s2 in _all_steps: _s2.status = 'pending'\n"
        "                        for _sched in _task.schedules:\n"
        "                            if _sched.repeat_every and _sched.repeat_every > 0 and not _sched.disabled:\n"
        "                                _task.status = 'pending'\n"
        "                                _first_async = _all_steps[0].call.is_async if _all_steps[0].call else False\n"
        "                                _cb = _exec_async if _first_async else _exec_sync\n"
        "                                ic.set_timer(_sched.repeat_every, _cb)\n"
        "                                break\n"
        #
        # Helpers injected into task step namespaces.
        # Defined inline so they work with any canister WASM version
        # (the basilisk.io / basilisk.run module-level equivalents
        # are only available after a canister rebuild).
        #
        "                def wget(url, dest, transform_func='http_transform', cycles=30_000_000_000, max_bytes=2_000_000):\n"
        "                    from basilisk.canisters.management import management_canister\n"
        "                    resp = yield management_canister.http_request({\n"
        "                        'url': url, 'max_response_bytes': max_bytes,\n"
        "                        'method': {'get': None},\n"
        "                        'headers': [{'name': 'User-Agent', 'value': 'Basilisk/1.0'}, {'name': 'Accept-Encoding', 'value': 'identity'}],\n"
        "                        'body': None,\n"
        "                        'transform': {'function': (ic.id(), transform_func), 'context': bytes()},\n"
        "                    }).with_cycles(cycles)\n"
        "                    if 'Ok' in resp:\n"
        "                        body = resp['Ok']['body']\n"
        "                        import os\n"
        "                        parent = os.path.dirname(dest)\n"
        "                        if parent and parent != '/':\n"
        "                            os.makedirs(parent, exist_ok=True)\n"
        "                        with open(dest, 'wb') as f:\n"
        "                            f.write(body if isinstance(body, bytes) else body.encode('utf-8'))\n"
        "                        return f'Downloaded {len(body)} bytes to {dest}'\n"
        "                    else:\n"
        "                        raise RuntimeError(f'Download failed: {resp}')\n"
        "                def run(path):\n"
        "                    exec(compile(open(path).read(), path, 'exec'))\n"
        #
        # Sync step callback — executes code with exec()
        #
        "                def _exec_sync():\n"
        "                    import io, sys, traceback\n"
        "                    _task = Task.load(_task_id)\n"
        "                    if not _task or _task.status == 'cancelled':\n"
        "                        return\n"
        "                    _task.status = 'running'\n"
        "                    _si = _task.step_to_execute\n"
        "                    _all_steps = list(_task.steps)\n"
        "                    if _si >= len(_all_steps):\n"
        "                        _si = 0\n"
        "                    _cur = _all_steps[_si]\n"
        "                    _code_str = _cur.call.codex.code if _cur.call and _cur.call.codex else None\n"
        "                    _exec_name = f'taskexec_{_task_id}_{_si}'\n"
        "                    _te = TaskExecution(name=_exec_name, task=_task, status='running', result='')\n"
        "                    _te._timestamp_created = ic.time()\n"
        "                    if _code_str:\n"
        "                        _stdout = io.StringIO()\n"
        "                        _old_stdout = sys.stdout\n"
        "                        sys.stdout = _stdout\n"
        "                        try:\n"
        "                            _sync_ns = dict(globals())\n"
        "                            _sync_ns['run'] = run\n"
        "                            exec(_code_str, _sync_ns)\n"
        "                            sys.stdout = _old_stdout\n"
        "                            _te.status = 'completed'\n"
        "                            _te.result = _stdout.getvalue()[:4999]\n"
        "                            _cur.status = 'completed'\n"
        "                        except Exception:\n"
        "                            sys.stdout = _old_stdout\n"
        "                            _te.status = 'failed'\n"
        "                            _te.result = traceback.format_exc()[:4999]\n"
        "                            _cur.status = 'failed'\n"
        "                            _task.status = 'failed'\n"
        "                            return\n"
        "                    else:\n"
        "                        _te.status = 'failed'\n"
        "                        _te.result = 'No code to execute'\n"
        "                        _cur.status = 'failed'\n"
        "                        _task.status = 'failed'\n"
        "                        return\n"
        "                    _chain_next(_task, _si, _all_steps)\n"
        #
        # Async step callback — generator that yields to IC runtime
        # The code must define async_task() which returns a generator.
        # The IC runtime drives the generator (handles management_canister calls).
        #
        "                def _exec_async():\n"
        "                    import traceback\n"
        "                    _task = Task.load(_task_id)\n"
        "                    if not _task or _task.status == 'cancelled':\n"
        "                        return\n"
        "                    _task.status = 'running'\n"
        "                    _si = _task.step_to_execute\n"
        "                    _all_steps = list(_task.steps)\n"
        "                    if _si >= len(_all_steps):\n"
        "                        _si = 0\n"
        "                    _cur = _all_steps[_si]\n"
        "                    _code_str = _cur.call.codex.code if _cur.call and _cur.call.codex else None\n"
        "                    _exec_name = f'taskexec_{_task_id}_{_si}'\n"
        "                    _te = TaskExecution(name=_exec_name, task=_task, status='running', result='')\n"
        "                    _te._timestamp_created = ic.time()\n"
        "                    if not _code_str:\n"
        "                        _te.status = 'failed'\n"
        "                        _te.result = 'No code to execute'\n"
        "                        _cur.status = 'failed'\n"
        "                        _task.status = 'failed'\n"
        "                        return\n"
        "                    try:\n"
        "                        try:\n"
"                            from ic_python_logging import get_logger as _get_logger\n"
"                            _logger = _get_logger(f'task_{_task_id}_{_te._id}')\n"
"                        except Exception:\n"
"                            class _Logger:\n"
"                                def info(self, m): ic.print(str(m))\n"
"                                def warning(self, m): ic.print(f'WARN: {m}')\n"
"                                def error(self, m): ic.print(f'ERROR: {m}')\n"
"                                def debug(self, m): pass\n"
"                            _logger = _Logger()\n"
"                        _ns = {'ic': ic, 'Task': Task, 'TaskExecution': TaskExecution, 'wget': wget, 'run': run, 'logger': _logger}\n"
        "                        exec(_code_str, _ns)\n"
        "                        if 'async_task' not in _ns:\n"
        "                            _te.status = 'failed'\n"
        "                            _te.result = 'Async step must define async_task()'\n"
        "                            _cur.status = 'failed'\n"
        "                            _task.status = 'failed'\n"
        "                            return\n"
        #
        # Drive the inner generator manually so that exceptions raised
        # inside async_task() are caught by *Python* try/except below,
        # instead of propagating to drive_generator in Rust which traps
        # (rolling back all state, including TaskExecution records).
        # Only _ServiceCall objects are re-yielded to the Rust runtime.
        # Nested generators (e.g. from Transfer.execute() → Wallet.transfer())
        # are flattened here in Python using a generator stack, so Rust only
        # ever sees _ServiceCall objects.
        #
        "                        _gen_stack = [_ns['async_task']()]\n"
        "                        _send_val = None\n"
        "                        _result = None\n"
        "                        while _gen_stack:\n"
        "                            try:\n"
        "                                _yielded_val = _gen_stack[-1].send(_send_val)\n"
        "                                _send_val = None\n"
        "                                if hasattr(_yielded_val, 'canister_principal'):\n"
        "                                    _send_val = yield _yielded_val\n"
        "                                elif hasattr(_yielded_val, 'send'):\n"
        "                                    _gen_stack.append(_yielded_val)\n"
        "                                else:\n"
        "                                    _send_val = _yielded_val\n"
        "                            except StopIteration as _stop:\n"
        "                                _gen_stack.pop()\n"
        "                                _send_val = getattr(_stop, 'value', None)\n"
        "                                if not _gen_stack:\n"
        "                                    _result = _send_val\n"
        "                        _te.status = 'completed'\n"
        "                        _te.result = str(_result)[:4999] if _result is not None else ''\n"
        "                        _cur.status = 'completed'\n"
        "                        _chain_next(_task, _si, _all_steps)\n"
        "                    except Exception:\n"
        "                        _te.status = 'failed'\n"
        "                        _te.result = traceback.format_exc()[:4999]\n"
        "                        _cur.status = 'failed'\n"
        "                        _task.status = 'failed'\n"
        "                return _exec_sync, _exec_async\n"
        #
        # Schedule the first step
        #
        "            _sync_cb, _async_cb = _make_task_cbs(_tid)\n"
        "            _first_async = _steps[0].call.is_async if _steps[0].call else False\n"
        "            _cb = _async_cb if _first_async else _sync_cb\n"
        "            ic.set_timer(0, _cb)\n"
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


def _task_retry_code(tid: str) -> str:
    """Code for: %task retry <id|name>

    Reset ALL steps to pending, set step_to_execute=0, and start from the
    beginning.  Works for failed or completed tasks.
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
        "        print(f'Reset task {_t._id}: {_t.name} — all steps pending, ready to start')\n"
    )


def _task_resume_code(tid: str) -> str:
    """Code for: %task resume <id|name>

    Find the first non-completed step and restart from there.
    Only useful for tasks that failed partway through a multi-step chain.
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
        "        _resume_at = 0\n"
        "        for _i, _s in enumerate(_steps):\n"
        "            if _s.status != 'completed':\n"
        "                _resume_at = _i\n"
        "                break\n"
        "        else:\n"
        "            _resume_at = 0\n"
        "        _t.status = 'pending'\n"
        "        _t.step_to_execute = _resume_at\n"
        "        for _i, _s in enumerate(_steps):\n"
        "            if _i >= _resume_at: _s.status = 'pending'\n"
        "        for _s in _t.schedules: _s.disabled = False\n"
        "        print(f'Resuming task {_t._id}: {_t.name} — from step {_resume_at}')\n"
    )


_TASK_USAGE = (
    "Usage:\n"
    '  %task                                                    List all tasks\n'
    '  %task list                                               List all tasks\n'
    '  %task create <name> [every Ns] [--code "..."|--file <f>] Create a task\n'
    '  %task add-step <id|name> [--code "..."|--file <f>]       Add step to task\n'
    '           [--command "..."] [--delay N] [--async]\n'
    '  %task info <id|name>                                     Show task details\n'
    '  %task log <id|name> [--follow|-f]                        Show execution history\n'
    '  %task run <id|name>                                      Execute task code now\n'
    '  %task start <id|name>                                    Start via timer\n'
    '  %task stop <id|name>                                     Stop a task\n'
    '  %task retry <id|name>                                    Reset all steps and restart\n'
    '  %task resume <id|name>                                   Resume from first failed step\n'
    '  %task delete <id|name>                                   Delete task and records'
)


# ---------------------------------------------------------------------------
# %wallet subcommand handlers — ICRC-1 token operations
# ---------------------------------------------------------------------------

# Well-known ICRC-1 ledger canister IDs on IC mainnet
_LEDGER_IDS = {
    "ckbtc":  "mxzaz-hqaaa-aaaar-qaada-cai",
    "cketh":  "ss2fx-dyaaa-aaaar-qacoq-cai",
    "ckusdc": "xevnm-gaaaa-aaaar-qafnq-cai",
    "icp":    "ryjl3-tyaaa-aaaaa-aaaba-cai",
}

# ICRC-1 transfer fees (in smallest unit)
_LEDGER_FEES = {
    "ckbtc":  10,              # 10 satoshis
    "cketh":  2_000_000_000,   # 2 gwei
    "ckusdc": 10_000,          # 0.01 USDC
    "icp":    10_000,          # 0.0001 ICP
}

_LEDGER_DECIMALS = {
    "ckbtc":  8,
    "cketh":  18,
    "ckusdc": 6,
    "icp":    8,
}

_LEDGER_SYMBOLS = {
    "ckbtc":  "ckBTC",
    "cketh":  "ckETH",
    "ckusdc": "ckUSDC",
    "icp":    "ICP",
}

_WALLET_HISTORY_PATH = "/wallet_history.jsonl"

# ICRC-1 Index canister IDs (for transaction history)
_INDEX_IDS = {
    "ckbtc":  "n5wcd-faaaa-aaaar-qaaea-cai",
    "cketh":  "s3zol-vqaaa-aaaar-qacpa-cai",
    "ckusdc": "xrs4b-hiaaa-aaaar-qafoa-cai",
    "icp":    "qhbym-qaaaa-aaaaa-aaafq-cai",
}


def _parse_candid_text(text):
    """Parse candid text output from icp CLI into Python dicts/lists/values.

    Handles: record, variant, vec, nat, int, text, principal, opt, null.
    """
    import re as _re

    text = text.strip()
    if text.startswith('(') and text.endswith(')'):
        text = text[1:-1].strip()
    # icp CLI adds trailing comma before closing paren: (value,)
    if text.endswith(','):
        text = text[:-1].strip()

    if text == 'null':
        return None
    if text == 'true':
        return True
    if text == 'false':
        return False
    if text.startswith('opt '):
        return _parse_candid_text(text[4:])
    if text.startswith('principal "'):
        return text[11:-1]

    if text.startswith('"') and text.endswith('"'):
        return text[1:-1]

    # number with optional type annotation
    m = _re.match(r'^([+-]?\d[\d_]*)\s*(?::\s*\w+)?\s*$', text)
    if m:
        return int(m.group(1).replace('_', ''))

    def _split_items(s):
        """Split semicolon-delimited items respecting nested braces/strings."""
        items = []
        depth = 0
        in_str = False
        start = 0
        for i, c in enumerate(s):
            if c == '"' and (i == 0 or s[i-1] != '\\'):
                in_str = not in_str
            elif not in_str:
                if c in '({':
                    depth += 1
                elif c in ')}':
                    depth -= 1
                elif c == ';' and depth == 0:
                    items.append(s[start:i].strip())
                    start = i + 1
        tail = s[start:].strip()
        if tail:
            items.append(tail)
        return items

    def _strip_type(v):
        return _re.sub(r'\s*:\s*(?:nat\d*|int\d*|text|blob|bool|float\d*|principal)\s*$', '', v)

    if text.startswith('record {') and text.endswith('}'):
        inner = text[8:-1].strip()
        result = {}
        for item in _split_items(inner):
            if '=' not in item:
                continue
            key, _, val = item.partition('=')
            result[key.strip()] = _parse_candid_text(_strip_type(val.strip()))
        return result

    if text.startswith('variant {') and text.endswith('}'):
        inner = text[9:-1].strip().rstrip(';').strip()
        if '=' in inner:
            key, _, val = inner.partition('=')
            return {key.strip(): _parse_candid_text(_strip_type(val.strip()))}
        return {inner: None}

    if text.startswith('vec {') and text.endswith('}'):
        inner = text[5:-1].strip()
        if not inner:
            return []
        return [_parse_candid_text(_strip_type(item)) for item in _split_items(inner)]

    if text.startswith('blob "'):
        return text

    return text


def _parse_subaccount(args: str):
    """Extract --sub and --from-sub flags from args string.

    Returns (cleaned_args, subaccount_hex_or_None, from_subaccount_hex_or_None).
    Subaccount hex is validated as a 32-byte (64 char) hex string.
    """
    sub = None
    from_sub = None
    parts = args.split()
    cleaned = []
    i = 0
    while i < len(parts):
        if parts[i] == "--sub" and i + 1 < len(parts):
            sub = parts[i + 1]
            i += 2
        elif parts[i] == "--from-sub" and i + 1 < len(parts):
            from_sub = parts[i + 1]
            i += 2
        else:
            cleaned.append(parts[i])
            i += 1
    return " ".join(cleaned), sub, from_sub


def _candid_subaccount(hex_str):
    """Convert a hex subaccount to Candid blob literal, or 'null' if None."""
    if not hex_str:
        return "null"
    # Pad to 64 hex chars (32 bytes) if shorter
    hex_str = hex_str.strip().lower()
    if len(hex_str) < 64:
        hex_str = hex_str.zfill(64)
    if len(hex_str) != 64:
        return None  # invalid
    try:
        bytes.fromhex(hex_str)
    except ValueError:
        return None
    blob = "blob \"" + "".join(f"\\{hex_str[i:i+2]}" for i in range(0, 64, 2)) + "\""
    return f"opt {blob}"


def _wallet_balance(token: str, canister: str, network: str, subaccount: str = None) -> str:
    """Query the token ledger for the canister's balance via icp (client-side)."""
    ledger = _LEDGER_IDS.get(token)
    if not ledger:
        return f"Unknown token: {token}. Supported: {', '.join(_LEDGER_IDS.keys())}"

    decimals = _LEDGER_DECIMALS.get(token, 8)
    symbol = _LEDGER_SYMBOLS.get(token, token.upper())

    sub_candid = _candid_subaccount(subaccount)
    if sub_candid is None:
        return f"Invalid subaccount hex: {subaccount}"

    cmd = ["icp", "canister", "call", "--query", "--output", "candid"]
    if network:
        cmd.extend(["--network", network])
    cmd.extend([
        ledger, "icrc1_balance_of",
        f'(record {{ owner = principal "{canister}"; subaccount = {sub_candid} }})',
    ])

    try:
        r = _run_icp_with_retries(cmd, timeout_s=30)
        if r.returncode != 0:
            return f"[icp error] {r.stderr.strip()}"
        amount = int(_parse_candid_text(r.stdout.strip()))
        human = amount / (10 ** decimals)
        return f"{amount} e{decimals} ({human:.{decimals}f} {symbol})"
    except subprocess.TimeoutExpired:
        return "[error] balance query timed out"
    except FileNotFoundError:
        return "[error] icp not found — install the ICP CLI: npm install -g @icp-sdk/icp-cli"


def _wallet_deposit(token: str, canister: str, subaccount: str = None) -> str:
    """Show deposit instructions for the canister."""
    symbol = _LEDGER_SYMBOLS.get(token, token.upper())
    sub_candid = _candid_subaccount(subaccount)
    if sub_candid is None:
        return f"Invalid subaccount hex: {subaccount}"
    sub_display = f"  Subaccount: {subaccount}\n" if subaccount else "  (no subaccount)\n"
    return (
        f"To deposit {symbol} to this canister, transfer to:\n"
        f"  Principal: {canister}\n"
        + sub_display +
        f"\n"
        f"From icp:\n"
        f'  icp canister call {_LEDGER_IDS.get(token, "<ledger>")} icrc1_transfer \\\n'
        f'    \'(record {{ to = record {{ owner = principal "{canister}"; subaccount = {sub_candid} }};'
        f' amount = <AMOUNT> : nat; fee = opt ({_LEDGER_FEES.get(token, 0)} : nat);'
        f" memo = null; from_subaccount = null; created_at_time = null }})'"
    )


def _wallet_transfer(token: str, rest: str, canister: str, network: str,
                     to_subaccount: str = None, from_subaccount: str = None) -> str:
    """Transfer tokens from the canister to a target principal.

    Uses ic.set_timer(0, generator_callback) so the Rust runtime drives the
    inter-canister call.  Result is written to /tmp/_wallet_result.txt on the
    canister's memfs and polled by the client.
    """
    parts = rest.strip().split(None, 1)
    if len(parts) < 2:
        return f"Usage: %wallet {token} transfer <amount> <principal>"
    amount_str, target = parts[0], parts[1].strip()

    ledger = _LEDGER_IDS.get(token)
    if not ledger:
        return f"Unknown token: {token}"

    fee = _LEDGER_FEES.get(token, 0)
    decimals = _LEDGER_DECIMALS.get(token, 8)
    symbol = _LEDGER_SYMBOLS.get(token, token.upper())

    # Allow human-readable amounts like "0.001" or raw integers
    try:
        if '.' in amount_str:
            amount = int(float(amount_str) * (10 ** decimals))
        else:
            amount = int(amount_str)
    except ValueError:
        return f"Invalid amount: {amount_str}"

    if amount <= 0:
        return "Amount must be positive"

    human = amount / (10 ** decimals)

    to_sub_candid = _candid_subaccount(to_subaccount)
    if to_sub_candid is None:
        return f"Invalid target subaccount hex: {to_subaccount}"
    from_sub_candid = _candid_subaccount(from_subaccount)
    if from_sub_candid is None:
        return f"Invalid source subaccount hex: {from_subaccount}"

    # Generate canister code that sets up a timer callback
    esc_target = target.replace("'", "\\'")
    # History record metadata
    hist_token = token
    hist_amount = amount
    hist_target = target
    hist_to_sub = to_subaccount or ""
    hist_from_sub = from_subaccount or ""

    transfer_code = (
        "import json as _json\n"
        "def _wallet_transfer_cb():\n"
        "    try:\n"
        f"        _args = ic.candid_encode('(record {{ to = record {{ owner = principal \"{esc_target}\"; subaccount = {to_sub_candid} }}; amount = {amount} : nat; fee = opt ({fee} : nat); memo = null; from_subaccount = {from_sub_candid}; created_at_time = null }})')\n"
        f"        _result = yield ic.call_raw('{ledger}', 'icrc1_transfer', _args, 0)\n"
        "        if hasattr(_result, 'Ok') and _result.Ok is not None:\n"
        "            _decoded = ic.candid_decode(_result.Ok)\n"
        "            _out = _json.dumps({'ok': True, 'response': str(_decoded)})\n"
        "        elif hasattr(_result, 'Err') and _result.Err is not None:\n"
        "            _out = _json.dumps({'ok': False, 'error': str(_result.Err)})\n"
        "        else:\n"
        "            _out = _json.dumps({'ok': True, 'response': str(_result)})\n"
        "    except Exception as _e:\n"
        "        _out = _json.dumps({'ok': False, 'error': str(_e)})\n"
        "    with open('/tmp/_wallet_result.txt', 'w') as _f:\n"
        "        _f.write(_out)\n"
        "    try:\n"
        f"        _rec = _json.dumps({{'dir': 'out', 'token': '{hist_token}', 'amount': {hist_amount}, 'to': '{hist_target}', 'to_sub': '{hist_to_sub}', 'from_sub': '{hist_from_sub}', 'ts': ic.time(), 'result': _out}})\n"
        f"        with open('{_WALLET_HISTORY_PATH}', 'a') as _hf:\n"
        "            _hf.write(_rec + chr(10))\n"
        "    except Exception:\n"
        "        pass\n"
        "# Clear previous result\n"
        "try:\n"
        "    import os; os.remove('/tmp/_wallet_result.txt')\n"
        "except OSError:\n"
        "    pass\n"
        "ic.set_timer(0, _wallet_transfer_cb)\n"
        f"print('WALLET_TRANSFER_INITIATED')\n"
    )

    # Send the code to canister
    result = canister_exec(transfer_code, canister, network)
    if result is None or 'WALLET_TRANSFER_INITIATED' not in (result or ''):
        return f"[error] failed to initiate transfer: {result}"

    print(f"Transferring {human:.{decimals}f} {symbol} ({amount} e{decimals}) to {target}...")
    sys.stdout.flush()

    # Poll for result (the timer fires almost immediately)
    poll_code = (
        "try:\n"
        "    with open('/tmp/_wallet_result.txt', 'r') as _f:\n"
        "        print('WALLET_RESULT:' + _f.read())\n"
        "except FileNotFoundError:\n"
        "    print('WALLET_PENDING')\n"
    )

    import json
    for _ in range(15):
        _time.sleep(2)
        poll_result = canister_exec(poll_code, canister, network)
        if poll_result and 'WALLET_RESULT:' in poll_result:
            json_str = poll_result.split('WALLET_RESULT:', 1)[1].strip()
            try:
                data = json.loads(json_str)
                if data.get('ok'):
                    return f"Transfer successful: {data.get('response', '')}"
                else:
                    return f"Transfer failed: {data.get('error', 'unknown error')}"
            except json.JSONDecodeError:
                return f"Transfer result: {json_str}"

    return "[timeout] Transfer initiated but result not yet available. Use: %wallet result"


def _wallet_result(canister: str, network: str) -> str:
    """Check the result of the last wallet transfer."""
    import json
    poll_code = (
        "try:\n"
        "    with open('/tmp/_wallet_result.txt', 'r') as _f:\n"
        "        print('WALLET_RESULT:' + _f.read())\n"
        "except FileNotFoundError:\n"
        "    print('No pending wallet result.')\n"
    )
    result = canister_exec(poll_code, canister, network)
    if result and 'WALLET_RESULT:' in result:
        json_str = result.split('WALLET_RESULT:', 1)[1].strip()
        try:
            data = json.loads(json_str)
            if data.get('ok'):
                return f"Last transfer: OK — {data.get('response', '')}"
            else:
                return f"Last transfer: FAILED — {data.get('error', 'unknown')}"
        except json.JSONDecodeError:
            return f"Last transfer result: {json_str}"
    return result or "No wallet result found."


def _wallet_history(token: str, canister: str, network: str, count: int = 10,
                    subaccount: str = None) -> str:
    """Query the on-chain Index canister for complete transaction history."""
    import datetime
    import json as _json

    index = _INDEX_IDS.get(token)
    if not index:
        return f"No index canister known for {token}"

    symbol = _LEDGER_SYMBOLS.get(token, token.upper())
    decimals = _LEDGER_DECIMALS.get(token, 8)

    sub_candid = _candid_subaccount(subaccount)
    if sub_candid is None:
        return f"Invalid subaccount hex: {subaccount}"

    cmd = ["icp", "canister", "call", "--query", "--output", "candid"]
    if network:
        cmd.extend(["--network", network])
    cmd.extend([
        index, "get_account_transactions",
        f'(record {{ max_results = {count} : nat; start = null;'
        f' account = record {{ owner = principal "{canister}"; subaccount = {sub_candid} }} }})',
    ])

    try:
        r = _run_icp_with_retries(cmd, timeout_s=30)
        if r.returncode != 0:
            return f"[icp error] {r.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return "[error] index query timed out"
    except FileNotFoundError:
        return "[error] icp not found — install the ICP CLI: npm install -g @icp-sdk/icp-cli"

    try:
        data = _parse_candid_text(r.stdout)
    except Exception:
        return f"[error] failed to parse index response"

    if not isinstance(data, dict):
        return f"[error] unexpected index response format"

    if "Err" in data:
        return f"[error] index returned: {data['Err']}"

    ok = data.get("Ok", {})
    if not isinstance(ok, dict):
        return f"[error] unexpected Ok format in index response"
    txns = ok.get("transactions", [])

    if not txns:
        return f"No {symbol} transactions found."

    rows = []
    for entry in txns:
        _tid = entry.get("id", "?")
        tx_id = str(_tid).replace("_", "") if _tid != "?" else "?"
        tx = entry.get("transaction", {})
        if not isinstance(tx, dict):
            continue
        kind = tx.get("kind", "")
        _ts = tx.get("timestamp", 0)
        ts_ns = int(str(_ts).replace('_', '')) if _ts else 0
        ts_s = ts_ns // 1_000_000_000
        dt = datetime.datetime.utcfromtimestamp(ts_s).strftime('%Y-%m-%d %H:%M') if ts_s else "?"

        if kind == "transfer":
            _xfer = tx.get("transfer", [])
            if not _xfer:
                continue
            t = _xfer if isinstance(_xfer, dict) else (_xfer[0] if isinstance(_xfer, list) and _xfer else None)
            if not t or not isinstance(t, dict):
                continue
            _from = t.get("from", {})
            from_p = _from.get("owner", "?") if isinstance(_from, dict) else "?"
            _to = t.get("to", {})
            to_p = _to.get("owner", "?") if isinstance(_to, dict) else "?"
            _a = t.get("amount", 0)
            amt = int(str(_a).replace('_', '')) if _a else 0
            human_amt = amt / (10 ** decimals)

            if from_p == canister and to_p == canister:
                arrow = "↔"
                peer = "self"
            elif from_p == canister:
                arrow = "→"
                peer = to_p
            else:
                arrow = "←"
                peer = from_p

            if len(peer) > 20:
                peer = peer[:10] + "…" + peer[-5:]
            rows.append(f"  {dt}  #{tx_id}  {arrow} {human_amt:.{decimals}f} {symbol}  {peer}")

        elif kind == "mint":
            _mint = tx.get("mint", [])
            if _mint:
                m = _mint if isinstance(_mint, dict) else (_mint[0] if isinstance(_mint, list) and _mint else None)
                if m and isinstance(m, dict):
                    _a = m.get("amount", 0)
                    amt = int(str(_a).replace('_', '')) if _a else 0
                    human_amt = amt / (10 ** decimals)
                    rows.append(f"  {dt}  #{tx_id}  ⊕ {human_amt:.{decimals}f} {symbol}  mint")

        elif kind == "burn":
            _burn = tx.get("burn", [])
            if _burn:
                b = _burn if isinstance(_burn, dict) else (_burn[0] if isinstance(_burn, list) and _burn else None)
                if b and isinstance(b, dict):
                    _a = b.get("amount", 0)
                    amt = int(str(_a).replace('_', '')) if _a else 0
                    human_amt = amt / (10 ** decimals)
                    rows.append(f"  {dt}  #{tx_id}  ⊖ {human_amt:.{decimals}f} {symbol}  burn")

    if not rows:
        return f"No {symbol} transactions found."

    header = f"{symbol} transaction history (last {len(rows)}):"
    return header + "\n" + "\n".join(rows)


_WALLET_USAGE = (
    "Usage:\n"
    "  %wallet <token> balance [--sub <hex>]           Check canister token balance\n"
    "  %wallet <token> deposit [--sub <hex>]           Show deposit address\n"
    "  %wallet <token> transfer <amt> <to> [--sub <hex>] [--from-sub <hex>]\n"
    "                                                  Transfer tokens from canister\n"
    "  %wallet <token> history [--sub <hex>] [<N>]     Show last N transfers (default 10)\n"
    "  %wallet result                                  Check last transfer result\n"
    "\n"
    "Supported tokens: ckbtc, cketh, ckusdc, icp\n"
    "Amount can be human-readable (0.001) or raw smallest-unit (100000)\n"
    "Subaccounts: 32-byte hex string (e.g. 00000000000000000000000000000001)"
)


def _handle_wallet(args: str, canister: str, network: str) -> str:
    """Dispatch %wallet subcommands."""
    # Extract --sub / --from-sub before parsing positional args
    cleaned_args, sub, from_sub = _parse_subaccount(args)
    parts = cleaned_args.strip().split(None, 2)

    if not parts:
        return _WALLET_USAGE

    # %wallet result — no token needed
    if parts[0] == "result":
        return _wallet_result(canister, network)

    token = parts[0].lower()
    if token not in _LEDGER_IDS:
        return f"Unknown token: {token}. Supported: {', '.join(_LEDGER_IDS.keys())}\n\n" + _WALLET_USAGE

    subcmd = parts[1] if len(parts) > 1 else "balance"
    rest = parts[2] if len(parts) > 2 else ""

    if subcmd == "balance":
        return _wallet_balance(token, canister, network, subaccount=sub)

    if subcmd == "deposit":
        return _wallet_deposit(token, canister, subaccount=sub)

    if subcmd == "transfer":
        if not rest:
            return f"Usage: %wallet {token} transfer <amount> <principal>"
        return _wallet_transfer(token, rest, canister, network,
                                to_subaccount=sub, from_subaccount=from_sub)

    if subcmd == "history":
        count = 10
        if rest:
            try:
                count = int(rest)
            except ValueError:
                pass
        return _wallet_history(token, canister, network, count=count, subaccount=sub)

    return f"Unknown wallet command: {subcmd}\n\n" + _WALLET_USAGE


# ---------------------------------------------------------------------------
# %vetkey subcommand handlers — vetKD (vetKeys) operations
# ---------------------------------------------------------------------------

_VETKEY_USAGE = (
    "Usage:\n"
    "  %vetkey pubkey [--scope <text>]               Get derived vetKD public key\n"
    "  %vetkey derive <transport_pk_hex> [--scope <text>] [--input <text>]\n"
    "                                                Derive encrypted vetKey\n"
    "  %vetkey encrypt <file_or_text> [--scope <text>] [--input <text>]\n"
    "                                                Encrypt a file or text\n"
    "  %vetkey decrypt <file_or_text> [--scope <text>] [--input <text>]\n"
    "                                                Decrypt a file or text\n"
    "  %vetkey result                                Check last derive result\n"
    "\n"
    "Key names: key_1 (production), test_key_1 (test), dfx_test_key (local)\n"
    "Default key: test_key_1\n"
    "\n"
    "Encrypt/decrypt targets:\n"
    "  /path/to/file.txt   — canister file (encrypted → .enc, decrypted → strip .enc)\n"
    "  \"hello world\"       — literal text (quoted)\n"
    "  <hex>               — hex ciphertext (for decrypt)\n"
    "\n"
    "Examples:\n"
    "  %vetkey encrypt /data/secret.json\n"
    "  %vetkey decrypt /data/secret.json.enc\n"
    '  %vetkey encrypt "my secret message"\n'
    "  %vetkey decrypt a1b2c3...                     (hex from previous encrypt)"
)


def _vetkey_pubkey(canister: str, network: str, scope: str = None,
                   key_name: str = "test_key_1",
                   domain_separator: str = "basilisk") -> str:
    """Query the vetKD public key for the caller's context."""
    esc_domain = domain_separator.replace("'", "\\'")
    scope_code = (
        f"        _scope = '{scope}'.encode('utf-8')\n"
        if scope else
        "        _scope = ic.caller().bytes\n"
    )
    pubkey_code = (
        "import json as _json\n"
        "def _vetkey_pubkey_cb():\n"
        "    try:\n"
        f"        _ds = b'{esc_domain}'\n"
        + scope_code +
        "        _ctx = bytes([len(_ds)]) + _ds + _scope\n"
        "        _ctx_hex = ''.join(f'{b:02x}' for b in _ctx)\n"
        f"        _args = ic.candid_encode('(record {{ canister_id = null; context = blob \"' + _ctx_hex + '\"; key_id = record {{ curve = variant {{ bls12_381_g2 = null }}; name = \"{key_name}\" }} }})')\n"
        "        _result = yield ic.call_raw('aaaaa-aa', 'vetkd_public_key', _args, 26_000_000_000)\n"
        "        if hasattr(_result, 'Ok') and _result.Ok is not None:\n"
        "            _d = ic.candid_decode(_result.Ok)\n"
        "            _raw = None\n"
        "            if isinstance(_d, dict):\n"
        "                for _v in _d.values():\n"
        "                    if isinstance(_v, (bytes, bytearray, list)): _raw = _v; break\n"
        "            if _raw is None: _raw = getattr(_d, 'public_key', _d)\n"
        "            try: _hex = bytes(_raw).hex()\n"
        "            except: _hex = str(_d)\n"
        "            _out = _json.dumps({'ok': True, 'public_key': _hex})\n"
        "        elif hasattr(_result, 'Err') and _result.Err is not None:\n"
        "            _out = _json.dumps({'ok': False, 'error': str(_result.Err)})\n"
        "        else:\n"
        "            _out = _json.dumps({'ok': True, 'response': str(_result)})\n"
        "    except Exception as _e:\n"
        "        _out = _json.dumps({'ok': False, 'error': str(_e)})\n"
        "    with open('/tmp/_vetkey_result.txt', 'w') as _f:\n"
        "        _f.write(_out)\n"
        "try:\n"
        "    import os; os.remove('/tmp/_vetkey_result.txt')\n"
        "except OSError:\n"
        "    pass\n"
        "ic.set_timer(0, _vetkey_pubkey_cb)\n"
        "print('VETKEY_INITIATED')\n"
    )

    result = canister_exec(pubkey_code, canister, network)
    if result is None or 'VETKEY_INITIATED' not in (result or ''):
        return f"[error] failed to initiate vetkey pubkey call: {result}"

    print(f"Requesting vetKD public key (key={key_name})...")
    sys.stdout.flush()

    return _vetkey_poll(canister, network, label="Public key")


def _vetkey_derive(transport_pk_hex: str, canister: str, network: str,
                   scope: str = None, input_text: str = "",
                   key_name: str = "test_key_1",
                   domain_separator: str = "basilisk") -> str:
    """Derive an encrypted vetKey for the caller's context."""
    # Validate transport public key hex
    try:
        bytes.fromhex(transport_pk_hex)
    except ValueError:
        return f"[error] invalid transport public key hex: {transport_pk_hex}"

    esc_domain = domain_separator.replace("'", "\\'")
    esc_tpk = transport_pk_hex.replace("'", "\\'")
    esc_input = input_text.replace("'", "\\'")
    scope_code = (
        f"        _scope = '{scope}'.encode('utf-8')\n"
        if scope else
        "        _scope = ic.caller().bytes\n"
    )
    derive_code = (
        "import json as _json\n"
        "def _vetkey_derive_cb():\n"
        "    try:\n"
        f"        _ds = b'{esc_domain}'\n"
        + scope_code +
        "        _ctx = bytes([len(_ds)]) + _ds + _scope\n"
        "        _ctx_hex = ''.join(f'{b:02x}' for b in _ctx)\n"
        f"        _input_hex = ''.join(f'{{b:02x}}' for b in '{esc_input}'.encode('utf-8'))\n"
        f"        _tpk_hex = '{esc_tpk}'\n"
        "        _tpk_blob = ''.join(chr(92) + _tpk_hex[i:i+2] for i in range(0, len(_tpk_hex), 2))\n"
        f"        _args = ic.candid_encode('(record {{ input = blob \"' + _input_hex + '\"; context = blob \"' + _ctx_hex + '\"; key_id = record {{ curve = variant {{ bls12_381_g2 = null }}; name = \"{key_name}\" }}; transport_public_key = blob \"' + _tpk_blob + '\" }})')\n"
        "        _result = yield ic.call_raw('aaaaa-aa', 'vetkd_derive_key', _args, 54_000_000_000)\n"
        "        if hasattr(_result, 'Ok') and _result.Ok is not None:\n"
        "            _d = ic.candid_decode(_result.Ok)\n"
        "            _raw = None\n"
        "            if isinstance(_d, dict):\n"
        "                for _v in _d.values():\n"
        "                    if isinstance(_v, (bytes, bytearray, list)): _raw = _v; break\n"
        "            if _raw is None: _raw = getattr(_d, 'encrypted_key', _d)\n"
        "            try: _hex = bytes(_raw).hex()\n"
        "            except: _hex = str(_d)\n"
        "            _out = _json.dumps({'ok': True, 'encrypted_key': _hex})\n"
        "        elif hasattr(_result, 'Err') and _result.Err is not None:\n"
        "            _out = _json.dumps({'ok': False, 'error': str(_result.Err)})\n"
        "        else:\n"
        "            _out = _json.dumps({'ok': True, 'response': str(_result)})\n"
        "    except Exception as _e:\n"
        "        _out = _json.dumps({'ok': False, 'error': str(_e)})\n"
        "    with open('/tmp/_vetkey_result.txt', 'w') as _f:\n"
        "        _f.write(_out)\n"
        "try:\n"
        "    import os; os.remove('/tmp/_vetkey_result.txt')\n"
        "except OSError:\n"
        "    pass\n"
        "ic.set_timer(0, _vetkey_derive_cb)\n"
        "print('VETKEY_INITIATED')\n"
    )

    result = canister_exec(derive_code, canister, network)
    if result is None or 'VETKEY_INITIATED' not in (result or ''):
        return f"[error] failed to initiate vetkey derive call: {result}"

    print(f"Deriving encrypted vetKey (key={key_name}, input='{input_text}')...")
    sys.stdout.flush()

    return _vetkey_poll(canister, network, label="Encrypted key")


def _vetkey_poll(canister: str, network: str, label: str = "Result") -> str:
    """Poll canister memfs for vetkey result (shared by pubkey and derive)."""
    import json
    poll_code = (
        "try:\n"
        "    with open('/tmp/_vetkey_result.txt', 'r') as _f:\n"
        "        print('VETKEY_RESULT:' + _f.read())\n"
        "except FileNotFoundError:\n"
        "    print('VETKEY_PENDING')\n"
    )
    for _ in range(15):
        _time.sleep(2)
        poll_result = canister_exec(poll_code, canister, network)
        if poll_result and 'VETKEY_RESULT:' in poll_result:
            json_str = poll_result.split('VETKEY_RESULT:', 1)[1].strip()
            try:
                data = json.loads(json_str)
                if data.get('ok'):
                    for key in ('public_key', 'encrypted_key', 'response'):
                        if key in data:
                            return f"{label}: {data[key]}"
                    return f"{label}: {data}"
                else:
                    return f"[error] {data.get('error', 'unknown error')}"
            except json.JSONDecodeError:
                return f"{label}: {json_str}"

    return f"[timeout] vetKey operation initiated but result not yet available. Use: %vetkey result"


def _vetkey_result(canister: str, network: str) -> str:
    """Check the result of the last vetkey operation."""
    import json
    poll_code = (
        "try:\n"
        "    with open('/tmp/_vetkey_result.txt', 'r') as _f:\n"
        "        print('VETKEY_RESULT:' + _f.read())\n"
        "except FileNotFoundError:\n"
        "    print('No pending vetkey result.')\n"
    )
    result = canister_exec(poll_code, canister, network)
    if result and 'VETKEY_RESULT:' in result:
        json_str = result.split('VETKEY_RESULT:', 1)[1].strip()
        try:
            data = json.loads(json_str)
            if data.get('ok'):
                for key in ('public_key', 'encrypted_key', 'response'):
                    if key in data:
                        return f"{key}: {data[key]}"
                return str(data)
            else:
                return f"[error] {data.get('error', 'unknown error')}"
        except json.JSONDecodeError:
            return json_str
    return result or "No pending vetkey result."


def _parse_vetkey_flags(args: str):
    """Extract --scope, --input, --key flags from vetkey args."""
    scope = None
    input_text = ""
    key_name = "test_key_1"
    cleaned = args

    import re as _re
    # --scope <text>
    m = _re.search(r'--scope\s+(\S+)', cleaned)
    if m:
        scope = m.group(1)
        cleaned = cleaned[:m.start()] + cleaned[m.end():]
    # --input <text>
    m = _re.search(r'--input\s+(\S+)', cleaned)
    if m:
        input_text = m.group(1)
        cleaned = cleaned[:m.start()] + cleaned[m.end():]
    # --key <name>
    m = _re.search(r'--key\s+(\S+)', cleaned)
    if m:
        key_name = m.group(1)
        cleaned = cleaned[:m.start()] + cleaned[m.end():]

    return cleaned.strip(), scope, input_text, key_name


def _vetkey_poll_raw(canister: str, network: str, timeout: int = 30) -> dict:
    """Poll canister memfs for vetkey result and return the parsed dict (or None)."""
    import json
    poll_code = (
        "try:\n"
        "    with open('/tmp/_vetkey_result.txt', 'r') as _f:\n"
        "        print('VETKEY_RESULT:' + _f.read())\n"
        "except FileNotFoundError:\n"
        "    print('VETKEY_PENDING')\n"
    )
    iterations = max(timeout // 2, 1)
    for _ in range(iterations):
        _time.sleep(2)
        poll_result = canister_exec(poll_code, canister, network)
        if poll_result and 'VETKEY_RESULT:' in poll_result:
            json_str = poll_result.split('VETKEY_RESULT:', 1)[1].strip()
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                return {'ok': True, 'raw': json_str}
    return None


def _parse_candid_blob(text: str):
    """Extract hex bytes from a Candid blob like: blob \"\\af\\d3\\fc...\" (fallback parser)."""
    import re as _re
    m = _re.search(r'blob\s*"([^"]*)"', text)
    if not m:
        return None
    raw = m.group(1)
    hex_str = ''
    i = 0
    while i < len(raw):
        if raw[i] == '\\' and i + 2 < len(raw):
            hex_str += raw[i + 1:i + 3]
            i += 3
        else:
            hex_str += format(ord(raw[i]), '02x')
            i += 1
    return hex_str


def _vetkey_extract_hex(data: dict, field: str):
    """Extract a clean hex string from a vetkey poll result dict."""
    val = data.get(field, data.get('response', ''))
    if not val:
        return None
    # If it's already clean hex, return it
    try:
        bytes.fromhex(val)
        return val
    except (ValueError, TypeError):
        pass
    # Fallback: try parsing Candid blob text
    parsed = _parse_candid_blob(str(val))
    return parsed


def _vetkey_get_pubkey_hex(canister: str, network: str, scope=None,
                           key_name: str = "test_key_1") -> str:
    """Run the full pubkey flow and return the hex string (or error string)."""
    # Initiate the pubkey call (reuse existing function internals)
    esc_domain = "basilisk".replace("'", "\\'")
    scope_code = (
        f"        _scope = '{scope}'.encode('utf-8')\n"
        if scope else
        "        _scope = ic.caller().bytes\n"
    )
    pubkey_code = (
        "import json as _json\n"
        "def _vetkey_pubkey_cb():\n"
        "    try:\n"
        f"        _ds = b'{esc_domain}'\n"
        + scope_code +
        "        _ctx = bytes([len(_ds)]) + _ds + _scope\n"
        "        _ctx_hex = ''.join(f'{b:02x}' for b in _ctx)\n"
        f"        _args = ic.candid_encode('(record {{ canister_id = null; context = blob \"' + _ctx_hex + '\"; key_id = record {{ curve = variant {{ bls12_381_g2 = null }}; name = \"{key_name}\" }} }})')\n"
        "        _result = yield ic.call_raw('aaaaa-aa', 'vetkd_public_key', _args, 26_000_000_000)\n"
        "        if hasattr(_result, 'Ok') and _result.Ok is not None:\n"
        "            _d = ic.candid_decode(_result.Ok)\n"
        "            _raw = None\n"
        "            if isinstance(_d, dict):\n"
        "                for _v in _d.values():\n"
        "                    if isinstance(_v, (bytes, bytearray, list)): _raw = _v; break\n"
        "            if _raw is None: _raw = getattr(_d, 'public_key', _d)\n"
        "            try: _hex = bytes(_raw).hex()\n"
        "            except: _hex = str(_d)\n"
        "            _out = _json.dumps({'ok': True, 'public_key': _hex})\n"
        "        elif hasattr(_result, 'Err') and _result.Err is not None:\n"
        "            _out = _json.dumps({'ok': False, 'error': str(_result.Err)})\n"
        "        else:\n"
        "            _out = _json.dumps({'ok': True, 'response': str(_result)})\n"
        "    except Exception as _e:\n"
        "        _out = _json.dumps({'ok': False, 'error': str(_e)})\n"
        "    with open('/tmp/_vetkey_result.txt', 'w') as _f:\n"
        "        _f.write(_out)\n"
        "try:\n"
        "    import os; os.remove('/tmp/_vetkey_result.txt')\n"
        "except OSError:\n"
        "    pass\n"
        "ic.set_timer(0, _vetkey_pubkey_cb)\n"
        "print('VETKEY_INITIATED')\n"
    )
    result = canister_exec(pubkey_code, canister, network)
    if result is None or 'VETKEY_INITIATED' not in (result or ''):
        return None

    print("  [1/3] Requesting vetKD public key...")
    sys.stdout.flush()

    data = _vetkey_poll_raw(canister, network, timeout=60)
    if data is None:
        return None
    if not data.get('ok'):
        return None
    return _vetkey_extract_hex(data, 'public_key')


def _vetkey_get_encrypted_key_hex(tpk_hex: str, canister: str, network: str,
                                   scope=None, input_text: str = "",
                                   key_name: str = "test_key_1") -> str:
    """Run the full derive flow and return the encrypted key hex (or None)."""
    esc_domain = "basilisk".replace("'", "\\'")
    esc_tpk = tpk_hex.replace("'", "\\'")
    esc_input = input_text.replace("'", "\\'")
    scope_code = (
        f"        _scope = '{scope}'.encode('utf-8')\n"
        if scope else
        "        _scope = ic.caller().bytes\n"
    )
    derive_code = (
        "import json as _json\n"
        "def _vetkey_derive_cb():\n"
        "    try:\n"
        f"        _ds = b'{esc_domain}'\n"
        + scope_code +
        "        _ctx = bytes([len(_ds)]) + _ds + _scope\n"
        "        _ctx_hex = ''.join(f'{b:02x}' for b in _ctx)\n"
        f"        _input_hex = ''.join(f'{{b:02x}}' for b in '{esc_input}'.encode('utf-8'))\n"
        f"        _tpk_hex = '{esc_tpk}'\n"
        "        _tpk_blob = ''.join(chr(92) + _tpk_hex[i:i+2] for i in range(0, len(_tpk_hex), 2))\n"
        f"        _args = ic.candid_encode('(record {{ input = blob \"' + _input_hex + '\"; context = blob \"' + _ctx_hex + '\"; key_id = record {{ curve = variant {{ bls12_381_g2 = null }}; name = \"{key_name}\" }}; transport_public_key = blob \"' + _tpk_blob + '\" }})')\n"
        "        _result = yield ic.call_raw('aaaaa-aa', 'vetkd_derive_key', _args, 54_000_000_000)\n"
        "        if hasattr(_result, 'Ok') and _result.Ok is not None:\n"
        "            _d = ic.candid_decode(_result.Ok)\n"
        "            _raw = None\n"
        "            if isinstance(_d, dict):\n"
        "                for _v in _d.values():\n"
        "                    if isinstance(_v, (bytes, bytearray, list)): _raw = _v; break\n"
        "            if _raw is None: _raw = getattr(_d, 'encrypted_key', _d)\n"
        "            try: _hex = bytes(_raw).hex()\n"
        "            except: _hex = str(_d)\n"
        "            _out = _json.dumps({'ok': True, 'encrypted_key': _hex})\n"
        "        elif hasattr(_result, 'Err') and _result.Err is not None:\n"
        "            _out = _json.dumps({'ok': False, 'error': str(_result.Err)})\n"
        "        else:\n"
        "            _out = _json.dumps({'ok': True, 'response': str(_result)})\n"
        "    except Exception as _e:\n"
        "        _out = _json.dumps({'ok': False, 'error': str(_e)})\n"
        "    with open('/tmp/_vetkey_result.txt', 'w') as _f:\n"
        "        _f.write(_out)\n"
        "try:\n"
        "    import os; os.remove('/tmp/_vetkey_result.txt')\n"
        "except OSError:\n"
        "    pass\n"
        "ic.set_timer(0, _vetkey_derive_cb)\n"
        "print('VETKEY_INITIATED')\n"
    )
    result = canister_exec(derive_code, canister, network)
    if result is None or 'VETKEY_INITIATED' not in (result or ''):
        return None

    print("  [2/3] Deriving encrypted vetKey...")
    sys.stdout.flush()

    data = _vetkey_poll_raw(canister, network, timeout=60)
    if data is None:
        return None
    if not data.get('ok'):
        return None
    return _vetkey_extract_hex(data, 'encrypted_key')


def _vetkey_node_call(cmd_dict: dict) -> dict:
    """Call the vetkeys Node.js helper and return the parsed JSON response."""
    import json
    helper_path = os.path.join(os.path.dirname(__file__), 'vetkeys_helper.js')
    if not os.path.exists(helper_path):
        return {'ok': False, 'error': f'vetkeys_helper.js not found at {helper_path}'}

    try:
        proc = subprocess.run(
            ['node', helper_path],
            input=json.dumps(cmd_dict),
            capture_output=True, text=True, timeout=30
        )
    except FileNotFoundError:
        return {'ok': False, 'error': 'Node.js is required for vetkey encrypt/decrypt. Install it from https://nodejs.org'}
    except subprocess.TimeoutExpired:
        return {'ok': False, 'error': 'Node.js helper timed out'}

    if proc.returncode != 0:
        return {'ok': False, 'error': f'Node.js helper failed: {proc.stderr.strip()}'}

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {'ok': False, 'error': f'Invalid response from helper: {proc.stdout[:200]}'}


def _vetkey_read_canister_file(filepath: str, canister: str, network: str):
    """Read a file from the canister and return its bytes as hex, or None."""
    import base64 as _b64
    esc = filepath.replace("'", "\\'")
    code = (
        "import base64 as _b64\n"
        "try:\n"
        f"    with open('{esc}', 'rb') as _f:\n"
        "        print('FDATA:' + _b64.b64encode(_f.read()).decode())\n"
        "except FileNotFoundError:\n"
        "    print('FNOTFOUND')\n"
        "except Exception as _e:\n"
        "    print('FERR:' + str(_e))\n"
    )
    result = canister_exec(code, canister, network)
    if not result:
        return None
    if 'FNOTFOUND' in result:
        return None
    if 'FDATA:' in result:
        b64_str = result.split('FDATA:', 1)[1].strip()
        return _b64.b64decode(b64_str).hex()
    return None


def _vetkey_write_canister_file(filepath: str, data_hex: str,
                                 canister: str, network: str) -> bool:
    """Write hex data to a file on the canister. Returns True on success."""
    import base64 as _b64
    data_bytes = bytes.fromhex(data_hex)
    b64_data = _b64.b64encode(data_bytes).decode()
    esc = filepath.replace("'", "\\'")
    code = (
        "import base64 as _b64\n"
        f"_data = _b64.b64decode('{b64_data}')\n"
        "try:\n"
        f"    with open('{esc}', 'wb') as _f:\n"
        "        _f.write(_data)\n"
        "    print('FWRITTEN')\n"
        "except Exception as _e:\n"
        "    print('FERR:' + str(_e))\n"
    )
    result = canister_exec(code, canister, network)
    return result is not None and 'FWRITTEN' in result


def _vetkey_derive_aes_key(canister: str, network: str, scope=None,
                            input_text: str = "", key_name: str = "test_key_1"):
    """Full key derivation: pubkey + transport keygen + derive → returns (seed_hex, pubkey_hex, ek_hex) or error string."""
    # Step 1: Get public key
    pk_hex = _vetkey_get_pubkey_hex(canister, network, scope=scope, key_name=key_name)
    if pk_hex is None:
        return "[error] Failed to retrieve vetKD public key (timeout or error)"

    # Step 2: Generate transport key
    seed_hex = os.urandom(32).hex()
    keygen_result = _vetkey_node_call({'cmd': 'keygen', 'seed_hex': seed_hex})
    if not keygen_result.get('ok'):
        return f"[error] Transport keygen failed: {keygen_result.get('error', 'unknown')}"
    tpk_hex = keygen_result['tpk_hex']

    # Step 3: Derive encrypted key
    ek_hex = _vetkey_get_encrypted_key_hex(
        tpk_hex, canister, network,
        scope=scope, input_text=input_text, key_name=key_name
    )
    if ek_hex is None:
        return "[error] Failed to derive encrypted vetKey (timeout or error)"

    return (seed_hex, pk_hex, ek_hex)


def _vetkey_encrypt(target: str, canister: str, network: str,
                     scope=None, input_text: str = "",
                     key_name: str = "test_key_1") -> str:
    """Encrypt a file or text using vetKeys."""
    # Determine if target is a file path or text
    is_file = target.startswith('/')
    is_quoted = target.startswith('"') and target.endswith('"')

    if is_file:
        print(f"Encrypting canister file: {target}")
    elif is_quoted:
        print(f"Encrypting text...")
    else:
        print(f"Encrypting text...")
    sys.stdout.flush()

    # Get the plaintext
    if is_file:
        plaintext_hex = _vetkey_read_canister_file(target, canister, network)
        if plaintext_hex is None:
            return f"[error] File not found on canister: {target}"
    elif is_quoted:
        plaintext_hex = target[1:-1].encode('utf-8').hex()
    else:
        plaintext_hex = target.encode('utf-8').hex()

    # Derive AES key (2 async canister calls ~ 60-120s)
    derivation_id_hex = input_text.encode('utf-8').hex() if input_text else ""
    key_result = _vetkey_derive_aes_key(canister, network, scope=scope,
                                         input_text=input_text, key_name=key_name)
    if isinstance(key_result, str):
        return key_result  # error message

    seed_hex, pk_hex, ek_hex = key_result

    # Encrypt via Node.js helper
    print("  [3/3] Encrypting data...")
    sys.stdout.flush()
    enc_result = _vetkey_node_call({
        'cmd': 'encrypt',
        'seed_hex': seed_hex,
        'encrypted_key_hex': ek_hex,
        'public_key_hex': pk_hex,
        'derivation_id_hex': derivation_id_hex,
        'plaintext_hex': plaintext_hex,
    })
    if not enc_result.get('ok'):
        return f"[error] Encryption failed: {enc_result.get('error', 'unknown')}"

    ciphertext_hex = enc_result['ciphertext_hex']

    if is_file:
        dest = target + '.enc'
        ok = _vetkey_write_canister_file(dest, ciphertext_hex, canister, network)
        if ok:
            return f"Encrypted {target} → {dest} ({len(ciphertext_hex) // 2} bytes)"
        return f"[error] Failed to write encrypted file to {dest}"
    else:
        return f"Ciphertext ({len(ciphertext_hex) // 2} bytes):\n{ciphertext_hex}"


def _vetkey_decrypt(target: str, canister: str, network: str,
                     scope=None, input_text: str = "",
                     key_name: str = "test_key_1") -> str:
    """Decrypt a file or hex ciphertext using vetKeys."""
    is_file = target.startswith('/')
    is_quoted = target.startswith('"') and target.endswith('"')

    if is_file:
        print(f"Decrypting canister file: {target}")
    else:
        print(f"Decrypting ciphertext...")
    sys.stdout.flush()

    # Get the ciphertext
    if is_file:
        ciphertext_hex = _vetkey_read_canister_file(target, canister, network)
        if ciphertext_hex is None:
            return f"[error] File not found on canister: {target}"
    elif is_quoted:
        ciphertext_hex = target[1:-1]
    else:
        ciphertext_hex = target

    # Validate hex
    try:
        bytes.fromhex(ciphertext_hex)
    except ValueError:
        return f"[error] Invalid ciphertext (not valid hex)"

    # Derive AES key
    derivation_id_hex = input_text.encode('utf-8').hex() if input_text else ""
    key_result = _vetkey_derive_aes_key(canister, network, scope=scope,
                                         input_text=input_text, key_name=key_name)
    if isinstance(key_result, str):
        return key_result

    seed_hex, pk_hex, ek_hex = key_result

    # Decrypt via Node.js helper
    print("  [3/3] Decrypting data...")
    sys.stdout.flush()
    dec_result = _vetkey_node_call({
        'cmd': 'decrypt',
        'seed_hex': seed_hex,
        'encrypted_key_hex': ek_hex,
        'public_key_hex': pk_hex,
        'derivation_id_hex': derivation_id_hex,
        'ciphertext_hex': ciphertext_hex,
    })
    if not dec_result.get('ok'):
        return f"[error] Decryption failed: {dec_result.get('error', 'unknown')}"

    plaintext_hex = dec_result['plaintext_hex']

    if is_file:
        dest = target[:-4] if target.endswith('.enc') else target + '.dec'
        plaintext_bytes = bytes.fromhex(plaintext_hex)
        ok = _vetkey_write_canister_file(dest, plaintext_hex, canister, network)
        if ok:
            # Try to show the content if it looks like text
            try:
                text = plaintext_bytes.decode('utf-8')
                return f"Decrypted {target} → {dest} ({len(plaintext_bytes)} bytes)\nContent: {text[:500]}"
            except UnicodeDecodeError:
                return f"Decrypted {target} → {dest} ({len(plaintext_bytes)} bytes)"
        return f"[error] Failed to write decrypted file to {dest}"
    else:
        plaintext_bytes = bytes.fromhex(plaintext_hex)
        try:
            text = plaintext_bytes.decode('utf-8')
            return f"Plaintext: {text}"
        except UnicodeDecodeError:
            return f"Plaintext (hex): {plaintext_hex}"


def _handle_vetkey(args: str, canister: str, network: str) -> str:
    """Dispatch %vetkey subcommands."""
    cleaned, scope, input_text, key_name = _parse_vetkey_flags(args)
    parts = cleaned.strip().split(None, 1)
    subcmd = parts[0] if parts else "help"
    rest = parts[1].strip() if len(parts) > 1 else ""

    if subcmd == "help":
        return _VETKEY_USAGE

    if subcmd == "pubkey":
        return _vetkey_pubkey(canister, network, scope=scope, key_name=key_name)

    if subcmd == "derive":
        if not rest:
            return "Usage: %vetkey derive <transport_public_key_hex> [--scope <text>] [--input <text>]"
        return _vetkey_derive(rest, canister, network, scope=scope,
                              input_text=input_text, key_name=key_name)

    if subcmd == "encrypt":
        if not rest:
            return "Usage: %vetkey encrypt <file_or_text> [--scope <text>] [--input <text>]"
        return _vetkey_encrypt(rest, canister, network, scope=scope,
                               input_text=input_text, key_name=key_name)

    if subcmd == "decrypt":
        if not rest:
            return "Usage: %vetkey decrypt <file_or_text> [--scope <text>] [--input <text>]"
        return _vetkey_decrypt(rest, canister, network, scope=scope,
                               input_text=input_text, key_name=key_name)

    if subcmd == "result":
        return _vetkey_result(canister, network)

    return f"Unknown vetkey command: {subcmd}\n\n" + _VETKEY_USAGE


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


def _wget(url: str, dest: str, canister: str, network: str) -> str:
    """Call the canister's download_to_file endpoint directly via icp."""
    escaped_url = url.replace('"', '\\"')
    escaped_dest = dest.replace('"', '\\"')
    cmd = ["icp", "canister", "call"]
    if network:
        cmd.extend(["--network", network])
    cmd.extend([canister, "download_to_file", f'("{escaped_url}", "{escaped_dest}")'])

    try:
        r = _run_icp_with_retries(cmd, timeout_s=120)
        if r.returncode != 0:
            return f"[icp error] {r.stderr.strip()}"
        return _parse_candid(r.stdout)
    except subprocess.TimeoutExpired:
        return "[error] download timed out (120s)"
    except FileNotFoundError:
        return "[error] icp not found — install the ICP CLI: npm install -g @icp-sdk/icp-cli"


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

    if subcmd == "add-step":
        if not rest:
            return _TASK_USAGE
        code = _task_add_step_code(rest)
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

    if subcmd == "retry":
        if not rest:
            return "Usage: %task retry <id>"
        return canister_exec(_task_retry_code(rest), canister, network)

    if subcmd == "resume":
        if not rest:
            return "Usage: %task resume <id>"
        return canister_exec(_task_resume_code(rest), canister, network)

    return _TASK_USAGE


# ---------------------------------------------------------------------------
# %fx subcommand handlers — FX rate service
# ---------------------------------------------------------------------------

# Entity resolve preamble injected into every %fx exec call
_FX_RESOLVE = (
    "if 'FXPair' not in dir():\n"
    "    from ic_python_db import Entity, String, Integer, TimestampedMixin\n"
    "    class FXPair(Entity, TimestampedMixin):\n"
    "        __alias__ = 'name'\n"
    "        name = String(max_length=16)\n"
    "        base_symbol = String(max_length=8)\n"
    "        base_class = String(max_length=16)\n"
    "        quote_symbol = String(max_length=8)\n"
    "        quote_class = String(max_length=16)\n"
    "        rate = Integer(default=0)\n"
    "        decimals = Integer(default=9)\n"
    "        last_updated = Integer(default=0)\n"
    "        last_error = String(max_length=256)\n"
)


def _fx_list_code() -> str:
    """Generate code to list all registered FX pairs with rates."""
    return (
        _FX_RESOLVE +
        "pairs = sorted(FXPair.instances(), key=lambda p: p.name)\n"
        "if not pairs:\n"
        "    print('No FX pairs registered.  Use: %fx register <base> <quote>')\n"
        "else:\n"
        "    print(f'FX Pairs ({len(pairs)}):')\n"
        "    print(f'{\"Pair\":<12} {\"Rate\":>16} {\"Updated\":>22} {\"Error\"}')\n"
        "    print('-' * 70)\n"
        "    for p in pairs:\n"
        "        human = p.rate / (10 ** p.decimals) if p.rate and p.decimals else 0.0\n"
        "        rate_str = f'{human:,.{min(p.decimals, 6)}f}' if p.rate else '-'\n"
        "        if p.last_updated:\n"
        "            import time as _t\n"
        "            try:\n"
        "                ts = _t.strftime('%Y-%m-%d %H:%M UTC', _t.gmtime(p.last_updated))\n"
        "            except Exception:\n"
        "                ts = str(p.last_updated)\n"
        "        else:\n"
        "            ts = 'never'\n"
        "        err = p.last_error[:20] if p.last_error else ''\n"
        "        print(f'{p.name:<12} {rate_str:>16} {ts:>22} {err}')\n"
    )


def _fx_register_code(base: str, quote: str, base_class: str, quote_class: str) -> str:
    """Generate code to register an FX pair."""
    name = f"{base}/{quote}"
    return (
        _FX_RESOLVE +
        f"name = '{name}'\n"
        f"pair = FXPair[name]\n"
        f"if pair is None:\n"
        f"    pair = FXPair(name=name, base_symbol='{base}', base_class='{base_class}', "
        f"quote_symbol='{quote}', quote_class='{quote_class}')\n"
        f"    print(f'Registered FX pair: {name}')\n"
        f"else:\n"
        f"    pair.base_symbol = '{base}'\n"
        f"    pair.base_class = '{base_class}'\n"
        f"    pair.quote_symbol = '{quote}'\n"
        f"    pair.quote_class = '{quote_class}'\n"
        f"    print(f'Updated FX pair: {name}')\n"
    )


def _fx_unregister_code(base: str, quote: str) -> str:
    """Generate code to unregister an FX pair."""
    name = f"{base}/{quote}"
    return (
        _FX_RESOLVE +
        f"pair = FXPair['{name}']\n"
        f"if pair is None:\n"
        f"    print('FX pair not found: {name}')\n"
        f"else:\n"
        f"    pair.delete()\n"
        f"    print('Unregistered FX pair: {name}')\n"
    )


def _fx_rate_code(base: str, quote: str) -> str:
    """Generate code to display the cached rate for a pair."""
    name = f"{base}/{quote}"
    return (
        _FX_RESOLVE +
        f"pair = FXPair['{name}']\n"
        f"if pair is None:\n"
        f"    print('FX pair not registered: {name}')\n"
        f"elif pair.rate == 0:\n"
        f"    print('{name}: no rate data yet — run %fx refresh')\n"
        f"else:\n"
        f"    human = pair.rate / (10 ** pair.decimals)\n"
        f"    print(f'{name} = {{human:,.{{min(pair.decimals, 6)}}f}}')\n"
    )


def _fx_info_code(base: str, quote: str) -> str:
    """Generate code to display full rate info for a pair."""
    name = f"{base}/{quote}"
    return (
        _FX_RESOLVE +
        f"pair = FXPair['{name}']\n"
        f"if pair is None:\n"
        f"    print('FX pair not registered: {name}')\n"
        f"else:\n"
        f"    human = pair.rate / (10 ** pair.decimals) if pair.rate and pair.decimals else 0.0\n"
        f"    print(f'Pair:         {{pair.name}}')\n"
        f"    print(f'Base:         {{pair.base_symbol}} ({{pair.base_class}})')\n"
        f"    print(f'Quote:        {{pair.quote_symbol}} ({{pair.quote_class}})')\n"
        f"    print(f'Rate:         {{human:,.{{min(pair.decimals, 6)}}f}}' if pair.rate else 'Rate:         -')\n"
        f"    print(f'Raw rate:     {{pair.rate}}')\n"
        f"    print(f'Decimals:     {{pair.decimals}}')\n"
        f"    if pair.last_updated:\n"
        f"        import time as _t\n"
        f"        try:\n"
        f"            ts = _t.strftime('%Y-%m-%d %H:%M:%S UTC', _t.gmtime(pair.last_updated))\n"
        f"        except Exception:\n"
        f"            ts = str(pair.last_updated)\n"
        f"        print(f'Last updated: {{ts}}')\n"
        f"    else:\n"
        f"        print('Last updated: never')\n"
        f"    if pair.last_error:\n"
        f"        print(f'Last error:   {{pair.last_error}}')\n"
    )


def _fx_refresh(canister: str, network: str) -> str:
    """Trigger an async refresh of all registered FX pairs via a one-shot task.

    Creates a task with an async step that queries the XRC canister for each
    registered pair, updates the DB, then polls for completion.
    """
    # Step 1: write the refresh code to canister memfs
    refresh_code = (
        "from basilisk import Record, Service, service_update, Principal, Opt, Variant, nat32, nat64, null, text, Async\n"
        "from ic_python_db import Entity, String, Integer, TimestampedMixin\n"
        "\n"
        "if 'FXPair' not in dir():\n"
        "    class FXPair(Entity, TimestampedMixin):\n"
        "        __alias__ = 'name'\n"
        "        name = String(max_length=16)\n"
        "        base_symbol = String(max_length=8)\n"
        "        base_class = String(max_length=16)\n"
        "        quote_symbol = String(max_length=8)\n"
        "        quote_class = String(max_length=16)\n"
        "        rate = Integer(default=0)\n"
        "        decimals = Integer(default=9)\n"
        "        last_updated = Integer(default=0)\n"
        "        last_error = String(max_length=256)\n"
        "\n"
        "class _AssetClass(Variant, total=False):\n"
        "    Cryptocurrency: null\n"
        "    FiatCurrency: null\n"
        "class _Asset(Record):\n"
        "    symbol: text\n"
        "    class_: _AssetClass\n"
        "class _GetExchangeRateRequest(Record):\n"
        "    base_asset: _Asset\n"
        "    quote_asset: _Asset\n"
        "    timestamp: Opt[nat64]\n"
        "class _ExchangeRateMetadata(Record):\n"
        "    decimals: nat32\n"
        "    base_asset_num_queried_sources: nat64\n"
        "    base_asset_num_received_rates: nat64\n"
        "    quote_asset_num_queried_sources: nat64\n"
        "    quote_asset_num_received_rates: nat64\n"
        "    standard_deviation: nat64\n"
        "    forex_timestamp: Opt[nat64]\n"
        "class _ExchangeRate(Record):\n"
        "    base_asset: _Asset\n"
        "    quote_asset: _Asset\n"
        "    timestamp: nat64\n"
        "    rate: nat64\n"
        "    metadata: _ExchangeRateMetadata\n"
        "class _OtherError(Record):\n"
        "    code: nat32\n"
        "    description: text\n"
        "class _ExchangeRateError(Variant, total=False):\n"
        "    AnonymousPrincipalNotAllowed: null\n"
        "    Pending: null\n"
        "    CryptoBaseAssetNotFound: null\n"
        "    CryptoQuoteAssetNotFound: null\n"
        "    StablecoinRateNotFound: null\n"
        "    StablecoinRateTooFewRates: null\n"
        "    StablecoinRateZeroRate: null\n"
        "    ForexInvalidTimestamp: null\n"
        "    ForexBaseAssetNotFound: null\n"
        "    ForexQuoteAssetNotFound: null\n"
        "    ForexAssetsNotFound: null\n"
        "    RateLimited: null\n"
        "    NotEnoughCycles: null\n"
        "    FailedToAcceptCycles: null\n"
        "    InconsistentRatesReceived: null\n"
        "    Other: _OtherError\n"
        "class _GetExchangeRateResult(Variant, total=False):\n"
        "    Ok: _ExchangeRate\n"
        "    Err: _ExchangeRateError\n"
        "class XRCCanister(Service):\n"
        "    @service_update\n"
        "    def get_exchange_rate(self, args: _GetExchangeRateRequest) -> _GetExchangeRateResult: ...\n"
        "\n"
        "_ASSET_CLASS_CANDID = 'variant { Cryptocurrency : null; FiatCurrency : null }'\n"
        "_ASSET_CANDID = f'record {{ symbol : text; class : {_ASSET_CLASS_CANDID} }}'\n"
        "_METADATA_CANDID = 'record { decimals : nat32; base_asset_num_queried_sources : nat64; "
        "base_asset_num_received_rates : nat64; quote_asset_num_queried_sources : nat64; "
        "quote_asset_num_received_rates : nat64; standard_deviation : nat64; forex_timestamp : opt nat64 }'\n"
        "_EXCHANGE_RATE_CANDID = f'record {{ base_asset : {_ASSET_CANDID}; quote_asset : {_ASSET_CANDID}; "
        "timestamp : nat64; rate : nat64; metadata : {_METADATA_CANDID} }}'\n"
        "_OTHER_ERROR_CANDID = 'record { code : nat32; description : text }'\n"
        "_EXCHANGE_RATE_ERROR_CANDID = f'variant {{ AnonymousPrincipalNotAllowed : null; Pending : null; "
        "CryptoBaseAssetNotFound : null; CryptoQuoteAssetNotFound : null; StablecoinRateNotFound : null; "
        "StablecoinRateTooFewRates : null; StablecoinRateZeroRate : null; ForexInvalidTimestamp : null; "
        "ForexBaseAssetNotFound : null; ForexQuoteAssetNotFound : null; ForexAssetsNotFound : null; "
        "RateLimited : null; NotEnoughCycles : null; FailedToAcceptCycles : null; "
        "InconsistentRatesReceived : null; Other : {_OTHER_ERROR_CANDID} }}'\n"
        "_GET_EXCHANGE_RATE_RESULT_CANDID = f'variant {{ Ok : {_EXCHANGE_RATE_CANDID}; "
        "Err : {_EXCHANGE_RATE_ERROR_CANDID} }}'\n"
        "XRCCanister._arg_types = {'get_exchange_rate': f'record {{ base_asset : {_ASSET_CANDID}; "
        "quote_asset : {_ASSET_CANDID}; timestamp : opt nat64 }}'}\n"
        "XRCCanister._return_types = {'get_exchange_rate': _GET_EXCHANGE_RATE_RESULT_CANDID}\n"
        "\n"
        "def async_task():\n"
        "    xrc = XRCCanister(Principal.from_str('uf6dk-hyaaa-aaaaq-qaaaq-cai'))\n"
        "    pairs = list(FXPair.instances())\n"
        "    if not pairs:\n"
        "        return 'No FX pairs registered'\n"
        "    now = int(ic.time() / 1e9)\n"
        "    results = []\n"
        "    for pair in pairs:\n"
        "        try:\n"
        "            result = yield xrc.get_exchange_rate({\n"
        "                'base_asset': {'symbol': pair.base_symbol, 'class': {pair.base_class: None}},\n"
        "                'quote_asset': {'symbol': pair.quote_symbol, 'class': {pair.quote_class: None}},\n"
        "                'timestamp': None,\n"
        "            }).with_cycles(1_000_000_000)\n"
        "            raw = result\n"
        "            if hasattr(result, 'Ok'):\n"
        "                raw = result.Ok if result.Ok else result.Err\n"
        "            if isinstance(raw, dict) and 'Ok' in raw:\n"
        "                data = raw['Ok']\n"
        "                pair.rate = data['rate']\n"
        "                pair.decimals = data['metadata']['decimals']\n"
        "                pair.last_updated = now\n"
        "                pair.last_error = ''\n"
        "                human = data['rate'] / (10 ** data['metadata']['decimals'])\n"
        "                results.append(f'{pair.name}={human}')\n"
        "            elif isinstance(raw, dict) and 'Err' in raw:\n"
        "                pair.last_error = str(raw['Err'])[:255]\n"
        "                pair.last_updated = now\n"
        "                results.append(f'{pair.name}=ERR:{pair.last_error}')\n"
        "            else:\n"
        "                pair.last_error = str(raw)[:255]\n"
        "                pair.last_updated = now\n"
        "                results.append(f'{pair.name}=ERR:{pair.last_error}')\n"
        "        except Exception as e:\n"
        "            pair.last_error = str(e)[:255]\n"
        "            pair.last_updated = now\n"
        "            results.append(f'{pair.name}=ERR:{e}')\n"
        "    return 'FX_REFRESH_DONE: ' + '; '.join(results)\n"
    )

    # Write refresh code to canister memfs
    import base64
    b64 = base64.b64encode(refresh_code.encode()).decode()
    write_code = (
        "import base64\n"
        f"_data = base64.b64decode('{b64}').decode()\n"
        "with open('/_fx_refresh.py', 'w') as f:\n"
        "    f.write(_data)\n"
        "print('FX_FILE_WRITTEN')\n"
    )
    result = canister_exec(write_code, canister, network)
    if not result or 'FX_FILE_WRITTEN' not in result:
        return f"[error] failed to write refresh code: {result}"

    # Create task, add async step, start it
    create_result = canister_exec(
        _task_create_code("_fx_refresh"), canister, network
    )
    if not create_result:
        return "[error] failed to create refresh task"

    import re
    m = re.search(r'task\s+(\d+)', create_result, re.IGNORECASE)
    if not m:
        return f"[error] failed to parse task ID: {create_result}"
    tid = m.group(1)

    step_result = canister_exec(
        _task_add_step_code(f"{tid} --async --file /_fx_refresh.py"),
        canister, network,
    )
    if not step_result or "Added" not in step_result and "step" not in step_result.lower():
        _cleanup_fx_task(tid, canister, network)
        return f"[error] failed to add step: {step_result}"

    canister_exec(_task_start_code(tid), canister, network)
    print("Refreshing FX rates from XRC canister...")
    sys.stdout.flush()

    # Poll for completion
    for _ in range(30):
        _time.sleep(3)
        log = canister_exec(_task_log_code(tid), canister, network)
        if log and ("completed" in log or "failed" in log):
            # Clean up task and temp file
            _cleanup_fx_task(tid, canister, network)
            canister_exec(
                "import os; os.remove('/_fx_refresh.py') if os.path.exists('/_fx_refresh.py') else None",
                canister, network,
            )
            # Parse and display results
            if "FX_REFRESH_DONE:" in log:
                raw = log.split("FX_REFRESH_DONE:", 1)[1].strip()
                lines = []
                for item in raw.split(";"):
                    item = item.strip()
                    if "=" in item:
                        pair, val = item.split("=", 1)
                        if val.startswith("ERR:"):
                            lines.append(f"  {pair.strip()}: error — {val[4:]}")
                        else:
                            try:
                                lines.append(f"  {pair.strip()}: {float(val):,.6f}")
                            except ValueError:
                                lines.append(f"  {pair.strip()}: {val}")
                return "FX rates updated:\n" + "\n".join(lines)
            return log
        sys.stdout.write(".")
        sys.stdout.flush()

    _cleanup_fx_task(tid, canister, network)
    return "\n[timeout] Refresh task started but did not complete within 90s. Check with: %fx list"


def _cleanup_fx_task(tid: str, canister: str, network: str):
    """Delete a temporary FX refresh task."""
    try:
        canister_exec(_task_delete_code(tid), canister, network)
    except Exception:
        pass


# Well-known crypto and fiat symbols for auto-classification
_CRYPTO_SYMBOLS = {"BTC", "ETH", "ICP", "USDT", "USDC", "DAI"}
_FIAT_SYMBOLS = {"USD", "EUR", "GBP", "JPY", "CNY", "CHF", "CAD", "SGD", "CXDR"}


_FX_USAGE = (
    "Usage:\n"
    "  %fx                                    List all registered pairs with rates\n"
    "  %fx list                               Same as above\n"
    "  %fx register <base> <quote>            Register an FX pair for tracking\n"
    "  %fx unregister <base> <quote>          Remove an FX pair\n"
    "  %fx rate <base> <quote>                Show cached rate\n"
    "  %fx info <base> <quote>                Show full rate details\n"
    "  %fx refresh                            Refresh all pairs from XRC canister\n"
    "\n"
    "Symbols are auto-classified (crypto vs fiat). Override with flags:\n"
    "  %fx register EUR USD --fiat-base       Force base as FiatCurrency\n"
    "  %fx register BTC ETH --crypto-quote    Force quote as Cryptocurrency\n"
    "\n"
    "Supported crypto: BTC, ETH, ICP, USDT, USDC, DAI\n"
    "Supported fiat:   USD, EUR, GBP, JPY, CNY, CHF, CAD, SGD, CXDR"
)


def _handle_fx(args: str, canister: str, network: str) -> str:
    """Dispatch %fx subcommands."""
    parts = args.strip().split()

    if not parts or parts[0] == "list":
        return canister_exec(_fx_list_code(), canister, network)

    subcmd = parts[0]

    if subcmd == "register":
        if len(parts) < 3:
            return "Usage: %fx register <base> <quote> [--fiat-base] [--crypto-quote]"
        base = parts[1].upper()
        quote = parts[2].upper()
        # Auto-classify based on known symbols, allow flag overrides
        base_class = "Cryptocurrency" if base in _CRYPTO_SYMBOLS else "FiatCurrency"
        quote_class = "Cryptocurrency" if quote in _CRYPTO_SYMBOLS else "FiatCurrency"
        if "--fiat-base" in parts:
            base_class = "FiatCurrency"
        if "--crypto-base" in parts:
            base_class = "Cryptocurrency"
        if "--fiat-quote" in parts:
            quote_class = "FiatCurrency"
        if "--crypto-quote" in parts:
            quote_class = "Cryptocurrency"
        return canister_exec(
            _fx_register_code(base, quote, base_class, quote_class),
            canister, network,
        )

    if subcmd == "unregister":
        if len(parts) < 3:
            return "Usage: %fx unregister <base> <quote>"
        base = parts[1].upper()
        quote = parts[2].upper()
        return canister_exec(
            _fx_unregister_code(base, quote), canister, network,
        )

    if subcmd == "rate":
        if len(parts) < 3:
            return "Usage: %fx rate <base> <quote>"
        base = parts[1].upper()
        quote = parts[2].upper()
        return canister_exec(
            _fx_rate_code(base, quote), canister, network,
        )

    if subcmd == "info":
        if len(parts) < 3:
            return "Usage: %fx info <base> <quote>"
        base = parts[1].upper()
        quote = parts[2].upper()
        return canister_exec(
            _fx_info_code(base, quote), canister, network,
        )

    if subcmd == "refresh":
        return _fx_refresh(canister, network)

    return f"Unknown fx command: {subcmd}\n\n" + _FX_USAGE


# ---------------------------------------------------------------------------
# %group subcommand handlers — manage CryptoGroups on canister
# ---------------------------------------------------------------------------

_GROUP_USAGE = (
    "Usage:\n"
    "  %group                              List all groups\n"
    "  %group list                         List all groups\n"
    "  %group create <name> [description]  Create a new group\n"
    "  %group delete <name>                Delete a group and its members\n"
    "  %group members <name>               List members of a group\n"
    "  %group add <name> <principal>       Add a principal to a group\n"
    "  %group remove <name> <principal>    Remove a principal from a group"
)


def _group_list_code() -> str:
    """Generate on-canister code for %group list."""
    return (
        "from basilisk.os.crypto import CryptoGroup, CryptoGroupMember\n"
        "_groups = list(CryptoGroup.instances())\n"
        "if not _groups:\n"
        "    print('No groups defined.')\n"
        "else:\n"
        "    for _g in sorted(_groups, key=lambda g: str(g.name)):\n"
        "        _members = [m for m in CryptoGroupMember.instances() if str(m.group) == str(_g.name)]\n"
        "        _desc = f'  {_g.description}' if _g.description else ''\n"
        "        print(f'  {_g.name:<20} ({len(_members)} members){_desc}')\n"
    )


def _group_create_code(name: str, description: str = "") -> str:
    """Generate on-canister code for %group create."""
    esc_name = name.replace("'", "\\'")
    esc_desc = description.replace("'", "\\'")
    return (
        "from basilisk.os.crypto import CryptoGroup\n"
        f"_existing = CryptoGroup['{esc_name}']\n"
        "if _existing:\n"
        f"    print('Group {esc_name} already exists.')\n"
        "else:\n"
        f"    CryptoGroup(name='{esc_name}', description='{esc_desc}')\n"
        f"    print('Created group: {esc_name}')\n"
    )


def _group_delete_code(name: str) -> str:
    """Generate on-canister code for %group delete."""
    esc_name = name.replace("'", "\\'")
    return (
        "from basilisk.os.crypto import CryptoGroup, CryptoGroupMember\n"
        f"_g = CryptoGroup['{esc_name}']\n"
        "if not _g:\n"
        f"    print('Group {esc_name} not found.')\n"
        "else:\n"
        "    _count = 0\n"
        "    for _m in list(CryptoGroupMember.instances()):\n"
        f"        if str(_m.group) == '{esc_name}':\n"
        "            _m._delete()\n"
        "            _count += 1\n"
        "    _g._delete()\n"
        f"    print(f'Deleted group {esc_name} ({{_count}} members removed).')\n"
    )


def _group_members_code(name: str) -> str:
    """Generate on-canister code for %group members."""
    esc_name = name.replace("'", "\\'")
    return (
        "from basilisk.os.crypto import CryptoGroup, CryptoGroupMember\n"
        f"_g = CryptoGroup['{esc_name}']\n"
        "if not _g:\n"
        f"    print('Group {esc_name} not found.')\n"
        "else:\n"
        "    _members = [m for m in CryptoGroupMember.instances() if str(m.group) == str(_g.name)]\n"
        "    if not _members:\n"
        f"        print('Group {esc_name} has no members.')\n"
        "    else:\n"
        "        for _m in sorted(_members, key=lambda m: str(m.principal)):\n"
        "            print(f'  {str(_m.principal):<50} {_m.role or \"member\"}')\n"
    )


def _group_add_code(name: str, principal: str) -> str:
    """Generate on-canister code for %group add."""
    esc_name = name.replace("'", "\\'")
    esc_princ = principal.replace("'", "\\'")
    return (
        "from basilisk.os.crypto import CryptoGroup, CryptoGroupMember\n"
        f"_g = CryptoGroup['{esc_name}']\n"
        "if not _g:\n"
        f"    print('Group {esc_name} not found.')\n"
        "else:\n"
        "    _exists = False\n"
        "    for _m in CryptoGroupMember.instances():\n"
        f"        if str(_m.group) == '{esc_name}' and str(_m.principal) == '{esc_princ}':\n"
        "            _exists = True\n"
        "            break\n"
        "    if _exists:\n"
        f"        print('{esc_princ} is already a member of {esc_name}.')\n"
        "    else:\n"
        f"        CryptoGroupMember(group='{esc_name}', principal='{esc_princ}', role='member')\n"
        f"        print('Added {esc_princ} to group {esc_name}.')\n"
    )


def _group_remove_code(name: str, principal: str) -> str:
    """Generate on-canister code for %group remove."""
    esc_name = name.replace("'", "\\'")
    esc_princ = principal.replace("'", "\\'")
    return (
        "from basilisk.os.crypto import CryptoGroupMember, KeyEnvelope\n"
        "_found = False\n"
        "for _m in list(CryptoGroupMember.instances()):\n"
        f"    if str(_m.group) == '{esc_name}' and str(_m.principal) == '{esc_princ}':\n"
        "        _m._delete()\n"
        "        _found = True\n"
        "        break\n"
        "if _found:\n"
        "    _revoked = 0\n"
        "    for _e in list(KeyEnvelope.instances()):\n"
        f"        if str(_e.principal) == '{esc_princ}':\n"
        "            _e._delete()\n"
        "            _revoked += 1\n"
        f"    print(f'Removed {esc_princ} from group {esc_name}. Revoked {{_revoked}} envelope(s).')\n"
        "else:\n"
        f"    print('{esc_princ} is not a member of {esc_name}.')\n"
    )


def _handle_group(args: str, canister: str, network: str) -> str:
    """Dispatch %group subcommands."""
    parts = args.strip().split(None, 2)
    subcmd = parts[0] if parts else "list"

    if subcmd == "help":
        return _GROUP_USAGE

    if subcmd == "list":
        return canister_exec(_group_list_code(), canister, network)

    if subcmd == "create":
        if len(parts) < 2:
            return "Usage: %group create <name> [description]"
        name = parts[1]
        desc = parts[2] if len(parts) > 2 else ""
        return canister_exec(_group_create_code(name, desc), canister, network)

    if subcmd == "delete":
        if len(parts) < 2:
            return "Usage: %group delete <name>"
        return canister_exec(_group_delete_code(parts[1]), canister, network)

    if subcmd == "members":
        if len(parts) < 2:
            return "Usage: %group members <name>"
        return canister_exec(_group_members_code(parts[1]), canister, network)

    if subcmd == "add":
        add_parts = args.strip().split()
        if len(add_parts) < 3:
            return "Usage: %group add <name> <principal>"
        return canister_exec(_group_add_code(add_parts[1], add_parts[2]), canister, network)

    if subcmd == "remove":
        rm_parts = args.strip().split()
        if len(rm_parts) < 3:
            return "Usage: %group remove <name> <principal>"
        return canister_exec(_group_remove_code(rm_parts[1], rm_parts[2]), canister, network)

    return f"Unknown group command: {subcmd}\n\n" + _GROUP_USAGE


# ---------------------------------------------------------------------------
# %crypto subcommand handlers — encryption, sharing, envelopes
# ---------------------------------------------------------------------------

_CRYPTO_USAGE = (
    "Usage:\n"
    "  %crypto                                          Show this help\n"
    "  %crypto status                                   Show current identity & cached keys\n"
    "  %crypto scopes                                   List scopes accessible by current user\n"
    "\n"
    "  %crypto encrypt <file> [--scope <s>]             Encrypt a file in memfs (in-place)\n"
    "  %crypto decrypt <file>                           Decrypt a file in memfs (in-place)\n"
    "  %crypto encrypt-text <plaintext> [--scope <s>]   Encrypt a string, print ciphertext\n"
    "  %crypto decrypt-text <ciphertext>                Decrypt a string, print plaintext\n"
    "\n"
    "  %crypto share <scope> --with <principal>         Wrap DEK for a principal\n"
    "  %crypto share <scope> --with-group <group>       Wrap DEK for all group members\n"
    "  %crypto revoke <scope> --from <principal>        Delete principal's envelope\n"
    "  %crypto revoke <scope> --from-group <group>      Delete group members' envelopes\n"
    "\n"
    "  %crypto envelopes <scope>                        List who has access to a scope\n"
    "  %crypto init [--scope <s>]                       Create a new DEK for a scope"
)


def _crypto_status_code() -> str:
    """Generate on-canister code for %crypto status."""
    return (
        "from _cdk import ic\n"
        "from basilisk.os.crypto import KeyEnvelope\n"
        "_caller = ic.caller().to_str()\n"
        "_scopes = set()\n"
        "for _e in KeyEnvelope.instances():\n"
        "    if str(_e.principal) == _caller:\n"
        "        _scopes.add(str(_e.scope))\n"
        "print(f'Identity: {_caller}')\n"
        "print(f'Accessible scopes: {len(_scopes)}')\n"
        "if _scopes:\n"
        "    for _s in sorted(_scopes):\n"
        "        print(f'  {_s}')\n"
    )


def _crypto_scopes_code() -> str:
    """Generate on-canister code for %crypto scopes."""
    return (
        "from _cdk import ic\n"
        "from basilisk.os.crypto import KeyEnvelope\n"
        "_caller = ic.caller().to_str()\n"
        "_scopes = {}\n"
        "for _e in KeyEnvelope.instances():\n"
        "    _s = str(_e.scope)\n"
        "    if _s not in _scopes:\n"
        "        _scopes[_s] = {'total': 0, 'mine': False}\n"
        "    _scopes[_s]['total'] += 1\n"
        "    if str(_e.principal) == _caller:\n"
        "        _scopes[_s]['mine'] = True\n"
        "if not _scopes:\n"
        "    print('No encryption scopes defined.')\n"
        "else:\n"
        "    print(f'  {\"Scope\":<40} {\"Principals\":>10}  Access')\n"
        "    print('  ' + '-' * 65)\n"
        "    for _s in sorted(_scopes):\n"
        "        _info = _scopes[_s]\n"
        "        _access = 'YES' if _info['mine'] else '-'\n"
        "        print(f'  {_s:<40} {_info[\"total\"]:>10}  {_access}')\n"
    )


def _crypto_envelopes_code(scope: str) -> str:
    """Generate on-canister code for %crypto envelopes <scope>."""
    esc = scope.replace("'", "\\'")
    return (
        "from _cdk import ic\n"
        "from basilisk.os.crypto import KeyEnvelope, CryptoGroupMember\n"
        f"_scope = '{esc}'\n"
        "_caller = ic.caller().to_str()\n"
        "_envelopes = [e for e in KeyEnvelope.instances() if str(e.scope) == _scope]\n"
        "if not _envelopes:\n"
        "    print(f'No envelopes for scope {_scope}.')\n"
        "else:\n"
        "    print(f'Scope: {_scope}')\n"
        "    print(f'Authorized principals: {len(_envelopes)}')\n"
        "    print()\n"
        "    _group_map = {}\n"
        "    for _m in CryptoGroupMember.instances():\n"
        "        _p = str(_m.principal)\n"
        "        if _p not in _group_map:\n"
        "            _group_map[_p] = []\n"
        "        _group_map[_p].append(str(_m.group))\n"
        "    for _e in sorted(_envelopes, key=lambda e: str(e.principal)):\n"
        "        _p = str(_e.principal)\n"
        "        _self = ' (self)' if _p == _caller else ''\n"
        "        _groups = _group_map.get(_p, [])\n"
        "        _g = f' (groups: {\", \".join(_groups)})' if _groups else ''\n"
        "        print(f'  {_p}{_self}{_g}')\n"
    )


def _crypto_init_code(scope: str) -> str:
    """Generate on-canister code for %crypto init --scope <s>."""
    esc = scope.replace("'", "\\'")
    return (
        "from _cdk import ic\n"
        "import os as _os\n"
        "from basilisk.os.crypto import KeyEnvelope, encode_envelope\n"
        f"_scope = '{esc}'\n"
        "_caller = ic.caller().to_str()\n"
        "_existing = None\n"
        "for _e in KeyEnvelope.instances():\n"
        "    if str(_e.scope) == _scope and str(_e.principal) == _caller:\n"
        "        _existing = _e\n"
        "        break\n"
        "if _existing:\n"
        "    print(f'Scope {_scope} already initialized for you.')\n"
        "else:\n"
        "    _dek = _os.urandom(32)\n"
        "    KeyEnvelope(scope=_scope, principal=_caller, wrapped_dek=encode_envelope(_dek.hex()))\n"
        "    print(f'Created DEK for scope {_scope}.')\n"
        "    print(f'Wrapped for: {_caller} (self)')\n"
    )


def _crypto_share_principal_code(scope: str, principal: str) -> str:
    """Generate on-canister code for %crypto share <scope> --with <principal>."""
    esc_scope = scope.replace("'", "\\'")
    esc_princ = principal.replace("'", "\\'")
    return (
        "from basilisk.os.crypto import KeyEnvelope, encode_envelope\n"
        f"_scope = '{esc_scope}'\n"
        f"_target = '{esc_princ}'\n"
        "_existing = None\n"
        "for _e in KeyEnvelope.instances():\n"
        "    if str(_e.scope) == _scope and str(_e.principal) == _target:\n"
        "        _existing = _e\n"
        "        break\n"
        "if _existing:\n"
        "    print(f'{_target} already has access to scope {_scope}.')\n"
        "else:\n"
        "    KeyEnvelope(scope=_scope, principal=_target, wrapped_dek=encode_envelope(''))\n"
        "    print(f'Shared scope {_scope} with {_target}.')\n"
        "    print('Note: Client must wrap the DEK for this principal on next access.')\n"
    )


def _crypto_share_group_code(scope: str, group_name: str) -> str:
    """Generate on-canister code for %crypto share <scope> --with-group <group>."""
    esc_scope = scope.replace("'", "\\'")
    esc_group = group_name.replace("'", "\\'")
    return (
        "from basilisk.os.crypto import CryptoGroup, CryptoGroupMember, KeyEnvelope, encode_envelope\n"
        f"_scope = '{esc_scope}'\n"
        f"_group_name = '{esc_group}'\n"
        "_group = CryptoGroup[_group_name]\n"
        "if not _group:\n"
        "    print(f'Group {_group_name} not found.')\n"
        "else:\n"
        "    _members = [m for m in CryptoGroupMember.instances() if str(m.group) == _group_name]\n"
        "    _created = 0\n"
        "    _skipped = 0\n"
        "    for _m in _members:\n"
        "        _p = str(_m.principal)\n"
        "        _exists = False\n"
        "        for _e in KeyEnvelope.instances():\n"
        "            if str(_e.scope) == _scope and str(_e.principal) == _p:\n"
        "                _exists = True\n"
        "                break\n"
        "        if _exists:\n"
        "            _skipped += 1\n"
        "        else:\n"
        "            KeyEnvelope(scope=_scope, principal=_p, wrapped_dek=encode_envelope(''))\n"
        "            _created += 1\n"
        "    print(f'Shared scope {_scope} with group {_group_name}: {_created} new, {_skipped} existing.')\n"
    )


def _crypto_revoke_principal_code(scope: str, principal: str) -> str:
    """Generate on-canister code for %crypto revoke <scope> --from <principal>."""
    esc_scope = scope.replace("'", "\\'")
    esc_princ = principal.replace("'", "\\'")
    return (
        "from basilisk.os.crypto import KeyEnvelope\n"
        f"_scope = '{esc_scope}'\n"
        f"_target = '{esc_princ}'\n"
        "_found = False\n"
        "for _e in list(KeyEnvelope.instances()):\n"
        "    if str(_e.scope) == _scope and str(_e.principal) == _target:\n"
        "        _e._delete()\n"
        "        _found = True\n"
        "        break\n"
        "if _found:\n"
        "    print(f'Revoked access to scope {_scope} from {_target}.')\n"
        "else:\n"
        "    print(f'{_target} has no envelope for scope {_scope}.')\n"
    )


def _crypto_revoke_group_code(scope: str, group_name: str) -> str:
    """Generate on-canister code for %crypto revoke <scope> --from-group <group>."""
    esc_scope = scope.replace("'", "\\'")
    esc_group = group_name.replace("'", "\\'")
    return (
        "from basilisk.os.crypto import CryptoGroupMember, KeyEnvelope\n"
        f"_scope = '{esc_scope}'\n"
        f"_group_name = '{esc_group}'\n"
        "_members = [m for m in CryptoGroupMember.instances() if str(m.group) == _group_name]\n"
        "_principals = set(str(m.principal) for m in _members)\n"
        "_count = 0\n"
        "for _e in list(KeyEnvelope.instances()):\n"
        "    if str(_e.scope) == _scope and str(_e.principal) in _principals:\n"
        "        _e._delete()\n"
        "        _count += 1\n"
        "print(f'Revoked {_count} envelope(s) for scope {_scope} from group {_group_name}.')\n"
    )


def _crypto_encrypt_file_code(filepath: str, scope: str) -> str:
    """Generate on-canister code for %crypto encrypt <file> --scope <s>."""
    esc_path = filepath.replace("'", "\\'")
    esc_scope = scope.replace("'", "\\'")
    return (
        "import os as _os\n"
        "from basilisk.os.crypto import encode_ciphertext, is_encrypted\n"
        f"_path = '{esc_path}'\n"
        f"_scope = '{esc_scope}'\n"
        "try:\n"
        "    with open(_path, 'rb') as _f:\n"
        "        _data = _f.read()\n"
        "except FileNotFoundError:\n"
        "    print(f'{_path}: No such file')\n"
        "    _data = None\n"
        "if _data is not None:\n"
        "    if is_encrypted(_data.decode('utf-8', errors='replace')):\n"
        "        print(f'{_path}: Already encrypted.')\n"
        "    else:\n"
        "        _iv = _os.urandom(12)\n"
        "        _ct = encode_ciphertext(_iv.hex(), _data.hex())\n"
        "        with open(_path, 'w') as _f:\n"
        "            _f.write(_ct)\n"
        "        print(f'Encrypted {_path} ({len(_data)} bytes) with scope {_scope}.')\n"
    )


def _crypto_decrypt_file_code(filepath: str) -> str:
    """Generate on-canister code for %crypto decrypt <file>."""
    esc_path = filepath.replace("'", "\\'")
    return (
        "from basilisk.os.crypto import decode_ciphertext, is_encrypted\n"
        f"_path = '{esc_path}'\n"
        "try:\n"
        "    with open(_path, 'r') as _f:\n"
        "        _content = _f.read()\n"
        "except FileNotFoundError:\n"
        "    print(f'{_path}: No such file')\n"
        "    _content = None\n"
        "if _content is not None:\n"
        "    if not is_encrypted(_content):\n"
        "        print(f'{_path}: Not encrypted.')\n"
        "    else:\n"
        "        _iv, _data_hex = decode_ciphertext(_content)\n"
        "        _data = bytes.fromhex(_data_hex)\n"
        "        with open(_path, 'wb') as _f:\n"
        "            _f.write(_data)\n"
        "        print(f'Decrypted {_path} ({len(_data)} bytes).')\n"
    )


def _crypto_encrypt_text_code(plaintext: str, scope: str) -> str:
    """Generate on-canister code for %crypto encrypt-text."""
    esc_text = plaintext.replace("'", "\\'")
    esc_scope = scope.replace("'", "\\'")
    return (
        "import os as _os\n"
        "from basilisk.os.crypto import encode_ciphertext\n"
        f"_text = '{esc_text}'\n"
        "_iv = _os.urandom(12)\n"
        "_ct = encode_ciphertext(_iv.hex(), _text.encode('utf-8').hex())\n"
        "print(_ct)\n"
    )


def _crypto_decrypt_text_code(ciphertext: str) -> str:
    """Generate on-canister code for %crypto decrypt-text."""
    esc_ct = ciphertext.replace("'", "\\'")
    return (
        "from basilisk.os.crypto import decode_ciphertext, is_encrypted\n"
        f"_ct = '{esc_ct}'\n"
        "if not is_encrypted(_ct):\n"
        "    print('Not in encrypted format.')\n"
        "else:\n"
        "    _iv, _data_hex = decode_ciphertext(_ct)\n"
        "    print(bytes.fromhex(_data_hex).decode('utf-8', errors='replace'))\n"
    )


def _handle_crypto(args: str, canister: str, network: str) -> str:
    """Dispatch %crypto subcommands."""
    parts = args.strip().split()
    if not parts:
        return _CRYPTO_USAGE
    subcmd = parts[0]

    if subcmd == "help":
        return _CRYPTO_USAGE

    if subcmd == "status":
        return canister_exec(_crypto_status_code(), canister, network)

    if subcmd == "scopes":
        return canister_exec(_crypto_scopes_code(), canister, network)

    if subcmd == "envelopes":
        if len(parts) < 2:
            return "Usage: %crypto envelopes <scope>"
        return canister_exec(_crypto_envelopes_code(parts[1]), canister, network)

    if subcmd == "init":
        scope = "default"
        if "--scope" in parts:
            idx = parts.index("--scope")
            if idx + 1 < len(parts):
                scope = parts[idx + 1]
        return canister_exec(_crypto_init_code(scope), canister, network)

    if subcmd == "encrypt":
        if len(parts) < 2:
            return "Usage: %crypto encrypt <file> [--scope <s>]"
        filepath = parts[1]
        scope = "default"
        if "--scope" in parts:
            idx = parts.index("--scope")
            if idx + 1 < len(parts):
                scope = parts[idx + 1]
        return canister_exec(_crypto_encrypt_file_code(filepath, scope), canister, network)

    if subcmd == "decrypt":
        if len(parts) < 2:
            return "Usage: %crypto decrypt <file>"
        return canister_exec(_crypto_decrypt_file_code(parts[1]), canister, network)

    if subcmd == "encrypt-text":
        if len(parts) < 2:
            return "Usage: %crypto encrypt-text <plaintext> [--scope <s>]"
        # Collect text (everything except --scope flag)
        text_parts = []
        scope = "default"
        i = 1
        while i < len(parts):
            if parts[i] == "--scope" and i + 1 < len(parts):
                scope = parts[i + 1]
                i += 2
            else:
                text_parts.append(parts[i])
                i += 1
        text = " ".join(text_parts)
        return canister_exec(_crypto_encrypt_text_code(text, scope), canister, network)

    if subcmd == "decrypt-text":
        if len(parts) < 2:
            return "Usage: %crypto decrypt-text <ciphertext>"
        return canister_exec(_crypto_decrypt_text_code(parts[1]), canister, network)

    if subcmd == "share":
        if len(parts) < 4:
            return "Usage: %crypto share <scope> --with <principal>  or  --with-group <group>"
        scope = parts[1]
        if "--with-group" in parts:
            idx = parts.index("--with-group")
            if idx + 1 < len(parts):
                return canister_exec(_crypto_share_group_code(scope, parts[idx + 1]), canister, network)
        if "--with" in parts:
            idx = parts.index("--with")
            if idx + 1 < len(parts):
                return canister_exec(_crypto_share_principal_code(scope, parts[idx + 1]), canister, network)
        return "Usage: %crypto share <scope> --with <principal>  or  --with-group <group>"

    if subcmd == "revoke":
        if len(parts) < 4:
            return "Usage: %crypto revoke <scope> --from <principal>  or  --from-group <group>"
        scope = parts[1]
        if "--from-group" in parts:
            idx = parts.index("--from-group")
            if idx + 1 < len(parts):
                return canister_exec(_crypto_revoke_group_code(scope, parts[idx + 1]), canister, network)
        if "--from" in parts:
            idx = parts.index("--from")
            if idx + 1 < len(parts):
                return canister_exec(_crypto_revoke_principal_code(scope, parts[idx + 1]), canister, network)
        return "Usage: %crypto revoke <scope> --from <principal>  or  --from-group <group>"

    return f"Unknown crypto command: {subcmd}\n\n" + _CRYPTO_USAGE


def _handle_magic(line: str, canister: str, network: str) -> str:
    """Handle % magic commands. Returns output or None if not a magic command."""
    stripped = line.strip()

    # %run <file> — execute a file from canister memfs
    if stripped.startswith("%run "):
        filepath = stripped[5:].strip()
        if not filepath:
            return "Usage: %run <file>"
        esc = filepath.replace("'", "\\'")
        run_code = (
            "try:\n"
            f"    exec(open('{esc}').read())\n"
            "except FileNotFoundError:\n"
            f"    print('run: {esc}: No such file or directory')\n"
        )
        return canister_exec(run_code, canister, network)

    # %get <remote> [local] — download file from canister to local filesystem
    if stripped.startswith("%get "):
        parts = stripped[5:].strip().split(None, 1)
        if not parts:
            return "Usage: %get <remote_path> [local_path]"
        remote = parts[0]
        local = parts[1] if len(parts) > 1 else os.path.basename(remote)
        esc = remote.replace("'", "\\'")
        dl_code = (
            "import base64 as _b64\n"
            "try:\n"
            f"    _data = open('{esc}', 'rb').read()\n"
            "    print(_b64.b64encode(_data).decode())\n"
            "except FileNotFoundError:\n"
            f"    print('ERROR: {esc}: No such file or directory')\n"
        )
        result = canister_exec(dl_code, canister, network)
        if result is None:
            return "[error] no response from canister"
        result = result.strip()
        if result.startswith("ERROR:"):
            return f"[error] {result[7:]}"
        try:
            import base64
            data = base64.b64decode(result)
            os.makedirs(os.path.dirname(local) or ".", exist_ok=True)
            with open(local, "wb") as f:
                f.write(data)
            return f"Downloaded {remote} -> {local} ({len(data)} bytes)"
        except Exception as e:
            return f"[error] failed to save file: {e}"

    # %put <local> [remote] — upload local file to canister memfs
    if stripped.startswith("%put "):
        parts = stripped[5:].strip().split(None, 1)
        if not parts:
            return "Usage: %put <local_path> [remote_path]"
        local = parts[0]
        remote = parts[1] if len(parts) > 1 else os.path.basename(local)
        try:
            with open(local, "rb") as f:
                data = f.read()
        except FileNotFoundError:
            return f"[error] local file not found: {local}"
        import base64
        b64 = base64.b64encode(data).decode()
        esc = remote.replace("'", "\\'")
        ul_code = (
            "import base64 as _b64, os\n"
            f"_data = _b64.b64decode('{b64}')\n"
            f"_dir = os.path.dirname('{esc}')\n"
            "if _dir:\n"
            "    os.makedirs(_dir, exist_ok=True)\n"
            f"with open('{esc}', 'wb') as _f:\n"
            "    _f.write(_data)\n"
            f"print('Uploaded {len(data)} bytes -> {esc}')\n"
        )
        return canister_exec(ul_code, canister, network)

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

    # %wget <url> <dest> — download a file from URL into canister filesystem
    if stripped.startswith("%wget "):
        parts = stripped[6:].strip().split(None, 1)
        if len(parts) < 2:
            return "Usage: %wget <url> <dest_path>"
        return _wget(parts[0], parts[1], canister, network)

    # %db subcommand system
    if stripped == "%db" or stripped.startswith("%db "):
        args = stripped[3:].strip()
        return _handle_db(args, canister, network)

    # %task subcommand system
    if stripped == "%task" or stripped.startswith("%task "):
        args = stripped[5:].strip()
        return _handle_task(args, canister, network)

    # %wallet subcommand system
    if stripped == "%wallet" or stripped.startswith("%wallet "):
        args = stripped[7:].strip()
        return _handle_wallet(args, canister, network)

    # %vetkey subcommand system
    if stripped == "%vetkey" or stripped.startswith("%vetkey "):
        args = stripped[7:].strip()
        return _handle_vetkey(args, canister, network)

    # %fx subcommand system
    if stripped == "%fx" or stripped.startswith("%fx "):
        args = stripped[3:].strip()
        return _handle_fx(args, canister, network)

    # %group subcommand system
    if stripped == "%group" or stripped.startswith("%group "):
        args = stripped[6:].strip()
        return _handle_group(args, canister, network)

    # %crypto subcommand system
    if stripped == "%crypto" or stripped.startswith("%crypto "):
        args = stripped[7:].strip()
        return _handle_crypto(args, canister, network)

    # %info — comprehensive canister information
    if stripped == "%info":
        return _canister_info(canister, network)

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

    # Client-side version info
    ver = _get_basilisk_version()
    git = _get_git_info()
    ver_str = f"v{ver}"
    if git.get("commit"):
        ver_str += f"  ({git['commit']})"
    if git.get("commit_date"):
        ver_str += f"  {git['commit_date']}"

    print("=" * 60)
    print(f"  Basilisk Shell {ver_str}")
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

# Available libraries with versions
_libs = []
try:
    import basilisk
    _v = getattr(basilisk, '__version__', '')
    _libs.append(f'basilisk {_v}' if _v else 'basilisk')
except: pass
try:
    import ic_python_db
    _v = getattr(ic_python_db, '__version__', '')
    _libs.append(f'ic_python_db {_v}' if _v else 'ic_python_db')
except: pass
try:
    import ic_python_logging
    _v = getattr(ic_python_logging, '__version__', '')
    _libs.append(f'ic_python_logging {_v}' if _v else 'ic_python_logging')
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

print('__BASILISK_INFO__' + json.dumps(_info))
"""
    result = canister_exec(info_code, canister, network)

    # Parse the info JSON from the output
    info = {}
    for line in (result or "").split("\n"):
        if line.startswith("__BASILISK_INFO__"):
            try:
                import json
                info = json.loads(line[len("__BASILISK_INFO__"):])
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
    print("    %wget <url> <dest>        Download URL into canister")
    print("    %task                     List tasks (also %ps)")
    print('    %task create <name> [every Ns] [--code "..."|--file <f>]')
    print('    %task add-step <id|name> [--code "..."|--file <f>] [--async]')
    print("    %task info|log|start|stop|delete <id|name>")
    print("    %who                      List namespace variables")
    print("    %info                     Show canister info")
    print("    %db types|list|show|search Database exploration")
    print("    %db export|import          Import/export entities as JSON")
    print("    %db count|dump|clear       Database operations")
    print("    %wallet <token> balance   Check token balance (ckbtc, cketh, icp)")
    print("    %wallet <token> transfer <amt> <to>  Transfer tokens")
    print("    %vetkey pubkey            Get vetKD public key")
    print("    %vetkey derive <tpk_hex>  Derive encrypted vetKey")
    print("    %vetkey encrypt <target>  Encrypt file or text")
    print("    %vetkey decrypt <target>  Decrypt file or text")
    print("    %group                    Manage encryption groups")
    print("    %group create|delete|add|remove|members <name>")
    print("    %crypto status|scopes    Encryption status & scopes")
    print("    %crypto encrypt|decrypt  Encrypt/decrypt files & text")
    print("    %crypto share|revoke     Share/revoke scope access")
    print("    %crypto envelopes|init   View/create key envelopes")
    print("    %run <file>               Execute file from canister")
    print("    %get <remote> [local]     Download file from canister")
    print("    %put <local> [remote]     Upload file to canister")
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
            prompt = "basilisk>>> " if not buffer else "...        "
            line = input(prompt)
        except (EOFError, KeyboardInterrupt):
            print()
            break

        # Meta commands
        stripped = line.strip()
        if stripped in (":q", "exit", "quit"):
            break
        if stripped == "clear":
            os.system("clear")
            continue
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
        print(f"basilisk: {filepath}: No such file", file=sys.stderr)
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
        2. basilisk shell executes it on the canister
        3. basilisk shell writes result + READY marker to <outbox>
        4. Caller reads <outbox>, waits for READY marker, repeats
    """
    READY = "---READY---"

    # Initialize
    with open(inbox, "w") as f:
        f.write("")
    with open(outbox, "w") as f:
        f.write(f"{READY}\n")

    net_label = network or "local"
    print(f"basilisk shell watch mode started", file=sys.stderr)
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
                f.write(f"[basilisk shell error] {e}\n{READY}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="basilisk-shell",
        description="Basilisk Shell \u2014 a shell interpreter for IC canisters",
        add_help=False,
    )
    parser.add_argument("--canister", required=True, help="Canister name or ID")
    parser.add_argument("--network", default=None, help="Network: local, ic, or URL")
    parser.add_argument("-c", dest="code", default=None, help="Execute code string")
    parser.add_argument("--watch", default=None, metavar="INBOX",
                        help="Watch mode: read commands from INBOX file")
    parser.add_argument("--outbox", default="/tmp/basilisk_shell_out",
                        help="Output file for watch mode (default: /tmp/basilisk_shell_out)")
    parser.add_argument("--login", action="store_true",
                        help="Force interactive mode (used by basilisk sshd)")
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
