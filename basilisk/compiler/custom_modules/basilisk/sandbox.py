"""Capability descriptors and host-side helpers for the subinterpreter
sandbox (Phase 3 of the subinterpreter sandboxing work).

This module runs in the MAIN interpreter only (it is part of the `basilisk`
shim, which is never importable inside a sandbox — enforced by the spawn
primitive and covered by tests). It provides:

- the capability descriptor: a plain-data (JSON-serializable) dict,
- the intersection logic between an extension's declared scope and the
  caller's actual permissions,
- a convenience wrapper around ``_basilisk_sandbox.spawn_subinterpreter``.

Capability descriptor shape::

    {
        "context_id": "<opaque host-side id>",
        "classes": {                # intersected class scopes
            "ClassName": "read" | "read_write",
        },
        "allowed_actions": ["get_object", ...],   # intersected action list
    }

The sandboxed code NEVER sees this descriptor object — it lives host-side.
The spawn primitive receives ``context_id`` and ``allowed_actions`` (the C
layer enforces the action gate before any rpc handler runs); the full
descriptor including class scopes is for the host's rpc handler and the
Phase 5 result validator.

Security model / trust boundary (read this first)
--------------------------------------------------

The isolation guarantee is **capability + absence-by-construction**, NOT an
import denylist. Two points an external reviewer usually asks about:

1. **The "approved set" of importable modules is exactly CPython's
   frozen/builtin modules** — the ones baked into the interpreter image.
   Anything that needs ``sys.path`` (arbitrary on-disk code) cannot import,
   because the sandbox runs with ``sys.path == []``; and single-phase C
   extensions — including the entire privileged host surface
   (``_basilisk_ic``) and the spawn primitive (``_basilisk_sandbox``) — are
   refused *fail-closed* by CPython itself under
   ``check_multi_interp_extensions=1``. There is no denylist to keep in
   sync.

2. **``import os`` SUCCEEDS inside a sandbox, and that is fine.** ``os`` is
   part of CPython's default *frozen* module set, so it is importable in any
   subinterpreter regardless of ``sys.path`` — it is in the approved set by
   virtue of being frozen, not because anything explicitly allowed it. The
   safety does not come from blocking the ``os`` import; it comes from the
   dangerous *native* surface being **absent by construction**: this build's
   ``posix`` is a Basilisk stub, and modules like ``_socket`` / ``_subprocess``
   / ``ctypes`` backends are not compiled in at all. So ``os`` exposes no real
   filesystem, no subprocess spawning, and no sockets — there is nothing
   underneath it to reach. The trust model is: *approved set = frozen/builtin
   modules; the dangerous native surface is simply not present, rather than
   denylisted.*

The reflection/escape tests (host harness ``tests/subinterp_harness`` and the
on-wasm ``test_reflection_escape`` fixture endpoint) exercise this boundary
directly; see ``docs/SUBINTERPRETER_AUDIT.md`` §D9.
"""

try:
    import _basilisk_sandbox
except ImportError:  # host-side unit tests / non-canister environments
    _basilisk_sandbox = None

_ACCESS_RANK = {"read": 1, "read_write": 2}

#: Default per-spawn instruction budget (bytecode instructions, counted
#: deterministically in the interpreter's dispatch loop — never wall-clock).
DEFAULT_BUDGET = 10_000_000


class BudgetExceeded(Exception):
    """Host-side counterpart of the sandbox's BudgetExceeded.

    Inside the sandbox the interpreter raises its own ``BudgetExceeded``
    (injected at spawn); it crosses the boundary as text, and
    ``spawn_sandboxed`` / ``call_sandboxed`` re-raise it as this class so
    host code can catch it by name.
    """


def _check_access_value(value, side, cls):
    if value not in _ACCESS_RANK:
        raise ValueError(
            f"invalid access level {value!r} for class {cls!r} in {side}: "
            f"must be 'read' or 'read_write'"
        )


def intersect_class_scopes(extension_scope, caller_permissions):
    """Intersect an extension's declared class scope with the caller's
    actual permissions.

    Both arguments are dicts of ``{class_name: "read" | "read_write"}``.

    Rules (exact, per design review):

    - ``read_write`` ∩ ``read_write`` = ``read_write``
    - ``read_write`` ∩ ``read`` = ``read`` (either order)
    - ``read`` ∩ ``read`` = ``read``
    - a class absent from EITHER side gets NO access — absence is not
      ``read``, and there is no fallthrough to the other side's grant;
      the class is simply omitted from the result.
    """
    result = {}
    for cls, ext_access in extension_scope.items():
        _check_access_value(ext_access, "extension scope", cls)
        caller_access = caller_permissions.get(cls)
        if caller_access is None:
            continue  # absent on the caller side -> no access
        _check_access_value(caller_access, "caller permissions", cls)
        rank = min(_ACCESS_RANK[ext_access], _ACCESS_RANK[caller_access])
        result[cls] = "read" if rank == 1 else "read_write"
    # Classes only in caller_permissions never enter the loop -> no access.
    return result


def build_capability(manifest, caller_permissions, context_id=""):
    """Compute the capability descriptor for one sandbox invocation.

    ``manifest``: the extension's declared scope —
        ``{"classes": {...}, "allowed_actions": [...]}``
    ``caller_permissions``: the caller's actual permissions in the current
        application context — same shape.

    The result is the intersection: the sandboxed code never receives
    broader access than BOTH sides granted, and never negotiates its own
    scope at runtime.
    """
    classes = intersect_class_scopes(
        manifest.get("classes", {}), caller_permissions.get("classes", {})
    )
    allowed_actions = sorted(
        set(manifest.get("allowed_actions", []))
        & set(caller_permissions.get("allowed_actions", []))
    )
    return {
        "context_id": str(context_id),
        "classes": classes,
        "allowed_actions": allowed_actions,
    }


def _reraise_budget(exc):
    """Map the text-only crossing of the sandbox's BudgetExceeded onto the
    host-side class; re-raise anything else unchanged."""
    if "BudgetExceeded" in str(exc):
        raise BudgetExceeded(str(exc)) from None
    raise exc


def spawn_sandboxed(source_code, content_hash, capability, rpc_handler,
                    budget=DEFAULT_BUDGET):
    """Spawn a subinterpreter running ``source_code`` under ``capability``.

    ``rpc_handler(context_id, action, kwargs) -> plain data`` runs in the
    MAIN interpreter for each ``rpc()`` call the sandboxed code makes; it is
    only invoked for actions in ``capability["allowed_actions"]`` (the C
    layer refuses others before the handler is reached). All data crossing
    either direction is deep-copied plain data (None/bool/int/float/str/
    list/dict) — never live object references.

    ``budget`` is the per-spawn deterministic instruction budget shared by
    the module body and all subsequent ``call_sandboxed`` calls; exceeding
    it raises :class:`BudgetExceeded`. ``budget=0`` disables metering —
    a host-side decision only, never negotiable from inside the sandbox.

    Returns the raw handle; close with
    ``_basilisk_sandbox.close_subinterpreter(handle)``.
    """
    if _basilisk_sandbox is None:
        raise RuntimeError("_basilisk_sandbox is not available here")
    try:
        return _basilisk_sandbox.spawn_subinterpreter(
            source_code,
            content_hash,
            capability.get("context_id", ""),
            tuple(capability.get("allowed_actions", [])),
            rpc_handler,
            budget,
        )
    except RuntimeError as exc:
        _reraise_budget(exc)


def call_sandboxed(handle, function_name, kwargs=None):
    """Call a top-level function in a spawned sandbox; plain data both ways.

    Raises :class:`BudgetExceeded` if the call exhausts the spawn's
    remaining instruction budget.
    """
    if _basilisk_sandbox is None:
        raise RuntimeError("_basilisk_sandbox is not available here")
    try:
        return _basilisk_sandbox.call_in_subinterpreter(
            handle, function_name, kwargs
        )
    except RuntimeError as exc:
        _reraise_budget(exc)


# ---------------------------------------------------------------------------
# Phase 5 — result validation (two sequential passes, then atomic commit)
# ---------------------------------------------------------------------------
#
# Everything a sandboxed call returns is UNTRUSTED input. Before ANY of it is
# committed to canister state it goes through two sequential passes:
#
#   Pass 1 (schema/type): the result matches the declared object shape for its
#     class — required fields present, no unexpected fields, correct types.
#   Pass 2 (authorization): every touched field is within the capability's
#     granted WRITE scope, field values satisfy the class's declared
#     constraints (bounds/enum), and applicable rule modules re-evaluated at
#     WRITE time all pass.
#
# On ANY violation the ENTIRE result is rejected and NOTHING is committed
# (no partial application under any error path). Rejection messages name the
# violated field/class/expected-type/constraint kind but NEVER echo back a
# value from the result — those values are untrusted at this point.
#
# A sandboxed result to be committed is plain data of the shape::
#
#     {"writes": [{"cls": str, "id": str, "fields": {str: <plain>}}, ...]}
#
# i.e. the set of object mutations the sandbox is proposing. A class schema is
# plain data too::
#
#     {
#       "Order": {
#         "amount": {"type": int, "required": True, "min": 0, "max": 10000},
#         "status": {"type": str, "enum": ["open", "paid", "void"]},
#         # Type checking is EXACT (see _type_matches): an int literal does
#         # NOT satisfy a float field, and bool never satisfies int. Declare a
#         # tuple type to accept either — this is the recommended way to write
#         # a money/measurement field that a sandbox may return as 0 or 0.0:
#         "discount": {"type": (int, float), "min": 0},
#       },
#     }


class ResultRejected(Exception):
    """A sandboxed result failed validation; nothing was committed.

    The message names the violated field/class/expected-type/constraint but
    never echoes a value taken from the (untrusted) result.
    """


def _type_name(t):
    if isinstance(t, tuple):
        return "|".join(_type_name(x) for x in t)
    return getattr(t, "__name__", str(t))


def _type_matches(value, expected):
    """Strict, bool-aware, EXACT type check.

    Type checking is intentionally exact, with two consequences extension
    authors must know about (see also the "Type checking" note in this
    module's design doc / SUBINTERPRETER_AUDIT.md):

    * ``bool`` never satisfies an ``int`` field, even though ``bool``
      subclasses ``int`` — a stray ``True`` must not sneak through as ``1``.
    * ``int`` does NOT widen to ``float``. A field declared
      ``{"type": float}`` REJECTS an int literal such as ``amount: 0``;
      the author must write ``0.0``, or declare ``{"type": (int, float)}``
      to accept either. This is deliberate (untrusted input is validated
      against the shape it literally has, not a coerced one), but it is a
      common source of confusing rejections, so it is called out here.

    A tuple ``expected`` means "any one of these exact types".
    """
    if isinstance(expected, tuple):
        return any(_type_matches(value, e) for e in expected)
    if expected is bool:
        return type(value) is bool
    if type(value) is bool:
        return False
    return type(value) is expected


def _normalize_writes(result):
    """Structural validation of the result envelope itself.

    Returns the list of writes. Raises :class:`ResultRejected` (structural
    identifiers only, no values) on any malformed shape.
    """
    if not isinstance(result, dict):
        raise ResultRejected("result must be an object with a 'writes' list")
    if set(result.keys()) - {"writes"}:
        raise ResultRejected("result has unexpected top-level keys")
    writes = result.get("writes")
    if not isinstance(writes, list):
        raise ResultRejected("result 'writes' must be a list")
    for i, w in enumerate(writes):
        if not isinstance(w, dict):
            raise ResultRejected(f"write #{i} must be an object")
        if set(w.keys()) - {"cls", "id", "fields"}:
            raise ResultRejected(f"write #{i} has unexpected keys")
        if not isinstance(w.get("cls"), str) or not w["cls"]:
            raise ResultRejected(f"write #{i} 'cls' must be a non-empty string")
        if not isinstance(w.get("id"), str) or not w["id"]:
            raise ResultRejected(f"write #{i} 'id' must be a non-empty string")
        fields = w.get("fields")
        if not isinstance(fields, dict):
            raise ResultRejected(
                f"write #{i} (class '{w['cls']}') 'fields' must be an object"
            )
        for k in fields:
            if not isinstance(k, str):
                raise ResultRejected(
                    f"write #{i} (class '{w['cls']}') has a non-string "
                    f"field name"
                )
    return writes


def _pass1_schema(writes, schemas):
    """Pass 1 — schema / type validity, over EVERY write."""
    for w in writes:
        cls = w["cls"]
        schema = schemas.get(cls)
        if schema is None:
            raise ResultRejected(f"unknown class '{cls}'")
        fields = w["fields"]

        for name in fields:
            if name not in schema:
                raise ResultRejected(
                    f"unexpected field '{name}' for class '{cls}'"
                )

        for name, spec in schema.items():
            if spec.get("required") and name not in fields:
                raise ResultRejected(
                    f"missing required field '{name}' for class '{cls}'"
                )

        for name, value in fields.items():
            expected = schema[name].get("type")
            if expected is not None and not _type_matches(value, expected):
                raise ResultRejected(
                    f"field '{name}' for class '{cls}' expected type "
                    f"{_type_name(expected)}, got {_type_name(type(value))}"
                )


def _pass2_authorization(writes, capability, schemas, rules):
    """Pass 2 — write-scope, declared constraints, and write-time rules,
    over EVERY write."""
    granted = capability.get("classes", {}) if capability else {}

    for w in writes:
        cls = w["cls"]

        access = granted.get(cls)
        if access is None:
            raise ResultRejected(
                f"class '{cls}' is not in this capability's write scope"
            )
        if access != "read_write":
            raise ResultRejected(
                f"class '{cls}' is read-only in this capability"
            )

        schema = schemas[cls]
        for name, value in w["fields"].items():
            spec = schema[name]
            if "enum" in spec and value not in spec["enum"]:
                raise ResultRejected(
                    f"field '{name}' for class '{cls}' is not a permitted "
                    f"value (enum)"
                )
            lo, hi = spec.get("min"), spec.get("max")
            if lo is not None and value < lo:
                raise ResultRejected(
                    f"field '{name}' for class '{cls}' is below the "
                    f"declared minimum ({lo})"
                )
            if hi is not None and value > hi:
                raise ResultRejected(
                    f"field '{name}' for class '{cls}' is above the "
                    f"declared maximum ({hi})"
                )

    _run_rules(writes, rules)


def _run_rules(writes, rules):
    """Re-run applicable rule modules at WRITE time.

    ``rules`` may be:
      - ``None`` — no rules,
      - a flat iterable of callables — each applied to every write,
      - a dict ``{class_name: [callables]}`` — applied only to writes of
        that class.

    Each rule is called ``rule(write, all_writes)`` and must return a truthy
    value; a falsy return or any raised exception rejects the whole result.
    Rule exceptions are converted to :class:`ResultRejected` with the rule's
    name only (never the exception's message, which could carry a value).
    """
    if not rules:
        return

    def apply(rule, write):
        name = getattr(rule, "__name__", "rule")
        try:
            ok = rule(write, writes)
        except Exception:  # noqa: BLE001 - text-only, no value leak
            raise ResultRejected(
                f"rule '{name}' rejected write to class '{write['cls']}'"
            ) from None
        if not ok:
            raise ResultRejected(
                f"rule '{name}' rejected write to class '{write['cls']}'"
            )

    if isinstance(rules, dict):
        for w in writes:
            for rule in rules.get(w["cls"], ()):
                apply(rule, w)
    else:
        for w in writes:
            for rule in rules:
                apply(rule, w)


def validate_result(result, capability, schemas, rules=None):
    """Two-pass validation of a sandboxed ``result``. Pure — no side effects.

    Runs Pass 1 (schema/type) over every write, then Pass 2 (write-scope +
    declared constraints + write-time rules) over every write. Raises
    :class:`ResultRejected` on the first violation (which rejects the whole
    result); on success returns the normalized list of writes.
    """
    writes = _normalize_writes(result)
    _pass1_schema(writes, schemas)
    _pass2_authorization(writes, capability, schemas, rules)
    return writes


def _plain_deepcopy(value):
    """Deep-copy plain data (dict/list/tuple/primitives) without importing
    the ``copy`` module — the sandbox store is plain data by construction,
    and this avoids ``copy``'s weakref/copyreg import chain inside the
    canister's main interpreter."""
    if isinstance(value, dict):
        return {k: _plain_deepcopy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain_deepcopy(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_plain_deepcopy(v) for v in value)
    return value


class DictCommitter:
    """Atomic committer over a plain ``{cls: {id: {field: value}}}`` store.

    Used by the sandbox result path (and tests/fixtures): snapshot/restore
    give all-or-nothing application even if an individual apply raises.
    """

    def __init__(self, store):
        self.store = store

    def snapshot(self):
        return _plain_deepcopy(self.store)

    def restore(self, snap):
        self.store.clear()
        self.store.update(snap)

    def apply(self, cls, id, fields):
        self.store.setdefault(cls, {}).setdefault(id, {}).update(fields)


def commit_result(result, capability, schemas, committer, rules=None):
    """Validate ``result`` (both passes) and, only if it fully clears,
    commit every write ATOMICALLY.

    ``committer`` implements ``snapshot()``, ``restore(token)`` and
    ``apply(cls, id, fields)``. Validation completes entirely before the
    first ``apply``, so a result with any violating object commits nothing
    (partial-application guard). If an ``apply`` itself raises mid-way, the
    snapshot is restored so nothing is partially applied under any error
    path.

    Returns the number of writes committed. Raises :class:`ResultRejected`
    (or re-raises a commit-time error after rollback) otherwise.
    """
    writes = validate_result(result, capability, schemas, rules)
    snap = committer.snapshot()
    try:
        for w in writes:
            committer.apply(w["cls"], w["id"], w["fields"])
    except Exception:
        committer.restore(snap)
        raise
    return len(writes)
