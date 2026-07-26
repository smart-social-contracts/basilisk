# Subinterpreter Sandbox Benchmarks

Quantifies the runtime cost of `_basilisk_sandbox` so downstream projects
(e.g. Realms, [realms#244](https://github.com/smart-social-contracts/realms/issues/244))
can decide which workloads to sandbox. Full write-up:
[docs/SANDBOX_BENCHMARKS.md](../../docs/SANDBOX_BENCHMARKS.md). Tracked in
[issue #52](https://github.com/smart-social-contracts/basilisk/issues/52).

Numbers via `ic0.performance_counter` on PocketIC (median of 5 runs).
On the IC, **1 instruction ≈ 1 cycle**. Exclude the fixed per-call fee
(~590K cycles/update, ~260K/query).

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
    of instructions — e.g. a 10 KB JSON transform lands at ~3.5x in-process)
    or when calls are admin/governance-frequency. At ~0.15B cycles per call
    all in, cost per sandboxed extension call is on the order of hundredths
    of a cent.
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

## Run

```bash
pip install ../..          # or: pip install ic-basilisk
icp network start -d
bash run_benchmark.sh      # --runs N, --soak-cycles N, --network ic
```

Or trigger the
[Benchmark workflow](https://github.com/smart-social-contracts/basilisk/actions/workflows/benchmark.yml)
with backend `sandbox`.
