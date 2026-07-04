"""Integration tests for the subinterpreter sandbox primitive (Phases 2+3).

Deploys tests/fixtures/subinterpreter and exercises _basilisk_sandbox on a
real wasm canister: hash gating, spawn/close, isolation invariants
(_basilisk_ic refusal above all), converted-stub imports inside the sandbox,
the memory soak measurement, and the Phase 3 capability/rpc/marshalling
boundary.
"""

import os

import pytest

from .conftest import deploy_example, call_canister

EXAMPLE_DIR = os.path.join(
    os.path.dirname(__file__), "..", "fixtures", "subinterpreter"
)


@pytest.fixture(scope="module")
def canister(replica):
    canister_ids = deploy_example("subinterpreter", replica)
    return canister_ids["subinterpreter"]


def _assert_all_pass(raw, label):
    assert "PASS" in raw, f"{label}: no PASS lines in {raw}"
    assert "FAIL" not in raw, f"{label}: {raw}"


def test_hash_gate(canister):
    raw = call_canister(canister, "test_hash_gate", example_dir=EXAMPLE_DIR)
    _assert_all_pass(raw, "hash gate")


def test_spawn_basic(canister):
    raw = call_canister(canister, "test_spawn_basic", example_dir=EXAMPLE_DIR)
    _assert_all_pass(raw, "spawn basic")


def test_isolation_invariants(canister):
    """THE key Phase 2 invariant: _basilisk_ic (and the sandbox primitive
    itself, and the basilisk shim) must not be importable in a sandbox."""
    raw = call_canister(
        canister, "test_isolation_invariants", example_dir=EXAMPLE_DIR
    )
    _assert_all_pass(raw, "isolation invariants")
    assert "_basilisk_ic refused" in raw


def test_stub_imports_in_sandbox(canister):
    raw = call_canister(
        canister, "test_stub_imports_in_sandbox", example_dir=EXAMPLE_DIR
    )
    _assert_all_pass(raw, "stub imports")


def test_capability_intersection_on_wasm(canister):
    """The five explicitly-required intersection cases (also unit-tested
    host-side in tests/test_capability_intersection.py) verified on-wasm."""
    raw = call_canister(
        canister, "test_capability_intersection", example_dir=EXAMPLE_DIR
    )
    _assert_all_pass(raw, "capability intersection")
    for case in ("case1", "case2", "case3", "case4", "case5"):
        assert f"PASS {case}" in raw, f"{case} missing/failed: {raw}"


def test_rpc_boundary(canister):
    """rpc() through a real capability: happy path, allowed_actions gate
    (refused in C before the handler), class-scope gate in the handler,
    and host failures crossing as TEXT-ONLY RuntimeError (no __cause__ /
    __context__ — asserted inside the sandboxed source itself)."""
    raw = call_canister(canister, "test_rpc_boundary", example_dir=EXAMPLE_DIR)
    _assert_all_pass(raw, "rpc boundary")
    assert "PASS rpc happy path + action gate + class gate" in raw
    assert "PASS write took effect host-side" in raw


def test_result_marshalling(canister):
    """call_in_subinterpreter: results materialized via the C API cross as
    deep-copied plain data; sandbox errors cross as text."""
    raw = call_canister(
        canister, "test_result_marshalling", example_dir=EXAMPLE_DIR
    )
    _assert_all_pass(raw, "result marshalling")


def test_result_validation(canister):
    """Phase 5: two-pass result validation (schema, then authorization) with
    atomic commit, on-wasm. A sandboxed call proposes a write-set; the host
    validates and commits only if BOTH passes clear, rejecting the whole
    result (nothing committed) on any violation."""
    raw = call_canister(
        canister, "test_result_validation", example_dir=EXAMPLE_DIR
    )
    _assert_all_pass(raw, "result validation")
    for case in ("case1", "case2", "case3", "case4", "case5", "case6",
                 "case7"):
        assert f"PASS {case}" in raw, f"{case} missing/failed: {raw}"


def test_reflection_escape(canister):
    """Phase 6: reflection / namespace-escape attempts from inside a sandbox.
    A sandboxed subinterpreter must not reach host state it was not handed.
    Every attempt must fail cleanly (named exception or C-gate refusal)
    without exposing host objects, host state, or a traceback."""
    raw = call_canister(
        canister, "test_reflection_escape", example_dir=EXAMPLE_DIR
    )
    _assert_all_pass(raw, "reflection escape")
    for needle in (
        "PASS import _basilisk_ic / basilisk refused",
        "PASS __subclasses__() walk reaches no host type",
        "PASS __globals__/__builtins__ expose no host refs",
        "PASS __import__ of unapproved modules refused",
        "PASS spawn primitive unreachable in sandbox",
        "PASS rpc disallowed action refused at C gate",
        "PASS rpc re-entrancy into same sandbox refused",
    ):
        assert needle in raw, f"escape attempt missing/failed: {raw}"


def test_end_to_end(canister):
    """Phase 6: the whole stack in one call — capability intersection ->
    spawn -> rpc read (through the intersected read scope) ->
    call_in_subinterpreter -> two-pass result validation -> atomic commit,
    via a realistic auto-tax-assessment extension. Catches cross-phase
    regressions that per-phase unit tests would miss."""
    raw = call_canister(canister, "test_end_to_end", example_dir=EXAMPLE_DIR)
    _assert_all_pass(raw, "end to end")
    assert "PASS intersection downgraded Citizen to read" in raw
    assert "PASS end-to-end tax assessment committed" in raw


def test_metering(canister):
    """Phase 4: deterministic instruction budget on-wasm — infinite loop
    trips BudgetExceeded, within-budget work completes, the budget covers
    call_in_subinterpreter, and the main interpreter is never metered."""
    raw = call_canister(canister, "test_metering", example_dir=EXAMPLE_DIR)
    _assert_all_pass(raw, "metering")
    assert "PASS infinite loop trips BudgetExceeded" in raw
    assert "PASS within-budget work completes" in raw
    assert "PASS spinning call trips BudgetExceeded" in raw
    assert "PASS main interpreter unmetered" in raw


def test_memory_soak(canister):
    """Linear-memory high-water mark across spawn/close cycles.

    The CPython 3.13.0 subinterpreter teardown leak (~1.1 pages/cycle
    upstream; docs/SUBINTERPRETER_AUDIT.md §D5) is closed by patches
    0004-0006: measured pages_delta=0 over 200 cycles on-wasm. The
    tripwire below allows minor allocator variance but catches any
    regression toward the old per-cycle growth.
    """
    raw = call_canister(
        canister, "test_memory_soak", args="(200)", example_dir=EXAMPLE_DIR
    )
    _assert_all_pass(raw, "memory soak")
    print(f"soak result: {raw}")

    import re as _re

    m = _re.search(r"pages_delta=(\d+)", raw)
    assert m, raw
    pages_delta = int(m.group(1))
    assert pages_delta < 32, (
        f"memory growth {pages_delta} pages over 200 cycles; the teardown "
        f"leak was closed by patches 0004-0006 (measured delta 0) — this "
        f"looks like a leak regression"
    )
