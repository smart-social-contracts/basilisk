//! Stub implementations for C symbols that CPython's static library (`libpython3.13.a`)
//! references but are not available in the IC/WASI environment.
//!
//! ## Why these stubs exist
//!
//! When CPython is compiled to `wasm32-wasip1`, the static library includes object files
//! for several extension modules that depend on external C libraries:
//!
//! - **pyexpat** → expat XML parser (`PyExpat_XML_*` symbols)
//! - **_decimal** → mpdecimal arbitrary-precision decimal library (`mpd_*` symbols)
//! - **_hashlib** → HACL* cryptographic hash library (`python_hashlib_Hacl_*` symbols)
//! - **dlopen/dlsym/dlerror** → dynamic library loading (not available in WASI)
//! - **PyModule_Create** → CPython module creation (resolved differently in embedded use)
//!
//! These external symbols become unresolved wasm `"env"` imports. The `wasi2ic` tool
//! (which converts WASI wasm to IC-compatible wasm) rejects any remaining `"env"` imports
//! because the IC runtime cannot provide them.
//!
//! ## Design decision
//!
//! Rather than rebuilding CPython with these modules disabled (which requires modifying
//! `Modules/Setup.local` and re-running the ~30min cross-compilation), we provide no-op
//! stub functions here. This is a **temporary pragmatic solution** for the E2E proof of
//! concept. The proper long-term fix is to rebuild CPython with:
//!
//! ```text
//! # In Modules/Setup.local:
//! *disabled*
//! _decimal
//! pyexpat
//! _hashlib
//! ```
//!
//! ## Safety
//!
//! These stubs are `#[no_mangle] extern "C"` functions that return zero/null. If Python
//! code actually tries to use `decimal`, `xml.parsers.expat`, or `hashlib` at runtime,
//! it will get incorrect results or a Python-level error — but it won't crash the canister.
//! For the IC use case, none of these modules are expected to be needed.

#![allow(non_snake_case)]
#![allow(unused_variables)]

use core::ffi::c_char;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Null pointer constant for returning from stub functions.
const NULL: *mut u8 = core::ptr::null_mut();

// ---------------------------------------------------------------------------
// dlopen / dlsym / dlerror  (dynamic loading — not available in WASI)
// ---------------------------------------------------------------------------

#[no_mangle]
pub unsafe extern "C" fn dlopen(filename: *const c_char, flags: i32) -> *mut u8 { NULL }

#[no_mangle]
pub unsafe extern "C" fn dlsym(handle: *mut u8, symbol: *const c_char) -> *mut u8 { NULL }

#[no_mangle]
pub unsafe extern "C" fn dlerror() -> *const c_char { core::ptr::null() }

// ---------------------------------------------------------------------------
// PyModule_Create  (CPython C API — needed by extension modules)
// ---------------------------------------------------------------------------

#[no_mangle]
pub unsafe extern "C" fn PyModule_Create(module_def: *mut u8) -> *mut u8 { NULL }

// ---------------------------------------------------------------------------
// pyexpat — expat XML parser stubs
// ---------------------------------------------------------------------------

macro_rules! xml_stub_ptr {
    ($name:ident $(, $arg:ident : $ty:ty)*) => {
        #[no_mangle]
        pub unsafe extern "C" fn $name($($arg: $ty),*) -> *mut u8 { NULL }
    };
}

macro_rules! xml_stub_void {
    ($name:ident $(, $arg:ident : $ty:ty)*) => {
        #[no_mangle]
        pub unsafe extern "C" fn $name($($arg: $ty),*) {}
    };
}

macro_rules! xml_stub_int {
    ($name:ident $(, $arg:ident : $ty:ty)*) => {
        #[no_mangle]
        pub unsafe extern "C" fn $name($($arg: $ty),*) -> i32 { 0 }
    };
}

// Parser lifecycle
xml_stub_ptr!(PyExpat_XML_ParserCreate_MM, encoding: *const c_char, memsuite: *mut u8, sep: *const c_char);
xml_stub_void!(PyExpat_XML_ParserFree, parser: *mut u8);
xml_stub_ptr!(PyExpat_XML_ExternalEntityParserCreate, parser: *mut u8, context: *const c_char, encoding: *const c_char);

// Parsing
xml_stub_int!(PyExpat_XML_Parse, parser: *mut u8, s: *const c_char, len: i32, is_final: i32);
xml_stub_int!(PyExpat_XML_ParseBuffer, parser: *mut u8, len: i32, is_final: i32);
xml_stub_ptr!(PyExpat_XML_GetBuffer, parser: *mut u8, len: i32);
xml_stub_int!(PyExpat_XML_StopParser, parser: *mut u8, resumable: i32);

// Error handling
xml_stub_int!(PyExpat_XML_GetErrorCode, parser: *mut u8);
xml_stub_ptr!(PyExpat_XML_ErrorString, code: i32);
xml_stub_int!(PyExpat_XML_GetCurrentLineNumber, parser: *mut u8);
xml_stub_int!(PyExpat_XML_GetCurrentColumnNumber, parser: *mut u8);
xml_stub_int!(PyExpat_XML_GetCurrentByteIndex, parser: *mut u8);

// Configuration
xml_stub_int!(PyExpat_XML_SetEncoding, parser: *mut u8, encoding: *const c_char);
xml_stub_int!(PyExpat_XML_SetBase, parser: *mut u8, base: *const c_char);
xml_stub_ptr!(PyExpat_XML_GetBase, parser: *mut u8);
xml_stub_int!(PyExpat_XML_GetSpecifiedAttributeCount, parser: *mut u8);
xml_stub_int!(PyExpat_XML_SetParamEntityParsing, parser: *mut u8, parsing: i32);
xml_stub_int!(PyExpat_XML_SetHashSalt, parser: *mut u8, salt: u64);
xml_stub_void!(PyExpat_XML_SetUserData, parser: *mut u8, user_data: *mut u8);
xml_stub_void!(PyExpat_XML_SetReturnNSTriplet, parser: *mut u8, do_nst: i32);
xml_stub_int!(PyExpat_XML_UseForeignDTD, parser: *mut u8, use_dtd: i32);
xml_stub_void!(PyExpat_XML_SetReparseDeferralEnabled, parser: *mut u8, enabled: i32);

// Handler setters (all take parser + callback pointer)
xml_stub_void!(PyExpat_XML_SetElementHandler, parser: *mut u8, start: *mut u8, end: *mut u8);
xml_stub_void!(PyExpat_XML_SetCharacterDataHandler, parser: *mut u8, handler: *mut u8);
xml_stub_void!(PyExpat_XML_SetProcessingInstructionHandler, parser: *mut u8, handler: *mut u8);
xml_stub_void!(PyExpat_XML_SetCommentHandler, parser: *mut u8, handler: *mut u8);
xml_stub_void!(PyExpat_XML_SetDefaultHandler, parser: *mut u8, handler: *mut u8);
xml_stub_void!(PyExpat_XML_SetDefaultHandlerExpand, parser: *mut u8, handler: *mut u8);
xml_stub_void!(PyExpat_XML_SetStartElementHandler, parser: *mut u8, handler: *mut u8);
xml_stub_void!(PyExpat_XML_SetEndElementHandler, parser: *mut u8, handler: *mut u8);
xml_stub_void!(PyExpat_XML_SetUnparsedEntityDeclHandler, parser: *mut u8, handler: *mut u8);
xml_stub_void!(PyExpat_XML_SetNotationDeclHandler, parser: *mut u8, handler: *mut u8);
xml_stub_void!(PyExpat_XML_SetStartNamespaceDeclHandler, parser: *mut u8, handler: *mut u8);
xml_stub_void!(PyExpat_XML_SetEndNamespaceDeclHandler, parser: *mut u8, handler: *mut u8);
xml_stub_void!(PyExpat_XML_SetNamespaceDeclHandler, parser: *mut u8, start: *mut u8, end: *mut u8);
xml_stub_void!(PyExpat_XML_SetStartCdataSectionHandler, parser: *mut u8, handler: *mut u8);
xml_stub_void!(PyExpat_XML_SetEndCdataSectionHandler, parser: *mut u8, handler: *mut u8);
xml_stub_void!(PyExpat_XML_SetNotStandaloneHandler, parser: *mut u8, handler: *mut u8);
xml_stub_void!(PyExpat_XML_SetExternalEntityRefHandler, parser: *mut u8, handler: *mut u8);
xml_stub_void!(PyExpat_XML_SetStartDoctypeDeclHandler, parser: *mut u8, handler: *mut u8);
xml_stub_void!(PyExpat_XML_SetEndDoctypeDeclHandler, parser: *mut u8, handler: *mut u8);
xml_stub_void!(PyExpat_XML_SetEntityDeclHandler, parser: *mut u8, handler: *mut u8);
xml_stub_void!(PyExpat_XML_SetXmlDeclHandler, parser: *mut u8, handler: *mut u8);
xml_stub_void!(PyExpat_XML_SetElementDeclHandler, parser: *mut u8, handler: *mut u8);
xml_stub_void!(PyExpat_XML_SetAttlistDeclHandler, parser: *mut u8, handler: *mut u8);
xml_stub_void!(PyExpat_XML_SetSkippedEntityHandler, parser: *mut u8, handler: *mut u8);
xml_stub_void!(PyExpat_XML_SetUnknownEncodingHandler, parser: *mut u8, handler: *mut u8, data: *mut u8);
xml_stub_void!(PyExpat_XML_FreeContentModel, parser: *mut u8, model: *mut u8);

// Version info
xml_stub_ptr!(PyExpat_XML_ExpatVersion);
#[no_mangle]
pub unsafe extern "C" fn PyExpat_XML_ExpatVersionInfo() -> u64 { 0 }
xml_stub_ptr!(PyExpat_XML_GetFeatureList);
xml_stub_ptr!(PyExpat_XML_GetInputContext, parser: *mut u8, offset: *mut i32, size: *mut i32);

// ---------------------------------------------------------------------------
// _decimal — mpdecimal library stubs
// ---------------------------------------------------------------------------

// Context setup
#[no_mangle] pub unsafe extern "C" fn mpd_qsetprec(ctx: *mut u8, prec: i64) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_qsetround(ctx: *mut u8, round: i32) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_qsetemin(ctx: *mut u8, emin: i64) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_qsetemax(ctx: *mut u8, emax: i64) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_qsetclamp(ctx: *mut u8, clamp: i32) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_qsettraps(ctx: *mut u8, traps: u32) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_qsetstatus(ctx: *mut u8, status: u32) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_maxcontext(ctx: *mut u8) {}
#[no_mangle] pub unsafe extern "C" fn mpd_setminalloc(n: i64) {}

// Context getters
#[no_mangle] pub unsafe extern "C" fn mpd_getprec(ctx: *const u8) -> i64 { 28 }
#[no_mangle] pub unsafe extern "C" fn mpd_getround(ctx: *const u8) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_getemin(ctx: *const u8) -> i64 { -999999 }
#[no_mangle] pub unsafe extern "C" fn mpd_getemax(ctx: *const u8) -> i64 { 999999 }
#[no_mangle] pub unsafe extern "C" fn mpd_getclamp(ctx: *const u8) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_etiny(ctx: *const u8) -> i64 { -999999 }
#[no_mangle] pub unsafe extern "C" fn mpd_etop(ctx: *const u8) -> i64 { 999999 }

// Allocation
#[no_mangle] pub unsafe extern "C" fn mpd_callocfunc_em(nmemb: usize, size: usize) -> *mut u8 { NULL }
#[no_mangle] pub unsafe extern "C" fn mpd_qnew() -> *mut u8 { NULL }
#[no_mangle] pub unsafe extern "C" fn mpd_qncopy(a: *const u8) -> *mut u8 { NULL }
#[no_mangle] pub unsafe extern "C" fn mpd_del(dec: *mut u8) {}

// String conversion
#[no_mangle] pub unsafe extern "C" fn mpd_to_sci(dec: *const u8, fmt: i32) -> *mut c_char { core::ptr::null_mut() }
#[no_mangle] pub unsafe extern "C" fn mpd_to_sci_size(result: *mut *mut c_char, dec: *const u8, fmt: i32) -> i64 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_to_eng_size(result: *mut *mut c_char, dec: *const u8, fmt: i32) -> i64 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_qset_string(dec: *mut u8, s: *const c_char, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_parse_fmt_str(spec: *mut u8, fmt: *const c_char, caps: i32) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_qformat_spec(dec: *const u8, spec: *const u8, ctx: *mut u8, status: *mut u32) -> *mut c_char { core::ptr::null_mut() }
#[no_mangle] pub unsafe extern "C" fn mpd_validate_lconv(spec: *mut u8) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_lsnprint_signals(dest: *mut c_char, nmemb: usize, flags: u32, signal_string: *const *const c_char) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_version() -> *const c_char { b"stub\0".as_ptr() as *const c_char }

// Integer get/set
#[no_mangle] pub unsafe extern "C" fn mpd_qset_ssize(dec: *mut u8, val: i64, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qsset_ssize(dec: *mut u8, val: i64, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qset_uint(dec: *mut u8, val: u64, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qget_ssize(dec: *const u8, status: *mut u32) -> i64 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_qimport_u32(dec: *mut u8, src: *const u32, srclen: usize, srcsign: u8, base: u32, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qexport_u32(rdata: *mut *mut u32, rlen: *mut usize, base: u32, src: *const u8, status: *mut u32) -> usize { 0 }

// Predicates
#[no_mangle] pub unsafe extern "C" fn mpd_isspecial(dec: *const u8) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_issnan(dec: *const u8) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_isnan(dec: *const u8) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_isqnan(dec: *const u8) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_isinfinite(dec: *const u8) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_isfinite(dec: *const u8) -> i32 { 1 }
#[no_mangle] pub unsafe extern "C" fn mpd_iszero(dec: *const u8) -> i32 { 1 }
#[no_mangle] pub unsafe extern "C" fn mpd_ispositive(dec: *const u8) -> i32 { 1 }
#[no_mangle] pub unsafe extern "C" fn mpd_isnegative(dec: *const u8) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_issigned(dec: *const u8) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_isnormal(dec: *const u8, ctx: *const u8) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_issubnormal(dec: *const u8, ctx: *const u8) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_iscanonical(dec: *const u8) -> i32 { 1 }
#[no_mangle] pub unsafe extern "C" fn mpd_isdynamic_data(dec: *const u8) -> i32 { 0 }

// Sign/flag manipulation
#[no_mangle] pub unsafe extern "C" fn mpd_arith_sign(dec: *const u8) -> u8 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_sign(dec: *const u8) -> u8 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_set_positive(dec: *mut u8) {}
#[no_mangle] pub unsafe extern "C" fn mpd_set_sign(dec: *mut u8, sign: u8) {}
#[no_mangle] pub unsafe extern "C" fn mpd_set_flags(dec: *mut u8, flags: u8) {}
#[no_mangle] pub unsafe extern "C" fn mpd_clear_flags(dec: *mut u8) {}
#[no_mangle] pub unsafe extern "C" fn mpd_seterror(dec: *mut u8, flags: u32, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_setspecial(dec: *mut u8, sign: u8, typ: u8) {}
#[no_mangle] pub unsafe extern "C" fn mpd_setdigits(dec: *mut u8) {}
#[no_mangle] pub unsafe extern "C" fn mpd_adjexp(dec: *const u8) -> i64 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_class(dec: *const u8, ctx: *const u8) -> *const c_char { b"sNaN\0".as_ptr() as *const c_char }
#[no_mangle] pub unsafe extern "C" fn mpd_same_quantum(a: *const u8, b: *const u8) -> i32 { 0 }

// Arithmetic operations
#[no_mangle] pub unsafe extern "C" fn mpd_qcopy(result: *mut u8, a: *const u8, status: *mut u32) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_qcopy_abs(result: *mut u8, a: *const u8, status: *mut u32) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_qcopy_negate(result: *mut u8, a: *const u8, status: *mut u32) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_qcopy_sign(result: *mut u8, a: *const u8, b: *const u8, status: *mut u32) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_qadd(result: *mut u8, a: *const u8, b: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qsub(result: *mut u8, a: *const u8, b: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qmul(result: *mut u8, a: *const u8, b: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qdiv(result: *mut u8, a: *const u8, b: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qdivint(result: *mut u8, a: *const u8, b: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qdivmod(q: *mut u8, r: *mut u8, a: *const u8, b: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qrem(result: *mut u8, a: *const u8, b: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qrem_near(result: *mut u8, a: *const u8, b: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qpow(result: *mut u8, base: *const u8, exp: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qpowmod(result: *mut u8, base: *const u8, exp: *const u8, modl: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qfma(result: *mut u8, a: *const u8, b: *const u8, c: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qabs(result: *mut u8, a: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qminus(result: *mut u8, a: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qplus(result: *mut u8, a: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qsqrt(result: *mut u8, a: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qexp(result: *mut u8, a: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qln(result: *mut u8, a: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qlog10(result: *mut u8, a: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qlogb(result: *mut u8, a: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qscaleb(result: *mut u8, a: *const u8, b: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qquantize(result: *mut u8, a: *const u8, b: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qreduce(result: *mut u8, a: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qfinalize(result: *mut u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qround_to_int(result: *mut u8, a: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qround_to_intx(result: *mut u8, a: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qnext_minus(result: *mut u8, a: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qnext_plus(result: *mut u8, a: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qnext_toward(result: *mut u8, a: *const u8, b: *const u8, ctx: *mut u8, status: *mut u32) {}

// Comparison
#[no_mangle] pub unsafe extern "C" fn mpd_qcmp(a: *const u8, b: *const u8, status: *mut u32) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_qcompare(result: *mut u8, a: *const u8, b: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qcompare_signal(result: *mut u8, a: *const u8, b: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_compare_total(result: *mut u8, a: *const u8, b: *const u8) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_compare_total_mag(result: *mut u8, a: *const u8, b: *const u8) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn mpd_qmax(result: *mut u8, a: *const u8, b: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qmax_mag(result: *mut u8, a: *const u8, b: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qmin(result: *mut u8, a: *const u8, b: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qmin_mag(result: *mut u8, a: *const u8, b: *const u8, ctx: *mut u8, status: *mut u32) {}

// Bitwise / shift
#[no_mangle] pub unsafe extern "C" fn mpd_qand(result: *mut u8, a: *const u8, b: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qor(result: *mut u8, a: *const u8, b: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qxor(result: *mut u8, a: *const u8, b: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qinvert(result: *mut u8, a: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qshift(result: *mut u8, a: *const u8, b: *const u8, ctx: *mut u8, status: *mut u32) {}
#[no_mangle] pub unsafe extern "C" fn mpd_qrotate(result: *mut u8, a: *const u8, b: *const u8, ctx: *mut u8, status: *mut u32) {}

// ---------------------------------------------------------------------------
// _hashlib — HACL* cryptographic hash stubs
// ---------------------------------------------------------------------------

#[no_mangle] pub unsafe extern "C" fn python_hashlib_Hacl_Hash_SHA2_malloc_224() -> *mut u8 { NULL }
#[no_mangle] pub unsafe extern "C" fn python_hashlib_Hacl_Hash_SHA2_malloc_256() -> *mut u8 { NULL }
#[no_mangle] pub unsafe extern "C" fn python_hashlib_Hacl_Hash_SHA2_malloc_384() -> *mut u8 { NULL }
#[no_mangle] pub unsafe extern "C" fn python_hashlib_Hacl_Hash_SHA2_malloc_512() -> *mut u8 { NULL }
#[no_mangle] pub unsafe extern "C" fn python_hashlib_Hacl_Hash_SHA2_copy_256(state: *mut u8) -> *mut u8 { NULL }
#[no_mangle] pub unsafe extern "C" fn python_hashlib_Hacl_Hash_SHA2_copy_512(state: *mut u8) -> *mut u8 { NULL }
#[no_mangle] pub unsafe extern "C" fn python_hashlib_Hacl_Hash_SHA2_update_256(state: *mut u8, data: *const u8, len: u32) {}
#[no_mangle] pub unsafe extern "C" fn python_hashlib_Hacl_Hash_SHA2_update_512(state: *mut u8, data: *const u8, len: u32) {}
#[no_mangle] pub unsafe extern "C" fn python_hashlib_Hacl_Hash_SHA2_digest_256(state: *mut u8, output: *mut u8) {}
#[no_mangle] pub unsafe extern "C" fn python_hashlib_Hacl_Hash_SHA2_digest_512(state: *mut u8, output: *mut u8) {}
#[no_mangle] pub unsafe extern "C" fn python_hashlib_Hacl_Hash_SHA2_free_256(state: *mut u8) {}
#[no_mangle] pub unsafe extern "C" fn python_hashlib_Hacl_Hash_SHA2_free_512(state: *mut u8) {}
