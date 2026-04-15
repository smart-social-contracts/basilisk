"""
Basilisk WASM Repository + Deployer Canister

Stores versioned cpython_canister_template.wasm files on-chain and deploys
new basilisk canisters from them.

See: https://github.com/smart-social-contracts/basilisk/issues/40
"""

import json
import hashlib
import base64
import os
from basilisk import (
    Async,
    blob,
    CallResult,
    ic,
    match,
    Opt,
    Principal,
    query,
    text,
    update,
    void,
)
from basilisk.canisters.management import (
    CreateCanisterResult,
    UploadChunkResult,
    management_canister,
)


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

VERSIONS_FILE = "/deployer_versions.json"
CHUNK_PREFIX = "/deployer_chunk_"

# Deployment cost: cycles attached when creating a new canister
DEFAULT_DEPLOY_CYCLES = 500_000_000_000  # 0.5 T

# Max chunk size for upload_chunk calls to management canister (< 2 MB message limit)
UPLOAD_CHUNK_SIZE = 1_000_000  # 1 MB


def _load_versions():
    try:
        with open(VERSIONS_FILE, "r") as f:
            return json.loads(f.read())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_versions(versions):
    with open(VERSIONS_FILE, "w") as f:
        f.write(json.dumps(versions))


def _chunk_path(version, chunk_index):
    return f"{CHUNK_PREFIX}{version}_{chunk_index:04d}"


def _require_admin():
    if not ic.is_controller(ic.caller()):
        return json.dumps({"error": "Unauthorized: caller is not a controller"})
    return None


# ---------------------------------------------------------------------------
# Admin endpoints — controller-only
# ---------------------------------------------------------------------------

@update
def upload_wasm_chunk(args: text) -> text:
    """Upload a chunk of WASM data for a version.

    Args (JSON): {
        "version": str,
        "chunk_index": int,
        "data": str  (base64-encoded binary)
    }
    """
    err = _require_admin()
    if err:
        return err

    params = json.loads(args)
    version = params["version"]
    chunk_index = params["chunk_index"]
    data = base64.b64decode(params["data"])

    versions = _load_versions()
    if version in versions and versions[version].get("status") == "finalized":
        return json.dumps({"error": f"Version {version} is already finalized"})

    path = _chunk_path(version, chunk_index)
    with open(path, "wb") as f:
        f.write(data)

    chunk_hash = hashlib.sha256(data).hexdigest()

    if version not in versions:
        versions[version] = {
            "version": version,
            "status": "uploading",
            "chunks_uploaded": 0,
            "total_size": 0,
            "chunk_sizes": [],
            "description": "",
        }
    versions[version]["chunks_uploaded"] = max(
        versions[version].get("chunks_uploaded", 0), chunk_index + 1
    )
    # Track cumulative size
    chunk_sizes = versions[version].get("chunk_sizes", [])
    while len(chunk_sizes) <= chunk_index:
        chunk_sizes.append(0)
    chunk_sizes[chunk_index] = len(data)
    versions[version]["chunk_sizes"] = chunk_sizes
    versions[version]["total_size"] = sum(chunk_sizes)
    _save_versions(versions)

    return json.dumps({
        "ok": True,
        "chunk_index": chunk_index,
        "size": len(data),
        "chunk_hash": chunk_hash,
    })


@update
def finalize_version(args: text) -> text:
    """Mark a version as complete after all chunks have been uploaded.

    Args (JSON): {
        "version": str,
        "description": str,
        "expected_hash": str  (optional, SHA-256 hex)
    }
    """
    err = _require_admin()
    if err:
        return err

    params = json.loads(args)
    version = params["version"]
    description = params.get("description", "")
    expected_hash = params.get("expected_hash", "")

    versions = _load_versions()
    if version not in versions:
        return json.dumps({"error": f"Version {version} not found"})
    if versions[version].get("status") == "finalized":
        return json.dumps({"error": f"Version {version} is already finalized"})

    num_chunks = versions[version].get("chunks_uploaded", 0)
    total_size = versions[version].get("total_size", 0)

    # Verify all chunk files are present (lightweight check, no re-reading)
    for i in range(num_chunks):
        chunk_path = _chunk_path(version, i)
        try:
            with open(chunk_path, "rb") as f:
                # Just read 1 byte to verify existence
                if f.read(1) == b"":
                    return json.dumps({"error": f"Chunk {i} is empty for version {version}"})
        except FileNotFoundError:
            return json.dumps({"error": f"Missing chunk {i} for version {version}"})

    # Trust the client-provided hash (caller is a verified controller)
    wasm_hash = expected_hash if expected_hash else "unknown"

    versions[version] = {
        "version": version,
        "status": "finalized",
        "description": description,
        "size": total_size,
        "sha256": wasm_hash,
        "num_chunks": num_chunks,
        "upload_timestamp": ic.time(),
    }
    _save_versions(versions)

    return json.dumps({
        "ok": True,
        "version": version,
        "size": total_size,
        "sha256": wasm_hash,
    })


@update
def remove_version(args: text) -> text:
    """Remove a version from the store.

    Args (JSON): {"version": str}
    """
    err = _require_admin()
    if err:
        return err

    params = json.loads(args)
    version = params["version"]

    versions = _load_versions()
    if version not in versions:
        return json.dumps({"error": f"Version {version} not found"})

    num_chunks = versions[version].get("chunks_uploaded", 0)
    for i in range(num_chunks):
        try:
            os.remove(_chunk_path(version, i))
        except FileNotFoundError:
            pass

    del versions[version]
    _save_versions(versions)

    return json.dumps({"ok": True, "version": version})


# ---------------------------------------------------------------------------
# Public query endpoints
# ---------------------------------------------------------------------------

@query
def list_versions() -> text:
    """Return JSON list of finalized versions."""
    versions = _load_versions()
    result = []
    for v in versions.values():
        if v.get("status") == "finalized":
            result.append({
                "version": v["version"],
                "description": v.get("description", ""),
                "size": v.get("size", 0),
                "sha256": v.get("sha256", ""),
                "upload_timestamp": v.get("upload_timestamp", 0),
            })
    result.sort(key=lambda x: x["version"])
    return json.dumps(result)


@query
def get_version_info(version: text) -> text:
    """Return JSON metadata for a specific version."""
    versions = _load_versions()
    if version not in versions:
        return json.dumps({"error": f"Version {version} not found"})
    return json.dumps(versions[version])


# ---------------------------------------------------------------------------
# Deploy endpoint
# ---------------------------------------------------------------------------

@update
def deploy(args: text) -> Async[text]:
    """Deploy a new canister with the specified version's WASM.

    Args (JSON): {
        "version": str,
        "controllers": [str]  (optional extra controller principals),
        "cycles": int          (optional cycles to attach, default 0.5T)
    }
    Returns JSON: {"ok": true, "canister_id": str, "version": str}
                  or {"error": str}
    """
    params = json.loads(args)
    version = params["version"]
    extra_controllers = params.get("controllers", [])
    deploy_cycles = params.get("cycles", DEFAULT_DEPLOY_CYCLES)

    versions = _load_versions()
    if version not in versions:
        return json.dumps({"error": f"Version {version} not found"})
    if versions[version].get("status") != "finalized":
        return json.dumps({"error": f"Version {version} is not finalized"})

    num_chunks = versions[version].get("num_chunks", 0)
    wasm_hash_hex = versions[version].get("sha256", "")
    wasm_hash = bytes.fromhex(wasm_hash_hex)

    # Controllers: deployer (self) + caller + any extras
    controllers = [ic.id(), ic.caller()]
    for c in extra_controllers:
        controllers.append(Principal.from_str(c))

    # --- Step 1: Create canister ---
    create_result: CallResult[CreateCanisterResult] = (
        yield management_canister.create_canister({
            "settings": Opt({
                "controllers": Opt(controllers),
                "compute_allocation": None,
                "memory_allocation": None,
                "freezing_threshold": None,
            })
        }).with_cycles(deploy_cycles)
    )

    create_err = match(create_result, {
        "Ok": lambda _r: None,
        "Err": lambda e: str(e),
    })
    if create_err:
        return json.dumps({"error": f"create_canister failed: {create_err}"})

    canister_id = match(create_result, {
        "Ok": lambda r: r["canister_id"],
        "Err": lambda _e: None,
    })

    # --- Step 2: Upload stored chunks to the new canister ---
    chunk_hashes = []
    for i in range(num_chunks):
        try:
            with open(_chunk_path(version, i), "rb") as f:
                chunk_data = f.read()
        except FileNotFoundError:
            return json.dumps({
                "error": f"Missing chunk {i} for version {version}",
                "canister_id": canister_id.to_str(),
            })

        upload_result: CallResult[UploadChunkResult] = (
            yield management_canister.upload_chunk({
                "canister_id": canister_id,
                "chunk": chunk_data,
            })
        )

        upload_err = match(upload_result, {
            "Ok": lambda _r: None,
            "Err": lambda e: str(e),
        })
        if upload_err:
            return json.dumps({
                "error": f"upload_chunk failed: {upload_err}",
                "canister_id": canister_id.to_str(),
            })

        chunk_hash = match(upload_result, {
            "Ok": lambda r: r["hash"],
            "Err": lambda _e: None,
        })
        chunk_hashes.append({"hash": chunk_hash})

    # --- Step 3: Install chunked code ---
    install_result: CallResult[void] = (
        yield management_canister.install_chunked_code({
            "mode": {"install": None},
            "target_canister": canister_id,
            "store_canister": None,
            "chunk_hashes_list": chunk_hashes,
            "wasm_module_hash": wasm_hash,
            "arg": bytes(),
        })
    )

    install_err = match(install_result, {
        "Ok": lambda _: None,
        "Err": lambda e: str(e),
    })
    if install_err:
        return json.dumps({
            "error": f"install_chunked_code failed: {install_err}",
            "canister_id": canister_id.to_str(),
        })

    return json.dumps({
        "ok": True,
        "canister_id": canister_id.to_str(),
        "version": version,
    })
