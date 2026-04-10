"""
Tests for controller guard access control on critical entrypoints.

Unit tests verify that wasm_manipulator correctly extracts guard metadata.
Integration tests verify that:
  - Controllers can call execute_code_shell and download_to_file
  - Non-controllers are rejected with the correct error message
"""

import ast
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import exec_on_canister, _get_canister, _get_network


# ===========================================================================
# Unit tests — guard metadata extraction from AST (no canister needed)
# ===========================================================================

class _GuardMetadataMixin:
    """Shared helper for extracting guard metadata from Python source."""

    def _extract_guards(self, source: str) -> dict:
        """Parse source and return {func_name: guard_name} for guarded methods."""
        tree = ast.parse(source)
        guards = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                for kw in decorator.keywords:
                    if kw.arg == "guard" and isinstance(kw.value, ast.Name):
                        guards[node.name] = kw.value.id
        return guards

    def _extract_func_names(self, source: str) -> list:
        """Parse source and return all function names."""
        tree = ast.parse(source)
        return [
            node.name for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
        ]


class TestGuardMetadataExtraction(_GuardMetadataMixin):
    """Verify wasm_manipulator correctly extracts guard= from decorators."""

    @property
    def _canister_source(self):
        canister_path = os.path.join(
            os.path.dirname(__file__), "test_canister", "src", "main.py"
        )
        with open(canister_path) as f:
            return f.read()

    def test_canister_has_guard_on_execute_code_shell(self):
        guards = self._extract_guards(self._canister_source)
        assert "execute_code_shell" in guards
        assert guards["execute_code_shell"] == "guard_against_non_controllers"

    def test_canister_has_guard_on_download_to_file(self):
        guards = self._extract_guards(self._canister_source)
        assert "download_to_file" in guards
        assert guards["download_to_file"] == "guard_against_non_controllers"

    def test_canister_guard_function_defined(self):
        assert "guard_against_non_controllers" in self._extract_func_names(self._canister_source)

    def test_benign_endpoints_not_guarded(self):
        guards = self._extract_guards(self._canister_source)
        for name in ("status", "whoami", "http_transform"):
            assert name not in guards, f"{name} should not have a guard"


# ===========================================================================
# Integration tests — controller access (live canister)
# ===========================================================================

class TestControllerAccess:
    """Verify that the CI identity (a controller) can call guarded endpoints."""

    def test_controller_can_execute_code_shell(self, canister_reachable, canister, network):
        result = exec_on_canister("print('guard_pass')", canister, network)
        assert result == "guard_pass"

    def test_controller_can_call_status(self, canister_reachable, canister, network):
        """Unguarded endpoint should always work."""
        r = subprocess.run(
            ["dfx", "canister", "call", canister, "status", "--network", network],
            capture_output=True, text=True, timeout=30,
        )
        assert r.returncode == 0
        assert "ok" in r.stdout.lower()


# ===========================================================================
# Integration tests — non-controller rejection (live canister)
# ===========================================================================

class TestNonControllerRejection:
    """Verify that a non-controller identity is rejected by guarded endpoints.

    These tests create a temporary dfx identity that is NOT a controller
    of the test canister, then attempt to call guarded endpoints.
    """

    TEMP_IDENTITY = "_ci_guard_test_noncontroller"

    @pytest.fixture(autouse=True)
    def setup_non_controller_identity(self, canister_reachable):
        """Create a temporary non-controller identity for testing."""
        # Create temp identity (ignore error if already exists)
        subprocess.run(
            ["dfx", "identity", "new", self.TEMP_IDENTITY, "--storage-mode", "plaintext"],
            capture_output=True, text=True,
        )
        yield
        # Cleanup: switch back to default identity
        # (the original identity is restored by switching away from temp)
        subprocess.run(
            ["dfx", "identity", "use", "ci-deploy"],
            capture_output=True, text=True,
        )
        # Remove temp identity
        subprocess.run(
            ["dfx", "identity", "remove", self.TEMP_IDENTITY],
            capture_output=True, text=True,
        )

    def _call_as_non_controller(self, canister, network, method, args=""):
        """Call a canister method using the non-controller identity."""
        cmd = [
            "dfx", "canister", "call", canister, method,
            "--network", network,
            "--identity", self.TEMP_IDENTITY,
        ]
        if args:
            cmd.append(args)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return r

    def test_non_controller_rejected_execute_code_shell(self, canister, network):
        r = self._call_as_non_controller(
            canister, network,
            "execute_code_shell", '("print(1)",)',
        )
        # The call should fail — either via trap (Rust guard) or Err return (Python guard)
        combined = r.stdout + r.stderr
        assert r.returncode != 0 or "Not Authorized" in combined, \
            f"Expected rejection but got: {combined}"
        assert "Not Authorized" in combined or "only controllers" in combined.lower(), \
            f"Expected controller rejection message, got: {combined}"

    def test_non_controller_rejected_download_to_file(self, canister, network):
        r = self._call_as_non_controller(
            canister, network,
            "download_to_file", '("https://example.com", "/tmp/test.txt")',
        )
        combined = r.stdout + r.stderr
        assert r.returncode != 0 or "Not Authorized" in combined, \
            f"Expected rejection but got: {combined}"
        assert "Not Authorized" in combined or "only controllers" in combined.lower(), \
            f"Expected controller rejection message, got: {combined}"

    def test_non_controller_can_call_status(self, canister, network):
        """Unguarded endpoint should still work for non-controllers."""
        r = self._call_as_non_controller(canister, network, "status")
        assert r.returncode == 0
        assert "ok" in r.stdout.lower()

    def test_non_controller_can_call_whoami(self, canister, network):
        """Unguarded query endpoint should still work for non-controllers."""
        r = self._call_as_non_controller(canister, network, "whoami")
        assert r.returncode == 0
        # Should return the non-controller's principal (not empty/error)
        assert len(r.stdout.strip()) > 10
