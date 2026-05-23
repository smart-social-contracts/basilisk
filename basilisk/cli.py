"""
Basilisk — An Internet Computer's Python Canister Development Kit.

Usage: basilisk <command> [options]

Commands:
  (Plugins installed via entry points are listed here)

Other:
  --version        Print version info
  help, -h         Show this help

Use icp-cli for project management:
  icp new <name>   Scaffold a new project
  icp deploy       Build and deploy
  https://cli.internetcomputer.org
"""

import os
import subprocess
import sys
from pathlib import Path


def _discover_plugin_commands() -> dict:
    """Discover CLI commands from installed plugins via entry points."""
    from importlib.metadata import entry_points

    eps = entry_points(group="basilisk.commands")
    return {ep.name: ep for ep in eps}


def _help_text() -> str:
    """Return help text, including plugin commands if available."""
    base = __doc__.strip()
    plugins = _discover_plugin_commands()
    if plugins:
        lines = base.split("\n")
        result = []
        for line in lines:
            if line.startswith("Other:"):
                result.append("Plugin commands:")
                for name, ep in sorted(plugins.items()):
                    fn = ep.load()
                    desc = (fn.__doc__ or "").split("\n")[0].strip()
                    # Strip "basilisk <cmd> — " prefix from docstring
                    if "\u2014" in desc:
                        desc = desc.split("\u2014", 1)[1].strip()
                    elif "--" in desc:
                        desc = desc.split("--", 1)[1].strip()
                    result.append(f"  {name:<16s} {desc}")
                result.append("")
            result.append(line)
        return "\n".join(result)
    return base


def main():
    if len(sys.argv) < 2:
        print(_help_text())
        sys.exit(1)

    command = sys.argv[1]

    if command in ("new", "build"):
        print(f"'basilisk {command}' has been removed.", file=sys.stderr)
        print("Use icp-cli instead:", file=sys.stderr)
        print("  icp new <project>    Scaffold a new project", file=sys.stderr)
        print("  icp deploy           Build and deploy", file=sys.stderr)
        print("  https://cli.internetcomputer.org", file=sys.stderr)
        sys.exit(1)

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

    else:
        # Check for plugin commands
        plugins = _discover_plugin_commands()
        if command in plugins:
            handler = plugins[command].load()
            handler()
            return

        # Unknown command
        print(f"Unknown command: {command}", file=sys.stderr)
        print(_help_text())
        sys.exit(1)


if __name__ == "__main__":
    main()
