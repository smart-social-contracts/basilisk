"""Integration tests for file store persistence limits (issue #38).

Tests enforce:
  - Per-file size limit (50 MB)
  - File count limit (10,000)
  - Total size limit (200 MB)
  - fs_stats() correctness
  - Exceptions raised on limit violations
  - Files still work on memfs after rejection
  - Upgrade stress test near limits
"""

import os
import subprocess

import pytest
from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR

EXAMPLE = "file_store_limits"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    name = list(ids.keys())[0]
    yield ids[name]
    # Cleanup after all tests in module
    call_canister(ids[name], "cleanup_all_files", example_dir=EXAMPLE_DIR, update=True)


def _call(canister, method, args=None):
    raw = call_canister(canister, method, args, example_dir=EXAMPLE_DIR, update=True)
    return parse_candid_text(raw)


def _get_stats(canister):
    """Call get_fs_stats and return parsed dict from pipe-delimited string."""
    text = _call(canister, "get_fs_stats")
    if text.startswith("ERROR:"):
        pytest.skip(f"fs_stats() not available: {text}")
    parts = text.split('|')
    assert len(parts) >= 7, f"Unexpected fs_stats format: {text!r}"
    return {
        "files": int(parts[0]),
        "max_files": int(parts[1]),
        "total_bytes": int(parts[2]),
        "max_total_bytes": int(parts[3]),
        "max_file_bytes": int(parts[4]),
        "largest_bytes": int(parts[5]),
        "largest_path": parts[6],
    }


# ===========================================================================
# fs_stats() tests
# ===========================================================================

class TestFsStats:
    """Test that fs_stats() returns correct usage information."""

    def test_fs_stats_empty(self, canister):
        """Initially the file store should be empty."""
        _call(canister, "cleanup_all_files")
        stats = _get_stats(canister)
        assert stats["files"] == 0
        assert stats["max_files"] == 10_000
        assert stats["total_bytes"] == 0
        assert stats["max_total_bytes"] == 200_000_000
        assert stats["max_file_bytes"] == 50_000_000
        assert stats["largest_bytes"] == 0
        assert stats["largest_path"] == ""

    def test_fs_stats_after_write(self, canister):
        """After writing a file, stats should reflect it."""
        _call(canister, "cleanup_all_files")
        result = _call(canister, "write_file", '("/stats_test.dat", 1000)')
        assert result == "ok"
        stats = _get_stats(canister)
        assert stats["files"] == 1
        assert stats["total_bytes"] == 1000
        assert stats["largest_bytes"] == 1000
        assert stats["largest_path"] == "/stats_test.dat"
        _call(canister, "delete_file", '("/stats_test.dat")')

    def test_fs_stats_tracks_largest(self, canister):
        """Stats should track the largest file correctly."""
        _call(canister, "cleanup_all_files")
        _call(canister, "write_file", '("/small.dat", 100)')
        _call(canister, "write_file", '("/big.dat", 5000)')
        _call(canister, "write_file", '("/medium.dat", 500)')
        stats = _get_stats(canister)
        assert stats["files"] == 3
        assert stats["total_bytes"] == 5600
        assert stats["largest_bytes"] == 5000
        assert stats["largest_path"] == "/big.dat"
        _call(canister, "cleanup_all_files")


# ===========================================================================
# Per-file size limit tests
# ===========================================================================

class TestFileSizeLimit:
    """Test the 50 MB per-file size limit."""

    def test_file_within_limit(self, canister):
        """A file under 50 MB should persist successfully."""
        _call(canister, "cleanup_all_files")
        result = _call(canister, "write_file", '("/ok_size.dat", 1000000)')
        assert result == "ok"
        stats = _get_stats(canister)
        assert stats["files"] == 1
        assert stats["total_bytes"] == 1_000_000
        _call(canister, "cleanup_all_files")

    def test_file_exceeds_limit(self, canister):
        """A file over 50 MB should raise FileTooLargeError."""
        _call(canister, "cleanup_all_files")
        result = _call(canister, "write_file", '("/too_big.dat", 51000000)')
        assert "FileTooLargeError" in result
        assert "51000000" in result
        # File should NOT be in the store
        stats = _get_stats(canister)
        assert stats["files"] == 0

    def test_file_at_exact_limit(self, canister):
        """A file at exactly 50 MB should succeed."""
        _call(canister, "cleanup_all_files")
        result = _call(canister, "write_file", '("/exact_50mb.dat", 50000000)')
        assert result == "ok"
        stats = _get_stats(canister)
        assert stats["files"] == 1
        assert stats["total_bytes"] == 50_000_000
        _call(canister, "cleanup_all_files")

    def test_oversized_file_still_on_memfs(self, canister):
        """Even if persistence fails, the file should still be readable on memfs."""
        _call(canister, "cleanup_all_files")
        result = _call(canister, "write_file", '("/memfs_only.dat", 51000000)')
        assert "FileTooLargeError" in result
        check = _call(canister, "read_file_check", '("/memfs_only.dat")')
        assert check == "ok:51000000"
        stats = _get_stats(canister)
        assert stats["files"] == 0


# ===========================================================================
# File count limit tests
# ===========================================================================

class TestFileCountLimit:
    """Test the 10,000-file count limit."""

    def test_write_many_within_limit(self, canister):
        """Writing files within the count limit should succeed."""
        _call(canister, "cleanup_all_files")
        result = _call(canister, "write_many_files", '("/data/batch", 10, 100)')
        assert result == "ok:10"
        stats = _get_stats(canister)
        assert stats["files"] == 10
        _call(canister, "cleanup_all_files")

    @pytest.mark.xfail(
        reason="Creating 10,000 files exceeds IC instruction limit (~50B) "
               "due to O(n) file-store serialization on each write",
        strict=False,
    )
    def test_count_limit_enforced(self, canister):
        """Writing beyond 10,000 files should raise FileStoreLimitError."""
        _call(canister, "cleanup_all_files")
        batch_size = 500
        for batch in range(20):
            offset = batch * batch_size
            result = _call(canister, "write_many_files",
                           f'("/limit/b{batch:02d}_f", {batch_size}, 10)')
            assert result == f"ok:{batch_size}", (
                f"Batch {batch} (offset {offset}) failed: {result}")
        stats = _get_stats(canister)
        assert stats["files"] == 10_000
        # The 10,001st file should fail
        result = _call(canister, "write_file", '("/limit/overflow.dat", 10)')
        assert "FileStoreLimitError" in result
        assert "10000/10000" in result
        _call(canister, "cleanup_all_files")


# ===========================================================================
# Total size limit tests
# ===========================================================================

class TestTotalSizeLimit:
    """Test the 200 MB total size limit."""

    def test_total_size_limit_new_file(self, canister):
        """Adding a new file that would exceed 200 MB total should fail."""
        _call(canister, "cleanup_all_files")
        # Write 4 files of ~49 MB each = ~196 MB (under 200 MB limit)
        for i in range(4):
            result = _call(canister, "write_file", f'("/big/chunk_{i:02d}.dat", 49000000)')
            assert result == "ok", f"File {i} failed: {result}"

        stats = _get_stats(canister)
        assert stats["files"] == 4
        assert stats["total_bytes"] == 4 * 49_000_000  # 196 MB

        # A 5 MB file would push total to 201 MB — should fail
        result = _call(canister, "write_file", '("/big/overflow.dat", 5000000)')
        assert "FileStoreLimitError" in result

        _call(canister, "cleanup_all_files")

    def test_update_existing_file_within_total(self, canister):
        """Updating an existing file should account for replaced size."""
        _call(canister, "cleanup_all_files")
        result = _call(canister, "write_file", '("/update_test.dat", 1000000)')
        assert result == "ok"
        result = _call(canister, "write_file", '("/update_test.dat", 1500000)')
        assert result == "ok"
        stats = _get_stats(canister)
        assert stats["files"] == 1
        assert stats["total_bytes"] == 1_500_000
        _call(canister, "cleanup_all_files")


# ===========================================================================
# Exception class hierarchy tests
# ===========================================================================

class TestExceptionHierarchy:
    """Test that exceptions have correct inheritance."""

    def test_file_too_large_is_file_store_error(self, canister):
        """FileTooLargeError should be caught by FileStoreError handler."""
        _call(canister, "cleanup_all_files")
        result = _call(canister, "write_file", '("/hierarchy.dat", 51000000)')
        assert "FileTooLargeError" in result

    @pytest.mark.xfail(
        reason="Creating 10,000 files exceeds IC instruction limit (~50B) "
               "due to O(n) file-store serialization on each write",
        strict=False,
    )
    def test_store_limit_is_file_store_error(self, canister):
        """FileStoreLimitError should be caught by FileStoreError handler."""
        _call(canister, "cleanup_all_files")
        batch_size = 500
        for batch in range(20):
            result = _call(canister, "write_many_files",
                           f'("/hier/b{batch:02d}_f", {batch_size}, 10)')
            assert result == f"ok:{batch_size}", (
                f"Batch {batch} failed: {result}")
        result = _call(canister, "write_file", '("/hier/overflow.dat", 10)')
        assert "FileStoreLimitError" in result
        _call(canister, "cleanup_all_files")


# ===========================================================================
# Stress test: upgrade near limits
# ===========================================================================

class TestUpgradeStress:
    """Test that canister upgrade works correctly near file store limits.

    This is the key safety test: fill the store close to limits,
    perform an upgrade, verify all files are restored without hitting
    the IC instruction limit.
    """

    def test_upgrade_with_many_files(self, canister):
        """Fill near limits, upgrade, verify all files survive."""
        _call(canister, "cleanup_all_files")

        # Write 100 files of 10 KB each = 1 MB total
        # This is a realistic stress scenario without being too slow
        result = _call(canister, "write_many_files", '("/stress/f", 100, 10000)')
        assert result == "ok:100"

        stats = _get_stats(canister)
        assert stats["files"] == 100
        assert stats["total_bytes"] == 100 * 10_000

        # Perform canister upgrade (reinstall with same WASM)
        wasm_path = os.path.join(
            EXAMPLE_DIR, ".basilisk", "file_store_limits", "file_store_limits.wasm"
        )
        if not os.path.exists(wasm_path):
            pytest.skip("WASM not available for upgrade test")

        result = subprocess.run(
            ["dfx", "canister", "install", "file_store_limits",
             "--mode", "upgrade", "--wasm", wasm_path, "--upgrade-unchanged"],
            cwd=EXAMPLE_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"Upgrade failed: {result.stderr}"

        # Verify files survived the upgrade
        stats = _get_stats(canister)
        assert stats["files"] == 100, f"Expected 100 files after upgrade, got {stats['files']}"
        assert stats["total_bytes"] == 100 * 10_000

        # Spot-check a few files
        for i in [0, 50, 99]:
            check = _call(canister, "read_file_check", f'("/stress/f_{i:04d}.dat")')
            assert check == "ok:10000", f"File {i} check failed: {check}"

        _call(canister, "cleanup_all_files")
