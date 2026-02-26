//! Type conversion helpers.
//!
//! In the template pattern, most type conversions happen dynamically via
//! candid::IDLValue (see method_dispatch.rs). This module provides only
//! the minimal conversion traits needed by the IC API and async handler code.

/// Trait for converting Rust values to Python objects (used by IC API code).
pub trait CdkActTryIntoVmValue<Context, VmValue> {
    fn try_into_vm_value(self, context: Context) -> Result<VmValue, CdkActTryIntoVmValueError>;
}

#[derive(Debug)]
pub struct CdkActTryIntoVmValueError(pub String);

/// Trait for converting Python objects to Rust values (used by IC API code).
pub trait CdkActTryFromVmValue<Ok, Err, Context> {
    fn try_from_vm_value(self, context: Context) -> Result<Ok, Err>;
}

// ─── Minimal impls needed by IC API and async handler ───────────────────────

impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for String {
    fn try_into_vm_value(
        self,
        _: (),
    ) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
        basilisk_cpython::PyObjectRef::from_str(&self)
            .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))
    }
}

impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for u64 {
    fn try_into_vm_value(
        self,
        _: (),
    ) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
        basilisk_cpython::PyObjectRef::from_u64(self)
            .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))
    }
}

impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for candid::Principal {
    fn try_into_vm_value(
        self,
        _: (),
    ) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
        let principal_class = unsafe { crate::PRINCIPAL_CLASS_OPTION.as_ref() }
            .ok_or_else(|| CdkActTryIntoVmValueError("Principal class not cached".to_string()))?;
        let from_str = principal_class
            .get_attr("from_str")
            .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;
        let text = basilisk_cpython::PyObjectRef::from_str(&self.to_text())
            .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;
        let args = basilisk_cpython::PyTuple::new(vec![text])
            .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;
        from_str
            .call(&args.into_object(), None)
            .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))
    }
}

impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef>
    for ic_cdk::api::call::RejectionCode
{
    fn try_into_vm_value(
        self,
        _: (),
    ) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
        let attribute = match self {
            ic_cdk::api::call::RejectionCode::NoError => "NoError",
            ic_cdk::api::call::RejectionCode::SysFatal => "SysFatal",
            ic_cdk::api::call::RejectionCode::SysTransient => "SysTransient",
            ic_cdk::api::call::RejectionCode::DestinationInvalid => "DestinationInvalid",
            ic_cdk::api::call::RejectionCode::CanisterReject => "CanisterReject",
            ic_cdk::api::call::RejectionCode::CanisterError => "CanisterError",
            ic_cdk::api::call::RejectionCode::Unknown => "Unknown",
        };
        let dict = basilisk_cpython::PyDict::new()
            .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;
        let none = basilisk_cpython::PyObjectRef::none();
        dict.set_item_str(attribute, &none)
            .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;
        Ok(dict.into_object())
    }
}
