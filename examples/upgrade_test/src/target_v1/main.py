"""
Target Canister v1 - will be upgraded
"""

from basilisk import query


@query
def get_version() -> str:
    return "v1"


@query
def greet(name: str) -> str:
    return f"Hello, {name}!"
