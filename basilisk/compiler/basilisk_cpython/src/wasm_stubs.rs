//! Stub implementations for C symbols that CPython's static library references
//! but are not available in the IC/WASI environment.
//!
//! With the custom config.c approach (see CPYTHON_MIGRATION_NOTES.md section 7),
//! most extension module stubs (pyexpat, _decimal, _hashlib) are no longer needed
//! because those modules are excluded from the link via the trimmed _PyImport_Inittab.
//!
//! Remaining stubs:
//! - atexit/__cxa_atexit — prevent crash during WASI cleanup
//! - dlopen/dlsym/dlerror — dynamic loading (not available in WASI)
//! - POSIX/Linux-specific functions — referenced by posixmodule.o (still linked)

#![allow(non_snake_case)]
#![allow(unused_variables)]

use core::ffi::c_char;

// ---------------------------------------------------------------------------
// atexit / __cxa_atexit — prevent CPython from registering cleanup handlers
// that crash during WASI __funcs_on_exit after each canister method call.
// On IC canisters, the process lives for the canister lifetime; no cleanup needed.
// ---------------------------------------------------------------------------

#[no_mangle]
pub unsafe extern "C" fn atexit(_func: *mut u8) -> i32 { 0 }

#[no_mangle]
pub unsafe extern "C" fn __cxa_atexit(_func: *mut u8, _arg: *mut u8, _dso_handle: *mut u8) -> i32 { 0 }

// ---------------------------------------------------------------------------
// dlopen / dlsym / dlerror  (dynamic loading — not available in WASI)
// ---------------------------------------------------------------------------

#[no_mangle]
pub unsafe extern "C" fn dlopen(filename: *const c_char, flags: i32) -> *mut u8 { core::ptr::null_mut() }

#[no_mangle]
pub unsafe extern "C" fn dlsym(handle: *mut u8, symbol: *const c_char) -> *mut u8 { core::ptr::null_mut() }

#[no_mangle]
pub unsafe extern "C" fn dlerror() -> *const c_char { core::ptr::null() }

// ---------------------------------------------------------------------------
// POSIX / Linux-specific functions — stubs for symbols that CPython's
// posixmodule.o (and others) reference when built on Linux hosts.
// The CI-built CPython detects these via ./configure on Ubuntu 24.04,
// but they are not available in the WASI environment.
// ---------------------------------------------------------------------------

#[no_mangle] pub unsafe extern "C" fn memfd_create(_name: *const c_char, _flags: u32) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn copy_file_range(_fd_in: i32, _off_in: *mut i64, _fd_out: i32, _off_out: *mut i64, _len: usize, _flags: u32) -> isize { -1 }
#[no_mangle] pub unsafe extern "C" fn pidfd_open(_pid: i32, _flags: u32) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn splice(_fd_in: i32, _off_in: *mut i64, _fd_out: i32, _off_out: *mut i64, _len: usize, _flags: u32) -> isize { -1 }
#[no_mangle] pub unsafe extern "C" fn sendfile(_out_fd: i32, _in_fd: i32, _offset: *mut i64, _count: usize) -> isize { -1 }
#[no_mangle] pub unsafe extern "C" fn preadv(_fd: i32, _iov: *const u8, _iovcnt: i32, _offset: i64) -> isize { -1 }
#[no_mangle] pub unsafe extern "C" fn pwritev(_fd: i32, _iov: *const u8, _iovcnt: i32, _offset: i64) -> isize { -1 }
#[no_mangle] pub unsafe extern "C" fn preadv2(_fd: i32, _iov: *const u8, _iovcnt: i32, _offset: i64, _flags: i32) -> isize { -1 }
#[no_mangle] pub unsafe extern "C" fn pwritev2(_fd: i32, _iov: *const u8, _iovcnt: i32, _offset: i64, _flags: i32) -> isize { -1 }
#[no_mangle] pub unsafe extern "C" fn posix_fadvise(_fd: i32, _offset: i64, _len: i64, _advice: i32) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn posix_fallocate(_fd: i32, _offset: i64, _len: i64) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn sched_get_priority_max(_policy: i32) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn sched_get_priority_min(_policy: i32) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn sched_setaffinity(_pid: i32, _cpusetsize: usize, _mask: *const u8) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn sched_getaffinity(_pid: i32, _cpusetsize: usize, _mask: *mut u8) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn sched_setscheduler(_pid: i32, _policy: i32, _param: *const u8) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn sched_getscheduler(_pid: i32) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn sched_setparam(_pid: i32, _param: *const u8) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn sched_getparam(_pid: i32, _param: *mut u8) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn sched_rr_get_interval(_pid: i32, _tp: *mut u8) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn getpriority(_which: i32, _who: i32) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn setpriority(_which: i32, _who: i32, _prio: i32) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn getrlimit(_resource: i32, _rlim: *mut u8) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn setrlimit(_resource: i32, _rlim: *const u8) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn prlimit(_pid: i32, _resource: i32, _new_limit: *const u8, _old_limit: *mut u8) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn waitid(_idtype: i32, _id: u32, _infop: *mut u8, _options: i32) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn wait3(_status: *mut i32, _options: i32, _rusage: *mut u8) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn wait4(_pid: i32, _status: *mut i32, _options: i32, _rusage: *mut u8) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn nice(_inc: i32) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn getloadavg(_loadavg: *mut f64, _nelem: i32) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn getlogin() -> *mut c_char { core::ptr::null_mut() }
#[no_mangle] pub unsafe extern "C" fn getlogin_r(_buf: *mut c_char, _bufsize: usize) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn setgroups(_size: usize, _list: *const u32) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn getgroups(_size: i32, _list: *mut u32) -> i32 { 0 }
#[no_mangle] pub unsafe extern "C" fn getgrouplist(_user: *const c_char, _group: u32, _groups: *mut u32, _ngroups: *mut i32) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn initgroups(_user: *const c_char, _group: u32) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn getresuid(_ruid: *mut u32, _euid: *mut u32, _suid: *mut u32) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn getresgid(_rgid: *mut u32, _egid: *mut u32, _sgid: *mut u32) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn setresuid(_ruid: u32, _euid: u32, _suid: u32) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn setresgid(_rgid: u32, _egid: u32, _sgid: u32) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn setregid(_rgid: u32, _egid: u32) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn setreuid(_ruid: u32, _euid: u32) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn setsid() -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn getsid(_pid: i32) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn setpgid(_pid: i32, _pgid: i32) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn getpgid(_pid: i32) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn tcgetpgrp(_fd: i32) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn tcsetpgrp(_fd: i32, _pgrp: i32) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn lchown(_pathname: *const c_char, _owner: u32, _group: u32) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn fchown(_fd: i32, _owner: u32, _group: u32) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn lockf(_fd: i32, _cmd: i32, _len: i64) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn timerfd_create(_clockid: i32, _flags: i32) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn timerfd_settime(_fd: i32, _flags: i32, _new: *const u8, _old: *mut u8) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn timerfd_gettime(_fd: i32, _curr: *mut u8) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn eventfd(_initval: u32, _flags: i32) -> i32 { -1 }
#[no_mangle] pub unsafe extern "C" fn epoll_create1(_flags: i32) -> i32 { -1 }
