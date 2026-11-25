"""Tests for scripts/check_no_start_function.py, the CI check that a template has no wasm start function."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from check_no_start_function import has_start_section, main  # noqa: E402

HEADER = b"\0asm\x01\0\0\0"
TYPE_SECTION = b"\x01\x04\x01\x60\x00\x00"  # one type: () -> ()
FUNCTION_SECTION = b"\x03\x02\x01\x00"  # one function of that type
START_SECTION = b"\x08\x01\x00"  # start: function 0
CODE_SECTION = b"\x0a\x04\x01\x02\x00\x0b"  # its body: end


def test_a_module_without_start_passes(tmp_path):
    module = HEADER + TYPE_SECTION + FUNCTION_SECTION + CODE_SECTION
    assert not has_start_section(module)
    path = tmp_path / "plain.wasm"
    path.write_bytes(module)
    assert main([str(path)]) == 0


def test_a_module_with_start_fails(tmp_path, capsys):
    module = HEADER + TYPE_SECTION + FUNCTION_SECTION + START_SECTION + CODE_SECTION
    assert has_start_section(module)
    path = tmp_path / "start.wasm"
    path.write_bytes(module)
    assert main([str(path)]) == 1
    assert "has a wasm start function" in capsys.readouterr().out


def test_not_wasm_is_an_error():
    with pytest.raises(ValueError):
        has_start_section(b"not wasm")
