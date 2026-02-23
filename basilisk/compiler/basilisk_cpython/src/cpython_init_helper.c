/*
 * CPython initialization helper for IC/WASI.
 *
 * Measured cost: ~28M instructions for full init with importlib.
 * IC canister_init budget: 5B+ instructions (with DTS: hundreds of billions).
 * So full single-call init is fine — no phasing needed.
 */

#include "Python.h"

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

    PyStatus status = Py_InitializeFromConfig(&config);
    PyConfig_Clear(&config);

    if (PyStatus_Exception(status)) {
        return 1;
    }

    /* Complete initialization (IO, path config, codecs) */
    status = _Py_InitializeMain();
    if (PyStatus_Exception(status)) {
        return 1;
    }

    basilisk_initialized = 1;
    return 0;
}
