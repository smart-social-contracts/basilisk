"""Unit tests for the capability intersection logic (Phase 3).

The five explicitly-required cases from the design review are labeled
case1..case5; additional edge cases follow.
"""

import importlib.util
import os

import pytest

# Import the canister-side module directly from the repo (it has no
# canister-only dependencies when _basilisk_sandbox is absent).
_SANDBOX_PY = os.path.join(
    os.path.dirname(__file__),
    "..", "basilisk", "compiler", "custom_modules", "basilisk", "sandbox.py",
)
_spec = importlib.util.spec_from_file_location("basilisk_sandbox_py", _SANDBOX_PY)
sandbox = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sandbox)

intersect = sandbox.intersect_class_scopes
build_capability = sandbox.build_capability


# --- The five explicitly-required cases ---


def test_case1_extension_declares_class_caller_has_no_entry():
    """Extension declares a class the caller has no entry for -> no access."""
    result = intersect({"Invoice": "read_write"}, {})
    assert "Invoice" not in result
    assert result == {}


def test_case2_caller_has_permission_extension_does_not_declare():
    """Caller has a permission for a class the extension manifest doesn't
    declare -> no access (no fallthrough to the caller's grant)."""
    result = intersect({}, {"Invoice": "read_write"})
    assert "Invoice" not in result
    assert result == {}


def test_case3_both_absent_class_absent_entirely():
    """Both sides absent -> class absent from the capability entirely."""
    result = intersect({"Order": "read"}, {"Order": "read"})
    assert "Invoice" not in result  # never mentioned by either side


def test_case4_read_where_one_side_had_read_write():
    """Happy path: intersection produces read where one side had
    read_write (both orders)."""
    assert intersect({"Order": "read_write"}, {"Order": "read"}) == {
        "Order": "read"
    }
    assert intersect({"Order": "read"}, {"Order": "read_write"}) == {
        "Order": "read"
    }


def test_case5_read_write_where_both_sides_had_read_write():
    """Happy path: read_write only when BOTH sides granted read_write."""
    assert intersect({"Order": "read_write"}, {"Order": "read_write"}) == {
        "Order": "read_write"
    }


# --- Additional rule coverage ---


def test_read_intersect_read_is_read():
    assert intersect({"Order": "read"}, {"Order": "read"}) == {"Order": "read"}


def test_mixed_multi_class():
    ext = {"Order": "read_write", "Invoice": "read", "Audit": "read_write"}
    caller = {"Order": "read", "Audit": "read_write", "Ledger": "read_write"}
    assert intersect(ext, caller) == {
        "Order": "read",          # rw ∩ r
        "Audit": "read_write",    # rw ∩ rw
        # Invoice: caller absent -> no access
        # Ledger: extension absent -> no access
    }


def test_absence_is_not_read():
    """A class missing on one side must NOT silently degrade to read."""
    result = intersect({"Order": "read_write"}, {"Other": "read_write"})
    assert result == {}


def test_invalid_access_level_rejected():
    with pytest.raises(ValueError):
        intersect({"Order": "admin"}, {"Order": "read"})
    with pytest.raises(ValueError):
        intersect({"Order": "read"}, {"Order": "write"})
    with pytest.raises(ValueError):
        intersect({"Order": None}, {"Order": "read"})


# --- build_capability (descriptor + allowed_actions intersection) ---


def test_build_capability_intersects_actions_and_classes():
    manifest = {
        "classes": {"Order": "read_write", "Invoice": "read"},
        "allowed_actions": ["get_object", "update_object", "list_objects"],
    }
    caller = {
        "classes": {"Order": "read"},
        "allowed_actions": ["get_object", "list_objects", "delete_object"],
    }
    cap = build_capability(manifest, caller, context_id="ctx-42")
    assert cap == {
        "context_id": "ctx-42",
        "classes": {"Order": "read"},
        "allowed_actions": ["get_object", "list_objects"],
    }


def test_build_capability_is_json_serializable_plain_data():
    import json

    cap = build_capability(
        {"classes": {"A": "read"}, "allowed_actions": ["x"]},
        {"classes": {"A": "read_write"}, "allowed_actions": ["x", "y"]},
        context_id="c1",
    )
    # Round-trips through JSON without loss -> plain data only.
    assert json.loads(json.dumps(cap)) == cap


def test_build_capability_empty_sides():
    cap = build_capability({}, {})
    assert cap["classes"] == {}
    assert cap["allowed_actions"] == []
