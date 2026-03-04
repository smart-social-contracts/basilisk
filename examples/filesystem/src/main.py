import os
import sys

from basilisk import query, update, Vec


@update
def test_fs_diagnostics() -> Vec[str]:
    """Probe filesystem capabilities - returns diagnostic info."""
    results = []
    results.append(f"python={sys.version}")
    results.append(f"has_mkdir={hasattr(os, 'mkdir')}")
    results.append(f"has_stat={hasattr(os, 'stat')}")
    results.append(f"has_listdir={hasattr(os, 'listdir')}")
    results.append(f"has_rename={hasattr(os, 'rename')}")
    results.append(f"has_rmdir={hasattr(os, 'rmdir')}")
    results.append(f"has_unlink={hasattr(os, 'unlink')}")
    results.append(f"has_path_exists={hasattr(os.path, 'exists')}")

    try:
        os.mkdir("/diag_test")
        results.append("mkdir OK")
    except Exception as e:
        results.append(f"mkdir ERR: {e}")

    try:
        st = os.stat("/diag_test")
        results.append(f"stat OK mode={st.st_mode}")
    except Exception as e:
        results.append(f"stat ERR: {e}")

    try:
        exists = os.path.exists("/diag_test")
        results.append(f"path.exists={exists}")
    except Exception as e:
        results.append(f"path.exists ERR: {e}")

    try:
        entries = os.listdir("/diag_test")
        results.append(f"listdir={entries}")
    except Exception as e:
        results.append(f"listdir ERR: {e}")

    try:
        os.rmdir("/diag_test")
        results.append("rmdir OK")
    except Exception as e:
        results.append(f"rmdir ERR: {e}")

    try:
        gone = not os.path.exists("/diag_test")
        results.append(f"after_rmdir_gone={gone}")
    except Exception as e:
        results.append(f"after_rmdir ERR: {e}")

    return results


@update
def test_fs_mkdir() -> Vec[str]:
    """Test os.mkdir and verify with os.stat."""
    results = []
    try:
        os.mkdir("/test_mkdir")
        results.append("mkdir=OK")
    except FileExistsError:
        results.append("mkdir=EXISTS")
    st = os.stat("/test_mkdir")
    import stat as stat_mod
    results.append(f"is_dir={stat_mod.S_ISDIR(st.st_mode)}")
    return results


@update
def test_fs_path_exists() -> Vec[str]:
    """Test os.path.exists, isdir, isfile via os.stat."""
    results = []
    try:
        os.mkdir("/test_exists")
    except FileExistsError:
        pass
    results.append(str(os.path.exists("/test_exists")))
    results.append(str(os.path.exists("/nonexistent_path")))
    results.append(str(os.path.isdir("/test_exists")))
    return results


@update
def test_fs_rename() -> Vec[str]:
    """Test os.rename and verify with os.stat."""
    results = []
    try:
        os.mkdir("/test_rename_src")
    except FileExistsError:
        pass
    os.rename("/test_rename_src", "/test_rename_dst")
    results.append(str(os.path.exists("/test_rename_src")))
    results.append(str(os.path.exists("/test_rename_dst")))
    return results


@update
def test_fs_rmdir() -> Vec[str]:
    """Test os.rmdir and verify removal with os.stat."""
    results = []
    try:
        os.mkdir("/test_rmdir")
    except FileExistsError:
        pass
    results.append(str(os.path.exists("/test_rmdir")))
    os.rmdir("/test_rmdir")
    results.append(str(os.path.exists("/test_rmdir")))
    return results


@update
def test_fs_nested_mkdir() -> Vec[str]:
    """Test os.makedirs for nested directories."""
    results = []
    os.makedirs("/test_nested/a/b/c", exist_ok=True)
    results.append(str(os.path.exists("/test_nested")))
    results.append(str(os.path.exists("/test_nested/a")))
    results.append(str(os.path.exists("/test_nested/a/b")))
    results.append(str(os.path.exists("/test_nested/a/b/c")))
    results.append(str(os.path.isdir("/test_nested/a/b/c")))
    return results
