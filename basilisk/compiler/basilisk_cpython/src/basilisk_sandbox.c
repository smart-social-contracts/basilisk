/*
 * _basilisk_sandbox — Basilisk's subinterpreter sandbox primitive (Phase 2).
 *
 * Runs untrusted/semi-trusted Python code (extensions, rule modules) in an
 * ISOLATED CPython subinterpreter, bound directly to the C-API (no dependency
 * on the provisional stdlib `interpreters`/`_interpreters` module).
 *
 * Public (main-interpreter-only) API:
 *
 *   spawn_subinterpreter(source_code: str, content_hash: str,
 *                        context_id: str = "",
 *                        allowed_actions: Sequence[str] = (),
 *                        rpc_handler: Callable | None = None,
 *                        budget: int = 10_000_000) -> int
 *       Verifies sha256(source_code) == content_hash AND that content_hash is
 *       in the approved-hash registry, then creates an isolated
 *       subinterpreter, minimally bootstraps it (sys.path = [], rpc()
 *       builtin injected), and executes source_code in a fresh module
 *       namespace. Returns an opaque handle. Refuses (PermissionError) on
 *       hash mismatch or unapproved hash. Any exception raised by the
 *       sandboxed source tears the interpreter down and re-raises host-side
 *       as RuntimeError carrying only TEXT (plain data — no live objects
 *       cross the boundary).
 *       context_id/allowed_actions come from the capability descriptor
 *       (see basilisk/sandbox.py); rpc_handler is a MAIN-interpreter
 *       callable `(context_id, action, kwargs) -> plain data`.
 *       budget is the per-spawn deterministic bytecode-instruction budget
 *       (counted in the ceval dispatch loop — never wall-clock); when
 *       exhausted the interpreter raises sandbox.BudgetExceeded inside the
 *       sandbox, on every subsequent instruction. budget=0 disables
 *       metering (host-only choice). The main interpreter is never
 *       metered.
 *
 *   close_subinterpreter(handle: int) -> None
 *       Tears down the subinterpreter and discards its heap. Lifecycle is
 *       fresh-per-call by design; there is deliberately NO pooling/reuse.
 *
 *   call_in_subinterpreter(handle: int, function_name: str,
 *                          kwargs: dict | None = None) -> plain data
 *       Call a top-level function defined by the sandboxed source; kwargs
 *       and result are deep-copied plain data (result materialized via the
 *       C API — the sandbox needs no json module).
 *
 *   approve_hash(content_hash: str) / revoke_hash(content_hash: str)
 *       Host-side registry management (main interpreter only, so only
 *       privileged application code can call it).
 *
 * Security invariants (do not weaken without a design review):
 *
 *   1. use_main_obmalloc = 0 — the subinterpreter gets its OWN object
 *      allocator arena. This is what lets Py_EndInterpreter discard the
 *      sandbox heap wholesale, and per CPython (pylifecycle.c,
 *      init_interp_settings) an own-obmalloc interpreter REQUIRES
 *      check_multi_interp_extensions = 1: flipping this to 1 (shared
 *      obmalloc) would both entangle sandbox allocations with host ones and
 *      LIFT the mandatory fail-closed import check. Never flip it.
 *   2. check_multi_interp_extensions = 1 — single-phase C extensions
 *      (including _basilisk_ic, the entire privileged host surface) are
 *      REFUSED at import inside the sandbox. This is enforced fail-closed by
 *      CPython itself, not by a deny-list we maintain.
 *   3. This module is importable from the MAIN interpreter only (guard in
 *      the Py_mod_exec slot). Sandboxed code therefore cannot reach the
 *      spawn primitive to nest interpreters or manage the hash registry.
 *   4. Communication is plain data only. Phase 2 crosses only str (source,
 *      hash), int (handle), and error TEXT. Phase 3's rpc()/result
 *      marshalling must keep it that way.
 *
 * The handle table and registry are C statics: they belong to the HOST
 * (main interpreter). This module must never be initialized in a
 * subinterpreter (invariant 3), so per-interpreter duplication is not a
 * concern.
 */

#include "Python.h"
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

/* ------------------------------------------------------------------ */
/* Compact SHA-256 (FIPS 180-4). Local implementation because Basilisk's
 * trimmed CPython has no _hashlib/_sha2 compiled in.                   */
/* ------------------------------------------------------------------ */

typedef struct {
    uint32_t state[8];
    uint64_t bitlen;
    uint8_t buf[64];
    size_t buflen;
} sha256_ctx;

static const uint32_t sha256_k[64] = {
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,
    0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,
    0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,
    0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,
    0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,
    0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,
    0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,
    0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,
    0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
};

#define ROTR(x,n) (((x) >> (n)) | ((x) << (32 - (n))))

static void sha256_transform(sha256_ctx *c, const uint8_t *p) {
    uint32_t w[64], a, b, d, e, f, g, h, s0, s1, t1, t2, ch, maj;
    uint32_t cc;
    int i;
    for (i = 0; i < 16; i++) {
        w[i] = ((uint32_t)p[i*4] << 24) | ((uint32_t)p[i*4+1] << 16) |
               ((uint32_t)p[i*4+2] << 8) | (uint32_t)p[i*4+3];
    }
    for (i = 16; i < 64; i++) {
        s0 = ROTR(w[i-15],7) ^ ROTR(w[i-15],18) ^ (w[i-15] >> 3);
        s1 = ROTR(w[i-2],17) ^ ROTR(w[i-2],19) ^ (w[i-2] >> 10);
        w[i] = w[i-16] + s0 + w[i-7] + s1;
    }
    a = c->state[0]; b = c->state[1]; cc = c->state[2]; d = c->state[3];
    e = c->state[4]; f = c->state[5]; g = c->state[6]; h = c->state[7];
    for (i = 0; i < 64; i++) {
        s1 = ROTR(e,6) ^ ROTR(e,11) ^ ROTR(e,25);
        ch = (e & f) ^ ((~e) & g);
        t1 = h + s1 + ch + sha256_k[i] + w[i];
        s0 = ROTR(a,2) ^ ROTR(a,13) ^ ROTR(a,22);
        maj = (a & b) ^ (a & cc) ^ (b & cc);
        t2 = s0 + maj;
        h = g; g = f; f = e; e = d + t1;
        d = cc; cc = b; b = a; a = t1 + t2;
    }
    c->state[0] += a; c->state[1] += b; c->state[2] += cc; c->state[3] += d;
    c->state[4] += e; c->state[5] += f; c->state[6] += g; c->state[7] += h;
}

static void sha256_init(sha256_ctx *c) {
    c->state[0] = 0x6a09e667; c->state[1] = 0xbb67ae85;
    c->state[2] = 0x3c6ef372; c->state[3] = 0xa54ff53a;
    c->state[4] = 0x510e527f; c->state[5] = 0x9b05688c;
    c->state[6] = 0x1f83d9ab; c->state[7] = 0x5be0cd19;
    c->bitlen = 0;
    c->buflen = 0;
}

static void sha256_update(sha256_ctx *c, const uint8_t *data, size_t len) {
    c->bitlen += (uint64_t)len * 8;
    while (len > 0) {
        size_t take = 64 - c->buflen;
        if (take > len) take = len;
        memcpy(c->buf + c->buflen, data, take);
        c->buflen += take;
        data += take;
        len -= take;
        if (c->buflen == 64) {
            sha256_transform(c, c->buf);
            c->buflen = 0;
        }
    }
}

static void sha256_final_hex(sha256_ctx *c, char out_hex[65]) {
    /* Message bit length is captured BEFORE padding; the padding bytes fed
     * through sha256_update below advance c->bitlen, but that value is no
     * longer read. */
    uint64_t bitlen = c->bitlen;
    uint8_t pad[64 + 8] = {0x80}; /* 0x80 then zeros */
    size_t padlen = (c->buflen < 56) ? (56 - c->buflen) : (120 - c->buflen);
    uint8_t lenbuf[8];
    int i;

    for (i = 0; i < 8; i++) {
        lenbuf[i] = (uint8_t)(bitlen >> (56 - 8 * i));
    }
    sha256_update(c, pad, padlen);
    sha256_update(c, lenbuf, 8);
    /* buflen is now 0: (buflen + padlen) % 64 == 56, plus 8 == 64. */

    for (i = 0; i < 8; i++) {
        static const char hexd[] = "0123456789abcdef";
        uint32_t v = c->state[i];
        out_hex[i*8]     = hexd[(v >> 28) & 0xf];
        out_hex[i*8 + 1] = hexd[(v >> 24) & 0xf];
        out_hex[i*8 + 2] = hexd[(v >> 20) & 0xf];
        out_hex[i*8 + 3] = hexd[(v >> 16) & 0xf];
        out_hex[i*8 + 4] = hexd[(v >> 12) & 0xf];
        out_hex[i*8 + 5] = hexd[(v >> 8) & 0xf];
        out_hex[i*8 + 6] = hexd[(v >> 4) & 0xf];
        out_hex[i*8 + 7] = hexd[v & 0xf];
    }
    out_hex[64] = '\0';
}

static void sha256_hex(const uint8_t *data, size_t len, char out_hex[65]) {
    sha256_ctx c;
    sha256_init(&c);
    sha256_update(&c, data, len);
    sha256_final_hex(&c, out_hex);
}

/* ------------------------------------------------------------------ */
/* Plain-data marshaller                                               */
/*                                                                     */
/* THE single enforcement point of the plain-data boundary (Phase 3).  */
/* Objects crossing between interpreters are ENCODED into a C byte     */
/* buffer with the source interpreter active, then DECODED into brand- */
/* new objects with the target interpreter active. No PyObject pointer */
/* ever crosses; the buffer lives in raw malloc memory (interpreter-   */
/* independent — obmalloc arenas are per-interpreter and must not be   */
/* used for data that outlives a swap).                                */
/*                                                                     */
/* Accepted types (JSON-equivalent): None, bool, int (64-bit), float,  */
/* str, list/tuple (both decode as list), dict with str keys.          */
/* Everything else is rejected with the TYPE NAME only — never repr(), */
/* which could leak host data into the sandbox.                        */
/* ------------------------------------------------------------------ */

/* --- Instruction metering (provided by the ic-metering libpython patch,
 * see patches/0007-instruction-metering.patch). Deterministic bytecode
 * budget checked in the ceval DISPATCH() loop; never wall-clock. The main
 * interpreter is never enabled (budget stays 0 there). */
extern void _PyBasilisk_MeterEnable(PyThreadState *tstate, uint64_t budget,
                                    PyObject *exc_type);
extern void _PyBasilisk_MeterDisable(PyThreadState *tstate);
extern uint64_t _PyBasilisk_MeterUsed(PyThreadState *tstate);

/* Default per-spawn budget: 10M bytecode instructions. Far above any
 * legitimate extension/rule evaluation, far below what could stall a
 * canister message. Explicit budget=0 disables metering (host's choice,
 * e.g. for trusted rule modules — sandboxed code cannot influence it). */
#define SANDBOX_DEFAULT_BUDGET 10000000ULL

#define PD_MAX_DEPTH 32
#define PD_MAX_BYTES (4u * 1024u * 1024u)

typedef struct {
    uint8_t *buf;
    size_t len;
    size_t cap;
} pd_buf;

static int pd_write(pd_buf *b, const void *data, size_t n) {
    if (b->len + n > PD_MAX_BYTES) {
        return -1;
    }
    if (b->len + n > b->cap) {
        size_t cap = b->cap ? b->cap * 2 : 256;
        while (cap < b->len + n) cap *= 2;
        uint8_t *nb = realloc(b->buf, cap);
        if (nb == NULL) return -1;
        b->buf = nb;
        b->cap = cap;
    }
    memcpy(b->buf + b->len, data, n);
    b->len += n;
    return 0;
}

static int pd_write_u32(pd_buf *b, uint32_t v) {
    return pd_write(b, &v, 4);
}

/* Encode obj into b. Returns 0 on success; on failure returns -1 with a
 * sanitized message in err (no repr of the value). Must run with the
 * interpreter OWNING obj active. Never leaves a Python exception set. */
static int pd_encode(PyObject *obj, pd_buf *b, char *err, size_t errlen,
                     int depth) {
    if (depth > PD_MAX_DEPTH) {
        snprintf(err, errlen, "nesting depth exceeds %d", PD_MAX_DEPTH);
        return -1;
    }
    if (obj == Py_None) {
        return pd_write(b, "N", 1);
    }
    if (PyBool_Check(obj)) { /* before PyLong: bool subclasses int */
        if (pd_write(b, obj == Py_True ? "T" : "F", 1) != 0) goto nomem;
        return 0;
    }
    if (PyLong_Check(obj)) {
        int overflow = 0;
        long long v = PyLong_AsLongLongAndOverflow(obj, &overflow);
        if (overflow != 0 || (v == -1 && PyErr_Occurred())) {
            PyErr_Clear();
            snprintf(err, errlen,
                     "int does not fit in 64 bits (plain-data boundary)");
            return -1;
        }
        if (pd_write(b, "I", 1) != 0 || pd_write(b, &v, 8) != 0) goto nomem;
        return 0;
    }
    if (PyFloat_Check(obj)) {
        double d = PyFloat_AS_DOUBLE(obj);
        if (pd_write(b, "D", 1) != 0 || pd_write(b, &d, 8) != 0) goto nomem;
        return 0;
    }
    if (PyUnicode_Check(obj)) {
        Py_ssize_t n = 0;
        const char *s = PyUnicode_AsUTF8AndSize(obj, &n);
        if (s == NULL) {
            PyErr_Clear();
            snprintf(err, errlen, "string is not encodable as UTF-8");
            return -1;
        }
        if (pd_write(b, "S", 1) != 0 || pd_write_u32(b, (uint32_t)n) != 0 ||
            pd_write(b, s, (size_t)n) != 0) goto nomem;
        return 0;
    }
    if (PyList_Check(obj) || PyTuple_Check(obj)) {
        Py_ssize_t n = PySequence_Size(obj);
        if (pd_write(b, "L", 1) != 0 || pd_write_u32(b, (uint32_t)n) != 0)
            goto nomem;
        for (Py_ssize_t i = 0; i < n; i++) {
            PyObject *item = PySequence_GetItem(obj, i); /* new ref */
            if (item == NULL) {
                PyErr_Clear();
                snprintf(err, errlen, "sequence item unavailable");
                return -1;
            }
            int rc = pd_encode(item, b, err, errlen, depth + 1);
            Py_DECREF(item);
            if (rc != 0) return -1;
        }
        return 0;
    }
    if (PyDict_Check(obj)) {
        Py_ssize_t n = PyDict_Size(obj);
        if (pd_write(b, "M", 1) != 0 || pd_write_u32(b, (uint32_t)n) != 0)
            goto nomem;
        PyObject *key, *value;
        Py_ssize_t pos = 0;
        while (PyDict_Next(obj, &pos, &key, &value)) {
            if (!PyUnicode_Check(key)) {
                snprintf(err, errlen,
                         "dict keys must be str at the plain-data boundary "
                         "(got %.100s)", Py_TYPE(key)->tp_name);
                return -1;
            }
            if (pd_encode(key, b, err, errlen, depth + 1) != 0) return -1;
            if (pd_encode(value, b, err, errlen, depth + 1) != 0) return -1;
        }
        return 0;
    }
    /* Type name only — never the value. */
    snprintf(err, errlen,
             "type %.100s cannot cross the plain-data boundary "
             "(allowed: None, bool, int, float, str, list, dict)",
             Py_TYPE(obj)->tp_name);
    return -1;

nomem:
    snprintf(err, errlen, "plain-data buffer limit exceeded (%u bytes)",
             PD_MAX_BYTES);
    return -1;
}

/* Decode one value from *p (advancing it) into a NEW object owned by the
 * CURRENTLY ACTIVE interpreter. Returns NULL with a Python exception set
 * on malformed input (which would indicate a bug, not user error). */
static PyObject *pd_decode(const uint8_t **p, const uint8_t *end) {
    if (*p >= end) goto corrupt;
    uint8_t tag = *(*p)++;
    switch (tag) {
    case 'N':
        Py_RETURN_NONE;
    case 'T':
        Py_RETURN_TRUE;
    case 'F':
        Py_RETURN_FALSE;
    case 'I': {
        long long v;
        if (end - *p < 8) goto corrupt;
        memcpy(&v, *p, 8);
        *p += 8;
        return PyLong_FromLongLong(v);
    }
    case 'D': {
        double d;
        if (end - *p < 8) goto corrupt;
        memcpy(&d, *p, 8);
        *p += 8;
        return PyFloat_FromDouble(d);
    }
    case 'S': {
        uint32_t n;
        if (end - *p < 4) goto corrupt;
        memcpy(&n, *p, 4);
        *p += 4;
        if ((size_t)(end - *p) < n) goto corrupt;
        PyObject *s = PyUnicode_FromStringAndSize((const char *)*p,
                                                  (Py_ssize_t)n);
        *p += n;
        return s;
    }
    case 'L': {
        uint32_t n;
        if (end - *p < 4) goto corrupt;
        memcpy(&n, *p, 4);
        *p += 4;
        PyObject *list = PyList_New((Py_ssize_t)n);
        if (list == NULL) return NULL;
        for (uint32_t i = 0; i < n; i++) {
            PyObject *item = pd_decode(p, end);
            if (item == NULL) {
                Py_DECREF(list);
                return NULL;
            }
            PyList_SET_ITEM(list, (Py_ssize_t)i, item);
        }
        return list;
    }
    case 'M': {
        uint32_t n;
        if (end - *p < 4) goto corrupt;
        memcpy(&n, *p, 4);
        *p += 4;
        PyObject *dict = PyDict_New();
        if (dict == NULL) return NULL;
        for (uint32_t i = 0; i < n; i++) {
            PyObject *key = pd_decode(p, end);
            PyObject *value = key ? pd_decode(p, end) : NULL;
            if (key == NULL || value == NULL) {
                Py_XDECREF(key);
                Py_XDECREF(value);
                Py_DECREF(dict);
                return NULL;
            }
            int rc = PyDict_SetItem(dict, key, value);
            Py_DECREF(key);
            Py_DECREF(value);
            if (rc != 0) {
                Py_DECREF(dict);
                return NULL;
            }
        }
        return dict;
    }
    default:
        break;
    }
corrupt:
    PyErr_SetString(PyExc_RuntimeError,
                    "corrupt plain-data buffer (internal error)");
    return NULL;
}

/* ------------------------------------------------------------------ */
/* Handle table                                                        */
/* ------------------------------------------------------------------ */

/* Fresh-per-call lifecycle on a single-threaded canister: realistically one
 * live sandbox at a time, but allow a few for host code that prepares
 * several before closing them. Fails loudly when exhausted. */
#define SANDBOX_MAX_HANDLES 8

#define SANDBOX_MAX_ACTIONS 32
#define SANDBOX_MAX_ACTION_LEN 64
#define SANDBOX_MAX_CONTEXT_ID 128

typedef struct {
    int in_use;
    PyThreadState *tstate;   /* the subinterpreter's thread state */
    PyObject *globals;       /* module namespace dict (owned BY the sub-
                                interpreter's allocator; only touched with
                                the subinterpreter active) */

    /* --- capability data (host-side, plain C — no PyObject shared) --- */
    char context_id[SANDBOX_MAX_CONTEXT_ID];
    char allowed_actions[SANDBOX_MAX_ACTIONS][SANDBOX_MAX_ACTION_LEN];
    int n_allowed_actions;

    /* Main-interpreter callable handling rpc(action, **kwargs). Owned by
     * the MAIN interpreter: only touched (incl. decref) with main active. */
    PyObject *rpc_handler;

    /* The main interpreter's thread state at spawn time, so the rpc()
     * builtin (running with the SUBinterpreter active) can swap over. */
    PyThreadState *main_tstate;

    int in_rpc; /* re-entrancy guard */
} sandbox_handle;

static sandbox_handle sandbox_handles[SANDBOX_MAX_HANDLES];

static int action_is_allowed(const sandbox_handle *h, const char *action) {
    for (int i = 0; i < h->n_allowed_actions; i++) {
        if (strncmp(h->allowed_actions[i], action,
                    SANDBOX_MAX_ACTION_LEN) == 0) {
            return 1;
        }
    }
    return 0;
}

/* Approved-hash registry: array of 64-char lowercase hex strings. Kept as
 * plain C data (not a Python set) so no PyObject is shared host-side. */
#define SANDBOX_MAX_HASHES 64
static char approved_hashes[SANDBOX_MAX_HASHES][65];
static int n_approved_hashes = 0;

static int hash_is_approved(const char *hex) {
    for (int i = 0; i < n_approved_hashes; i++) {
        if (strcmp(approved_hashes[i], hex) == 0) {
            return 1;
        }
    }
    return 0;
}

/* Validate + lowercase a 64-hex-char string. Returns 0 on success. */
static int normalize_hash(const char *in, char out[65]) {
    if (strlen(in) != 64) {
        return -1;
    }
    for (int i = 0; i < 64; i++) {
        char ch = in[i];
        if (ch >= 'A' && ch <= 'F') ch = (char)(ch - 'A' + 'a');
        if (!((ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'f'))) {
            return -1;
        }
        out[i] = ch;
    }
    out[64] = '\0';
    return 0;
}

/* ------------------------------------------------------------------ */
/* Spawn / close                                                       */
/* ------------------------------------------------------------------ */

/* The audit-mandated sandbox configuration. See file header for why
 * use_main_obmalloc / check_multi_interp_extensions must never change. */
static PyInterpreterConfig sandbox_interp_config(void) {
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

/* Capture the current (sub)interpreter's pending exception as text into
 * buf. Must be called with the failing interpreter active. Clears the
 * error. */
static void capture_error_text(char *buf, size_t buflen) {
    PyObject *exc = PyErr_GetRaisedException();
    buf[0] = '\0';
    if (exc == NULL) {
        snprintf(buf, buflen, "unknown error (no exception set)");
        return;
    }
    {
        PyObject *s = PyObject_Str(exc);
        PyObject *tname = PyObject_GetAttrString((PyObject *)Py_TYPE(exc),
                                                 "__name__");
        const char *msg = s ? PyUnicode_AsUTF8(s) : NULL;
        const char *name = tname ? PyUnicode_AsUTF8(tname) : NULL;
        snprintf(buf, buflen, "%s: %s",
                 name ? name : "Exception",
                 msg ? msg : "<unprintable>");
        Py_XDECREF(s);
        Py_XDECREF(tname);
    }
    Py_DECREF(exc);
    PyErr_Clear();
}

/* Tear down the subinterpreter in `handle` and swap back to `main_ts`.
 * Safe to call with either the subinterpreter or main active. */
static void teardown_handle(sandbox_handle *h, PyThreadState *main_ts) {
    if (PyThreadState_Get() != h->tstate) {
        PyThreadState_Swap(h->tstate);
    }
    /* Release the meter's exception-type ref (owned by this interpreter)
     * before finalization. */
    _PyBasilisk_MeterDisable(h->tstate);
    Py_XDECREF(h->globals);
    h->globals = NULL;
    Py_EndInterpreter(h->tstate);
    /* Py_EndInterpreter leaves no current thread state. */
    PyThreadState_Swap(main_ts);
    /* The rpc handler is a MAIN-interpreter object: release it with main
     * active (we just swapped). */
    Py_XDECREF(h->rpc_handler);
    h->rpc_handler = NULL;
    h->main_tstate = NULL;
    h->n_allowed_actions = 0;
    h->context_id[0] = '\0';
    h->in_rpc = 0;
    h->tstate = NULL;
    h->in_use = 0;
}

/* --------------------------------------------------------------- */
/* rpc() builtin — injected into each sandbox at spawn time          */
/* --------------------------------------------------------------- */

/* Runs with the SUBINTERPRETER active. `self` is a PyLong holding the
 * handle index (the "closure over a host-side context id": the C function
 * object carries the handle, the handle carries context_id — sandboxed
 * code cannot alter either).
 *
 * Boundary discipline:
 *   sandbox kwargs --pd_encode (sub active)--> C buffer
 *     --swap to main--> pd_decode --> handler(context_id, action, kwargs)
 *     result --pd_encode (main active)--> C buffer
 *     --swap to sub--> pd_decode --> returned to sandboxed code.
 * Handler failures cross as TEXT ONLY: the host exception is stringified
 * and destroyed while MAIN is active; the sandbox gets a fresh
 * RuntimeError with that string. No exception object, no traceback, no
 * chaining crosses the boundary (information-disclosure control). */
static PyObject *sandbox_rpc(PyObject *self, PyObject *args,
                             PyObject *kwargs) {
    long idx = PyLong_AsLong(self);
    if (idx < 0 || idx >= SANDBOX_MAX_HANDLES ||
        !sandbox_handles[idx].in_use) {
        PyErr_SetString(PyExc_RuntimeError, "rpc: stale sandbox handle");
        return NULL;
    }
    sandbox_handle *h = &sandbox_handles[idx];
    if (PyThreadState_Get() != h->tstate) {
        PyErr_SetString(PyExc_RuntimeError,
                        "rpc: called from the wrong interpreter");
        return NULL;
    }
    if (h->in_rpc) {
        PyErr_SetString(PyExc_RuntimeError, "rpc: re-entrant call");
        return NULL;
    }

    const char *action;
    if (!PyArg_ParseTuple(args, "s:rpc", &action)) {
        return NULL;
    }

    /* Capability gate: enforced HERE, before the handler is reached. */
    if (!action_is_allowed(h, action)) {
        PyErr_Format(PyExc_PermissionError,
                     "rpc: action '%.100s' is not in the capability's "
                     "allowed_actions", action);
        return NULL;
    }
    if (h->rpc_handler == NULL) {
        PyErr_SetString(PyExc_RuntimeError,
                        "rpc: no handler was provided at spawn time");
        return NULL;
    }

    /* Encode sandbox-side kwargs (sub active). */
    char errtext[1024];
    pd_buf req = {0};
    if (kwargs != NULL) {
        if (pd_encode(kwargs, &req, errtext, sizeof(errtext), 0) != 0) {
            free(req.buf);
            PyErr_Format(PyExc_TypeError, "rpc arguments: %s", errtext);
            return NULL;
        }
    } else {
        pd_write(&req, "M", 1);
        pd_write_u32(&req, 0);
    }

    /* --- Cross to the MAIN interpreter --- */
    h->in_rpc = 1;
    PyThreadState_Swap(h->main_tstate);

    int failed = 0;
    pd_buf resp = {0};
    {
        const uint8_t *p = req.buf;
        PyObject *kw_main = pd_decode(&p, req.buf + req.len);
        PyObject *result = NULL;
        if (kw_main == NULL) {
            capture_error_text(errtext, sizeof(errtext));
            failed = 1;
        }
        else {
            result = PyObject_CallFunction(h->rpc_handler, "ssO",
                                           h->context_id, action, kw_main);
            Py_DECREF(kw_main);
            if (result == NULL) {
                /* TEXT ONLY: stringify + destroy the host exception while
                 * main is active. */
                capture_error_text(errtext, sizeof(errtext));
                failed = 1;
            }
            else {
                if (pd_encode(result, &resp, errtext, sizeof(errtext), 0)
                        != 0) {
                    failed = 1; /* errtext carries type name only */
                }
                Py_DECREF(result);
            }
        }
    }

    /* --- Back to the sandbox --- */
    PyThreadState_Swap(h->tstate);
    h->in_rpc = 0;
    free(req.buf);

    if (failed) {
        free(resp.buf);
        PyErr_Format(PyExc_RuntimeError, "rpc failed: %s", errtext);
        return NULL;
    }

    const uint8_t *p = resp.buf;
    PyObject *out = pd_decode(&p, resp.buf + resp.len);
    free(resp.buf);
    return out;
}

static PyMethodDef sandbox_rpc_def = {
    "rpc", (PyCFunction)(void (*)(void))sandbox_rpc,
    METH_VARARGS | METH_KEYWORDS,
    "rpc(action, **kwargs) -> plain data\n"
    "Host-validated privileged operation. `action` must be in the\n"
    "capability's allowed_actions; arguments and result are plain data\n"
    "(None/bool/int/float/str/list/dict) deep-copied across the\n"
    "interpreter boundary."
};

static PyObject *sandbox_spawn(PyObject *self, PyObject *args) {
    const char *source;
    const char *content_hash;
    const char *context_id = "";
    PyObject *allowed_actions = NULL; /* sequence of str, or None */
    PyObject *rpc_handler = NULL;     /* callable, or None */
    unsigned long long budget = SANDBOX_DEFAULT_BUDGET;

    /* "s" (not "s#"): rejects embedded NULs, so the bytes we hash are
     * exactly the bytes PyRun_String will execute. */
    if (!PyArg_ParseTuple(args, "ss|sOOK", &source, &content_hash,
                          &context_id, &allowed_actions, &rpc_handler,
                          &budget)) {
        return NULL;
    }
    size_t source_len = strlen(source);

    if (rpc_handler == Py_None) {
        rpc_handler = NULL;
    }
    if (rpc_handler != NULL && !PyCallable_Check(rpc_handler)) {
        PyErr_SetString(PyExc_TypeError, "rpc_handler must be callable");
        return NULL;
    }
    if (strlen(context_id) >= SANDBOX_MAX_CONTEXT_ID) {
        PyErr_Format(PyExc_ValueError, "context_id longer than %d",
                     SANDBOX_MAX_CONTEXT_ID - 1);
        return NULL;
    }

    /* --- 1. Hash verification, BEFORE any interpreter work --- */
    char wanted[65];
    if (normalize_hash(content_hash, wanted) != 0) {
        PyErr_SetString(PyExc_ValueError,
                        "content_hash must be 64 hex characters (sha256)");
        return NULL;
    }

    char actual[65];
    sha256_hex((const uint8_t *)source, (size_t)source_len, actual);
    if (strcmp(actual, wanted) != 0) {
        PyErr_Format(PyExc_PermissionError,
                     "refusing to spawn: content hash mismatch "
                     "(source hashes to %s)", actual);
        return NULL;
    }
    if (!hash_is_approved(wanted)) {
        PyErr_SetString(PyExc_PermissionError,
                        "refusing to spawn: content hash is not in the "
                        "approved-hash registry");
        return NULL;
    }

    /* --- 2. Allocate a handle --- */
    int idx = -1;
    for (int i = 0; i < SANDBOX_MAX_HANDLES; i++) {
        if (!sandbox_handles[i].in_use) {
            idx = i;
            break;
        }
    }
    if (idx < 0) {
        PyErr_Format(PyExc_RuntimeError,
                     "sandbox handle table exhausted (%d live interpreters); "
                     "close_subinterpreter() the ones you are done with",
                     SANDBOX_MAX_HANDLES);
        return NULL;
    }
    sandbox_handle *h = &sandbox_handles[idx];

    /* --- 2b. Capability data: copy into plain C storage (main active) --- */
    h->n_allowed_actions = 0;
    if (allowed_actions != NULL && allowed_actions != Py_None) {
        PyObject *seq = PySequence_Fast(allowed_actions,
                                        "allowed_actions must be a sequence");
        if (seq == NULL) {
            return NULL;
        }
        Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
        if (n > SANDBOX_MAX_ACTIONS) {
            Py_DECREF(seq);
            PyErr_Format(PyExc_ValueError, "more than %d allowed_actions",
                         SANDBOX_MAX_ACTIONS);
            return NULL;
        }
        for (Py_ssize_t i = 0; i < n; i++) {
            PyObject *item = PySequence_Fast_GET_ITEM(seq, i); /* borrowed */
            const char *s = PyUnicode_Check(item) ? PyUnicode_AsUTF8(item)
                                                  : NULL;
            if (s == NULL || strlen(s) >= SANDBOX_MAX_ACTION_LEN) {
                Py_DECREF(seq);
                PyErr_SetString(PyExc_ValueError,
                                "allowed_actions entries must be str "
                                "shorter than 64 chars");
                return NULL;
            }
            strcpy(h->allowed_actions[h->n_allowed_actions++], s);
        }
        Py_DECREF(seq);
    }
    strcpy(h->context_id, context_id);
    h->rpc_handler = rpc_handler; /* owned by MAIN interpreter */
    Py_XINCREF(h->rpc_handler);
    h->in_rpc = 0;

    /* --- 3. Create the isolated subinterpreter --- */
    PyThreadState *main_ts = PyThreadState_Get();
    h->main_tstate = main_ts;
    PyThreadState *sub_ts = NULL;
    PyInterpreterConfig config = sandbox_interp_config();

    PyStatus status = Py_NewInterpreterFromConfig(&sub_ts, &config);
    if (PyStatus_Exception(status)) {
        /* No interpreter was created; we are still on main. */
        PyThreadState_Swap(main_ts);
        Py_XDECREF(h->rpc_handler);
        h->rpc_handler = NULL;
        PyErr_Format(PyExc_RuntimeError,
                     "failed to create subinterpreter: %s",
                     status.err_msg ? status.err_msg : "unknown error");
        return NULL;
    }
    /* From here the SUBinterpreter is active until we swap back. */
    h->in_use = 1;
    h->tstate = sub_ts;
    h->globals = NULL;

    char errbuf[1024];

    /* --- 4. Minimal bootstrap: no import paths into host-visible files.
     * Frozen/builtin modules remain importable via sys.meta_path; that is
     * the intended surface (see audit addendum section C/D). --- */
    {
        PyObject *sys_path = PyList_New(0);
        int rc = -1;
        if (sys_path != NULL) {
            rc = PySys_SetObject("path", sys_path);
            Py_DECREF(sys_path);
        }
        if (rc != 0) {
            capture_error_text(errbuf, sizeof(errbuf));
            teardown_handle(h, main_ts);
            PyErr_Format(PyExc_RuntimeError,
                         "sandbox bootstrap failed: %s", errbuf);
            return NULL;
        }
    }

    /* --- 4b. Inject the rpc() builtin (sandbox-owned C function object
     * closed over the handle index; see sandbox_rpc). Injected into the
     * sandbox's __builtins__ so it is reachable without any import — and
     * while sandboxed code can shadow the NAME, it cannot forge the
     * capability, which lives host-side in the handle. --- */
    {
        PyObject *idx_obj = PyLong_FromLong(idx);
        PyObject *rpc_fn =
            idx_obj ? PyCFunction_New(&sandbox_rpc_def, idx_obj) : NULL;
        Py_XDECREF(idx_obj); /* PyCFunction_New holds its own reference */
        int rc = -1;
        if (rpc_fn != NULL) {
            rc = PyDict_SetItemString(PyEval_GetBuiltins(), "rpc", rpc_fn);
            Py_DECREF(rpc_fn);
        }
        if (rc != 0) {
            capture_error_text(errbuf, sizeof(errbuf));
            teardown_handle(h, main_ts);
            PyErr_Format(PyExc_RuntimeError,
                         "sandbox rpc injection failed: %s", errbuf);
            return NULL;
        }
    }

    /* --- 4c. Instruction metering: create the sandbox-owned
     * BudgetExceeded class (also exposed via __builtins__ so sandboxed
     * code can name it), then arm the meter BEFORE the untrusted source
     * runs. budget == 0 (explicit, host-only choice) leaves the meter
     * off. --- */
    if (budget != 0) {
        PyObject *exc = PyErr_NewExceptionWithDoc(
            "sandbox.BudgetExceeded",
            "Raised by the interpreter when the sandbox's deterministic "
            "bytecode-instruction budget is exhausted. Re-raised on every "
            "subsequent instruction, so it cannot be usefully caught.",
            NULL, NULL);
        int rc = -1;
        if (exc != NULL) {
            rc = PyDict_SetItemString(PyEval_GetBuiltins(),
                                      "BudgetExceeded", exc);
        }
        if (rc != 0) {
            Py_XDECREF(exc);
            capture_error_text(errbuf, sizeof(errbuf));
            teardown_handle(h, main_ts);
            PyErr_Format(PyExc_RuntimeError,
                         "sandbox meter setup failed: %s", errbuf);
            return NULL;
        }
        /* The meter takes its own strong ref; ours is dropped. */
        _PyBasilisk_MeterEnable(sub_ts, (uint64_t)budget, exc);
        Py_DECREF(exc);
    }

    /* --- 5. Execute the (hash-verified) source in a fresh namespace --- */
    {
        PyObject *globals = PyDict_New();
        PyObject *mod_name =
            globals ? PyUnicode_FromString("__sandbox__") : NULL;
        int setup_ok =
            mod_name != NULL &&
            PyDict_SetItemString(globals, "__name__", mod_name) == 0 &&
            PyDict_SetItemString(globals, "__builtins__",
                                 PyEval_GetBuiltins()) == 0;
        Py_XDECREF(mod_name);
        if (!setup_ok) {
            Py_XDECREF(globals);
            capture_error_text(errbuf, sizeof(errbuf));
            teardown_handle(h, main_ts);
            PyErr_Format(PyExc_RuntimeError,
                         "sandbox namespace setup failed: %s", errbuf);
            return NULL;
        }

        PyObject *result = PyRun_String(source, Py_file_input,
                                        globals, globals);
        if (result == NULL) {
            capture_error_text(errbuf, sizeof(errbuf));
            Py_DECREF(globals);
            teardown_handle(h, main_ts);
            /* Plain-data boundary: only the TEXT of the sandbox error
             * crosses back into the host interpreter. */
            PyErr_Format(PyExc_RuntimeError,
                         "sandboxed code raised: %s", errbuf);
            return NULL;
        }
        Py_DECREF(result);
        h->globals = globals; /* kept for Phase 3 entry-point calls */
    }

    /* --- 6. Back to the host interpreter --- */
    PyThreadState_Swap(main_ts);
    return PyLong_FromLong(idx);
}

static PyObject *sandbox_close(PyObject *self, PyObject *args) {
    int idx;
    if (!PyArg_ParseTuple(args, "i", &idx)) {
        return NULL;
    }
    if (idx < 0 || idx >= SANDBOX_MAX_HANDLES ||
        !sandbox_handles[idx].in_use) {
        PyErr_Format(PyExc_ValueError, "invalid sandbox handle %d", idx);
        return NULL;
    }
    if (sandbox_handles[idx].in_rpc) {
        /* An rpc() is suspended inside this interpreter; ending it now
         * would crash when the rpc call frame resumes. */
        PyErr_Format(PyExc_RuntimeError,
                     "cannot close sandbox %d during one of its rpc calls",
                     idx);
        return NULL;
    }
    PyThreadState *main_ts = PyThreadState_Get();
    teardown_handle(&sandbox_handles[idx], main_ts);
    Py_RETURN_NONE;
}

/* call_in_subinterpreter(handle, function_name, kwargs=None) -> plain data
 *
 * Calls a top-level function defined by the sandboxed source and returns
 * its result ACROSS the plain-data boundary: kwargs are encoded with the
 * main interpreter active and decoded inside the sandbox; the result is
 * encoded inside the sandbox and decoded (materialized via the C API, per
 * the agreed design — no json module involved) with main active. Sandbox
 * exceptions cross as text-only RuntimeError. */
static PyObject *sandbox_call(PyObject *self, PyObject *args) {
    int idx;
    const char *func_name;
    PyObject *kwargs = NULL;
    if (!PyArg_ParseTuple(args, "is|O", &idx, &func_name, &kwargs)) {
        return NULL;
    }
    if (kwargs == Py_None) {
        kwargs = NULL;
    }
    if (kwargs != NULL && !PyDict_Check(kwargs)) {
        PyErr_SetString(PyExc_TypeError, "kwargs must be a dict or None");
        return NULL;
    }
    if (idx < 0 || idx >= SANDBOX_MAX_HANDLES ||
        !sandbox_handles[idx].in_use) {
        PyErr_Format(PyExc_ValueError, "invalid sandbox handle %d", idx);
        return NULL;
    }
    sandbox_handle *h = &sandbox_handles[idx];
    if (PyThreadState_Get() != h->main_tstate) {
        PyErr_SetString(PyExc_RuntimeError,
                        "call_in_subinterpreter: main interpreter only");
        return NULL;
    }
    if (h->in_rpc) {
        PyErr_SetString(PyExc_RuntimeError,
                        "call_in_subinterpreter: re-entrant call");
        return NULL;
    }

    char errtext[1024];

    /* Encode kwargs with MAIN active. */
    pd_buf req = {0};
    if (kwargs != NULL) {
        if (pd_encode(kwargs, &req, errtext, sizeof(errtext), 0) != 0) {
            free(req.buf);
            PyErr_Format(PyExc_TypeError, "call arguments: %s", errtext);
            return NULL;
        }
    } else {
        pd_write(&req, "M", 1);
        pd_write_u32(&req, 0);
    }

    /* --- Into the sandbox --- */
    PyThreadState_Swap(h->tstate);

    int failed = 0;
    pd_buf resp = {0};
    {
        PyObject *func = PyDict_GetItemString(h->globals, func_name);
        if (func == NULL || !PyCallable_Check(func)) {
            snprintf(errtext, sizeof(errtext),
                     "sandbox has no callable named '%.100s'", func_name);
            failed = 1;
        }
        else {
            const uint8_t *p = req.buf;
            PyObject *kw_sub = pd_decode(&p, req.buf + req.len);
            PyObject *empty = kw_sub ? PyTuple_New(0) : NULL;
            PyObject *result =
                empty ? PyObject_Call(func, empty, kw_sub) : NULL;
            Py_XDECREF(empty);
            Py_XDECREF(kw_sub);
            if (result == NULL) {
                capture_error_text(errtext, sizeof(errtext));
                failed = 1;
            }
            else {
                if (pd_encode(result, &resp, errtext, sizeof(errtext), 0)
                        != 0) {
                    failed = 1; /* type name only, never the value */
                }
                Py_DECREF(result);
            }
        }
    }

    /* --- Back to main --- */
    PyThreadState_Swap(h->main_tstate);
    free(req.buf);

    if (failed) {
        free(resp.buf);
        PyErr_Format(PyExc_RuntimeError, "sandboxed call raised: %s",
                     errtext);
        return NULL;
    }

    const uint8_t *p = resp.buf;
    PyObject *out = pd_decode(&p, resp.buf + resp.len);
    free(resp.buf);
    return out;
}

static PyObject *sandbox_approve_hash(PyObject *self, PyObject *args) {
    const char *hex;
    if (!PyArg_ParseTuple(args, "s", &hex)) {
        return NULL;
    }
    char norm[65];
    if (normalize_hash(hex, norm) != 0) {
        PyErr_SetString(PyExc_ValueError,
                        "content_hash must be 64 hex characters (sha256)");
        return NULL;
    }
    if (hash_is_approved(norm)) {
        Py_RETURN_NONE;
    }
    if (n_approved_hashes >= SANDBOX_MAX_HASHES) {
        PyErr_Format(PyExc_RuntimeError,
                     "approved-hash registry full (%d)", SANDBOX_MAX_HASHES);
        return NULL;
    }
    memcpy(approved_hashes[n_approved_hashes], norm, 65);
    n_approved_hashes++;
    Py_RETURN_NONE;
}

static PyObject *sandbox_revoke_hash(PyObject *self, PyObject *args) {
    const char *hex;
    if (!PyArg_ParseTuple(args, "s", &hex)) {
        return NULL;
    }
    char norm[65];
    if (normalize_hash(hex, norm) != 0) {
        PyErr_SetString(PyExc_ValueError,
                        "content_hash must be 64 hex characters (sha256)");
        return NULL;
    }
    for (int i = 0; i < n_approved_hashes; i++) {
        if (strcmp(approved_hashes[i], norm) == 0) {
            memmove(&approved_hashes[i], &approved_hashes[i + 1],
                    (size_t)(n_approved_hashes - i - 1) * 65);
            n_approved_hashes--;
            Py_RETURN_NONE;
        }
    }
    Py_RETURN_NONE;
}

/* sha256 of a str — exposed so host code / tests can compute content
 * hashes without hashlib (which is not compiled into this build). */
static PyObject *sandbox_sha256(PyObject *self, PyObject *args) {
    const char *data;
    Py_ssize_t len;
    if (!PyArg_ParseTuple(args, "s#", &data, &len)) {
        return NULL;
    }
    char hex[65];
    sha256_hex((const uint8_t *)data, (size_t)len, hex);
    return PyUnicode_FromString(hex);
}

/* Wasm linear-memory size in 64 KiB pages (0 off-wasm). For the Phase 2
 * memory soak measurements: linear memory never shrinks, so this IS the
 * high-water mark. */
static PyObject *sandbox_memory_pages(PyObject *self, PyObject *args) {
#if defined(__wasm__)
    return PyLong_FromLong((long)__builtin_wasm_memory_size(0));
#else
    return PyLong_FromLong(0);
#endif
}

static PyMethodDef sandbox_methods[] = {
    {"spawn_subinterpreter", sandbox_spawn, METH_VARARGS,
     "spawn_subinterpreter(source_code, content_hash) -> handle\n"
     "Verify hash against the approved registry, spawn an isolated\n"
     "subinterpreter and execute source_code in it."},
    {"close_subinterpreter", sandbox_close, METH_VARARGS,
     "close_subinterpreter(handle)\nTear down the subinterpreter and "
     "discard its heap."},
    {"call_in_subinterpreter", sandbox_call, METH_VARARGS,
     "call_in_subinterpreter(handle, function_name, kwargs=None) -> plain "
     "data\nCall a top-level function defined by the sandboxed source; "
     "arguments and result cross as deep-copied plain data."},
    {"approve_hash", sandbox_approve_hash, METH_VARARGS,
     "approve_hash(content_hash)\nAdd a sha256 hex digest to the "
     "approved-hash registry."},
    {"revoke_hash", sandbox_revoke_hash, METH_VARARGS,
     "revoke_hash(content_hash)\nRemove a digest from the registry."},
    {"sha256", sandbox_sha256, METH_VARARGS,
     "sha256(text) -> hex digest of the UTF-8 encoding of text."},
    {"wasm_memory_pages", sandbox_memory_pages, METH_NOARGS,
     "Current wasm linear memory size in 64 KiB pages (0 off-wasm)."},
    {NULL, NULL, 0, NULL}
};

/* Main-interpreter-only guard (security invariant 3 in the header). */
static int sandbox_exec(PyObject *module) {
    if (PyInterpreterState_Get() != PyInterpreterState_Main()) {
        PyErr_SetString(PyExc_ImportError,
                        "_basilisk_sandbox is only available in the main "
                        "interpreter");
        return -1;
    }
    return 0;
}

static PyModuleDef_Slot sandbox_slots[] = {
    {Py_mod_exec, sandbox_exec},
    /* NOT_SUPPORTED would also block the main-interpreter import under some
     * configs; the exec-slot guard above is the enforcement mechanism, and
     * multiple-interpreters support here refers to the module machinery,
     * which is fine. */
    {Py_mod_multiple_interpreters, Py_MOD_PER_INTERPRETER_GIL_SUPPORTED},
    {0, NULL}
};

static struct PyModuleDef sandbox_module = {
    PyModuleDef_HEAD_INIT, "_basilisk_sandbox",
    "Basilisk subinterpreter sandbox primitive (host side).",
    0, sandbox_methods, sandbox_slots, NULL, NULL, NULL
};

PyObject *PyInit__basilisk_sandbox(void) {
    return PyModuleDef_Init(&sandbox_module);
}
