"""
Basilisk CLI — scaffold, build, and interact with IC canister projects in Python.

Usage:
    basilisk new [--backend cpython|rustpython] <project_name>
    basilisk build                 Build the canister in the current directory
    basilisk exec [options] <code> Execute Python code on a deployed canister
    basilisk shell [options]       Interactive shell for a deployed canister
    basilisk sshd [options]        SSH server proxy to a deployed canister
    basilisk --version             Print version

Exec options:
    --canister <name_or_id>   Canister name or ID (default: auto-detect from dfx.json)
    --network <network>       Network: local, ic, or URL (default: local)
    -f <file>                 Execute a local Python file on the canister
"""

import ast
import os
import re
import subprocess
import sys
from pathlib import Path


def cmd_new(project_name: str, backend: str = "cpython"):
    """Scaffold a new basilisk canister project."""
    project_dir = Path(project_name)

    if project_dir.exists():
        print(f"Error: directory '{project_name}' already exists.", file=sys.stderr)
        sys.exit(1)

    # Validate project name (must be a valid canister name)
    if not project_name.replace("_", "").replace("-", "").isalnum():
        print(f"Error: '{project_name}' is not a valid project name. Use alphanumeric, dashes, and underscores.", file=sys.stderr)
        sys.exit(1)

    if backend not in ("cpython", "rustpython"):
        print(f"Error: unknown backend '{backend}'. Use 'cpython' or 'rustpython'.", file=sys.stderr)
        sys.exit(1)

    print(f"Creating new basilisk project: {project_name} (backend: {backend})")

    # Create directory structure
    src_dir = project_dir / "src"
    src_dir.mkdir(parents=True)

    # Build command depends on backend
    if backend == "rustpython":
        build_cmd = f"BASILISK_PYTHON_BACKEND=rustpython CANISTER_CANDID_PATH=./{project_name}.did python -m basilisk {project_name} src/main.py"
    else:
        build_cmd = f"CANISTER_CANDID_PATH=./{project_name}.did python -m basilisk {project_name} src/main.py"

    dfx_json = f"""\
{{
    "canisters": {{
        "{project_name}": {{
            "type": "custom",
            "build": "{build_cmd}",
            "candid": "{project_name}.did",
            "wasm": ".basilisk/{project_name}/{project_name}.wasm"
        }}
    }}
}}
"""
    (project_dir / "dfx.json").write_text(dfx_json)

    # src/main.py
    main_py = """\
from basilisk import query, update, text, nat64, ic

# A simple counter stored in a global variable.
# State persists across calls but resets on canister upgrade.
counter = 0

@query
def greet(name: text) -> text:
    \"\"\"Return a greeting message.\"\"\"
    return f"Hello, {name}! The counter is at {counter}."

@query
def get_counter() -> nat64:
    \"\"\"Read the current counter value.\"\"\"
    return counter

@update
def increment() -> nat64:
    \"\"\"Increment the counter and return the new value.\"\"\"
    global counter
    counter += 1
    return counter

@query
def get_time() -> nat64:
    \"\"\"Return the current IC timestamp in nanoseconds.\"\"\"
    return ic.time()

@query
def whoami() -> text:
    \"\"\"Return the caller's principal ID.\"\"\"
    return str(ic.caller())
"""
    (src_dir / "main.py").write_text(main_py)

    # .gitignore
    gitignore = """\
.dfx/
.basilisk/
node_modules/
"""
    (project_dir / ".gitignore").write_text(gitignore)

    build_note = "⚡ fast template build" if backend == "cpython" else "🔨 full Rust build (~5-10 min first time)"
    print(f"""
Done! Created {project_name}/ ({build_note})
  src/main.py    — your canister code (query + update examples)
  dfx.json       — IC project config (backend: {backend})

Next steps:
  cd {project_name}
  dfx start --background
  dfx deploy
  dfx canister call {project_name} greet '("World")'
  dfx canister call {project_name} increment
  dfx canister call {project_name} get_counter
""")


def cmd_build():
    """Build the canister in the current directory."""
    # Find dfx.json
    if not Path("dfx.json").exists():
        print("Error: no dfx.json found. Run this from a basilisk project directory.", file=sys.stderr)
        sys.exit(1)

    import json
    with open("dfx.json") as f:
        dfx = json.load(f)

    canisters = dfx.get("canisters", {})
    if not canisters:
        print("Error: no canisters defined in dfx.json.", file=sys.stderr)
        sys.exit(1)

    # Build each canister
    for name, config in canisters.items():
        build_cmd = config.get("build", "")
        if "basilisk" in build_cmd:
            print(f"Building canister: {name}")
            # Extract entry point from build command
            parts = build_cmd.split()
            # Expected: python -m basilisk <name> <entry_point>
            if len(parts) >= 5:
                entry_point = parts[4]
            else:
                entry_point = "src/main.py"

            candid_path = config.get("candid", f"{name}.did")
            os.environ["CANISTER_CANDID_PATH"] = f"./{candid_path}"

            # Run the basilisk build
            import subprocess
            result = subprocess.run(
                [sys.executable, "-m", "basilisk", name, entry_point],
                env={**os.environ},
            )
            if result.returncode != 0:
                print(f"Error: build failed for canister '{name}'.", file=sys.stderr)
                sys.exit(1)


def _parse_candid_string(output: str) -> str:
    """Parse a Candid-encoded string response from dfx into plain text."""
    output = output.strip()
    # General tuple pattern: (  "content"  ) or (  "content",  )
    m = re.search(r'\(\s*"(.*)"\s*,?\s*\)', output, re.DOTALL)
    if m:
        try:
            return ast.literal_eval(f'"{m.group(1)}"')
        except (SyntaxError, ValueError):
            return m.group(1).replace("\\n", "\n").replace('\\"', '"')
    return output


def _detect_canister_from_dfx() -> str | None:
    """Try to find the first basilisk canister name from dfx.json."""
    import json
    if not Path("dfx.json").exists():
        return None
    try:
        with open("dfx.json") as f:
            dfx = json.load(f)
        for name, config in dfx.get("canisters", {}).items():
            if "basilisk" in config.get("build", ""):
                return name
    except Exception:
        pass
    return None


def cmd_exec(args: list[str]):
    """Execute Python code on a deployed basilisk canister."""
    canister = None
    network = None
    file_path = None
    code_parts = []

    i = 0
    while i < len(args):
        if args[i] == "--canister" and i + 1 < len(args):
            canister = args[i + 1]; i += 2
        elif args[i] == "--network" and i + 1 < len(args):
            network = args[i + 1]; i += 2
        elif args[i] == "-f" and i + 1 < len(args):
            file_path = args[i + 1]; i += 2
        else:
            code_parts.append(args[i]); i += 1

    # Get code from file or args
    if file_path:
        try:
            code = Path(file_path).read_text()
        except FileNotFoundError:
            print(f"Error: file not found: {file_path}", file=sys.stderr)
            sys.exit(1)
    elif code_parts:
        code = " ".join(code_parts)
    else:
        # Read from stdin
        code = sys.stdin.read()

    if not code.strip():
        print("Error: no code provided. Usage: basilisk exec [--canister <c>] [--network <n>] [-f <file>] <code>", file=sys.stderr)
        sys.exit(1)

    # Auto-detect canister if not specified
    if not canister:
        canister = _detect_canister_from_dfx()
        if not canister:
            print("Error: --canister required (could not auto-detect from dfx.json)", file=sys.stderr)
            sys.exit(1)

    # Build dfx command
    escaped_code = code.replace('"', '\\"').replace("\n", "\\n")
    cmd = ["dfx", "canister", "call"]
    if network:
        cmd.extend(["--network", network])
    cmd.extend([canister, "execute_code_shell", f'("{escaped_code}")'])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            print(result.stderr.strip(), file=sys.stderr)
            sys.exit(1)
        output = _parse_candid_string(result.stdout)
        if output:
            print(output, end="" if output.endswith("\n") else "\n")
    except subprocess.TimeoutExpired:
        print("Error: canister call timed out (120s)", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("Error: dfx not found. Install the DFINITY SDK.", file=sys.stderr)
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip())
        sys.exit(1)

    command = sys.argv[1]

    if command == "new":
        # Parse --backend flag
        args = sys.argv[2:]
        backend = "cpython"  # default
        if "--backend" in args:
            idx = args.index("--backend")
            if idx + 1 >= len(args):
                print("Error: --backend requires a value (cpython or rustpython)", file=sys.stderr)
                sys.exit(1)
            backend = args[idx + 1]
            args = args[:idx] + args[idx + 2:]

        if len(args) < 1:
            print("Usage: basilisk new [--backend cpython|rustpython] <project_name>", file=sys.stderr)
            sys.exit(1)
        cmd_new(args[0], backend)

    elif command == "build":
        cmd_build()

    elif command == "exec":
        cmd_exec(sys.argv[2:])

    elif command == "shell":
        from basilisk.shell import main as shell_main
        sys.argv = ["basilisk-shell"] + sys.argv[2:]
        shell_main()

    elif command == "sshd":
        from basilisk.sshd import main as sshd_main
        sys.argv = ["basilisk-sshd"] + sys.argv[2:]
        sshd_main()

    elif command in ("-h", "--help", "help"):
        print(__doc__.strip())

    elif command == "--version":
        from basilisk import __version__
        print(f"basilisk {__version__}")

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        print(__doc__.strip())
        sys.exit(1)


if __name__ == "__main__":
    main()
