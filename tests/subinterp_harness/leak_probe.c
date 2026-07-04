/*
 * Leak probe: measures heap growth across spawn/close cycles of the
 * sandbox-config subinterpreter, in several variants, to localize the
 * ~70 KiB/cycle linear-memory ratchet observed on wasm.
 *
 * Uses mallinfo2's uordblks (bytes in use) — on glibc this counts live
 * malloc'd bytes, so a per-cycle delta is a true leak (not fragmentation).
 */
#include <Python.h>
#include <malloc.h>
#include <stdio.h>

/* Referenced by the renamed (unused) wasm inittab; never called on host. */
PyObject *b5k_dummy_PyInit__struct(void) { return NULL; }
PyObject *b5k_dummy_PyInit__json(void) { return NULL; }

static long heap_in_use(void) {
    struct mallinfo2 mi = mallinfo2();
    return (long)(mi.uordblks + mi.hblkhd);
}

/* Internal CPython symbol (exported from libpython): count of obmalloc
 * blocks still allocated in an interpreter. If nonzero at Py_EndInterpreter,
 * obmalloc "leaks" ALL the interpreter's arenas by design (see
 * _PyInterpreterState_FinalizeAllocatedBlocks in Objects/obmalloc.c). */
extern Py_ssize_t _PyInterpreterState_GetAllocatedBlocks(PyInterpreterState *);

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

/* One spawn/close cycle. variant: 0 = bare spawn/end; 1 = + run source. */
static int cycle(int variant, const char *source) {
    PyThreadState *main_ts = PyThreadState_Get();
    PyThreadState *sub_ts = NULL;
    PyInterpreterConfig config = sandbox_config();
    PyThreadState_Swap(NULL);
    PyStatus status = Py_NewInterpreterFromConfig(&sub_ts, &config);
    if (PyStatus_Exception(status)) {
        PyThreadState_Swap(main_ts);
        fprintf(stderr, "spawn failed: %s\n",
                status.err_msg ? status.err_msg : "?");
        return -1;
    }
    if (variant >= 1) {
        PyObject *globals = PyDict_New();
        PyDict_SetItemString(globals, "__builtins__", PyEval_GetBuiltins());
        PyObject *r = PyRun_String(source, Py_file_input, globals, globals);
        if (r == NULL) {
            PyErr_Print();
        }
        Py_XDECREF(r);
        Py_DECREF(globals);
    }
    Py_EndInterpreter(sub_ts);
    PyThreadState_Swap(main_ts);
    return 0;
}

/* Exported internal: total live obmalloc blocks across interpreters PLUS
 * runtime->obmalloc.interpreter_leaks (blocks that survived teardown of
 * ended interpreters). Its per-cycle delta == blocks leaked per cycle. */
extern Py_ssize_t _Py_GetGlobalAllocatedBlocks(void);

static void measure(const char *label, int variant, const char *source,
                    int warmup, int cycles) {
    for (int i = 0; i < warmup; i++) {
        if (cycle(variant, source) != 0) return;
    }
    long before = heap_in_use();
    Py_ssize_t blocks_before = _Py_GetGlobalAllocatedBlocks();
    for (int i = 0; i < cycles; i++) {
        if (cycle(variant, source) != 0) return;
    }
    long after = heap_in_use();
    Py_ssize_t blocks_after = _Py_GetGlobalAllocatedBlocks();
    printf("%-38s %6ld bytes/cycle, %5zd leaked obmalloc blocks/cycle\n",
           label, (after - before) / cycles,
           (blocks_after - blocks_before) / cycles);
}

int main(void) {
    Py_Initialize();

    measure("bare spawn/end", 0, NULL, 20, 200);
    measure("+ empty source", 1, "pass\n", 20, 200);
    measure("+ allocations", 1,
            "data = [list(range(100)) for _ in range(50)]\n", 20, 200);
    measure("+ import _thread (heap type)", 1, "import _thread\n", 20, 200);
    measure("+ import sys", 1, "import sys\n", 20, 200);

    Py_Finalize();
    return 0;
}
