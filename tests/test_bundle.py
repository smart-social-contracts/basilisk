"""Tests for build-time auto-bundling of pip-installed pure Python packages.

Tests the native extension detection, unresolved import warnings, and
bundle summary features added for GitHub issue #31.
"""

import io
import sys
import types
import unittest
from unittest.mock import patch

# Add basilisk source to path so we import the local version
sys.path.insert(0, "/home/user/dev/smartsocialcontracts/some-repos-2/basilisk")

from basilisk.__main__ import (
    _is_from_site_packages,
    _track_bundled_package,
    _check_native_extensions,
    _warn_unresolved_imports,
    _print_bundle_summary,
)


class _FakeModule:
    """Minimal stand-in for modulefinder.Module."""

    def __init__(self, name, file=None, path=None):
        self.__name__ = name
        self.__file__ = file
        self.__path__ = path


class _FakeFinder:
    """Minimal stand-in for modulefinder.ModuleFinder."""

    def __init__(self, modules=None, badmodules=None):
        self.modules = modules or {}
        self.badmodules = badmodules or {}


# ── _is_from_site_packages ──────────────────────────────────────────


class TestIsFromSitePackages(unittest.TestCase):
    def test_site_packages(self):
        self.assertTrue(
            _is_from_site_packages("/home/user/.local/lib/python3.10/site-packages/foo/__init__.py")
        )

    def test_dist_packages(self):
        self.assertTrue(
            _is_from_site_packages("/usr/lib/python3/dist-packages/bar.py")
        )

    def test_stdlib(self):
        self.assertFalse(
            _is_from_site_packages("/usr/lib/python3.10/json/__init__.py")
        )

    def test_lib_dynload(self):
        self.assertFalse(
            _is_from_site_packages("/usr/lib/python3.10/lib-dynload/_json.cpython-310-x86_64-linux-gnu.so")
        )

    def test_user_source(self):
        self.assertFalse(
            _is_from_site_packages("/home/user/myproject/src/main.py")
        )


# ── _track_bundled_package ──────────────────────────────────────────


class TestTrackBundledPackage(unittest.TestCase):
    def test_top_level(self):
        pkgs = {}
        _track_bundled_package(pkgs, "some_pkg")
        self.assertEqual(pkgs, {"some_pkg": 1})

    def test_submodule(self):
        pkgs = {}
        _track_bundled_package(pkgs, "some_pkg.fields")
        self.assertEqual(pkgs, {"some_pkg": 1})

    def test_accumulates(self):
        pkgs = {}
        _track_bundled_package(pkgs, "some_pkg")
        _track_bundled_package(pkgs, "some_pkg.fields")
        _track_bundled_package(pkgs, "some_pkg.entity")
        self.assertEqual(pkgs, {"some_pkg": 3})

    def test_multiple_packages(self):
        pkgs = {}
        _track_bundled_package(pkgs, "pkg_a")
        _track_bundled_package(pkgs, "pkg_b.handler")
        self.assertEqual(pkgs, {"pkg_a": 1, "pkg_b": 1})


# ── _check_native_extensions ────────────────────────────────────────


class TestCheckNativeExtensions(unittest.TestCase):
    def test_pure_python_passes(self):
        """Pure Python packages should pass without error."""
        finder = _FakeFinder(modules={
            "some_pkg": _FakeModule(
                "some_pkg",
                file="/home/user/.local/lib/python3.10/site-packages/some_pkg/__init__.py",
                path=["/home/user/.local/lib/python3.10/site-packages/some_pkg"],
            ),
        })
        # Should not raise or exit
        _check_native_extensions(finder)

    def test_stdlib_native_ignored(self):
        """Stdlib .so files (lib-dynload) should be silently ignored."""
        finder = _FakeFinder(modules={
            "_json": _FakeModule(
                "_json",
                file="/usr/lib/python3.10/lib-dynload/_json.cpython-310-x86_64-linux-gnu.so",
            ),
        })
        _check_native_extensions(finder)

    def test_pip_native_exits(self):
        """Pip packages with .so files should cause sys.exit(1)."""
        finder = _FakeFinder(modules={
            "numpy.core._multiarray_umath": _FakeModule(
                "numpy.core._multiarray_umath",
                file="/home/user/.local/lib/python3.10/site-packages/numpy/core/_multiarray_umath.cpython-310-x86_64-linux-gnu.so",
            ),
        })
        with self.assertRaises(SystemExit) as ctx:
            _check_native_extensions(finder)
        self.assertEqual(ctx.exception.code, 1)

    def test_error_message_includes_package_name(self):
        """Error output should name the offending package."""
        finder = _FakeFinder(modules={
            "numpy.core._multiarray_umath": _FakeModule(
                "numpy.core._multiarray_umath",
                file="/home/user/.local/lib/python3.10/site-packages/numpy/core/_multiarray_umath.cpython-310-x86_64-linux-gnu.so",
            ),
        })
        buf = io.StringIO()
        with patch("sys.stdout", buf), self.assertRaises(SystemExit):
            _check_native_extensions(finder)
        self.assertIn("numpy", buf.getvalue())
        self.assertIn("native code", buf.getvalue())

    def test_multiple_native_packages(self):
        """Multiple offending packages should all be listed."""
        finder = _FakeFinder(modules={
            "numpy.core._fast": _FakeModule(
                "numpy.core._fast",
                file="/usr/lib/python3/dist-packages/numpy/core/_fast.cpython-310-x86_64-linux-gnu.so",
            ),
            "cryptography.hazmat.bindings._rust": _FakeModule(
                "cryptography.hazmat.bindings._rust",
                file="/usr/lib/python3/dist-packages/cryptography/hazmat/bindings/_rust.abi3.so",
            ),
        })
        buf = io.StringIO()
        with patch("sys.stdout", buf), self.assertRaises(SystemExit):
            _check_native_extensions(finder)
        output = buf.getvalue()
        self.assertIn("numpy", output)
        self.assertIn("cryptography", output)


# ── _warn_unresolved_imports ────────────────────────────────────────


class TestWarnUnresolvedImports(unittest.TestCase):
    def test_no_bad_modules(self):
        """No warnings when badmodules is empty."""
        finder = _FakeFinder(badmodules={})
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            _warn_unresolved_imports(finder)
        self.assertEqual(buf.getvalue(), "")

    def test_private_modules_ignored(self):
        """Private C accelerator modules (starting with _) should be ignored."""
        finder = _FakeFinder(badmodules={
            "_pickle": {"json": 1},
            "_io": {"io": 1},
        })
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            _warn_unresolved_imports(finder)
        self.assertEqual(buf.getvalue(), "")

    def test_known_platform_modules_ignored(self):
        """Platform-specific modules like nt, winreg should be ignored."""
        finder = _FakeFinder(badmodules={
            "nt": {"os": 1},
            "msvcrt": {"subprocess": 1},
            "winreg": {"platform": 1},
        })
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            _warn_unresolved_imports(finder)
        self.assertEqual(buf.getvalue(), "")

    def test_real_unresolved_printed(self):
        """Genuinely missing packages should be warned about."""
        finder = _FakeFinder(badmodules={
            "requests": {"main": 1},
        })
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            _warn_unresolved_imports(finder)
        self.assertIn("requests", buf.getvalue())
        self.assertIn("unresolved", buf.getvalue())

    def test_max_10_shown(self):
        """Only first 10 unresolved imports should be listed, with a '... and N more' note."""
        bad = {f"pkg{i}": {"main": 1} for i in range(15)}
        finder = _FakeFinder(badmodules=bad)
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            _warn_unresolved_imports(finder)
        output = buf.getvalue()
        self.assertIn("15 unresolved", output)
        self.assertIn("... and 5 more", output)


# ── _print_bundle_summary ──────────────────────────────────────────


class TestPrintBundleSummary(unittest.TestCase):
    def test_empty_no_output(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            _print_bundle_summary({})
        self.assertEqual(buf.getvalue(), "")

    def test_single_package(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            _print_bundle_summary({"some_pkg": 5})
        output = buf.getvalue()
        self.assertIn("1 pip package", output)
        self.assertIn("some_pkg", output)
        self.assertIn("5 modules", output)

    def test_multiple_packages_sorted(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            _print_bundle_summary({"zz_pkg": 2, "aa_pkg": 1})
        output = buf.getvalue()
        # aa_pkg should appear before zz_pkg
        self.assertLess(output.index("aa_pkg"), output.index("zz_pkg"))

    def test_singular_module(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            _print_bundle_summary({"foo": 1})
        self.assertIn("1 module", buf.getvalue())
        self.assertNotIn("1 modules", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
