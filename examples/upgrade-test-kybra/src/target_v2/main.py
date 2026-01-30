"""
Target Canister v2 - the upgraded version
"""

from kybra import query


@query
def get_version() -> str:
    return "v2"


@query
def greet(name: str) -> str:
    return f"Greetings, {name}! (upgraded)"
