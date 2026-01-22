"""
Controller Canister - upgrade other canisters using IC's chunked code upload API
"""

from basilisk import Async, blob, CallResult, ic, nat32, Principal, query, update, Variant, Vec, void
from basilisk.canisters.management import (
    management_canister,
    ChunkHash,
    UploadChunkResult,
)


class UpgradeResult(Variant, total=False):
    Ok: str
    Err: str


# Track uploaded chunk hashes per target canister
uploaded_hashes: dict[str, list[bytes]] = {}


@update
def upload_wasm_chunk(target_canister_id: Principal, chunk: blob) -> Async[UpgradeResult]:
    """Upload a WASM chunk to IC's chunk store via management canister"""
    canister_key = str(target_canister_id)
    chunk_size = len(chunk)
    
    ic.print(f"Uploading chunk for {target_canister_id}, size: {chunk_size} bytes")
    
    # Upload chunk to the management canister's chunk store
    call_result: CallResult[UploadChunkResult] = yield management_canister.upload_chunk({
        "canister_id": target_canister_id,
        "chunk": chunk,
    })
    
    if "Err" in call_result:
        return {"Err": f"Failed to upload chunk: {call_result['Err']}"}
    
    result = call_result["Ok"]
    chunk_hash = result["hash"]
    if canister_key not in uploaded_hashes:
        uploaded_hashes[canister_key] = []
    uploaded_hashes[canister_key].append(bytes(chunk_hash))
    chunk_index = len(uploaded_hashes[canister_key]) - 1
    ic.print(f"Chunk {chunk_index} uploaded, hash: {bytes(chunk_hash).hex()[:16]}...")
    return {"Ok": f"Chunk {chunk_index} uploaded ({chunk_size} bytes)"}


@update
def execute_chunked_upgrade(target_canister_id: Principal, wasm_module_hash: blob) -> Async[UpgradeResult]:
    """Execute upgrade using IC's install_chunked_code with previously uploaded chunks"""
    canister_key = str(target_canister_id)
    
    if canister_key not in uploaded_hashes or len(uploaded_hashes[canister_key]) == 0:
        return {"Err": "No chunks uploaded. Call upload_wasm_chunk first."}
    
    # Build chunk hashes list
    chunk_hashes_list: list[ChunkHash] = [
        {"hash": h} for h in uploaded_hashes[canister_key]
    ]
    
    ic.print(f"Installing chunked code with {len(chunk_hashes_list)} chunks, wasm hash: {bytes(wasm_module_hash).hex()[:16]}...")
    
    # Call install_chunked_code
    call_result: CallResult[void] = yield management_canister.install_chunked_code({
        "mode": {"upgrade": None},
        "target_canister": target_canister_id,
        "store_canister": None,  # Use target canister as store
        "chunk_hashes_list": chunk_hashes_list,
        "wasm_module_hash": wasm_module_hash,
        "arg": bytes(),
    })
    
    if "Err" in call_result:
        return {"Err": f"Failed to install chunked code: {call_result['Err']}"}
    
    del uploaded_hashes[canister_key]
    return {"Ok": f"Canister {target_canister_id} upgraded successfully with chunked code"}


@update
def clear_chunks(target_canister_id: Principal) -> Async[UpgradeResult]:
    """Clear uploaded chunks from IC's chunk store"""
    canister_key = str(target_canister_id)
    
    # Clear from management canister's chunk store
    call_result: CallResult[void] = yield management_canister.clear_chunk_store({
        "canister_id": target_canister_id,
    })
    
    if "Err" in call_result:
        return {"Err": f"Failed to clear chunk store: {call_result['Err']}"}
    
    count = 0
    if canister_key in uploaded_hashes:
        count = len(uploaded_hashes[canister_key])
        del uploaded_hashes[canister_key]
    return {"Ok": f"Cleared {count} chunks"}


@query
def get_chunk_count(target_canister_id: Principal) -> nat32:
    """Get number of uploaded chunks for a canister"""
    canister_key = str(target_canister_id)
    if canister_key in uploaded_hashes:
        return len(uploaded_hashes[canister_key])
    return 0


@query
def whoami() -> str:
    """Return this canister's ID"""
    return str(ic.id())
