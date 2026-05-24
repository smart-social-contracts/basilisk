from basilisk import query, text


@query
def greet(name: text) -> text:
    return f"Hello, {name}!"
