"""
bosh SFTP — virtual filesystem backed by a Basilisk OS canister's memfs.

Each SFTP operation translates to Python code executed on the canister via
execute_code_shell. Binary data is base64-encoded for transport.
"""

import base64
import json
import stat as stat_module
import time

import asyncssh
from asyncssh.sftp import SFTPAttrs, SFTPName, SFTPError

from basilisk.bosh import canister_exec

# Marker prefix for structured JSON responses from canister
_MARKER = "__BOSH_SFTP__"


class CanisterSFTPServer(asyncssh.SFTPServer):
    """SFTP server backed by the canister's in-memory filesystem."""

    def __init__(self, conn, canister: str, network: str):
        super().__init__(conn)
        self._canister = canister
        self._network = network
        self._handles = {}
        self._next_id = 0

    # -- helpers --

    def _exec(self, code: str) -> str:
        """Execute Python on the canister and return raw output."""
        return canister_exec(code, self._canister, self._network) or ""

    def _exec_json(self, code: str):
        """Execute Python on canister, expecting JSON after _MARKER."""
        full_code = f"""
import json as _j
try:
{_indent(code, 4)}
except FileNotFoundError as _e:
    print('{_MARKER}' + _j.dumps({{"error": "ENOENT", "msg": str(_e)}}))
except NotADirectoryError as _e:
    print('{_MARKER}' + _j.dumps({{"error": "ENOTDIR", "msg": str(_e)}}))
except IsADirectoryError as _e:
    print('{_MARKER}' + _j.dumps({{"error": "EISDIR", "msg": str(_e)}}))
except PermissionError as _e:
    print('{_MARKER}' + _j.dumps({{"error": "EACCES", "msg": str(_e)}}))
except FileExistsError as _e:
    print('{_MARKER}' + _j.dumps({{"error": "EEXIST", "msg": str(_e)}}))
except OSError as _e:
    print('{_MARKER}' + _j.dumps({{"error": "EIO", "msg": str(_e)}}))
except Exception as _e:
    print('{_MARKER}' + _j.dumps({{"error": "EIO", "msg": str(_e)}}))
"""
        result = self._exec(full_code)
        for line in result.split("\n"):
            if line.startswith(_MARKER):
                data = json.loads(line[len(_MARKER):])
                if "error" in data:
                    _raise_sftp_error(data["error"], data.get("msg", ""))
                return data
        raise SFTPError(asyncssh.FX_FAILURE, f"No response from canister")

    def _new_handle(self):
        self._next_id += 1
        return self._next_id

    # -- SFTP operations --

    def stat(self, path):
        path = _norm(path)
        data = self._exec_json(f"""
import os
_s = os.stat('{_esc(path)}')
print('{_MARKER}' + _j.dumps({{"mode": _s.st_mode, "size": _s.st_size, "mtime": int(_s.st_mtime)}}))
""")
        return _to_attrs(data)

    lstat = stat  # no symlinks in memfs

    def listdir(self, path):
        path = _norm(path)
        data = self._exec_json(f"""
import os
_path = '{_esc(path)}'
_entries = []
for _name in os.listdir(_path):
    _full = _path.rstrip('/') + '/' + _name
    try:
        _s = os.stat(_full)
        _entries.append({{"name": _name, "mode": _s.st_mode, "size": _s.st_size}})
    except Exception:
        _entries.append({{"name": _name, "mode": 0o100644, "size": 0}})
print('{_MARKER}' + _j.dumps({{"entries": _entries}}))
""")
        result = []
        for e in data.get("entries", []):
            attrs = SFTPAttrs(
                size=e.get("size", 0),
                permissions=e.get("mode", 0o100644),
                mtime=0,
            )
            result.append(SFTPName(e["name"].encode() if isinstance(e["name"], str) else e["name"], attrs=attrs))
        return result

    def open(self, path, pflags, attrs):
        path = _norm(path)
        handle = self._new_handle()

        is_read = bool(pflags & asyncssh.FXF_READ)
        is_write = bool(pflags & (asyncssh.FXF_WRITE | asyncssh.FXF_CREAT | asyncssh.FXF_TRUNC | asyncssh.FXF_APPEND))

        file_data = b""
        if is_read:
            data = self._exec_json(f"""
import base64 as _b64
with open('{_esc(path)}', 'rb') as _f:
    _raw = _f.read()
print('{_MARKER}' + _j.dumps({{"b64": _b64.b64encode(_raw).decode()}}))
""")
            file_data = base64.b64decode(data.get("b64", ""))

        self._handles[handle] = {
            "path": path,
            "data": bytearray(file_data),
            "dirty": False,
            "read": is_read,
            "write": is_write,
        }
        return handle

    def close(self, handle):
        info = self._handles.pop(handle, None)
        if info and info["dirty"]:
            b64 = base64.b64encode(bytes(info["data"])).decode()
            self._exec_json(f"""
import base64 as _b64
_data = _b64.b64decode('{b64}')
with open('{_esc(info["path"])}', 'wb') as _f:
    _f.write(_data)
print('{_MARKER}' + _j.dumps({{"ok": True, "size": len(_data)}}))
""")

    def read(self, handle, offset, length):
        info = self._handles.get(handle)
        if not info:
            raise SFTPError(asyncssh.FX_FAILURE, "Invalid handle")
        data = info["data"]
        end = min(offset + length, len(data))
        if offset >= len(data):
            return b""
        return bytes(data[offset:end])

    def write(self, handle, offset, data):
        info = self._handles.get(handle)
        if not info:
            raise SFTPError(asyncssh.FX_FAILURE, "Invalid handle")
        buf = info["data"]
        end = offset + len(data)
        if end > len(buf):
            buf.extend(b"\x00" * (end - len(buf)))
        buf[offset:end] = data
        info["dirty"] = True
        return len(data)

    def mkdir(self, path, attrs):
        path = _norm(path)
        self._exec_json(f"""
import os
os.mkdir('{_esc(path)}')
print('{_MARKER}' + _j.dumps({{"ok": True}}))
""")

    def rmdir(self, path):
        path = _norm(path)
        self._exec_json(f"""
import os
os.rmdir('{_esc(path)}')
print('{_MARKER}' + _j.dumps({{"ok": True}}))
""")

    def remove(self, path):
        path = _norm(path)
        self._exec_json(f"""
import os
os.remove('{_esc(path)}')
print('{_MARKER}' + _j.dumps({{"ok": True}}))
""")

    def rename(self, oldpath, newpath):
        oldpath, newpath = _norm(oldpath), _norm(newpath)
        self._exec_json(f"""
import os
os.rename('{_esc(oldpath)}', '{_esc(newpath)}')
print('{_MARKER}' + _j.dumps({{"ok": True}}))
""")

    def realpath(self, path):
        return _norm(path).encode() if isinstance(path, str) else _norm(path.decode())


# -- utility functions --

def _norm(path):
    """Normalize path to absolute POSIX."""
    if isinstance(path, bytes):
        path = path.decode("utf-8", errors="replace")
    if not path.startswith("/"):
        path = "/" + path
    parts = []
    for part in path.replace("\\", "/").split("/"):
        if part == "" or part == ".":
            continue
        if part == "..":
            if parts:
                parts.pop()
        else:
            parts.append(part)
    return "/" + "/".join(parts)


def _esc(s: str) -> str:
    """Escape a string for safe embedding in Python single-quoted string."""
    return s.replace("\\", "\\\\").replace("'", "\\'")


def _indent(code: str, spaces: int) -> str:
    """Indent every line of code by given spaces."""
    prefix = " " * spaces
    return "\n".join(prefix + line for line in code.strip().split("\n"))


def _to_attrs(data: dict) -> SFTPAttrs:
    """Convert a dict with mode/size/mtime to SFTPAttrs."""
    return SFTPAttrs(
        size=data.get("size", 0),
        permissions=data.get("mode", 0o100644),
        mtime=data.get("mtime", 0),
    )


def _raise_sftp_error(code: str, msg: str):
    """Raise an appropriate SFTPError from canister error code."""
    mapping = {
        "ENOENT": asyncssh.FX_NO_SUCH_FILE,
        "ENOTDIR": asyncssh.FX_NO_SUCH_FILE,
        "EISDIR": asyncssh.FX_FAILURE,
        "EACCES": asyncssh.FX_PERMISSION_DENIED,
        "EEXIST": asyncssh.FX_FAILURE,
        "EIO": asyncssh.FX_FAILURE,
    }
    raise SFTPError(mapping.get(code, asyncssh.FX_FAILURE), msg)
