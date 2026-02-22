/*
 * CPython initialization helper for IC/WASI.
 *
 * Uses _init_main=0 for core-only initialization (skips sys.streams
 * setup which requires encodings). Core init is sufficient for running
 * Python code — our Rust layer handles __main__ and builtins.
 */

#include "Python.h"

static int basilisk_init_done = 0;

int basilisk_cpython_is_initialized(void) {
    return basilisk_init_done;
}

/* Initialize CPython core only (no main phase).
 * Returns 0 on success, 1 on failure. */
int basilisk_cpython_init(void) {
    if (basilisk_init_done || Py_IsInitialized()) {
        return 0;
    }

    PyConfig config;
    PyConfig_InitIsolatedConfig(&config);

    config.use_frozen_modules = 1;
    config.install_signal_handlers = 0;
    config.site_import = 0;
    config.pathconfig_warnings = 0;
    config._is_python_build = 0;
    config._init_main = 0;

    PyStatus status = Py_InitializeFromConfig(&config);
    PyConfig_Clear(&config);

    if (PyStatus_Exception(status)) {
        return 1;
    }

    basilisk_init_done = 1;
    return 0;
}
