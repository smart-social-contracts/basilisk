from basilisk import blob, nat, null, Opt, Principal, Record, Variant, Vec

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
    hash: ChunkHash


class ClearChunkStoreArgs(Record):
    canister_id: Principal


class StoredChunksArgs(Record):
    canister_id: Principal


class StoredChunksResult(Record):
    hash: ChunkHash


class InstallChunkedCodeArgs(Record):
    mode: "InstallCodeMode"
    target_canister: Principal
    store_canister: Opt[Principal]
    chunk_hashes_list: Vec[ChunkHash]
    wasm_module_hash: blob
    arg: blob
