"""Tests for scripts/stage_release.py: a release stages only what its own run built (#83)."""

import hashlib
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from stage_release import main, release_assets  # noqa: E402

VERSION = "9.9.9"


@pytest.fixture
def built(tmp_path):
    """Every asset of a release, as a run's build steps leave them, and their record."""
    out = tmp_path / "built"
    out.mkdir()
    lines = []
    for name in release_assets(VERSION):
        data = f"built in this run: {name}".encode()
        (out / name).write_bytes(data)
        lines.append(f"{hashlib.sha256(data).hexdigest()}  {name}")
    record = tmp_path / "record.txt"
    record.write_text("\n".join(lines) + "\n")
    return out, record


def run_stage(tmp_path, record, files):
    dest = tmp_path / "release"
    code = main(["stage", VERSION, str(record), str(dest), *map(str, files)])
    return code, dest


def test_a_complete_run_stages_and_writes_checksums(tmp_path, built):
    out, record = built
    code, dest = run_stage(tmp_path, record, sorted(out.iterdir()))
    assert code == 0
    assert sorted(p.name for p in dest.iterdir()) == sorted(release_assets(VERSION) + ["checksums.txt"])
    sums = (dest / "checksums.txt").read_text()
    for name in release_assets(VERSION):
        digest = hashlib.sha256((dest / name).read_bytes()).hexdigest()
        assert f"{digest}  {name}\n" in sums


def test_a_file_from_elsewhere_is_refused(tmp_path, built, capsys):
    """The rolling release's template has other bytes than the one this run built."""
    out, record = built
    (out / "cpython_canister_template.wasm").write_bytes(b"the rolling release's template")
    code, dest = run_stage(tmp_path, record, sorted(out.iterdir()))
    assert code == 1
    assert not dest.exists()
    assert "cpython_canister_template.wasm: sha256" in capsys.readouterr().err


def test_a_file_without_a_build_record_is_refused(tmp_path, built, capsys):
    out, record = built
    kept = [line for line in record.read_text().splitlines() if "cedar" not in line]
    record.write_text("\n".join(kept) + "\n")
    code, dest = run_stage(tmp_path, record, sorted(out.iterdir()))
    assert code == 1
    assert not dest.exists()
    assert "cpython_canister_template_cedar.wasm: no build record" in capsys.readouterr().err


def test_an_empty_build_time_hash_is_refused(tmp_path, built, capsys):
    """A build job that did not run leaves its output empty: `  <name>` in the record."""
    out, record = built
    lines = [
        f"  {line.split()[1]}" if line.endswith("  cpython_canister_template.wasm") else line
        for line in record.read_text().splitlines()
    ]
    record.write_text("\n".join(lines) + "\n")
    code, dest = run_stage(tmp_path, record, sorted(out.iterdir()))
    assert code == 1
    assert not dest.exists()
    assert "unparsable line" in capsys.readouterr().err


@pytest.mark.parametrize("missing", release_assets(VERSION))
def test_a_release_missing_any_asset_is_refused(tmp_path, built, capsys, missing):
    out, record = built
    files = [p for p in sorted(out.iterdir()) if p.name != missing]
    code, dest = run_stage(tmp_path, record, files)
    assert code == 1
    assert not dest.exists()
    assert f"{missing}: missing" in capsys.readouterr().err


def test_an_extra_file_is_refused(tmp_path, built, capsys):
    out, record = built
    extra = out / "template-sources.txt"
    extra.write_text("sources 0\n")
    code, dest = run_stage(tmp_path, record, sorted(out.iterdir()))
    assert code == 1
    assert not dest.exists()
    assert "template-sources.txt: not an asset" in capsys.readouterr().err


def test_an_unreadable_record_is_refused(tmp_path, built, capsys):
    out, record = built
    record.write_text("not a checksum line\n")
    code, dest = run_stage(tmp_path, record, sorted(out.iterdir()))
    assert code == 1
    assert not dest.exists()
    assert "unparsable line" in capsys.readouterr().err


def test_listed_passes_a_complete_checksums_file(tmp_path, built):
    out, record = built
    run_stage(tmp_path, record, sorted(out.iterdir()))
    assert main(["listed", VERSION, str(tmp_path / "release" / "checksums.txt")]) == 0


def test_listed_fails_a_checksums_file_without_the_template(tmp_path, built, capsys):
    """v0.17.0's attack chain started from a release that could ship without a template."""
    out, record = built
    run_stage(tmp_path, record, sorted(out.iterdir()))
    sums = tmp_path / "release" / "checksums.txt"
    sums.write_text("".join(
        line + "\n" for line in sums.read_text().splitlines()
        if not line.endswith("  cpython_canister_template.wasm")
    ))
    assert main(["listed", VERSION, str(sums)]) == 1
    assert "does not list cpython_canister_template.wasm" in capsys.readouterr().err


def test_listed_fails_another_versions_checksums(tmp_path, built, capsys):
    out, record = built
    run_stage(tmp_path, record, sorted(out.iterdir()))
    assert main(["listed", "9.9.10", str(tmp_path / "release" / "checksums.txt")]) == 1
    assert "ic_basilisk-9.9.10.tar.gz" in capsys.readouterr().err
