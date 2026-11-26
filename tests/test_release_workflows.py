"""The release path builds what it signs, and its rehearsal cannot release (#83).

These read the workflow files: a pull request that puts the rolling release, a
release download or a cache back on the release path fails here, before any
release is cut.
"""

from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"

# What would let a release take bytes it did not build in its own run. Other
# projects' downloads (the WASI SDK) are allowed: they are pinned by hash.
FOREIGN_SOURCES = [
    "cpython-wasm-3.13.0-ic1",
    "ROLLING_RELEASE_URL",
    "smart-social-contracts/basilisk/releases",
    "releases/latest",
    "gh release download",
    "actions/cache",
]


def load(name):
    return yaml.safe_load((WORKFLOWS / name).read_text())


def text(node):
    return yaml.safe_dump(node)


def foreign_sources_in(node):
    dump = text(node)
    return [source for source in FOREIGN_SOURCES if source in dump]


def test_the_release_workflows_never_read_another_release():
    for name in ["release.yml", "release-build.yml", "release-rehearsal.yml"]:
        assert foreign_sources_in(load(name)) == [], name


def test_releases_and_rehearsals_build_in_release_mode():
    for name in ["release.yml", "release-rehearsal.yml"]:
        assert load(name)["jobs"]["build"]["uses"] == "./.github/workflows/release-build.yml", name
    binaries = load("release-build.yml")["jobs"]["binaries"]
    assert binaries["uses"] == "./.github/workflows/build-cpython-wasm.yml"
    assert binaries["with"]["release"] is True


def test_build_time_hashes_come_only_from_jobs_that_build():
    """A release stages a binary only against the hash its build step recorded."""
    workflow = load("build-cpython-wasm.yml")
    outputs = workflow[True]["workflow_call"]["outputs"]
    hash_jobs = {
        outputs[name]["value"].split("jobs.")[1].split(".")[0]
        for name in outputs if name.endswith("-sha256")
    }
    assert hash_jobs == {"build-cpython-wasm", "build-canister-template"}
    for name in hash_jobs:
        job = workflow["jobs"][name]
        for step in job["steps"]:
            if "actions/cache" in step.get("uses", ""):
                assert "!inputs.release" in step.get("if", ""), (name, step["name"])
            else:
                assert foreign_sources_in(step) == [], (name, step.get("name"))


def test_release_mode_never_fetches_the_published_template():
    jobs = load("build-cpython-wasm.yml")["jobs"]
    readers = {name for name, job in jobs.items() if "ROLLING_RELEASE_URL" in text(job)}
    assert readers == {"check-changes", "fetch-published-template"}
    assert "!inputs.release" in jobs["fetch-published-template"]["if"]
    script = jobs["check-changes"]["steps"][-1]["run"]
    assert script.index("inputs.release") < script.index("ROLLING_RELEASE_URL")


def test_the_rehearsal_cannot_release():
    rehearsal = load("release-rehearsal.yml")
    assert rehearsal["permissions"] == {"contents": "read"}
    assert "release.yml" not in [Path(job.get("uses", "")).name for job in rehearsal["jobs"].values()]
    build = load("release-build.yml")
    assert build["permissions"] == {"contents": "read"}
    for workflow in (rehearsal, build):
        assert all("permissions" not in job for job in workflow["jobs"].values())


def test_a_draft_needs_the_build():
    draft = load("release.yml")["jobs"]["draft"]
    assert set(draft["needs"]) == {"tag", "build"}
    assert "if" not in draft
