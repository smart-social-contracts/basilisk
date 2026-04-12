//! Rust-backed stable structures exposed to Python.
//!
//! Uses `ic-stable-structures` MemoryManager to partition stable memory into
//! up to 255 virtual memories, each backing one stable structure instance.
//! Python picks a `memory_id` (0..254) when creating a structure.
//!
//! All keys and values are opaque `Vec<u8>` — Python handles JSON serialization.

use ic_stable_structures::{
    memory_manager::{MemoryId, MemoryManager, VirtualMemory},
    BTreeMap as StableBTreeMap,
    Cell as StableCell,
    DefaultMemoryImpl,
    Log as StableLog,
    MinHeap as StableMinHeap,
    Vec as StableVec,
    Storable,
    storable::Bound,
};
use std::borrow::Cow;
use std::cell::RefCell;
use std::collections::HashMap;

// ---------------------------------------------------------------------------
// Memory
// ---------------------------------------------------------------------------

type VM = VirtualMemory<DefaultMemoryImpl>;

thread_local! {
    static MEMORY_MANAGER: RefCell<MemoryManager<DefaultMemoryImpl>> =
        RefCell::new(MemoryManager::init(DefaultMemoryImpl::default()));

    // Registries — one per structure kind
    static MAPS:    RefCell<HashMap<u8, StableBTreeMap<SBytes, SBytes, VM>>> = RefCell::new(HashMap::new());
    // BTreeSet is emulated via BTreeMap<SBytes, SBytes, VM> with empty values
    static SETS:    RefCell<HashMap<u8, StableBTreeMap<SBytes, SBytes, VM>>>  = RefCell::new(HashMap::new());
    static VECS:    RefCell<HashMap<u8, StableVec<SBytes, VM>>>              = RefCell::new(HashMap::new());
    static LOGS:    RefCell<HashMap<u8, StableLog<SBytes, VM, VM>>>           = RefCell::new(HashMap::new());
    static CELLS:   RefCell<HashMap<u8, StableCell<SBytes, VM>>>             = RefCell::new(HashMap::new());
    static HEAPS:   RefCell<HashMap<u8, StableMinHeap<SBytes, VM>>>          = RefCell::new(HashMap::new());
}

fn get_vm(id: u8) -> VM {
    MEMORY_MANAGER.with(|mm| mm.borrow().get(MemoryId::new(id)))
}

// ---------------------------------------------------------------------------
// Storable wrapper for arbitrary bytes
// ---------------------------------------------------------------------------

/// Wrapper around `Vec<u8>` that implements `Storable` with variable-length
/// encoding (max 10 MB per value — generous upper bound).
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct SBytes(pub Vec<u8>);

impl Storable for SBytes {
    fn to_bytes(&self) -> Cow<[u8]> {
        Cow::Borrowed(&self.0)
    }
    fn from_bytes(bytes: Cow<[u8]>) -> Self {
        SBytes(bytes.to_vec())
    }
    const BOUND: Bound = Bound::Bounded {
        max_size: 2_000_000,
        is_fixed_size: false,
    };
}

// ---------------------------------------------------------------------------
// BTreeMap
// ---------------------------------------------------------------------------

pub fn smap_init(id: u8) {
    MAPS.with(|maps| {
        let mut maps = maps.borrow_mut();
        if !maps.contains_key(&id) {
            let vm = get_vm(id);
            maps.insert(id, StableBTreeMap::init(vm));
        }
    });
}

pub fn smap_insert(id: u8, key: Vec<u8>, value: Vec<u8>) -> Option<Vec<u8>> {
    MAPS.with(|maps| {
        let mut maps = maps.borrow_mut();
        let map = maps.get_mut(&id).expect("smap not initialized");
        map.insert(SBytes(key), SBytes(value)).map(|v| v.0)
    })
}

pub fn smap_get(id: u8, key: &[u8]) -> Option<Vec<u8>> {
    MAPS.with(|maps| {
        let maps = maps.borrow();
        let map = maps.get(&id).expect("smap not initialized");
        map.get(&SBytes(key.to_vec())).map(|v| v.0)
    })
}

pub fn smap_remove(id: u8, key: &[u8]) -> Option<Vec<u8>> {
    MAPS.with(|maps| {
        let mut maps = maps.borrow_mut();
        let map = maps.get_mut(&id).expect("smap not initialized");
        map.remove(&SBytes(key.to_vec())).map(|v| v.0)
    })
}

pub fn smap_contains_key(id: u8, key: &[u8]) -> bool {
    MAPS.with(|maps| {
        let maps = maps.borrow();
        let map = maps.get(&id).expect("smap not initialized");
        map.contains_key(&SBytes(key.to_vec()))
    })
}

pub fn smap_len(id: u8) -> u64 {
    MAPS.with(|maps| {
        let maps = maps.borrow();
        let map = maps.get(&id).expect("smap not initialized");
        map.len()
    })
}

/// Returns all keys as a Vec of byte vectors.
pub fn smap_keys(id: u8) -> Vec<Vec<u8>> {
    MAPS.with(|maps| {
        let maps = maps.borrow();
        let map = maps.get(&id).expect("smap not initialized");
        map.iter().map(|(k, _v)| k.0).collect()
    })
}

/// Returns all (key, value) pairs.
pub fn smap_items(id: u8) -> Vec<(Vec<u8>, Vec<u8>)> {
    MAPS.with(|maps| {
        let maps = maps.borrow();
        let map = maps.get(&id).expect("smap not initialized");
        map.iter().map(|(k, v)| (k.0, v.0)).collect()
    })
}

// ---------------------------------------------------------------------------
// BTreeSet
// ---------------------------------------------------------------------------

// BTreeSet emulated via BTreeMap with empty values (BTreeSet not in 0.6.x)

pub fn sset_init(id: u8) {
    SETS.with(|sets| {
        let mut sets = sets.borrow_mut();
        if !sets.contains_key(&id) {
            let vm = get_vm(id);
            sets.insert(id, StableBTreeMap::init(vm));
        }
    });
}

pub fn sset_insert(id: u8, key: Vec<u8>) -> bool {
    SETS.with(|sets| {
        let mut sets = sets.borrow_mut();
        let set = sets.get_mut(&id).expect("sset not initialized");
        set.insert(SBytes(key), SBytes(Vec::new())).is_none()
    })
}

pub fn sset_remove(id: u8, key: &[u8]) -> bool {
    SETS.with(|sets| {
        let mut sets = sets.borrow_mut();
        let set = sets.get_mut(&id).expect("sset not initialized");
        set.remove(&SBytes(key.to_vec())).is_some()
    })
}

pub fn sset_contains(id: u8, key: &[u8]) -> bool {
    SETS.with(|sets| {
        let sets = sets.borrow();
        let set = sets.get(&id).expect("sset not initialized");
        set.contains_key(&SBytes(key.to_vec()))
    })
}

pub fn sset_len(id: u8) -> u64 {
    SETS.with(|sets| {
        let sets = sets.borrow();
        let set = sets.get(&id).expect("sset not initialized");
        set.len()
    })
}

pub fn sset_items(id: u8) -> Vec<Vec<u8>> {
    SETS.with(|sets| {
        let sets = sets.borrow();
        let set = sets.get(&id).expect("sset not initialized");
        set.iter().map(|(k, _v)| k.0).collect()
    })
}

// ---------------------------------------------------------------------------
// Vec
// ---------------------------------------------------------------------------

pub fn svec_init(id: u8) {
    VECS.with(|vecs| {
        let mut vecs = vecs.borrow_mut();
        if !vecs.contains_key(&id) {
            let vm = get_vm(id);
            vecs.insert(id, StableVec::init(vm).expect("svec init failed"));
        }
    });
}

pub fn svec_get(id: u8, index: u64) -> Option<Vec<u8>> {
    VECS.with(|vecs| {
        let vecs = vecs.borrow();
        let v = vecs.get(&id).expect("svec not initialized");
        v.get(index).map(|sb| sb.0)
    })
}

pub fn svec_push(id: u8, value: Vec<u8>) {
    VECS.with(|vecs| {
        let mut vecs = vecs.borrow_mut();
        let v = vecs.get_mut(&id).expect("svec not initialized");
        v.push(&SBytes(value)).expect("svec push failed");
    });
}

pub fn svec_pop(id: u8) -> Option<Vec<u8>> {
    VECS.with(|vecs| {
        let mut vecs = vecs.borrow_mut();
        let v = vecs.get_mut(&id).expect("svec not initialized");
        v.pop().map(|sb| sb.0)
    })
}

pub fn svec_set(id: u8, index: u64, value: Vec<u8>) {
    VECS.with(|vecs| {
        let mut vecs = vecs.borrow_mut();
        let v = vecs.get_mut(&id).expect("svec not initialized");
        v.set(index, &SBytes(value));
    });
}

pub fn svec_len(id: u8) -> u64 {
    VECS.with(|vecs| {
        let vecs = vecs.borrow();
        let v = vecs.get(&id).expect("svec not initialized");
        v.len()
    })
}

// ---------------------------------------------------------------------------
// Log (append-only)
// ---------------------------------------------------------------------------

pub fn slog_init(id_index: u8, id_data: u8) {
    LOGS.with(|logs| {
        let mut logs = logs.borrow_mut();
        if !logs.contains_key(&id_index) {
            let vm_index = get_vm(id_index);
            let vm_data = get_vm(id_data);
            logs.insert(
                id_index,
                StableLog::init(vm_index, vm_data).expect("slog init failed"),
            );
        }
    });
}

pub fn slog_append(id: u8, value: Vec<u8>) -> u64 {
    LOGS.with(|logs| {
        let mut logs = logs.borrow_mut();
        let log = logs.get_mut(&id).expect("slog not initialized");
        log.append(&SBytes(value)).expect("slog append failed")
    })
}

pub fn slog_get(id: u8, index: u64) -> Option<Vec<u8>> {
    LOGS.with(|logs| {
        let logs = logs.borrow();
        let log = logs.get(&id).expect("slog not initialized");
        log.get(index).map(|sb| sb.0)
    })
}

pub fn slog_len(id: u8) -> u64 {
    LOGS.with(|logs| {
        let logs = logs.borrow();
        let log = logs.get(&id).expect("slog not initialized");
        log.len()
    })
}

// ---------------------------------------------------------------------------
// Cell (single value)
// ---------------------------------------------------------------------------

pub fn scell_init(id: u8, default_value: Vec<u8>) {
    CELLS.with(|cells| {
        let mut cells = cells.borrow_mut();
        if !cells.contains_key(&id) {
            let vm = get_vm(id);
            cells.insert(
                id,
                StableCell::init(vm, SBytes(default_value)).expect("scell init failed"),
            );
        }
    });
}

pub fn scell_get(id: u8) -> Vec<u8> {
    CELLS.with(|cells| {
        let cells = cells.borrow();
        let cell = cells.get(&id).expect("scell not initialized");
        cell.get().0.clone()
    })
}

pub fn scell_set(id: u8, value: Vec<u8>) {
    CELLS.with(|cells| {
        let mut cells = cells.borrow_mut();
        let cell = cells.get_mut(&id).expect("scell not initialized");
        cell.set(SBytes(value)).expect("scell set failed");
    });
}

// ---------------------------------------------------------------------------
// MinHeap
// ---------------------------------------------------------------------------

pub fn sheap_init(id: u8) {
    HEAPS.with(|heaps| {
        let mut heaps = heaps.borrow_mut();
        if !heaps.contains_key(&id) {
            let vm = get_vm(id);
            heaps.insert(id, StableMinHeap::init(vm).expect("sheap init failed"));
        }
    });
}

pub fn sheap_push(id: u8, value: Vec<u8>) {
    HEAPS.with(|heaps| {
        let mut heaps = heaps.borrow_mut();
        let heap = heaps.get_mut(&id).expect("sheap not initialized");
        heap.push(&SBytes(value)).expect("sheap push failed");
    });
}

pub fn sheap_pop(id: u8) -> Option<Vec<u8>> {
    HEAPS.with(|heaps| {
        let mut heaps = heaps.borrow_mut();
        let heap = heaps.get_mut(&id).expect("sheap not initialized");
        heap.pop().map(|sb| sb.0)
    })
}

pub fn sheap_peek(id: u8) -> Option<Vec<u8>> {
    HEAPS.with(|heaps| {
        let heaps = heaps.borrow();
        let heap = heaps.get(&id).expect("sheap not initialized");
        heap.peek().map(|sb| sb.0)
    })
}

pub fn sheap_len(id: u8) -> u64 {
    HEAPS.with(|heaps| {
        let heaps = heaps.borrow();
        let heap = heaps.get(&id).expect("sheap not initialized");
        heap.len()
    })
}
