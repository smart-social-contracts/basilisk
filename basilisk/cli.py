"""
Basilisk — An Internet Computer's Python Canister Development Kit.

Usage: basilisk <command> [options]

Commands:
  new <name>       Scaffold a new canister project
  build            Build the canister(s) in the current directory
  exec <code>      Execute Python code on a deployed canister
  shell            Interactive Python shell on a deployed canister
  sshd             Start an SSH/SFTP server proxy to a canister

Options (exec, shell, sshd):
  --canister <id>  Canister name or principal ID  [auto-detect from dfx.json]
  --network <net>  Network: local, ic, or URL     [default: local]

Other:
  --version        Print version info
  help, -h         Show this help

Run basilisk <command> --help for command-specific options and examples.
"""

import ast
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

_HELP_NEW = """\
basilisk new — Scaffold a new canister project.

Usage: basilisk new [--template simple|tip_jar] [--backend cpython|rustpython] <project_name>

Options:
  --template <t>   Project template: tip_jar (full-stack) or simple (minimal)
                   [default: tip_jar]
  --backend <be>   Python backend: cpython or rustpython  [default: cpython]
                   (rustpython is deprecated and will be removed in a future release)

Examples:
  basilisk new my_app                          Full-stack tip jar template
  basilisk new --template simple my_app        Minimal single-file template
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

_HELP_EXEC = """\
basilisk exec — Execute Python code on a deployed canister.

Usage: basilisk exec [options] <code>
       basilisk exec [options] -f <file>
       echo "code" | basilisk exec [options]

Options:
  --canister <id>  Canister name or principal ID  [auto-detect from dfx.json]
  --network <net>  Network: local, ic, or URL     [default: local]
  -f <file>        Execute a local Python file instead of inline code

Examples:
  basilisk exec 'print("hello")'                         Inline code
  basilisk exec --canister my_app 'print(1+1)'           Explicit canister
  basilisk exec --network ic 'print(ic.time())'          On mainnet
  basilisk exec -f script.py                             Run a local file
  echo "import sys; print(sys.version)" | basilisk exec  Pipe from stdin
"""


def cmd_new(project_name: str, backend: str = "cpython", template: str = "tip_jar"):
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

    if template not in ("simple", "tip_jar"):
        print(f"Error: unknown template '{template}'. Use 'simple' or 'tip_jar'.", file=sys.stderr)
        sys.exit(1)

    if backend == "rustpython":
        print("Warning: rustpython is deprecated and will be removed in a future release. Use cpython instead.", file=sys.stderr)

    print(f"Creating new basilisk project: {project_name} (template: {template}, backend: {backend})")

    template_dir = Path(__file__).parent / "templates"

    if template == "tip_jar":
        _scaffold_tip_jar(project_dir, project_name, backend, template_dir)
    else:
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
  src/main.py    — your canister code (shell, DB, counter, HTTP outcalls)
  dfx.json       — IC project config (backend: {backend})

Next steps:
  cd {project_name}
  dfx start --background
  dfx deploy
  dfx canister call {project_name} greet '("World")'
  dfx canister call {project_name} increment
  dfx canister call {project_name} get_counter
  basilisk shell --canister {project_name}          # interactive shell
  basilisk exec --canister {project_name} 'print(1)'  # one-shot exec
""")


def _scaffold_tip_jar(project_dir: Path, project_name: str, backend: str, template_dir: Path):
    """Scaffold the full-stack Tip Jar template with frontend."""
    tip_jar_template = template_dir / "tip_jar"

    # Copy the entire template tree
    shutil.copytree(tip_jar_template, project_dir)

    # Rename canister references from "tip_jar" to <project_name>
    _replace_in_project(project_dir, project_name, backend)

    backend_name = f"{project_name}_backend"
    build_note = "⚡ fast template build" if backend == "cpython" else "🔨 full Rust build (~5-10 min first time)"
    print(f"""
Done! Created {project_name}/ ({build_note})
  src/backend/     — canister code (models, services, endpoints)
  src/frontend/    — web UI (HTML, JS, CSS)
  dfx.json         — IC project config (backend + frontend canisters)
  README.md        — quick-start guide

Next steps:
  cd {project_name}
  dfx start --background
  dfx deploy
  dfx canister call {backend_name} status
  dfx canister call {backend_name} register_donor '("Alice")'
  dfx canister call {backend_name} get_leaderboard
  basilisk shell --canister {backend_name}

  # Open frontend:
  echo "http://$(dfx canister id {project_name}_frontend).localhost:4943"
""")


def _replace_in_project(project_dir: Path, project_name: str, backend: str):
    """Replace 'tip_jar' with the actual project name in scaffolded files."""
    backend_prefix = "BASILISK_PYTHON_BACKEND=rustpython " if backend == "rustpython" else ""
    replacements = {
        "tip_jar_backend": f"{project_name}_backend",
        "tip_jar_frontend": f"{project_name}_frontend",
        "Tip Jar": project_name.replace("_", " ").title(),
        "tip_jar": project_name,
    }

    # Also patch the build command for rustpython if needed
    if backend == "rustpython":
        replacements[
            f"CANISTER_CANDID_PATH=./{project_name}_backend.did python -m basilisk"
        ] = f"{backend_prefix}CANISTER_CANDID_PATH=./{project_name}_backend.did python -m basilisk"

    text_extensions = {".py", ".json", ".html", ".js", ".css", ".md", ".gitignore"}

    for filepath in project_dir.rglob("*"):
        if not filepath.is_file():
            continue
        if filepath.suffix not in text_extensions and filepath.name != ".gitignore":
            continue
        try:
            content = filepath.read_text()
        except UnicodeDecodeError:
            continue
        original = content
        for old, new in replacements.items():
            content = content.replace(old, new)
        if content != original:
            filepath.write_text(content)


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
        # Parse --backend and --template flags
        args = sys.argv[2:]
        if "--help" in args or "-h" in args:
            print(_HELP_NEW, end="")
            return
        backend = "cpython"  # default
        template = "tip_jar"  # default
        if "--backend" in args:
            idx = args.index("--backend")
            if idx + 1 >= len(args):
                print("Error: --backend requires a value (cpython or rustpython)", file=sys.stderr)
                sys.exit(1)
            backend = args[idx + 1]
            args = args[:idx] + args[idx + 2:]
        if "--template" in args:
            idx = args.index("--template")
            if idx + 1 >= len(args):
                print("Error: --template requires a value (simple or tip_jar)", file=sys.stderr)
                sys.exit(1)
            template = args[idx + 1]
            args = args[:idx] + args[idx + 2:]

        if len(args) < 1:
            print(_HELP_NEW, end="")
            sys.exit(1)
        cmd_new(args[0], backend, template)

    elif command == "build":
        if "--help" in sys.argv[2:] or "-h" in sys.argv[2:]:
            print(_HELP_BUILD, end="")
            return
        cmd_build()

    elif command == "exec":
        if "--help" in sys.argv[2:] or "-h" in sys.argv[2:]:
            print(_HELP_EXEC, end="")
            return
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
        import subprocess
        commit = ""
        date = ""
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
        print(f"{__version__},{date},{commit}")

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        print(__doc__.strip())
        sys.exit(1)


if __name__ == "__main__":
    main()
