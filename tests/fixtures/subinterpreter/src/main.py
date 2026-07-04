"""Fixture canister for the subinterpreter sandbox primitive (Phase 2).

Each endpoint returns a Vec[str] of "PASS ..." / "FAIL ..." lines so the
integration test can assert on exact outcomes without a trap hiding detail.
"""

import _basilisk_sandbox as sb

from basilisk import update, Vec
from basilisk.sandbox import (
    BudgetExceeded,
    DictCommitter,
    ResultRejected,
    build_capability,
    call_sandboxed,
    commit_result,
    spawn_sandboxed,
)


def _spawn_ok(source):
    """Approve + spawn + close; return None on success, error text on failure."""
    h = sb.sha256(source)
    sb.approve_hash(h)
    try:
        handle = sb.spawn_subinterpreter(source, h)
    except Exception as e:  # noqa: BLE001 - report, don't trap
        return f"{type(e).__name__}: {e}"
    sb.close_subinterpreter(handle)
    return None


@update
def test_hash_gate() -> Vec[str]:
    """Hash mismatch / unapproved hash must refuse to spawn."""
    results = []
    src = "x = 1"
    h = sb.sha256(src)
    sb.revoke_hash(h)  # idempotence: a previous run of this endpoint approved it

    try:
        sb.spawn_subinterpreter(src, h)
        results.append("FAIL unapproved hash accepted")
    except PermissionError:
        results.append("PASS unapproved hash refused")
    except Exception as e:  # noqa: BLE001
        results.append(f"FAIL unexpected: {type(e).__name__}: {e}")

    sb.approve_hash(h)
    try:
        sb.spawn_subinterpreter("x = 2", h)
        results.append("FAIL mismatched hash accepted")
    except PermissionError:
        results.append("PASS mismatched hash refused")
    except Exception as e:  # noqa: BLE001
        results.append(f"FAIL unexpected: {type(e).__name__}: {e}")

    err = _spawn_ok(src)
    results.append("PASS approved hash spawns" if err is None
                   else f"FAIL approved hash: {err}")
    return results


@update
def test_spawn_basic() -> Vec[str]:
    """Spawn runs code; sandboxed exceptions come back as plain text."""
    results = []

    err = _spawn_ok("total = sum(range(100))\nassert total == 4950")
    results.append("PASS compute in sandbox" if err is None
                   else f"FAIL compute: {err}")

    src = "raise ValueError('boom from sandbox')"
    h = sb.sha256(src)
    sb.approve_hash(h)
    try:
        sb.spawn_subinterpreter(src, h)
        results.append("FAIL failing source did not raise")
    except RuntimeError as e:
        if "ValueError: boom from sandbox" in str(e):
            results.append("PASS sandbox error propagates as text")
        else:
            results.append(f"FAIL wrong error text: {e}")
    except Exception as e:  # noqa: BLE001
        results.append(f"FAIL unexpected: {type(e).__name__}: {e}")

    return results


@update
def test_isolation_invariants() -> Vec[str]:
    """THE key invariants: no _basilisk_ic, no basilisk shim, no
    _basilisk_sandbox, no host filesystem imports inside the sandbox."""
    results = []

    checks = [
        # (module that must NOT import, label)
        ("_basilisk_ic", "privileged host surface"),
        ("_basilisk_sandbox", "sandbox primitive itself"),
        ("basilisk", "basilisk shim"),
    ]
    for mod, label in checks:
        src = (
            "ok = False\n"
            "try:\n"
            f"    import {mod}\n"
            "except ImportError:\n"
            "    ok = True\n"
            f"assert ok, '{mod} importable in sandbox'\n"
        )
        err = _spawn_ok(src)
        results.append(f"PASS {mod} refused ({label})" if err is None
                       else f"FAIL {mod}: {err}")

    err = _spawn_ok("import sys\nassert sys.path == [], sys.path")
    results.append("PASS sys.path empty in sandbox" if err is None
                   else f"FAIL sys.path: {err}")

    return results


@update
def test_stub_imports_in_sandbox() -> Vec[str]:
    """Converted C stubs must import inside an isolated subinterpreter.

    `re`/`collections`/`operator` etc. are preamble-provided pure-Python in
    the MAIN interpreter and intentionally absent in the sandbox (audit
    addendum section C); what must work are the C-level builtins.
    """
    results = []
    for mod in ["_collections", "_operator", "_sre", "_signal", "posix",
                "_thread", "sys", "builtins", "_json"]:
        err = _spawn_ok(f"import {mod}")
        results.append(f"PASS import {mod}" if err is None
                       else f"FAIL import {mod}: {err}")

    err = _spawn_ok(
        "import _thread\n"
        "lock = _thread.allocate_lock()\n"
        "assert lock.acquire() is True\n"
        "with lock:\n"
        "    pass\n"
    )
    results.append("PASS _thread lock functional" if err is None
                   else f"FAIL _thread lock: {err}")

    return results


@update
def test_capability_intersection() -> Vec[str]:
    """The five required intersection cases, on-wasm."""
    from basilisk.sandbox import intersect_class_scopes as ix

    results = []
    cases = [
        ("case1 ext-only class -> no access",
         ix({"Invoice": "read_write"}, {}) == {}),
        ("case2 caller-only class -> no access",
         ix({}, {"Invoice": "read_write"}) == {}),
        ("case3 both absent -> absent entirely",
         "Invoice" not in ix({"Order": "read"}, {"Order": "read"})),
        ("case4 rw ∩ r -> read (both orders)",
         ix({"O": "read_write"}, {"O": "read"}) == {"O": "read"}
         and ix({"O": "read"}, {"O": "read_write"}) == {"O": "read"}),
        ("case5 rw ∩ rw -> read_write",
         ix({"O": "read_write"}, {"O": "read_write"}) == {"O": "read_write"}),
    ]
    for label, ok in cases:
        results.append(f"PASS {label}" if ok else f"FAIL {label}")
    return results


# Toy host-side store the rpc handler exposes, scoped by the capability.
_STORE = {"Order": {"o1": {"amount": 100}}, "Secret": {"s1": {"key": "x"}}}


def _make_rpc_handler(capability):
    classes = capability["classes"]

    def handler(context_id, action, kwargs):
        cls = kwargs.get("cls", "")
        if action == "get_object":
            if classes.get(cls) not in ("read", "read_write"):
                raise PermissionError(f"no read access to {cls}")
            return _STORE[cls][kwargs["id"]]
        if action == "update_object":
            if classes.get(cls) != "read_write":
                raise PermissionError(f"no write access to {cls}")
            _STORE[cls][kwargs["id"]].update(kwargs["fields"])
            return {"ok": True}
        raise ValueError(f"unknown action {action}")

    return handler


@update
def test_rpc_boundary() -> Vec[str]:
    """rpc() through a real capability on-wasm: happy path, action gate,
    class gate via handler, and TEXT-ONLY failure crossing."""
    results = []

    manifest = {
        "classes": {"Order": "read_write", "Secret": "read"},
        "allowed_actions": ["get_object", "update_object"],
    }
    caller = {
        "classes": {"Order": "read_write"},  # no Secret entry -> no access
        "allowed_actions": ["get_object", "update_object", "delete_object"],
    }
    cap = build_capability(manifest, caller, context_id="ctx-wasm")
    handler = _make_rpc_handler(cap)

    src = """
r = rpc('get_object', cls='Order', id='o1')
assert r == {'amount': 100}, r
r2 = rpc('update_object', cls='Order', id='o1', fields={'amount': 150})
assert r2 == {'ok': True}, r2

# Secret: absent from the intersected capability -> handler refuses,
# and the refusal crosses as TEXT-ONLY RuntimeError.
try:
    rpc('get_object', cls='Secret', id='s1')
    raise AssertionError('Secret was readable')
except RuntimeError as e:
    assert type(e) is RuntimeError, type(e)
    assert 'PermissionError' in str(e) and 'Secret' in str(e), e
    assert e.__cause__ is None and e.__context__ is None

# delete_object was not in the manifest -> not in allowed_actions ->
# refused by the C gate before the handler runs.
try:
    rpc('delete_object', cls='Order', id='o1')
    raise AssertionError('delete_object was allowed')
except PermissionError as e:
    assert 'allowed_actions' in str(e), e
"""
    h = sb.sha256(src)
    sb.approve_hash(h)
    try:
        handle = spawn_sandboxed(src, h, cap, handler)
    except Exception as e:  # noqa: BLE001
        results.append(f"FAIL rpc scenario: {type(e).__name__}: {e}")
        return results
    sb.close_subinterpreter(handle)
    results.append("PASS rpc happy path + action gate + class gate")

    if _STORE["Order"]["o1"]["amount"] == 150:
        results.append("PASS write took effect host-side")
    else:
        results.append(f"FAIL store state: {_STORE}")
    _STORE["Order"]["o1"]["amount"] = 100  # reset for idempotent re-runs

    return results


@update
def test_result_marshalling() -> Vec[str]:
    """call_in_subinterpreter materializes results via the C API."""
    results = []
    src = """
def compute(base=0, factors=None):
    return {
        'total': base + sum(factors or []),
        'nested': {'list': [1, 2.5, None, True, 'x'], 'neg': -(2**60)},
    }
"""
    h = sb.sha256(src)
    sb.approve_hash(h)
    handle = sb.spawn_subinterpreter(src, h)
    try:
        r = sb.call_in_subinterpreter(
            handle, "compute", {"base": 10, "factors": [1, 2, 3]}
        )
        expected = {
            "total": 16,
            "nested": {"list": [1, 2.5, None, True, "x"], "neg": -(2 ** 60)},
        }
        results.append("PASS marshalled result" if r == expected
                       else f"FAIL result: {r}")

        try:
            sb.call_in_subinterpreter(handle, "missing_function")
            results.append("FAIL missing function did not raise")
        except RuntimeError as e:
            results.append("PASS missing function -> text-only RuntimeError"
                           if "no callable" in str(e)
                           else f"FAIL wrong error: {e}")
    finally:
        sb.close_subinterpreter(handle)
    return results


_EMPTY_CAP = {"context_id": "meter-test", "classes": {}, "allowed_actions": []}


def _deny_all_rpc(context_id, action, kwargs):
    raise PermissionError("no rpc in metering tests")


def _spawn_budgeted(src, budget):
    h = sb.sha256(src)
    sb.approve_hash(h)
    return spawn_sandboxed(src, h, _EMPTY_CAP, _deny_all_rpc, budget=budget)


@update
def test_metering() -> Vec[str]:
    """Phase 4 instruction metering, on-wasm: an infinite loop trips
    BudgetExceeded at the configured limit; work within budget completes;
    the budget also covers call_in_subinterpreter; the MAIN interpreter is
    never metered."""
    results = []

    # 1. Infinite loop in the module body trips BudgetExceeded.
    try:
        handle = _spawn_budgeted("while True:\n    pass\n", 100_000)
        sb.close_subinterpreter(handle)
        results.append("FAIL infinite loop did not trip")
    except BudgetExceeded:
        results.append("PASS infinite loop trips BudgetExceeded")
    except Exception as e:  # noqa: BLE001
        results.append(f"FAIL unexpected: {type(e).__name__}: {e}")

    # 2. Work within budget completes under the same limit.
    try:
        handle = _spawn_budgeted(
            "total = sum(range(1000))\nassert total == 499500\n", 100_000
        )
        sb.close_subinterpreter(handle)
        results.append("PASS within-budget work completes")
    except Exception as e:  # noqa: BLE001
        results.append(f"FAIL within budget: {type(e).__name__}: {e}")

    # 3. The budget is shared with call_in_subinterpreter.
    try:
        handle = _spawn_budgeted(
            "def spin():\n"
            "    while True:\n"
            "        pass\n"
            "def small():\n"
            "    return 42\n",
            200_000,
        )
    except Exception as e:  # noqa: BLE001
        results.append(f"FAIL spawn for call: {type(e).__name__}: {e}")
        return results
    try:
        r = call_sandboxed(handle, "small")
        results.append("PASS metered call ok" if r == 42
                       else f"FAIL call result: {r}")
        try:
            call_sandboxed(handle, "spin")
            results.append("FAIL spinning call did not trip")
        except BudgetExceeded:
            results.append("PASS spinning call trips BudgetExceeded")
    finally:
        sb.close_subinterpreter(handle)

    # 4. Main interpreter is unmetered: run far more instructions here than
    # any sandbox budget above (this endpoint itself would have tripped
    # long ago if metering leaked into the main interpreter).
    total = 0
    for i in range(300_000):
        total += i
    results.append("PASS main interpreter unmetered"
                   if total == 44999850000 else f"FAIL main loop: {total}")

    return results


_P5_SCHEMAS = {
    "Order": {
        "amount": {"type": int, "required": True, "min": 0, "max": 10000},
        "status": {"type": str, "enum": ["open", "paid", "void"]},
    },
    "Invoice": {
        "total": {"type": int, "required": True, "min": 0},
    },
    "Ledger": {
        "balance": {"type": int, "required": True},
    },
}


def _p5_capability():
    # Order: read_write; Invoice: read-only; Ledger: absent entirely.
    return {
        "context_id": "ctx-p5-wasm",
        "classes": {"Order": "read_write", "Invoice": "read"},
        "allowed_actions": ["update_object"],
    }


def _p5_run(source, store, rules=None):
    """Spawn a sandbox that returns a proposed write-set, then two-pass
    validate + atomically commit it host-side. Returns (committed_n, error)."""
    h = sb.sha256(source)
    sb.approve_hash(h)
    handle = sb.spawn_subinterpreter(source, h)
    try:
        result = sb.call_in_subinterpreter(handle, "propose", None)
    finally:
        sb.close_subinterpreter(handle)
    committer = DictCommitter(store)
    n = commit_result(result, _p5_capability(), _P5_SCHEMAS, committer,
                      rules=rules)
    return n


@update
def test_result_validation() -> Vec[str]:
    """Phase 5, on-wasm: a sandboxed call proposes a write-set; the host
    two-pass validates (schema, then authorization) and commits atomically.
    Covers all seven required cases."""
    results = []

    # case1 — happy path: valid, in scope, within constraints -> committed.
    store = {"Order": {"o1": {"amount": 100, "status": "open"}}}
    src = (
        "def propose():\n"
        "    return {'writes': [\n"
        "        {'cls': 'Order', 'id': 'o1',\n"
        "         'fields': {'amount': 150, 'status': 'paid'}}]}\n"
    )
    try:
        n = _p5_run(src, store)
        ok = n == 1 and store["Order"]["o1"] == {"amount": 150,
                                                 "status": "paid"}
        results.append("PASS case1 happy path committed" if ok
                       else f"FAIL case1: n={n} store={store}")
    except Exception as e:  # noqa: BLE001
        results.append(f"FAIL case1: {type(e).__name__}: {e}")

    # case2 — schema violation: missing required 'amount'.
    store = {"Order": {"o1": {"amount": 100}}}
    src = (
        "def propose():\n"
        "    return {'writes': [\n"
        "        {'cls': 'Order', 'id': 'o2', 'fields': {'status': 'paid'}}]}\n"
    )
    results.append(_p5_expect_reject(src, store, "case2 missing required",
                                     "missing required field"))

    # case3 — write-scope: Invoice is read-only in the capability.
    store = {"Invoice": {"i1": {"total": 1}}}
    src = (
        "def propose():\n"
        "    return {'writes': [\n"
        "        {'cls': 'Invoice', 'id': 'i1', 'fields': {'total': 9}}]}\n"
    )
    results.append(_p5_expect_reject(src, store, "case3 read-only class",
                                     "read-only"))

    # case4 — write-scope: Ledger absent from the capability entirely.
    store = {"Ledger": {"l1": {"balance": 0}}}
    src = (
        "def propose():\n"
        "    return {'writes': [\n"
        "        {'cls': 'Ledger', 'id': 'l1', 'fields': {'balance': 999}}]}\n"
    )
    results.append(_p5_expect_reject(src, store, "case4 class absent",
                                     "not in this capability's write scope"))

    # case5 — constraint: amount above declared maximum.
    store = {"Order": {"o1": {"amount": 100}}}
    src = (
        "def propose():\n"
        "    return {'writes': [\n"
        "        {'cls': 'Order', 'id': 'o1', 'fields': {'amount': 999999}}]}\n"
    )
    results.append(_p5_expect_reject(src, store, "case5 out of bounds",
                                     "above the declared maximum"))

    # case6 — rule module re-evaluated at write time rejects.
    store = {"Order": {"o1": {"amount": 100}}}
    src = (
        "def propose():\n"
        "    return {'writes': [\n"
        "        {'cls': 'Order', 'id': 'o1',\n"
        "         'fields': {'amount': 100, 'status': 'void'}}]}\n"
    )

    def no_void(write, all_writes):
        return write["fields"].get("status") != "void"

    before = {"Order": {"o1": {"amount": 100}}}
    try:
        _p5_run(src, store, rules=[no_void])
        results.append("FAIL case6 rule did not reject")
    except ResultRejected as e:
        ok = "rule 'no_void' rejected" in str(e) and store == before
        results.append("PASS case6 rule rejected at write time" if ok
                       else f"FAIL case6: {e} store={store}")
    except Exception as e:  # noqa: BLE001
        results.append(f"FAIL case6 unexpected: {type(e).__name__}: {e}")

    # case7 — partial-application guard: one valid + one violating object
    # commits NOTHING.
    store = {"Order": {"o1": {"amount": 100}}}
    before = {"Order": {"o1": {"amount": 100}}}
    src = (
        "def propose():\n"
        "    return {'writes': [\n"
        "        {'cls': 'Order', 'id': 'o1', 'fields': {'amount': 150}},\n"
        "        {'cls': 'Ledger', 'id': 'l1', 'fields': {'balance': 5}}]}\n"
    )
    try:
        _p5_run(src, store)
        results.append("FAIL case7 committed a partial result")
    except ResultRejected:
        ok = store == before and "Ledger" not in store
        results.append("PASS case7 partial application guarded" if ok
                       else f"FAIL case7: store mutated: {store}")
    except Exception as e:  # noqa: BLE001
        results.append(f"FAIL case7 unexpected: {type(e).__name__}: {e}")

    return results


def _p5_expect_reject(src, store, label, needle):
    before = {k: {i: dict(v) for i, v in d.items()}
              for k, d in store.items()}
    try:
        _p5_run(src, store)
        return f"FAIL {label}: not rejected"
    except ResultRejected as e:
        if needle not in str(e):
            return f"FAIL {label}: wrong reason: {e}"
        if store != before:
            return f"FAIL {label}: store mutated: {store}"
        return f"PASS {label}"
    except Exception as e:  # noqa: BLE001
        return f"FAIL {label} unexpected: {type(e).__name__}: {e}"


@update
def test_reflection_escape() -> Vec[str]:
    """Phase 6, on-wasm: reflection / namespace-escape attempts. A sandboxed
    subinterpreter must not reach host state it was not handed. Each attempt
    either raises a clean named exception or is refused at the C gate; none
    exposes a host object, host state, or a traceback across the boundary.

    Attempts that can prove themselves from inside the sandbox assert there
    and rely on `_spawn_ok` (a failed in-sandbox assert crosses back as
    text-only RuntimeError, so a clean spawn IS the proof). The rpc gate and
    re-entrancy attempts are driven from the host."""
    results = []

    def selfcheck(label, src):
        err = _spawn_ok(src)
        results.append(f"PASS {label}" if err is None else f"FAIL {label}: {err}")

    # (a)/(b) import _basilisk_ic and basilisk both refused.
    selfcheck(
        "import _basilisk_ic / basilisk refused",
        "for m in ('_basilisk_ic', 'basilisk'):\n"
        "    ok = False\n"
        "    try:\n"
        "        __import__(m)\n"
        "    except ImportError:\n"
        "        ok = True\n"
        "    assert ok, m + ' importable'\n",
    )

    # (c) __subclasses__() walk from object reaches no host-privileged type.
    selfcheck(
        "__subclasses__() walk reaches no host type",
        "bad = ('_basilisk_ic', '_basilisk_sandbox', 'basilisk')\n"
        "seen = set()\n"
        "stack = [object]\n"
        "while stack:\n"
        "    c = stack.pop()\n"
        "    if id(c) in seen:\n"
        "        continue\n"
        "    seen.add(id(c))\n"
        "    m = str(getattr(c, '__module__', ''))\n"
        "    assert not any(b in m for b in bad), m\n"
        "    stack.extend(type.__subclasses__(c))\n"
        "assert len(seen) > 0\n",
    )

    # (d) __globals__ / __builtins__ expose no host references; the injected
    # rpc() C function has no __globals__ to pivot through.
    selfcheck(
        "__globals__/__builtins__ expose no host refs",
        "def f():\n"
        "    return 1\n"
        "g = f.__globals__\n"
        "assert '_basilisk_ic' not in g and '_basilisk_sandbox' not in g\n"
        "assert not hasattr(rpc, '__globals__')\n"
        "b = g.get('__builtins__')\n"
        "bd = b if isinstance(b, dict) else vars(b)\n"
        "assert '_basilisk_ic' not in bd and '_basilisk_sandbox' not in bd\n"
        "import sys\n"
        "assert '_basilisk_ic' not in sys.modules\n"
        "assert '_basilisk_sandbox' not in sys.modules\n",
    )

    # (e) __import__ of anything outside the approved (frozen/builtin) set is
    # refused: the privileged surfaces and a name that is neither frozen,
    # builtin, nor on sys.path (== []).
    selfcheck(
        "__import__ of unapproved modules refused",
        "for m in ('_basilisk_ic', '_basilisk_sandbox', 'basilisk',\n"
        "          'no_such_module_xyz', 'subprocess'):\n"
        "    ok = False\n"
        "    try:\n"
        "        __import__(m)\n"
        "    except ImportError:\n"
        "        ok = True\n"
        "    assert ok, 'imported ' + m\n",
    )

    # (h) spawn primitive unreachable inside a sandbox (exec-slot guard).
    selfcheck(
        "spawn primitive unreachable in sandbox",
        "ok = False\n"
        "try:\n"
        "    import _basilisk_sandbox\n"
        "except ImportError:\n"
        "    ok = True\n"
        "assert ok, '_basilisk_sandbox importable'\n",
    )

    # (f) rpc() with an action outside allowed_actions -> PermissionError at
    # the C gate, before any handler runs.
    cap = build_capability(
        {"classes": {}, "allowed_actions": ["get_object"]},
        {"classes": {}, "allowed_actions": ["get_object"]},
        context_id="ctx-escape",
    )

    def _unreached(context_id, action, kwargs):
        raise AssertionError("handler must not be reached")

    src_f = (
        "try:\n"
        "    rpc('delete_everything')\n"
        "    raise AssertionError('forbidden action allowed')\n"
        "except PermissionError as e:\n"
        "    assert 'allowed_actions' in str(e), e\n"
    )
    h = sb.sha256(src_f)
    sb.approve_hash(h)
    try:
        handle = spawn_sandboxed(src_f, h, cap, _unreached)
        sb.close_subinterpreter(handle)
        results.append("PASS rpc disallowed action refused at C gate")
    except Exception as e:  # noqa: BLE001
        results.append(f"FAIL rpc disallowed action: {type(e).__name__}: {e}")

    # (g) rpc() re-entrancy: while an rpc is in flight (in_rpc latched), a
    # re-entry into the SAME sandbox is refused.
    cap_g = build_capability(
        {"classes": {}, "allowed_actions": ["cb"]},
        {"classes": {}, "allowed_actions": ["cb"]},
        context_id="ctx-reentry",
    )
    state = {}

    def _reentrant_handler(context_id, action, kwargs):
        if action == "cb":
            try:
                call_sandboxed(state["h"], "reenter")
                state["reentry"] = "ALLOWED"
            except RuntimeError as e:
                state["reentry"] = str(e)
            return {"ok": True}
        return None

    src_g = "def reenter():\n    return rpc('cb')\n"
    hg = sb.sha256(src_g)
    sb.approve_hash(hg)
    try:
        state["h"] = spawn_sandboxed(src_g, hg, cap_g, _reentrant_handler)
        r = call_sandboxed(state["h"], "reenter")
        sb.close_subinterpreter(state["h"])
        ok = r == {"ok": True} and "re-entrant" in state.get("reentry", "")
        results.append("PASS rpc re-entrancy into same sandbox refused" if ok
                       else f"FAIL rpc re-entrancy: r={r} state={state}")
    except Exception as e:  # noqa: BLE001
        results.append(f"FAIL rpc re-entrancy: {type(e).__name__}: {e}")

    return results


# --- End-to-end: a realistic extension exercising the whole stack ----------

_E2E_SCHEMAS = {
    "TaxRecord": {
        # citizen_id is set at record creation and immutable; it is not
        # required on a partial update write (the assessment only touches
        # 'assessed' and 'status').
        "citizen_id": {"type": str},
        "assessed": {"type": int, "min": 0, "max": 1_000_000},
        "status": {"type": str, "enum": ["draft", "assessed", "disputed"]},
    },
    "Citizen": {
        "income": {"type": int, "required": True},
    },
}

# The auto-assessment extension: reads the citizen's income via a privileged
# rpc (read-only capability), computes a flat 10% assessment, and PROPOSES a
# write to the tax record (never writing directly — the host validates and
# commits). Its hash is what the host approves.
_E2E_SOURCE = (
    "def assess():\n"
    "    citizen = rpc('get_object', cls='Citizen', id='c1')\n"
    "    income = citizen['income']\n"
    "    tax = income * 10 // 100\n"
    "    return {'writes': [\n"
    "        {'cls': 'TaxRecord', 'id': 't1',\n"
    "         'fields': {'assessed': tax, 'status': 'assessed'}}]}\n"
)


@update
def test_end_to_end() -> Vec[str]:
    """Phase 6, on-wasm: ONE call exercising the full stack together —
    capability intersection -> spawn -> rpc read (through the intersected
    read scope) -> call_in_subinterpreter -> two-pass result validation ->
    atomic commit. A realistic auto-tax-assessment extension. This is the
    test that catches a regression where the phases stop composing even if
    each phase's own tests still pass."""
    results = []

    store = {
        "Citizen": {"c1": {"income": 50000}},
        "TaxRecord": {"t1": {"citizen_id": "c1", "assessed": 0,
                             "status": "draft"}},
    }

    # 1. Capability intersection. The extension asks for TaxRecord:rw and
    # Citizen:rw; the caller only grants Citizen:read -> Citizen is downgraded
    # to read (the sandbox can read income but could never write it), and
    # only the actions both sides allow survive.
    manifest = {
        "classes": {"TaxRecord": "read_write", "Citizen": "read_write"},
        "allowed_actions": ["get_object", "update_object"],
    }
    caller = {
        "classes": {"TaxRecord": "read_write", "Citizen": "read"},
        "allowed_actions": ["get_object"],
    }
    cap = build_capability(manifest, caller, context_id="ctx-e2e")
    if cap["classes"] == {"TaxRecord": "read_write", "Citizen": "read"} \
            and cap["allowed_actions"] == ["get_object"]:
        results.append("PASS intersection downgraded Citizen to read")
    else:
        results.append(f"FAIL intersection: {cap}")
        return results

    # 2. The rpc handler enforces the capability's class access; only
    # get_object is reachable (update_object was intersected out).
    def handler(context_id, action, kwargs):
        cls = kwargs.get("cls", "")
        if action == "get_object":
            if cap["classes"].get(cls) not in ("read", "read_write"):
                raise PermissionError(f"no read access to {cls}")
            return store[cls][kwargs["id"]]
        raise ValueError(f"unknown action {action}")

    # 3. Approve the extension's exact source hash, spawn, run, validate,
    # commit — with a write-time domain rule re-checked at commit.
    def status_must_be_assessed(write, all_writes):
        # Domain rule: an auto-assessment may only move a record to
        # 'assessed' (never 'disputed'/'draft').
        return write["fields"].get("status") == "assessed"

    h = sb.sha256(_E2E_SOURCE)
    sb.approve_hash(h)
    try:
        handle = spawn_sandboxed(_E2E_SOURCE, h, cap, handler)
    except Exception as e:  # noqa: BLE001
        results.append(f"FAIL spawn: {type(e).__name__}: {e}")
        return results
    try:
        proposal = call_sandboxed(handle, "assess")
    finally:
        sb.close_subinterpreter(handle)

    committer = DictCommitter(store)
    try:
        n = commit_result(proposal, cap, _E2E_SCHEMAS, committer,
                          rules=[status_must_be_assessed])
    except Exception as e:  # noqa: BLE001
        results.append(f"FAIL validate/commit: {type(e).__name__}: {e}")
        return results

    rec = store["TaxRecord"]["t1"]
    ok = (n == 1 and rec["assessed"] == 5000 and rec["status"] == "assessed"
          and store["Citizen"]["c1"]["income"] == 50000)
    results.append("PASS end-to-end tax assessment committed" if ok
                   else f"FAIL e2e result: n={n} store={store}")

    return results


@update
def test_memory_soak(cycles: int) -> Vec[str]:
    """Spawn/close `cycles` subinterpreters with varied allocation patterns;
    report the wasm linear-memory high-water mark (pages never shrink)."""
    results = []
    pages_before = sb.wasm_memory_pages()

    # Varied allocation patterns to encourage fragmentation.
    sources = [
        "data = [list(range(100)) for _ in range(50)]",
        "s = 'x' * 65536\nparts = [s[i:i+7] for i in range(0, 4096, 7)]",
        "d = {i: str(i) * (i % 13 + 1) for i in range(2000)}",
        "import _collections\nblob = bytearray(200000)",
    ]

    for i in range(cycles):
        src = sources[i % len(sources)]
        h = sb.sha256(src)
        sb.approve_hash(h)
        try:
            handle = sb.spawn_subinterpreter(src, h)
        except Exception as e:  # noqa: BLE001
            results.append(f"FAIL cycle {i}: {type(e).__name__}: {e}")
            return results
        sb.close_subinterpreter(handle)

    pages_after = sb.wasm_memory_pages()
    results.append(f"PASS {cycles} cycles")
    results.append(f"pages_before={pages_before}")
    results.append(f"pages_after={pages_after}")
    results.append(f"pages_delta={pages_after - pages_before}")
    results.append(f"high_water_mib={pages_after * 64 // 1024}")
    return results
