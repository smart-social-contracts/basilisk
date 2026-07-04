"""Subinterpreter-safety tests for the PEP 489 stub-module conversions.

Delegates to tests/subinterp_harness/, which compiles the real
``src/cpython_config.c`` against a native libpython3.13.a built from the
same pinned+patched CPython 3.13.0 tree as the wasm artifact, and runs the
converted stubs inside subinterpreters created with the sandbox
``PyInterpreterConfig`` (own GIL, own obmalloc,
``check_multi_interp_extensions=1``).

The harness covers:
- import success for all six converted stubs in an isolated subinterpreter;
- the audit's flagged ``_thread`` risk: the real ``_threadmodule.o`` is
  deleted from the archive so importlib's early-init import of ``_thread``
  (in the main interpreter AND every subinterpreter) exercises the stub's
  ``PyType_FromSpec``-in-``Py_mod_exec`` path;
- per-interpreter isolation of ``posix.stat_result`` / ``_thread.LockType``;
- a single-phase negative control being REFUSED by the sandbox config;
- 100 spawn/teardown cycles.

Requires the host CPython build (``builddir/build/libpython3.13.a`` in the
Basilisk CPython cache); skipped when absent (e.g. plain CI runners).
"""

import os
import subprocess
from pathlib import Path

import pytest

HARNESS = Path(__file__).parent / "subinterp_harness" / "build_and_run.sh"
CPYTHON_DIR = Path(
    os.environ.get(
        "BASILISK_CPYTHON_SRC",
        Path.home() / ".cache" / "basilisk" / "cpython" / "cpython-3.13.0",
    )
)
HOST_LIBPYTHON = CPYTHON_DIR / "builddir" / "build" / "libpython3.13.a"


@pytest.mark.skipif(
    not HOST_LIBPYTHON.exists(),
    reason=f"host libpython3.13.a not found at {HOST_LIBPYTHON} "
    "(build the host CPython first)",
)
def test_stub_conversions_in_subinterpreters():
    result = subprocess.run(
        ["bash", str(HARNESS), str(CPYTHON_DIR)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, (
        f"harness failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "All subinterpreter harness tests passed" in result.stdout
    assert "FAIL" not in result.stdout
