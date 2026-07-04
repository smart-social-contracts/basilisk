"""Unit tests for basilisk/compiler/cpython/apply_patches.sh.

The IC patches applied to the CPython source tree are load-bearing
(frozen encodings are required for subinterpreter spawning; the instruction
metering patch is a security control). These tests pin the contract that a
patch which fails to apply FAILS THE BUILD instead of being silently skipped
(the pre-fix behavior was `git apply ... || true`).

Pure-Python + git, no WASM or canister needed.
"""

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
APPLY_SCRIPT = REPO_ROOT / "basilisk" / "compiler" / "cpython" / "apply_patches.sh"


def _run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


@pytest.fixture()
def fake_cpython_repo(tmp_path):
    """A tiny git repo standing in for the CPython source tree."""
    repo = tmp_path / "cpython"
    repo.mkdir()
    _run(["git", "init", "-q"], cwd=repo)
    _run(["git", "config", "user.email", "test@test"], cwd=repo)
    _run(["git", "config", "user.name", "test"], cwd=repo)
    (repo / "Python").mkdir()
    (repo / "Python" / "example.c").write_text("int the_answer(void) { return 42; }\n")
    _run(["git", "add", "-A"], cwd=repo)
    _run(["git", "commit", "-q", "-m", "init"], cwd=repo)
    return repo


@pytest.fixture()
def patches_dir(tmp_path):
    d = tmp_path / "patches"
    d.mkdir()
    return d


GOOD_PATCH = """\
--- a/Python/example.c
+++ b/Python/example.c
@@ -1 +1,2 @@
+/* patched for IC */
 int the_answer(void) { return 42; }
"""

# Context line does not match the actual file content -> can never apply.
BROKEN_PATCH = """\
--- a/Python/example.c
+++ b/Python/example.c
@@ -1 +1,2 @@
+/* patched for IC */
 int something_else_entirely(void) { return 0; }
"""


def test_good_patch_applies(fake_cpython_repo, patches_dir):
    (patches_dir / "0001-good.patch").write_text(GOOD_PATCH)
    result = _run(["bash", str(APPLY_SCRIPT), str(fake_cpython_repo), str(patches_dir)])
    assert result.returncode == 0, result.stderr
    content = (fake_cpython_repo / "Python" / "example.c").read_text()
    assert "/* patched for IC */" in content


def test_reapply_is_idempotent(fake_cpython_repo, patches_dir):
    (patches_dir / "0001-good.patch").write_text(GOOD_PATCH)
    first = _run(["bash", str(APPLY_SCRIPT), str(fake_cpython_repo), str(patches_dir)])
    assert first.returncode == 0, first.stderr
    second = _run(["bash", str(APPLY_SCRIPT), str(fake_cpython_repo), str(patches_dir)])
    assert second.returncode == 0, second.stderr
    assert "already applied" in second.stdout


def test_broken_patch_fails_loudly(fake_cpython_repo, patches_dir):
    """The core Step-0 requirement: a patch that cannot apply must fail the build."""
    (patches_dir / "0001-broken.patch").write_text(BROKEN_PATCH)
    result = _run(["bash", str(APPLY_SCRIPT), str(fake_cpython_repo), str(patches_dir)])
    assert result.returncode != 0
    assert "FAILED to apply" in result.stderr


def test_one_broken_among_good_fails(fake_cpython_repo, patches_dir):
    (patches_dir / "0001-good.patch").write_text(GOOD_PATCH)
    (patches_dir / "0002-broken.patch").write_text(BROKEN_PATCH)
    result = _run(["bash", str(APPLY_SCRIPT), str(fake_cpython_repo), str(patches_dir)])
    assert result.returncode != 0
    assert "FAILED to apply" in result.stderr


def test_garbage_patch_fails(fake_cpython_repo, patches_dir):
    (patches_dir / "0001-garbage.patch").write_text("this is not a patch at all\n")
    result = _run(["bash", str(APPLY_SCRIPT), str(fake_cpython_repo), str(patches_dir)])
    assert result.returncode != 0


def test_missing_cpython_dir_fails(patches_dir, tmp_path):
    result = _run(
        ["bash", str(APPLY_SCRIPT), str(tmp_path / "does-not-exist"), str(patches_dir)]
    )
    assert result.returncode != 0


def test_verify_exact_passes_on_clean_tree(fake_cpython_repo, patches_dir):
    (patches_dir / "0001-good.patch").write_text(GOOD_PATCH)
    result = _run(
        ["bash", str(APPLY_SCRIPT), str(fake_cpython_repo), str(patches_dir), "--verify-exact"]
    )
    assert result.returncode == 0, result.stderr
    assert "Zero drift" in result.stdout
    # Tree must be left in the fully-patched state.
    assert "/* patched for IC */" in (fake_cpython_repo / "Python" / "example.c").read_text()


def test_verify_exact_detects_unpatched_drift(fake_cpython_repo, patches_dir):
    """Modifications not captured by any repo patch must fail the build.

    This is the guard against the Step-0 finding: load-bearing edits living
    only in a cached source tree, with nothing in the repository.
    """
    (patches_dir / "0001-good.patch").write_text(GOOD_PATCH)
    # Simulate an uncommitted local-cache modification in a tracked file.
    rogue = fake_cpython_repo / "Python" / "rogue.c"
    rogue.write_text("int rogue(void) { return 1; }\n")
    _run(["git", "add", "Python/rogue.c"], cwd=fake_cpython_repo)
    _run(["git", "commit", "-q", "-m", "add rogue file"], cwd=fake_cpython_repo)
    rogue.write_text("int rogue(void) { return 2; } /* uncommitted local edit */\n")

    result = _run(
        ["bash", str(APPLY_SCRIPT), str(fake_cpython_repo), str(patches_dir), "--verify-exact"]
    )
    assert result.returncode != 0
    assert "DRIFT DETECTED" in result.stderr
    # The tree must still be usable (patches re-applied) even after the failure.
    assert "/* patched for IC */" in (fake_cpython_repo / "Python" / "example.c").read_text()


def test_verify_exact_ignores_untracked_build_dirs(fake_cpython_repo, patches_dir):
    (patches_dir / "0001-good.patch").write_text(GOOD_PATCH)
    build_dir = fake_cpython_repo / "build-host"
    build_dir.mkdir()
    (build_dir / "artifact.o").write_text("binary stuff")
    result = _run(
        ["bash", str(APPLY_SCRIPT), str(fake_cpython_repo), str(patches_dir), "--verify-exact"]
    )
    assert result.returncode == 0, result.stderr


def test_repo_patches_are_well_formed():
    """Every shipped patch must be non-empty and parse as a unified diff."""
    shipped = sorted((REPO_ROOT / "basilisk" / "compiler" / "cpython" / "patches").glob("*.patch"))
    assert shipped, "expected at least one shipped patch"
    for p in shipped:
        text = p.read_text()
        assert "--- a/" in text and "+++ b/" in text and "@@" in text, (
            f"{p.name} does not look like a valid unified diff"
        )
