//! Cedar authorization exposed as the `_basilisk_cedar` CPython module.
//!
//! Deliberately dumb: it knows about schemas, policies and entities, and nothing
//! about whatever application is using it. Ergonomics belong in a Python layer
//! above this one.
//!
//! The schema and policy set are parsed once, at canister init or upgrade, and
//! held here. Parsing dominates everything else — roughly 20M instructions
//! against ~711k for a decision — so it must never happen per request.
//!
//! `authorize_many` exists because listing is the common case: it crosses the
//! FFI boundary once and reuses one parsed entity store across every candidate
//! row, rather than paying both costs per row.
//!
//! Every entry point returns a JSON envelope rather than a bare value, so that a
//! failure is distinguishable from a denial. Conflating the two is how a broken
//! deployment comes to look like a working one that simply denies everything.

use std::cell::RefCell;
use std::str::FromStr;

use basilisk_cpython::ffi;
use basilisk_cpython::PyObjectRef;
use cedar_policy::{
    ActionConstraint, Authorizer, Context, Decision, Effect, Entities, EntityUid, PolicySet,
    PrincipalConstraint, Request, ResourceConstraint, Schema, ValidationMode, Validator,
};

struct Loaded {
    schema: Schema,
    policies: PolicySet,
}

thread_local! {
    static LOADED: RefCell<Option<Loaded>> = RefCell::new(None);
}

/// Create the `_basilisk_cedar` Python module.
pub fn basilisk_cedar_create_module() -> Result<PyObjectRef, basilisk_cpython::PyError> {
    static mut METHODS: [ffi::PyMethodDef; 4] = unsafe { core::mem::zeroed() };

    unsafe {
        let methods = &mut METHODS;
        let mut i = 0;

        macro_rules! add_method {
            ($name:expr, $func:ident, $flags:expr) => {
                methods[i] = ffi::PyMethodDef {
                    ml_name: concat!($name, "\0").as_ptr() as *const core::ffi::c_char,
                    ml_meth: Some($func),
                    ml_flags: $flags,
                    ml_doc: core::ptr::null(),
                };
                i += 1;
            };
        }

        add_method!("load", cedar_load, ffi::METH_VARARGS);
        add_method!("is_authorized", cedar_is_authorized, ffi::METH_VARARGS);
        add_method!("authorize_many", cedar_authorize_many, ffi::METH_VARARGS);

        methods[i] = core::mem::zeroed();

        static mut MODULE_DEF: ffi::PyModuleDef = unsafe { core::mem::zeroed() };
        MODULE_DEF.m_base = ffi::PyModuleDef_HEAD_INIT;
        MODULE_DEF.m_name = b"_basilisk_cedar\0".as_ptr() as *const core::ffi::c_char;
        MODULE_DEF.m_doc = core::ptr::null();
        MODULE_DEF.m_size = -1;
        MODULE_DEF.m_methods = METHODS.as_mut_ptr();

        let module = ffi::PyModule_Create(&mut MODULE_DEF as *mut ffi::PyModuleDef);
        if module.is_null() {
            return Err(basilisk_cpython::PyError::new(
                "SystemError",
                "Failed to create _basilisk_cedar module",
            ));
        }

        let sys_import =
            ffi::PyImport_ImportModule(b"sys\0".as_ptr() as *const core::ffi::c_char);
        if !sys_import.is_null() {
            let modules = ffi::PyObject_GetAttrString(
                sys_import,
                b"modules\0".as_ptr() as *const core::ffi::c_char,
            );
            if !modules.is_null() {
                ffi::PyDict_SetItemString(
                    modules,
                    b"_basilisk_cedar\0".as_ptr() as *const core::ffi::c_char,
                    module,
                );
            }
        }

        PyObjectRef::from_owned(module).ok_or_else(|| {
            basilisk_cpython::PyError::new("SystemError", "null _basilisk_cedar module")
        })
    }
}

/// `load(schema_src, policy_src) -> json`
///
/// `{"ok": true}`, or `{"error": "..."}` when the schema or policies fail to
/// parse or the policies do not typecheck against the schema.
///
/// Validation runs here rather than in a publisher's CI because policies arrive
/// at runtime from third parties, so the canister cannot take their word for it.
/// A realm can then refuse an extension whose policies do not typecheck, instead
/// of discovering it on a live request.
unsafe extern "C" fn cedar_load(
    _self: *mut ffi::PyObject,
    args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let t = match basilisk_cpython::PyTuple::from_object_unchecked(args) {
        Some(t) => t,
        None => return error("load: expected (schema, policies)"),
    };
    let schema_src = match arg_str(&t, 0) {
        Ok(s) => s,
        Err(e) => return error(&format!("load: schema {e}")),
    };
    let policy_src = match arg_str(&t, 1) {
        Ok(s) => s,
        Err(e) => return error(&format!("load: policies {e}")),
    };

    let schema = match Schema::from_cedarschema_str(&schema_src) {
        Ok((s, _warnings)) => s,
        Err(e) => return error(&format!("schema: {e}")),
    };
    let policies = match PolicySet::from_str(&policy_src) {
        Ok(p) => p,
        Err(e) => return error(&format!("policies: {e}")),
    };

    let result = Validator::new(schema.clone()).validate(&policies, ValidationMode::Strict);
    if !result.validation_passed() {
        let msgs: Vec<String> = result.validation_errors().map(|e| e.to_string()).collect();
        return error(&format!("validation: {}", msgs.join("; ")));
    }

    let warnings = breadth_warnings(&policies);

    LOADED.with(|l| *l.borrow_mut() = Some(Loaded { schema, policies }));

    let body = serde_json::json!({ "ok": true, "warnings": warnings });
    match serde_json::to_string(&body) {
        Ok(s) => out(&s),
        Err(_) => out(r#"{"ok":true,"warnings":[]}"#),
    }
}

/// Flag permits that grant far more than an author probably meant.
///
/// A restricted schema stops an extension's policy reaching core data, but says
/// nothing about how much of the extension's *own* data it hands out.
/// `permit (principal, action, resource);` typechecks cleanly and gives every
/// user full access to every record the extension owns — for a procurement
/// extension, sealed bids readable before opening. Cheap to spot and almost
/// always a mistake.
///
/// These warn rather than reject: a blanket permit is legitimate for an
/// extension whose data is meant to be public, and nothing here can tell the
/// difference. Refusing would make that case unimplementable.
fn breadth_warnings(policies: &PolicySet) -> Vec<String> {
    let mut warnings = Vec::new();
    for policy in policies.policies() {
        // Only `permit` grants anything. A wide-open `forbid` is how the realm's
        // guardrails are written, and warning about those would teach people to
        // ignore the warning.
        if policy.effect() != Effect::Permit {
            continue;
        }

        let principal_any = matches!(policy.principal_constraint(), PrincipalConstraint::Any);
        let action_any = matches!(policy.action_constraint(), ActionConstraint::Any);
        let resource_any = matches!(policy.resource_constraint(), ResourceConstraint::Any);

        // The `when`/`unless` clauses live in the EST; the scope accessors above
        // do not expose them.
        let unconditional = policy
            .to_json()
            .ok()
            .and_then(|j| {
                j.get("conditions")
                    .and_then(|c| c.as_array())
                    .map(|a| a.is_empty())
            })
            .unwrap_or(false);

        if principal_any && action_any && resource_any && unconditional {
            warnings.push(format!(
                "{}: blanket permit — grants every principal full access to every \
                 resource in scope",
                policy.id()
            ));
        } else if principal_any && resource_any && !unconditional {
            warnings.push(format!(
                "{}: broad permit — any principal on any resource, limited only by \
                 its condition",
                policy.id()
            ));
        }
    }
    warnings
}

/// `is_authorized(principal, action, resource, entities_json[, context_json]) -> json`
///
/// `{"decision": "allow"}`, `{"decision": "deny"}`, or `{"error": "..."}`.
unsafe extern "C" fn cedar_is_authorized(
    _self: *mut ffi::PyObject,
    args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let t = match basilisk_cpython::PyTuple::from_object_unchecked(args) {
        Some(t) => t,
        None => return error("is_authorized: expected (principal, action, resource, entities)"),
    };

    let principal = match arg_str(&t, 0) {
        Ok(s) => s,
        Err(e) => return error(&format!("principal {e}")),
    };
    let action = match arg_str(&t, 1) {
        Ok(s) => s,
        Err(e) => return error(&format!("action {e}")),
    };
    let resource = match arg_str(&t, 2) {
        Ok(s) => s,
        Err(e) => return error(&format!("resource {e}")),
    };
    let entities_json = match arg_str(&t, 3) {
        Ok(s) => s,
        Err(e) => return error(&format!("entities {e}")),
    };
    let context_json = t.get_item(4).and_then(|o| o.extract_str().ok());

    LOADED.with(|l| {
        let borrowed = l.borrow();
        let loaded = match borrowed.as_ref() {
            Some(x) => x,
            None => return error("no policies loaded; call load() first"),
        };
        let entities = match Entities::from_json_str(&entities_json, Some(&loaded.schema)) {
            Ok(e) => e,
            Err(e) => return error(&format!("entities: {e}")),
        };
        let context = match build_context(context_json.as_deref()) {
            Ok(c) => c,
            Err(e) => return error(&e),
        };
        let (p, a, r) = match (
            EntityUid::from_str(&principal),
            EntityUid::from_str(&action),
            EntityUid::from_str(&resource),
        ) {
            (Ok(p), Ok(a), Ok(r)) => (p, a, r),
            _ => return error("principal, action or resource is not a valid entity uid"),
        };
        let request = match Request::new(p, a, r, context, Some(&loaded.schema)) {
            Ok(req) => req,
            Err(e) => return error(&format!("request: {e}")),
        };
        let decision = Authorizer::new()
            .is_authorized(&request, &loaded.policies, &entities)
            .decision();
        out(if decision == Decision::Allow {
            r#"{"decision":"allow"}"#
        } else {
            r#"{"decision":"deny"}"#
        })
    })
}

/// `authorize_many(principal, action, resources_json, entities_json[, context_json]) -> json`
///
/// `resources_json` is a JSON array of resource uids; the reply is
/// `{"allowed": [...]}` with the subset permitted, or `{"error": "..."}`.
///
/// Everything that does not vary per row is hoisted out of the loop: the entity
/// store, the principal and action uids, the context and the `Authorizer`.
/// Building a schema-validated `Request` per row cost ~1.6M instructions against
/// ~711k for the evaluation itself, so the per-row request skips revalidation —
/// `load` already validated these policies against this schema.
unsafe extern "C" fn cedar_authorize_many(
    _self: *mut ffi::PyObject,
    args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let t = match basilisk_cpython::PyTuple::from_object_unchecked(args) {
        Some(t) => t,
        None => return error("authorize_many: expected (principal, action, resources, entities)"),
    };

    let principal = match arg_str(&t, 0) {
        Ok(s) => s,
        Err(e) => return error(&format!("principal {e}")),
    };
    let action = match arg_str(&t, 1) {
        Ok(s) => s,
        Err(e) => return error(&format!("action {e}")),
    };
    let resources_json = match arg_str(&t, 2) {
        Ok(s) => s,
        Err(e) => return error(&format!("resources {e}")),
    };
    let entities_json = match arg_str(&t, 3) {
        Ok(s) => s,
        Err(e) => return error(&format!("entities {e}")),
    };
    let context_json = t.get_item(4).and_then(|o| o.extract_str().ok());

    let resources: Vec<String> = match serde_json::from_str(&resources_json) {
        Ok(v) => v,
        Err(e) => return error(&format!("resources: {e}")),
    };

    LOADED.with(|l| {
        let borrowed = l.borrow();
        let loaded = match borrowed.as_ref() {
            Some(x) => x,
            None => return error("no policies loaded; call load() first"),
        };
        let entities = match Entities::from_json_str(&entities_json, Some(&loaded.schema)) {
            Ok(e) => e,
            Err(e) => return error(&format!("entities: {e}")),
        };
        let context = match build_context(context_json.as_deref()) {
            Ok(c) => c,
            Err(e) => return error(&e),
        };
        let (p, a) = match (EntityUid::from_str(&principal), EntityUid::from_str(&action)) {
            (Ok(p), Ok(a)) => (p, a),
            _ => return error("principal or action is not a valid entity uid"),
        };
        let authorizer = Authorizer::new();

        let mut allowed = Vec::new();
        for r in resources {
            let uid = match EntityUid::from_str(&r) {
                Ok(u) => u,
                // A malformed uid is the caller's bug, but denying the row is
                // the safe reading of it, and reporting it would abandon the
                // rows that are fine.
                Err(_) => continue,
            };
            let request =
                match Request::new(p.clone(), a.clone(), uid, context.clone(), None) {
                    Ok(req) => req,
                    Err(_) => continue,
                };
            if authorizer
                .is_authorized(&request, &loaded.policies, &entities)
                .decision()
                == Decision::Allow
            {
                allowed.push(r);
            }
        }

        match serde_json::to_string(&serde_json::json!({ "allowed": allowed })) {
            Ok(s) => out(&s),
            Err(e) => error(&format!("encoding reply: {e}")),
        }
    })
}

/// Parse the request context, which carries facts about *who is asking* rather
/// than about the data. An absent context is empty, not an error: host-originated
/// calls legitimately have nothing to say.
fn build_context(context_json: Option<&str>) -> Result<Context, String> {
    match context_json {
        None => Ok(Context::empty()),
        Some(s) if s.trim().is_empty() => Ok(Context::empty()),
        Some(s) => Context::from_json_str(s, None).map_err(|e| format!("context: {e}")),
    }
}

fn arg_str(t: &basilisk_cpython::PyTuple, index: usize) -> Result<String, String> {
    match t.get_item(index) {
        None => Err("is missing".to_string()),
        Some(o) => o.extract_str().map_err(|_| "must be str".to_string()),
    }
}

fn error(message: &str) -> *mut ffi::PyObject {
    let body = serde_json::json!({ "error": message });
    match serde_json::to_string(&body) {
        Ok(s) => out(&s),
        // The message itself failed to encode, so say something rather than
        // returning null and tripping a bare SystemError in the caller.
        Err(_) => out(r#"{"error":"unencodable error"}"#),
    }
}

fn out(s: &str) -> *mut ffi::PyObject {
    match PyObjectRef::from_str(s) {
        Ok(o) => o.into_ptr(),
        Err(_) => core::ptr::null_mut(),
    }
}
