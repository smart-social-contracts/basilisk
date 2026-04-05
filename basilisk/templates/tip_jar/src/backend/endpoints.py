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

from models import Donor, TipMessage
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
def register_donor(name: text) -> text:
    """Register a new donor (or return existing one)."""
    existing = Donor[name]
    if existing is not None:
        return json.dumps({"status": "exists", "name": existing.name})

    donor = Donor(name=name, principal=str(ic.caller()))
    return json.dumps({"status": "created", "name": donor.name, "id": donor._id})


@update
def leave_message(donor_name: text, message: text) -> text:
    """Leave a message in the tip jar (without a transfer)."""
    donor = Donor[donor_name]
    if donor is None:
        return json.dumps({"error": f"Donor '{donor_name}' not found. Call register_donor first."})

    now_secs = int(ic.time() / 1_000_000_000)
    msg = TipMessage(
        donor_name=donor_name,
        message=message,
        amount=0,
        token="",
        timestamp=now_secs,
    )
    donor.message_count = donor.message_count + 1
    return json.dumps({"status": "ok", "message_id": msg._id})


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
def tip(donor_name: text, token_name: text, amount: nat64, message: text) -> Async[text]:
    """Record a tip and leave a message.

    In a real application you would first ``yield wallet.transfer(...)``
    to move tokens.  Here we record the intent so the example stays
    simple and doesn't require the caller to hold real tokens.
    """
    donor = Donor[donor_name]
    if donor is None:
        return json.dumps({"error": f"Donor '{donor_name}' not found."})

    # -- Record the tip in the DB --
    now_secs = int(ic.time() / 1_000_000_000)
    msg = TipMessage(
        donor_name=donor_name,
        message=message,
        amount=amount,
        token=token_name,
        timestamp=now_secs,
    )
    donor.total_donated = donor.total_donated + amount
    donor.message_count = donor.message_count + 1

    # -- Refresh balance from the ledger (async inter-canister call) --
    balance = yield wallet.balance_of(token_name)

    return json.dumps({
        "status": "ok",
        "message_id": msg._id,
        "new_total": donor.total_donated,
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
def get_public_key() -> Async[text]:
    """Derive the caller's vetKey public key (async)."""
    pub = yield vetkeys.public_key()
    return f"Public key ({len(pub)} bytes): {pub.hex()[:64]}..."


@update
def init_encryption(scope: text) -> Async[text]:
    """Initialize an encryption scope and generate a DEK (async).

    A *scope* is a named encryption context (e.g. ``"user:alice:private"``).
    ``init_scope`` creates a Data Encryption Key (DEK) wrapped with the
    caller's vetKey-derived key, stored as a ``KeyEnvelope`` entity.
    """
    dek = yield crypto.init_scope(scope)
    return json.dumps({
        "scope": scope,
        "dek_length": len(dek) if dek else 0,
    })


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

def _satoshis_to_usd(satoshis: int) -> float | None:
    """Convert ckBTC satoshis to USD using the cached BTC/USD rate."""
    btc_price = fx.get_rate("BTC", "USD")
    if btc_price is None:
        return None
    return round(satoshis / 1e8 * btc_price, 2)
