"""
Integration tests for Basilisk SFTP — virtual filesystem over SSH.

Tests SFTP operations against a live canister via the basilisk sshd SSH server.
These tests require basilisk sshd to be running (or test the SFTP server class
directly via canister_exec).

For full SFTP-over-SSH tests, start sshd first:
    python -m basilisk.sshd --canister <id> --network ic

Then run:
    pytest tests/test_sftp.py -v
"""

import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import exec_on_canister


def _unique(prefix="sftp"):
    """Generate a unique path to avoid test collisions."""
    return f"/{prefix}_{uuid.uuid4().hex[:8]}"


# ===========================================================================
# SFTP utility functions (pure, no canister needed)
# ===========================================================================

class TestSFTPUtils:
    """Test SFTP utility functions."""

    def test_norm_absolute(self):
        from basilisk.sftp import _norm
        assert _norm("/foo/bar") == "/foo/bar"

    def test_norm_relative(self):
        from basilisk.sftp import _norm
        assert _norm("foo/bar") == "/foo/bar"

    def test_norm_dotdot(self):
        from basilisk.sftp import _norm
        assert _norm("/foo/bar/../baz") == "/foo/baz"

    def test_norm_dot(self):
        from basilisk.sftp import _norm
        assert _norm("/foo/./bar") == "/foo/bar"

    def test_norm_double_slash(self):
        from basilisk.sftp import _norm
        assert _norm("//foo///bar//") == "/foo/bar"

    def test_norm_root(self):
        from basilisk.sftp import _norm
        assert _norm("/") == "/"

    def test_norm_bytes(self):
        from basilisk.sftp import _norm
        assert _norm(b"/foo/bar") == "/foo/bar"

    def test_esc_single_quote(self):
        from basilisk.sftp import _esc
        assert _esc("it's") == "it\\'s"

    def test_esc_backslash(self):
        from basilisk.sftp import _esc
        assert _esc("a\\b") == "a\\\\b"

    def test_indent(self):
        from basilisk.sftp import _indent
        result = _indent("line1\nline2", 4)
        assert result == "    line1\n    line2"


# ===========================================================================
# SFTP file operations via canister exec (no SSH server needed)
# ===========================================================================

class TestSFTPFileOps:
    """
    Test the filesystem operations that SFTP relies on,
    exercised via direct canister_exec (same code paths SFTP uses).
    """

    def test_write_read_binary(self, canister_reachable, canister, network):
        """Write binary via base64, read back — the core SFTP data path."""
        path = _unique("binrw")
        import base64
        content = b"hello sftp binary \x00\x01\xff"
        b64 = base64.b64encode(content).decode()

        exec_on_canister(
            f"import base64\n"
            f"data = base64.b64decode('{b64}')\n"
            f"with open('{path}', 'wb') as f: f.write(data)\n",
            canister, network,
        )

        result = exec_on_canister(
            f"import base64\n"
            f"with open('{path}', 'rb') as f: raw = f.read()\n"
            f"print(base64.b64encode(raw).decode())\n",
            canister, network,
        )
        recovered = base64.b64decode(result)
        assert recovered == content

    def test_stat_file(self, canister_reachable, canister, network):
        """os.stat on a file should return mode and size."""
        path = _unique("statf")
        exec_on_canister(
            f"with open('{path}', 'w') as f: f.write('12345')",
            canister, network,
        )
        result = exec_on_canister(
            f"import os, json\n"
            f"s = os.stat('{path}')\n"
            f"print(json.dumps({{'mode': s.st_mode, 'size': s.st_size}}))\n",
            canister, network,
        )
        import json
        data = json.loads(result)
        assert data["size"] == 5
        assert data["mode"] & 0o100000  # regular file bit

    def test_stat_directory(self, canister_reachable, canister, network):
        """os.stat on a directory should return directory mode."""
        path = _unique("statd")
        exec_on_canister(
            f"import os; os.makedirs('{path}')", canister, network
        )
        result = exec_on_canister(
            f"import os, json\n"
            f"s = os.stat('{path}')\n"
            f"print(json.dumps({{'mode': s.st_mode}}))\n",
            canister, network,
        )
        import json
        data = json.loads(result)
        assert data["mode"] & 0o040000  # directory bit

    def test_stat_nonexistent(self, canister_reachable, canister, network):
        """os.stat on nonexistent path should raise FileNotFoundError."""
        result = exec_on_canister(
            "import os\n"
            "try:\n"
            "    os.stat('/nonexistent_sftp_path_xyz')\n"
            "except FileNotFoundError:\n"
            "    print('ENOENT')\n",
            canister, network,
        )
        assert "ENOENT" in result

    def test_listdir_json(self, canister_reachable, canister, network):
        """listdir returning structured data — the SFTP listdir path."""
        base = _unique("lsj")
        exec_on_canister(
            f"import os\n"
            f"os.makedirs('{base}')\n"
            f"with open('{base}/a.txt', 'w') as f: f.write('a')\n"
            f"with open('{base}/b.txt', 'w') as f: f.write('bb')\n",
            canister, network,
        )
        result = exec_on_canister(
            f"import os, json\n"
            f"entries = []\n"
            f"for name in os.listdir('{base}'):\n"
            f"    full = '{base}/' + name\n"
            f"    s = os.stat(full)\n"
            f"    entries.append({{'name': name, 'mode': s.st_mode, 'size': s.st_size}})\n"
            f"print(json.dumps({{'entries': entries}}))\n",
            canister, network,
        )
        import json
        data = json.loads(result)
        names = {e["name"] for e in data["entries"]}
        assert "a.txt" in names
        assert "b.txt" in names

    def test_mkdir_via_exec(self, canister_reachable, canister, network):
        path = _unique("mkd")
        exec_on_canister(
            f"import os; os.mkdir('{path}')", canister, network
        )
        result = exec_on_canister(
            f"import os; print(os.path.isdir('{path}'))", canister, network
        )
        assert result == "True"

    def test_rmdir_via_exec(self, canister_reachable, canister, network):
        path = _unique("rmd")
        exec_on_canister(
            f"import os; os.mkdir('{path}')", canister, network
        )
        exec_on_canister(
            f"import os; os.rmdir('{path}')", canister, network
        )
        result = exec_on_canister(
            f"import os; print(os.path.isdir('{path}'))", canister, network
        )
        assert result == "False"

    def test_remove_via_exec(self, canister_reachable, canister, network):
        path = _unique("rmf")
        exec_on_canister(
            f"with open('{path}', 'w') as f: f.write('x')", canister, network
        )
        exec_on_canister(
            f"import os; os.remove('{path}')", canister, network
        )
        result = exec_on_canister(
            f"import os; print(os.path.exists('{path}'))", canister, network
        )
        assert result == "False"

    def test_rename_via_exec(self, canister_reachable, canister, network):
        old = _unique("rnold")
        new = _unique("rnnew")
        exec_on_canister(
            f"with open('{old}', 'w') as f: f.write('data')", canister, network
        )
        exec_on_canister(
            f"import os; os.rename('{old}', '{new}')", canister, network
        )
        result = exec_on_canister(
            f"with open('{new}', 'r') as f: print(f.read())", canister, network
        )
        assert result == "data"
        result2 = exec_on_canister(
            f"import os; print(os.path.exists('{old}'))", canister, network
        )
        assert result2 == "False"


# ===========================================================================
# Base64 round-trip (critical for SFTP binary transport)
# ===========================================================================

class TestBase64Transport:
    """Test base64 encoding round-trip — SFTP's binary data path."""

    def test_small_binary(self, canister_reachable, canister, network):
        import base64
        data = bytes(range(256))
        b64 = base64.b64encode(data).decode()
        path = _unique("b64sm")

        exec_on_canister(
            f"import base64\n"
            f"with open('{path}', 'wb') as f:\n"
            f"    f.write(base64.b64decode('{b64}'))\n",
            canister, network,
        )
        result = exec_on_canister(
            f"import base64\n"
            f"with open('{path}', 'rb') as f:\n"
            f"    print(base64.b64encode(f.read()).decode())\n",
            canister, network,
        )
        assert base64.b64decode(result) == data

    def test_medium_binary(self, canister_reachable, canister, network):
        """Test ~4KB binary transfer (typical small file)."""
        import base64
        data = os.urandom(4096)
        b64 = base64.b64encode(data).decode()
        path = _unique("b64md")

        exec_on_canister(
            f"import base64\n"
            f"with open('{path}', 'wb') as f:\n"
            f"    f.write(base64.b64decode('{b64}'))\n",
            canister, network,
        )
        result = exec_on_canister(
            f"import base64\n"
            f"with open('{path}', 'rb') as f:\n"
            f"    print(base64.b64encode(f.read()).decode())\n",
            canister, network,
        )
        assert base64.b64decode(result) == data

    def test_empty_binary(self, canister_reachable, canister, network):
        """Empty file via base64."""
        import base64
        path = _unique("b64empty")
        exec_on_canister(
            f"import base64\n"
            f"with open('{path}', 'wb') as f:\n"
            f"    f.write(base64.b64decode(''))\n",
            canister, network,
        )
        result = exec_on_canister(
            f"import base64\n"
            f"with open('{path}', 'rb') as f:\n"
            f"    print(base64.b64encode(f.read()).decode())\n",
            canister, network,
        )
        assert base64.b64decode(result) == b""
