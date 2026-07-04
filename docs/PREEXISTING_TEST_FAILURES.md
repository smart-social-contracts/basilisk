# Pre-existing integration-test failures (unrelated to subinterpreter sandboxing)

These two failures surfaced while trying to run the full 335-test integration
suite during the subinterpreter-sandboxing work. **Neither is caused by that
feature** — both reproduce on a *stock, pre-feature* CPython-wasm template and
live in toolkit fixtures the feature never touched. They are recorded here so
they can be triaged on their own.

How "pre-Phase-2 artifact" was reproduced below: the subinterpreter feature
rebuilt the canister template as `cpython-wasm-3.13.0-ic1`. A genuinely
pre-feature artifact is still cached at
`~/.config/basilisk/0.14.1/cpython_canister_template.wasm` (the stock template
shipped with Basilisk 0.14.1, dated well before this work, with no
`_basilisk_sandbox`, no instruction metering, and none of the teardown-leak
patches). Each test below was run with:

```
BASILISK_TEMPLATE_WASM=~/.config/basilisk/0.14.1/cpython_canister_template.wasm \
  python3 -m pytest <test> -v
```

Provenance note: every subinterpreter-feature change is currently uncommitted
in the working tree; `HEAD` is `0.14.2`. The only change the feature makes to
either fixture below is `icp.yaml` (gateway port `8010`, to avoid a local
port-8000 collision) — not the source, the Candid interface, or the test
assertions.

---

## 1. `test_audio_recorder` — Candid variant label rendered as a field-hash

- **Fixture:** `tests/fixtures/audio_recorder` (toolkit ORM `Entity` demo).
- **Tests failing:** `test_create_recording`, `test_delete_user`
  (and `test_delete_recording` cascades: it asserts the previous test ran).
- **What fails:** the tests assert `"Ok" in raw`, where `raw` is the textual
  Candid the `icp-cli` client prints for the update-call response.
- **What the output shows:** the canister call **succeeds** and returns a
  valid record; the response is rendered as

  ```
  (
    variant {
      17_724 = record {
        23_515 = principal "ww3yx-...";
        662_730_966 = blob "\01\02\03\04";
        1_224_700_491 = "test recording";
        1_779_848_746 = 1_783_... : nat64;
        1_869_947_023 = principal "jzmgs-...";
      }
    },
  )
  ```

  The variant tag prints as **`17_724`**, not `Ok`. This is exactly the
  Candid field-hash of `"Ok"`:

  ```
  hash(name) = (Σ over bytes b: hash*223 + b) mod 2^32
  hash("Ok") = 223*ord('O') + ord('k') = 223*79 + 107 = 17_724
  ```

  i.e. **the canister genuinely returned `Ok(...)`** — only the client's
  rendering lost the label (the `.did`/type handed to `icp canister call`
  doesn't carry the variant label, so `icp-cli` falls back to the numeric
  hash). It is a **client-side rendering issue**, independent of the wasm
  the canister runs.

- **Reproduces on pre-Phase-2 artifact?** **Yes — identical.** On the stock
  `0.14.1` template: `3 failed, 3 passed`, with the byte-for-byte same
  `17_724 = record { ... }` output. (Same result on the feature's `-ic1`
  artifact — the artifact is irrelevant to the failure.)

- **Likely fix (for the separate triage):** either have the test parse the
  Candid structurally / match the `17_724` hash, or generate + pass the
  fully-labelled `.did` to `icp canister call` so the client can render `Ok`.
  A libpython/canister change cannot affect this — it is entirely about how
  the client decodes the reply.

---

## 2. `test_browse` — hangs at fixture bring-up / first `__browse__` call

- **Fixture:** `tests/fixtures/browse` (built-in `__shell__` / `__browse__`
  introspection endpoints, added in commit `96f907ae`, long before this work).
- **What fails:** the module hangs and never completes. Under `pytest -v` the
  run prints `test_browse_schema ` (the first test) and then stalls
  indefinitely; the outer `timeout` kills it with exit code **124**.
- **What the observation shows:** during the hang, the `pytest` process is
  **sleeping (`S`) with no active `icp canister call` child process**, while
  the browse network and its canisters are up. So it is not a slow canister
  call in flight — the process is blocked in the harness around fixture
  bring-up / the first `__browse__` query, not inside a running `icp`
  subprocess.
- **Reproduces on pre-Phase-2 artifact?** **Yes.** On the stock `0.14.1`
  template the module hangs at `test_browse_schema` and is killed at the 330s
  timeout (exit 124) — same symptom as under the full suite (`test_browse.py`
  printed `0` progress and never advanced).

- **Notes for the separate triage:** the hang was first seen while the full
  suite plus a parallel host-libpython harness build were competing for the
  machine; it also reproduces in isolation on the stock template, so it is not
  merely resource contention. Suggested next steps: run `test_browse.py` alone
  with `faulthandler`/`-o faulthandler_timeout=60` (or `py-spy dump` on the
  sleeping `pytest` pid) to capture the exact blocked frame — most likely in
  the browse fixture deploy/health-wait or the first `__browse__` query path.

---

### Summary

| Test | Symptom | Canister call | Root cause | Repro on stock 0.14.1 | Feature-related? |
|------|---------|---------------|------------|-----------------------|------------------|
| `test_audio_recorder` (`create_recording`, `delete_user`) | `assert "Ok" in raw` fails | **Succeeds** (`Ok`, hash `17_724`) | client-side Candid label rendering | Yes, identical | No |
| `test_browse` | hangs at first test (exit 124) | none active during hang | harness/deploy/first-query stall | Yes | No |
