/*
 * Symbol renames for compiling src/cpython_config.c against a HOST (native)
 * libpython3.13.a for testing, instead of the wasm32-wasip1 one.
 *
 * The host archive already contains the real posix/_thread/_signal/... module
 * objects and the stock config.o inittab, so every symbol cpython_config.c
 * exports would clash at link time. This header (force-included via
 * `-include`) renames them all with a b5k_ prefix. The SOURCE under test is
 * byte-identical to what ships in the wasm build; only linkage names change.
 *
 * Used only by tests/subinterp_harness — never by the real build.
 */
#ifndef BASILISK_HOST_RENAME_H
#define BASILISK_HOST_RENAME_H

/* The inittab: the host archive's config.o provides the real one. */
#define _PyImport_Inittab b5k_wasm_inittab

/* Stub module init functions (real ones exist in the host archive). */
#define PyInit_posix b5k_PyInit_posix
#define PyInit__signal b5k_PyInit__signal
#define PyInit__thread b5k_PyInit__thread
#define PyInit__operator b5k_PyInit__operator
#define PyInit__collections b5k_PyInit__collections
#define PyInit__sre b5k_PyInit__sre

/* Referenced by the (renamed, unused) inittab but built as shared .so on the
 * host, so the symbols are absent from the archive. The harness provides
 * dummy definitions; they are never called. */
#define PyInit__struct b5k_dummy_PyInit__struct
#define PyInit__json b5k_dummy_PyInit__json

/* C-level stubs that duplicate real host libpython symbols. */
#define PyOS_FSPath b5k_PyOS_FSPath
#define _PySignal_Init b5k__PySignal_Init
#define _PySignal_Fini b5k__PySignal_Fini
#define PyErr_CheckSignals b5k_PyErr_CheckSignals
#define _PyErr_CheckSignalsTstate b5k__PyErr_CheckSignalsTstate
#define _PyOS_InterruptOccurred b5k__PyOS_InterruptOccurred
#define PyErr_SetInterruptEx b5k_PyErr_SetInterruptEx
#define _PyFaulthandler_Init b5k__PyFaulthandler_Init
#define _PyFaulthandler_Fini b5k__PyFaulthandler_Fini
#define _PyPerfTrampoline_Init b5k__PyPerfTrampoline_Init
#define _PyPerfTrampoline_Fini b5k__PyPerfTrampoline_Fini
#define _PyPerfTrampoline_FreeArenas b5k__PyPerfTrampoline_FreeArenas

#endif /* BASILISK_HOST_RENAME_H */
