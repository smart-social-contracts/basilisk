/*
 * Makes Basilisk's _thread STUB the real "_thread" of the host python.
 *
 * The harness build deletes _threadmodule.o from a copy of the host
 * libpython3.13.a; the archive's config.o inittab entry {"_thread",
 * PyInit__thread} then resolves to this shim, which dispatches to the stub's
 * (static) init function through the renamed wasm inittab.
 *
 * This is the decisive test for the audit's flagged _thread risk: importlib's
 * _bootstrap._setup() imports "_thread" with no fallback during EVERY
 * interpreter's early init — main interpreter and each subinterpreter — so
 * with this shim in place, Py_Initialize() and Py_NewInterpreterFromConfig()
 * only succeed if the multi-phase stub (PyType_FromSpec inside Py_mod_exec)
 * survives that early-init path.
 */
#include <Python.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern struct _inittab b5k_wasm_inittab[];

/* _threadmodule.o also exported this fork hook; the harness never forks. */
void _PyThread_AfterFork(void *state) {}

PyObject *PyInit__thread(void) {
    for (struct _inittab *p = b5k_wasm_inittab; p->name != NULL; p++) {
        if (strcmp(p->name, "_thread") == 0) {
            return p->initfunc();
        }
    }
    fprintf(stderr, "fatal: _thread not in wasm inittab\n");
    exit(1);
}
