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
extern PyObject* PyInit_posix(void);
extern PyObject* PyInit__io(void);
extern PyObject* PyInit__abc(void);
extern PyObject* PyInit__codecs(void);
extern PyObject* PyInit__collections(void);
extern PyObject* PyInit__functools(void);
extern PyObject* PyInit__operator(void);
extern PyObject* PyInit__sre(void);
extern PyObject* PyInit__stat(void);
extern PyObject* PyInit__string(void);
extern PyObject* PyInit__struct(void);
extern PyObject* PyInit__thread(void);
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
    {"_collections", PyInit__collections},
    {"_functools", PyInit__functools},
    {"_operator", PyInit__operator},
    {"_sre", PyInit__sre},
    {"_stat", PyInit__stat},
    {"_string", PyInit__string},
    {"_struct", PyInit__struct},
    {"_thread", PyInit__thread},
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
