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

/* Enhanced posix stub — posixmodule.o removed to save ~457K.
 * Provides real filesystem access via ic-wasi-polyfill's virtual filesystem.
 *
 * ic-wasi-polyfill (already a dependency) intercepts all WASI syscalls and
 * provides a virtual in-memory filesystem. This stub forwards key posix
 * operations to standard C library functions, which the WASI SDK maps to
 * WASI syscalls intercepted by the polyfill.
 *
 * Only commonly-needed operations are implemented. The full posixmodule.o
 * (~457K) contains hundreds of functions (fork, exec, pipe, chmod, etc.)
 * that are irrelevant on the IC.
 *
 * See CPYTHON_MIGRATION_NOTES.md section 9 for details.
 */

#include <errno.h>
#include <sys/stat.h>
#include <dirent.h>
#include <unistd.h>
#include <stdio.h>
#include <string.h>

/* --- stat_result type (PyStructSequence matching CPython's os.stat_result) --- */

static PyTypeObject *StatResultType = NULL;

static PyStructSequence_Field stat_result_fields[] = {
    {"st_mode",  "protection bits"},
    {"st_ino",   "inode"},
    {"st_dev",   "device"},
    {"st_nlink", "number of hard links"},
    {"st_uid",   "user ID of owner"},
    {"st_gid",   "group ID of owner"},
    {"st_size",  "total size, in bytes"},
    {"st_atime", "time of last access"},
    {"st_mtime", "time of last modification"},
    {"st_ctime", "time of last change"},
    {0}
};

static PyStructSequence_Desc stat_result_desc = {
    "posix.stat_result",
    NULL,
    stat_result_fields,
    10
};

static PyObject* _make_stat_result(const struct stat *st) {
    PyObject *v = PyStructSequence_New(StatResultType);
    if (!v) return NULL;
    PyStructSequence_SET_ITEM(v, 0, PyLong_FromLong(st->st_mode));
    PyStructSequence_SET_ITEM(v, 1, PyLong_FromUnsignedLongLong(st->st_ino));
    PyStructSequence_SET_ITEM(v, 2, PyLong_FromUnsignedLongLong(st->st_dev));
    PyStructSequence_SET_ITEM(v, 3, PyLong_FromLong(st->st_nlink));
    PyStructSequence_SET_ITEM(v, 4, PyLong_FromLong(st->st_uid));
    PyStructSequence_SET_ITEM(v, 5, PyLong_FromLong(st->st_gid));
    PyStructSequence_SET_ITEM(v, 6, PyLong_FromLongLong(st->st_size));
    PyStructSequence_SET_ITEM(v, 7, PyFloat_FromDouble(
        (double)st->st_atim.tv_sec + (double)st->st_atim.tv_nsec * 1e-9));
    PyStructSequence_SET_ITEM(v, 8, PyFloat_FromDouble(
        (double)st->st_mtim.tv_sec + (double)st->st_mtim.tv_nsec * 1e-9));
    PyStructSequence_SET_ITEM(v, 9, PyFloat_FromDouble(
        (double)st->st_ctim.tv_sec + (double)st->st_ctim.tv_nsec * 1e-9));
    if (PyErr_Occurred()) {
        Py_DECREF(v);
        return NULL;
    }
    return v;
}

/* --- posix.stat(path, *, dir_fd=None, follow_symlinks=True) --- */
static PyObject* _posix_stat(PyObject *self, PyObject *args, PyObject *kwargs) {
    static char *kwlist[] = {"path", "dir_fd", "follow_symlinks", NULL};
    PyObject *path_obj;
    PyObject *dir_fd = Py_None;
    int follow_symlinks = 1;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|Op", kwlist,
                                      &path_obj, &dir_fd, &follow_symlinks))
        return NULL;

    const char *path;
    if (PyUnicode_Check(path_obj)) {
        path = PyUnicode_AsUTF8(path_obj);
        if (!path) return NULL;
    } else {
        PyErr_SetString(PyExc_TypeError, "stat: path should be string");
        return NULL;
    }

    struct stat st;
    int ret;
    if (follow_symlinks) {
        ret = stat(path, &st);
    } else {
        ret = lstat(path, &st);
    }

    if (ret != 0) {
        PyErr_SetFromErrnoWithFilename(PyExc_OSError, path);
        return NULL;
    }

    return _make_stat_result(&st);
}

/* --- posix.lstat(path, *, dir_fd=None) --- */
static PyObject* _posix_lstat(PyObject *self, PyObject *args, PyObject *kwargs) {
    static char *kwlist[] = {"path", "dir_fd", NULL};
    PyObject *path_obj;
    PyObject *dir_fd = Py_None;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|O", kwlist,
                                      &path_obj, &dir_fd))
        return NULL;

    const char *path;
    if (PyUnicode_Check(path_obj)) {
        path = PyUnicode_AsUTF8(path_obj);
        if (!path) return NULL;
    } else {
        PyErr_SetString(PyExc_TypeError, "lstat: path should be string");
        return NULL;
    }

    struct stat st;
    if (lstat(path, &st) != 0) {
        PyErr_SetFromErrnoWithFilename(PyExc_OSError, path);
        return NULL;
    }

    return _make_stat_result(&st);
}

/* --- posix.getcwd() --- */
static PyObject* _posix_getcwd(PyObject *self, PyObject *args) {
    char buf[4096];
    if (getcwd(buf, sizeof(buf)) != NULL) {
        return PyUnicode_FromString(buf);
    }
    return PyUnicode_FromString("/");
}

/* --- posix.listdir(path='.') --- */
static PyObject* _posix_listdir(PyObject *self, PyObject *args) {
    const char *path = ".";
    if (!PyArg_ParseTuple(args, "|s", &path))
        return NULL;

    DIR *dir = opendir(path);
    if (!dir) {
        PyErr_SetFromErrnoWithFilename(PyExc_OSError, path);
        return NULL;
    }

    PyObject *list = PyList_New(0);
    if (!list) {
        closedir(dir);
        return NULL;
    }

    struct dirent *entry;
    while ((entry = readdir(dir)) != NULL) {
        if (strcmp(entry->d_name, ".") == 0 || strcmp(entry->d_name, "..") == 0)
            continue;
        PyObject *name = PyUnicode_FromString(entry->d_name);
        if (!name) {
            Py_DECREF(list);
            closedir(dir);
            return NULL;
        }
        if (PyList_Append(list, name) < 0) {
            Py_DECREF(name);
            Py_DECREF(list);
            closedir(dir);
            return NULL;
        }
        Py_DECREF(name);
    }

    closedir(dir);
    return list;
}

/* --- posix.mkdir(path, mode=0o777, *, dir_fd=None) --- */
static PyObject* _posix_mkdir(PyObject *self, PyObject *args, PyObject *kwargs) {
    static char *kwlist[] = {"path", "mode", "dir_fd", NULL};
    const char *path;
    int mode = 0777;
    PyObject *dir_fd = Py_None;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s|iO", kwlist,
                                      &path, &mode, &dir_fd))
        return NULL;

    if (mkdir(path, (mode_t)mode) != 0) {
        PyErr_SetFromErrnoWithFilename(PyExc_OSError, path);
        return NULL;
    }

    Py_RETURN_NONE;
}

/* --- posix.unlink(path, *, dir_fd=None) --- */
static PyObject* _posix_unlink(PyObject *self, PyObject *args, PyObject *kwargs) {
    static char *kwlist[] = {"path", "dir_fd", NULL};
    const char *path;
    PyObject *dir_fd = Py_None;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s|O", kwlist,
                                      &path, &dir_fd))
        return NULL;

    if (unlink(path) != 0) {
        PyErr_SetFromErrnoWithFilename(PyExc_OSError, path);
        return NULL;
    }

    Py_RETURN_NONE;
}

/* --- posix.rmdir(path, *, dir_fd=None) --- */
static PyObject* _posix_rmdir(PyObject *self, PyObject *args, PyObject *kwargs) {
    static char *kwlist[] = {"path", "dir_fd", NULL};
    const char *path;
    PyObject *dir_fd = Py_None;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s|O", kwlist,
                                      &path, &dir_fd))
        return NULL;

    if (rmdir(path) != 0) {
        PyErr_SetFromErrnoWithFilename(PyExc_OSError, path);
        return NULL;
    }

    Py_RETURN_NONE;
}

/* --- posix.rename(src, dst, *, src_dir_fd=None, dst_dir_fd=None) --- */
static PyObject* _posix_rename(PyObject *self, PyObject *args, PyObject *kwargs) {
    static char *kwlist[] = {"src", "dst", "src_dir_fd", "dst_dir_fd", NULL};
    const char *src;
    const char *dst;
    PyObject *src_dir_fd = Py_None;
    PyObject *dst_dir_fd = Py_None;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "ss|OO", kwlist,
                                      &src, &dst, &src_dir_fd, &dst_dir_fd))
        return NULL;

    if (rename(src, dst) != 0) {
        PyErr_SetFromErrnoWithFilename(PyExc_OSError, src);
        return NULL;
    }

    Py_RETURN_NONE;
}

/* --- posix.fspath(path) --- */
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
    {"mkdir",   (PyCFunction)_posix_mkdir,   METH_VARARGS | METH_KEYWORDS, NULL},
    {"unlink",  (PyCFunction)_posix_unlink,  METH_VARARGS | METH_KEYWORDS, NULL},
    {"rmdir",   (PyCFunction)_posix_rmdir,   METH_VARARGS | METH_KEYWORDS, NULL},
    {"rename",  (PyCFunction)_posix_rename,  METH_VARARGS | METH_KEYWORDS, NULL},
    {"fspath",  _posix_fspath,               METH_VARARGS, NULL},
    {NULL, NULL, 0, NULL}
};
static struct PyModuleDef _posix_stub_module = {
    PyModuleDef_HEAD_INIT, "posix", NULL, -1, _posix_stub_methods
};
static PyObject* PyInit_posix(void) {
    /* Create stat_result type */
    StatResultType = PyStructSequence_NewType(&stat_result_desc);
    if (StatResultType == NULL)
        return NULL;

    PyObject *module = PyModule_Create(&_posix_stub_module);
    if (!module) return NULL;

    /* Add stat_result type to module (needed by os.stat) */
    Py_INCREF(StatResultType);
    if (PyModule_AddObject(module, "stat_result", (PyObject *)StatResultType) < 0) {
        Py_DECREF(StatResultType);
        Py_DECREF(module);
        return NULL;
    }

    return module;
}

/* PyOS_FSPath — converts path-like object to string/bytes. */
PyObject* PyOS_FSPath(PyObject *path) {
    if (PyUnicode_Check(path)) {
        Py_INCREF(path);
        return path;
    }
    if (PyBytes_Check(path)) {
        Py_INCREF(path);
        return path;
    }
    /* Check for __fspath__ method */
    PyObject *func = PyObject_GetAttrString(path, "__fspath__");
    if (func) {
        PyObject *result = PyObject_CallNoArgs(func);
        Py_DECREF(func);
        return result;
    }
    PyErr_Clear();
    PyErr_Format(PyExc_TypeError,
                 "expected str, bytes or os.PathLike object, not %.200s",
                 Py_TYPE(path)->tp_name);
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
