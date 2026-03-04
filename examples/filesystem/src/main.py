import os

from basilisk import query, update, Vec


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
