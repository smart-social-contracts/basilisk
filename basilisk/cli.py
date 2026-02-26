"""
Basilisk CLI — scaffold and build IC canister projects in Python.

Usage:
    basilisk new <project_name>    Create a new canister project
    basilisk build                 Build the canister in the current directory
"""

import os
import sys
from pathlib import Path


def cmd_new(project_name: str):
    """Scaffold a new basilisk canister project."""
    project_dir = Path(project_name)

    if project_dir.exists():
        print(f"Error: directory '{project_name}' already exists.", file=sys.stderr)
        sys.exit(1)

    # Validate project name (must be a valid canister name)
    if not project_name.replace("_", "").replace("-", "").isalnum():
        print(f"Error: '{project_name}' is not a valid project name. Use alphanumeric, dashes, and underscores.", file=sys.stderr)
        sys.exit(1)

    print(f"Creating new basilisk project: {project_name}")

    # Create directory structure
    src_dir = project_dir / "src"
    src_dir.mkdir(parents=True)

    # dfx.json
    dfx_json = f"""\
{{
    "canisters": {{
        "{project_name}": {{
            "type": "custom",
            "build": "python -m basilisk {project_name} src/main.py",
            "candid": "{project_name}.did",
            "wasm": ".basilisk/{project_name}/{project_name}.wasm"
        }}
    }}
}}
"""
    (project_dir / "dfx.json").write_text(dfx_json)

    # src/main.py
    main_py = """\
from basilisk import query, text

@query
def greet(name: text) -> text:
    return f"Hello, {name}!"
"""
    (src_dir / "main.py").write_text(main_py)

    # .gitignore
    gitignore = """\
.dfx/
.basilisk/
node_modules/
"""
    (project_dir / ".gitignore").write_text(gitignore)

    print(f"""
Done! Created {project_name}/
  src/main.py    — your canister code
  dfx.json       — IC project config

Next steps:
  cd {project_name}
  dfx start --background
  dfx deploy
  dfx canister call {project_name} greet '("World")'
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
        print(__doc__.strip())
        sys.exit(1)

    command = sys.argv[1]

    if command == "new":
        if len(sys.argv) < 3:
            print("Usage: basilisk new <project_name>", file=sys.stderr)
            sys.exit(1)
        cmd_new(sys.argv[2])

    elif command == "build":
        cmd_build()

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
