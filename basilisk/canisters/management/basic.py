from basilisk import blob, nat, nat64, null, Opt, Principal, Record, Variant, Vec

# TODO type aliases do not work yet
# TODO many canister_id fields need to be changed to use this alias
# CanisterId = Principal
# WasmModule = blob


class CreateCanisterArgs(Record):
    settings: Opt["CanisterSettings"]


class CanisterSettings(Record):
    controllers: Opt[Vec[Principal]]
    compute_allocation: Opt[nat]
    memory_allocation: Opt[nat]
    freezing_threshold: Opt[nat]


class DefiniteCanisterSettings(Record):
    controllers: Vec[Principal]
    compute_allocation: nat
    memory_allocation: nat
    freezing_threshold: nat


class CreateCanisterResult(Record):
    canister_id: Principal


class UpdateSettingsArgs(Record):
    canister_id: Principal
    settings: CanisterSettings


class InstallCodeArgs(Record):
    mode: "InstallCodeMode"
    canister_id: Principal
    wasm_module: blob
    arg: blob


class InstallCodeMode(Variant, total=False):
    install: null
    reinstall: null
    upgrade: null


class UninstallCodeArgs(Record):
    canister_id: Principal


class StartCanisterArgs(Record):
    canister_id: Principal


class StopCanisterArgs(Record):
    canister_id: Principal


class CanisterStatusArgs(Record):
    canister_id: Principal


class CanisterStatusResult(Record):
    status: "CanisterStatus"
    settings: DefiniteCanisterSettings
    module_hash: Opt[blob]
    memory_size: nat
    cycles: nat


class CanisterStatus(Variant):
    running: null
    stopping: null
    stopped: null


class DeleteCanisterArgs(Record):
    canister_id: Principal


class DepositCyclesArgs(Record):
    canister_id: Principal


class ProvisionalCreateCanisterWithCyclesArgs(Record):
    amount: Opt[nat]
    settings: Opt[CanisterSettings]


class ProvisionalCreateCanisterWithCyclesResult(Record):
    canister_id: Principal


class ProvisionalTopUpCanisterArgs(Record):
    canister_id: Principal
    amount: nat


# Chunked code upload API (for WASMs > 10MB)
# See: https://internetcomputer.org/docs/current/references/ic-interface-spec#ic-upload_chunk

class ChunkHash(Record):
    hash: blob


class UploadChunkArgs(Record):
    canister_id: Principal
    chunk: blob


class UploadChunkResult(Record):
    hash: blob


class ClearChunkStoreArgs(Record):
    canister_id: Principal


class StoredChunksArgs(Record):
    canister_id: Principal


class StoredChunksResult(Record):
    hash: blob


class InstallChunkedCodeArgs(Record):
    mode: InstallCodeMode
    target_canister: Principal
    store_canister: Opt[Principal]
    chunk_hashes_list: Vec[ChunkHash]
    wasm_module_hash: blob
    arg: blob


# Canister snapshot API
# See: https://internetcomputer.org/docs/current/references/ic-interface-spec#ic-take_canister_snapshot

class TakeCanisterSnapshotArgs(Record):
    canister_id: Principal
    replace_snapshot: Opt[blob]


class CanisterSnapshotResult(Record):
    id: blob
    taken_at_timestamp: nat64
    total_size: nat64


class LoadCanisterSnapshotArgs(Record):
    canister_id: Principal
    snapshot_id: blob
    sender_canister_version: Opt[nat64]


class DeleteCanisterSnapshotArgs(Record):
    canister_id: Principal
    snapshot_id: blob


class ListCanisterSnapshotsArgs(Record):
    canister_id: Principal
