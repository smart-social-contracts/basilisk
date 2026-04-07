from basilisk import query


@query
def say(phrase: str) -> str:
    return phrase
