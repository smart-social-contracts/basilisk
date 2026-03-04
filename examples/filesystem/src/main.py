import os
import sys

# --- Runtime patches: the frozen_stdlib_preamble registers a fake os module
# that doesn't expose all posix C functions. Forward them manually. ---
try:
    import posix as _posix
    for _name in dir(_posix):
        if not _name.startswith('_') and not hasattr(os, _name):
            setattr(os, _name, getattr(_posix, _name))
except ImportError:
    pass

# Restore real builtins.open from _io C module
try:
    import _io
    import builtins
    builtins.open = _io.open
except Exception:
    pass

from basilisk import query, update, Vec


@update
def test_fs_diagnostics() -> Vec[str]:
    """Probe what's available - always passes, returns diagnostic info."""
    results = []
    results.append(f"python={sys.version}")
    results.append(f"has_mkdir={hasattr(os, 'mkdir')}")
    results.append(f"has_makedirs={hasattr(os, 'makedirs')}")
    results.append(f"has_listdir={hasattr(os, 'listdir')}")
    results.append(f"has_stat={hasattr(os, 'stat')}")
    results.append(f"has_remove={hasattr(os, 'remove')}")
    results.append(f"has_rename={hasattr(os, 'rename')}")
    results.append(f"has_path_exists={hasattr(os.path, 'exists')}")

    try:
        os.mkdir("/diag_test")
        results.append("mkdir=/diag_test OK")
    except Exception as e:
        results.append(f"mkdir=/diag_test ERR: {e}")

    try:
        entries = os.listdir("/")
        results.append(f"listdir=/: {entries}")
    except Exception as e:
        results.append(f"listdir=/ ERR: {e}")

    try:
        entries = os.listdir("/diag_test")
        results.append(f"listdir=/diag_test: {entries}")
    except Exception as e:
        results.append(f"listdir=/diag_test ERR: {e}")

    try:
        st = os.stat("/diag_test")
        results.append(f"stat=/diag_test: mode={st.st_mode}")
    except Exception as e:
        results.append(f"stat=/diag_test ERR: {e}")

    try:
        with open("/diag_test/file.txt", "w") as f:
            f.write("hello")
        results.append("write=/diag_test/file.txt OK")
    except Exception as e:
        results.append(f"write ERR: {e}")

    try:
        with open("/diag_test/file.txt", "r") as f:
            content = f.read()
        results.append(f"read=/diag_test/file.txt: '{content}'")
    except Exception as e:
        results.append(f"read ERR: {e}")

    try:
        exists = os.path.exists("/diag_test/file.txt")
        results.append(f"path.exists=/diag_test/file.txt: {exists}")
    except Exception as e:
        results.append(f"path.exists ERR: {e}")

    return results


@update
def test_fs_mkdir_and_listdir() -> Vec[str]:
    os.makedirs("/test_data/subdir", exist_ok=True)
    entries = sorted(os.listdir("/test_data"))
    return entries


@update
def test_fs_write_and_read() -> str:
    os.makedirs("/test_data", exist_ok=True)
    with open("/test_data/hello.txt", "w") as f:
        f.write("hello from ic-wasi-polyfill")
    with open("/test_data/hello.txt", "r") as f:
        return f.read()


@update
def test_fs_path_exists() -> Vec[str]:
    os.makedirs("/test_data", exist_ok=True)
    with open("/test_data/check.txt", "w") as f:
        f.write("exists")
    results = []
    results.append(str(os.path.exists("/test_data/check.txt")))
    results.append(str(os.path.exists("/test_data/nonexistent.txt")))
    results.append(str(os.path.isdir("/test_data")))
    results.append(str(os.path.isfile("/test_data/check.txt")))
    return results


@update
def test_fs_stat() -> Vec[str]:
    os.makedirs("/test_data", exist_ok=True)
    with open("/test_data/stat_test.txt", "w") as f:
        f.write("0123456789")
    st = os.stat("/test_data/stat_test.txt")
    results = []
    results.append(str(st.st_size))
    results.append(str(st.st_size == 10))
    return results


@update
def test_fs_remove_and_rename() -> Vec[str]:
    os.makedirs("/test_data", exist_ok=True)
    with open("/test_data/to_remove.txt", "w") as f:
        f.write("remove me")
    with open("/test_data/to_rename.txt", "w") as f:
        f.write("rename me")
    results = []
    os.remove("/test_data/to_remove.txt")
    results.append(str(os.path.exists("/test_data/to_remove.txt")))
    os.rename("/test_data/to_rename.txt", "/test_data/renamed.txt")
    results.append(str(os.path.exists("/test_data/to_rename.txt")))
    results.append(str(os.path.exists("/test_data/renamed.txt")))
    return results
