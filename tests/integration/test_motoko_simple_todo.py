"""Integration tests for examples/motoko_examples/simple-to-do — todo list canister."""

import pytest
from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR
import os

EXAMPLE = "motoko_examples/simple-to-do"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_get_todos_initially_empty(canister):
    raw = call_canister(canister, "get_todos", example_dir=EXAMPLE_DIR)
    assert "vec {}" in raw or raw.strip() == "(vec {})"


def test_add_todo(canister):
    result = parse_candid_text(call_canister(canister, "add_todo", '("Buy milk")', example_dir=EXAMPLE_DIR))
    assert result == 0


def test_add_todo_second(canister):
    result = parse_candid_text(call_canister(canister, "add_todo", '("Walk dog")', example_dir=EXAMPLE_DIR))
    assert result == 1


def test_get_todos_after_adding(canister):
    raw = call_canister(canister, "get_todos", example_dir=EXAMPLE_DIR)
    assert "Buy milk" in raw


def test_complete_todo(canister):
    call_canister(canister, "complete_todo", "(0 : nat)", example_dir=EXAMPLE_DIR)
    raw = call_canister(canister, "get_todos", example_dir=EXAMPLE_DIR)
    assert "true" in raw


def test_show_todos(canister):
    result = parse_candid_text(call_canister(canister, "show_todos", example_dir=EXAMPLE_DIR))
    assert "Buy milk" in result


def test_clear_completed(canister):
    call_canister(canister, "clear_completed", example_dir=EXAMPLE_DIR)
    raw = call_canister(canister, "get_todos", example_dir=EXAMPLE_DIR)
    assert "Walk dog" in raw
    assert "Buy milk" not in raw
