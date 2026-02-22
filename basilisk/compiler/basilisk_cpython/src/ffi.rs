//! Raw CPython C API FFI bindings.
//!
//! These are the minimal subset of CPython's C API needed for Basilisk canister runtime.
//! We declare them manually rather than using bindgen to keep the wasm32-wasip1 build simple.
//!
//! Reference: https://docs.python.org/3.13/c-api/

#![allow(non_camel_case_types)]
#![allow(non_snake_case)]

use core::ffi::{c_char, c_int, c_long, c_void};

// === Core types ===

/// Opaque CPython object. All Python values are PyObject pointers.
#[repr(C)]
pub struct PyObject {
    _private: [u8; 0],
}

/// Py_ssize_t — signed size type used throughout CPython API
pub type Py_ssize_t = isize;

/// PyGILState_STATE
pub type PyGILState_STATE = c_int;

// === Initialization & Finalization ===

extern "C" {
    pub fn Py_Initialize();
    pub fn Py_InitializeEx(initsigs: c_int);
    pub fn Py_Finalize();
    pub fn Py_FinalizeEx() -> c_int;
    pub fn Py_IsInitialized() -> c_int;

    // Pre-initialization configuration (CPython 3.12+)
    pub fn Py_SetProgramName(name: *const c_char);
    pub fn Py_SetPythonHome(home: *const c_char);
}

// === Reference counting ===

extern "C" {
    pub fn Py_IncRef(o: *mut PyObject);
    pub fn Py_DecRef(o: *mut PyObject);
}

// === Object Protocol ===

extern "C" {
    pub fn PyObject_GetAttrString(o: *mut PyObject, attr_name: *const c_char) -> *mut PyObject;
    pub fn PyObject_SetAttrString(
        o: *mut PyObject,
        attr_name: *const c_char,
        v: *mut PyObject,
    ) -> c_int;
    pub fn PyObject_HasAttrString(o: *mut PyObject, attr_name: *const c_char) -> c_int;
    pub fn PyObject_Call(
        callable: *mut PyObject,
        args: *mut PyObject,
        kwargs: *mut PyObject,
    ) -> *mut PyObject;
    pub fn PyObject_CallObject(callable: *mut PyObject, args: *mut PyObject) -> *mut PyObject;
    pub fn PyObject_Str(o: *mut PyObject) -> *mut PyObject;
    pub fn PyObject_Repr(o: *mut PyObject) -> *mut PyObject;
    pub fn PyObject_IsTrue(o: *mut PyObject) -> c_int;
    pub fn PyObject_Length(o: *mut PyObject) -> Py_ssize_t;
    pub fn PyObject_GetItem(o: *mut PyObject, key: *mut PyObject) -> *mut PyObject;
    pub fn PyObject_SetItem(o: *mut PyObject, key: *mut PyObject, v: *mut PyObject) -> c_int;
    pub fn PyObject_Type(o: *mut PyObject) -> *mut PyObject;
    pub fn PyObject_RichCompareBool(o1: *mut PyObject, o2: *mut PyObject, opid: c_int) -> c_int;
}

// === None, True, False singletons ===

extern "C" {
    // These are actually macros in CPython, but 3.13 provides function equivalents
    pub fn Py_None() -> *mut PyObject;
    pub fn Py_True() -> *mut PyObject;
    pub fn Py_False() -> *mut PyObject;
}

// In case function variants aren't available, we can use the global symbols
extern "C" {
    pub static mut _Py_NoneStruct: PyObject;
    pub static mut _Py_TrueStruct: PyObject;
    pub static mut _Py_FalseStruct: PyObject;
}

// === Error handling ===

extern "C" {
    pub fn PyErr_Occurred() -> *mut PyObject;
    pub fn PyErr_Clear();
    pub fn PyErr_Fetch(
        ptype: *mut *mut PyObject,
        pvalue: *mut *mut PyObject,
        ptraceback: *mut *mut PyObject,
    );
    pub fn PyErr_Restore(typ: *mut PyObject, value: *mut PyObject, traceback: *mut PyObject);
    pub fn PyErr_SetString(typ: *mut PyObject, message: *const c_char);
    pub fn PyErr_Format(exception: *mut PyObject, format: *const c_char, ...) -> *mut PyObject;
    pub fn PyErr_NormalizeException(
        exc: *mut *mut PyObject,
        val: *mut *mut PyObject,
        tb: *mut *mut PyObject,
    );

    // Standard exception types
    pub static mut PyExc_RuntimeError: *mut PyObject;
    pub static mut PyExc_TypeError: *mut PyObject;
    pub static mut PyExc_ValueError: *mut PyObject;
    pub static mut PyExc_KeyError: *mut PyObject;
    pub static mut PyExc_IndexError: *mut PyObject;
    pub static mut PyExc_AttributeError: *mut PyObject;
    pub static mut PyExc_SystemError: *mut PyObject;
    pub static mut PyExc_Exception: *mut PyObject;
}

// === Integer (Long) objects ===

extern "C" {
    pub fn PyLong_FromLong(v: c_long) -> *mut PyObject;
    pub fn PyLong_FromUnsignedLong(v: core::ffi::c_ulong) -> *mut PyObject;
    pub fn PyLong_FromLongLong(v: core::ffi::c_longlong) -> *mut PyObject;
    pub fn PyLong_FromUnsignedLongLong(v: core::ffi::c_ulonglong) -> *mut PyObject;
    pub fn PyLong_FromDouble(v: core::ffi::c_double) -> *mut PyObject;
    pub fn PyLong_AsLong(o: *mut PyObject) -> c_long;
    pub fn PyLong_AsUnsignedLong(o: *mut PyObject) -> core::ffi::c_ulong;
    pub fn PyLong_AsLongLong(o: *mut PyObject) -> core::ffi::c_longlong;
    pub fn PyLong_AsUnsignedLongLong(o: *mut PyObject) -> core::ffi::c_ulonglong;
    pub fn PyLong_Check(o: *mut PyObject) -> c_int;
}

// === Float objects ===

extern "C" {
    pub fn PyFloat_FromDouble(v: core::ffi::c_double) -> *mut PyObject;
    pub fn PyFloat_AsDouble(o: *mut PyObject) -> core::ffi::c_double;
    pub fn PyFloat_Check(o: *mut PyObject) -> c_int;
}

// === Boolean objects ===

extern "C" {
    pub fn PyBool_FromLong(v: c_long) -> *mut PyObject;
}

// === String (Unicode) objects ===

extern "C" {
    pub fn PyUnicode_FromString(u: *const c_char) -> *mut PyObject;
    pub fn PyUnicode_FromStringAndSize(u: *const c_char, size: Py_ssize_t) -> *mut PyObject;
    pub fn PyUnicode_AsUTF8(unicode: *mut PyObject) -> *const c_char;
    pub fn PyUnicode_AsUTF8AndSize(
        unicode: *mut PyObject,
        size: *mut Py_ssize_t,
    ) -> *const c_char;
    pub fn PyUnicode_GetLength(unicode: *mut PyObject) -> Py_ssize_t;
    pub fn PyUnicode_Check(o: *mut PyObject) -> c_int;
}

// === Bytes objects ===

extern "C" {
    pub fn PyBytes_FromStringAndSize(v: *const c_char, len: Py_ssize_t) -> *mut PyObject;
    pub fn PyBytes_AsString(o: *mut PyObject) -> *const c_char;
    pub fn PyBytes_Size(o: *mut PyObject) -> Py_ssize_t;
    pub fn PyBytes_AsStringAndSize(
        o: *mut PyObject,
        buffer: *mut *const c_char,
        length: *mut Py_ssize_t,
    ) -> c_int;
    pub fn PyBytes_Check(o: *mut PyObject) -> c_int;
}

// === List objects ===

extern "C" {
    pub fn PyList_New(len: Py_ssize_t) -> *mut PyObject;
    pub fn PyList_Size(list: *mut PyObject) -> Py_ssize_t;
    pub fn PyList_GetItem(list: *mut PyObject, index: Py_ssize_t) -> *mut PyObject; // borrowed ref
    pub fn PyList_SetItem(list: *mut PyObject, index: Py_ssize_t, item: *mut PyObject) -> c_int; // steals ref
    pub fn PyList_Append(list: *mut PyObject, item: *mut PyObject) -> c_int;
    pub fn PyList_Check(o: *mut PyObject) -> c_int;
}

// === Tuple objects ===

extern "C" {
    pub fn PyTuple_New(len: Py_ssize_t) -> *mut PyObject;
    pub fn PyTuple_Size(p: *mut PyObject) -> Py_ssize_t;
    pub fn PyTuple_GetItem(p: *mut PyObject, pos: Py_ssize_t) -> *mut PyObject; // borrowed ref
    pub fn PyTuple_SetItem(p: *mut PyObject, pos: Py_ssize_t, o: *mut PyObject) -> c_int; // steals ref
    pub fn PyTuple_Check(o: *mut PyObject) -> c_int;
}

// === Dict objects ===

extern "C" {
    pub fn PyDict_New() -> *mut PyObject;
    pub fn PyDict_SetItem(
        dp: *mut PyObject,
        key: *mut PyObject,
        item: *mut PyObject,
    ) -> c_int;
    pub fn PyDict_SetItemString(
        dp: *mut PyObject,
        key: *const c_char,
        item: *mut PyObject,
    ) -> c_int;
    pub fn PyDict_GetItem(dp: *mut PyObject, key: *mut PyObject) -> *mut PyObject; // borrowed ref
    pub fn PyDict_GetItemString(dp: *mut PyObject, key: *const c_char) -> *mut PyObject; // borrowed ref
    pub fn PyDict_Contains(dp: *mut PyObject, key: *mut PyObject) -> c_int;
    pub fn PyDict_Keys(dp: *mut PyObject) -> *mut PyObject;
    pub fn PyDict_Values(dp: *mut PyObject) -> *mut PyObject;
    pub fn PyDict_Size(dp: *mut PyObject) -> Py_ssize_t;
    pub fn PyDict_Next(
        dp: *mut PyObject,
        ppos: *mut Py_ssize_t,
        pkey: *mut *mut PyObject,
        pvalue: *mut *mut PyObject,
    ) -> c_int;
    pub fn PyDict_Check(o: *mut PyObject) -> c_int;
}

// === Module objects ===

extern "C" {
    pub fn PyImport_ImportModule(name: *const c_char) -> *mut PyObject;
    pub fn PyImport_AddModule(name: *const c_char) -> *mut PyObject; // borrowed ref
    pub fn PyModule_GetDict(module: *mut PyObject) -> *mut PyObject; // borrowed ref
}

// === Running code ===

extern "C" {
    pub fn PyRun_SimpleString(command: *const c_char) -> c_int;
    pub fn PyRun_String(
        str: *const c_char,
        start: c_int,
        globals: *mut PyObject,
        locals: *mut PyObject,
    ) -> *mut PyObject;

    // File input constants
    // Py_eval_input = 258, Py_file_input = 257, Py_single_input = 256
}

/// Py_file_input — parse a module (sequence of statements)
pub const PY_FILE_INPUT: c_int = 257;
/// Py_eval_input — parse a single expression
pub const PY_EVAL_INPUT: c_int = 258;
/// Py_single_input — parse a single interactive statement
pub const PY_SINGLE_INPUT: c_int = 256;

// === Sys module ===

extern "C" {
    pub fn PySys_SetPath(path: *const c_char);
    pub fn PySys_GetObject(name: *const c_char) -> *mut PyObject; // borrowed ref
}

// === Type checking ===

extern "C" {
    pub fn PyType_IsSubtype(a: *mut PyObject, b: *mut PyObject) -> c_int;
}

// === Conversion helpers ===

extern "C" {
    pub fn PyNumber_Long(o: *mut PyObject) -> *mut PyObject;
    pub fn PyNumber_Float(o: *mut PyObject) -> *mut PyObject;
}

// === Iterator protocol ===

extern "C" {
    pub fn PyIter_Next(o: *mut PyObject) -> *mut PyObject;
    pub fn PyObject_GetIter(o: *mut PyObject) -> *mut PyObject;
}

// === Sequence protocol ===

extern "C" {
    pub fn PySequence_GetItem(o: *mut PyObject, i: Py_ssize_t) -> *mut PyObject;
    pub fn PySequence_Length(o: *mut PyObject) -> Py_ssize_t;
}

// === Coroutine / Generator support (for async canister methods) ===

extern "C" {
    pub fn PyCoro_CheckExact(o: *mut PyObject) -> c_int;
    pub fn PyGen_CheckExact(o: *mut PyObject) -> c_int;
}

// === Memory ===

extern "C" {
    pub fn PyMem_Malloc(size: usize) -> *mut c_void;
    pub fn PyMem_Free(ptr: *mut c_void);
}

// === Method/Module definition types (for C extension modules) ===

/// Method calling convention flags
pub const METH_VARARGS: c_int = 0x0001;
pub const METH_NOARGS: c_int = 0x0004;
pub const METH_O: c_int = 0x0008;

/// PyCFunction type — the C function pointer type for Python callable methods.
pub type PyCFunction =
    unsafe extern "C" fn(slf: *mut PyObject, args: *mut PyObject) -> *mut PyObject;

/// Method definition entry for PyMethodDef arrays.
#[repr(C)]
pub struct PyMethodDef {
    pub ml_name: *const c_char,
    pub ml_meth: Option<PyCFunction>,
    pub ml_flags: c_int,
    pub ml_doc: *const c_char,
}

// PyMethodDef needs to be Send+Sync for static storage on wasm32 (single-threaded)
unsafe impl Send for PyMethodDef {}
unsafe impl Sync for PyMethodDef {}

/// Module definition for PyModule_Create.
#[repr(C)]
pub struct PyModuleDef {
    pub m_base: PyModuleDef_Base,
    pub m_name: *const c_char,
    pub m_doc: *const c_char,
    pub m_size: Py_ssize_t,
    pub m_methods: *mut PyMethodDef,
    pub m_slots: *mut c_void,
    pub m_traverse: Option<unsafe extern "C" fn(*mut PyObject, *mut c_void, *mut c_void) -> c_int>,
    pub m_clear: Option<unsafe extern "C" fn(*mut PyObject) -> c_int>,
    pub m_free: Option<unsafe extern "C" fn(*mut c_void)>,
}

unsafe impl Send for PyModuleDef {}
unsafe impl Sync for PyModuleDef {}

/// Base struct for PyModuleDef (simplified for our use case).
#[repr(C)]
pub struct PyModuleDef_Base {
    pub ob_base: PyObject_HEAD,
    pub m_init: Option<unsafe extern "C" fn() -> *mut PyObject>,
    pub m_index: Py_ssize_t,
    pub m_copy: *mut PyObject,
}

unsafe impl Send for PyModuleDef_Base {}
unsafe impl Sync for PyModuleDef_Base {}

/// Simplified PyObject_HEAD for module def base.
#[repr(C)]
pub struct PyObject_HEAD {
    pub ob_refcnt: Py_ssize_t,
    pub ob_type: *mut PyObject,
}

unsafe impl Send for PyObject_HEAD {}
unsafe impl Sync for PyObject_HEAD {}

/// Zero-initialized module def base (equivalent to PyModuleDef_HEAD_INIT macro).
pub const PyModuleDef_HEAD_INIT: PyModuleDef_Base = PyModuleDef_Base {
    ob_base: PyObject_HEAD {
        ob_refcnt: 1,
        ob_type: core::ptr::null_mut(),
    },
    m_init: None,
    m_index: 0,
    m_copy: core::ptr::null_mut(),
};

extern "C" {
    pub fn PyModule_Create(module: *mut PyModuleDef) -> *mut PyObject;
    pub fn PyModule_AddObject(
        module: *mut PyObject,
        name: *const c_char,
        value: *mut PyObject,
    ) -> c_int;
}
