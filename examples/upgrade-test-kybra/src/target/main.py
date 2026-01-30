"""
Target Canister v1 - will be upgraded
"""

from kybra import query
from my_lib import VERSION, get_greeting_prefix


@query
def get_version() -> str:
    return "v1"


@query
def get_lib_version() -> str:
    return VERSION


@query
def greet(name: str) -> str:
    return f"{get_greeting_prefix()}, {name}!"
