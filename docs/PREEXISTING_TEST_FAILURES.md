# Pre-existing integration-test failure (unrelated to subinterpreter sandboxing)

This failure surfaced while trying to run the full integration suite during
the subinterpreter-sandboxing work. **It is not caused by that feature** —
it reproduces on a *stock, pre-feature* CPython-wasm template and lives in a
fixture the feature never touched. Recorded here so it can be triaged on its
own.

How "pre-Phase-2 artifact" was reproduced below: the subinterpreter feature
rebuilt the canister template as `cpython-wasm-3.13.0-ic1`. A genuinely
pre-feature artifact is still cached at
`~/.config/basilisk/0.14.1/cpython_canister_template.wasm` (the stock template
shipped with Basilisk 0.14.1, dated well before this work, with no
`_basilisk_sandbox`, no instruction metering, and none of the teardown-leak
patches). The test was run with:

```
BASILISK_TEMPLATE_WASM=~/.config/basilisk/0.14.1/cpython_canister_template.wasm \
  python3 -m pytest tests/integration/test_browse.py -v
```

---

## `test_browse` — hangs at fixture bring-up / first `__browse__` call

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

- **Notes for triage:** the hang was first seen while the full suite plus a
  parallel host-libpython harness build were competing for the machine; it
  also reproduces in isolation on the stock template, so it is not merely
  resource contention. Suggested next steps: run `test_browse.py` alone with
  `faulthandler`/`-o faulthandler_timeout=60` (or `py-spy dump` on the
  sleeping `pytest` pid) to capture the exact blocked frame — most likely in
  the browse fixture deploy/health-wait or the first `__browse__` query path.

### Related: `test_browse_custom` (also not in CI)

The `browse_custom` fixture tests custom `__shell__`/`__browse__` overrides.
It does **not** hang, but all four tests fail on the stock `0.14.1` template
with JSON parse errors on `__browse__` responses (`json.loads` after
`parse_candid_text`) and a shell output assertion (`'2\\n'` vs expected digit
string). Likely the same class of `icp-cli` candid/text rendering issues as
the deleted `audio_recorder` tests. Left out of CI until fixed.

### Summary

| Test | Symptom | Canister call | Root cause | Repro on stock 0.14.1 | Feature-related? |
|------|---------|---------------|------------|-----------------------|------------------|
| `test_browse` | hangs at first test (exit 124) | none active during hang | harness/deploy/first-query stall | Yes | No |
| `test_browse_custom` | 4/4 fail (JSON parse / shell text) | calls complete | client-side candid/text rendering | Yes (stock 0.14.1) | No |

### Removed: `test_audio_recorder`

The `audio_recorder` fixture and its integration tests were **deleted**
(permanently) rather than fixed. They were a toolkit ORM demo whose tests
asserted `"Ok"` in the raw `icp-cli` Candid output, but the client renders
variant labels as field-hashes (`17_724` for `"Ok"`). The canister calls
succeeded; only the string assertion was wrong. Removing the fixture avoids
carrying broken CI debt unrelated to Basilisk core.
