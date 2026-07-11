# Subinterpreter-Safety Audit of Basilisk's Compiled-in C Extension Surface

**Phase 1 deliverable** for the subinterpreter-based sandboxing work (untrusted
extensions & rule modules). This report enumerates every C extension module
compiled into Basilisk's CPython build, classifies each as subinterpreter-safe
or not, and estimates the patching effort. No code has been changed for this
phase.

- Pinned interpreter: **CPython 3.13.0** (`build_cpython_wasm.sh`,
  `CPYTHON_VERSION="3.13.0"`), cross-compiled to `wasm32-wasip1`.
- Audited sources: the pinned CPython 3.13.0 tree, Basilisk's custom module
  table `basilisk/compiler/basilisk_cpython/src/cpython_config.c`, the trimmed
  archive logic in `basilisk/compiler/basilisk_cpython/build.rs`, the link-time
  stubs in `basilisk/compiler/basilisk_cpython/src/wasm_stubs.rs`, and the
  Rust-created `_basilisk_ic` module in
  `basilisk/compiler/cpython_canister_template/src/ic_api.rs`.

## 1. How the extension surface is determined

The set of importable C extensions is exactly the `_PyImport_Inittab` array in
`cpython_config.c` — Basilisk replaces CPython's stock `config.o` with this
file at build time, and there is no dynamic module loading on the IC
(`dynload_shlib.o` is deleted from the archive). This makes the audit **closed
and complete**: nothing outside the table below can ever be imported as a C
extension in a canister.

Note: `zlibmodule.o` remains in the trimmed archive (and `libz.a` is linked)
but `zlib` is *not* in the inittab, so it is unreachable dead weight, not an
isolation concern (it is multi-phase upstream anyway).

## 2. Background: what "subinterpreter-safe" means here

CPython 3.13 distinguishes:

- **Single-phase init** (`m_size = -1`, module created inside `PyInit_*` via
  `PyModule_Create`): the module object and its dict are created once and
  cached in `PyModuleDef.m_base.m_copy`; any C statics are process-global.
  These modules can leak state across interpreters.
- **Multi-phase init** (PEP 489: `PyInit_*` returns `PyModuleDef_Init(&def)`,
  state in `m_size > 0` per-module memory, slots incl.
  `Py_mod_multiple_interpreters`): a fresh module object with fresh state is
  created per interpreter.

Critically, CPython 3.13 is **fail-closed**: when a subinterpreter is created
with `check_multi_interp_extensions = 1` (mandatory when the interpreter has
its own obmalloc — enforced in `pylifecycle.c:init_interp_settings`), importing
a single-phase module raises `ImportError` instead of sharing state. So an
unsafe module in the table below cannot silently break isolation; it breaks
*functionality* inside the sandbox until converted.

## 3. Module-by-module audit

### 3.1 Stock CPython 3.13.0 modules — all SAFE as-is

All sixteen stock modules in the inittab use PEP 489 multi-phase init and
explicitly declare `{Py_mod_multiple_interpreters,
Py_MOD_PER_INTERPRETER_GIL_SUPPORTED}` in the pinned 3.13.0 source. State is
either absent (`m_size = 0` with per-interpreter state reached via
`PyInterpreterState`, e.g. `gc`) or per-module (`m_size = sizeof(state)`).

| Module | Source file | `m_size` | State location | Verdict |
|---|---|---|---|---|
| `_io` | `Modules/_io/_iomodule.c` | `sizeof(_PyIO_State)` | per-module | safe |
| `_abc` | `Modules/_abc.c` | `sizeof(_abcmodule_state)` | per-module | safe |
| `_codecs` | `Modules/_codecsmodule.c` | 0 | per-interpreter (codec registry on `PyInterpreterState`) | safe |
| `_functools` | `Modules/_functoolsmodule.c` | `sizeof(_functools_state)` | per-module | safe |
| `_stat` | `Modules/_stat.c` | 0 | stateless | safe |
| `_string` | `Objects/unicodeobject.c` | 0 | stateless | safe |
| `_struct` | `Modules/_struct.c` | `sizeof(_structmodulestate)` | per-module | safe |
| `_typing` | `Modules/_typingmodule.c` | 0 | per-interpreter | safe |
| `_weakref` | `Modules/_weakref.c` | 0 | stateless | safe |
| `atexit` | `Modules/atexitmodule.c` | 0 | per-interpreter (`interp->atexit`) | safe |
| `errno` | `Modules/errnomodule.c` | 0 | stateless (constants) | safe |
| `gc` | `Modules/gcmodule.c` | 0 | per-interpreter (`get_gc_state()`) | safe |
| `_json` | `Modules/_json.c` | per-module | per-module | safe |
| `marshal` | `Python/marshal.c` | per-module | per-module | safe |
| `_imp` | `Python/import.c` | 0 | per-interpreter import state | safe |
| `_warnings` | `Python/_warnings.c` | 0 | per-interpreter (`interp->warnings`) | safe |

Core-runtime globals these rely on (static builtin types, small-int cache,
interned strings) are immortal/immutable by design in 3.13 and are the
supported sharing model for subinterpreters — not an isolation gap for our
threat model (Python code cannot mutate them in ways visible across
interpreters, aside from denial-of-service-style resource use which metering
bounds).

### 3.2 Basilisk-authored stub modules (`cpython_config.c`) — all currently UNSAFE (single-phase)

These six stubs replace deleted CPython `.o` files. All are single-phase
(`m_size = -1`, created via `PyModule_Create` inside `PyInit_*`). Under the
isolated config they will be **refused at import** in a subinterpreter — and
several are imported by stdlib modules sandboxed code will realistically use
(`os` → `posix`, `re` → `_sre`, `collections` → `_collections`, `operator` →
`_operator`, `threading`/importlib internals → `_thread`, early runtime →
`_signal`). They must be converted to PEP 489 multi-phase init.

| Module | C-global state | Risk if left single-phase | Conversion effort |
|---|---|---|---|
| `posix` | `static PyTypeObject *StatResultType` (heap type created in `PyInit_posix`, stored in a C static) | Type object created by the main interpreter would be re-created/overwritten on each init; instances would cross interpreter heaps at teardown | **~0.5 day.** Move `StatResultType` into per-module state (`m_size = sizeof(state)`, `PyStructSequence_NewType` in `Py_mod_exec`, add `m_traverse`/`m_clear`/`m_free`) |
| `_thread` | `static PyTypeObject _thread_lock_type` (a **static type** — `tp_subclasses`, `tp_mro` cache etc. are process-global) | Static extension types are exactly the PEP 554 leak class; also refused under isolated config | **~1 day.** Convert to a heap type via `PyType_FromSpec` in `Py_mod_exec`, stored in per-module state. Caveat: an existing comment says `PyType_FromSpec` "corrupts interpreter state during early init" — that was observed during main-interpreter bootstrap; with multi-phase init the exec slot still runs during importlib bootstrap, so this needs an explicit test. Fallback: keep the static type for the main interpreter and create per-interpreter heap types lazily |
| `_signal` | none (empty method table), but note the *internal* C stubs beside it (`PyErr_CheckSignals` etc.) are stateless functions — fine | Import refusal only | **~30 min.** Mechanical multi-phase conversion (`m_size = 0`, add slots) |
| `_operator` | none | Import refusal only (breaks `operator`, and thus much of the stdlib) | **~30 min.** Mechanical |
| `_collections` | none | Import refusal only (breaks `collections`) | **~30 min.** Mechanical |
| `_sre` | none | Import refusal only (breaks `re`) | **~30 min.** Mechanical |

All six conversions should also declare
`{Py_mod_multiple_interpreters, Py_MOD_PER_INTERPRETER_GIL_SUPPORTED}` so the
import system accepts them in isolated interpreters.

### 3.3 `_basilisk_ic` (Rust, `ic_api.rs`) — UNSAFE by construction, and must stay out of the sandbox

- Single-phase: `MODULE_DEF.m_size = -1`, built with `PyModule_Create` from
  `static mut METHODS: [PyMethodDef; 77]` and `static mut MODULE_DEF`, then
  manually inserted into the **main interpreter's** `sys.modules`.
- It is the entire privileged host surface: stable-memory access
  (`smap_*`/`sset_*`/`svec_*`/…), `ic.caller()`, `ic.reply()`, timers,
  cross-canister calls.

**Verdict: do not convert; deliberately withhold.** The sandbox design requires
that subinterpreters *never* see `_basilisk_ic` — privileged operations go
through the host-validated `rpc()` stub instead. Its single-phase init is
actually a defense-in-depth here: even if sandboxed code tries
`import _basilisk_ic`, the isolated-config import check refuses it. It is
registered only by direct `sys.modules` insertion in the main interpreter, and
`sys.modules` is per-interpreter, so a fresh subinterpreter does not inherit
it. Phase 6 must include a test asserting `import _basilisk_ic` fails inside
the sandbox.

### 3.4 Other C-level state examined

| Item | Assessment |
|---|---|
| `basilisk_initialized` static in `cpython_init_helper.c` | Host-process init flag, guards `Py_InitializeFromConfig` only — orthogonal to subinterpreters, fine |
| Rust statics in the canister template (`INTERPRETER_OPTION`, `SCOPE_OPTION`, `PRINCIPAL_CLASS_OPTION`, `METHOD_METADATA`, `TIMER_CB_COUNTER`, `CURRENT_RETURN_TYPE`) | Host-side singletons holding *main-interpreter* objects. Safe as long as the sandbox binding never passes them into a subinterpreter — enforced by the plain-data-only RPC boundary in Phase 3 |
| `PyImport_FrozenModules` global (frozen `encodings` bytecode) | Shared read-only table of marshalled code objects; each interpreter unmarshals its own module objects — safe |
| `wasm_stubs.rs` (137 `#[no_mangle]` link stubs for `_decimal`/`pyexpat`/HACL/etc.) | Stateless no-ops for symbols in `.o` files that are never importable — safe |
| `-DPYTHONHASHSEED=0`, determinism patch | Process-wide, identical for all interpreters — safe and desirable (deterministic replicas) |

## 4. Runtime feasibility on the pinned build (flags & caveats)

1. **C-API availability — confirmed.** `Py_NewInterpreterFromConfig`,
   `PyInterpreterConfig`, `Py_EndInterpreter`, and `PyThreadState_Swap` all
   exist in the pinned 3.13.0 headers (`Include/cpython/pylifecycle.h`). No
   dependency on the provisional stdlib `interpreters`/`_interpreters` module
   is needed or wanted.
2. **Recommended spawn config** (variant of `_PyInterpreterConfig_INIT`):
   `use_main_obmalloc = 0`, `allow_fork = 0`, `allow_exec = 0`,
   `allow_threads = 0`, `allow_daemon_threads = 0`,
   `check_multi_interp_extensions = 1`, `gil = PyInterpreterConfig_OWN_GIL`.
   Note `use_main_obmalloc = 0` *forces* `check_multi_interp_extensions = 1`
   (enforced in `init_interp_settings`), which is exactly the fail-closed
   behavior we want. The build is `--without-pymalloc`, so "own obmalloc"
   degrades to plain `malloc` — still correct; `Py_EndInterpreter` frees the
   interpreter's allocations back to malloc (wasm linear memory does not
   shrink, but pages are reused).
3. **Single-threaded WASI is not a problem.** Subinterpreters do not require
   OS threads — only `PyThreadState` swapping on the one existing thread. The
   `_thread` stub's fake locks are consistent with `allow_threads = 0`.
4. **Sandbox environment bootstrap.** A fresh subinterpreter gets its own
   `sys.modules` and does *not* inherit the main interpreter's frozen-stdlib
   preamble (`json` fallback etc.), the `basilisk` shim, or the persistent-file
   `open()` wrapper. Phase 2/3 must decide the minimal environment to
   re-initialize inside the sandbox (at minimum: the `rpc()` stub and a
   `json`-capable environment for plain-data results). Not inheriting the
   shims is a feature — the sandbox should not get `basilisk.ic`.
5. **No existing ceval.c performance patch.** The task brief assumes Basilisk
   "already modifies" the `ceval.c` dispatch loop; it does not. The only
   IC patch today is `patches/0001-ic-determinism.patch`, which touches
   `Python/bootstrap_hash.c` and is comment-only. Phase 4's instruction
   metering will be the **first functional interpreter-core patch**, added as
   a new file in `basilisk/compiler/cpython/patches/` and applied by the
   existing `apply_ic_patches` mechanism. Two follow-ups this implies:
   - `apply_ic_patches` currently runs `git apply "${patch_file}" || true` —
     failures are silent. Before a load-bearing patch lands, this must become
     fatal (or at least verify the patch applied).
   - Metering requires rebuilding `libpython3.13.a` and republishing the
     prebuilt artifact; canister-template-only changes are not sufficient for
     Phase 4 (they are for Phases 2/3/5).
6. **Where the sandbox binding should live.** The natural home is a new C
   file beside `cpython_config.c` compiled into the trimmed archive step (or
   the init-helper static lib), exposed to Rust via `ffi.rs`, with the
   spawn/close/run API surfaced through `basilisk_cpython::` and a
   `_basilisk_sandbox` inittab entry for the *main interpreter only*.

## 5. Summary of required patching work (input to Phase 2)

| Work item | Effort |
|---|---|
| Convert `_signal`, `_operator`, `_collections`, `_sre` stubs to multi-phase | ~2 h total, mechanical |
| Convert `posix` stub to multi-phase with per-module `stat_result` type | ~0.5 day |
| Convert `_thread` stub to multi-phase with heap `lock` type (early-init caveat to verify) | ~1 day |
| Keep `_basilisk_ic` single-phase and main-interpreter-only; add sandbox test that its import fails | trivial (test in Phase 6) |
| Make `apply_ic_patches` fail loudly on patch failure | ~15 min |
| Stock CPython modules | none |

**Bottom line:** the isolation gap in this build is confined to six
Basilisk-authored stub modules (all small, all in one file we own) and the
deliberately-privileged `_basilisk_ic`. CPython 3.13.0's fail-closed
multi-interp import check means none of them can *silently* leak state — the
work is converting the six stubs so the sandbox is functional, not plugging
silent leaks. Total estimated conversion effort: **~2 days** including tests.

---

# Addendum (Step 0.2): Sandbox stdlib bootstrap

Answers to the pre-Phase-2 questions: what is importable inside an isolated
subinterpreter on this build, where module source comes from, and the minimal
per-spawn bootstrap. Verified by code trace against the pinned 3.13.0 source
and, where possible, empirically against a native build of the same pinned
tag (single-phase refusal and multi-phase import success confirmed; the
native `_interpreters` module was used only as a *test harness*, not as a
product dependency).

## A. Where Python-level modules come from on this build

There are exactly three sources, with very different subinterpreter behavior:

1. **The frozen-module table compiled into `libpython3.13.a`**
   (`PyImport_FrozenModules`, a process-global read-only table — visible to
   **all** interpreters). Stock 3.13.0 freezes: the importlib bootstrap,
   `zipimport`, `abc`, `codecs`, `io`, `_collections_abc`, `_sitebuiltins`,
   `genericpath`, `ntpath`, `posixpath`, `os`, `os.path`, `site`, `stat`,
   `importlib.util`, `importlib.machinery`, `runpy`. In addition, Basilisk's
   build freezes the **entire `encodings` package** — this modification
   existed only as uncommitted edits in the cached source tree and is now
   captured as `patches/0002-freeze-encodings.patch` (plus
   `0003-codecs-tolerate-missing-encodings.patch`); see Step 0.1 notes below.
2. **`frozen_stdlib_preamble.py`** — ~3,100 lines executed at canister init
   into the **main interpreter's `sys.modules` only**. Provides handwritten
   pure-Python versions of `json`, `random`, `time`, `datetime`, `itertools`,
   `typing`, `enum`, `collections`, `dataclasses`, `functools`, `traceback`,
   `uuid`, `hashlib`, `base64`, `math`, `secrets`, `__future__`, an enhanced
   `os`, and a `_wasi_safe_import` hook that stubs any other missing stdlib
   name. **None of this exists in a fresh subinterpreter**, and it must stay
   that way: the preamble also wires `basilisk`, `_basilisk_ic` fallbacks,
   and the persistent-file `open()` wrapper. **Invariant, not gap:** the
   sandbox never re-runs the preamble or the basilisk shim.
3. **The memfs** (ic-wasi-polyfill virtual filesystem) via importlib's
   `PathFinder` — per-interpreter `sys.path`. Persistent files hold
   application state, so the sandbox must never see them. **Invariant:** the
   spawn primitive sets `sys.path = []` (and leaves `path_hooks` harmless) in
   every subinterpreter before user code runs.

## B. Two spawn-blocking findings (hard prerequisites, discovered by trace)

`Py_NewInterpreterFromConfig` → `new_interpreter()` runs `pycore_interp_init`
and then `init_interp_main` **unconditionally** (it does not honor the
`_init_main = 0` trick the main interpreter uses to skip main-init on WASI).
Three consequences:

1. **`_thread` blocks interpreter creation.** `pycore_interp_init` runs the
   frozen `importlib._bootstrap._setup()`, which imports the builtins
   `_thread`, `_warnings`, `_weakref` with **no ImportError fallback**
   (verified in pinned `Lib/importlib/_bootstrap.py`). `_warnings`/`_weakref`
   are stock multi-phase; `_thread` is our single-phase stub → refused →
   spawn fails.
2. **`posix` blocks interpreter creation.** `init_interp_main` →
   `_PyImport_InitExternal` executes the frozen
   `importlib._bootstrap_external`, whose module body does
   `import posix as _os` (verified, line 38). Single-phase stub → refused →
   spawn fails. (Only module-level attribute access is needed at spawn time;
   the existing nine stub functions are sufficient once the module itself is
   importable.)
3. **Frozen `encodings` is required.** `init_interp_main` →
   `_PyUnicode_InitEncodings` → `init_fs_encoding` → `_PyCodec_Lookup("utf-8")`
   requires the `encodings` package importable *in the new interpreter*. No
   filesystem → the frozen table is the only possible source. This is why
   patch `0002-freeze-encodings.patch` is a hard prerequisite for Phase 2,
   not housekeeping.

**Impact on conversion order:** the agreed order (mechanical four → `posix` →
`_thread`) stands, but end-to-end spawn cannot be smoke-tested until `posix`
and `_thread` are converted. The mechanical four can be validated indirectly
(main-interpreter regression + unit inspection) in the meantime.

## C. What is importable inside an isolated subinterpreter

After the six conversions land:

| Category | Modules | Status in sandbox |
|---|---|---|
| Multi-phase C builtins | the 16 stock modules (§3.1) + 6 converted stubs | importable |
| Frozen pure-Python | `abc`, `codecs`, `io`, `os`, `os.path`/`posixpath`, `stat`, `encodings.*`, `importlib.util`/`.machinery`, `runpy`, `site`, `zipimport` | importable (`os` only after `posix` conversion) |
| Preamble-provided (`json`, `collections`, `functools`, `dataclasses`, `datetime`, `traceback`, …) | main interpreter only | **not importable** unless explicitly injected per spawn |
| `decimal` | absent everywhere (`_decimal.o` deleted, `_pydecimal` not shipped) | not available (matches main interpreter) |
| `re` | see flag below | **not functional even after `_sre` stub conversion** |

**Flag — `re` cannot work by stub conversion alone.** The `_sre` stub has an
*empty* method table; converting it to multi-phase makes `import _sre`
succeed but `re` needs a real regex engine (`_sre.compile` etc.) plus the
pure-Python `re` package source (~220 KB, not frozen, not in the preamble).
Today `re` is a nonfunctional empty stub **even in the main interpreter**.
Making the Phase 2 "import re succeeds" test meaningful requires restoring
`sre.o` (+~334 KB wasm — risky against the ~3.8 MB DTS install ceiling with a
current binary of ~3.73 MB) and freezing `re`'s Python source. Decision
needed at the Phase 2 stop point; until then the test will assert the
*import-refusal is gone*, not that regex works.

## D. Minimal per-spawn bootstrap (recommendation for the spawn primitive)

1. Create the interpreter with the fixed isolated config (§4.2). Do not make
   the config caller-configurable.
2. Immediately, from the host, in the new interpreter: `sys.path = []`
   (isolation invariant A.3), and leave `sys.modules` untouched (it is
   already minimal).
3. Inject the `rpc` callable as a C builtin closed over a host-side context
   id — the capability descriptor itself stays in host memory and is never
   represented as a sandbox object.
4. Pass arguments/results as **plain data materialized via the C API**
   (host walks its validated JSON-safe structure and builds
   dict/list/str/int/float/bool/None objects inside the target interpreter).
   This avoids needing `json` inside the sandbox at all and keeps the
   plain-data-only boundary enforced in one place. If sandbox code itself
   wants `json`, that becomes an explicit, capability-gated source injection
   later — not part of the minimal bootstrap.
5. Nothing else. No preamble, no shim, no `open()` wrapper, no `_basilisk_ic`
   (its absence is enforced both by per-interpreter `sys.modules` and by the
   single-phase import refusal).

## D2. Determinism dependency check (Step 0 follow-up)

Requested question: did anything silently depend on determinism that the
broken `0001-ic-determinism.patch` was believed to provide?

**Findings:**

1. **The broken patch had zero functional impact** — it was comment-only, so
   whether it applied or not never changed a compiled byte.
2. **The other advertised mechanism was also a no-op.** The build passed
   `-DPYTHONHASHSEED=0` in CFLAGS, but no C source in CPython reads a macro
   of that name — `PYTHONHASHSEED` exists only as an environment variable
   (`initconfig.c:config_get_env`), and the isolated config ignores the
   environment entirely (`use_environment = 0`). So *neither* advertised
   determinism mechanism ever did anything.
3. **Cross-replica determinism nevertheless held in practice — by accident.**
   The isolated config defaults to `use_hash_seed = 0` ("draw a random
   seed"), which on wasm32-wasip1 resolves to `getentropy()` → WASI
   `random_get` → ic-wasi-polyfill's RNG. That RNG is
   `StdRng::from_seed([0u8; 32])` — a fixed zero seed at canister start —
   and the `raw_rand()`-based reseed only lands asynchronously *after*
   canister init, while CPython's hash secret is drawn *during* init. Every
   replica (and every upgrade) therefore derived the same hash secret from
   the same fixed sequence. Deterministic, but hinging on a polyfill
   implementation detail nobody had written down.
4. **Fix applied:** determinism is now by-construction, not by accident —
   `cpython_init_helper.c` sets `use_hash_seed = 1, hash_seed = 0`, which
   zeroes `_Py_HashSecret` by specification. The no-op `-DPYTHONHASHSEED=0`
   flag was removed from the build script (with an explanatory comment), and
   `0001-ic-determinism.patch` was regenerated to document the real
   mechanism.
5. **Dependents found:** one real one.
   `realms/codices/codices/syntropia/quarter_assignment.py` uses
   `hash(principal) % len(quarters)` for its "random" quarter-assignment
   strategy — this directly depends on the str-hash secret. It was stable
   under the accidental determinism. **Migration note:** zeroing the hash
   secret changes `hash(str)` values once; if any deployment persisted
   assignments *and* recomputes them via `hash()` for verification, the
   recomputation will disagree after the next template rebuild. Assignments
   that are persisted at join time and never recomputed are unaffected.
   Nothing in `basilisk`, `ic-basilisk-toolkit` (which ships its own
   xorshift64 PRNG precisely to avoid this class of dependency), or
   `geister` reads `PYTHONHASHSEED` or otherwise depends on str-hash values.
6. **Known property, not a regression:** with a fixed hash secret,
   `str`/`bytes` hashing is predictable, so attacker-controlled dict keys
   can be crafted to collide (hash-flooding). This is inherent to
   deterministic replicated execution (any fixed seed has this property,
   and the accidental zero-seeded StdRng was equally predictable). Phase 4
   instruction metering is the mitigation for sandboxed code.

## D3. Tracked follow-up — `re`/`sre.o` (decision: deferred)

Restoring functional regex in the sandbox (and main interpreter) requires
re-adding `sre.o` (~334 KB against the ~3.8 MB DTS install ceiling; current
binary ~3.73 MB) plus freezing the pure-Python `re` package. **Decision
(Phase 1 review):** do not spend the budget speculatively. Revisit once a
real inventory of extensions exists and demonstrates need. Until then, the
`_sre` stub stays functionally empty (its PEP 489 conversion below is
structural only) and Phase 2's `re` test asserts only that the
subinterpreter import *refusal* is gone.

## D4. Phase 2a record — all six stub conversions landed (PEP 489 multi-phase)

All six Basilisk-authored stubs in `cpython_config.c` (§3.2) are now
multi-phase with `{Py_mod_multiple_interpreters,
Py_MOD_PER_INTERPRETER_GIL_SUPPORTED}` declared:

- **Mechanical four** (`_signal`, `_operator`, `_collections`, `_sre`):
  `m_size = 0`, shared stateless slot table, `PyModuleDef_Init` return.
- **`posix`**: `StatResultType` moved from a C static into per-module state
  (`m_size = sizeof(posix_state)`), created via `PyStructSequence_NewType`
  in `Py_mod_exec`, with `m_traverse`/`m_clear`/`m_free`. `stat`/`lstat`
  reach the type through `PyModule_GetState(self)`.
- **`_thread`**: clean heap-type conversion — `PyType_FromSpec` in
  `Py_mod_exec`, type stored in per-module state. **The audit's flagged
  early-init risk did not reproduce**, so the fallback (static type for the
  main interpreter) was not needed. Explanation: the historical "corrupts
  interpreter state during early init" observation dated from experiments
  where the type was readied *inside `PyInit__thread` itself* during
  main-interpreter bootstrap under the old init sequence. Under multi-phase
  init, `Py_mod_exec` runs via importlib's module-execution machinery, by
  which point the type machinery is fully initialized — in the main
  interpreter and in every subinterpreter. Verified in the most adversarial
  way available (below).

### Verification

1. **Host-embedded harness** (`tests/subinterp_harness/`, run by
   `tests/test_subinterpreter_stubs.py`; skips if the host libpython is
   absent): compiles the *real* `cpython_config.c` (symbol-renamed via
   `-include host_rename.h`) against a native `libpython3.13.a` from the
   same pinned+patched tree, **deletes the real `_threadmodule.o`** from the
   archive so importlib's early-init `import _thread` — in the main
   interpreter and every subinterpreter — resolves to Basilisk's stub, and
   creates subinterpreters with the exact sandbox `PyInterpreterConfig`
   (own GIL, own obmalloc, `check_multi_interp_extensions = 1`). 9/9 checks
   pass:
   - all six stubs import inside the isolated subinterpreter;
   - `_thread`'s heap type works there (locks allocate, context-manager
     protocol works);
   - `posix.stat_result` and `_thread.LockType` are **distinct type
     objects** per interpreter — the isolation leak is gone;
   - a deliberately single-phase negative-control module is **refused**
     with `ImportError`, proving the conversions are load-bearing;
   - 100 spawn/teardown cycles with per-module state, no crash.
2. **Real wasm canister**: the canister template was rebuilt with the
   converted stubs (`cargo build --target wasm32-wasip1 --release` +
   `wasi2ic`), deployed to a local PocketIC replica, and exercised:
   - `counter` fixture: deploys, increments — proves main-interpreter boot
     on wasm with all six multi-phase stubs, including `_thread`'s
     `PyType_FromSpec`-in-exec during main-interpreter bootstrap (the exact
     scenario the old warning comment described);
   - `filesystem` fixture: all six `test_fs_*` methods pass — proves the
     per-module-state `posix` (`stat`/`mkdir`/`listdir`/`rename`/`rmdir`/
     `unlink` against the WASI polyfill memfs) end to end.

Subinterpreter import tests on *wasm* (as opposed to the host harness)
require the spawn primitive and land with it in Phase 2b.

## D5. Phase 2b record — spawn/teardown primitive landed

`_basilisk_sandbox` (new C file `basilisk_sandbox.c` beside
`cpython_config.c`, compiled into the trimmed archive by `build.rs`,
declared in `ffi.rs`, registered in the inittab) implements the agreed API:

- `spawn_subinterpreter(source_code, content_hash) -> handle` — computes
  sha256 of the source with a local FIPS 180-4 implementation (no _hashlib
  in this build), refuses on mismatch (`PermissionError`) or on a hash not
  in the approved registry, then creates the subinterpreter with the
  audit-mandated config (`use_main_obmalloc=0`, fork/exec/threads/daemon
  all 0, `check_multi_interp_extensions=1`, own GIL — invariants documented
  in the file header), empties `sys.path`, and executes the source in a
  fresh namespace. Sandbox exceptions cross back as TEXT only.
- `close_subinterpreter(handle)` — full teardown, fresh-per-call, no
  pooling.
- `approve_hash` / `revoke_hash` / `sha256` / `wasm_memory_pages` helpers.
- Main-interpreter-only: the module's `Py_mod_exec` slot refuses to
  initialize in a subinterpreter, so sandboxed code can neither nest
  spawns nor touch the registry.

Enabler fix: main-interpreter init previously stopped before
`_Py_InitializeMain` (`_init_main = 0` — a workaround for the WASI path-
config hang and the then-missing `encodings`). `Py_NewInterpreterFromConfig`
refuses to run before main init completes ("Py_Initialize must be called
first"), so `cpython_init_helper.c` now runs full init with
`module_search_paths_set = 1` (skips the hanging path computation; frozen
encodings from patch 0002 satisfy the rest). The `counter` and `filesystem`
fixtures were re-verified on the full-init template.

### Verification

- Host harness: 15/15 (sha256 known-answer vectors; unapproved/mismatched/
  malformed hash refusal; spawn+close happy path with case-insensitive hash
  normalization; sandboxed exception as plain text; `sys.path == []`;
  `_basilisk_sandbox` NOT importable inside a sandbox; double-close raises).
- On-wasm fixture (`tests/fixtures/subinterpreter`, integration test
  `tests/integration/test_subinterpreter.py`): all PASS —
  hash gating; compute-in-sandbox; error-as-text; **`import _basilisk_ic`
  fails in the sandbox** (the design's key invariant, landed with the spawn
  primitive as required); `basilisk` shim and `_basilisk_sandbox` also
  refused; all six converted stubs import inside the sandbox on wasm.

### Memory soak results (report-only, as agreed)

500 spawn/close cycles with varied allocation patterns, measured via
`wasm_memory_pages()` (64 KiB pages; linear memory never shrinks):

| run | pages before | pages after | Δ pages | ≈ per cycle |
|---|---|---|---|---|
| 1 (cold) | 159 | 685 | 526 | ~67 KiB |
| 2 | 685 | 1256 | 571 | ~73 KiB |
| 3 | 1256 | 1826 | 570 | ~73 KiB |
| 4 | 1826 | 2397 | 571 | ~73 KiB |

The growth is **linear, not a plateau**: ~1.1 pages (~70 KiB) ratchets per
spawn/close cycle.

**Diagnosis — upstream CPython bug, not Basilisk code.** Reproduced on the
host build: ~394 KiB and exactly **2730 obmalloc blocks leak per cycle**,
identical for a bare `Py_NewInterpreterFromConfig`/`Py_EndInterpreter` pair
with no Basilisk stubs involved, and identical on **stock** CPython 3.13.0
(`test.support.run_in_subinterp_with_config`, both own- and
shared-obmalloc). LeakSanitizer attributes the bytes to obmalloc arenas and
arena radix-tree nodes: interpreter finalization leaves ~2.7k blocks alive
(known upstream per-interpreter finalization leaks, e.g. gh-140301 PyConfig
leak, fixed in later 3.13.x/3.14), and
`_PyInterpreterState_FinalizeAllocatedBlocks` deliberately leaks the whole
arena set when any block survives ("safer to not free and to leak",
`Objects/obmalloc.c`). Probe: `tests/subinterp_harness/leak_probe.c`.

**Consequences for the design:**

1. At ~70 KiB/cycle, ~15k sandbox calls cost ~1 GiB of canister heap that
   is never returned within a canister lifetime (heap resets on upgrade).
   Fine for admin-frequency extension installs; NOT fine for
   high-frequency rule evaluation.
2. This answers the question the soak was commissioned for: as things
   stand, **pooling/reuse is a memory argument, not just latency**.
3. Preferred remediation before resorting to pooling: bump/backport — the
   pinned 3.13.0 is the oldest 3.13; later 3.13.x releases carry the
   subinterpreter-teardown leak fixes. The now-fail-loud patch pipeline can
   carry cherry-picked fixes as `0004+` patches if a full version bump is
   too invasive.
   **Decision (Phase 2 review): folded into Phase 4, not a separate
   phase.** The upstream teardown-leak fix lands as
   `0004-teardown-leak-fix.patch` (follow-on hunks as `0005+`) via
   `apply_ic_patches`, in the SAME `libpython3.13.a` rebuild/artifact
   publish as the metering hook; `leak_probe.c` re-runs as part of Phase 4
   verification alongside the metering tests.

### Phase 4 update — leak backport landed, leak closed

Three upstream 3.13-branch commits were cherry-picked (as patches, applied
to the pinned v3.13.0 tree via `apply_ic_patches`):

| patch | upstream | what it fixes |
|---|---|---|
| `0004-teardown-leak-pyconfig.patch` | gh-140301 (a615fb4) | `PyInterpreterState_Delete` never called `PyConfig_Clear(&interp->config)` — leaked the interp's `PyConfig` strings each teardown. |
| `0005-teardown-leak-module-ref.patch` | gh-144307 (219b7ac) | `finalize_remove_modules` leaked the module-dict key on the `value == NULL` error path. |
| `0006-teardown-leak-interned-strings.patch` | gh-113993 family | `_PyUnicode_ClearInterned` only demoted immortal interned strings back to mortal under `Py_DEBUG`; in release builds every interned string (dominated by code-object names interned via `marshal` during frozen imports) stayed immortal and leaked its whole obmalloc arena set at teardown. Backport demotes unconditionally for **non-main** interpreters (main keeps stock behavior to preserve the documented re-init caveat). |

Root cause confirmed by LeakSanitizer (`PYTHONMALLOC=malloc`): before the
backport the dominant leak stack was `PyUnicode_New → _PyUnicode_FromUCS1 →
r_object (marshal) → unmarshal_frozen_code` — i.e. interned frozen-module
code strings surviving finalization, which made
`_PyInterpreterState_FinalizeAllocatedBlocks` leak the arenas.

**Re-measured with `leak_probe.c` (host, patched build):**

| variant | before | after |
|---|---|---|
| bare spawn/end | 394 KiB/cycle, 2762 blocks | **86 B/cycle, 0 blocks** |
| + empty source | 394 KiB/cycle | **~0 B/cycle, 0 blocks** |
| + allocations | 394 KiB/cycle | **~0 B/cycle, 0 blocks** |
| + import _thread | 394 KiB/cycle | **0 B/cycle, 0 blocks** |
| + import sys | 394 KiB/cycle | **~0 B/cycle, 0 blocks** |

**Re-measured on-wasm (`test_memory_soak`, 200 spawn/close cycles, patched
`cpython-wasm-3.13.0-ic1` artifact):**

| metric | pre-backport (Phase 2) | post-backport (Phase 4) |
|---|---|---|
| pages before | 159 | 160 |
| pages after | 685 → 2397 (linear ratchet) | **160** |
| pages Δ | ~1.1 pages/cycle (~70 KiB) | **0** |
| high-water MiB | grew each run | **10** (stable) |

Zero obmalloc blocks survive teardown now, so the arena set is freed
normally. The residual ≈86 bytes on the first-measured variant is
noise-level, non-accumulating malloc bookkeeping (near-zero and sometimes
negative on later variants), not a per-cycle ratchet. **Pass criterion
met**: at ~0 B/cycle there is no 1 GiB heap growth under any realistic
call volume; pooling is no longer a memory argument. ASan still reports a
one-time ~148 KiB of interned strings retained through `Py_Finalize` (the
main interpreter's, deliberately, per the caveat above) — a fixed cost, not
per-cycle.

## D6. Phase 3 record — capability descriptor, intersection, rpc(), marshalling

### Capability descriptor and intersection (host-side Python)

`basilisk/compiler/custom_modules/basilisk/sandbox.py` (canister-side
`basilisk.sandbox`, MAIN interpreter only — the `basilisk` shim is never
importable inside a sandbox, re-verified by the Phase 2 isolation tests):

- Descriptor: plain-data dict `{"context_id", "classes": {name: "read" |
  "read_write"}, "allowed_actions": [str]}` — JSON round-trip covered by a
  unit test.
- `intersect_class_scopes(extension_scope, caller_permissions)` implements
  the exact agreed rules: pairwise `min(read=1, read_write=2)`, and a class
  absent from **either** side is omitted entirely (absence ≠ read, no
  fallthrough). Invalid access strings raise `ValueError`.
- `build_capability(manifest, caller_permissions, context_id)` also
  intersects `allowed_actions` as a set intersection.
- The five required cases are covered twice: host-side pytest
  (`tests/test_capability_intersection.py`, 12 tests, in the unit CI job)
  and on-wasm (`test_capability_intersection` endpoint, asserted per-case
  by `tests/integration/test_subinterpreter.py`).

### Plain-data marshaller (the single enforcement point)

`basilisk_sandbox.c` gained a C marshaller (`pd_encode`/`pd_decode`):
objects are encoded to a raw-malloc byte buffer with the source interpreter
active and decoded into brand-new objects with the target interpreter
active — no `PyObject*` ever crosses, in either direction, and the sandbox
needs no `json` module. Accepted types: `None`, `bool`, `int` (64-bit,
larger rejected), `float`, `str`, `list`/`tuple` (→ `list`), `dict` with
`str` keys. Limits: depth 32, 4 MiB per crossing. Rejections carry the
offending **type name only** — never `repr()` of the value, so a rejection
message cannot itself leak host data.

### rpc() stub

- Injected at spawn into the sandbox's own `__builtins__` as a
  `PyCFunction` closed over the handle index (the handle carries
  `context_id`, `allowed_actions`, and the main-interpreter handler —
  all host-side C state the sandbox cannot reach or forge; shadowing the
  *name* `rpc` gains nothing).
- `spawn_subinterpreter` grew optional `(context_id, allowed_actions,
  rpc_handler)` parameters (backward compatible; Phase 2 call sites
  unchanged).
- The `allowed_actions` gate is enforced **in C before the handler is
  invoked**: a non-allowed action raises `PermissionError` inside the
  sandbox without ever crossing to main.
- **Text-only failure crossing:** if the handler raises, the host
  exception is stringified and destroyed while MAIN is active; the sandbox
  receives a fresh `RuntimeError` with that string. Verified by tests
  asserting, *inside the sandbox*: `type(e) is RuntimeError`,
  `e.__cause__ is None`, `e.__context__ is None`, no `__notes__` — host
  harness check "rpc: handler failure crosses as TEXT-ONLY RuntimeError"
  and the on-wasm `test_rpc_boundary` endpoint.
- A handler returning non-plain data fails the encode on the main side and
  crosses as text (type name only). Non-plain sandbox *arguments* are
  rejected before the swap (`TypeError`).
- Re-entrancy guards: `rpc` refuses re-entrant calls on the same handle;
  `close_subinterpreter` refuses while one of the handle's rpc calls is
  suspended (would otherwise free the interpreter we must swap back into).

### Result extraction

`call_in_subinterpreter(handle, function_name, kwargs=None)` calls a
top-level function defined by the sandboxed source through the same
marshaller (kwargs encoded on main, decoded in the sandbox; result encoded
in the sandbox, materialized on main via the C API). Sandbox exceptions
cross as text-only `RuntimeError`.

### Verification

- Host harness: 21/21 checks (15 Phase 2 + 6 Phase 3: rpc happy path with
  context-id delivery, action gate, text-only failure, non-plain result,
  non-plain argument, call/marshalling incl. 2**60 ints, >64-bit rejection,
  deep-copy semantics).
- On-wasm (locally built template, PocketIC): 8/8 integration tests —
  Phase 2 suite unchanged plus `test_capability_intersection` (5 cases),
  `test_rpc_boundary` (capability-scoped store: read+write through rpc,
  class absent from intersection refused by handler and crossing as
  text-only RuntimeError, `delete_object` outside allowed_actions refused
  by the C gate), `test_result_marshalling`.

## D7. Phase 4 record — instruction metering

Landed as `0007-instruction-metering.patch`, the FIRST functional
interpreter-core patch, applied to the pinned v3.13.0 tree via
`apply_ic_patches`. Touches three files:

- `Include/internal/pycore_interp.h`: three fields appended at the very
  end of `struct _is` (`basilisk_meter_budget`, `_used`, `_exc`, and a
  `_killed` latch) — appended last so no existing offset/initializer
  assumption changes.
- `Python/ceval_macros.h`: `BASILISK_METER_CHECK()` in the hot `DISPATCH()`
  macro. For an unmetered interpreter (`budget == 0`) the cost is a single
  load + branch per instruction; the main interpreter always has
  `budget == 0`.
- `Python/ceval.c`: the host-facing control surface
  (`_PyBasilisk_MeterEnable/Disable/Used`) and `_PyBasilisk_MeterTrip`.

**Design points:**

- **Instruction count, never wall-clock.** The counter increments once per
  bytecode dispatch, so identical code + inputs trip at the identical
  instruction on every replica — deterministic, canister-safe.
- **Per sandboxed frame only.** Metering is armed by the spawn primitive on
  the subinterpreter (`_PyBasilisk_MeterEnable` after
  `Py_NewInterpreterFromConfig`, before the untrusted source runs) and is
  never enabled on the main interpreter. The budget lives on the
  interpreter state, so every frame the sandbox runs (module body and all
  `call_in_subinterpreter` calls) shares one budget; the main interpreter's
  budget stays 0.
- **Named exception.** On the soft trip the interpreter raises a
  per-spawn `sandbox.BudgetExceeded` class, injected into the sandbox
  `__builtins__` so sandboxed code (and tests) can name it. Host wrappers
  `basilisk.sandbox.spawn_sandboxed` / `call_sandboxed` re-raise the
  text-only crossing as `basilisk.sandbox.BudgetExceeded`.
- **Cannot be caught to escape.** A soft `BudgetExceeded` is catchable
  (for bounded cleanup) but the budget is already spent, so it re-trips on
  the very next instruction. After a grace margin (100k instructions past
  the budget) the meter *hard-kills*: it latches `basilisk_meter_killed`,
  which makes the `exception_unwind` machinery treat every frame as
  handler-less, so a `while True: pass` inside `except BudgetExceeded:` (or
  a bare `except:`) unwinds the whole stack instead of livelocking. The
  hard path still runs the normal stack-clearing, so `tstate->exc_info`
  stays consistent and teardown does not crash (verified: an earlier
  handler-bypass via `goto exit_unwind` corrupted the exc-info stack and
  segfaulted at `Py_EndInterpreter`; the latch approach does not).
- **Per-spawn budget parameter.** `spawn_subinterpreter(..., budget=...)`,
  default `10_000_000` instructions (`SANDBOX_DEFAULT_BUDGET`). `budget=0`
  disables metering — a host-only choice, never reachable from inside the
  sandbox.

**Verification (host harness, 26/26):** infinite loop trips
`BudgetExceeded` at exactly the limit (`used == budget + 1`); within-budget
code (including a subsequent `call_in_subinterpreter`) completes; the
budget applies to `call_in_subinterpreter` and is fresh per spawn;
catching `BudgetExceeded` and looping is hard-killed after grace
(`used == budget + grace + 1`, terminates, no crash); and the **main
interpreter runs 3M instructions unmetered while a metered sandbox handle
is live** — confirming metering fires only inside sandboxed frames.
`leak_probe.c` re-run with the metering patch compiled in still shows 0
leaked blocks/cycle, so metering did not regress the leak fix.

**Verification (on-wasm, `test_metering` endpoint):** infinite loop trips
`BudgetExceeded`; within-budget work completes; budget covers
`call_in_subinterpreter` (small call ok, spinning call trips); main
interpreter endpoint runs 300k iterations unmetered. Confirmed as part of
the Phase 4 integration run against the published
`cpython-wasm-3.13.0-ic1` artifact (20/20 Phase 4 fixture tests:
counter, filesystem, subinterpreter).

**Artifact rebuild and publish:** `libpython3.13.a` rebuilt locally with
all seven patches (0001–0007) using wasi-sdk 24.0 (matches CI). Build
script fix: seed `ac_cv_func_clock=yes` — autoconf's generic `clock()`
probe declares a mismatched wasm signature and fails wasm-ld validation
even though wasi-libc provides `clock()` via
`-lwasi-emulated-process-clocks`. Meter symbols verified in the archive
(`_PyBasilisk_MeterEnable/Disable/Trip/Used`). Published as GitHub
release [`cpython-wasm-3.13.0-ic1`](https://github.com/smart-social-contracts/basilisk/releases/tag/cpython-wasm-3.13.0-ic1)
(tarball + `cpython_canister_template.wasm`); `install_cpython_wasm.sh`
downloads and SHA-256 matches the local build. CI workflows, template
fallback URL, and `ARTIFACT_REVISION=ic1` in `install_cpython_wasm.sh`
updated to point at the new release.

**Phase 4 stop point:** leak backport closed (host + on-wasm), instruction
metering landed (host + on-wasm), artifact rebuilt and published,
counter/filesystem/subinterpreter fixtures re-verified on the new
artifact. Ready for Phase 5 (result validation).

## D8. Phase 5 record — result validation (two passes, atomic commit)

Everything a sandboxed call returns is UNTRUSTED. Before any of it reaches
canister state it goes through two sequential passes in
`basilisk.sandbox` (host-side, main interpreter only — no C, no template
change; pure additions to the module already shipped in Phase 3). The
result to commit is plain data:
`{"writes": [{"cls": str, "id": str, "fields": {str: <plain>}}, ...]}`, and
a class schema is plain data too (`{cls: {field: {"type", "required",
"min", "max", "enum"}}}`).

**Pass 1 — schema / type validity** (`_pass1_schema`, over EVERY write):
class must be known; required fields present; no unexpected fields; types
correct. Type checking is **exact and bool-aware** (`_type_matches`):
`bool` never satisfies `int` (a stray `True` must not pass as `1`), and
**`int` does NOT widen to `float`** — see the "Type checking gotcha" note
below.

> **Type checking gotcha (`bool`/`int`/`float`).** Because the check is
> exact, a field declared `{"type": float}` **rejects** an int literal such
> as `amount: 0`; the extension author must write `0.0`, or declare
> `{"type": (int, float)}` to accept either. This is deliberate — untrusted
> input is validated against the shape it literally has, not a coerced one —
> but it is a common source of confusing rejections, so it is documented
> both here and inline in `basilisk.sandbox._type_matches`'s docstring.
> Likewise `bool` (a subclass of `int`) never satisfies an `int` field;
> declare `{"type": (bool, int)}` if you really mean to accept both.

**Pass 2 — authorization** (`_pass2_authorization`, over EVERY write):
- **Write-scope.** The touched class must be `read_write` in the
  *intersected* capability. A class that is `read` → rejected
  ("read-only"); a class absent from the capability entirely → rejected
  ("not in this capability's write scope") — two distinct messages,
  distinct tests.
- **Declared constraints.** `min`/`max` numeric bounds and `enum`
  membership from the class schema.
- **Rule modules re-run at WRITE time**, not read-time-only
  (`_run_rules`): each `rule(write, all_writes)` must return truthy; a
  falsy return or a raised exception rejects the whole result. A rule's
  own exception message is discarded (it could carry a value) — only the
  rule name crosses into `ResultRejected`.

**No value echo.** `ResultRejected` names the field/class/expected-type/
constraint-kind but never a value taken from the result (type mismatches
report the *type name*, not the value; enum/bounds report the kind, not
the value). Covered by explicit "no echo" assertions in the unit tests.

**Commit** (`commit_result`): validation completes ENTIRELY before the
first `apply`, so a result containing any violating object commits nothing
(partial-application guard). Commit is atomic — a `DictCommitter`
snapshots the plain-data store (`_plain_deepcopy`, no `copy`-module import
chain in the canister) and `restore`s it if any per-object `apply` raises
mid-way, so nothing is partially applied under ANY error path.
`validate_result` is exposed separately as a pure, side-effect-free check.

**Verification (host, `tests/test_result_validation.py`, 21 tests):** the
seven required cases — (1) happy path commits; (2) missing required field
→ rejected, nothing committed; (3) write to a `read`-only class →
rejected; (4) write to a class absent from the capability → rejected; (5)
value outside declared bounds → rejected; (6) a write that passes schema
and scope but fails a write-time rule → rejected; (7) one valid + one
violating object commits NOTHING — plus type/bool/enum/envelope edge
cases (incl. the `int`-does-not-widen-to-`float` gotcha and the
`(int, float)` escape hatch), sequential-pass ordering, commit-time
mid-apply rollback, and the no-value-echo guarantees. Wired into the
unit-test CI job.

**Verification (on-wasm, `test_result_validation` endpoint):** a sandboxed
`propose()` returns a write-set that the host two-pass validates and
atomically commits; all seven cases asserted per-case by
`tests/integration/test_subinterpreter.py` against the
`cpython-wasm-3.13.0-ic1` artifact.

**Phase 5 stop point:** two-pass validation + atomic commit landed and
verified host + on-wasm; nothing partially applied on any error path;
untrusted values never echoed in rejections. Ready for Phase 6 (remaining
tests, incl. the reflection/escape attempt).

## D9. Phase 6 record — reflection/escape, end-to-end, docs

The final phase adds the adversarial and cross-phase tests on top of the
Phase 5 artifact (`cpython-wasm-3.13.0-ic1`); no C, patch, or template
changes.

**Reflection / namespace escape (the phase's most important test).** A
sandboxed subinterpreter must not reach host state it was not explicitly
handed via the capability. Eight attempts, each of which must fail with a
clean named exception or a C-gate refusal — never exposing a host object,
host state, or a traceback across the boundary:

| # | Attempt | Outcome |
|---|---------|---------|
| a | `import _basilisk_ic` | `ImportError` — single-phase module refused fail-closed by `check_multi_interp_extensions=1` (on host: absent) |
| b | `import basilisk` | `ImportError` — shim not frozen/builtin, `sys.path == []` |
| c | `object.__subclasses__()` walk (full transitive closure) | every reachable class's `__module__` asserted NOT in `{_basilisk_ic, _basilisk_sandbox, basilisk}` — the gadget reaches no host-privileged type |
| d | `__globals__` / `__builtins__` on reachable callables | a sandbox function's `__globals__` and `__builtins__` expose no host refs; the injected `rpc()` C function has no `__globals__`; `sys.modules` has no privileged surface |
| e | `__import__` of an unapproved module | `ImportError` for privileged surfaces + a non-frozen name. The **approved set is exactly the frozen/builtin modules** baked into the image; note `os` IS frozen (hence importable), but its dangerous surface is neutered because the underlying `posix` is a Basilisk stub |
| f | `rpc()` with an action not in `allowed_actions` | `PermissionError` at the C gate, **before** the handler runs |
| g | re-entrant `rpc()` (handler re-enters the same sandbox) | refused — `in_rpc` latch → `call_in_subinterpreter: re-entrant call` |
| h | `spawn_subinterpreter` from inside a sandbox | unreachable — `_basilisk_sandbox` import refused by the exec-slot guard |

Verified **on host** (`tests/subinterp_harness/main.c`, real subinterpreters
+ real `_basilisk_sandbox`, 7 escape checks) and **on-wasm**
(`test_reflection_escape` endpoint, asserted per-attempt by
`tests/integration/test_subinterpreter.py`).

**End-to-end integration test.** One call exercising the whole stack
together — capability intersection → spawn → `rpc()` read (through the
*intersected* read scope) → `call_in_subinterpreter` → two-pass result
validation → atomic commit — via a realistic auto-tax-assessment extension
(`test_end_to_end`): the caller grants `Citizen: read` while the extension
asks for `read_write`, so intersection downgrades `Citizen` to read (the
sandbox can read income via `rpc` but could never write it); the sandbox
proposes a `TaxRecord` write-set; the host validates it (schema + scope +
a write-time domain rule) and commits atomically. This is the test that
catches a regression where the phases stop composing even if each phase's
own unit tests still pass.

**Type-checking gotcha documented** (Phase 6 item 2): the exact
`bool`/`int`/`float` semantics — and the `(int, float)` escape hatch — are
documented inline in `basilisk.sandbox._type_matches` and in D8's "Type
checking gotcha" note above.

**Full integration suite note.** The subinterpreter feature's own fixtures
pass on the `-ic1` artifact (counter, filesystem, subinterpreter — 12/12 in
the subinterpreter suite). The whole 335-test integration suite could not
be run to a clean finish in the dev sandbox for two environment reasons
unrelated to this feature: (1) the Cursor IDE file-watcher holds ~62.9k of
the machine's 65,536 `fs.inotify.max_user_watches` (raising the limit needs
`sudo`, unavailable non-interactively here); (2) a pre-existing, non-sandbox
failure — `test_browse` hangs at its first test (see
`docs/PREEXISTING_TEST_FAILURES.md`). The `audio_recorder` fixture was
subsequently deleted rather than fixed.

**Phase 6 stop point:** reflection/escape (8/8 host + on-wasm),
end-to-end, and the type-widening documentation all landed. The
subinterpreter sandboxing feature is complete.

## E. Step 0.1 record — patch pipeline made fail-loud

- `apply_ic_patches` in `build_cpython_wasm.sh` now delegates to
  `apply_patches.sh`, which is **fatal** on any patch that neither applies
  nor is already applied (idempotent re-runs stay supported). Covered by
  `tests/test_apply_patches.py` (7 tests, incl. deliberately-broken patch ⇒
  non-zero exit), wired into the unit-test CI workflow.
- Found in the process: the shipped `0001-ic-determinism.patch` was
  **malformed and had never applied** (its context lines presupposed the
  change already present) — the `|| true` hid this. Regenerated as a valid
  diff.
- Found in the process: the cached CPython tree contained **uncommitted,
  load-bearing modifications** (freeze-encodings across
  `Tools/build/freeze_modules.py`, `Makefile.pre.in`, `Python/frozen.c`,
  PCbuild files; and a `Python/codecs.c` missing-encodings tolerance). Any
  rebuild from a fresh clone would have silently produced an artifact on
  which subinterpreter creation is impossible (see B.3). Captured as
  `0002-freeze-encodings.patch` and
  `0003-codecs-tolerate-missing-encodings.patch`; verified to apply cleanly
  to pristine 3.13.0 and to be detected as already-applied on the cache tree.
- **Reproducibility guard (Step 0 review follow-up):** `apply_patches.sh
  --verify-exact` now reverse-applies every repo patch after applying and
  requires the tree to be byte-exactly pristine — any modification not
  captured by a repo patch is a fatal "SOURCE TREE DRIFT DETECTED" error.
  Enforced (a) on every real build via `build_cpython_wasm.sh`, including
  cached trees, and (b) in CI against a *fresh* clone of the pinned tag: a
  `verify-cpython-patches` job in the unit-test workflow (every PR) and a
  `verify-source-tree` job gating the CPython wasm build workflow. Unit
  coverage in `tests/test_apply_patches.py` includes a synthetic
  drifted-tree case.
