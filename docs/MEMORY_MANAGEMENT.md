# Memory Management in Basilisk

This document explains how basilisk manages persistent data on the Internet Computer using stable memory. It covers the MemoryManager architecture, the six stable data structures exposed to Python, the tagged binary serialization layer, and the automatic file persistence system.

## Overview

Basilisk canisters run CPython inside a WebAssembly module on the IC. Heap memory (regular Python objects) is **volatile** — it is lost on every canister upgrade. **Stable memory** is the IC's mechanism for data that must survive upgrades.

Rather than serializing the entire Python heap into stable memory (which is fragile and hits the IC's 3 MB reply limit), basilisk uses DFINITY's [`ic-stable-structures`](https://github.com/dfinity/stable-structures) crate (v0.6.x) to provide purpose-built data structures that read and write directly to stable memory. From the Python developer's perspective, these structures behave like ordinary collections — but their contents automatically persist across upgrades with zero boilerplate.

## MemoryManager

### What it does

The `MemoryManager` partitions the canister's single contiguous stable memory region into up to **255 virtual memories** (VMs), each identified by a `memory_id` (0–254). Each VM acts as an independent address space that can back one stable structure instance.

### How it works

On canister initialization, basilisk creates a single global `MemoryManager`:

```rust
// stable_structures.rs
thread_local! {
    static MEMORY_MANAGER: RefCell<MemoryManager<DefaultMemoryImpl>> =
        RefCell::new(MemoryManager::init(DefaultMemoryImpl::default()));
}
```

When a Python program creates a stable structure, e.g. `StableBTreeMap[str, str](memory_id=5)`, the Rust layer calls `MemoryManager::get(MemoryId::new(5))` to obtain a `VirtualMemory` handle. This handle is then passed to the structure's `init()` constructor.

The MemoryManager maintains its own **bookkeeping region** at the start of stable memory. This region tracks which "buckets" (groups of Wasm pages) belong to which virtual memory. On first init, the MemoryManager pre-allocates approximately 129 pages (~8.4 MB) of stable memory for its internal metadata. This is why `ic.stable_size()` returns a non-zero value even before any user data is stored.

### Virtual memory allocation

Each virtual memory grows on demand. When a structure needs more space, the MemoryManager allocates additional buckets (each bucket is 128 Wasm pages = 8 MB) from the underlying stable memory and maps them to the requesting VM. Buckets belonging to different VMs can be interleaved in physical stable memory — the MemoryManager handles the mapping transparently.

### Reserved memory IDs

| Memory ID | Purpose |
|-----------|---------|
| 0–253     | Available for user-defined stable structures |
| 254       | **File persistence store** (internal `StableBTreeMap`) |

Memory ID 254 is reserved by basilisk's file persistence layer (see [File Persistence](#file-persistence) below). User code should avoid using this ID.

## Architecture

The stable structures system has three layers:

```
┌─────────────────────────────────────────────────┐
│  Python layer  (python_init.rs shim)            │
│  StableBTreeMap, StableBTreeSet, StableVec, ... │
│  Tagged binary serialization / deserialization  │
├─────────────────────────────────────────────────┤
│  C FFI bridge  (ic_api.rs)                      │
│  smap_init, smap_insert, svec_push, ...         │
│  32 exported functions, PyMethodDef table        │
├─────────────────────────────────────────────────┤
│  Rust layer  (stable_structures.rs)             │
│  ic-stable-structures 0.6.x                     │
│  MemoryManager + per-type registries            │
│  SBytes wrapper (Storable, Bounded, max 2 MB)   │
├─────────────────────────────────────────────────┤
│  IC Stable Memory  (canister-level, survives    │
│  upgrades)                                      │
└─────────────────────────────────────────────────┘
```

### Rust layer (`stable_structures.rs`)

This module owns all Rust-side state as `thread_local!` registries:

```rust
static MAPS:  RefCell<HashMap<u8, StableBTreeMap<SBytes, SBytes, VM>>>
static SETS:  RefCell<HashMap<u8, StableBTreeMap<SBytes, SBytes, VM>>>  // emulated
static VECS:  RefCell<HashMap<u8, StableVec<SBytes, VM>>>
static LOGS:  RefCell<HashMap<u8, StableLog<SBytes, VM, VM>>>
static CELLS: RefCell<HashMap<u8, StableCell<SBytes, VM>>>
static HEAPS: RefCell<HashMap<u8, StableMinHeap<SBytes, VM>>>
```

Each registry is a `HashMap<u8, Structure>` keyed by `memory_id`. When Python calls `StableBTreeMap(memory_id=5)`, the Rust function `smap_init(5)` checks if memory_id 5 is already in the `MAPS` registry. If not, it obtains a virtual memory and initializes a new `StableBTreeMap` with it.

#### SBytes — the Storable wrapper

All keys and values are stored as opaque byte blobs using the `SBytes` wrapper:

```rust
pub struct SBytes(pub Vec<u8>);

impl Storable for SBytes {
    const BOUND: Bound = Bound::Bounded {
        max_size: 2_000_000,  // 2 MB per key or value
        is_fixed_size: false,
    };
    // ...
}
```

The `Bounded` trait is required by `StableVec`, `StableLog`, `StableCell`, and `StableMinHeap` in `ic-stable-structures` 0.6.x. Only `StableBTreeMap` supports unbounded types, but a uniform bounded type (2 MB max) is used across all structures for simplicity.

### C FFI bridge (`ic_api.rs`)

The Rust functions are exposed to CPython as a native extension module (`_basilisk_ic`) via the Python C API. Each function is registered in a `PyMethodDef` table:

```rust
add_method!("smap_init",   ic_smap_init,   ffi::METH_O);
add_method!("smap_insert", ic_smap_insert, ffi::METH_VARARGS);
// ... 32 methods total for stable structures
```

These bridge functions handle:
- Extracting Python arguments (integers, byte strings) from `*mut PyObject`
- Calling the corresponding `stable_structures.rs` function
- Converting Rust return values (`Option<Vec<u8>>`, `bool`, `u64`) back to Python objects

### Python layer (`python_init.rs` shim)

The Python shim provides ergonomic classes that handle tagged binary serialization and delegate to the Rust layer. Type hints from the generic parameters (e.g. `nat8`, `int32`) are captured and forwarded to the encoder:

```python
class StableBTreeMap(metaclass=_StableBTreeMapMeta):
    def __init__(self, memory_id=0, ..., _key_type=None, _val_type=None):
        self._memory_id = memory_id
        self._kt = _type_hint_for(_key_type)  # e.g. nat8
        self._vt = _type_hint_for(_val_type)  # e.g. int32
        _basilisk_ic.smap_init(memory_id)

    def get(self, key):
        return _decode_val(_basilisk_ic.smap_get(self._memory_id, _encode(key, self._kt)))

    def insert(self, key, value):
        prev = _basilisk_ic.smap_insert(self._memory_id, _encode(key, self._kt), _encode(value, self._vt))
        return _decode_val(prev)
    # ...
```

## Serialization

### Tagged binary encoding

Python objects are serialized to a compact tagged binary format before being stored. Each encoded value begins with a **1-byte type tag** followed by the payload. All integers use **big-endian** byte order, which preserves correct numeric ordering at the byte level.

#### Tag table

| Tag | Type | Payload |
|------|-----------|------------------------------------------|
| 0x00 | `None` | (empty) |
| 0x01 | `bool` | 1 byte (0x00 = False, 0x01 = True) |
| 0x02 | `int` (default int64) | 8 bytes big-endian signed |
| 0x03 | `float` (default float64) | 8 bytes IEEE 754 |
| 0x04 | `str` | 4-byte length + UTF-8 bytes |
| 0x05 | `bytes` | 4-byte length + raw bytes |
| 0x06 | `Principal` | 4-byte length + text representation |
| 0x07 | `list` | 4-byte count + tagged items (recursive) |
| 0x08 | `dict` | 4-byte count + tagged (key, value) pairs |
| 0x09 | `tuple` | 4-byte count + tagged items (recursive) |
| 0x10 | `nat8` | 1 byte unsigned |
| 0x11 | `nat16` | 2 bytes big-endian unsigned |
| 0x12 | `nat32` | 4 bytes big-endian unsigned |
| 0x13 | `nat64` | 8 bytes big-endian unsigned |
| 0x14 | `int8` | 1 byte signed |
| 0x15 | `int16` | 2 bytes big-endian signed |
| 0x16 | `int32` | 4 bytes big-endian signed |
| 0x17 | `float32` | 4 bytes IEEE 754 |

#### Default inference vs explicit type hints

When no type hint is provided, the encoder infers the tag from the Python value's type: `int` → int64 (0x02), `float` → float64 (0x03), `str` → text (0x04), etc.

Explicit type hints are passed via generic parameters on the stable structure:

```python
from basilisk import StableBTreeMap, nat8, int32

# Default: keys encoded as int64 (8 bytes), values as int64 (8 bytes)
default_map = StableBTreeMap[int, int](memory_id=0)

# Explicit: keys encoded as nat8 (1 byte), values as int32 (4 bytes)
compact_map = StableBTreeMap[nat8, int32](memory_id=1)
```

Available type hints: `nat8`, `nat16`, `nat32`, `nat64`, `int8`, `int16`, `int32`, `float32`.

#### Ordering correctness

Because all integers use big-endian encoding, they sort **numerically** at the byte level. This means `StableBTreeMap` keys and `StableMinHeap` values maintain correct ordering — unlike text-based encodings where `"9" > "10"` lexicographically.

### Encoding and decoding

```python
def _encode(value, type_hint=None):
    """Encode a Python value to tagged binary bytes."""
    # If explicit type hint, use its tag and format
    # Otherwise, infer from the Python type
    ...

def _decode_val(raw):
    """Decode a complete tagged binary blob."""
    if raw is None:
        return None
    val, _ = _decode(raw)
    return val
```

Every key and value passes through `_encode()` → bytes before entering Rust, and raw bytes → `_decode_val()` on the way back.

## Stable Data Structures

### StableBTreeMap

A sorted key-value map backed by a B-tree stored entirely in stable memory.

```python
from basilisk import StableBTreeMap

db = StableBTreeMap[str, str](memory_id=0)
db.insert("alice", "wonderland")
db.get("alice")           # → "wonderland"
db.contains_key("alice")  # → True
db.remove("alice")        # → "wonderland"
db.keys()                 # → ["alice"]
db.values()               # → ["wonderland"]
db.items()                # → [("alice", "wonderland")]
db.len()                  # → 1
db.is_empty()             # → True/False
```

**Rust backing**: `ic_stable_structures::BTreeMap<SBytes, SBytes, VM>` — supports unbounded keys/values, uses a single virtual memory.

### StableBTreeSet

A sorted set of unique elements. Since `ic-stable-structures` 0.6.x does not include a `BTreeSet` type, this is **emulated** using a `BTreeMap` with empty values.

```python
from basilisk import StableBTreeSet

colors = StableBTreeSet(memory_id=10)
colors.insert("red")      # → True (new)
colors.insert("red")      # → False (already existed)
colors.contains("red")    # → True
colors.remove("red")      # → True (was present)
colors.items()             # → ["blue", "green"]
colors.len()               # → 2
colors.is_empty()          # → True/False
```

**Rust backing**: `ic_stable_structures::BTreeMap<SBytes, SBytes, VM>` with `SBytes(Vec::new())` as the value for every entry.

### StableVec

A growable array (like Python's `list`) with index-based access.

```python
from basilisk import StableVec

log = StableVec(memory_id=20)
log.push("first")
log.push("second")
log.get(0)             # → "first"
log.set(0, "updated")  # replace at index
log.pop()              # → "second"
log.len()              # → 1
log.is_empty()         # → True/False
```

**Rust backing**: `ic_stable_structures::Vec<SBytes, VM>` — requires `Bound::Bounded`.

### StableLog

An **append-only** sequence. Entries can be read by index but never modified or removed. The log uses **two** virtual memories — one for the index and one for the data — which is why it takes two `memory_id` parameters.

```python
from basilisk import StableLog

audit = StableLog(memory_id_index=30, memory_id_data=31)
audit.append("user logged in")   # → 0 (index of new entry)
audit.append("file uploaded")    # → 1
audit.get(0)                     # → "user logged in"
audit.len()                      # → 2
audit.is_empty()                 # → True/False
```

**Rust backing**: `ic_stable_structures::Log<SBytes, VM, VM>` — the index VM stores entry offsets, the data VM stores entry payloads.

### StableCell

A single persistent value — the simplest stable structure. Useful for configuration, counters, or any singleton state.

```python
from basilisk import StableCell

config = StableCell(memory_id=40, default_value="initial")
config.get()            # → "initial"
config.set("updated")
config.get()            # → "updated"
```

**Rust backing**: `ic_stable_structures::Cell<SBytes, VM>` — stores exactly one `SBytes` value. The `default_value` is used only when the cell is first created (on a fresh canister); after an upgrade, the previously stored value is returned.

### StableMinHeap

A min-heap (priority queue) where `pop()` always returns the smallest element. Ordering is based on the byte-level comparison of the binary-encoded values.

```python
from basilisk import StableMinHeap

pq = StableMinHeap(memory_id=50)
pq.push("cherry")
pq.push("apple")
pq.push("banana")
pq.peek()    # → "apple" (smallest lexicographically)
pq.pop()     # → "apple"
pq.pop()     # → "banana"
pq.pop()     # → "cherry"
pq.len()     # → 0
pq.is_empty() # → True
```

**Rust backing**: `ic_stable_structures::MinHeap<SBytes, VM>` — ordering is by `SBytes`'s `Ord` implementation, which compares the raw bytes lexicographically.

**Numeric ordering works correctly**: Because integers are encoded in big-endian binary, `9` sorts before `10` as expected. This is a key advantage of the tagged binary encoding over the previous JSON-based approach.

## Memory ID Assignment

Each stable structure instance must have a **unique** `memory_id`. Two structures sharing the same memory ID will corrupt each other's data. The `StableLog` requires **two** unique IDs (one for the index, one for the data).

Example assignment scheme:

```python
# Good — each structure gets its own memory_id
users    = StableBTreeMap[str, str](memory_id=0)
sessions = StableBTreeMap[str, str](memory_id=1)
tags     = StableBTreeSet(memory_id=2)
events   = StableLog(memory_id_index=3, memory_id_data=4)
counter  = StableCell(memory_id=5, default_value=0)
queue    = StableMinHeap(memory_id=6)

# Bad — these two maps share memory_id=0 and will corrupt each other!
map_a = StableBTreeMap[str, str](memory_id=0)
map_b = StableBTreeMap[str, str](memory_id=0)
```

## File Persistence

### How it works

Basilisk provides **automatic file persistence** — files written to the canister's in-memory filesystem (memfs) are transparently backed up to stable memory and restored after upgrades. No user code is needed.

The system uses a dedicated `StableBTreeMap` at **memory_id 254** as a key-value store where:
- **Key**: the file path (UTF-8 bytes)
- **Value**: the raw file content (bytes)

### Write path

When Python code writes a file using `open()`, basilisk's monkey-patched `open()` function wraps the returned file object in a `_PersistentFile`. When the file is closed (either explicitly or via a context manager), the wrapper:

1. Closes the underlying file object (writing to memfs)
2. Re-reads the file content from memfs
3. Stores it in the file store at memory_id 254 via `smap_insert`

```
Python: open("data.json", "w") → write → close
                                           ↓
                                   _PersistentFile.close()
                                           ↓
                                   _persist_file("data.json")
                                           ↓
                                   smap_insert(254, b"data.json", <raw bytes>)
                                           ↓
                                   Stable Memory (VM 254)
```

### Volatile prefixes

Files under these prefixes are **not** persisted (they are considered temporary):
- `/tmp/`
- `/proc/`
- `/dev/`

### File operations

The following operations are patched to keep the file store in sync:

| Operation | Behavior |
|-----------|----------|
| `open(path, "w"/"a"/"x"/"+")` | Content persisted to stable memory on `close()` |
| `open(path, "r")` | No persistence (read-only) |
| `os.remove(path)` / `os.unlink(path)` | Entry removed from file store |
| `os.rename(src, dst)` | Old entry removed, new entry created |

### Restore path (post-upgrade)

On canister upgrade, the `post_upgrade` hook calls `_basilisk_load_files()` which:

1. Iterates all entries in the file store (`smap_items(254)`)
2. For each entry, creates parent directories with `os.makedirs`
3. Writes the file content back to memfs using the original (un-patched) `open()`

```
post_upgrade
    ↓
_basilisk_load_files()
    ↓
for (path_bytes, content) in smap_items(254):
    path = path_bytes.decode('utf-8')
    os.makedirs(dirname(path), exist_ok=True)
    open(path, 'wb').write(content)
```

After this, all files are available on the memfs exactly as they were before the upgrade.

## `stable_bytes()` and Raw Stable Memory

The `ic.stable_bytes()` function is **disabled** when the MemoryManager is active. Calling it will trap with:

```
ic.stable_bytes() is not available: the MemoryManager owns stable memory.
Use StableBTreeMap/StableVec/etc. for persistent storage, or
ic.stable_read(offset, length) for raw access to specific regions.
```

This is because `stable_bytes()` attempts to read *all* of stable memory into a single response, but the MemoryManager pre-allocates metadata pages that push the total well beyond the IC's 3 MB reply limit.

Low-level functions `ic.stable_read(offset, length)` and `ic.stable_write(offset, data)` still work for reading/writing specific byte ranges, but using them alongside the MemoryManager requires understanding the internal layout and is generally not recommended.

## Upgrade Lifecycle

The complete upgrade flow:

1. **Pre-upgrade**: Nothing to do. All stable structures already live in stable memory.
2. **IC performs upgrade**: Heap memory is wiped. Stable memory is preserved.
3. **Post-upgrade / init**: 
   - MemoryManager re-initializes from its existing bookkeeping in stable memory
   - Python code re-creates structure handles (e.g., `StableBTreeMap(memory_id=0)`) — these reconnect to existing data
   - `_basilisk_load_files()` restores files from the file store to memfs

No serialization or deserialization step is needed. The structures are always "live" in stable memory.

## Limits and Constraints

| Constraint | Value |
|-----------|-------|
| Max virtual memories | 255 (memory_id 0–254) |
| Max key/value size | 2 MB (SBytes bounded limit) |
| Bucket size | 128 Wasm pages (8 MB) |
| MemoryManager metadata overhead | ~129 pages (~8.4 MB) on init |
| Max stable memory (IC limit) | 96 GB per canister |
| IC reply size limit | 3 MB (affects `stable_bytes()`) |
| Reserved memory IDs | 254 (file store) |
