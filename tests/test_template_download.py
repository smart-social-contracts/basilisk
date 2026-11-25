"""Tests for how the build downloads and verifies the canister template (#68).

A download must match checksums.txt of the release it came from, and a
versioned release's checksums.txt must carry the release key's signature.
GitHub is faked; the signed files are the real ones of v0.17.0 (tests/data).
"""

import hashlib
import io
import os
import shutil
import subprocess
import urllib.error
import urllib.request

import pytest

import basilisk
from basilisk import build_wasm_binary_or_exit as build
from basilisk.build_wasm_binary_or_exit import TemplateVerificationError

DATA = os.path.join(os.path.dirname(__file__), "data")
RELEASES = "https://github.com/smart-social-contracts/basilisk/releases/download"
V0_17_0 = f"{RELEASES}/v0.17.0"
ROLLING = f"{RELEASES}/cpython-wasm-3.13.0-ic1"
TEMPLATE = "cpython_canister_template.wasm"

needs_gpg = pytest.mark.skipif(shutil.which("gpg") is None, reason="gpg is not installed")


def data(name):
    with open(os.path.join(DATA, name), "rb") as f:
        return f.read()


def checksums_for(**assets):
    lines = ["# SHA-256 checksums for release assets"]
    lines += [f"{hashlib.sha256(content).hexdigest()}  {name}" for name, content in assets.items()]
    return ("\n".join(lines) + "\n").encode()


@pytest.fixture
def github(monkeypatch):
    """A fake GitHub: put {url: bytes} in `pages`; `requested` lists what the build fetched."""
    pages, requested = {}, []

    def urlopen(url):
        requested.append(url)
        if url not in pages:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return io.BytesIO(pages[url])

    def urlretrieve(url, dest):
        with open(dest, "wb") as f:
            f.write(urlopen(url).read())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(urllib.request, "urlretrieve", urlretrieve)
    monkeypatch.setattr(basilisk, "__version__", "0.17.0")
    return pages, requested


def signed_v0_17_0(pages):
    pages[f"{V0_17_0}/checksums.txt"] = data("v0.17.0-checksums.txt")
    pages[f"{V0_17_0}/checksums.txt.asc"] = data("v0.17.0-checksums.txt.asc")


@needs_gpg
def test_the_bundled_key_is_the_release_key():
    shown = subprocess.run(["gpg", "--show-keys", "--with-colons", build.RELEASE_KEY_PATH],
                           capture_output=True, text=True, check=True).stdout
    primary = next(line for line in shown.splitlines() if line.startswith("fpr:"))
    assert primary.split(":")[9] == build.RELEASE_KEY_FINGERPRINT


@needs_gpg
def test_an_asset_of_a_signed_release_verifies(github, tmp_path):
    pages, _ = github
    signed_v0_17_0(pages)
    asset = tmp_path / "recipe.hbs"
    asset.write_bytes(data("v0.17.0-recipe.hbs"))
    build._verify_template(f"{V0_17_0}/recipe.hbs", str(asset), signed=True)


@needs_gpg
def test_altered_checksums_fail_the_signature(github, tmp_path):
    pages, _ = github
    signed_v0_17_0(pages)
    pages[f"{V0_17_0}/checksums.txt"] = data("v0.17.0-checksums.txt").replace(b"2940", b"2941")
    asset = tmp_path / "recipe.hbs"
    asset.write_bytes(data("v0.17.0-recipe.hbs"))
    with pytest.raises(TemplateVerificationError, match="not a valid signature by the release key"):
        build._verify_template(f"{V0_17_0}/recipe.hbs", str(asset), signed=True)


def test_a_signed_release_without_a_signature_fails(github, tmp_path):
    pages, _ = github
    pages[f"{V0_17_0}/checksums.txt"] = data("v0.17.0-checksums.txt")
    asset = tmp_path / "recipe.hbs"
    asset.write_bytes(data("v0.17.0-recipe.hbs"))
    with pytest.raises(TemplateVerificationError, match="checksums.txt.asc"):
        build._verify_template(f"{V0_17_0}/recipe.hbs", str(asset), signed=True)


def test_without_gpg_the_checksum_still_decides(github, tmp_path, monkeypatch, capsys):
    pages, _ = github
    signed_v0_17_0(pages)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    asset = tmp_path / "recipe.hbs"
    asset.write_bytes(data("v0.17.0-recipe.hbs"))
    build._verify_template(f"{V0_17_0}/recipe.hbs", str(asset), signed=True)
    assert "gpg is not installed" in capsys.readouterr().out
    asset.write_bytes(b"something else")
    with pytest.raises(TemplateVerificationError, match="but checksums.txt lists"):
        build._verify_template(f"{V0_17_0}/recipe.hbs", str(asset), signed=True)


def test_a_template_that_does_not_match_stops_the_build(github, tmp_path):
    """A replaced template is removed, and the build does not go on to the fallback."""
    pages, requested = github
    signed_v0_17_0(pages)
    pages[f"{V0_17_0}/{TEMPLATE}"] = b"not the template that was signed"
    pages[f"{ROLLING}/{TEMPLATE}"] = b"rolling"
    pages[f"{ROLLING}/checksums.txt"] = checksums_for(**{TEMPLATE: b"rolling"})
    dest = tmp_path / TEMPLATE
    with pytest.raises(SystemExit):
        build._download_template(str(dest))
    assert not dest.exists()
    assert not any(url.startswith(ROLLING) for url in requested)


def test_the_fallback_is_checked_against_its_checksums(github, tmp_path, capsys):
    pages, _ = github
    pages[f"{ROLLING}/{TEMPLATE}"] = b"rolling"
    pages[f"{ROLLING}/checksums.txt"] = checksums_for(**{TEMPLATE: b"rolling"})
    dest = tmp_path / TEMPLATE
    assert build._download_template(str(dest)) is True
    assert dest.read_bytes() == b"rolling"
    assert "not signed" in capsys.readouterr().out


def test_a_fallback_without_checksums_stops_the_build(github, tmp_path):
    pages, _ = github
    pages[f"{ROLLING}/{TEMPLATE}"] = b"rolling"
    dest = tmp_path / TEMPLATE
    with pytest.raises(SystemExit):
        build._download_template(str(dest))
    assert not dest.exists()


def test_a_checksums_file_that_does_not_list_the_template_fails(github, tmp_path):
    pages, _ = github
    pages[f"{ROLLING}/{TEMPLATE}"] = b"rolling"
    pages[f"{ROLLING}/checksums.txt"] = checksums_for(**{"other.wasm": b"rolling"})
    dest = tmp_path / TEMPLATE
    with pytest.raises(SystemExit):
        build._download_template(str(dest))


def test_no_template_anywhere_returns_false(github, tmp_path):
    assert build._download_template(str(tmp_path / TEMPLATE)) is False


def test_an_explicit_template_that_does_not_exist_stops_the_build(monkeypatch, tmp_path):
    monkeypatch.setenv("BASILISK_TEMPLATE_WASM", str(tmp_path / "missing.wasm"))
    with pytest.raises(SystemExit):
        build.find_template_wasm({"global_basilisk_version_dir": str(tmp_path)})
