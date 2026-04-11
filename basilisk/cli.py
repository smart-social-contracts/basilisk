"""
Basilisk — An Internet Computer's Python Canister Development Kit.

Usage: basilisk <command> [options]

Commands:
  new <name>       Scaffold a new canister project
  build            Build the canister(s) in the current directory

Other:
  --version        Print version info
  help, -h         Show this help

Run basilisk <command> --help for command-specific options and examples.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

_TOOLKIT_COMMANDS = {"shell", "exec", "sshd"}

_HELP_TOOLKIT = """
Toolkit commands (provided by ic-basilisk-toolkit):
  shell            Interactive Python shell on a deployed canister
  exec <code>      Execute Python code on a deployed canister
  sshd             Start an SSH/SFTP server proxy to a canister
"""


def _toolkit_available() -> bool:
    """Check if ic-basilisk-toolkit is installed."""
    try:
        import ic_basilisk_toolkit.cli  # noqa: F401
        return True
    except ImportError:
        return False


def _help_text() -> str:
    """Return help text, including toolkit commands if available."""
    base = __doc__.strip()
    if _toolkit_available():
        # Insert toolkit commands before the "Other:" section
        lines = base.split("\n")
        result = []
        for line in lines:
            if line.startswith("Other:"):
                result.append(_HELP_TOOLKIT.strip())
                result.append("")
            result.append(line)
        return "\n".join(result)
    return base


_HELP_NEW = """\
basilisk new — Scaffold a new canister project.

Usage: basilisk new [--backend cpython|rustpython] <project_name>

Options:
  --backend <be>   Python backend: cpython or rustpython  [default: cpython]
                   (rustpython is deprecated and will be removed in a future release)

Examples:
  basilisk new my_app
  cd my_app && dfx start --background && dfx deploy
"""

_HELP_BUILD = """\
basilisk build — Build the canister(s) in the current directory.

Usage: basilisk build

Reads dfx.json in the current directory and builds every canister whose
build command references basilisk.

Examples:
  basilisk build
  basilisk build && dfx deploy
"""


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

    if backend == "rustpython":
        print("Warning: rustpython is deprecated and will be removed in a future release. Use cpython instead.", file=sys.stderr)

    print(f"Creating new basilisk project: {project_name} (backend: {backend})")

    template_dir = Path(__file__).parent / "templates"
    _scaffold_simple(project_dir, project_name, backend, template_dir)


def _scaffold_simple(project_dir: Path, project_name: str, backend: str, template_dir: Path):
    """Scaffold the minimal single-file template."""
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

    # src/main.py — copy from bundled template
    shutil.copy(template_dir / "main.py", src_dir / "main.py")

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
  src/main.py    — your canister code (counter, greet, status)
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


def main():
    if len(sys.argv) < 2:
        print(_help_text())
        sys.exit(1)

    command = sys.argv[1]

    if command == "new":
        # Parse --backend flag
        args = sys.argv[2:]
        if "--help" in args or "-h" in args:
            print(_HELP_NEW, end="")
            return
        backend = "cpython"  # default
        if "--backend" in args:
            idx = args.index("--backend")
            if idx + 1 >= len(args):
                print("Error: --backend requires a value (cpython or rustpython)", file=sys.stderr)
                sys.exit(1)
            backend = args[idx + 1]
            args = args[:idx] + args[idx + 2:]

        if len(args) < 1:
            print(_HELP_NEW, end="")
            sys.exit(1)
        cmd_new(args[0], backend)

    elif command == "build":
        if "--help" in sys.argv[2:] or "-h" in sys.argv[2:]:
            print(_HELP_BUILD, end="")
            return
        cmd_build()

    elif command in ("-h", "--help", "help"):
        print(_help_text())

    elif command == "--version":
        from basilisk import __version__
        commit = ""
        date = ""
        try:
            from basilisk._build_info import __commit__, __date__
            commit = __commit__
            date = __date__
        except ImportError:
            pass
        if not commit:
            import subprocess
            try:
                commit = subprocess.run(
                    ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                    cwd=os.path.dirname(os.path.abspath(__file__)),
                ).stdout.strip()[:8]
                date = subprocess.run(
                    ["git", "log", "-1", "--format=%cI"],
                    capture_output=True, text=True,
                    cwd=os.path.dirname(os.path.abspath(__file__)),
                ).stdout.strip()
            except FileNotFoundError:
                pass
        print(__version__)
        if date:
            print(date)
        if commit:
            print(commit)

    elif command in _TOOLKIT_COMMANDS:
        try:
            from ic_basilisk_toolkit.cli import main as toolkit_main
            toolkit_main()
        except ImportError:
            print(f"The '{command}' command requires ic-basilisk-toolkit.", file=sys.stderr)
            print("Install it with: pip install ic-basilisk-toolkit", file=sys.stderr)
            sys.exit(1)

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        print(_help_text())
        sys.exit(1)


if __name__ == "__main__":
    main()
