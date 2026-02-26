/*
 * Custom CPython module configuration for IC canisters (wasm32-wasip1).
 *
 * This replaces the stock config.o from libpython3.13.a to control which
 * built-in extension modules are linked into the final wasm binary.
 *
 * Includes all CPython internal modules needed for Py_Initialize and basic
 * canister operation. Only heavy modules with external library dependencies
 * are excluded (_decimal/libmpdec, pyexpat/libexpat, _hashlib/HACL*).
 *
 * See CPYTHON_MIGRATION_NOTES.md section 7 for details.
 */

#include "Python.h"

/* --- Forward declarations for all included modules --- */

/* Core modules required by Py_Initialize / importlib bootstrap */
extern PyObject* PyInit__io(void);
extern PyObject* PyInit__abc(void);
extern PyObject* PyInit__codecs(void);
extern PyObject* PyInit__functools(void);
extern PyObject* PyInit__stat(void);
extern PyObject* PyInit__string(void);
extern PyObject* PyInit__struct(void);
/* _thread stubbed — IC is single-threaded */
extern PyObject* PyInit__typing(void);
extern PyObject* PyInit__weakref(void);
extern PyObject* PyInit_atexit(void);
extern PyObject* PyInit_errno(void);
extern PyObject* PyInit_gc(void);

/* Minimal _signal stub — signalmodule.o removed to save ~179K.
 * All stubs in C to guarantee correct ABI (especially PyStatus).
 */
static PyMethodDef _signal_stub_methods[] = {{NULL, NULL, 0, NULL}};
static struct PyModuleDef _signal_stub_module = {
    PyModuleDef_HEAD_INIT, "_signal", NULL, -1, _signal_stub_methods
};
static PyObject* PyInit__signal(void) {
    return PyModule_Create(&_signal_stub_module);
}

/* Signal internal stubs */
int _PySignal_Init(int install_signal_handlers) { return 0; }
void _PySignal_Fini(void) {}
int PyErr_CheckSignals(void) { return 0; }
int _PyErr_CheckSignalsTstate(void *tstate) { return 0; }
int _PyOS_InterruptOccurred(void *tstate) { return 0; }
int PyErr_SetInterruptEx(int signum) { return 0; }

/* Faulthandler internal stubs (config.faulthandler=0 on WASI) */
PyStatus _PyFaulthandler_Init(int enable) {
    PyStatus status = {0};
    return status;
}
void _PyFaulthandler_Fini(void) {}

/* Perf trampoline stubs (Linux-only, N/A on IC) */
int _PyPerfTrampoline_Init(int activate) { return 0; }
int _PyPerfTrampoline_Fini(void) { return 0; }
void _PyPerfTrampoline_FreeArenas(void) {}

/* Minimal posix stub — posixmodule.o removed to save ~457K.
 * IC/WASI has no POSIX filesystem. Frozen modules don't need file ops. */
static PyMethodDef _posix_stub_methods[] = {{NULL, NULL, 0, NULL}};
static struct PyModuleDef _posix_stub_module = {
    PyModuleDef_HEAD_INIT, "posix", NULL, -1, _posix_stub_methods
};
static PyObject* PyInit_posix(void) {
    return PyModule_Create(&_posix_stub_module);
}

/* PyOS_FSPath — converts path-like object to string/bytes.
 * On IC, just return the argument if it's already a string. */
PyObject* PyOS_FSPath(PyObject *path) {
    if (PyUnicode_Check(path)) {
        Py_INCREF(path);
        return path;
    }
    if (PyBytes_Check(path)) {
        Py_INCREF(path);
        return path;
    }
    PyErr_SetString(PyExc_TypeError, "expected str or bytes path on IC");
    return NULL;
}

/* Minimal _operator stub — _operator.o removed to save ~256K.
 * Pure Python fallback in operator.py handles all functionality. */
static PyMethodDef _operator_stub_methods[] = {{NULL, NULL, 0, NULL}};
static struct PyModuleDef _operator_stub_module = {
    PyModuleDef_HEAD_INIT, "_operator", NULL, -1, _operator_stub_methods
};
static PyObject* PyInit__operator(void) {
    return PyModule_Create(&_operator_stub_module);
}

/* Minimal _collections stub — _collectionsmodule.o removed to save ~265K.
 * Pure Python fallback in collections/__init__.py handles deque, OrderedDict. */
static PyMethodDef _collections_stub_methods[] = {{NULL, NULL, 0, NULL}};
static struct PyModuleDef _collections_stub_module = {
    PyModuleDef_HEAD_INIT, "_collections", NULL, -1, _collections_stub_methods
};
static PyObject* PyInit__collections(void) {
    return PyModule_Create(&_collections_stub_module);
}

/* Minimal _sre stub — sre.o removed to save ~334K.
 * If user code needs regex, pure Python re fallback would be needed. */
static PyMethodDef _sre_stub_methods[] = {{NULL, NULL, 0, NULL}};
static struct PyModuleDef _sre_stub_module = {
    PyModuleDef_HEAD_INIT, "_sre", NULL, -1, _sre_stub_methods
};
static PyObject* PyInit__sre(void) {
    return PyModule_Create(&_sre_stub_module);
}

/* Minimal _thread stub — _threadmodule.o removed to save ~252K.
 * IC is single-threaded. Stub provides lock no-ops for CPython internals. */
static PyMethodDef _thread_stub_methods[] = {{NULL, NULL, 0, NULL}};
static struct PyModuleDef _thread_stub_module = {
    PyModuleDef_HEAD_INIT, "_thread", NULL, -1, _thread_stub_methods
};
static PyObject* PyInit__thread(void) {
    return PyModule_Create(&_thread_stub_module);
}

/* NOTE: Non-essential modules removed for wasm size reduction.
 * See CPYTHON_MIGRATION_NOTES.md section 8 for details.
 * Removed: time, _tracemalloc, _locale, _contextvars, itertools,
 *          _symtable, _tokenize, _suggestions, _sysconfig
 */

/* Internal modules (always needed by interpreter core) */
extern PyObject* PyMarshal_Init(void);
extern PyObject* PyInit__imp(void);
extern PyObject* _PyWarnings_Init(void);

struct _inittab _PyImport_Inittab[] = {
    /* Core modules for Py_Initialize */
    {"posix", PyInit_posix},
    {"_io", PyInit__io},
    {"_abc", PyInit__abc},
    {"_codecs", PyInit__codecs},
    {"_collections", PyInit__collections},  /* stub — _collectionsmodule.o removed */
    {"_functools", PyInit__functools},
    {"_operator", PyInit__operator},  /* stub — _operator.o removed */
    {"_sre", PyInit__sre},  /* stub — sre.o removed */
    {"_stat", PyInit__stat},
    {"_string", PyInit__string},
    {"_struct", PyInit__struct},
    {"_thread", PyInit__thread},  /* stub — _threadmodule.o removed */
    {"_typing", PyInit__typing},
    {"_weakref", PyInit__weakref},
    {"atexit", PyInit_atexit},
    {"errno", PyInit_errno},
    {"gc", PyInit_gc},

    /* Modules needed during Py_Initialize */
    {"_signal", PyInit__signal},

    /* Internal modules (always needed by interpreter core) */
    {"marshal", PyMarshal_Init},
    {"_imp", PyInit__imp},
    {"_warnings", _PyWarnings_Init},

    /* Sentinel */
    {0, 0}
};
