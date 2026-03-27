#!/usr/bin/env node
/**
 * vetkeys_helper.js — Standalone Node.js helper for BLS12-381 transport key
 * operations and AES-256-GCM encryption/decryption.
 *
 * Loads the ic-vetkd-utils WASM (bundled alongside this file) and provides
 * a JSON-in/JSON-out CLI interface called by the Basilisk shell.
 *
 * Commands (JSON on stdin → JSON on stdout):
 *   { cmd: "keygen", seed_hex }
 *       → { ok: true, tpk_hex }
 *
 *   { cmd: "encrypt", seed_hex, encrypted_key_hex, public_key_hex,
 *          derivation_id_hex, plaintext_hex }
 *       → { ok: true, ciphertext_hex }
 *
 *   { cmd: "decrypt", seed_hex, encrypted_key_hex, public_key_hex,
 *          derivation_id_hex, ciphertext_hex }
 *       → { ok: true, plaintext_hex }
 */

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

// ---------------------------------------------------------------------------
// Minimal wasm-bindgen runtime (just enough to drive ic-vetkd-utils)
// ---------------------------------------------------------------------------

let wasm;
let cachedUint8Memory0 = null;
let cachedInt32Memory0 = null;
const heap = new Array(128).fill(undefined);
heap.push(undefined, null, true, false);
let heap_next = heap.length;
let WASM_VECTOR_LEN = 0;

const cachedTextDecoder = new TextDecoder('utf-8', { ignoreBOM: true, fatal: true });

function getUint8Memory0() {
    if (cachedUint8Memory0 === null || cachedUint8Memory0.byteLength === 0)
        cachedUint8Memory0 = new Uint8Array(wasm.memory.buffer);
    return cachedUint8Memory0;
}

function getInt32Memory0() {
    if (cachedInt32Memory0 === null || cachedInt32Memory0.byteLength === 0)
        cachedInt32Memory0 = new Int32Array(wasm.memory.buffer);
    return cachedInt32Memory0;
}

function getStringFromWasm0(ptr, len) {
    return cachedTextDecoder.decode(getUint8Memory0().subarray(ptr >>> 0, (ptr >>> 0) + len));
}

function addHeapObject(obj) {
    if (heap_next === heap.length) heap.push(heap.length + 1);
    const idx = heap_next;
    heap_next = heap[idx];
    heap[idx] = obj;
    return idx;
}

function getObject(idx) { return heap[idx]; }

function dropObject(idx) {
    if (idx < 132) return;
    heap[idx] = heap_next;
    heap_next = idx;
}

function takeObject(idx) {
    const ret = getObject(idx);
    dropObject(idx);
    return ret;
}

function passArray8ToWasm0(arg, malloc) {
    const ptr = malloc(arg.length, 1) >>> 0;
    getUint8Memory0().set(arg, ptr);
    WASM_VECTOR_LEN = arg.length;
    return ptr;
}

function getArrayU8FromWasm0(ptr, len) {
    return getUint8Memory0().subarray(ptr >>> 0, (ptr >>> 0) + len);
}

// ---------------------------------------------------------------------------
// WASM loading
// ---------------------------------------------------------------------------

function loadWasm() {
    const wasmPath = path.join(__dirname, 'ic_vetkd_utils_bg.wasm');
    const wasmBytes = fs.readFileSync(wasmPath);

    const imports = { wbg: {} };
    imports.wbg.__wbindgen_string_new = function (arg0, arg1) {
        return addHeapObject(getStringFromWasm0(arg0, arg1));
    };
    imports.wbg.__wbindgen_throw = function (arg0, arg1) {
        throw new Error(getStringFromWasm0(arg0, arg1));
    };

    const mod = new WebAssembly.Module(wasmBytes);
    const instance = new WebAssembly.Instance(mod, imports);
    wasm = instance.exports;
    cachedInt32Memory0 = null;
    cachedUint8Memory0 = null;
}

// ---------------------------------------------------------------------------
// TransportSecretKey operations
// ---------------------------------------------------------------------------

function tskFromSeed(seedBytes) {
    const retptr = wasm.__wbindgen_add_to_stack_pointer(-16);
    try {
        const ptr0 = passArray8ToWasm0(seedBytes, wasm.__wbindgen_malloc);
        const len0 = WASM_VECTOR_LEN;
        wasm.transportsecretkey_from_seed(retptr, ptr0, len0);
        const r0 = getInt32Memory0()[retptr / 4 + 0];
        const r2 = getInt32Memory0()[retptr / 4 + 2];
        if (r2) throw takeObject(getInt32Memory0()[retptr / 4 + 1]);
        return r0;
    } finally {
        wasm.__wbindgen_add_to_stack_pointer(16);
    }
}

function tskPublicKey(tskPtr) {
    const retptr = wasm.__wbindgen_add_to_stack_pointer(-16);
    try {
        wasm.transportsecretkey_public_key(retptr, tskPtr);
        const r0 = getInt32Memory0()[retptr / 4 + 0];
        const r1 = getInt32Memory0()[retptr / 4 + 1];
        const v = getArrayU8FromWasm0(r0, r1).slice();
        wasm.__wbindgen_free(r0, r1);
        return v;
    } finally {
        wasm.__wbindgen_add_to_stack_pointer(16);
    }
}

function tskDecryptAndHash(tskPtr, encKeyBytes, pubKeyBytes, derivIdBytes, symKeyLen, adBytes) {
    const retptr = wasm.__wbindgen_add_to_stack_pointer(-16);
    try {
        const p0 = passArray8ToWasm0(encKeyBytes, wasm.__wbindgen_malloc);  const l0 = WASM_VECTOR_LEN;
        const p1 = passArray8ToWasm0(pubKeyBytes, wasm.__wbindgen_malloc);  const l1 = WASM_VECTOR_LEN;
        const p2 = passArray8ToWasm0(derivIdBytes, wasm.__wbindgen_malloc); const l2 = WASM_VECTOR_LEN;
        const p3 = passArray8ToWasm0(adBytes, wasm.__wbindgen_malloc);      const l3 = WASM_VECTOR_LEN;
        wasm.transportsecretkey_decrypt_and_hash(retptr, tskPtr, p0, l0, p1, l1, p2, l2, symKeyLen, p3, l3);
        const r0 = getInt32Memory0()[retptr / 4 + 0];
        const r1 = getInt32Memory0()[retptr / 4 + 1];
        const r3 = getInt32Memory0()[retptr / 4 + 3];
        if (r3) throw takeObject(getInt32Memory0()[retptr / 4 + 2]);
        const v = getArrayU8FromWasm0(r0, r1).slice();
        wasm.__wbindgen_free(r0, r1);
        return v;
    } finally {
        wasm.__wbindgen_add_to_stack_pointer(16);
    }
}

function tskFree(ptr) { wasm.__wbg_transportsecretkey_free(ptr); }

// ---------------------------------------------------------------------------
// AES-256-GCM
// ---------------------------------------------------------------------------

function aesGcmEncrypt(keyBytes, plaintextBytes) {
    const iv = crypto.randomBytes(12);
    const cipher = crypto.createCipheriv('aes-256-gcm', Buffer.from(keyBytes), iv);
    const enc = Buffer.concat([cipher.update(plaintextBytes), cipher.final()]);
    const tag = cipher.getAuthTag();
    return Buffer.concat([iv, enc, tag]);
}

function aesGcmDecrypt(keyBytes, combined) {
    const iv = combined.subarray(0, 12);
    const tag = combined.subarray(combined.length - 16);
    const enc = combined.subarray(12, combined.length - 16);
    const decipher = crypto.createDecipheriv('aes-256-gcm', Buffer.from(keyBytes), iv);
    decipher.setAuthTag(tag);
    return Buffer.concat([decipher.update(enc), decipher.final()]);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const hexToBytes = (h) => Buffer.from(h, 'hex');
const bytesToHex = (b) => Buffer.from(b).toString('hex');
const AD = Buffer.from('aes-256-gcm-basilisk-vetkeys');

function deriveAesKey(seedHex, encKeyHex, pubKeyHex, derivIdHex) {
    const tskPtr = tskFromSeed(hexToBytes(seedHex));
    try {
        return tskDecryptAndHash(
            tskPtr,
            hexToBytes(encKeyHex),
            hexToBytes(pubKeyHex),
            derivIdHex ? hexToBytes(derivIdHex) : new Uint8Array(0),
            32,
            AD
        );
    } finally {
        tskFree(tskPtr);
    }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function main() {
    loadWasm();

    let input = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (chunk) => { input += chunk; });
    process.stdin.on('end', () => {
        let req;
        try { req = JSON.parse(input); }
        catch (e) { write({ ok: false, error: 'Invalid JSON input' }); return; }

        try {
            if (req.cmd === 'keygen') {
                const tskPtr = tskFromSeed(hexToBytes(req.seed_hex));
                const tpk = tskPublicKey(tskPtr);
                tskFree(tskPtr);
                write({ ok: true, tpk_hex: bytesToHex(tpk) });

            } else if (req.cmd === 'encrypt') {
                const aesKey = deriveAesKey(req.seed_hex, req.encrypted_key_hex, req.public_key_hex, req.derivation_id_hex);
                const ct = aesGcmEncrypt(aesKey, hexToBytes(req.plaintext_hex));
                write({ ok: true, ciphertext_hex: bytesToHex(ct) });

            } else if (req.cmd === 'decrypt') {
                const aesKey = deriveAesKey(req.seed_hex, req.encrypted_key_hex, req.public_key_hex, req.derivation_id_hex);
                const pt = aesGcmDecrypt(aesKey, hexToBytes(req.ciphertext_hex));
                write({ ok: true, plaintext_hex: bytesToHex(pt) });

            } else {
                write({ ok: false, error: 'Unknown command: ' + req.cmd });
            }
        } catch (e) {
            write({ ok: false, error: String(e.message || e) });
        }
    });
}

function write(obj) { process.stdout.write(JSON.stringify(obj)); }

main();
