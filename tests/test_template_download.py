"""Tests for how the build downloads and verifies the canister template (#68).

The template must be listed in its release's checksums.txt, checksums.txt must
be signed by the release key and name this version's sdist, and only a
template that passes all of that may reach the cache, which later builds trust
as it is. GitHub is faked; the signed files are the real ones of v0.17.0
(tests/data). A throwaway second key stands in for an attacker's valid key.
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


def signed_v0_17_0(pages, release=V0_17_0):
    pages[f"{release}/checksums.txt"] = data("v0.17.0-checksums.txt")
    pages[f"{release}/checksums.txt.asc"] = data("v0.17.0-checksums.txt.asc")


def recipe(tmp_path, content=None):
    """recipe.hbs, an asset that v0.17.0's signed checksums.txt lists, as a downloaded file."""
    asset = tmp_path / "recipe.hbs"
    asset.write_bytes(data("v0.17.0-recipe.hbs") if content is None else content)
    return str(asset)


def nothing_left_behind(directory):
    return [name for name in os.listdir(directory) if name.endswith(".download")] == []


@pytest.fixture
def other_key(tmp_path_factory):
    """A second, valid signing key in its own gpg home: (sign(bytes) -> signature, public key path)."""
    home = str(tmp_path_factory.mktemp("gnupg"))
    gpg = ["gpg", "--homedir", home, "--batch", "--quiet", "--pinentry-mode", "loopback", "--passphrase", ""]
    subprocess.run(gpg + ["--quick-gen-key", "Not the release key <other@example.org>", "ed25519", "sign", "never"],
                   check=True, capture_output=True)
    public = os.path.join(home, "other.asc")
    subprocess.run(gpg + ["--armor", "--output", public, "--export"], check=True, capture_output=True)

    def sign(content):
        source = os.path.join(home, "to-sign")
        with open(source, "wb") as f:
            f.write(content)
        return subprocess.run(gpg + ["--detach-sign", "--output", "-", source],
                              check=True, capture_output=True).stdout

    yield sign, public
    subprocess.run(["gpgconf", "--homedir", home, "--kill", "all"], capture_output=True)


# --- the signature --------------------------------------------------------------------


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
    build._verify_template(f"{V0_17_0}/recipe.hbs", recipe(tmp_path))


@needs_gpg
def test_altered_checksums_fail_the_signature(github, tmp_path):
    pages, _ = github
    signed_v0_17_0(pages)
    pages[f"{V0_17_0}/checksums.txt"] = data("v0.17.0-checksums.txt").replace(b"2940", b"2941")
    with pytest.raises(TemplateVerificationError, match="not a valid signature by the release key"):
        build._verify_template(f"{V0_17_0}/recipe.hbs", recipe(tmp_path))


@needs_gpg
def test_a_valid_signature_by_another_key_fails(github, tmp_path, monkeypatch, other_key):
    """gpg accepts it (the other key is known here), so only the fingerprint pin refuses it."""
    sign, other_public = other_key
    pages, _ = github
    checksums = data("v0.17.0-checksums.txt")
    pages[f"{V0_17_0}/checksums.txt"] = checksums
    pages[f"{V0_17_0}/checksums.txt.asc"] = sign(checksums)
    both = tmp_path / "both-keys.asc"
    both.write_bytes(data_of(build.RELEASE_KEY_PATH) + data_of(other_public))
    monkeypatch.setattr(build, "RELEASE_KEY_PATH", str(both))
    with pytest.raises(TemplateVerificationError, match="not a valid signature by the release key"):
        build._verify_template(f"{V0_17_0}/recipe.hbs", recipe(tmp_path))


@needs_gpg
def test_a_good_signature_with_an_unverifiable_one_beside_it_fails(github, tmp_path, other_key):
    """The release key's signature verifies, but gpg fails the file; its exit status counts."""
    sign, _ = other_key
    pages, _ = github
    signed_v0_17_0(pages)
    pages[f"{V0_17_0}/checksums.txt.asc"] = (
        dearmor(data("v0.17.0-checksums.txt.asc")) + sign(data("v0.17.0-checksums.txt")))
    with pytest.raises(TemplateVerificationError, match="not a valid signature by the release key"):
        build._verify_template(f"{V0_17_0}/recipe.hbs", recipe(tmp_path))


def test_a_release_without_a_signature_fails(github, tmp_path):
    pages, _ = github
    pages[f"{V0_17_0}/checksums.txt"] = data("v0.17.0-checksums.txt")
    with pytest.raises(TemplateVerificationError, match="checksums.txt.asc"):
        build._verify_template(f"{V0_17_0}/recipe.hbs", recipe(tmp_path))


def test_without_gpg_nothing_verifies(github, tmp_path, monkeypatch):
    pages, _ = github
    signed_v0_17_0(pages)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(TemplateVerificationError, match="gpg is not installed"):
        build._verify_template(f"{V0_17_0}/recipe.hbs", recipe(tmp_path))


@needs_gpg
def test_another_versions_signed_checksums_do_not_verify(github, tmp_path, monkeypatch):
    """v0.17.0's genuine signed pair, served as v0.18.0's: a replay."""
    pages, _ = github
    monkeypatch.setattr(basilisk, "__version__", "0.18.0")
    v0_18_0 = f"{RELEASES}/v0.18.0"
    signed_v0_17_0(pages, release=v0_18_0)
    with pytest.raises(TemplateVerificationError, match="does not list ic_basilisk-0.18.0.tar.gz"):
        build._verify_template(f"{v0_18_0}/recipe.hbs", recipe(tmp_path))


@needs_gpg
def test_an_asset_that_does_not_match_its_checksum_fails(github, tmp_path):
    pages, _ = github
    signed_v0_17_0(pages)
    with pytest.raises(TemplateVerificationError, match="but checksums.txt lists"):
        build._verify_template(f"{V0_17_0}/recipe.hbs", recipe(tmp_path, b"something else"))


# --- the download and the cache --------------------------------------------------------


def test_a_verified_template_is_cached(github, tmp_path, monkeypatch):
    pages, _ = github
    monkeypatch.setattr(build, "_verify_signature", lambda checksums, signature: None)
    pages[f"{V0_17_0}/{TEMPLATE}"] = b"the template"
    pages[f"{V0_17_0}/checksums.txt.asc"] = b"(signature, checked elsewhere)"
    pages[f"{V0_17_0}/checksums.txt"] = (
        f"{hashlib.sha256(b'the template').hexdigest()}  {TEMPLATE}\n"
        f"{hashlib.sha256(b'sdist').hexdigest()}  ic_basilisk-0.17.0.tar.gz\n").encode()
    dest = tmp_path / TEMPLATE
    assert build._download_template(str(dest)) is True
    assert dest.read_bytes() == b"the template"
    assert nothing_left_behind(tmp_path)


def test_a_template_that_does_not_match_stops_the_build(github, tmp_path):
    pages, _ = github
    signed_v0_17_0(pages)
    pages[f"{V0_17_0}/{TEMPLATE}"] = b"EVIL"
    dest = tmp_path / TEMPLATE
    with pytest.raises(SystemExit):
        build._download_template(str(dest))
    assert not dest.exists() and nothing_left_behind(tmp_path)


def test_a_missing_template_does_not_fall_back_to_the_unsigned_release(github, tmp_path):
    """B1: with v0.17.0's template gone, a template on cpython-wasm must not be used."""
    pages, requested = github
    signed_v0_17_0(pages)
    pages[f"{ROLLING}/{TEMPLATE}"] = b"EVIL"
    pages[f"{ROLLING}/checksums.txt"] = f"{hashlib.sha256(b'EVIL').hexdigest()}  {TEMPLATE}\n".encode()
    dest = tmp_path / TEMPLATE
    assert build._download_template(str(dest)) is False
    assert not dest.exists() and nothing_left_behind(tmp_path)
    assert not any(url.startswith(ROLLING) for url in requested)


def test_without_a_template_the_build_stops_unless_a_source_build_is_asked_for(monkeypatch):
    """A source build takes its CPython from the unsigned release, so it has to be asked for."""
    monkeypatch.setattr(build, "find_template_wasm", lambda paths: None)
    monkeypatch.delenv("BASILISK_TEMPLATE_FROM_SOURCE", raising=False)

    def source_build(*args):
        raise AssertionError("built from source without BASILISK_TEMPLATE_FROM_SOURCE=1")

    monkeypatch.setattr(build, "build_template_from_source", source_build)
    with pytest.raises(SystemExit):
        build.build_with_template({}, "canister", {}, False)


@pytest.mark.parametrize("failure", [
    "checksums.txt that is not UTF-8",
    "gpg cannot import the key",
    "interrupted while verifying",
])
def test_a_verification_that_does_not_finish_leaves_nothing_in_the_cache(github, tmp_path, monkeypatch, failure):
    """B2: later builds trust the cached file without checking, so only a verified one may get there."""
    pages, _ = github
    signed_v0_17_0(pages)
    pages[f"{V0_17_0}/{TEMPLATE}"] = b"EVIL"
    expected = SystemExit
    if failure == "checksums.txt that is not UTF-8":
        monkeypatch.setattr(build, "_verify_signature", lambda checksums, signature: None)
        pages[f"{V0_17_0}/checksums.txt"] = b"\xff\xfe not text"
    elif failure == "gpg cannot import the key":
        monkeypatch.setattr(build, "RELEASE_KEY_PATH", str(tmp_path / "missing-key.asc"))
        monkeypatch.setattr(shutil, "which", lambda name: "/bin/false")
    else:
        def interrupted(url, path):
            raise KeyboardInterrupt
        monkeypatch.setattr(build, "_verify_template", interrupted)
        expected = KeyboardInterrupt
    dest = tmp_path / TEMPLATE
    with pytest.raises(expected):
        build._download_template(str(dest))
    assert not dest.exists() and nothing_left_behind(tmp_path)


def test_no_template_returns_false(github, tmp_path):
    assert build._download_template(str(tmp_path / TEMPLATE)) is False
    assert nothing_left_behind(tmp_path)


def test_an_explicit_template_that_does_not_exist_stops_the_build(monkeypatch, tmp_path):
    monkeypatch.setenv("BASILISK_TEMPLATE_WASM", str(tmp_path / "missing.wasm"))
    with pytest.raises(SystemExit):
        build.find_template_wasm({"global_basilisk_version_dir": str(tmp_path)})


def data_of(path):
    with open(path, "rb") as f:
        return f.read()


def dearmor(armored):
    return subprocess.run(["gpg", "--dearmor"], input=armored, capture_output=True, check=True).stdout
