from basilisk import query, update, text


@query
def query1() -> bool:
    return True


@update
def update1() -> str:
    return 'SomeService update1'


@update
def echo_text(payload: text) -> text:
    return payload
