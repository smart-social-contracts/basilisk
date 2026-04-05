"""Tip Jar — Canister endpoints.

All ``@query`` and ``@update`` decorated functions are automatically
discovered by the basilisk build system and exposed in the Candid
interface.  They must be imported into ``main.py`` (via
``from endpoints import *``) so the Rust dispatcher can find them in
the entry module's global namespace at runtime.

Sections:
  1. Query endpoints   — read-only, no inter-canister calls
  2. Update endpoints  — may mutate state (sync)
  3. Async endpoints   — use ``yield`` for inter-canister calls
"""

import json
import os

from basilisk import query, update, text, nat64, ic, Async, match, CallResult
from basilisk.canisters.management import HttpResponse, HttpTransformArgs

from models import Donor, PendingTip, TipMessage, SecretNote
from services import wallet, fx, crypto, vetkeys


# ═══════════════════════════════════════════════════════════════════════════
# 1. QUERY ENDPOINTS  (read-only, no inter-canister calls)
# ═══════════════════════════════════════════════════════════════════════════

@query
def get_leaderboard() -> text:
    """Return top donors sorted by total donated, as JSON."""
    donors = sorted(
        Donor.instances(),
        key=lambda d: d.total_donated,
        reverse=True,
    )
    rows = []
    for d in donors[:20]:
        usd = _satoshis_to_usd(d.total_donated)
        rows.append({
            "name": d.name,
            "total_donated": d.total_donated,
            "usd_value": usd,
            "message_count": d.message_count,
        })
    return json.dumps(rows)


@query
def get_messages(limit: nat64) -> text:
    """Return the most recent tip messages, as JSON."""
    msgs = sorted(
        TipMessage.instances(),
        key=lambda m: m.timestamp,
        reverse=True,
    )
    rows = []
    for m in msgs[:limit]:
        rows.append({
            "donor": m.donor_name,
            "message": m.message,
            "amount": m.amount,
            "token": m.token,
            "timestamp": m.timestamp,
        })
    return json.dumps(rows)


@query
def get_stats() -> text:
    """Return aggregate tip jar statistics, as JSON."""
    total = sum(d.total_donated for d in Donor.instances())
    donor_count = sum(1 for _ in Donor.instances())
    msg_count = sum(1 for _ in TipMessage.instances())

    icp_price = fx.get_rate("ICP", "USD")
    btc_price = fx.get_rate("BTC", "USD")

    return json.dumps({
        "total_donated_satoshis": total,
        "total_donated_usd": _satoshis_to_usd(total),
        "donor_count": donor_count,
        "message_count": msg_count,
        "icp_usd": icp_price,
        "btc_usd": btc_price,
        "fx_last_updated": _get_fx_last_updated(),
        "secret_note_count": sum(1 for _ in SecretNote.instances()),
    })


@query
def status() -> text:
    """Health check endpoint."""
    return "ok"


@query
def get_time() -> nat64:
    """Return the current IC timestamp in nanoseconds."""
    return ic.time()


@query
def whoami() -> text:
    """Return the caller's principal ID."""
    return str(ic.caller())


@query
def read_file_endpoint(path: text) -> text:
    """Read a file from the canister's persistent filesystem."""
    try:
        with open(path, "r") as f:
            return f.read()
    except FileNotFoundError:
        return f"File not found: {path}"


@query
def list_files(path: text) -> text:
    """List files in a directory on the canister filesystem."""
    try:
        entries = os.listdir(path or "/")
        return "\n".join(entries) or "(empty)"
    except FileNotFoundError:
        return f"Directory not found: {path}"


@query
def http_transform(args: HttpTransformArgs) -> HttpResponse:
    """Transform function for HTTP outcalls — strips headers for consensus."""
    response = args["response"]
    response["headers"] = []
    return response


# ═══════════════════════════════════════════════════════════════════════════
# 2. UPDATE ENDPOINTS  (sync — mutate state, no inter-canister calls)
# ═══════════════════════════════════════════════════════════════════════════

@update
def register_tip(donor_name: text, amount: nat64, message: text, message_type: text) -> text:
    """Step 1: Register a pending tip before sending ckBTC.

    The user provides their name, the amount they plan to send,
    and an optional message (public or secret).  Returns a pending_id
    that is used later to verify the on-chain transfer.
    """
    if not donor_name.strip():
        return json.dumps({"error": "Name is required."})
    if amount <= 0:
        return json.dumps({"error": "Amount must be positive."})
    if message_type not in ("public", "secret"):
        message_type = "public"

    now_secs = int(ic.time() / 1_000_000_000)
    pending = PendingTip(
        donor_name=donor_name.strip(),
        message=message,
        message_type=message_type,
        amount=amount,
        token="ckBTC",
        principal=str(ic.caller()),
        timestamp=now_secs,
    )
    return json.dumps({
        "status": "pending",
        "pending_id": pending._id,
        "amount": amount,
    })


@update
def write_file_endpoint(path: text, content: text) -> text:
    """Write a file to the canister's persistent filesystem."""
    parent = os.path.dirname(path)
    if parent and parent != "/":
        os.makedirs(parent, exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    return f"Wrote {len(content)} bytes to {path}"


@update
def start_fx_timer(interval_secs: nat64) -> text:
    """Start a periodic timer that refreshes FX rates every N seconds."""
    def on_tick():
        ic.print(f"[timer] FX refresh tick at {ic.time()}")
    timer_id = ic.set_timer_interval(interval_secs, on_tick)
    return f"Started periodic FX timer id={timer_id}, interval={interval_secs}s"


@update
def schedule_once(delay_secs: nat64) -> text:
    """Schedule a one-shot timer that fires after N seconds."""
    def on_fire():
        ic.print("[timer] One-shot timer fired!")
    timer_id = ic.set_timer(delay_secs, on_fire)
    return f"Scheduled one-shot timer id={timer_id}, fires in {delay_secs}s"


# ═══════════════════════════════════════════════════════════════════════════
# 3. ASYNC ENDPOINTS  (use ``yield`` for inter-canister calls)
# ═══════════════════════════════════════════════════════════════════════════

@update
def verify_tip(pending_id: nat64) -> Async[text]:
    """Step 2: Verify a pending tip against on-chain ckBTC transfers.

    Refreshes the wallet from the ckBTC indexer, then scans for an
    incoming transfer whose amount matches the pending tip.  If found,
    the tip is confirmed: a Donor and TipMessage (or SecretNote) are
    created, and the pending record is removed.
    """
    pending = PendingTip.load(pending_id)
    if pending is None:
        return json.dumps({"error": "Pending tip not found."})

    # Refresh transactions from the indexer
    yield wallet.refresh("ckBTC")

    # Collect tx_ids already claimed by previous tips
    claimed_ids = set()
    for tm in TipMessage.instances():
        if tm.claimed_tx_id:
            claimed_ids.add(tm.claimed_tx_id)

    # Scan transfers for an unclaimed incoming tx matching the amount
    canister_id = str(ic.id())
    matched_tx = None
    transfers = wallet.list_transfers("ckBTC", limit=200)
    for tx in transfers:
        if tx["to"] != canister_id:
            continue
        if tx["tx_id"] in claimed_ids:
            continue
        if tx["amount"] == pending.amount:
            matched_tx = tx
            break

    if matched_tx is None:
        return json.dumps({
            "status": "not_found",
            "message": f"No matching {pending.amount}-sat transfer found yet. "
                       "Make sure you sent exactly that amount, then try again.",
        })

    # -- Match found: create or update Donor --
    donor = Donor[pending.donor_name]
    if donor is None:
        donor = Donor(name=pending.donor_name, principal=pending.principal)
    donor.total_donated = donor.total_donated + pending.amount
    donor.message_count = donor.message_count + (1 if pending.message else 0)

    now_secs = int(ic.time() / 1_000_000_000)

    # -- Store the message (public or secret) --
    if pending.message:
        if pending.message_type == "secret":
            import hashlib
            scope_hash = hashlib.sha256(b"tip_jar_secrets").digest()
            encrypted = _xor_encrypt(pending.message, scope_hash)
            SecretNote(
                sender_name=pending.donor_name,
                sender_principal=pending.principal,
                encrypted_text=encrypted,
                timestamp=now_secs,
            )
        else:
            TipMessage(
                donor_name=pending.donor_name,
                message=pending.message,
                amount=pending.amount,
                token="ckBTC",
                timestamp=now_secs,
                claimed_tx_id=matched_tx["tx_id"],
            )

    # If no message or secret message, still record a TipMessage for the amount
    if not pending.message or pending.message_type == "secret":
        TipMessage(
            donor_name=pending.donor_name,
            message="",
            amount=pending.amount,
            token="ckBTC",
            timestamp=now_secs,
            claimed_tx_id=matched_tx["tx_id"],
        )

    # Clean up pending record
    pending.delete()

    balance = yield wallet.balance_of("ckBTC")

    return json.dumps({
        "status": "verified",
        "donor": pending.donor_name,
        "amount": pending.amount,
        "tx_id": matched_tx["tx_id"],
        "canister_balance": balance,
    })


@update
def check_balance(token_name: text) -> Async[text]:
    """Query the canister's token balance from the ledger (async)."""
    balance = yield wallet.balance_of(token_name)
    return json.dumps({"token": token_name, "balance": balance})


@update
def refresh_wallet(token_name: text) -> Async[text]:
    """Sync transaction history from the indexer canister (async)."""
    result = yield wallet.refresh(token_name)
    return json.dumps({"token": token_name, "result": str(result)})


@update
def refresh_fx() -> Async[text]:
    """Fetch latest exchange rates from the IC XRC canister (async)."""
    summary = yield fx.refresh()
    return summary


@update
def submit_secret_note(sender_name: text, note_text: text) -> text:
    """Submit an encrypted note that only the canister owner can read.

    The note is encrypted at rest using a key derived from the
    canister's secret scope.  Only canister controllers can decrypt
    via the ``read_secret_notes`` query.

    In production, combine this with vetKey-derived keys and
    AES-GCM encryption on the client side for true end-to-end security.
    """
    import hashlib
    scope_hash = hashlib.sha256(b"tip_jar_secrets").digest()
    encrypted = _xor_encrypt(note_text, scope_hash)

    now_secs = int(ic.time() / 1_000_000_000)
    note = SecretNote(
        sender_name=sender_name,
        sender_principal=str(ic.caller()),
        encrypted_text=encrypted,
        timestamp=now_secs,
    )
    return json.dumps({"status": "ok", "note_id": note._id})


@query
def read_secret_notes() -> text:
    """Read all secret notes (controller-only, guarded in main.py).

    Decrypts the stored notes and returns them as JSON.
    """
    import hashlib
    scope_hash = hashlib.sha256(b"tip_jar_secrets").digest()

    notes = sorted(
        SecretNote.instances(),
        key=lambda n: n.timestamp,
        reverse=True,
    )
    rows = []
    for n in notes[:50]:
        rows.append({
            "sender_name": n.sender_name,
            "sender_principal": n.sender_principal,
            "note": _xor_decrypt(n.encrypted_text, scope_hash),
            "timestamp": n.timestamp,
        })
    return json.dumps(rows)


@update
def get_public_key() -> Async[text]:
    """Derive the caller's vetKey public key (async)."""
    pub = yield vetkeys.public_key()
    return f"Public key ({len(pub)} bytes): {pub.hex()[:64]}..."


@update
def download_page(url: text, dest: text) -> Async[text]:
    """Download a web page via HTTP outcall and save to the filesystem.

    Demonstrates IC HTTP outcalls through the management canister.
    The ``http_transform`` query strips non-deterministic headers so
    all replicas reach consensus on the response body.
    """
    from basilisk.canisters.management import management_canister

    http_result: CallResult[HttpResponse] = yield management_canister.http_request(
        {
            "url": url,
            "max_response_bytes": 2_000_000,
            "method": {"get": None},
            "headers": [
                {"name": "User-Agent", "value": "Basilisk-TipJar/1.0"},
                {"name": "Accept-Encoding", "value": "identity"},
            ],
            "body": None,
            "transform": {
                "function": (ic.id(), "http_transform"),
                "context": bytes(),
            },
        }
    ).with_cycles(30_000_000_000)

    def _handle_ok(response: HttpResponse) -> str:
        try:
            content = response["body"].decode("utf-8")
        except UnicodeDecodeError as e:
            return f"Error: failed to decode response as UTF-8: {e}"
        parent = os.path.dirname(dest)
        if parent and parent != "/":
            os.makedirs(parent, exist_ok=True)
        with open(dest, "w") as f:
            f.write(content)
        return f"Downloaded {len(content)} bytes to {dest}"

    def _handle_err(err: str) -> str:
        return f"Download failed: {err}"

    return match(http_result, {"Ok": _handle_ok, "Err": _handle_err})


# ═══════════════════════════════════════════════════════════════════════════
# Helpers (not exported as canister methods)
# ═══════════════════════════════════════════════════════════════════════════

def _get_fx_last_updated():
    """Get the most recent FX update timestamp (seconds epoch)."""
    info = fx.get_rate_info("BTC", "USD")
    if info and info.get("last_updated"):
        return info["last_updated"]
    return None


def _satoshis_to_usd(satoshis: int) -> float | None:
    """Convert ckBTC satoshis to USD using the cached BTC/USD rate."""
    btc_price = fx.get_rate("BTC", "USD")
    if btc_price is None:
        return None
    return round(satoshis / 1e8 * btc_price, 2)


def _xor_encrypt(plaintext: str, key: bytes) -> str:
    """Simple XOR obfuscation (demo only — use AES-GCM in production)."""
    import base64
    data = plaintext.encode("utf-8")
    encrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return base64.b64encode(encrypted).decode("ascii")


def _xor_decrypt(ciphertext: str, key: bytes) -> str:
    """Reverse XOR obfuscation."""
    import base64
    data = base64.b64decode(ciphertext)
    decrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return decrypted.decode("utf-8")
