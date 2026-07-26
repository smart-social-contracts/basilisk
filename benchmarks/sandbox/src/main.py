"""Benchmark canister for the subinterpreter sandbox (issue #52).

Quantifies the runtime cost of `_basilisk_sandbox` so downstream projects
(e.g. Realms, smart-social-contracts/realms#244) can decide which workloads
to sandbox. All numbers come from `ic0.performance_counter`: counter 0 is
the current-call instruction count (used for start/end deltas around the
measured region), counter 1 is the call-context total.

Measurements (one endpoint per data point, following benchmarks/counter/):

1. Spawn cost vs source size        bench_spawn_{1kb,10kb,50kb}
2. Call bridge overhead             bench_call_noop_{inprocess,sandbox}
3. Boundary deep-copy scaling       bench_roundtrip_{1kb,10kb,100kb,1mb}
4. Full fresh-per-use cycle         bench_fresh_cycle_{min,10kb}
5. Metering overhead                bench_{sum_to,fib}_{inprocess,
                                      sandbox_unmetered,sandbox_metered}
6. Realistic extension workload     bench_extension_{inprocess,
                                      sandbox_unmetered,sandbox_metered}
7. Memory footprint                 bench_memory_per_live,
                                    bench_memory_soak(cycles)
8. Capability rpc() round-trip      bench_rpc_roundtrip

Fairness notes:

- The compute and extension workloads run the IDENTICAL source both
  sandboxed and in-process (the in-process twin is `exec`d into a plain
  namespace), so the comparison isolates the sandbox/metering cost, not
  differences between implementations.
- The sandbox has no `json` module (the main interpreter's `json` is
  preamble-provided and intentionally absent in subinterpreters), so the
  extension workload carries a small pure-Python JSON parser/serializer in
  its own source — which is exactly what a real self-contained extension
  would have to do.
- "Sandboxed unmetered" spawns with budget=0 (metering disabled, but the
  per-dispatch load+branch check still runs); "metered" uses a generous
  budget so the meter never trips. The difference isolates the metering
  bookkeeping from the bridge cost.
"""

import json

import _basilisk_sandbox as sb

from basilisk import Record, Vec, ic, nat64, update
from basilisk.sandbox import build_capability, call_sandboxed, spawn_sandboxed


class BenchmarkResult(Record):
    body_instructions: nat64
    total_instructions: nat64
    result: nat64


# A budget high enough that no benchmark ever trips it, so the metered
# variants measure pure bookkeeping overhead, not trip handling.
GENEROUS_BUDGET = 10_000_000_000


def _approve(source):
    h = sb.sha256(source)
    sb.approve_hash(h)
    return h


def _result(start, end, result):
    return {
        "body_instructions": end - start,
        "total_instructions": ic.performance_counter(1),
        "result": result,
    }


# ─── Synthetic sources ───────────────────────────────────────────────────────

def _make_source(target_bytes):
    """Deterministic synthetic extension backend of roughly target_bytes:
    many small handler functions, plus a noop. Mimics the shape of a real
    10-50 KB extension module (mostly def statements at module body)."""
    parts = ["# synthetic extension backend\n"]
    size = len(parts[0])
    i = 0
    template = (
        "def handler_{i:04d}(payload=None):\n"
        "    \"\"\"Process one sync call for route {i:04d}.\"\"\"\n"
        "    data = payload or {{}}\n"
        "    total = 0\n"
        "    for key, value in data.items():\n"
        "        if isinstance(value, int):\n"
        "            total += value\n"
        "    return {{'route': {i}, 'total': total}}\n\n"
    )
    while size < target_bytes:
        chunk = template.format(i=i)
        parts.append(chunk)
        size += len(chunk)
        i += 1
    parts.append("def noop():\n    return None\n")
    return "".join(parts)


_SRC_1KB = _make_source(1 * 1024)
_SRC_10KB = _make_source(10 * 1024)
_SRC_50KB = _make_source(50 * 1024)

_SRC_MIN = "def noop():\n    return None\n"

_ECHO_SOURCE = "def echo(payload=None):\n    return payload\n"

# Compute-bound functions used for the metering comparison. Executed
# verbatim in the sandbox AND in-process (identical bytecode).
_COMPUTE_SOURCE = """\
def sum_to(n=10000):
    total = 0
    for i in range(1, n + 1):
        total += i
    return total


def fib(n=20):
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)


def noop():
    return None
"""

# Realistic extension workload: parse a JSON payload, transform it
# (dict/list manipulation), serialize the result. Self-contained pure-Python
# JSON because the sandbox has no `json` module; the in-process comparison
# runs this exact source so both sides pay for the same implementation.
_EXTENSION_SOURCE = '''\
_ESC = {'"': '"', '\\\\': '\\\\', '/': '/', 'b': '\\b', 'f': '\\f',
        'n': '\\n', 'r': '\\r', 't': '\\t'}


def _ws(s, i):
    while i < len(s) and s[i] in ' \\t\\n\\r':
        i += 1
    return i


def _pstr(s, i):
    if s[i] != '"':
        raise ValueError('expected string at %d' % i)
    i += 1
    buf = []
    while True:
        c = s[i]
        if c == '"':
            return ''.join(buf), i + 1
        if c == '\\\\':
            e = s[i + 1]
            if e == 'u':
                buf.append(chr(int(s[i + 2:i + 6], 16)))
                i += 6
            else:
                buf.append(_ESC[e])
                i += 2
        else:
            buf.append(c)
            i += 1


def _pnum(s, i):
    j = i
    if s[j] == '-':
        j += 1
    while j < len(s) and (s[j].isdigit() or s[j] in '.eE+-'):
        j += 1
    text = s[i:j]
    if '.' in text or 'e' in text or 'E' in text:
        return float(text), j
    return int(text), j


def _pv(s, i):
    c = s[i]
    if c == '{':
        return _pobj(s, i)
    if c == '[':
        return _parr(s, i)
    if c == '"':
        return _pstr(s, i)
    if s.startswith('true', i):
        return True, i + 4
    if s.startswith('false', i):
        return False, i + 5
    if s.startswith('null', i):
        return None, i + 4
    return _pnum(s, i)


def _pobj(s, i):
    i = _ws(s, i + 1)
    out = {}
    if s[i] == '}':
        return out, i + 1
    while True:
        k, i = _pstr(s, i)
        i = _ws(s, i)
        if s[i] != ':':
            raise ValueError('expected : at %d' % i)
        v, i = _pv(s, _ws(s, i + 1))
        out[k] = v
        i = _ws(s, i)
        if s[i] == ',':
            i = _ws(s, i + 1)
        elif s[i] == '}':
            return out, i + 1
        else:
            raise ValueError('expected , or } at %d' % i)


def _parr(s, i):
    i = _ws(s, i + 1)
    out = []
    if s[i] == ']':
        return out, i + 1
    while True:
        v, i = _pv(s, i)
        out.append(v)
        i = _ws(s, i)
        if s[i] == ',':
            i = _ws(s, i + 1)
        elif s[i] == ']':
            return out, i + 1
        else:
            raise ValueError('expected , or ] at %d' % i)


def loads(s):
    v, i = _pv(s, _ws(s, 0))
    if _ws(s, i) != len(s):
        raise ValueError('trailing data')
    return v


def _dstr(v, out):
    out.append('"')
    for c in v:
        if c == '"':
            out.append('\\\\"')
        elif c == '\\\\':
            out.append('\\\\\\\\')
        elif c < ' ':
            out.append('\\\\u%04x' % ord(c))
        else:
            out.append(c)
    out.append('"')


def _dv(v, out):
    if v is None:
        out.append('null')
    elif v is True:
        out.append('true')
    elif v is False:
        out.append('false')
    elif isinstance(v, (int, float)):
        out.append(repr(v))
    elif isinstance(v, str):
        _dstr(v, out)
    elif isinstance(v, (list, tuple)):
        out.append('[')
        for k, item in enumerate(v):
            if k:
                out.append(', ')
            _dv(item, out)
        out.append(']')
    elif isinstance(v, dict):
        out.append('{')
        first = True
        for k, item in v.items():
            if not first:
                out.append(', ')
            first = False
            _dstr(k, out)
            out.append(': ')
            _dv(item, out)
        out.append('}')
    else:
        raise TypeError(type(v).__name__)


def dumps(v):
    out = []
    _dv(v, out)
    return ''.join(out)


def handle_sync_call(payload_json=''):
    """Approximates a Realms extension_sync_call handler: json.loads a
    payload, transform it with dict/list manipulation, json.dumps the
    result."""
    data = loads(payload_json)
    items = data['items']
    active = [it for it in items if it['active']]
    total = 0.0
    for it in active:
        total += it['value']
    by_tag = {}
    for it in items:
        for t in it['tags']:
            by_tag[t] = by_tag.get(t, 0) + 1
    out = {
        'count': len(items),
        'active_count': len(active),
        'total_value': total,
        'by_tag': by_tag,
        'items': [{'id': it['id'], 'name': it['name']} for it in active],
    }
    return dumps(out)
'''

# In-process twins: exec the exact same sources into a plain namespace so
# the in-process benchmarks run identical bytecode.
_MAIN_NS = {}
exec(_COMPUTE_SOURCE, _MAIN_NS)
exec(_EXTENSION_SOURCE, _MAIN_NS)


def _make_payload(target_bytes):
    """Deterministic JSON-like payload (nested dict/list/str) of roughly
    target_bytes when JSON-serialized. Returns (payload, json_size)."""
    probe = {
        "id": 0,
        "name": "item-000000",
        "tags": ["alpha", "beta", "gamma"],
        "value": 0.0,
        "active": True,
        "note": None,
    }
    per_record = len(json.dumps(probe)) + 2
    n = max(1, target_bytes // per_record)
    items = [
        {
            "id": i,
            "name": "item-%06d" % i,
            "tags": ["alpha", "beta", "gamma"],
            "value": i * 1.5,
            "active": i % 2 == 0,
            "note": None,
        }
        for i in range(n)
    ]
    payload = {"items": items}
    return payload, len(json.dumps(payload))


# ─── 1. Spawn cost vs source size ────────────────────────────────────────────

def _bench_spawn(source) -> BenchmarkResult:
    h = _approve(source)
    start = ic.performance_counter(0)
    handle = sb.spawn_subinterpreter(source, h)
    end = ic.performance_counter(0)
    sb.close_subinterpreter(handle)
    return _result(start, end, len(source))


@update
def bench_spawn_1kb() -> BenchmarkResult:
    """Spawn cost, ~1 KB source (result = source bytes)."""
    return _bench_spawn(_SRC_1KB)


@update
def bench_spawn_10kb() -> BenchmarkResult:
    """Spawn cost, ~10 KB source (result = source bytes)."""
    return _bench_spawn(_SRC_10KB)


@update
def bench_spawn_50kb() -> BenchmarkResult:
    """Spawn cost, ~50 KB source (result = source bytes)."""
    return _bench_spawn(_SRC_50KB)


# ─── 2. Call bridge overhead ─────────────────────────────────────────────────

@update
def bench_call_noop_inprocess() -> BenchmarkResult:
    """Direct call of a noop function in the main interpreter."""
    noop = _MAIN_NS["noop"]
    start = ic.performance_counter(0)
    noop()
    end = ic.performance_counter(0)
    return _result(start, end, 0)


@update
def bench_call_noop_sandbox() -> BenchmarkResult:
    """call_in_subinterpreter of the identical noop (spawn outside timer)."""
    h = _approve(_COMPUTE_SOURCE)
    handle = sb.spawn_subinterpreter(_COMPUTE_SOURCE, h)
    try:
        start = ic.performance_counter(0)
        sb.call_in_subinterpreter(handle, "noop", None)
        end = ic.performance_counter(0)
    finally:
        sb.close_subinterpreter(handle)
    return _result(start, end, 0)


# ─── 3. Boundary deep-copy scaling ───────────────────────────────────────────

def _bench_roundtrip(target_bytes) -> BenchmarkResult:
    payload, size = _make_payload(target_bytes)
    h = _approve(_ECHO_SOURCE)
    handle = sb.spawn_subinterpreter(_ECHO_SOURCE, h)
    try:
        start = ic.performance_counter(0)
        sb.call_in_subinterpreter(handle, "echo", {"payload": payload})
        end = ic.performance_counter(0)
    finally:
        sb.close_subinterpreter(handle)
    return _result(start, end, size)


@update
def bench_roundtrip_1kb() -> BenchmarkResult:
    """Round-trip a ~1 KB payload as args and result (result = JSON bytes)."""
    return _bench_roundtrip(1 * 1024)


@update
def bench_roundtrip_10kb() -> BenchmarkResult:
    """Round-trip a ~10 KB payload (result = JSON bytes)."""
    return _bench_roundtrip(10 * 1024)


@update
def bench_roundtrip_100kb() -> BenchmarkResult:
    """Round-trip a ~100 KB payload (result = JSON bytes)."""
    return _bench_roundtrip(100 * 1024)


@update
def bench_roundtrip_1mb() -> BenchmarkResult:
    """Round-trip a ~1 MB payload (result = JSON bytes)."""
    return _bench_roundtrip(1024 * 1024)


# ─── 4. Full fresh-per-use cycle ─────────────────────────────────────────────

def _bench_fresh_cycle(source) -> BenchmarkResult:
    start = ic.performance_counter(0)
    h = sb.sha256(source)
    sb.approve_hash(h)
    handle = sb.spawn_subinterpreter(source, h)
    sb.call_in_subinterpreter(handle, "noop", None)
    sb.close_subinterpreter(handle)
    end = ic.performance_counter(0)
    return _result(start, end, len(source))


@update
def bench_fresh_cycle_min() -> BenchmarkResult:
    """sha256 + approve + spawn + one call + close, minimal source."""
    return _bench_fresh_cycle(_SRC_MIN)


@update
def bench_fresh_cycle_10kb() -> BenchmarkResult:
    """sha256 + approve + spawn + one call + close, ~10 KB source."""
    return _bench_fresh_cycle(_SRC_10KB)


# ─── 5. Instruction-budget metering overhead ─────────────────────────────────

def _bench_sandbox_call(source, fn, kwargs, budget, result_of):
    """Spawn `source` with `budget` (0 = metering disabled), time one call."""
    h = _approve(source)
    handle = sb.spawn_subinterpreter(source, h, "", (), None, budget)
    try:
        start = ic.performance_counter(0)
        r = sb.call_in_subinterpreter(handle, fn, kwargs)
        end = ic.performance_counter(0)
    finally:
        sb.close_subinterpreter(handle)
    return _result(start, end, result_of(r))


@update
def bench_sum_to_inprocess() -> BenchmarkResult:
    """sum_to(10000) in the main interpreter, unmetered."""
    sum_to = _MAIN_NS["sum_to"]
    start = ic.performance_counter(0)
    r = sum_to(10000)
    end = ic.performance_counter(0)
    return _result(start, end, r)


@update
def bench_sum_to_sandbox_unmetered() -> BenchmarkResult:
    """sum_to(10000) sandboxed with metering disabled (budget=0)."""
    return _bench_sandbox_call(_COMPUTE_SOURCE, "sum_to", {"n": 10000},
                               0, lambda r: r)


@update
def bench_sum_to_sandbox_metered() -> BenchmarkResult:
    """sum_to(10000) sandboxed with a generous instruction budget."""
    return _bench_sandbox_call(_COMPUTE_SOURCE, "sum_to", {"n": 10000},
                               GENEROUS_BUDGET, lambda r: r)


@update
def bench_fib_inprocess() -> BenchmarkResult:
    """Recursive fib(20) in the main interpreter, unmetered."""
    fib = _MAIN_NS["fib"]
    start = ic.performance_counter(0)
    r = fib(20)
    end = ic.performance_counter(0)
    return _result(start, end, r)


@update
def bench_fib_sandbox_unmetered() -> BenchmarkResult:
    """Recursive fib(20) sandboxed with metering disabled (budget=0)."""
    return _bench_sandbox_call(_COMPUTE_SOURCE, "fib", {"n": 20},
                               0, lambda r: r)


@update
def bench_fib_sandbox_metered() -> BenchmarkResult:
    """Recursive fib(20) sandboxed with a generous instruction budget."""
    return _bench_sandbox_call(_COMPUTE_SOURCE, "fib", {"n": 20},
                               GENEROUS_BUDGET, lambda r: r)


# ─── 6. Realistic extension workload ─────────────────────────────────────────

def _extension_payload_json():
    payload, _size = _make_payload(10 * 1024)
    return json.dumps(payload)


@update
def bench_extension_inprocess() -> BenchmarkResult:
    """Extension workload (parse 10 KB JSON + transform + serialize)
    in-process, running the identical source as the sandboxed variants."""
    payload_json = _extension_payload_json()
    handler = _MAIN_NS["handle_sync_call"]
    start = ic.performance_counter(0)
    out = handler(payload_json=payload_json)
    end = ic.performance_counter(0)
    return _result(start, end, len(out))


@update
def bench_extension_sandbox_unmetered() -> BenchmarkResult:
    """Extension workload sandboxed, metering disabled (budget=0)."""
    payload_json = _extension_payload_json()
    return _bench_sandbox_call(_EXTENSION_SOURCE, "handle_sync_call",
                               {"payload_json": payload_json}, 0, len)


@update
def bench_extension_sandbox_metered() -> BenchmarkResult:
    """Extension workload sandboxed with a generous instruction budget."""
    payload_json = _extension_payload_json()
    return _bench_sandbox_call(_EXTENSION_SOURCE, "handle_sync_call",
                               {"payload_json": payload_json},
                               GENEROUS_BUDGET, len)


# ─── 8. Capability rpc() round-trip ──────────────────────────────────────────

@update
def bench_rpc_roundtrip() -> BenchmarkResult:
    """One rpc() round-trip through a host handler with a small payload,
    on top of a plain sandboxed call (compare with bench_call_noop_sandbox)."""
    cap = build_capability(
        {"classes": {}, "allowed_actions": ["echo"]},
        {"classes": {}, "allowed_actions": ["echo"]},
        context_id="bench-rpc",
    )

    def handler(context_id, action, kwargs):
        return {"ok": True, "v": kwargs.get("v", 0)}

    source = "def do_rpc():\n    return rpc('echo', v=1)\n"
    h = _approve(source)
    handle = spawn_sandboxed(source, h, cap, handler)
    try:
        start = ic.performance_counter(0)
        call_sandboxed(handle, "do_rpc")
        end = ic.performance_counter(0)
    finally:
        sb.close_subinterpreter(handle)
    return _result(start, end, 0)


# ─── 7. Memory footprint ─────────────────────────────────────────────────────

@update
def bench_memory_per_live() -> Vec[str]:
    """Canister heap growth per LIVE subinterpreter: spawn 6 with a ~10 KB
    source, report wasm linear-memory pages (64 KiB each; the counter is a
    high-water mark — pages are never returned, but freed heap is reused by
    malloc, so repeat calls that report delta 0 mean close() fully recycles)."""
    n = 6
    h = _approve(_SRC_10KB)
    before = sb.wasm_memory_pages()
    handles = [sb.spawn_subinterpreter(_SRC_10KB, h) for _ in range(n)]
    after = sb.wasm_memory_pages()
    for handle in handles:
        sb.close_subinterpreter(handle)
    final = sb.wasm_memory_pages()
    delta = after - before
    return [
        f"live_interpreters={n}",
        f"pages_before={before}",
        f"pages_after_spawn={after}",
        f"pages_after_close={final}",
        f"pages_delta={delta}",
        f"kib_per_live_interpreter={delta * 64 // n}",
    ]


@update
def bench_memory_soak(cycles: int) -> Vec[str]:
    """Spawn/close `cycles` subinterpreters with varied allocation patterns;
    report page drift. Zero (or near-zero) drift on repeat calls means close
    fully reclaims the heap."""
    before = sb.wasm_memory_pages()
    sources = [
        "data = [list(range(100)) for _ in range(50)]",
        "s = 'x' * 65536\nparts = [s[i:i+7] for i in range(0, 4096, 7)]",
        "d = {i: str(i) * (i % 13 + 1) for i in range(2000)}",
        "blob = bytearray(200000)",
    ]
    for src in sources:
        _approve(src)
    for i in range(cycles):
        src = sources[i % len(sources)]
        handle = sb.spawn_subinterpreter(src, sb.sha256(src))
        sb.close_subinterpreter(handle)
    after = sb.wasm_memory_pages()
    return [
        f"cycles={cycles}",
        f"pages_before={before}",
        f"pages_after={after}",
        f"pages_delta={after - before}",
        f"kib_drift_per_cycle={(after - before) * 64 // max(cycles, 1)}",
    ]
