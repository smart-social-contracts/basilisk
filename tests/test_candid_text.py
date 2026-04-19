"""Tests for _to_candid_text string escaping in the Basilisk Python shim.

Regression tests for GitHub issue where _to_candid_text produced invalid
Candid text for strings containing double-quotes (e.g. JSON payloads),
which caused candid_encode to trap and silently break timer-driven
async flows in deployed canisters.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _load_to_candid_text():
    """Load the _to_candid_text function from the Basilisk Python shim
    embedded in python_init.rs by exec'ing the shim's helper functions."""
    shim_path = os.path.join(
        os.path.dirname(__file__), "..",
        "basilisk", "compiler", "cpython_canister_template", "src",
        "python_init.rs",
    )
    with open(shim_path) as f:
        content = f.read()

    # Extract from _parse_record_fields through end of _to_candid_text
    start = content.find("def _parse_record_fields(")
    if start < 0:
        raise RuntimeError("Could not find _parse_record_fields in python_init.rs")
    end = content.find("\nclass _ServiceCall:", start)
    if end < 0:
        raise RuntimeError("Could not find _ServiceCall in python_init.rs")
    src = content[start:end]

    class _Opt:
        def __init__(self, value=None):
            self.value = value

    class Principal:
        def __init__(self, text=""):
            self._text = text
        def to_str(self):
            return self._text

    ns = {"_Opt": _Opt, "Principal": Principal}
    exec(src, ns)
    return ns["_to_candid_text"]


_to_candid_text = _load_to_candid_text()


class TestToCandidText(unittest.TestCase):

    def test_plain_string(self):
        result = _to_candid_text("hello world")
        self.assertEqual(result, '"hello world"')

    def test_string_with_double_quotes(self):
        """JSON strings must have inner quotes escaped for valid Candid text."""
        result = _to_candid_text('{"key":"value"}')
        inner = result[1:-1]
        unescaped = re.findall(r'(?<!\\)"', inner)
        self.assertEqual(
            len(unescaped), 0,
            f"Unescaped quotes in Candid text: {result!r}",
        )

    def test_json_payload_roundtrip(self):
        """A realistic JSON payload should produce valid Candid text."""
        payload = '{"registry_canister_id":"abc-123","ext_id":"welcome","version":null}'
        result = _to_candid_text(payload)
        self.assertTrue(result.startswith('"'))
        self.assertTrue(result.endswith('"'))
        inner = result[1:-1]
        unescaped = re.findall(r'(?<!\\)"', inner)
        self.assertEqual(
            len(unescaped), 0,
            f"Unescaped quotes in Candid text: {result!r}",
        )

    def test_string_with_backslash(self):
        result = _to_candid_text('path\\to\\file')
        self.assertIn("\\\\", result)

    def test_string_with_backslash_and_quotes(self):
        result = _to_candid_text('say "hello\\world"')
        inner = result[1:-1]
        unescaped = re.findall(r'(?<!\\)"', inner)
        self.assertEqual(len(unescaped), 0)

    def test_integer(self):
        result = _to_candid_text(42)
        self.assertIn("42", result)

    def test_none(self):
        result = _to_candid_text(None)
        self.assertEqual(result, "null")

    def test_bool(self):
        self.assertEqual(_to_candid_text(True), "true")
        self.assertEqual(_to_candid_text(False), "false")

    def test_empty_string(self):
        result = _to_candid_text("")
        self.assertEqual(result, '""')


if __name__ == "__main__":
    unittest.main()
