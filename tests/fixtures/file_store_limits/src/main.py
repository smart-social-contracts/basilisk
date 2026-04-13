import os

from basilisk import (
    update, nat64,
    FileStoreError, FileTooLargeError, FileStoreLimitError,
)


@update
def get_fs_stats() -> str:
    """Return file store stats as pipe-delimited string.

    Format: files|max_files|total_bytes|max_total_bytes|max_file_bytes|largest_bytes|largest_path
    """
    try:
        from basilisk import fs_stats
        s = fs_stats()
        if s is None:
            return "ERROR:fs_stats returned None"
        return '|'.join([
            str(s['files']),
            str(s['max_files']),
            str(s['total_bytes']),
            str(s['max_total_bytes']),
            str(s['max_file_bytes']),
            str(s['largest_bytes']),
            s.get('largest_path', ''),
        ])
    except Exception as e:
        return f"ERROR:{type(e).__name__}:{e}"


@update
def write_file(path: str, size: nat64) -> str:
    """Write a file of the given size (bytes of 'A'). Returns 'ok' or error."""
    try:
        with open(path, 'wb') as f:
            f.write(b'A' * size)
        return "ok"
    except FileTooLargeError as e:
        return f"FileTooLargeError:{e}"
    except FileStoreLimitError as e:
        return f"FileStoreLimitError:{e}"
    except Exception as e:
        return f"Error:{type(e).__name__}:{e}"


@update
def write_file_text(path: str, content: str) -> str:
    """Write text content to a file. Returns 'ok' or error."""
    try:
        with open(path, 'w') as f:
            f.write(content)
        return "ok"
    except FileTooLargeError as e:
        return f"FileTooLargeError:{e}"
    except FileStoreLimitError as e:
        return f"FileStoreLimitError:{e}"
    except Exception as e:
        return f"Error:{type(e).__name__}:{e}"


@update
def delete_file(path: str) -> str:
    """Delete a file. Returns 'ok' or error."""
    try:
        os.remove(path)
        return "ok"
    except Exception as e:
        return f"Error:{type(e).__name__}:{e}"


@update
def write_many_files(prefix: str, count: nat64, size: nat64) -> str:
    """Write `count` files of `size` bytes each. Returns 'ok:N' or error at file N."""
    for i in range(count):
        path = f"{prefix}_{i:04d}.dat"
        try:
            with open(path, 'wb') as f:
                f.write(b'B' * size)
        except (FileTooLargeError, FileStoreLimitError) as e:
            return f"{type(e).__name__}:{i}:{e}"
        except Exception as e:
            return f"Error:{i}:{type(e).__name__}:{e}"
    return f"ok:{count}"


@update
def delete_many_files(prefix: str, count: nat64) -> str:
    """Delete `count` files. Returns 'ok:N' with count deleted."""
    deleted = 0
    for i in range(count):
        path = f"{prefix}_{i:04d}.dat"
        try:
            os.remove(path)
            deleted += 1
        except FileNotFoundError:
            pass
    return f"ok:{deleted}"


@update
def read_file_check(path: str) -> str:
    """Read a file and return its size, or error."""
    try:
        with open(path, 'rb') as f:
            data = f.read()
        return f"ok:{len(data)}"
    except Exception as e:
        return f"Error:{type(e).__name__}:{e}"


@update
def cleanup_all_files() -> str:
    """Remove all files from the persistent store by iterating and deleting."""
    import _basilisk_ic
    _mem_id = 254
    keys = [k for k, v in _basilisk_ic.smap_items(_mem_id)]
    for k in keys:
        _basilisk_ic.smap_remove(_mem_id, k)
        path = k.decode('utf-8')
        try:
            os.remove(path)
        except Exception:
            pass
    return f"ok:{len(keys)}"
