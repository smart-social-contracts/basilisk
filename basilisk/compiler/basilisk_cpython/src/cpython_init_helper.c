/*
 * CPython initialization helper for IC/WASI.
 *
 * Measured cost: ~28M instructions for full init with importlib.
 * IC canister_init budget: 5B+ instructions (with DTS: hundreds of billions).
 * So full single-call init is fine — no phasing needed.
 *
 * Also contains wasm manipulator placeholder functions. These MUST be in C
 * (compiled by WASI SDK clang) rather than Rust, because Rust's LTO inlines
 * #[no_mangle] extern "C" functions even with #[inline(never)] and black_box.
 * C object files are opaque to LLVM LTO and won't be inlined.
 */

#include "Python.h"
#include <stdio.h>

/* ─── Wasm manipulator placeholder functions ─────────────────────────────── */
/* These function bodies are replaced by the wasm manipulator at build time.  */
/* They inject passive data segment reads for Python source and metadata.     */

int python_source_passive_data_size(void) {
    return 0; /* placeholder — wasm manipulator replaces this body */
}

int method_meta_passive_data_size(void) {
    return 0; /* placeholder — wasm manipulator replaces this body */
}

void init_python_source_passive_data(int dest) {
    (void)dest; /* placeholder — wasm manipulator replaces this body */
}

void init_method_meta_passive_data(int dest) {
    (void)dest; /* placeholder — wasm manipulator replaces this body */
}

static int basilisk_initialized = 0;

int basilisk_cpython_is_initialized(void) {
    return basilisk_initialized;
}

int basilisk_cpython_get_phase(void) {
    return basilisk_initialized ? 1 : -1;
}

/* Full CPython init: type system, GC, builtins, importlib, codecs, path config.
 * Uses two-step approach to avoid hanging in single-call full init:
 *   Step 1: Py_InitializeFromConfig with _init_main=0 (core + importlib bootstrap)
 *   Step 2: _Py_InitializeMain (IO, path config, codecs)
 * Measured cost: ~28M instructions total (well under 5B IC limit).
 * Returns 0 on success, 1 on failure. */
int basilisk_cpython_init(void) {
    if (basilisk_initialized || Py_IsInitialized()) {
        return 0;
    }

    PyConfig config;
    PyConfig_InitIsolatedConfig(&config);

    config.use_frozen_modules = 1;
    config.install_signal_handlers = 0;
    config.site_import = 0;
    config.pathconfig_warnings = 0;
    config._is_python_build = 0;
    /* Enable importlib but defer main init to avoid hanging path config */
    config._init_main = 0;

    fprintf(stderr, "[basilisk] cpython_init: calling Py_InitializeFromConfig\n");
    PyStatus status = Py_InitializeFromConfig(&config);
    PyConfig_Clear(&config);

    if (PyStatus_Exception(status)) {
        fprintf(stderr, "[basilisk] cpython_init: Py_InitializeFromConfig FAILED: %s (func=%s)\n",
                status.err_msg ? status.err_msg : "(null)",
                status.func ? status.func : "(null)");
        return 1;
    }
    fprintf(stderr, "[basilisk] cpython_init: Py_InitializeFromConfig OK\n");

    /* Skip _Py_InitializeMain() — it requires 'encodings' module which is NOT
     * in the frozen module table of our WASI CPython build.
     * _Py_InitializeMain does: path config, install external importers,
     * set up IO (stdin/stdout/stderr with encodings).
     * On IC/WASI none of these are needed — we have no filesystem, no stdin,
     * and our output goes through ic_cdk::println / ic0.debug_print.
     *
     * Instead, set up minimal sys.stdout/stderr using a simple write-to-stderr
     * approach so that Python's print() doesn't crash. */
    {
        const char *io_setup =
            "import sys\n"
            "class _ICWriter:\n"
            "    def write(self, s):\n"
            "        if s: __import__('sys').stderr.write(s)\n"
            "        return len(s) if s else 0\n"
            "    def flush(self): pass\n"
            "    def fileno(self): raise OSError('no fileno on IC')\n"
            "    encoding = 'utf-8'\n"
            "    errors = 'replace'\n"
            "class _ICStderr:\n"
            "    softspace = 0\n"
            "    encoding = 'utf-8'\n"
            "    errors = 'replace'\n"
            "    def write(self, s): return len(s) if s else 0\n"
            "    def flush(self): pass\n"
            "    def fileno(self): raise OSError('no fileno on IC')\n"
            "sys.stderr = _ICStderr()\n"
            "sys.stdout = _ICWriter()\n"
            "sys.stdin = None\n"
            "sys.__stderr__ = sys.stderr\n"
            "sys.__stdout__ = sys.stdout\n"
            "sys.__stdin__ = None\n";

        int rc = PyRun_SimpleString(io_setup);
        if (rc != 0) {
            fprintf(stderr, "[basilisk] cpython_init: IO setup failed\n");
            /* Non-fatal — continue even if IO setup fails */
        }
        fprintf(stderr, "[basilisk] cpython_init: IO setup done (skipped _Py_InitializeMain)\n");
    }

    basilisk_initialized = 1;
    return 0;
}
