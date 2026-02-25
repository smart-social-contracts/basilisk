/*
 * Custom CPython module configuration for IC canisters (wasm32-wasip1).
 *
 * This replaces the stock config.o from libpython3.13.a to control which
 * built-in extension modules are linked into the final wasm binary.
 *
 * Only modules required for CPython boot (Py_Initialize) and basic canister
 * operation are included. Removing a module from this table prevents the
 * linker from pulling in its object file, significantly reducing wasm size.
 *
 * See CPYTHON_MIGRATION_NOTES.md section 7 for the full module classification
 * and instructions on adding/removing modules.
 */

#include "Python.h"

/*
 * Forward declarations for init functions of included modules.
 *
 * MINIMAL set — only what Py_Initialize absolutely requires.
 * Modules removed vs. stock CPython 3.13 config.c:
 *   _tracemalloc  — memory tracing (skipped during init if missing)
 *   faulthandler  — crash handler (skipped during init if missing)
 *   _symtable     — only needed for compile()
 *   _tokenize     — only needed for tokenize module
 *   _suggestions  — nicer error messages, not essential
 *   _locale       — locale support, not needed on IC
 *   _sysconfig    — build-time config, not needed at runtime
 *   itertools     — common but not boot-critical
 *   _contextvars  — context variables, not needed for basic operation
 *   _signal       — signal handling, not useful on IC/WASI
 *   time          — may be needed; add back if init fails
 */
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

/* These are always needed by the interpreter core */
extern PyObject* PyMarshal_Init(void);
extern PyObject* PyInit__imp(void);
extern PyObject* _PyWarnings_Init(void);

struct _inittab _PyImport_Inittab[] = {
    /* Absolute minimum for Py_Initialize to complete */
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

    /* Internal modules (always needed by interpreter core) */
    {"marshal", PyMarshal_Init},
    {"_imp", PyInit__imp},
    {"_warnings", _PyWarnings_Init},

    /* Sentinel */
    {0, 0}
};
