"""Tests for the lazy modules that `_bundle_all_modules` generates.

Each test bundles a few small modules, appends an entry program and runs the
result in a fresh interpreter, because the bundle registers its modules in
`sys.modules`. The entry program asserts on what a canister program can see.
"""

import os
import subprocess
import sys
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from basilisk.build_wasm_binary_or_exit import _bundle_all_modules


def run_bundle(tmp_path, modules, entry):
    """Bundle `modules` ({relative path: source}) plus `entry` and run it."""
    src = tmp_path / "src"
    for relpath, source in {**modules, "main.py": entry}.items():
        path = src / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(source))
    bundle = tmp_path / "bundle.py"
    bundle.write_text(_bundle_all_modules(str(src), "main"))
    return subprocess.run(
        [sys.executable, str(bundle)], capture_output=True, text=True, cwd=tmp_path
    )


def assert_passes(result):
    assert result.returncode == 0, result.stderr


PLAIN = {"lazy_mod.py": "X = 1\ndef f():\n    return X\n"}


class TestLoadedModuleIsPlain:
    def test_lazy_until_first_use(self, tmp_path):
        assert_passes(run_bundle(tmp_path, PLAIN, """
            import sys
            assert type(sys.modules['lazy_mod']).__name__ == '_LazyMod'
            assert 'X' not in sys.modules['lazy_mod'].__dict__
        """))

    def test_plain_module_after_first_attribute_access(self, tmp_path):
        assert_passes(run_bundle(tmp_path, PLAIN, """
            import sys
            import lazy_mod
            assert lazy_mod.X == 1
            assert type(lazy_mod) is type(sys)
            assert '__getattr__' not in dir(type(lazy_mod))
        """))

    def test_plain_module_after_from_import(self, tmp_path):
        assert_passes(run_bundle(tmp_path, PLAIN, """
            import sys
            from lazy_mod import X, f
            assert (X, f()) == (1, 1)
            assert type(sys.modules['lazy_mod']) is type(sys)
        """))

    def test_reference_taken_before_load_sees_the_loaded_module(self, tmp_path):
        assert_passes(run_bundle(tmp_path, PLAIN, """
            import sys
            import lazy_mod as early
            assert type(early).__name__ == '_LazyMod'
            from lazy_mod import X
            assert early is sys.modules['lazy_mod']
            assert type(early) is type(sys)
            assert early.f.__globals__ is early.__dict__
        """))

    def test_package_is_plain_after_load(self, tmp_path):
        assert_passes(run_bundle(tmp_path, PACKAGE, """
            import sys
            import lazy_pkg
            assert lazy_pkg.VALUE == 'pkg'
            assert type(lazy_pkg) is type(sys)
            assert type(sys.modules['lazy_pkg.sub']).__name__ == '_LazyMod'
        """))

    def test_modules_that_import_each_other_are_plain_once_loaded(self, tmp_path):
        modules = {
            "lazy_a.py": "import lazy_b\nX = lazy_b.Y\n",
            "lazy_b.py": "Y = 1\n",
            "lazy_pkg/__init__.py": "from . import sibling\n",
            "lazy_pkg/sibling.py": "",
        }
        assert_passes(run_bundle(tmp_path, modules, """
            import sys
            import lazy_a, lazy_pkg
            assert lazy_a.X == 1
            assert lazy_pkg.sibling is sys.modules['lazy_pkg.sibling']
            for name in ('lazy_a', 'lazy_b', 'lazy_pkg'):
                assert type(sys.modules[name]) is type(sys), name
        """))

    def test_modules_never_used_stay_unloaded(self, tmp_path):
        modules = {**PLAIN, "lazy_unused.py": "import builtins\nbuiltins.UNUSED_RAN = True\n"}
        assert_passes(run_bundle(tmp_path, modules, """
            import builtins, sys
            import lazy_mod
            lazy_mod.X
            assert not hasattr(builtins, 'UNUSED_RAN')
            assert type(sys.modules['lazy_unused']).__name__ == '_LazyMod'
        """))


class TestMissingAttributes:
    def test_attribute_error_message(self, tmp_path):
        assert_passes(run_bundle(tmp_path, PLAIN, """
            import lazy_mod
            try:
                lazy_mod.nope
            except AttributeError as e:
                assert str(e) == "module 'lazy_mod' has no attribute 'nope'", str(e)
            else:
                raise AssertionError('no AttributeError')
            assert not hasattr(lazy_mod, 'nope')
            assert getattr(lazy_mod, 'nope', 7) == 7
        """))

    def test_attribute_error_when_first_lookup_misses(self, tmp_path):
        assert_passes(run_bundle(tmp_path, PLAIN, """
            import lazy_mod
            assert not hasattr(lazy_mod, 'nope')
            assert lazy_mod.X == 1
        """))

    def test_from_import_of_missing_name(self, tmp_path):
        assert_passes(run_bundle(tmp_path, PLAIN, """
            try:
                from lazy_mod import nope
            except ImportError as e:
                assert str(e) == "cannot import name 'nope' from 'lazy_mod' (unknown location)", str(e)
            else:
                raise AssertionError('no ImportError')
        """))

    def test_non_package_has_no_path(self, tmp_path):
        assert_passes(run_bundle(tmp_path, PLAIN, """
            import lazy_mod
            assert not hasattr(lazy_mod, '__path__')
        """))


PACKAGE = {
    "lazy_pkg/__init__.py": "VALUE = 'pkg'\nshadowed = 'attribute of the package'\n",
    "lazy_pkg/sibling.py": "NAME = 'sibling'\n",
    "lazy_pkg/shadowed.py": "NAME = 'a module the package attribute hides'\n",
    "lazy_pkg/sub/__init__.py": "",
    "lazy_pkg/sub/leaf.py": "NAME = 'leaf'\n",
}


class TestSubmodules:
    def test_import_submodule_then_use_it_through_the_parent(self, tmp_path):
        assert_passes(run_bundle(tmp_path, PACKAGE, """
            import sys
            import lazy_pkg.sibling
            assert lazy_pkg.VALUE == 'pkg'
            assert lazy_pkg.sibling is sys.modules['lazy_pkg.sibling']
            assert lazy_pkg.sibling.NAME == 'sibling'
        """))

    def test_nested_submodule(self, tmp_path):
        assert_passes(run_bundle(tmp_path, PACKAGE, """
            import sys
            import lazy_pkg.sub.leaf
            assert lazy_pkg.sub is sys.modules['lazy_pkg.sub']
            assert lazy_pkg.sub.leaf.NAME == 'leaf'
            assert 'leaf' not in lazy_pkg.__dict__
        """))

    def test_from_package_import_submodule(self, tmp_path):
        assert_passes(run_bundle(tmp_path, PACKAGE, """
            import sys
            from lazy_pkg import sibling, VALUE
            assert sibling is sys.modules['lazy_pkg.sibling']
            assert VALUE == 'pkg'
        """))

    def test_package_attribute_wins_over_a_submodule_of_the_same_name(self, tmp_path):
        assert_passes(run_bundle(tmp_path, PACKAGE, """
            import lazy_pkg
            from lazy_pkg import shadowed
            assert lazy_pkg.shadowed == shadowed == 'attribute of the package'
        """))

    def test_package_keeps_its_path(self, tmp_path):
        assert_passes(run_bundle(tmp_path, PACKAGE, """
            import lazy_pkg
            assert lazy_pkg.__path__ == ['lazy_pkg']
            assert lazy_pkg.__package__ == 'lazy_pkg'
        """))

    def test_package_importing_its_own_submodule_while_loading(self, tmp_path):
        modules = {
            "lazy_pkg/__init__.py": "from . import sibling\nSEEN = sibling.NAME\n",
            "lazy_pkg/sibling.py": "NAME = 'sibling'\n",
        }
        assert_passes(run_bundle(tmp_path, modules, """
            import sys
            import lazy_pkg
            assert lazy_pkg.SEEN == 'sibling'
            assert lazy_pkg.sibling is sys.modules['lazy_pkg.sibling']
        """))


class TestLoadInProgressAndFailure:
    def test_circular_import_sees_the_partly_loaded_module(self, tmp_path):
        modules = {
            "lazy_a.py": "X = 1\nimport lazy_b\nY = lazy_b.SEEN_X\n",
            "lazy_b.py": (
                "import lazy_a\n"
                "SEEN_X = lazy_a.X\n"
                "try:\n"
                "    lazy_a.Y\n"
                "except AttributeError:\n"
                "    Y_MISSING = True\n"
                "from lazy_a import X as FROM_X\n"
            ),
        }
        assert_passes(run_bundle(tmp_path, modules, """
            import lazy_a, lazy_b
            assert lazy_a.Y == 1
            assert lazy_b.Y_MISSING and lazy_b.FROM_X == 1
        """))

    def test_failed_load_reports_the_module_and_stays_lazy(self, tmp_path):
        modules = {"lazy_broken.py": "raise ValueError('boom')\n"}
        assert_passes(run_bundle(tmp_path, modules, """
            import sys
            for _ in range(2):
                try:
                    from lazy_broken import anything
                except ValueError as e:
                    assert 'boom' in str(e) and 'Module: lazy_broken' in str(e), str(e)
                else:
                    raise AssertionError('no ValueError')
            assert type(sys.modules['lazy_broken']).__name__ == '_LazyMod'
        """))
