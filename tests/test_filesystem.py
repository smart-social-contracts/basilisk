"""
Integration tests for Basilisk OS filesystem — canister memfs via basilisk shell exec.

Tests the in-memory POSIX filesystem (open, read, write, os.listdir, pathlib, etc.)
by executing Python code on the canister through Basilisk Shell.
"""

import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import exec_on_canister


def _unique(prefix="test"):
    """Generate a unique name to avoid test collisions."""
    return f"/{prefix}_{uuid.uuid4().hex[:8]}"


# ===========================================================================
# Basic file operations
# ===========================================================================

class TestFileCreateReadDelete:
    """Test core file lifecycle: create, read, verify, delete."""

    def test_write_and_read_text(self, canister_reachable, canister, network):
        path = _unique("txtfile")
        # Write
        exec_on_canister(
            f"with open('{path}', 'w') as f: f.write('hello world')",
            canister, network,
        )
        # Read
        result = exec_on_canister(
            f"with open('{path}', 'r') as f: print(f.read())",
            canister, network,
        )
        assert result == "hello world"

    def test_write_and_read_binary(self, canister_reachable, canister, network):
        """Binary data must be base64-encoded for Candid text transport."""
        path = _unique("binfile")
        # Write binary via base64 (null bytes can't go through Candid text)
        import base64
        data = b'\x00\x01\x02\xff'
        b64 = base64.b64encode(data).decode()
        exec_on_canister(
            f"import base64\n"
            f"with open('{path}', 'wb') as f:\n"
            f"    f.write(base64.b64decode('{b64}'))",
            canister, network,
        )
        result = exec_on_canister(
            f"with open('{path}', 'rb') as f: print(list(f.read()))",
            canister, network,
        )
        assert result == "[0, 1, 2, 255]"

    def test_overwrite_file(self, canister_reachable, canister, network):
        path = _unique("overwrite")
        exec_on_canister(
            f"with open('{path}', 'w') as f: f.write('first')",
            canister, network,
        )
        exec_on_canister(
            f"with open('{path}', 'w') as f: f.write('second')",
            canister, network,
        )
        result = exec_on_canister(
            f"with open('{path}', 'r') as f: print(f.read())",
            canister, network,
        )
        assert result == "second"

    def test_append_file(self, canister_reachable, canister, network):
        path = _unique("append")
        exec_on_canister(
            f"with open('{path}', 'w') as f: f.write('hello')",
            canister, network,
        )
        exec_on_canister(
            f"with open('{path}', 'a') as f: f.write(' world')",
            canister, network,
        )
        result = exec_on_canister(
            f"with open('{path}', 'r') as f: print(f.read())",
            canister, network,
        )
        assert result == "hello world"

    def test_delete_file(self, canister_reachable, canister, network):
        path = _unique("delfile")
        exec_on_canister(
            f"with open('{path}', 'w') as f: f.write('temp')",
            canister, network,
        )
        exec_on_canister(f"import os; os.remove('{path}')", canister, network)
        result = exec_on_canister(
            f"import os; print(os.path.exists('{path}'))",
            canister, network,
        )
        assert result == "False"

    def test_read_nonexistent_file(self, canister_reachable, canister, network):
        result = exec_on_canister(
            "try:\n"
            "    open('/nonexistent_file_xyz', 'r')\n"
            "except FileNotFoundError as e:\n"
            "    print('FileNotFoundError')\n",
            canister, network,
        )
        assert "FileNotFoundError" in result

    def test_empty_file(self, canister_reachable, canister, network):
        path = _unique("empty")
        exec_on_canister(
            f"with open('{path}', 'w') as f: pass",
            canister, network,
        )
        result = exec_on_canister(
            f"with open('{path}', 'r') as f: print(repr(f.read()))",
            canister, network,
        )
        assert result == "''"

    def test_large_file(self, canister_reachable, canister, network):
        """Write and read a file larger than typical Candid payloads."""
        path = _unique("largefile")
        exec_on_canister(
            f"with open('{path}', 'w') as f: f.write('X' * 10000)",
            canister, network,
        )
        result = exec_on_canister(
            f"with open('{path}', 'r') as f: print(len(f.read()))",
            canister, network,
        )
        assert result == "10000"


# ===========================================================================
# Directory operations
# ===========================================================================

class TestDirectoryOps:
    """Test directory creation, listing, and removal."""

    def test_mkdir_and_listdir(self, canister_reachable, canister, network):
        dirname = _unique("dir")
        exec_on_canister(f"import os; os.makedirs('{dirname}')", canister, network)
        result = exec_on_canister(
            f"import os; print(os.path.isdir('{dirname}'))",
            canister, network,
        )
        assert result == "True"

    def test_nested_mkdir(self, canister_reachable, canister, network):
        base = _unique("nested")
        deep = f"{base}/a/b/c"
        exec_on_canister(
            f"import os; os.makedirs('{deep}', exist_ok=True)",
            canister, network,
        )
        result = exec_on_canister(
            f"import os; print(os.path.isdir('{deep}'))",
            canister, network,
        )
        assert result == "True"

    def test_listdir_contents(self, canister_reachable, canister, network):
        base = _unique("lsdir")
        exec_on_canister(f"import os; os.makedirs('{base}')", canister, network)
        exec_on_canister(
            f"with open('{base}/file1.txt', 'w') as f: f.write('a')",
            canister, network,
        )
        exec_on_canister(
            f"with open('{base}/file2.txt', 'w') as f: f.write('b')",
            canister, network,
        )
        result = exec_on_canister(
            f"import os; print(sorted(os.listdir('{base}')))",
            canister, network,
        )
        assert "file1.txt" in result
        assert "file2.txt" in result

    def test_listdir_empty_dir(self, canister_reachable, canister, network):
        base = _unique("emptydir")
        exec_on_canister(f"import os; os.makedirs('{base}')", canister, network)
        result = exec_on_canister(
            f"import os; print(os.listdir('{base}'))",
            canister, network,
        )
        assert result == "[]"

    def test_listdir_nonexistent(self, canister_reachable, canister, network):
        result = exec_on_canister(
            "try:\n"
            "    import os; os.listdir('/nonexistent_dir_xyz')\n"
            "except FileNotFoundError:\n"
            "    print('FileNotFoundError')\n",
            canister, network,
        )
        assert "FileNotFoundError" in result

    def test_rmdir(self, canister_reachable, canister, network):
        dirname = _unique("rmdir")
        exec_on_canister(f"import os; os.makedirs('{dirname}')", canister, network)
        exec_on_canister(f"import os; os.rmdir('{dirname}')", canister, network)
        result = exec_on_canister(
            f"import os; print(os.path.isdir('{dirname}'))",
            canister, network,
        )
        assert result == "False"


# ===========================================================================
# os.path operations
# ===========================================================================

class TestOsPath:
    """Test os.path functions on canister memfs."""

    def test_exists_file(self, canister_reachable, canister, network):
        path = _unique("existsfile")
        exec_on_canister(
            f"with open('{path}', 'w') as f: f.write('x')",
            canister, network,
        )
        result = exec_on_canister(
            f"import os; print(os.path.exists('{path}'))",
            canister, network,
        )
        assert result == "True"

    def test_exists_dir(self, canister_reachable, canister, network):
        path = _unique("existsdir")
        exec_on_canister(f"import os; os.makedirs('{path}')", canister, network)
        result = exec_on_canister(
            f"import os; print(os.path.exists('{path}'))",
            canister, network,
        )
        assert result == "True"

    def test_isfile(self, canister_reachable, canister, network):
        path = _unique("isfile")
        exec_on_canister(
            f"with open('{path}', 'w') as f: f.write('x')",
            canister, network,
        )
        result = exec_on_canister(
            f"import os; print(os.path.isfile('{path}'))",
            canister, network,
        )
        assert result == "True"

    def test_isdir(self, canister_reachable, canister, network):
        path = _unique("isdir")
        exec_on_canister(f"import os; os.makedirs('{path}')", canister, network)
        result = exec_on_canister(
            f"import os; print(os.path.isdir('{path}'))",
            canister, network,
        )
        assert result == "True"

    def test_getsize(self, canister_reachable, canister, network):
        path = _unique("sizefile")
        exec_on_canister(
            f"with open('{path}', 'w') as f: f.write('12345')",
            canister, network,
        )
        result = exec_on_canister(
            f"import os; print(os.path.getsize('{path}'))",
            canister, network,
        )
        assert result == "5"

    def test_stat(self, canister_reachable, canister, network):
        path = _unique("statfile")
        exec_on_canister(
            f"with open('{path}', 'w') as f: f.write('data')",
            canister, network,
        )
        result = exec_on_canister(
            f"import os\ns = os.stat('{path}')\nprint(s.st_size, s.st_mode)",
            canister, network,
        )
        assert "4" in result  # size = 4 bytes


# ===========================================================================
# pathlib operations
# ===========================================================================

class TestPathlib:
    """Test pathlib.Path on canister memfs."""

    def test_path_write_read(self, canister_reachable, canister, network):
        path = _unique("pathlib")
        exec_on_canister(
            f"from pathlib import Path; Path('{path}').write_text('pathlib-test')",
            canister, network,
        )
        result = exec_on_canister(
            f"from pathlib import Path; print(Path('{path}').read_text())",
            canister, network,
        )
        assert result == "pathlib-test"

    def test_path_exists(self, canister_reachable, canister, network):
        path = _unique("plexists")
        exec_on_canister(
            f"from pathlib import Path; Path('{path}').write_text('x')",
            canister, network,
        )
        result = exec_on_canister(
            f"from pathlib import Path; print(Path('{path}').exists())",
            canister, network,
        )
        assert result == "True"

    def test_path_mkdir(self, canister_reachable, canister, network):
        path = _unique("plmkdir")
        exec_on_canister(
            f"from pathlib import Path; Path('{path}').mkdir(parents=True)",
            canister, network,
        )
        result = exec_on_canister(
            f"from pathlib import Path; print(Path('{path}').is_dir())",
            canister, network,
        )
        assert result == "True"

    def test_path_iterdir(self, canister_reachable, canister, network):
        base = _unique("pliter")
        exec_on_canister(
            f"from pathlib import Path\n"
            f"Path('{base}').mkdir(parents=True)\n"
            f"Path('{base}/a.txt').write_text('a')\n"
            f"Path('{base}/b.txt').write_text('b')",
            canister, network,
        )
        result = exec_on_canister(
            f"from pathlib import Path\n"
            f"print(sorted([p.name for p in Path('{base}').iterdir()]))",
            canister, network,
        )
        assert "a.txt" in result
        assert "b.txt" in result

    def test_path_unlink(self, canister_reachable, canister, network):
        path = _unique("plunlink")
        exec_on_canister(
            f"from pathlib import Path; Path('{path}').write_text('x')",
            canister, network,
        )
        exec_on_canister(
            f"from pathlib import Path; Path('{path}').unlink()",
            canister, network,
        )
        result = exec_on_canister(
            f"from pathlib import Path; print(Path('{path}').exists())",
            canister, network,
        )
        assert result == "False"


# ===========================================================================
# Edge cases and special characters
# ===========================================================================

class TestFilesystemEdgeCases:
    """Edge cases for the filesystem."""

    def test_special_chars_in_filename(self, canister_reachable, canister, network):
        """Filenames with spaces and special chars."""
        path = _unique("special file (1)")
        exec_on_canister(
            f"with open('{path}', 'w') as f: f.write('ok')",
            canister, network,
        )
        result = exec_on_canister(
            f"with open('{path}', 'r') as f: print(f.read())",
            canister, network,
        )
        assert result == "ok"

    def test_unicode_filename(self, canister_reachable, canister, network):
        path = _unique("café")
        exec_on_canister(
            f"with open('{path}', 'w') as f: f.write('unicode')",
            canister, network,
        )
        result = exec_on_canister(
            f"with open('{path}', 'r') as f: print(f.read())",
            canister, network,
        )
        assert result == "unicode"

    def test_unicode_content(self, canister_reachable, canister, network):
        path = _unique("unicontent")
        exec_on_canister(
            f"with open('{path}', 'w') as f: f.write('日本語テスト')",
            canister, network,
        )
        result = exec_on_canister(
            f"with open('{path}', 'r') as f: print(f.read())",
            canister, network,
        )
        assert "日本語" in result

    def test_rename_file(self, canister_reachable, canister, network):
        old = _unique("rename_old")
        new = _unique("rename_new")
        exec_on_canister(
            f"with open('{old}', 'w') as f: f.write('moved')",
            canister, network,
        )
        exec_on_canister(
            f"import os; os.rename('{old}', '{new}')",
            canister, network,
        )
        result = exec_on_canister(
            f"with open('{new}', 'r') as f: print(f.read())",
            canister, network,
        )
        assert result == "moved"
        # Old should not exist
        result2 = exec_on_canister(
            f"import os; print(os.path.exists('{old}'))",
            canister, network,
        )
        assert result2 == "False"

    def test_deeply_nested_path(self, canister_reachable, canister, network):
        base = _unique("deep")
        deep = f"{base}/a/b/c/d/e/f/g"
        exec_on_canister(
            f"import os; os.makedirs('{deep}', exist_ok=True)",
            canister, network,
        )
        exec_on_canister(
            f"with open('{deep}/file.txt', 'w') as f: f.write('deep')",
            canister, network,
        )
        result = exec_on_canister(
            f"with open('{deep}/file.txt', 'r') as f: print(f.read())",
            canister, network,
        )
        assert result == "deep"
