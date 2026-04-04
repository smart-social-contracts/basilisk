"""
Integration and unit tests for %db shell commands.

Unit tests (TestDbCodeGeneration, TestHandleDbDispatch) run without a canister.

Integration tests (TestDbTypes, TestDbList, TestDbShow, TestDbSearch,
TestDbExportImport, TestDbDelete, TestDbCountDumpClear) run against
a live canister on IC mainnet via dfx.
"""

import base64
import json
import os
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from basilisk.shell import (
    _handle_db,
    _handle_magic,
    _db_types_code,
    _db_list_code,
    _db_show_code,
    _db_search_code,
    _db_export_code,
    _db_import_code,
    _db_delete_code,
    _DB_USAGE,
    canister_exec,
)
from tests.conftest import exec_on_canister, magic_on_canister


# ===========================================================================
# Pure unit tests — no canister needed
# ===========================================================================

class TestDbCodeGeneration:
    """Test that code generation functions produce valid Python strings."""

    def test_types_code_is_valid_python(self):
        code = _db_types_code()
        assert "from basilisk.db import Database" in code
        compile(code, "<test>", "exec")

    def test_list_code_is_valid_python(self):
        code = _db_list_code("User", 10)
        assert "'User'" in code
        assert "10" in code
        compile(code, "<test>", "exec")

    def test_list_code_default_limit(self):
        code = _db_list_code("Task")
        assert "20" in code

    def test_show_code_is_valid_python(self):
        code = _db_show_code("User", "1")
        assert "'User'" in code
        assert "'1'" in code
        compile(code, "<test>", "exec")

    def test_search_code_is_valid_python(self):
        code = _db_search_code("User", "name", "Alice")
        assert "'User'" in code
        assert "'name'" in code
        assert "'Alice'" in code
        compile(code, "<test>", "exec")

    def test_export_code_is_valid_python(self):
        code = _db_export_code("User")
        assert "__DB_EXPORT__" in code
        assert "'User'" in code
        compile(code, "<test>", "exec")

    def test_import_code_is_valid_python(self):
        payload = base64.b64encode(json.dumps([{"_type": "User", "_id": "1", "name": "Test"}]).encode()).decode()
        code = _db_import_code(payload)
        assert "Entity.deserialize" in code
        assert "_context.clear()" in code
        compile(code, "<test>", "exec")

    def test_delete_code_is_valid_python(self):
        code = _db_delete_code("User", "1")
        assert "'User'" in code
        assert "'1'" in code
        assert ".delete()" in code
        compile(code, "<test>", "exec")

    def test_escaping_single_quotes(self):
        """Ensure single quotes in type/id are properly escaped."""
        code = _db_show_code("O'Brien", "it's")
        assert "O\\'Brien" in code
        assert "it\\'s" in code
        compile(code, "<test>", "exec")


class TestHandleDbDispatch:
    """Test the _handle_db dispatcher routing (uses a dummy canister_exec)."""

    def test_help_no_args(self):
        result = _handle_db("", "dummy", "dummy")
        # empty args -> "help"
        assert "Usage:" in result
        assert "%db types" in result

    def test_help_explicit(self):
        result = _handle_db("help", "dummy", "dummy")
        assert "Usage:" in result

    def test_list_missing_type(self):
        result = _handle_db("list", "dummy", "dummy")
        assert "Usage:" in result

    def test_show_missing_id(self):
        result = _handle_db("show User", "dummy", "dummy")
        assert "Usage:" in result

    def test_show_missing_both(self):
        result = _handle_db("show", "dummy", "dummy")
        assert "Usage:" in result

    def test_search_missing_args(self):
        result = _handle_db("search", "dummy", "dummy")
        assert "Usage:" in result

    def test_search_missing_field(self):
        result = _handle_db("search User", "dummy", "dummy")
        assert "Usage:" in result

    def test_search_no_equals(self):
        result = _handle_db("search User name", "dummy", "dummy")
        assert "Usage:" in result

    def test_export_missing_type(self):
        result = _handle_db("export", "dummy", "dummy")
        assert "Usage:" in result

    def test_import_missing_file(self):
        result = _handle_db("import", "dummy", "dummy")
        assert "Usage:" in result

    def test_import_file_not_found(self):
        result = _handle_db("import /nonexistent/file.json", "dummy", "dummy")
        assert "[error] file not found" in result

    def test_import_invalid_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json{{{")
            f.flush()
            result = _handle_db(f"import {f.name}", "dummy", "dummy")
        os.unlink(f.name)
        assert "[error] invalid JSON" in result

    def test_delete_missing_args(self):
        result = _handle_db("delete", "dummy", "dummy")
        assert "Usage:" in result

    def test_delete_missing_id(self):
        result = _handle_db("delete User", "dummy", "dummy")
        assert "Usage:" in result

    def test_unknown_subcommand(self):
        result = _handle_db("foobar", "dummy", "dummy")
        assert "Unknown db command: foobar" in result
        assert "Usage:" in result

    def test_magic_dispatch_db(self):
        """Verify %db routes through _handle_magic."""
        result = _handle_magic("%db help", "dummy", "dummy")
        assert result is not None
        assert "Usage:" in result

    def test_magic_dispatch_db_bare(self):
        """Verify bare %db routes through _handle_magic."""
        result = _handle_magic("%db", "dummy", "dummy")
        assert result is not None
        assert "Usage:" in result


class TestDbUsageMessage:
    """Verify _DB_USAGE content."""

    def test_contains_all_subcommands(self):
        for subcmd in ["types", "list", "show", "search", "export", "import", "delete", "count", "dump", "clear"]:
            assert subcmd in _DB_USAGE, f"Missing subcommand: {subcmd}"


# ===========================================================================
# Integration tests — require a live canister
# ===========================================================================

@pytest.fixture(scope="module")
def _ensure_canister(canister_reachable):
    """Gate integration tests on canister availability."""
    return canister_reachable


class TestDbTypes:
    """Test %db types against the live test canister."""

    @pytest.mark.usefixtures("_ensure_canister")
    def test_types_returns_table(self):
        result = magic_on_canister("%db types")
        assert "Entity" in result
        assert "Count" in result
        # The test canister should have at least Task entity type
        assert "Task" in result or "Total:" in result

    @pytest.mark.usefixtures("_ensure_canister")
    def test_types_shows_total(self):
        result = magic_on_canister("%db types")
        assert "Total:" in result


class TestDbCount:
    """Test %db count against the live test canister."""

    @pytest.mark.usefixtures("_ensure_canister")
    def test_count_returns_number(self):
        result = magic_on_canister("%db count")
        assert "entries" in result
        # Should have at least some entries (system keys)
        parts = result.strip().split()
        assert parts[0].isdigit()


class TestDbList:
    """Test %db list against the live test canister."""

    @pytest.mark.usefixtures("_ensure_canister")
    def test_list_unknown_type(self):
        result = magic_on_canister("%db list NonExistentType")
        assert "Unknown entity type" in result

    @pytest.mark.usefixtures("_ensure_canister")
    def test_list_task_type(self):
        """List Task entities — may be empty but should not error."""
        result = magic_on_canister("%db list Task")
        # Either shows entities or "No Task entities found."
        assert "Task" in result or "#" in result or "total" in result

    @pytest.mark.usefixtures("_ensure_canister")
    def test_list_with_limit(self):
        result = magic_on_canister("%db list Task 5")
        # Should not error
        assert "Unknown" not in result or "Task" in result


class TestDbShow:
    """Test %db show against the live test canister."""

    @pytest.mark.usefixtures("_ensure_canister")
    def test_show_unknown_type(self):
        result = magic_on_canister("%db show NonExistentType 1")
        assert "Unknown entity type" in result

    @pytest.mark.usefixtures("_ensure_canister")
    def test_show_nonexistent_id(self):
        result = magic_on_canister("%db show Task 99999")
        assert "not found" in result


class TestDbSearch:
    """Test %db search against the live test canister."""

    @pytest.mark.usefixtures("_ensure_canister")
    def test_search_unknown_type(self):
        result = magic_on_canister("%db search NonExistentType name=test")
        assert "Unknown entity type" in result

    @pytest.mark.usefixtures("_ensure_canister")
    def test_search_no_match(self):
        result = magic_on_canister("%db search Task name=__nonexistent_xyz_12345__")
        assert "No Task entities matching" in result or "Found" in result


class TestDbCreateShowDeleteLifecycle:
    """
    End-to-end lifecycle: create an entity, show it, search it, export it,
    delete it. Uses Task entities since they're always available on the test canister.
    """

    @pytest.mark.usefixtures("_ensure_canister")
    def test_lifecycle_create_show_delete(self, canister, network):
        """Create a task, show it, then delete it."""
        # Create a task via direct code exec
        from basilisk.shell import _TASK_RESOLVE
        create_result = exec_on_canister(
            _TASK_RESOLVE +
            "_t = Task(name='db_test_entity_xyz')\n"
            "print(f'CREATED:{_t._id}')\n"
        )
        assert "CREATED:" in create_result
        task_id = create_result.strip().split("CREATED:")[1].strip()

        try:
            # Show it
            show_result = magic_on_canister(f"%db show Task {task_id}")
            assert '"_id"' in show_result
            assert "db_test_entity_xyz" in show_result

            # It should be valid JSON
            data = json.loads(show_result)
            assert data["_id"] == task_id
            assert data["name"] == "db_test_entity_xyz"

            # Search for it
            search_result = magic_on_canister("%db search Task name=db_test_entity_xyz")
            assert "Found" in search_result
            assert task_id in search_result

            # List should include it
            list_result = magic_on_canister("%db list Task")
            assert task_id in list_result or "db_test_entity_xyz" in list_result

        finally:
            # Cleanup: delete it
            delete_result = magic_on_canister(f"%db delete Task {task_id}")
            assert f"Deleted Task#{task_id}" in delete_result

        # Verify it's gone
        show_after = magic_on_canister(f"%db show Task {task_id}")
        assert "not found" in show_after


class TestDbExportImport:
    """Test %db export and %db import round-trip."""

    @pytest.mark.usefixtures("_ensure_canister")
    def test_export_unknown_type(self):
        result = magic_on_canister("%db export NonExistentType")
        assert "Unknown entity type" in result

    @pytest.mark.usefixtures("_ensure_canister")
    def test_export_to_stdout(self, canister, network):
        """Export Task entities to stdout (JSON array)."""
        # Create a task to export
        from basilisk.shell import _TASK_RESOLVE
        create_result = exec_on_canister(
            _TASK_RESOLVE +
            "_t = Task(name='export_test_xyz')\n"
            "print(f'CREATED:{_t._id}')\n"
        )
        task_id = create_result.strip().split("CREATED:")[1].strip()

        try:
            result = magic_on_canister("%db export Task")
            # Should be a JSON array
            data = json.loads(result)
            assert isinstance(data, list)
            # Should contain our entity
            names = [d.get("name") for d in data]
            assert "export_test_xyz" in names
        finally:
            magic_on_canister(f"%db delete Task {task_id}")

    @pytest.mark.usefixtures("_ensure_canister")
    def test_export_to_file(self, canister, network):
        """Export Task entities to a local file."""
        from basilisk.shell import _TASK_RESOLVE
        create_result = exec_on_canister(
            _TASK_RESOLVE +
            "_t = Task(name='export_file_test_xyz')\n"
            "print(f'CREATED:{_t._id}')\n"
        )
        task_id = create_result.strip().split("CREATED:")[1].strip()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            out_path = f.name

        try:
            result = magic_on_canister(f"%db export Task {out_path}")
            assert "Exported" in result
            assert out_path in result

            # Verify file contents
            with open(out_path) as f:
                data = json.load(f)
            assert isinstance(data, list)
            names = [d.get("name") for d in data]
            assert "export_file_test_xyz" in names
        finally:
            magic_on_canister(f"%db delete Task {task_id}")
            if os.path.exists(out_path):
                os.unlink(out_path)

    @pytest.mark.usefixtures("_ensure_canister")
    def test_export_import_roundtrip(self, canister, network):
        """Export, delete, re-import, verify entity is restored."""
        from basilisk.shell import _TASK_RESOLVE

        # Create entity
        create_result = exec_on_canister(
            _TASK_RESOLVE +
            "_t = Task(name='roundtrip_test_xyz')\n"
            "print(f'CREATED:{_t._id}')\n"
        )
        task_id = create_result.strip().split("CREATED:")[1].strip()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            out_path = f.name

        try:
            # Export to file
            export_result = magic_on_canister(f"%db export Task {out_path}")
            assert "Exported" in export_result

            # Delete the entity
            magic_on_canister(f"%db delete Task {task_id}")
            show_deleted = magic_on_canister(f"%db show Task {task_id}")
            assert "not found" in show_deleted

            # Re-import from file
            import_result = magic_on_canister(f"%db import {out_path}")
            assert "Imported" in import_result
            assert "failed" in import_result  # shows "(N failed)" even if 0

            # Verify entity is back
            show_restored = magic_on_canister(f"%db show Task {task_id}")
            assert "roundtrip_test_xyz" in show_restored
            data = json.loads(show_restored)
            assert data["name"] == "roundtrip_test_xyz"

        finally:
            # Final cleanup
            magic_on_canister(f"%db delete Task {task_id}")
            if os.path.exists(out_path):
                os.unlink(out_path)

    @pytest.mark.usefixtures("_ensure_canister")
    def test_import_invalid_type(self, canister, network):
        """Import with unknown entity type should fail gracefully."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([{"_type": "NonExistentTypeXYZ", "_id": "1", "foo": "bar"}], f)
            f.flush()
            import_path = f.name

        try:
            result = magic_on_canister(f"%db import {import_path}")
            assert "Imported" in result
            # Should report 1 failed
            assert "1 failed" in result or "ERROR:" in result
        finally:
            os.unlink(import_path)


class TestDbDump:
    """Test %db dump against the live test canister."""

    @pytest.mark.usefixtures("_ensure_canister")
    def test_dump_returns_json(self):
        result = magic_on_canister("%db dump")
        # Should be valid JSON (or at least start with { )
        assert result.strip().startswith("{")
        data = json.loads(result)
        assert isinstance(data, dict)


class TestDbOneShot:
    """Test %db commands via one-shot basilisk shell mode."""

    @pytest.fixture(scope="class")
    def _ensure(self, canister_reachable):
        return canister_reachable

    @pytest.mark.usefixtures("_ensure")
    def test_oneshot_db_types(self, canister, network):
        """Run %db types via one-shot mode."""
        cmd = [
            sys.executable, "-m", "basilisk.shell",
            "--canister", canister,
            "--network", network,
            "-c", "%db types",
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        assert r.returncode == 0
        assert "Entity" in r.stdout or "Total:" in r.stdout

    @pytest.mark.usefixtures("_ensure")
    def test_oneshot_db_count(self, canister, network):
        """Run %db count via one-shot mode."""
        cmd = [
            sys.executable, "-m", "basilisk.shell",
            "--canister", canister,
            "--network", network,
            "-c", "%db count",
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        assert r.returncode == 0
        assert "entries" in r.stdout

    @pytest.mark.usefixtures("_ensure")
    def test_oneshot_db_help(self, canister, network):
        """Run %db help via one-shot mode."""
        cmd = [
            sys.executable, "-m", "basilisk.shell",
            "--canister", canister,
            "--network", network,
            "-c", "%db help",
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        assert r.returncode == 0
        assert "Usage:" in r.stdout
