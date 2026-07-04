/*
 * Host-embedded test harness for Basilisk's PEP 489 stub-module conversions.
 *
 * Links the REAL src/cpython_config.c (symbol-renamed via host_rename.h, see
 * that file) against a native libpython3.13.a built from the same pinned,
 * patched CPython 3.13.0 tree as the wasm artifact. The stub modules are
 * registered in the inittab under b5k_-prefixed names (the host python has
 * real posix/_thread/... builtins that would shadow the originals) and then
 * imported inside subinterpreters created with the sandbox
 * PyInterpreterConfig from the audit:
 *
 *   use_main_obmalloc = 0, allow_fork/exec/threads/daemon_threads = 0,
 *   check_multi_interp_extensions = 1, gil = PyInterpreterConfig_OWN_GIL
 *
 * What this proves (and the wasm build cannot easily prove pre-spawn-
 * primitive):
 *   1. All six converted stubs import successfully under
 *      check_multi_interp_extensions=1 (single-phase modules are refused —
 *      verified by a deliberate single-phase negative control).
 *   2. _thread's PyType_FromSpec-in-Py_mod_exec works inside a
 *      subinterpreter (the audit's flagged risk item).
 *   3. Per-interpreter state isolation: posix.stat_result and
 *      _thread.LockType are DIFFERENT type objects in different
 *      interpreters (no shared C-static type).
 *   4. Repeated spawn/teardown with per-module state does not crash
 *      (m_free/m_clear correctness smoke test).
 *
 * NOT covered here: wasm32 specifics and main-interpreter early bootstrap
 * ordering (the wasm canister build exercises those).
 */
#include <Python.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* The REAL wasm inittab from cpython_config.c, renamed by host_rename.h so
 * it does not clash with the host archive's own _PyImport_Inittab. Stub
 * PyInit_* functions are static in cpython_config.c, so we reach them the
 * same way the interpreter does: through this table. */
extern struct _inittab b5k_wasm_inittab[];

static PyObject *(*find_init(const char *name))(void) {
    for (struct _inittab *p = b5k_wasm_inittab; p->name != NULL; p++) {
        if (strcmp(p->name, name) == 0) {
            return p->initfunc;
        }
    }
    fprintf(stderr, "fatal: %s not found in wasm inittab\n", name);
    exit(1);
}

/* Referenced by the renamed (unused) inittab; never called on host. */
PyObject *b5k_dummy_PyInit__struct(void) { return NULL; }
PyObject *b5k_dummy_PyInit__json(void) { return NULL; }

/* Negative control: a deliberately single-phase (legacy) module. Importing
 * it in a check_multi_interp_extensions=1 subinterpreter must FAIL — this
 * proves the sandbox config actually refuses unconverted modules, i.e. that
 * the PEP 489 conversions are load-bearing rather than cosmetic. */
static PyMethodDef singlephase_methods[] = {{NULL, NULL, 0, NULL}};
static struct PyModuleDef singlephase_module = {
    PyModuleDef_HEAD_INIT, "b5k_singlephase", NULL, -1, singlephase_methods
};
static PyObject *PyInit_b5k_singlephase(void) {
    return PyModule_Create(&singlephase_module);
}

static int n_failed = 0;

#define CHECK(cond, name)                                        \
    do {                                                         \
        if (cond) {                                              \
            printf("PASS: %s\n", name);                          \
        } else {                                                 \
            printf("FAIL: %s\n", name);                          \
            if (PyErr_Occurred()) PyErr_Print();                 \
            n_failed++;                                          \
        }                                                        \
    } while (0)

/* The audit-mandated sandbox interpreter config. */
static PyInterpreterConfig sandbox_config(void) {
    PyInterpreterConfig config = {
        .use_main_obmalloc = 0,
        .allow_fork = 0,
        .allow_exec = 0,
        .allow_threads = 0,
        .allow_daemon_threads = 0,
        .check_multi_interp_extensions = 1,
        .gil = PyInterpreterConfig_OWN_GIL,
    };
    return config;
}

/* Run source in the CURRENT interpreter; return 0 on success, -1 on error
 * (error printed). */
static int run(const char *source) {
    PyObject *globals = PyDict_New();
    if (!globals) return -1;
    PyDict_SetItemString(globals, "__builtins__", PyEval_GetBuiltins());
    PyObject *res = PyRun_String(source, Py_file_input, globals, globals);
    Py_DECREF(globals);
    if (!res) return -1;
    Py_DECREF(res);
    return 0;
}

/* Fetch `getattr(import_module(mod), attr)` as a raw pointer (borrowed
 * identity only — refcount released before return; used purely for
 * cross-interpreter identity comparison). */
static void *attr_identity(const char *mod, const char *attr) {
    PyObject *m = PyImport_ImportModule(mod);
    if (!m) return NULL;
    PyObject *a = PyObject_GetAttrString(m, attr);
    Py_DECREF(m);
    if (!a) return NULL;
    void *p = (void *)a;
    Py_DECREF(a);
    return p;
}

/* The sandbox primitive under test (real global symbol; no host clash). */
extern PyObject *PyInit__basilisk_sandbox(void);

int main(void) {
    PyImport_AppendInittab("b5k_posix", find_init("posix"));
    PyImport_AppendInittab("b5k_signal", find_init("_signal"));
    PyImport_AppendInittab("b5k_thread", find_init("_thread"));
    PyImport_AppendInittab("b5k_operator", find_init("_operator"));
    PyImport_AppendInittab("b5k_collections", find_init("_collections"));
    PyImport_AppendInittab("b5k_sre", find_init("_sre"));
    PyImport_AppendInittab("b5k_singlephase", PyInit_b5k_singlephase);
    PyImport_AppendInittab("_basilisk_sandbox", PyInit__basilisk_sandbox);

    Py_Initialize();

    /* --- Main interpreter: functional sanity of the converted stubs --- */
    CHECK(run(
        "import b5k_signal, b5k_operator, b5k_collections, b5k_sre\n"
        "import b5k_thread\n"
        "lock = b5k_thread.allocate_lock()\n"
        "assert lock.acquire() is True\n"
        "lock.release()\n"
        "with lock:\n"
        "    pass\n"
        "assert b5k_thread.get_ident() == 1\n"
        "assert isinstance(lock, b5k_thread.LockType)\n"
        "assert b5k_thread.TIMEOUT_MAX > 0\n"
        "import b5k_posix\n"
        "st = b5k_posix.stat('.')\n"
        "assert isinstance(st, b5k_posix.stat_result)\n"
        "assert st.st_mode > 0\n"
        "assert isinstance(b5k_posix.listdir('.'), list)\n"
    ) == 0, "main interpreter: all stubs import and function");

    void *main_stat_result = attr_identity("b5k_posix", "stat_result");
    void *main_lock_type = attr_identity("b5k_thread", "LockType");
    CHECK(main_stat_result && main_lock_type,
          "main interpreter: type identities captured");

    PyThreadState *main_ts = PyThreadState_Get();

    /* --- Subinterpreter with the sandbox config --- */
    {
        PyThreadState_Swap(NULL);
        PyThreadState *sub_ts = NULL;
        PyInterpreterConfig config = sandbox_config();
        PyStatus status = Py_NewInterpreterFromConfig(&sub_ts, &config);
        if (PyStatus_Exception(status)) {
            printf("FAIL: could not create sandbox subinterpreter: %s\n",
                   status.err_msg ? status.err_msg : "?");
            n_failed++;
            PyThreadState_Swap(main_ts);
        }
        else {
            CHECK(run(
                "import b5k_signal, b5k_operator, b5k_collections, b5k_sre\n"
            ) == 0, "subinterpreter: mechanical stubs import under "
                    "check_multi_interp_extensions=1");

            /* The flagged risk: PyType_FromSpec in Py_mod_exec inside a
             * subinterpreter. */
            CHECK(run(
                "import b5k_thread\n"
                "lock = b5k_thread.allocate_lock()\n"
                "assert lock.acquire() is True\n"
                "with lock:\n"
                "    pass\n"
                "assert isinstance(lock, b5k_thread.LockType)\n"
            ) == 0, "subinterpreter: _thread heap type via PyType_FromSpec");

            CHECK(run(
                "import b5k_posix\n"
                "st = b5k_posix.stat('.')\n"
                "assert isinstance(st, b5k_posix.stat_result)\n"
            ) == 0, "subinterpreter: posix with per-module stat_result");

            void *sub_stat_result = attr_identity("b5k_posix", "stat_result");
            void *sub_lock_type = attr_identity("b5k_thread", "LockType");
            CHECK(sub_stat_result && sub_stat_result != main_stat_result,
                  "isolation: posix.stat_result is a distinct type object "
                  "per interpreter");
            CHECK(sub_lock_type && sub_lock_type != main_lock_type,
                  "isolation: _thread.LockType is a distinct type object "
                  "per interpreter");

            /* Negative control: single-phase must be refused. */
            PyObject *sp = PyImport_ImportModule("b5k_singlephase");
            int refused = (sp == NULL) &&
                          PyErr_ExceptionMatches(PyExc_ImportError);
            Py_XDECREF(sp);
            PyErr_Clear();
            CHECK(refused,
                  "negative control: single-phase module REFUSED in "
                  "sandbox subinterpreter");

            Py_EndInterpreter(sub_ts);
            PyThreadState_Swap(main_ts);
        }
    }

    /* --- Sandbox primitive (_basilisk_sandbox) tests --- */
    CHECK(run(
        "import _basilisk_sandbox as sb\n"
        /* Known-answer test for the local SHA-256 (empty string + 'abc'). */
        "assert sb.sha256('') == "
        "'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'\n"
        "assert sb.sha256('abc') == "
        "'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'\n"
    ) == 0, "sandbox: sha256 known-answer vectors");

    CHECK(run(
        "import _basilisk_sandbox as sb\n"
        "src = 'x = 41 + 1'\n"
        "h = sb.sha256(src)\n"
        /* Unapproved hash: refused even though the hash is correct. */
        "try:\n"
        "    sb.spawn_subinterpreter(src, h)\n"
        "    raise AssertionError('unapproved hash was accepted')\n"
        "except PermissionError as e:\n"
        "    assert 'approved-hash registry' in str(e), e\n"
        /* Wrong hash: refused before registry lookup. */
        "sb.approve_hash(h)\n"
        "try:\n"
        "    sb.spawn_subinterpreter(src + ' + 1', h)\n"
        "    raise AssertionError('mismatched hash was accepted')\n"
        "except PermissionError as e:\n"
        "    assert 'hash mismatch' in str(e), e\n"
        /* Malformed hash string. */
        "try:\n"
        "    sb.spawn_subinterpreter(src, 'nothex')\n"
        "    raise AssertionError('malformed hash was accepted')\n"
        "except ValueError:\n"
        "    pass\n"
    ) == 0, "sandbox: hash-mismatch and unapproved-hash refusal");

    CHECK(run(
        "import _basilisk_sandbox as sb\n"
        "src = 'import b5k_collections\\ntotal = sum(range(10))'\n"
        "h = sb.sha256(src)\n"
        /* Approve uppercase, spawn lowercase: normalization must match. */
        "sb.approve_hash(h.upper())\n"
        "handle = sb.spawn_subinterpreter(src, h)\n"
        "assert isinstance(handle, int)\n"
        "sb.close_subinterpreter(handle)\n"
        /* Closing twice must fail cleanly, not crash. */
        "try:\n"
        "    sb.close_subinterpreter(handle)\n"
        "    raise AssertionError('double close accepted')\n"
        "except ValueError:\n"
        "    pass\n"
    ) == 0, "sandbox: spawn + close happy path (uppercase hash tolerated)");

    CHECK(run(
        "import _basilisk_sandbox as sb\n"
        /* Sandboxed exception comes back as TEXT in a host RuntimeError. */
        "src = 'raise ValueError(\"boom from sandbox\")'\n"
        "h = sb.sha256(src)\n"
        "sb.approve_hash(h)\n"
        "try:\n"
        "    sb.spawn_subinterpreter(src, h)\n"
        "    raise AssertionError('failing source did not raise')\n"
        "except RuntimeError as e:\n"
        "    assert 'ValueError: boom from sandbox' in str(e), e\n"
    ) == 0, "sandbox: sandboxed exception propagates as plain text");

    CHECK(run(
        "import _basilisk_sandbox as sb\n"
        /* sys.path is emptied: no filesystem imports inside the sandbox. */
        "src = ('import sys\\n'\n"
        "       'assert sys.path == [], sys.path\\n')\n"
        "h = sb.sha256(src)\n"
        "sb.approve_hash(h)\n"
        "sb.close_subinterpreter(sb.spawn_subinterpreter(src, h))\n"
    ) == 0, "sandbox: sys.path emptied at spawn");

    CHECK(run(
        "import _basilisk_sandbox as sb\n"
        /* THE key invariant: the sandbox module itself must not be
         * importable inside a sandbox (no nested spawning, no registry
         * tampering from sandboxed code). */
        "src = ('ok = False\\n'\n"
        "       'try:\\n'\n"
        "       '    import _basilisk_sandbox\\n'\n"
        "       'except ImportError:\\n'\n"
        "       '    ok = True\\n'\n"
        "       'assert ok, \"_basilisk_sandbox importable in sandbox!\"\\n')\n"
        "h = sb.sha256(src)\n"
        "sb.approve_hash(h)\n"
        "sb.close_subinterpreter(sb.spawn_subinterpreter(src, h))\n"
    ) == 0, "sandbox: _basilisk_sandbox NOT importable inside a sandbox");

    /* --- Phase 3: rpc() boundary + result marshalling --- */
    CHECK(run(
        "import _basilisk_sandbox as sb\n"
        "calls = []\n"
        "def handler(context_id, action, kwargs):\n"
        "    calls.append((context_id, action, kwargs))\n"
        "    if action == 'echo':\n"
        "        return {'you_sent': kwargs, 'n': 42, 'ok': True,\n"
        "                'items': [1, 2.5, None, 'x']}\n"
        "    if action == 'fail':\n"
        "        raise KeyError('secret host detail')\n"
        "    if action == 'bad_result':\n"
        "        return object()\n"
        "    return None\n"
        "src = '''\n"
        "res = rpc('echo', a=1, b=[1, 2, {'c': 'd'}])\n"
        "assert res == {'you_sent': {'a': 1, 'b': [1, 2, {'c': 'd'}]},\n"
        "               'n': 42, 'ok': True, 'items': [1, 2.5, None, 'x']}, res\n"
        "'''\n"
        "h = sb.sha256(src)\n"
        "sb.approve_hash(h)\n"
        "hd = sb.spawn_subinterpreter(src, h, 'ctx-7', ('echo', 'fail', 'bad_result'), handler)\n"
        "sb.close_subinterpreter(hd)\n"
        "assert calls == [('ctx-7', 'echo', {'a': 1, 'b': [1, 2, {'c': 'd'}]})], calls\n"
    ) == 0, "rpc: happy path round-trips plain data + context id");

    CHECK(run(
        "import _basilisk_sandbox as sb\n"
        "def handler(context_id, action, kwargs):\n"
        "    raise AssertionError('handler must not be reached')\n"
        "src = '''\n"
        "try:\n"
        "    rpc('forbidden_action')\n"
        "    raise AssertionError('unauthorized action was allowed')\n"
        "except PermissionError as e:\n"
        "    assert 'allowed_actions' in str(e), e\n"
        "'''\n"
        "h = sb.sha256(src)\n"
        "sb.approve_hash(h)\n"
        "sb.close_subinterpreter(\n"
        "    sb.spawn_subinterpreter(src, h, 'ctx', ('echo',), handler))\n"
    ) == 0, "rpc: action outside allowed_actions refused before handler");

    CHECK(run(
        "import _basilisk_sandbox as sb\n"
        "def handler(context_id, action, kwargs):\n"
        "    raise KeyError('secret host detail')\n"
        "src = '''\n"
        "try:\n"
        "    rpc('fail')\n"
        "    raise AssertionError('failing rpc did not raise')\n"
        "except RuntimeError as e:\n"
        "    # text-only crossing: plain RuntimeError, message text, and\n"
        "    # NO chained host exception object (information disclosure)\n"
        "    assert type(e) is RuntimeError, type(e)\n"
        "    assert 'KeyError' in str(e) and 'secret host detail' in str(e)\n"
        "    assert e.__cause__ is None, e.__cause__\n"
        "    assert e.__context__ is None, e.__context__\n"
        "    assert not hasattr(e, '__notes__')\n"
        "'''\n"
        "h = sb.sha256(src)\n"
        "sb.approve_hash(h)\n"
        "sb.close_subinterpreter(\n"
        "    sb.spawn_subinterpreter(src, h, 'ctx', ('fail',), handler))\n"
    ) == 0, "rpc: handler failure crosses as TEXT-ONLY RuntimeError");

    CHECK(run(
        "import _basilisk_sandbox as sb\n"
        "def handler(context_id, action, kwargs):\n"
        "    return object()  # not plain data\n"
        "src = '''\n"
        "try:\n"
        "    rpc('bad')\n"
        "    raise AssertionError('non-plain result was allowed through')\n"
        "except RuntimeError as e:\n"
        "    assert 'object' in str(e) and 'plain-data' in str(e), e\n"
        "'''\n"
        "h = sb.sha256(src)\n"
        "sb.approve_hash(h)\n"
        "sb.close_subinterpreter(\n"
        "    sb.spawn_subinterpreter(src, h, 'ctx', ('bad',), handler))\n"
    ) == 0, "rpc: non-plain handler result rejected (type name only)");

    CHECK(run(
        "import _basilisk_sandbox as sb\n"
        "src = '''\n"
        "class Sneaky:\n"
        "    pass\n"
        "try:\n"
        "    rpc('echo', obj=Sneaky())\n"
        "    raise AssertionError('non-plain rpc argument was allowed')\n"
        "except TypeError as e:\n"
        "    assert 'Sneaky' in str(e), e\n"
        "'''\n"
        "def handler(context_id, action, kwargs):\n"
        "    raise AssertionError('handler must not be reached')\n"
        "h = sb.sha256(src)\n"
        "sb.approve_hash(h)\n"
        "sb.close_subinterpreter(\n"
        "    sb.spawn_subinterpreter(src, h, 'ctx', ('echo',), handler))\n"
    ) == 0, "rpc: non-plain sandbox arguments rejected at the boundary");

    CHECK(run(
        "import _basilisk_sandbox as sb\n"
        "src = '''\n"
        "state = {'count': 0}\n"
        "def bump(by=1, tags=None):\n"
        "    state['count'] += by\n"
        "    return {'count': state['count'], 'tags': tags,\n"
        "            'big': 2**60, 'pi': 3.5, 'none': None, 'neg': -7}\n"
        "'''\n"
        "h = sb.sha256(src)\n"
        "sb.approve_hash(h)\n"
        "hd = sb.spawn_subinterpreter(src, h)\n"
        "r1 = sb.call_in_subinterpreter(hd, 'bump', {'by': 5, 'tags': ['a', 'b']})\n"
        "assert r1 == {'count': 5, 'tags': ['a', 'b'], 'big': 2**60,\n"
        "              'pi': 3.5, 'none': None, 'neg': -7}, r1\n"
        "r2 = sb.call_in_subinterpreter(hd, 'bump')\n"
        "assert r2['count'] == 6, r2\n"
        "# result is a fresh main-interpreter copy, mutating it is local\n"
        "r2['count'] = 999\n"
        "r3 = sb.call_in_subinterpreter(hd, 'bump')\n"
        "assert r3['count'] == 7, r3\n"
        "# unknown function -> text-only RuntimeError\n"
        "try:\n"
        "    sb.call_in_subinterpreter(hd, 'nope')\n"
        "    raise AssertionError('unknown function did not raise')\n"
        "except RuntimeError as e:\n"
        "    assert 'no callable' in str(e), e\n"
        "# oversized int -> rejected at the boundary, text only\n"
        "try:\n"
        "    sb.call_in_subinterpreter(hd, 'bump', {'by': 2**100})\n"
        "    raise AssertionError('>64-bit int crossed the boundary')\n"
        "except TypeError as e:\n"
        "    assert '64 bits' in str(e), e\n"
        "sb.close_subinterpreter(hd)\n"
    ) == 0, "call_in_subinterpreter: marshalling, statefulness, errors");

    /* --- Phase 4: instruction metering --- */
    CHECK(run(
        "import _basilisk_sandbox as sb\n"
        "src = 'while True:\\n    pass\\n'\n"
        "h = sb.sha256(src)\n"
        "sb.approve_hash(h)\n"
        "try:\n"
        "    sb.spawn_subinterpreter(src, h, '', (), None, 50000)\n"
        "    raise AssertionError('infinite loop did not trip the budget')\n"
        "except RuntimeError as e:\n"
        "    assert 'BudgetExceeded' in str(e), e\n"
        "    assert 'instruction budget (50000) exhausted' in str(e), e\n"
    ) == 0, "metering: infinite loop trips BudgetExceeded at the limit");

    CHECK(run(
        "import _basilisk_sandbox as sb\n"
        "src = '''\n"
        "total = sum(range(1000))\n"
        "def f():\n"
        "    return sum(range(1000))\n"
        "'''\n"
        "h = sb.sha256(src)\n"
        "sb.approve_hash(h)\n"
        "hd = sb.spawn_subinterpreter(src, h, '', (), None, 50000)\n"
        "assert sb.call_in_subinterpreter(hd, 'f') == 499500\n"
        "sb.close_subinterpreter(hd)\n"
    ) == 0, "metering: within-budget code completes normally");

    CHECK(run(
        "import _basilisk_sandbox as sb\n"
        "src = '''\n"
        "def burn(n=10**9):\n"
        "    i = 0\n"
        "    while i < n:\n"
        "        i += 1\n"
        "'''\n"
        "h = sb.sha256(src)\n"
        "sb.approve_hash(h)\n"
        "hd = sb.spawn_subinterpreter(src, h, '', (), None, 50000)\n"
        "try:\n"
        "    sb.call_in_subinterpreter(hd, 'burn')\n"
        "    raise AssertionError('call did not trip the budget')\n"
        "except RuntimeError as e:\n"
        "    assert 'BudgetExceeded' in str(e), e\n"
        "sb.close_subinterpreter(hd)\n"
        "# budget is per-spawn: a fresh spawn is fresh again\n"
        "hd2 = sb.spawn_subinterpreter(src, h, '', (), None, 50000)\n"
        "sb.close_subinterpreter(hd2)\n"
    ) == 0, "metering: budget applies to call_in_subinterpreter, per-spawn");

    CHECK(run(
        "import _basilisk_sandbox as sb\n"
        "src = '''\n"
        "caught = 0\n"
        "try:\n"
        "    while True:\n"
        "        pass\n"
        "except BudgetExceeded:\n"
        "    caught = 1\n"
        "    while True:\n"
        "        pass  # still metered: re-trips immediately\n"
        "'''\n"
        "h = sb.sha256(src)\n"
        "sb.approve_hash(h)\n"
        "try:\n"
        "    sb.spawn_subinterpreter(src, h, '', (), None, 50000)\n"
        "    raise AssertionError('except: resumed unmetered execution')\n"
        "except RuntimeError as e:\n"
        "    # after the grace window the meter hard-kills: the sandbox is\n"
        "    # terminated regardless of its except handler\n"
        "    assert 'budget' in str(e) and 'exhausted' in str(e), e\n"
        "    assert 'terminated after grace period' in str(e), e\n"
    ) == 0, "metering: catching BudgetExceeded cannot resume execution");

    CHECK(run(
        "# main interpreter is NEVER metered: run far more instructions\n"
        "# than any sandbox budget used above, while a metered sandbox\n"
        "# handle is live, and complete fine.\n"
        "import _basilisk_sandbox as sb\n"
        "src = 'x = 1'\n"
        "h = sb.sha256(src)\n"
        "sb.approve_hash(h)\n"
        "hd = sb.spawn_subinterpreter(src, h, '', (), None, 1000000)\n"
        "i = 0\n"
        "while i < 3000000:\n"
        "    i += 1\n"
        "assert i == 3000000\n"
        "sb.close_subinterpreter(hd)\n"
    ) == 0, "metering: main interpreter runs unmetered");

    /* --- Phase 6: reflection / namespace escape attempts ---
     *
     * Each attempt runs INSIDE a sandbox and asserts, from within, that the
     * escape fails; a failed in-sandbox assert propagates to the host as a
     * text-only RuntimeError, so the spawn call returning normally IS the
     * proof that every escape was refused. None of these may expose a host
     * object, host state, or a traceback across the boundary. */

    CHECK(run(
        "import _basilisk_sandbox as sb\n"
        /* (a) import _basilisk_ic and (b) import basilisk: the privileged
         * host surface and the basilisk shim must be unreachable. On host
         * neither is present; on wasm _basilisk_ic is single-phase and
         * refused fail-closed by check_multi_interp_extensions. */
        "src = ('for m in (\"_basilisk_ic\", \"basilisk\"):\\n'\n"
        "       '    ok = False\\n'\n"
        "       '    try:\\n'\n"
        "       '        __import__(m)\\n'\n"
        "       '    except ImportError:\\n'\n"
        "       '        ok = True\\n'\n"
        "       '    assert ok, m + \" importable in sandbox\"\\n')\n"
        "h = sb.sha256(src)\n"
        "sb.approve_hash(h)\n"
        "sb.close_subinterpreter(sb.spawn_subinterpreter(src, h))\n"
    ) == 0, "escape: import _basilisk_ic / basilisk both refused");

    CHECK(run(
        "import _basilisk_sandbox as sb\n"
        /* (c) __subclasses__() walk from object: exhaustively traverse the
         * subclass graph reachable inside the sandbox and assert NO class
         * belongs to a host-privileged module — i.e. the classic gadget
         * cannot reach host-side types. */
        "src = ('bad = (\"_basilisk_ic\", \"_basilisk_sandbox\", \"basilisk\")\\n'\n"
        "       'seen = set()\\n'\n"
        "       'stack = [object]\\n'\n"
        "       'while stack:\\n'\n"
        "       '    c = stack.pop()\\n'\n"
        "       '    if id(c) in seen:\\n'\n"
        "       '        continue\\n'\n"
        "       '    seen.add(id(c))\\n'\n"
        "       '    m = str(getattr(c, \"__module__\", \"\"))\\n'\n"
        "       '    assert not any(b in m for b in bad), m\\n'\n"
        "       '    stack.extend(type.__subclasses__(c))\\n'\n"
        "       'assert len(seen) > 0\\n')\n"
        "h = sb.sha256(src)\n"
        "sb.approve_hash(h)\n"
        "sb.close_subinterpreter(sb.spawn_subinterpreter(src, h))\n"
    ) == 0, "escape: __subclasses__() walk reaches no host-privileged type");

    CHECK(run(
        "import _basilisk_sandbox as sb\n"
        /* (d) __globals__ / __builtins__ on reachable callables expose no
         * host references, and the injected rpc() C function has no
         * __globals__ to pivot through. */
        "src = ('def f():\\n'\n"
        "       '    return 1\\n'\n"
        "       'g = f.__globals__\\n'\n"
        "       'assert \"_basilisk_ic\" not in g\\n'\n"
        "       'assert \"_basilisk_sandbox\" not in g\\n'\n"
        "       'assert not hasattr(rpc, \"__globals__\")\\n'\n"
        "       'b = g.get(\"__builtins__\")\\n'\n"
        "       'bd = b if isinstance(b, dict) else vars(b)\\n'\n"
        "       'assert \"_basilisk_ic\" not in bd\\n'\n"
        "       'assert \"_basilisk_sandbox\" not in bd\\n'\n"
        "       'import sys\\n'\n"
        "       'assert \"_basilisk_ic\" not in sys.modules\\n'\n"
        "       'assert \"_basilisk_sandbox\" not in sys.modules\\n')\n"
        "h = sb.sha256(src)\n"
        "sb.approve_hash(h)\n"
        "sb.close_subinterpreter(sb.spawn_subinterpreter(src, h))\n"
    ) == 0, "escape: __globals__/__builtins__ expose no host references");

    CHECK(run(
        "import _basilisk_sandbox as sb\n"
        /* (e) __import__ of anything outside the sandbox's approved set is
         * refused. The approved set is exactly the FROZEN/builtin modules
         * baked into the interpreter image (audit sec C/D) — those load
         * without sys.path by design. Everything that needs sys.path (i.e.
         * arbitrary on-disk code) and every privileged Basilisk surface is
         * unreachable, because sys.path == [] and those modules are neither
         * frozen nor builtin. NOTE: `os` IS a frozen stdlib module in
         * CPython, hence intentionally importable here; on the canister its
         * dangerous surface is neutered because the underlying `posix` is a
         * Basilisk stub. */
        "src = ('for m in (\"subprocess\", \"socket\", \"ctypes\",\\n'\n"
        "       '          \"_basilisk_ic\", \"_basilisk_sandbox\", \"basilisk\"):\\n'\n"
        "       '    ok = False\\n'\n"
        "       '    try:\\n'\n"
        "       '        __import__(m)\\n'\n"
        "       '    except ImportError:\\n'\n"
        "       '        ok = True\\n'\n"
        "       '    assert ok, \"imported \" + m\\n')\n"
        "h = sb.sha256(src)\n"
        "sb.approve_hash(h)\n"
        "sb.close_subinterpreter(sb.spawn_subinterpreter(src, h))\n"
    ) == 0, "escape: __import__ of unapproved (sys.path/privileged) modules "
            "refused");

    CHECK(run(
        "import _basilisk_sandbox as sb\n"
        /* (f) rpc() with an action outside allowed_actions: refused at the
         * C gate BEFORE the handler runs, as a clean PermissionError. */
        "def handler(context_id, action, kwargs):\n"
        "    raise AssertionError('handler must not be reached')\n"
        "src = ('try:\\n'\n"
        "       '    rpc(\"delete_everything\")\\n'\n"
        "       '    raise AssertionError(\"forbidden action allowed\")\\n'\n"
        "       'except PermissionError as e:\\n'\n"
        "       '    assert \"allowed_actions\" in str(e), e\\n')\n"
        "h = sb.sha256(src)\n"
        "sb.approve_hash(h)\n"
        "sb.close_subinterpreter(\n"
        "    sb.spawn_subinterpreter(src, h, 'ctx', ('get_object',), handler))\n"
    ) == 0, "escape: rpc() with disallowed action refused at C gate");

    CHECK(run(
        "import _basilisk_sandbox as sb\n"
        /* (g) rpc() re-entrancy: while an rpc call is being serviced
         * (in_rpc latched), a re-entry into the SAME sandbox is refused.
         * Driven from the host: reenter() calls rpc('cb'); the handler,
         * running with the rpc in flight, tries to call back into the same
         * handle and is refused with a re-entrant-call error. */
        "state = {}\n"
        "def handler(context_id, action, kwargs):\n"
        "    if action == 'cb':\n"
        "        try:\n"
        "            sb.call_in_subinterpreter(state['h'], 'reenter')\n"
        "            state['reentry'] = 'ALLOWED'\n"
        "        except RuntimeError as e:\n"
        "            state['reentry'] = str(e)\n"
        "        return {'ok': True}\n"
        "    return None\n"
        "src = 'def reenter():\\n    return rpc(\"cb\")\\n'\n"
        "h = sb.sha256(src)\n"
        "sb.approve_hash(h)\n"
        "state['h'] = sb.spawn_subinterpreter(src, h, 'ctx', ('cb',), handler)\n"
        "r = sb.call_in_subinterpreter(state['h'], 'reenter')\n"
        "assert r == {'ok': True}, r\n"
        "assert 're-entrant' in state.get('reentry', ''), state\n"
        "sb.close_subinterpreter(state['h'])\n"
    ) == 0, "escape: rpc() re-entrancy into the same sandbox refused");

    CHECK(run(
        "import _basilisk_sandbox as sb\n"
        /* (h) spawn_subinterpreter from inside a sandbox: _basilisk_sandbox
         * is not importable in a subinterpreter (exec-slot guard), so the
         * spawn primitive and hash registry are unreachable. Re-confirm. */
        "src = ('ok = False\\n'\n"
        "       'try:\\n'\n"
        "       '    import _basilisk_sandbox\\n'\n"
        "       'except ImportError:\\n'\n"
        "       '    ok = True\\n'\n"
        "       'assert ok, \"_basilisk_sandbox importable in sandbox\"\\n')\n"
        "h = sb.sha256(src)\n"
        "sb.approve_hash(h)\n"
        "sb.close_subinterpreter(sb.spawn_subinterpreter(src, h))\n"
    ) == 0, "escape: spawn primitive unreachable inside a sandbox");

    /* --- Repeated spawn/teardown: per-module state lifecycle smoke --- */
    {
        int cycles_ok = 1;
        for (int i = 0; i < 100 && cycles_ok; i++) {
            PyThreadState_Swap(NULL);
            PyThreadState *sub_ts = NULL;
            PyInterpreterConfig config = sandbox_config();
            PyStatus status = Py_NewInterpreterFromConfig(&sub_ts, &config);
            if (PyStatus_Exception(status)) {
                cycles_ok = 0;
                PyThreadState_Swap(main_ts);
                break;
            }
            if (run("import b5k_thread, b5k_posix\n"
                    "l = b5k_thread.allocate_lock()\n"
                    "s = b5k_posix.stat('.')\n") != 0) {
                cycles_ok = 0;
            }
            Py_EndInterpreter(sub_ts);
            PyThreadState_Swap(main_ts);
        }
        CHECK(cycles_ok, "100x spawn/import/teardown cycles");
    }

    Py_Finalize();

    if (n_failed) {
        printf("\n%d test(s) FAILED\n", n_failed);
        return 1;
    }
    printf("\nAll subinterpreter harness tests passed\n");
    return 0;
}
