"""Unit tests for _generate_post_upgrade_wrapper code generation.

Tests verify the generated Python source for the post_upgrade wrapper that
runs ic-python-db's check_upgrade_compatibility() after the user's hook.
"""

import os
import sys
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from basilisk.build_wasm_binary_or_exit import _generate_post_upgrade_wrapper


class TestGeneratePostUpgradeWrapperNoUserFunction:
    """When no user post_upgrade function exists."""

    def test_returns_string(self):
        result = _generate_post_upgrade_wrapper(None)
        assert isinstance(result, str)

    def test_defines_wrapper_function(self):
        result = _generate_post_upgrade_wrapper(None)
        assert "def _basilisk_post_upgrade_wrapper():" in result

    def test_does_not_call_user_function(self):
        result = _generate_post_upgrade_wrapper(None)
        lines = [l.strip() for l in result.splitlines() if l.strip()]
        func_body_start = next(
            i for i, l in enumerate(lines)
            if l.startswith("def _basilisk_post_upgrade_wrapper")
        )
        first_body_line = lines[func_body_start + 1]
        assert first_body_line == "try:"

    def test_imports_database(self):
        result = _generate_post_upgrade_wrapper(None)
        assert "from ic_python_db import Database as _DB" in result

    def test_calls_check_upgrade_compatibility(self):
        result = _generate_post_upgrade_wrapper(None)
        assert "_db.check_upgrade_compatibility()" in result

    def test_catches_import_error(self):
        result = _generate_post_upgrade_wrapper(None)
        assert "except ImportError:" in result
        assert "pass" in result

    def test_traps_on_other_exception(self):
        result = _generate_post_upgrade_wrapper(None)
        assert "except Exception as _e:" in result
        assert '_basilisk_ic.trap(f"Upgrade rejected: {_e}")' in result

    def test_is_valid_python(self):
        result = _generate_post_upgrade_wrapper(None)
        compile(result, "<test>", "exec")


class TestGeneratePostUpgradeWrapperWithUserFunction:
    """When the user defines their own post_upgrade function."""

    def test_calls_user_function_first(self):
        result = _generate_post_upgrade_wrapper("my_post_upgrade")
        lines = [l.strip() for l in result.splitlines() if l.strip()]
        func_idx = next(
            i for i, l in enumerate(lines)
            if l.startswith("def _basilisk_post_upgrade_wrapper")
        )
        first_body_line = lines[func_idx + 1]
        assert first_body_line == "my_post_upgrade()"

    def test_still_runs_schema_check(self):
        result = _generate_post_upgrade_wrapper("my_post_upgrade")
        assert "_db.check_upgrade_compatibility()" in result

    def test_user_call_before_try_block(self):
        result = _generate_post_upgrade_wrapper("my_post_upgrade")
        user_call_pos = result.index("my_post_upgrade()")
        try_pos = result.index("try:")
        assert user_call_pos < try_pos

    def test_preserves_user_function_name(self):
        for name in ["on_upgrade", "handle_post_upgrade", "post_upgrade_hook"]:
            result = _generate_post_upgrade_wrapper(name)
            assert f"{name}()" in result

    def test_is_valid_python(self):
        result = _generate_post_upgrade_wrapper("my_post_upgrade")
        compile(result, "<test>", "exec")

    def test_wrapper_executes_without_ic_python_db(self):
        """The wrapper should silently pass when ic_python_db isn't installed."""
        source = _generate_post_upgrade_wrapper(None)

        class FakeIc:
            trapped = None
            def trap(self, msg):
                FakeIc.trapped = msg

        # Temporarily hide ic_python_db so the ImportError path is taken
        saved = sys.modules.get("ic_python_db")
        sys.modules["ic_python_db"] = None  # forces ImportError on import
        try:
            namespace = {"_basilisk_ic": FakeIc()}
            exec(source, namespace)
            namespace["_basilisk_post_upgrade_wrapper"]()
            assert FakeIc.trapped is None
        finally:
            if saved is not None:
                sys.modules["ic_python_db"] = saved
            else:
                sys.modules.pop("ic_python_db", None)
