# Subinterpreter Sandbox Benchmarks

Quantifies the runtime cost of the subinterpreter sandbox (`_basilisk_sandbox`,
see [SUBINTERPRETER_AUDIT.md](SUBINTERPRETER_AUDIT.md) and the
[Sandboxing Untrusted Code](../README.md#sandboxing-untrusted-code) section)
so downstream projects can decide which workloads to sandbox. The immediate
consumer is [Realms](https://github.com/smart-social-contracts/realms)
(realms#244): keep core/system extensions in-process, route third-party
extensions and codex rule hooks through the sandbox — *if* the per-call
overhead is acceptable. Tracked in
[issue #52](https://github.com/smart-social-contracts/basilisk/issues/52).

## Methodology

- Suite: [`benchmarks/sandbox/`](../benchmarks/sandbox/), following the
  [`benchmarks/counter/`](../benchmarks/counter/) layout. Run it via the
  [Benchmark workflow](https://github.com/smart-social-contracts/basilisk/actions/workflows/benchmark.yml)
  with backend `sandbox`, or locally with
  `bash benchmarks/sandbox/run_benchmark.sh`.
- All numbers via `ic0.performance_counter(0)` deltas around exactly the
  measured region (median of 5 runs). On the IC, **1 instruction ≈ 1 cycle**
  of compute cost.
- Measured on a local PocketIC replica (icp-cli managed network), template
  artifact `cpython-wasm-3.13.0-ic1`, Basilisk 0.14.2.
- **Fairness:** every sandboxed-vs-in-process comparison runs the *identical
  Python source* on both sides (the in-process twin is `exec`d into a plain
  namespace), so differences isolate the sandbox cost, not implementation
  differences. The extension workload carries its own pure-Python JSON
  parser/serializer because the sandbox (deliberately) has no `json` module —
  exactly what a real self-contained extension would do.
- Metering variants: *unmetered* spawns with `budget=0` (metering disabled;
  the per-dispatch load+branch check still exists), *metered* uses a generous
  budget that never trips. The difference is pure metering bookkeeping.

### Cost context

These numbers exclude the fixed per-call fee — **~590K cycles per update
call** (~260K per query) — and memory/storage costs. Use that fee as the
yardstick for "absolute" overhead: e.g. a 55M-instruction fresh spawn cycle
costs ~93 update fees worth of cycles.

## Results

### 1. Spawn cost vs source size

`spawn_subinterpreter(source, hash)`, source is a synthetic extension backend
(many small handler functions — the typical shape of a 10–50 KB extension
module). Spawn cost includes creating the isolated interpreter *and*
compiling + executing the module body.

| Source size | Instructions per spawn |
|---|---:|
| ~1 KB (1,090 B) | 48,854,495 |
| ~10 KB (10,408 B) | 88,176,854 |
| ~50 KB (51,428 B) | 258,777,859 |

Linear in source size: **~44M fixed + ~4,200 instructions per source byte**
(~4.3M per KB). The fixed part is interpreter creation and bootstrap; the
per-byte part is compiling and executing the module body, so it depends on
what the module body *does* — a module that computes at import time costs
correspondingly more.

### 2. Call overhead (bridge cost)

A noop function called directly vs through `call_in_subinterpreter` on an
already-spawned handle (spawn outside the timer):

| Variant | Instructions |
|---|---:|
| In-process call | 2,426 |
| Sandboxed call | 9,795 |

**The bridge adds ~7,400 instructions per call** — about 1.3% of the ~590K
per-update fee. Once a sandbox is spawned, calling into it is essentially
free.

### 3. Boundary deep-copy scaling

Round-trip of a JSON-like payload (nested dict/list/str records) as kwargs
and result through an `echo` function; size is the JSON-serialized byte count:

| Payload | Instructions | per byte |
|---|---:|---:|
| ~1 KB (1,019 B) | 556,027 | 546 |
| ~10 KB (10,381 B) | 7,015,778 | 676 |
| ~100 KB (106,044 B) | 64,272,505 | 606 |
| ~1 MB (1,107,831 B) | 630,232,345 | 569 |

Linear, as expected: **~600 instructions per JSON-equivalent byte for a full
round-trip** (~300/byte per direction, i.e. ~0.6M instructions per KB
round-tripped). Note the marshaller caps a single crossing at 4 MiB.

### 4. Full fresh-per-use cycle

`sha256` + `approve_hash` + spawn + one noop call + `close_subinterpreter` —
the number a caller pays per sandboxed extension call under the recommended
fresh-per-use (no pooling) pattern:

| Source | Instructions per cycle |
|---|---:|
| Minimal (28 B) | 55,236,622 |
| ~10 KB extension | 101,696,194 |

**Floor: ~55M instructions (~55M cycles, ≈ 93 update-call fees); a realistic
10 KB extension pays ~102M.** Comparing with §1, hash + call + close add
~10M on top of the spawn itself (teardown is the bulk of that).

### 5. Instruction-budget metering overhead

Identical compute-bound source in-process (unmetered by construction) vs
sandboxed with `budget=0` vs sandboxed with a generous budget:

| Workload | In-process | Sandboxed, unmetered | Sandboxed, metered | Metering multiplier |
|---|---:|---:|---:|---:|
| `sum_to(10000)` | 13,246,278 | 13,259,206 | 13,978,898 | **1.05x** |
| `fib(20)` (recursive) | 28,198,421 | 28,211,839 | 31,364,095 | **1.11x** |
| extension workload (§6) | 42,294,795 | 42,425,734 | 46,002,098 | **1.08x** |

Two separate findings:

- **Sandboxed execution itself is free**: unmetered sandbox numbers are
  within 0.1–0.3% of in-process — same bytecode, same interpreter speed.
  All sandbox cost is at the boundaries (spawn, call, copy).
- **Metering costs 5–11%** (the armed per-dispatch counter check), worst for
  call-heavy recursive code, ~5% for arithmetic loops.

### 6. Realistic extension workload

Parse a ~10 KB JSON payload, transform it (dict/list manipulation: filtering,
aggregation, tag counting), serialize the result — approximating a Realms
`extension_sync_call` handler. Identical source both sides (see Methodology):

| Variant | Instructions |
|---|---:|
| In-process | 42,294,795 |
| Sandboxed (handle reused, unmetered) | 42,425,734 |
| Sandboxed (handle reused, metered) | 46,002,098 |
| + fresh-per-use spawn/close of its ~10 KB module (§4) | ~+101,700,000 |

A metered, fresh-per-use sandboxed call of this handler costs
**~148M instructions vs 42M in-process — ~3.5x** — of which the spawn/close
cycle is two thirds.

### 7. Memory footprint

Measured via `wasm_memory_pages()` (64 KiB pages; wasm linear memory is a
high-water mark and never shrinks, but freed heap is reused by malloc):

| Metric | Value |
|---|---:|
| Heap per live subinterpreter (~10 KB source) | **~224 KiB** (3.5 pages) |
| Handle table limit (live at once) | 8 |
| Page drift over 100 spawn/close cycles (pass 1) | 0 pages |
| Page drift over 100 more cycles (pass 2) | 0 pages |

**Close fully reclaims the heap**: after the Phase 4 teardown-leak backport
(see SUBINTERPRETER_AUDIT.md §D5) there is zero per-cycle drift, so
fresh-per-use has no memory argument against it.

### 8. Capability `rpc()` cost

One `rpc()` round-trip through a main-interpreter host handler with a small
payload, measured from `call_sandboxed` of a function that does exactly one
`rpc()`:

| Variant | Instructions |
|---|---:|
| Sandboxed call doing one `rpc()` | 35,490 |
| Sandboxed noop call (§2 baseline) | 9,795 |

**One rpc() round-trip adds ~26K instructions** on top of a plain sandboxed
call (two boundary crossings + the C action gate + handler dispatch), plus
~600 instructions per byte of rpc payload (§3). Tens of rpc calls per
extension call are noise next to the spawn cost.

## Conclusions

- **Sandboxed noop call: ~9.8K instructions** (vs 2.4K in-process; bridge
  cost ~7.4K, ~1.3% of the per-update fixed fee). Compute inside the sandbox
  runs at native interpreter speed (±0.3%).
- **Boundary copy: ~0.6K instructions per JSON-equivalent byte round-trip**
  (~0.6M/KB), linear from 1 KB through 1 MB.
- **Metering multiplier: 1.05–1.11x** on top of an already-spawned sandbox;
  disabled metering is free.
- **Fresh-per-use cycle: ~55M instructions floor + ~4.2K per source byte**
  (~102M for a 10 KB extension). Memory is a non-issue: ~224 KiB per live
  sandbox, fully reclaimed on close, zero drift over repeated cycles.
- **Spawn amortization guidance:**
  - Fresh-per-use is fine when the handler does real work (tens of millions
    of instructions — e.g. the §6 workload lands at ~3.5x in-process) or
    when calls are admin/governance-frequency. At ~0.15B cycles per call all
    in, cost per sandboxed extension call is on the order of hundredths of a
    cent.
  - Fresh-per-use *dominates* for small hot handlers: a trivial handler pays
    ~55–100M instructions of spawn/close for <100K of work (~1000x). For
    high-frequency, low-work hooks (e.g. per-message codex rule checks),
    either batch several evaluations into one spawn, reuse the handle within
    a single update call (per-call bridge cost is only ~10K), or keep those
    hooks in-process at a higher trust tier.
  - For Realms specifically: routing `extension_sync_call`-shaped workloads
    (10 KB payload, JSON transform) through a fresh sandbox costs ~3.5x
    in-process — acceptable for third-party extensions; per-event rule hooks
    that do little work should not be fresh-per-use sandboxed.

## Reproducing

- CI: trigger the
  [Benchmark workflow](https://github.com/smart-social-contracts/basilisk/actions/workflows/benchmark.yml)
  with backend `sandbox` (network `local` or `ic`). Results are uploaded as
  the `benchmark-sandbox-<network>` artifact.
- Locally:

```bash
cd benchmarks/sandbox
pip install ../..          # or: pip install ic-basilisk
icp network start -d
bash run_benchmark.sh      # --runs N, --soak-cycles N, --network ic
```
