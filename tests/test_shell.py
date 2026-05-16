"""
Integration tests for Basilisk CDK shell — exec, Candid parsing, edge cases.

Tests run against a live canister to verify end-to-end reliability.
Toolkit-specific tests (magic commands, database persistence) and shell modes
(one-shot, file, pipe, watch) live in ic-basilisk-toolkit.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from basilisk.shell import canister_exec, _parse_candid
from tests.conftest import exec_on_canister


# ===========================================================================
# Candid parsing (pure, no canister needed)
# ===========================================================================

class TestCandidParsing:
    """Test the Candid response parser — this is critical for reliability."""

    def test_simple_string(self):
        assert _parse_candid('("hello")') == "hello"

    def test_string_with_newlines(self):
        assert _parse_candid('("line1\\nline2")') == "line1\nline2"

    def test_string_with_escaped_quotes(self):
        assert _parse_candid('("say \\"hi\\"")') == 'say "hi"'

    def test_trailing_comma(self):
        """dfx sometimes returns trailing comma in tuple."""
        assert _parse_candid('("hello",)') == "hello"

    def test_empty_string(self):
        assert _parse_candid('("")') == ""

    def test_whitespace_around(self):
        assert _parse_candid('  ( "hello" )  ') == "hello"

    def test_multiline_candid(self):
        raw = '(\n  "line1\\nline2"\n)'
        assert _parse_candid(raw) == "line1\nline2"

    def test_non_string_passthrough(self):
        """Non-string Candid output should pass through unchanged."""
        assert _parse_candid("(42 : nat)") == "(42 : nat)"

    def test_unicode_content(self):
        assert _parse_candid('("héllo wörld 🌍")') == "héllo wörld 🌍"


# ===========================================================================
# Shell execution — basic operations
# ===========================================================================

class TestShellExec:
    """Test canister_exec against a live canister."""

    def test_simple_print(self, canister_reachable, canister, network):
        result = exec_on_canister("print('hello')", canister, network)
        assert result == "hello"

    def test_arithmetic(self, canister_reachable, canister, network):
        result = exec_on_canister("print(2 + 3)", canister, network)
        assert result == "5"

    def test_multiline_code(self, canister_reachable, canister, network):
        code = "x = 10\ny = 20\nprint(x + y)"
        result = exec_on_canister(code, canister, network)
        assert result == "30"

    def test_import_and_use(self, canister_reachable, canister, network):
        code = "import json\nprint(json.dumps({'a': 1}))"
        result = exec_on_canister(code, canister, network)
        # Canister CPython may or may not add spaces after colons
        assert result in ('{"a": 1}', '{"a":1}')

    def test_string_with_quotes(self, canister_reachable, canister, network):
        code = "print('she said \"hello\"')"
        result = exec_on_canister(code, canister, network)
        assert 'she said "hello"' in result

    def test_unicode_output(self, canister_reachable, canister, network):
        result = exec_on_canister("print('café ☕')", canister, network)
        assert "café" in result

    def test_empty_output(self, canister_reachable, canister, network):
        """Code that produces no output should return empty string."""
        result = exec_on_canister("x = 42", canister, network)
        assert result == ""

    def test_large_output(self, canister_reachable, canister, network):
        """Test output larger than typical Candid responses."""
        code = "print('A' * 5000)"
        result = exec_on_canister(code, canister, network)
        assert len(result) >= 5000
        assert result == "A" * 5000

    def test_syntax_error(self, canister_reachable, canister, network):
        """Syntax errors should be reported, not crash."""
        result = exec_on_canister("def (broken", canister, network)
        assert "SyntaxError" in result or "error" in result.lower()

    def test_runtime_error(self, canister_reachable, canister, network):
        """Runtime errors should be reported, not crash."""
        result = exec_on_canister("1/0", canister, network)
        assert "ZeroDivision" in result or "error" in result.lower()

    def test_name_error(self, canister_reachable, canister, network):
        result = exec_on_canister("print(undefined_variable_xyz)", canister, network)
        assert "NameError" in result or "error" in result.lower()

    def test_multiple_print_statements(self, canister_reachable, canister, network):
        code = "print('line1')\nprint('line2')\nprint('line3')"
        result = exec_on_canister(code, canister, network)
        lines = result.split("\n")
        assert len(lines) == 3
        assert lines[0] == "line1"
        assert lines[1] == "line2"
        assert lines[2] == "line3"


# ===========================================================================
# Persistent variables (shell session state)
# ===========================================================================

class TestPersistentVariables:
    """Test variable persistence in __shell__.

    IMPORTANT FINDING: Variables do NOT persist across separate dfx canister
    calls. Each call gets a fresh execution context. This is a known Basilisk
    OS limitation — within one interactive basilisk shell session the canister maintains
    state, but each `dfx canister call` is independent.
    """

    def test_variable_within_single_call(self, canister_reachable, canister, network):
        """Variables defined and used in the same call should work."""
        result = exec_on_canister(
            "shelltestvar = 42\nprint(shelltestvar)", canister, network
        )
        assert result == "42"

    def test_function_within_single_call(self, canister_reachable, canister, network):
        """Functions defined and called in the same execution work."""
        result = exec_on_canister(
            "def shelltestfn(x): return x * 2\nprint(shelltestfn(21))",
            canister, network,
        )
        assert result == "42"

    def test_import_within_single_call(self, canister_reachable, canister, network):
        """Imports used in the same call work."""
        result = exec_on_canister(
            "import json as shelltestjson\nprint(shelltestjson.dumps([1,2,3]))",
            canister, network,
        )
        assert result in ("[1, 2, 3]", "[1,2,3]")

    def test_variable_across_calls(self, canister_reachable, canister, network):
        """Variables set in one call should be visible in the next.
        Persistence depends on the canister's __shell__ implementation
        maintaining a per-principal namespace.
        """
        exec_on_canister("shelltestpersist = 42", canister, network)
        result = exec_on_canister("print(shelltestpersist)", canister, network)
        assert result == "42"


# ===========================================================================
# Edge cases and robustness
# ===========================================================================

class TestEdgeCases:
    """Stress tests and edge cases for reliability."""

    def test_empty_code(self, canister_reachable, canister, network):
        """Empty code should not crash."""
        result = exec_on_canister("", canister, network)
        # May return empty or whitespace
        assert isinstance(result, str)

    def test_only_whitespace(self, canister_reachable, canister, network):
        result = exec_on_canister("   \n  \n  ", canister, network)
        assert isinstance(result, str)

    def test_very_long_variable_name(self, canister_reachable, canister, network):
        name = "_test_" + "a" * 200
        result = exec_on_canister(f"{name} = 1\nprint({name})", canister, network)
        assert result == "1"

    def test_nested_data_structures(self, canister_reachable, canister, network):
        code = "import json\nprint(json.dumps({'a': [1, {'b': [2, 3]}]}))"
        result = exec_on_canister(code, canister, network)
        assert '"a"' in result
        # Canister CPython may use compact JSON
        assert "[2,3]" in result or "[2, 3]" in result

    def test_special_chars_in_string(self, canister_reachable, canister, network):
        """Strings with special chars that might break Candid encoding."""
        # Use explicit escape sequences via chr() to avoid Candid escaping issues
        code = "print('tab' + chr(9) + 'here')"
        result = exec_on_canister(code, canister, network)
        assert "tab" in result
        assert "here" in result

    def test_backslash_in_output(self, canister_reachable, canister, network):
        # Use string concatenation to avoid Candid double-escaping issues
        code = "print('path' + chr(92) + 'to' + chr(92) + 'file')"
        result = exec_on_canister(code, canister, network)
        assert "path" in result

    def test_rapid_sequential_calls(self, canister_reachable, canister, network):
        """Multiple rapid calls should all succeed."""
        results = []
        for i in range(5):
            r = exec_on_canister(f"print({i})", canister, network)
            results.append(r)
        for i in range(5):
            assert results[i] == str(i), f"Call {i} returned {results[i]!r}"

    def test_import_nonexistent_module_raises(self, canister_reachable, canister, network):
        """Importing a truly nonexistent module should raise ModuleNotFoundError."""
        code = (
            "try:\n"
            "    import thisdoesntexistforsure_xyz\n"
            "    print('BUG: should have raised')\n"
            "except ModuleNotFoundError as e:\n"
            "    print(f'OK: {e}')\n"
        )
        result = exec_on_canister(code, canister, network)
        assert "OK:" in result, f"Expected ModuleNotFoundError, got: {result}"
        assert "thisdoesntexistforsure_xyz" in result

    def test_import_stdlib_still_works(self, canister_reachable, canister, network):
        """Stdlib modules should still be importable (stubbed if unavailable in WASI)."""
        code = (
            "import socket\n"
            "print(type(socket).__name__)\n"
            "import json\n"
            "print(json.dumps({'ok': True}))\n"
        )
        result = exec_on_canister(code, canister, network)
        assert "module" in result
        assert '{"ok":true}' in result or '{"ok": true}' in result

    def test_import_internal_underscore_module(self, canister_reachable, canister, network):
        """Internal _-prefixed modules should still be stubbable."""
        code = (
            "import _fake_internal_module\n"
            "print(type(_fake_internal_module).__name__)\n"
        )
        result = exec_on_canister(code, canister, network)
        assert "module" in result

    def test_import_user_uploaded_py_file(self, canister_reachable, canister, network):
        """User-uploaded .py files on memfs should be importable (#34)."""
        # Write a module to memfs (avoid backslash-n in content — Candid
        # escaping in canister_exec makes \n indistinguishable from newlines)
        exec_on_canister(
            "with open('/test_import_mod_34.py', 'w') as f:\n"
            "    f.write('ANSWER = 42')\n",
            canister, network,
        )
        # Import it and use the exported symbol
        result = exec_on_canister(
            "import sys\n"
            "if 'test_import_mod_34' in sys.modules:\n"
            "    del sys.modules['test_import_mod_34']\n"
            "import test_import_mod_34\n"
            "print(test_import_mod_34.ANSWER)\n",
            canister, network,
        )
        assert result == "42", f"Expected '42', got: {result!r}"
        # Cleanup
        exec_on_canister(
            "import os\nos.remove('/test_import_mod_34.py')\n",
            canister, network,
        )
