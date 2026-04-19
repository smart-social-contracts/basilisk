from basilisk import (
    Async,
    CallResult,
    ic,
    Principal,
    query,
    Service,
    service_query,
    service_update,
    text,
    update,
    Variant,
    Vec,
)


class SomeService(Service):
    _arg_types = {
        "echo_text": "text",
    }

    @service_query
    def query1(self) -> bool:
        ...

    @service_update
    def update1(self) -> str:
        ...

    @service_update
    def echo_text(self, payload: text) -> text:
        ...


some_service = SomeService(Principal.from_str("ryjl3-tyaaa-aaaaa-aaaba-cai"))


class Update1Result(Variant, total=False):
    Ok: str
    Err: str


@query
def service_param(some_service: SomeService) -> SomeService:
    return some_service


@query
def service_return_type() -> SomeService:
    return some_service


@update
def service_list(some_services: Vec[SomeService]) -> Vec[SomeService]:
    return some_services


@update
def service_cross_canister_call(some_service: SomeService) -> Async[Update1Result]:
    result: CallResult[str] = yield some_service.update1()

    if result.Err is not None:
        return {"Err": result.Err}

    return {"Ok": result.Ok}


@update
def service_call_with_json_text(some_service: SomeService) -> Async[Update1Result]:
    """Call echo_text with a JSON payload containing quotes.

    This tests that _to_candid_text correctly escapes inner double-quotes
    in string arguments and that candid_encode handles them without trapping.
    """
    json_payload = '{"registry_canister_id":"abc-123","ext_id":"welcome","version":null}'
    result: CallResult[str] = yield some_service.echo_text(json_payload)

    if result.Err is not None:
        return {"Err": result.Err}

    return {"Ok": result.Ok}


@update
def test_candid_encode_error() -> text:
    """Test that ic.candid_encode with invalid input raises a catchable error
    instead of trapping the canister."""
    try:
        ic.candid_encode('(invalid { candid "text)')
        return "ERROR: should have raised"
    except Exception as e:
        return f"caught: {type(e).__name__}: {e}"
