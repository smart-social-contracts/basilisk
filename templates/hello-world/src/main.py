from basilisk import query, update, text, nat64, ic


counter = 0


@query
def greet(name: text) -> text:
    return f"Hello, {name}! The counter is at {counter}."


@query
def get_counter() -> nat64:
    return counter


@update
def increment() -> nat64:
    global counter
    counter += 1
    return counter


@query
def whoami() -> text:
    return str(ic.caller())
