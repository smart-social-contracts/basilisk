"""
Integration tests for bosh shell — exec, Candid parsing, magic commands, modes.

Tests run against a live canister to verify end-to-end reliability.
"""

import os
import subprocess
import sys
import tempfile
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from basilisk.bosh import canister_exec, _parse_candid, _handle_magic
from tests.conftest import exec_on_canister, magic_on_canister


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
    """Test variable persistence in execute_code_shell.

    IMPORTANT FINDING: Variables do NOT persist across separate dfx canister
    calls. Each call gets a fresh execution context. This is a known Basilisk
    OS limitation — within one interactive bosh session the canister maintains
    state, but each `dfx canister call` is independent.
    """

    def test_variable_within_single_call(self, canister_reachable, canister, network):
        """Variables defined and used in the same call should work."""
        result = exec_on_canister(
            "boshtestvar = 42\nprint(boshtestvar)", canister, network
        )
        assert result == "42"

    def test_function_within_single_call(self, canister_reachable, canister, network):
        """Functions defined and called in the same execution work."""
        result = exec_on_canister(
            "def boshtestfn(x): return x * 2\nprint(boshtestfn(21))",
            canister, network,
        )
        assert result == "42"

    def test_import_within_single_call(self, canister_reachable, canister, network):
        """Imports used in the same call work."""
        result = exec_on_canister(
            "import json as boshtestjson\nprint(boshtestjson.dumps([1,2,3]))",
            canister, network,
        )
        assert result in ("[1, 2, 3]", "[1,2,3]")

    def test_variable_across_calls(self, canister_reachable, canister, network):
        """Variables set in one call should be visible in the next.
        Persistence depends on the canister's execute_code_shell implementation
        maintaining a per-principal namespace.
        """
        exec_on_canister("boshtestpersist = 42", canister, network)
        result = exec_on_canister("print(boshtestpersist)", canister, network)
        assert result == "42"


# ===========================================================================
# Magic commands
# ===========================================================================

class TestMagicCommands:
    """Test magic commands via _handle_magic."""

    def test_who(self, canister_reachable, canister, network):
        result = magic_on_canister("%who", canister, network)
        # Should return a list (even if empty)
        assert result.startswith("[")

    def test_info(self, canister_reachable, canister, network):
        result = magic_on_canister("%info", canister, network)
        assert "Canister" in result and "Principal" in result

    def test_db_count(self, canister_reachable, canister, network):
        result = magic_on_canister("%db count", canister, network)
        assert "entries" in result

    def test_ps(self, canister_reachable, canister, network):
        result = magic_on_canister("%ps", canister, network)
        # Either shows tasks, "No tasks.", or ImportError if ggg not available
        assert "|" in result or "No tasks" in result or "ImportError" in result

    def test_ls_root(self, canister_reachable, canister, network):
        """%ls should list the canister's root filesystem."""
        result = magic_on_canister("%ls", canister, network)
        assert result  # Should have some files from prior tests

    def test_ls_with_path(self, canister_reachable, canister, network):
        """%ls with a specific path should list that directory."""
        result = magic_on_canister("%ls /", canister, network)
        assert result

    def test_ls_nonexistent_dir(self, canister_reachable, canister, network):
        """%ls on a nonexistent path should report an error."""
        result = magic_on_canister("%ls /nonexistent_dir_xyz", canister, network)
        assert "No such file or directory" in result

    def test_cat_file(self, canister_reachable, canister, network):
        """%cat should display file contents."""
        # First write a file
        exec_on_canister(
            "with open('/_test_cat_magic', 'w') as f: f.write('cat-magic-test')",
            canister, network,
        )
        result = magic_on_canister("%cat /_test_cat_magic", canister, network)
        assert result == "cat-magic-test"

    def test_cat_nonexistent(self, canister_reachable, canister, network):
        """%cat on a nonexistent file should report an error."""
        result = magic_on_canister("%cat /nonexistent_file_xyz", canister, network)
        assert "No such file or directory" in result

    def test_cat_no_path_shows_usage(self, canister, network):
        """%cat without a file should show usage."""
        result = _handle_magic("%cat", canister, network)
        # %cat with no arg should not match the startswith check, returns None
        assert result is None or "Usage" in (result or "")

    def test_mkdir(self, canister_reachable, canister, network):
        """%mkdir should create a directory."""
        result = magic_on_canister("%mkdir /_test_mkdir_magic", canister, network)
        assert "Created" in result
        # Verify via %ls
        ls = magic_on_canister("%ls /", canister, network)
        assert "_test_mkdir_magic" in ls

    def test_mkdir_no_path_shows_usage(self, canister, network):
        """%mkdir without a path should show usage."""
        result = _handle_magic("%mkdir", canister, network)
        assert result is None or "Usage" in (result or "")

    def test_unknown_magic_returns_none(self, canister, network):
        """Unknown magic commands should return None (not executed)."""
        result = _handle_magic("%nonexistent_cmd", canister, network)
        assert result is None

    def test_run_nonexistent_file(self, canister, network):
        result = _handle_magic("%run /nonexistent/file.py", canister, network)
        assert "no such file" in result.lower()

    def test_run_file_on_canister(self, canister_reachable, canister, network):
        """%run should execute a file from the canister's memfs."""
        # Write a script to the canister
        exec_on_canister(
            "with open('_test_run_file.py', 'w') as f: f.write('print(7*6)')",
            canister, network,
        )
        result = magic_on_canister("%run _test_run_file.py", canister, network)
        assert result == "42"

    def test_run_no_path_returns_none(self, canister, network):
        """%run without a file is not recognized as a magic command (like %cat, %mkdir)."""
        result = _handle_magic("%run ", canister, network)
        assert result is None

    def test_get_file_from_canister(self, canister_reachable, canister, network):
        """%get should download a file from canister memfs to local filesystem."""
        tag = "get_test_abc123"
        # Write a known file on the canister
        exec_on_canister(
            f"with open('{tag}', 'w') as f: f.write('hello-from-canister')",
            canister, network,
        )
        local_path = os.path.join(tempfile.gettempdir(), tag)
        try:
            result = magic_on_canister(f"%get {tag} {local_path}", canister, network)
            assert "Downloaded" in result
            assert os.path.exists(local_path)
            with open(local_path) as f:
                assert f.read() == "hello-from-canister"
        finally:
            if os.path.exists(local_path):
                os.unlink(local_path)

    def test_get_nonexistent_file(self, canister_reachable, canister, network):
        """%get on a nonexistent canister file should report an error."""
        result = magic_on_canister("%get /nonexistent_xyz", canister, network)
        assert "no such file" in result.lower() or "error" in result.lower()

    def test_get_defaults_to_basename(self, canister_reachable, canister, network):
        """%get without a local path should use the remote file's basename."""
        tag = "_get_basename_test"
        exec_on_canister(
            f"with open('{tag}', 'w') as f: f.write('basename-test')",
            canister, network,
        )
        # Run from a temp directory so the default basename lands there
        orig_cwd = os.getcwd()
        tmpdir = tempfile.mkdtemp()
        try:
            os.chdir(tmpdir)
            result = magic_on_canister(f"%get {tag}", canister, network)
            assert "Downloaded" in result
            local_file = os.path.join(tmpdir, tag)
            assert os.path.exists(local_file)
            with open(local_file) as f:
                assert f.read() == "basename-test"
        finally:
            os.chdir(orig_cwd)
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_put_file_to_canister(self, canister_reachable, canister, network):
        """%put should upload a local file to the canister's memfs."""
        tag = "_put_test_abc123"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            f.write("hello-from-local")
            local_path = f.name
        try:
            result = magic_on_canister(
                f"%put {local_path} {tag}", canister, network
            )
            assert "Uploaded" in result
            # Verify the file is on the canister
            cat_result = magic_on_canister(f"%cat {tag}", canister, network)
            assert cat_result == "hello-from-local"
        finally:
            os.unlink(local_path)

    def test_put_nonexistent_local_file(self, canister, network):
        """%put with a nonexistent local file should report an error."""
        result = _handle_magic("%put /nonexistent/local.txt remote.txt", canister, network)
        assert "error" in result.lower()

    def test_put_defaults_to_basename(self, canister_reachable, canister, network):
        """%put without a remote path should use the local file's basename."""
        with tempfile.NamedTemporaryFile(
            mode="w", prefix="_put_bn_", suffix=".txt", delete=False
        ) as f:
            f.write("basename-put")
            local_path = f.name
            remote_name = os.path.basename(local_path)
        try:
            result = magic_on_canister(f"%put {local_path}", canister, network)
            assert "Uploaded" in result
            cat_result = magic_on_canister(f"%cat {remote_name}", canister, network)
            assert cat_result == "basename-put"
        finally:
            os.unlink(local_path)

    def test_put_get_binary_roundtrip(self, canister_reachable, canister, network):
        """%put and %get should handle binary data correctly."""
        tag = "_binrt_test"
        data = bytes(range(256))
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(data)
            local_up = f.name
        local_down = local_up + ".down"
        try:
            # Upload
            result = magic_on_canister(
                f"%put {local_up} {tag}", canister, network
            )
            assert "Uploaded" in result
            # Download
            result = magic_on_canister(
                f"%get {tag} {local_down}", canister, network
            )
            assert "Downloaded" in result
            with open(local_down, "rb") as f:
                assert f.read() == data
        finally:
            for p in [local_up, local_down]:
                if os.path.exists(p):
                    os.unlink(p)


# ===========================================================================
# One-shot mode (-c flag)
# ===========================================================================

class TestOneshotMode:
    """Test bosh invocation via subprocess (one-shot mode)."""

    def _run_bosh(self, code, canister, network):
        """Run bosh -c and return stdout."""
        cmd = [
            sys.executable, "-m", "basilisk.bosh",
            "--canister", canister,
            "--network", network,
            "-c", code,
        ]
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            cwd=os.path.join(os.path.dirname(__file__), ".."),
        )
        return r.stdout.strip(), r.stderr.strip(), r.returncode

    def test_oneshot_print(self, canister_reachable, canister, network):
        out, err, rc = self._run_bosh("print('bosh-oneshot')", canister, network)
        assert rc == 0
        assert out == "bosh-oneshot"

    def test_oneshot_magic(self, canister_reachable, canister, network):
        out, err, rc = self._run_bosh("%info", canister, network)
        assert rc == 0
        assert "Canister" in out

    def test_oneshot_ps(self, canister_reachable, canister, network):
        out, err, rc = self._run_bosh("%ps", canister, network)
        assert rc == 0
        assert "|" in out or "No tasks" in out or "ImportError" in out

    def test_oneshot_local_command(self, canister_reachable, canister, network):
        out, err, rc = self._run_bosh("!echo local-test", canister, network)
        assert rc == 0
        assert "local-test" in out


# ===========================================================================
# File mode
# ===========================================================================

class TestFileMode:
    """Test bosh with a script file argument."""

    def test_file_execution(self, canister_reachable, canister, network):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write("print('from-file')\n")
            f.flush()
            tmppath = f.name

        try:
            cmd = [
                sys.executable, "-m", "basilisk.bosh",
                "--canister", canister,
                "--network", network,
                tmppath,
            ]
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
                cwd=os.path.join(os.path.dirname(__file__), ".."),
            )
            assert r.returncode == 0
            assert "from-file" in r.stdout
        finally:
            os.unlink(tmppath)

    def test_file_not_found(self, canister, network):
        cmd = [
            sys.executable, "-m", "basilisk.bosh",
            "--canister", canister,
            "--network", network,
            "/nonexistent/script.py",
        ]
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
            cwd=os.path.join(os.path.dirname(__file__), ".."),
        )
        assert r.returncode != 0
        assert "No such file" in r.stderr


# ===========================================================================
# Pipe mode
# ===========================================================================

class TestPipeMode:
    """Test bosh reading from stdin pipe."""

    def test_pipe_execution(self, canister_reachable, canister, network):
        cmd = [
            sys.executable, "-m", "basilisk.bosh",
            "--canister", canister,
            "--network", network,
        ]
        r = subprocess.run(
            cmd,
            input="print('from-pipe')\n",
            capture_output=True, text=True, timeout=120,
            cwd=os.path.join(os.path.dirname(__file__), ".."),
        )
        assert r.returncode == 0
        assert "from-pipe" in r.stdout


# ===========================================================================
# Watch mode
# ===========================================================================

class TestWatchMode:
    """Test bosh --watch mode (file-based session)."""

    def test_watch_round_trip(self, canister_reachable, canister, network):
        inbox = tempfile.mktemp(suffix="_inbox")
        outbox = tempfile.mktemp(suffix="_outbox")

        cmd = [
            sys.executable, "-m", "basilisk.bosh",
            "--canister", canister,
            "--network", network,
            "--watch", inbox,
            "--outbox", outbox,
        ]

        # Start bosh in watch mode
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=os.path.join(os.path.dirname(__file__), ".."),
        )

        try:
            # Wait for initialization
            for _ in range(20):
                time.sleep(0.5)
                if os.path.exists(outbox):
                    with open(outbox) as f:
                        if "---READY---" in f.read():
                            break

            # Send a command
            with open(inbox, "w") as f:
                f.write("print('watch-test')\n")

            # Wait for response
            result = ""
            for _ in range(40):
                time.sleep(0.5)
                if os.path.exists(outbox):
                    with open(outbox) as f:
                        content = f.read()
                    if "---READY---" in content and "watch-test" in content:
                        result = content
                        break

            assert "watch-test" in result

            # Send quit
            with open(inbox, "w") as f:
                f.write(":q\n")
            proc.wait(timeout=10)

        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            for p in [inbox, outbox]:
                if os.path.exists(p):
                    os.unlink(p)


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
