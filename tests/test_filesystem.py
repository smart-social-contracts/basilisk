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


# ===========================================================================
# Immediate file persistence via StableBTreeMap
# ===========================================================================

# Injection code: sets up file persistence on canisters that don't have
# the updated shim baked in.  Idempotent — skips if already present.
_INJECT_PERSISTENCE = """
import sys as _sys
_m = _sys.modules['__main__'].__dict__
if '_basilisk_file_store' not in _m:
    _VOLATILE_PREFIXES = _m.get('_VOLATILE_PREFIXES', ['/tmp/', '/proc/', '/dev/'])
    _SBM = _m.get('StableBTreeMap') or _sys.modules['__main__'].__dict__['StableBTreeMap']
    _fs = _SBM[str, str](memory_id=255, max_key_size=500, max_value_size=0)
    _m['_basilisk_file_store'] = _fs
    import builtins as _bu
    _orig_open = _bu.open
    _m['_original_open'] = _orig_open
    import base64 as _b64m
    def _persist_file(path):
        try:
            with _orig_open(path, 'rb') as _ff:
                _c = _ff.read()
            _fs.insert(path, _b64m.b64encode(_c).decode('ascii'))
        except Exception:
            pass
    _m['_persist_file'] = _persist_file
    class _PersistentFile:
        __slots__ = ('_pf_file', '_pf_path', '_pf_done')
        def __init__(self, fo, p):
            self._pf_file = fo; self._pf_path = p; self._pf_done = False
        def _pf_persist(self):
            if not self._pf_done:
                self._pf_done = True; _persist_file(self._pf_path)
        def close(self):
            self._pf_file.close(); self._pf_persist()
        def __enter__(self): return self
        def __exit__(self, *a):
            self._pf_file.close(); self._pf_persist(); return False
        def __getattr__(self, n): return getattr(self._pf_file, n)
        def __iter__(self): return iter(self._pf_file)
    def _persistent_open(file, mode='r', *args, **kwargs):
        _f = _orig_open(file, mode, *args, **kwargs)
        if isinstance(file, (str, bytes)):
            _p = str(file)
            if any(c in mode for c in 'wxa+') and not any(_p.startswith(pfx) for pfx in _VOLATILE_PREFIXES):
                return _PersistentFile(_f, _p)
        return _f
    _bu.open = _persistent_open
    import os as _os
    _orig_remove = _os.remove
    _orig_rename = _os.rename
    _m['_original_os_remove'] = _orig_remove
    _m['_original_os_rename'] = _orig_rename
    def _p_remove(path, *a, **kw):
        _orig_remove(path, *a, **kw)
        _p = str(path)
        if _fs.contains_key(_p): _fs.remove(_p)
    def _p_rename(src, dst, *a, **kw):
        _orig_rename(src, dst, *a, **kw)
        _s, _d = str(src), str(dst)
        if _fs.contains_key(_s):
            _data = _fs.get(_s); _fs.remove(_s)
            if _data is not None: _fs.insert(_d, _data)
    _os.remove = _p_remove
    _os.unlink = _p_remove
    _os.rename = _p_rename
    def _restore():
        import os as _ros; import base64 as _rb64
        for _path, _b64 in _fs.items():
            try:
                _par = _ros.path.dirname(_path)
                if _par and _par != '/': _ros.makedirs(_par, exist_ok=True)
                with _orig_open(_path, 'wb') as _ff: _ff.write(_rb64.b64decode(_b64))
            except Exception: pass
    _m['_basilisk_restore_files_from_map'] = _restore
print('persistence_ready')
"""

# Helper to access the shim's _basilisk_file_store from shell namespace
_FS_STORE = "import sys; _fs = sys.modules['__main__'].__dict__['_basilisk_file_store']"
_ORIG_OPEN = "import sys; _orig_open = sys.modules['__main__'].__dict__['_original_open']"
_ORIG_REMOVE = "import sys; _orig_remove = sys.modules['__main__'].__dict__['_original_os_remove']"
_RESTORE_FN = "import sys; _restore = sys.modules['__main__'].__dict__['_basilisk_restore_files_from_map']"


@pytest.fixture(scope="session")
def persistence_injected(canister_reachable, canister, network):
    """Inject file persistence code into the canister if not already present."""
    result = exec_on_canister(_INJECT_PERSISTENCE, canister, network)
    if "persistence_ready" not in result:
        pytest.skip(f"Canister template lacks StableBTreeMap support: {result!r}")
    return True


@pytest.mark.usefixtures("persistence_injected")
class TestFilePersistenceMap:
    """Test that files are automatically persisted to StableBTreeMap on write."""

    def test_file_auto_persisted_on_write(self, canister_reachable, canister, network):
        """Writing a file should auto-persist its content to the file store map."""
        path = _unique("persist_auto")
        exec_on_canister(
            f"with open('{path}', 'w') as f: f.write('durable')",
            canister, network,
        )
        result = exec_on_canister(
            f"{_FS_STORE}\nprint(_fs.contains_key('{path}'))",
            canister, network,
        )
        assert result == "True"

    def test_file_content_correct_in_map(self, canister_reachable, canister, network):
        """The map should store the correct base64-encoded file content."""
        path = _unique("persist_content")
        exec_on_canister(
            f"with open('{path}', 'w') as f: f.write('test_content_123')",
            canister, network,
        )
        result = exec_on_canister(
            f"{_FS_STORE}\nimport base64\n"
            f"b64 = _fs.get('{path}')\n"
            f"print(base64.b64decode(b64).decode())",
            canister, network,
        )
        assert result == "test_content_123"

    def test_file_survives_simulated_upgrade(self, canister_reachable, canister, network):
        """File should survive: write → delete from memfs → restore from map."""
        path = _unique("persist_upgrade")
        content = f"upgrade_test_{uuid.uuid4().hex[:8]}"
        # Write file (auto-persists to map)
        exec_on_canister(
            f"with open('{path}', 'w') as f: f.write('{content}')",
            canister, network,
        )
        # Delete from memfs ONLY (bypass the patched os.remove)
        exec_on_canister(
            f"{_ORIG_REMOVE}\n_orig_remove('{path}')",
            canister, network,
        )
        # Verify file is gone from memfs
        result = exec_on_canister(
            f"import os; print(os.path.exists('{path}'))",
            canister, network,
        )
        assert result == "False"
        # Restore from map (simulates post_upgrade)
        exec_on_canister(
            f"{_RESTORE_FN}\n_restore()",
            canister, network,
        )
        # Verify file is back with correct content
        result = exec_on_canister(
            f"with open('{path}', 'r') as f: print(f.read())",
            canister, network,
        )
        assert result == content

    def test_file_delete_removes_from_map(self, canister_reachable, canister, network):
        """Deleting a file via os.remove should also remove it from the map."""
        path = _unique("persist_del")
        exec_on_canister(
            f"with open('{path}', 'w') as f: f.write('temporary')",
            canister, network,
        )
        exec_on_canister(f"import os; os.remove('{path}')", canister, network)
        result = exec_on_canister(
            f"{_FS_STORE}\nprint(_fs.contains_key('{path}'))",
            canister, network,
        )
        assert result == "False"

    def test_file_rename_updates_map(self, canister_reachable, canister, network):
        """Renaming a file should move the entry in the map."""
        old = _unique("persist_ren_old")
        new = _unique("persist_ren_new")
        exec_on_canister(
            f"with open('{old}', 'w') as f: f.write('renamed_data')",
            canister, network,
        )
        exec_on_canister(
            f"import os; os.rename('{old}', '{new}')",
            canister, network,
        )
        # Old key gone
        result = exec_on_canister(
            f"{_FS_STORE}\nprint(_fs.contains_key('{old}'))",
            canister, network,
        )
        assert result == "False"
        # New key present with correct content
        result = exec_on_canister(
            f"{_FS_STORE}\nimport base64\n"
            f"print(base64.b64decode(_fs.get('{new}')).decode())",
            canister, network,
        )
        assert result == "renamed_data"

    def test_volatile_files_not_persisted(self, canister_reachable, canister, network):
        """Files under /tmp/ should NOT be persisted to the map."""
        path = f"/tmp/volatile_{uuid.uuid4().hex[:8]}"
        exec_on_canister(
            f"with open('{path}', 'w') as f: f.write('volatile')",
            canister, network,
        )
        result = exec_on_canister(
            f"{_FS_STORE}\nprint(_fs.contains_key('{path}'))",
            canister, network,
        )
        assert result == "False"

    def test_binary_file_persisted(self, canister_reachable, canister, network):
        """Binary file content should be correctly persisted and restored."""
        path = _unique("persist_bin")
        import base64
        data = bytes(range(256))
        b64 = base64.b64encode(data).decode()
        exec_on_canister(
            f"import base64\n"
            f"with open('{path}', 'wb') as f:\n"
            f"    f.write(base64.b64decode('{b64}'))",
            canister, network,
        )
        # Delete from memfs, restore from map, verify content
        exec_on_canister(
            f"{_ORIG_REMOVE}\n_orig_remove('{path}')",
            canister, network,
        )
        exec_on_canister(
            f"{_RESTORE_FN}\n_restore()",
            canister, network,
        )
        result = exec_on_canister(
            f"with open('{path}', 'rb') as f: print(list(f.read()[:5]))",
            canister, network,
        )
        assert result == "[0, 1, 2, 3, 4]"

    def test_overwrite_updates_map(self, canister_reachable, canister, network):
        """Overwriting a file should update the map with new content."""
        path = _unique("persist_overwrite")
        exec_on_canister(
            f"with open('{path}', 'w') as f: f.write('first')",
            canister, network,
        )
        exec_on_canister(
            f"with open('{path}', 'w') as f: f.write('second')",
            canister, network,
        )
        result = exec_on_canister(
            f"{_FS_STORE}\nimport base64\n"
            f"print(base64.b64decode(_fs.get('{path}')).decode())",
            canister, network,
        )
        assert result == "second"

    def test_nested_dir_file_persisted_and_restored(self, canister_reachable, canister, network):
        """Files in nested dirs should persist and restore with correct paths."""
        base = _unique("persist_nested")
        deep = f"{base}/sub/dir"
        exec_on_canister(
            f"import os; os.makedirs('{deep}', exist_ok=True)",
            canister, network,
        )
        exec_on_canister(
            f"with open('{deep}/data.txt', 'w') as f: f.write('nested_ok')",
            canister, network,
        )
        # Delete from memfs, restore, verify
        exec_on_canister(
            f"{_ORIG_REMOVE}\n_orig_remove('{deep}/data.txt')",
            canister, network,
        )
        exec_on_canister(
            f"{_RESTORE_FN}\n_restore()",
            canister, network,
        )
        result = exec_on_canister(
            f"with open('{deep}/data.txt', 'r') as f: print(f.read())",
            canister, network,
        )
        assert result == "nested_ok"
