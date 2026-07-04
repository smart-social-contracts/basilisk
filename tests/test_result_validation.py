"""Unit tests for the Phase 5 sandboxed-result validator.

Two sequential passes on everything a sandboxed call returns, before any of
it is committed:

  Pass 1 — schema / type validity
  Pass 2 — authorization (write-scope), declared constraints, write-time rules

Nothing is partially applied: any violation rejects the ENTIRE result and
commits nothing. The seven required cases from the design review are labeled
case1..case7; additional edge cases follow.
"""

import importlib.util
import os

import pytest

_SANDBOX_PY = os.path.join(
    os.path.dirname(__file__),
    "..", "basilisk", "compiler", "custom_modules", "basilisk", "sandbox.py",
)
_spec = importlib.util.spec_from_file_location("basilisk_sandbox_py", _SANDBOX_PY)
sandbox = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sandbox)

ResultRejected = sandbox.ResultRejected
validate_result = sandbox.validate_result
commit_result = sandbox.commit_result
DictCommitter = sandbox.DictCommitter
build_capability = sandbox.build_capability


# --- Shared schema + capability fixtures -----------------------------------

SCHEMAS = {
    "Order": {
        "amount": {"type": int, "required": True, "min": 0, "max": 10000},
        "status": {"type": str, "enum": ["open", "paid", "void"]},
        "memo": {"type": str},
    },
    "Invoice": {
        "total": {"type": int, "required": True, "min": 0},
    },
    "Ledger": {
        "balance": {"type": int, "required": True},
    },
}


def _capability():
    # Order: read_write, Invoice: read (read-only), Ledger: absent entirely.
    return {
        "context_id": "ctx-p5",
        "classes": {"Order": "read_write", "Invoice": "read"},
        "allowed_actions": ["update_object"],
    }


def _fresh_store():
    return {"Order": {"o1": {"amount": 100, "status": "open"}}}


# --- case1: happy path ------------------------------------------------------


def test_case1_happy_path_commits():
    store = _fresh_store()
    committer = DictCommitter(store)
    result = {"writes": [
        {"cls": "Order", "id": "o1",
         "fields": {"amount": 150, "status": "paid"}},
    ]}
    n = commit_result(result, _capability(), SCHEMAS, committer)
    assert n == 1
    assert store["Order"]["o1"] == {"amount": 150, "status": "paid"}


# --- case2: schema violation (missing required field) -----------------------


def test_case2_missing_required_field_rejected():
    store = _fresh_store()
    committer = DictCommitter(store)
    # New object o2 with no 'amount' (required).
    result = {"writes": [
        {"cls": "Order", "id": "o2", "fields": {"status": "paid"}},
    ]}
    with pytest.raises(ResultRejected) as ei:
        commit_result(result, _capability(), SCHEMAS, committer)
    assert "missing required field 'amount'" in str(ei.value)
    assert "Order" in str(ei.value)
    # nothing committed
    assert "o2" not in store["Order"]
    assert store == _fresh_store()


def test_schema_unexpected_field_rejected():
    result = {"writes": [
        {"cls": "Order", "id": "o1",
         "fields": {"amount": 10, "bogus": 1}},
    ]}
    with pytest.raises(ResultRejected) as ei:
        validate_result(result, _capability(), SCHEMAS)
    assert "unexpected field 'bogus'" in str(ei.value)


def test_schema_wrong_type_rejected_without_value_echo():
    result = {"writes": [
        {"cls": "Order", "id": "o1", "fields": {"amount": "not-an-int"}},
    ]}
    with pytest.raises(ResultRejected) as ei:
        validate_result(result, _capability(), SCHEMAS)
    msg = str(ei.value)
    assert "expected type int" in msg and "got str" in msg
    # the untrusted value itself must never be echoed
    assert "not-an-int" not in msg


def test_bool_does_not_satisfy_int():
    result = {"writes": [
        {"cls": "Order", "id": "o1", "fields": {"amount": True}},
    ]}
    with pytest.raises(ResultRejected):
        validate_result(result, _capability(), SCHEMAS)


def test_int_does_not_widen_to_float():
    """Type checking is EXACT: an int literal does NOT satisfy a float field
    (the documented `amount: 0` gotcha). A tuple type accepts either."""
    schemas = {"Price": {"value": {"type": float, "required": True}}}
    cap = {"classes": {"Price": "read_write"}, "allowed_actions": []}

    # int against a float field -> rejected, no value echo
    with pytest.raises(ResultRejected) as ei:
        validate_result(
            {"writes": [{"cls": "Price", "id": "p1", "fields": {"value": 0}}]},
            cap, schemas)
    assert "expected type float" in str(ei.value)
    assert "got int" in str(ei.value)

    # float against a float field -> accepted
    validate_result(
        {"writes": [{"cls": "Price", "id": "p1", "fields": {"value": 0.0}}]},
        cap, schemas)

    # tuple (int, float) accepts either literal, but never bool
    tup = {"Price": {"value": {"type": (int, float), "required": True}}}
    validate_result(
        {"writes": [{"cls": "Price", "id": "p1", "fields": {"value": 0}}]},
        cap, tup)
    validate_result(
        {"writes": [{"cls": "Price", "id": "p1", "fields": {"value": 1.5}}]},
        cap, tup)
    with pytest.raises(ResultRejected):
        validate_result(
            {"writes": [{"cls": "Price", "id": "p1",
                         "fields": {"value": True}}]},
            cap, tup)


# --- case3: write-scope violation (read-only class) -------------------------


def test_case3_read_only_class_rejected():
    store = {"Invoice": {"i1": {"total": 5}}}
    committer = DictCommitter(store)
    result = {"writes": [
        {"cls": "Invoice", "id": "i1", "fields": {"total": 9}},
    ]}
    with pytest.raises(ResultRejected) as ei:
        commit_result(result, _capability(), SCHEMAS, committer)
    assert "read-only" in str(ei.value) and "Invoice" in str(ei.value)
    assert store == {"Invoice": {"i1": {"total": 5}}}


# --- case4: write-scope violation (class absent from capability) ------------


def test_case4_class_absent_from_capability_rejected():
    store = {"Ledger": {"l1": {"balance": 0}}}
    committer = DictCommitter(store)
    result = {"writes": [
        {"cls": "Ledger", "id": "l1", "fields": {"balance": 999}},
    ]}
    with pytest.raises(ResultRejected) as ei:
        commit_result(result, _capability(), SCHEMAS, committer)
    assert "not in this capability's write scope" in str(ei.value)
    assert "Ledger" in str(ei.value)
    assert store == {"Ledger": {"l1": {"balance": 0}}}


# --- case5: constraint violation (value outside declared bounds) ------------


def test_case5_constraint_out_of_bounds_rejected():
    store = _fresh_store()
    committer = DictCommitter(store)
    result = {"writes": [
        {"cls": "Order", "id": "o1", "fields": {"amount": 999999}},
    ]}
    with pytest.raises(ResultRejected) as ei:
        commit_result(result, _capability(), SCHEMAS, committer)
    assert "above the declared maximum" in str(ei.value)
    assert store == _fresh_store()


def test_constraint_below_min_rejected():
    result = {"writes": [
        {"cls": "Order", "id": "o1", "fields": {"amount": -1}},
    ]}
    with pytest.raises(ResultRejected) as ei:
        validate_result(result, _capability(), SCHEMAS)
    assert "below the declared minimum" in str(ei.value)


def test_constraint_enum_violation_rejected():
    result = {"writes": [
        {"cls": "Order", "id": "o1",
         "fields": {"amount": 100, "status": "shipped"}},
    ]}
    with pytest.raises(ResultRejected) as ei:
        validate_result(result, _capability(), SCHEMAS)
    msg = str(ei.value)
    assert "not a permitted value" in msg
    assert "shipped" not in msg  # no value echo


# --- case6: rule-module write-time re-evaluation ----------------------------


def test_case6_rule_rejects_at_write_time():
    """A write that passes schema AND scope but fails a rule module
    re-evaluated at write time is rejected."""
    store = _fresh_store()
    committer = DictCommitter(store)

    def no_downgrade_to_void(write, all_writes):
        # Domain rule: an Order may never be set to 'void' via a sandbox.
        return write["fields"].get("status") != "void"

    result = {"writes": [
        {"cls": "Order", "id": "o1",
         "fields": {"amount": 100, "status": "void"}},
    ]}
    with pytest.raises(ResultRejected) as ei:
        commit_result(result, _capability(), SCHEMAS, committer,
                      rules=[no_downgrade_to_void])
    assert "rule 'no_downgrade_to_void' rejected" in str(ei.value)
    assert store == _fresh_store()


def test_rule_passes_commits():
    store = _fresh_store()
    committer = DictCommitter(store)

    def amount_must_grow(write, all_writes):
        return write["fields"].get("amount", 0) >= 100

    result = {"writes": [
        {"cls": "Order", "id": "o1", "fields": {"amount": 200}},
    ]}
    n = commit_result(result, _capability(), SCHEMAS, committer,
                      rules={"Order": [amount_must_grow]})
    assert n == 1
    assert store["Order"]["o1"]["amount"] == 200


def test_rule_exception_is_text_only():
    """A rule that raises rejects the result, but its exception message
    (which could carry a value) must not leak into ResultRejected."""
    def explodes(write, all_writes):
        raise ValueError("secret-value-42")

    result = {"writes": [
        {"cls": "Order", "id": "o1", "fields": {"amount": 100}},
    ]}
    with pytest.raises(ResultRejected) as ei:
        validate_result(result, _capability(), SCHEMAS, rules=[explodes])
    assert "secret-value-42" not in str(ei.value)
    assert "rule 'explodes' rejected" in str(ei.value)


# --- case7: partial-application guard ---------------------------------------


def test_case7_partial_application_guard():
    """A result with one valid object and one violating object must commit
    NOTHING — not just the valid one."""
    store = _fresh_store()
    before = {"Order": {"o1": dict(store["Order"]["o1"])}}
    committer = DictCommitter(store)
    result = {"writes": [
        # valid
        {"cls": "Order", "id": "o1", "fields": {"amount": 150}},
        # violating: class absent from capability
        {"cls": "Ledger", "id": "l1", "fields": {"balance": 5}},
    ]}
    with pytest.raises(ResultRejected):
        commit_result(result, _capability(), SCHEMAS, committer)
    # the valid write must NOT have been applied
    assert store == before
    assert "Ledger" not in store


def test_partial_guard_second_object_schema_violation():
    store = _fresh_store()
    before = {"Order": {"o1": dict(store["Order"]["o1"])}}
    committer = DictCommitter(store)
    result = {"writes": [
        {"cls": "Order", "id": "o1", "fields": {"amount": 150}},
        {"cls": "Order", "id": "o2", "fields": {"status": "paid"}},  # no amount
    ]}
    with pytest.raises(ResultRejected):
        commit_result(result, _capability(), SCHEMAS, committer)
    assert store == before


# --- atomic rollback if a commit-time apply raises --------------------------


def test_commit_time_apply_failure_rolls_back():
    store = _fresh_store()
    before = {"Order": {"o1": dict(store["Order"]["o1"])}}

    class FlakyCommitter(DictCommitter):
        def __init__(self, s):
            super().__init__(s)
            self.calls = 0

        def apply(self, cls, id, fields):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("store write failed")
            super().apply(cls, id, fields)

    committer = FlakyCommitter(store)
    result = {"writes": [
        {"cls": "Order", "id": "o1", "fields": {"amount": 150}},
        {"cls": "Order", "id": "o3", "fields": {"amount": 200}},
    ]}
    with pytest.raises(RuntimeError):
        commit_result(result, _capability(), SCHEMAS, committer)
    # first apply happened then failed on the second -> full rollback
    assert store == before
    assert "o3" not in store["Order"]


# --- envelope structural validation -----------------------------------------


def test_malformed_envelope_rejected():
    for bad in [
        [],                                   # not a dict
        {"writes": {}},                       # writes not a list
        {"writes": [], "extra": 1},           # unexpected top-level key
        {"writes": [{"cls": "Order"}]},       # missing id/fields
        {"writes": [{"cls": "", "id": "x", "fields": {}}]},   # empty cls
        {"writes": [{"cls": "Order", "id": "o1", "fields": []}]},  # fields list
    ]:
        with pytest.raises(ResultRejected):
            validate_result(bad, _capability(), SCHEMAS)


def test_empty_writes_commits_nothing():
    store = _fresh_store()
    committer = DictCommitter(store)
    n = commit_result({"writes": []}, _capability(), SCHEMAS, committer)
    assert n == 0
    assert store == _fresh_store()


def test_two_valid_writes_both_commit():
    store = {"Order": {"o1": {"amount": 1, "status": "open"}}}
    committer = DictCommitter(store)
    result = {"writes": [
        {"cls": "Order", "id": "o1", "fields": {"amount": 10}},
        {"cls": "Order", "id": "o2", "fields": {"amount": 20, "status": "paid"}},
    ]}
    n = commit_result(result, _capability(), SCHEMAS, committer)
    assert n == 2
    assert store["Order"]["o1"]["amount"] == 10
    assert store["Order"]["o2"] == {"amount": 20, "status": "paid"}


def test_passes_are_sequential_schema_before_scope():
    """A write that violates BOTH schema (unknown class) and scope should
    fail in Pass 1 (schema) first."""
    result = {"writes": [
        {"cls": "Nonexistent", "id": "x", "fields": {"a": 1}},
    ]}
    with pytest.raises(ResultRejected) as ei:
        validate_result(result, _capability(), SCHEMAS)
    assert "unknown class 'Nonexistent'" in str(ei.value)
