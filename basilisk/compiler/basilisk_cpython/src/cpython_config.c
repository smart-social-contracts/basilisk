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
 * IC/WASI has no POSIX filesystem. Provides stubs that importlib's
 * _bootstrap_external needs (stat, getcwd, listdir) so PathFinder
 * gracefully skips all filesystem paths. */

#include <errno.h>

static PyObject* _posix_stat(PyObject *self, PyObject *args, PyObject *kwargs) {
    errno = ENOENT;
    PyErr_SetFromErrnoWithFilename(PyExc_OSError, "");
    return NULL;
}
static PyObject* _posix_lstat(PyObject *self, PyObject *args, PyObject *kwargs) {
    return _posix_stat(self, args, kwargs);
}
static PyObject* _posix_getcwd(PyObject *self, PyObject *args) {
    return PyUnicode_FromString("/");
}
static PyObject* _posix_listdir(PyObject *self, PyObject *args) {
    return PyList_New(0);
}
static PyObject* _posix_fspath(PyObject *self, PyObject *args) {
    PyObject *path;
    if (!PyArg_ParseTuple(args, "O", &path)) return NULL;
    return PyOS_FSPath(path);
}
static PyMethodDef _posix_stub_methods[] = {
    {"stat",    (PyCFunction)_posix_stat,    METH_VARARGS | METH_KEYWORDS, NULL},
    {"lstat",   (PyCFunction)_posix_lstat,   METH_VARARGS | METH_KEYWORDS, NULL},
    {"getcwd",  _posix_getcwd,               METH_NOARGS, NULL},
    {"listdir", _posix_listdir,              METH_VARARGS, NULL},
    {"fspath",  _posix_fspath,               METH_VARARGS, NULL},
    {NULL, NULL, 0, NULL}
};
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
 * IC is single-threaded. _thread MUST be in _inittab (required by importlib
 * bootstrap in CPython 3.13). Provides no-op Lock/RLock using a static type
 * (avoids PyType_FromSpec which corrupts interpreter state during early init). */

typedef struct {
    PyObject_HEAD
} _thread_lock_object;

static PyObject* _lock_acquire(PyObject *self, PyObject *args, PyObject *kwargs) {
    Py_RETURN_TRUE;
}
static PyObject* _lock_release(PyObject *self, PyObject *args) {
    Py_RETURN_NONE;
}
static PyObject* _lock_enter(PyObject *self, PyObject *args) {
    Py_INCREF(self);
    return self;
}
static PyObject* _lock_exit(PyObject *self, PyObject *args) {
    Py_RETURN_FALSE;
}

static PyMethodDef _lock_methods[] = {
    {"acquire",     (PyCFunction)_lock_acquire, METH_VARARGS | METH_KEYWORDS, NULL},
    {"acquire_lock",(PyCFunction)_lock_acquire, METH_VARARGS | METH_KEYWORDS, NULL},
    {"release",     (PyCFunction)_lock_release, METH_VARARGS, NULL},
    {"release_lock",(PyCFunction)_lock_release, METH_VARARGS, NULL},
    {"__enter__",   (PyCFunction)_lock_enter,   METH_NOARGS, NULL},
    {"__exit__",    (PyCFunction)_lock_exit,    METH_VARARGS, NULL},
    {NULL, NULL, 0, NULL}
};

static PyObject* _lock_new(PyTypeObject *type, PyObject *args, PyObject *kwargs) {
    PyObject *self = type->tp_alloc(type, 0);
    return self;
}

static PyTypeObject _thread_lock_type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "_thread.lock",
    .tp_basicsize = sizeof(_thread_lock_object),
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_methods = _lock_methods,
    .tp_new = _lock_new,
};

static PyObject* _thread_allocate_lock(PyObject *self, PyObject *args) {
    return _lock_new(&_thread_lock_type, NULL, NULL);
}
static PyObject* _thread_get_ident(PyObject *self, PyObject *args) {
    return PyLong_FromLong(1);
}
static PyObject* _thread_count(PyObject *self, PyObject *args) {
    return PyLong_FromLong(1);
}

static PyMethodDef _thread_stub_methods[] = {
    {"allocate_lock", _thread_allocate_lock, METH_NOARGS, NULL},
    {"allocate",      _thread_allocate_lock, METH_NOARGS, NULL},
    {"get_ident",     _thread_get_ident,     METH_NOARGS, NULL},
    {"_count",        _thread_count,         METH_NOARGS, NULL},
    {NULL, NULL, 0, NULL}
};
static struct PyModuleDef _thread_stub_module = {
    PyModuleDef_HEAD_INIT, "_thread", NULL, -1, _thread_stub_methods
};
static PyObject* PyInit__thread(void) {
    if (PyType_Ready(&_thread_lock_type) < 0) return NULL;
    PyObject *module = PyModule_Create(&_thread_stub_module);
    if (!module) return NULL;
    Py_INCREF(&_thread_lock_type);
    PyModule_AddObject(module, "LockType", (PyObject*)&_thread_lock_type);
    Py_INCREF(&_thread_lock_type);
    PyModule_AddObject(module, "RLock", (PyObject*)&_thread_lock_type);
    PyModule_AddObject(module, "TIMEOUT_MAX", PyFloat_FromDouble(1e15));
    return module;
}

/* NOTE: Non-essential modules removed for wasm size reduction.
 * See CPYTHON_MIGRATION_NOTES.md section 8 for details.
 * Removed: time, _tracemalloc, _locale, _contextvars, itertools,
 *          _symtable, _tokenize, _suggestions, _sysconfig
 */

/* JSON C accelerator — restored for fast serialization (DB operations) */
extern PyObject* PyInit__json(void);

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
    {"_thread", PyInit__thread},  /* stub — _threadmodule.o removed, static type Lock/RLock */
    {"_typing", PyInit__typing},
    {"_weakref", PyInit__weakref},
    {"atexit", PyInit_atexit},
    {"errno", PyInit_errno},
    {"gc", PyInit_gc},

    /* Modules needed during Py_Initialize */
    {"_signal", PyInit__signal},

    /* JSON C accelerator — restored for fast serialization */
    {"_json", PyInit__json},

    /* Internal modules (always needed by interpreter core) */
    {"marshal", PyMarshal_Init},
    {"_imp", PyInit__imp},
    {"_warnings", _PyWarnings_Init},

    /* Sentinel */
    {0, 0}
};
