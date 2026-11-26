"""Stage a release's assets, refusing anything this run did not build (#83).

    stage_release.py stage VERSION RECORD DEST FILE...
    stage_release.py listed VERSION CHECKSUMS

`stage` copies FILE... into DEST and writes DEST/checksums.txt. RECORD is a
sha256sum-style file holding the hash of every asset as the step that built it
recorded it, in this release run. Nothing is staged unless:

- every asset a release must carry (release_assets) is among FILE..., and
  nothing else is: a release without its template is refused, not published;
- every one of them has a line in RECORD: a file this run did not build, such
  as one downloaded from the rolling cpython-wasm release, has no build record;
- each file's bytes hash to its recorded value.

`listed` checks that a release's checksums.txt lists every asset a release of
VERSION must carry. release-verify.yml runs it on the signed file, so a release
that lost an asset is not published.

Exits 1, staging nothing, on any failure.
"""

import hashlib
import re
import shutil
import sys
from pathlib import Path

LINE = re.compile(r"^([0-9a-f]{64})\s+\*?(\S+)$")


def release_assets(version: str) -> list[str]:
    """The files a signed release of `version` carries, besides checksums.txt."""
    return [
        f"ic_basilisk-{version}.tar.gz",
        f"ic_basilisk-{version}-py3-none-any.whl",
        "cpython_canister_template.wasm",
        "cpython_canister_template_cedar.wasm",
        "cpython-wasm32-wasip1.tar.gz",
        "recipe.hbs",
    ]


def read_sums(path: Path) -> dict[str, str]:
    """Parse `<sha256>  <name>` lines; comments and blank lines are skipped."""
    sums = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = LINE.match(line)
        if not match:
            raise ValueError(f"{path.name}: unparsable line {raw!r}")
        digest, name = match.groups()
        if name in sums:
            raise ValueError(f"{path.name}: {name} is listed twice")
        sums[name] = digest
    return sums


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def staging_errors(expected: list[str], record: dict[str, str], files: list[Path]) -> list[str]:
    errors = []
    by_name: dict[str, Path] = {}
    for path in files:
        if path.name in by_name:
            errors.append(f"{path.name}: given twice ({by_name[path.name]}, {path})")
        by_name[path.name] = path

    for name in expected:
        path = by_name.get(name)
        if path is None or not path.is_file():
            errors.append(f"{name}: missing; a release without it is refused")
        elif name not in record:
            errors.append(f"{name}: no build record from this run, so this run did not build it")
        elif (actual := sha256(path)) != record[name]:
            errors.append(f"{name}: sha256 {actual} is not the {record[name]} this run built")
    for name in sorted(set(by_name) - set(expected)):
        errors.append(f"{name}: not an asset a release carries")
    return errors


def stage(version: str, record_path: Path, dest: Path, files: list[Path]) -> int:
    expected = release_assets(version)
    errors = staging_errors(expected, read_sums(record_path), files)
    if dest.exists():
        errors.append(f"{dest}: already exists; stage into a new directory")
    if errors:
        for error in errors:
            print(f"::error::{error}", file=sys.stderr)
        return 1

    dest.mkdir(parents=True)
    by_name = {path.name: path for path in files}
    lines = ["# SHA-256 checksums for release assets"]
    for name in sorted(expected):
        shutil.copyfile(by_name[name], dest / name)
        lines.append(f"{sha256(dest / name)}  {name}")
    (dest / "checksums.txt").write_text("\n".join(lines) + "\n")
    print((dest / "checksums.txt").read_text(), end="")
    return 0


def listed(version: str, checksums: Path) -> int:
    missing = [name for name in release_assets(version) if name not in read_sums(checksums)]
    for name in missing:
        print(f"::error::{checksums.name} does not list {name}", file=sys.stderr)
    return 1 if missing else 0


def main(argv: list[str]) -> int:
    try:
        if len(argv) >= 5 and argv[0] == "stage":
            _, version, record, dest, *files = argv
            return stage(version, Path(record), Path(dest), [Path(f) for f in files])
        if len(argv) == 3 and argv[0] == "listed":
            return listed(argv[1], Path(argv[2]))
    except (OSError, ValueError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print(__doc__.strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
