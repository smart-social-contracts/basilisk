import base64
import collections
import datetime
import enum
import itertools
import json
import os
import random
import string
import struct
import time
import urllib.parse
import uuid
import weakref

from basilisk import blob, float64, ic, query, update, Vec

@query
def test_base64() -> blob:
    return base64.b64encode(b'Hello there sir')

@query
def test_collections() -> str:
    counter = collections.Counter(["apple", "banana", "orange", "apple", "banana", "apple"])
    return counter.most_common(1)[0][0]

@query
def test_datetime() -> str:
    return str(datetime.datetime.now())

@query
def test_time_is_the_ic_time() -> str:
    # time.time(), datetime.now() and ic.time(), all in seconds (#73)
    return "|".join(str(t) for t in (time.time(), datetime.datetime.now().timestamp(), ic.time() / 1e9))

@query
def test_datetime_values() -> str:
    a = datetime.datetime.fromtimestamp(1_800_000_000)
    b = datetime.datetime.fromtimestamp(1_700_000_000)
    parsed = datetime.datetime.strptime("2027-01-15 08:00:00.123", "%Y-%m-%d %H:%M:%S.%f")
    return "|".join([a.strftime("%Y-%m-%d %H:%M:%S"), str(a - b), str(a.timestamp()), parsed.isoformat()])

@query
def test_sleep_refuses() -> str:
    try:
        time.sleep(1)
    except NotImplementedError:
        return "refused"
    return "returned"

@query
def test_enum_members() -> str:
    class Color(enum.Enum):
        RED = enum.auto()
        BLUE = enum.auto()
    return "|".join([type(Color.RED).__name__, repr(Color.BLUE), ",".join(m.name for m in Color),
                     str(Color(2) is Color.BLUE)])

@query
def test_weakref_frees() -> str:
    class Thing:
        pass
    thing = Thing()
    ref = weakref.ref(thing)
    cache = weakref.WeakValueDictionary(a=thing)
    del thing
    return f"{ref() is None}|{len(cache)}"

@query
def test_struct_pack() -> str:
    return f"{struct.pack('<IH', 1, 2).hex()}|{struct.unpack('<IH', bytes.fromhex('010000000200'))}"

@query
def test_itertools() -> Vec[str]:
    perms = itertools.permutations("abcd", 2)
    result = ["".join(p) for p in perms]
    return result

@query
def test_json() -> str:
    return json.dumps({
        "hello": "world"
    })

@update
def test_random() -> float64:
    return random.random()

@query
def test_string() -> str:
    return string.ascii_letters

@query
def test_urllib() -> str:
    return urllib.parse.unquote("https%3A%2F%2Fwww.example.com%2Fsearch%3Fquery%3Dtest%26page%3D1")

@update
def test_uuid() -> str:
    return str(uuid.uuid4())

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