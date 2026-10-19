"""Bind independently signed Chromium expectations to the public browser replay.

The caller verifies the audit signature and the staged JS target hashes first.
The signed lane object must contain expected_artifact_hashes,
expected_runtime_identity, expected_archive_digests.staged-consumer,
expected_browser_toolchain, and expected_browser_bundles. Bundle hashes must
come from an independent audit, not from the browser producer receipt.
"""

import hashlib
import re
from pathlib import Path

import full_browser_consumer
import independent_gates


SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
TOOLCHAIN_KEYS = frozenset((
    "java_home", "java_version", "java_sha256", "gradle", "gradle_sha256",
    "gradle_version", "kgp_version", "browser", "browser_sha256",
    "browser_version", "gradle_user_home"))


def _digest(value):
    return type(value) is str and SHA256.fullmatch(value) is not None


def _executable(path, expected, label):
    if not path.is_file():
        raise ValueError(f"signed {label} executable bytes differ")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ValueError(f"signed {label} executable bytes differ")


def verify_full_browser_staged_consumer(repository, candidate_sha, lane_id,
                                        selected, archive, expected, gate_result,
                                        audited_target_hashes):
    if lane_id not in full_browser_consumer.LANES:
        raise ValueError(f"public full browser verifier does not cover lane: {lane_id}")
    if type(candidate_sha) is not str or SHA40.fullmatch(candidate_sha) is None:
        raise ValueError("exact browser candidate SHA is invalid")
    if not isinstance(expected, dict):
        raise ValueError("signed browser lane audit is missing")
    hashes = expected.get("expected_artifact_hashes")
    digests = expected.get("expected_archive_digests")
    archive_digest = digests.get("staged-consumer") if isinstance(digests, dict) else None
    runtime = expected.get("expected_runtime_identity")
    toolchain = expected.get("expected_browser_toolchain")
    bundles = expected.get("expected_browser_bundles")
    if (not isinstance(hashes, dict) or set(hashes) != set(full_browser_consumer.MODULES)
            or any(not _digest(value) for value in hashes.values())
            or hashes != audited_target_hashes or not _digest(archive_digest)
            or type(runtime) is not str or not runtime
            or not isinstance(toolchain, dict) or set(toolchain) != TOOLCHAIN_KEYS
            or not isinstance(bundles, dict) or set(bundles) != {"core", "facade"}
            or any(not _digest(value) for value in bundles.values())):
        raise ValueError("signed browser artifact, archive, runtime, toolchain, or bundle identity is incomplete")
    role = lane_id.split(":")[2]
    major, pinned_browser = full_browser_consumer.CHROMIUM[role]
    if (toolchain["java_sha256"] != full_browser_consumer.JAVA_SHA256
            or toolchain["gradle_sha256"] != full_browser_consumer.GRADLE_SHA256
            or toolchain["browser_sha256"] != pinned_browser
            or toolchain["gradle_version"] != "9.5.0"
            or toolchain["kgp_version"] != "2.4.20"
            or not isinstance(toolchain["java_version"], str)
            or not toolchain["java_version"].startswith('openjdk version "21.')
            or not isinstance(toolchain["browser_version"], str)
            or re.search(rf"\b{major}\.\d+", toolchain["browser_version"]) is None):
        raise ValueError("signed browser toolchain differs from selected route or pins")
    for key in ("java_home", "gradle", "browser", "gradle_user_home"):
        if type(toolchain[key]) is not str or not Path(toolchain[key]).is_absolute():
            raise ValueError(f"signed browser {key} is missing or relative")
    _executable(Path(toolchain["java_home"]) / "bin/java", toolchain["java_sha256"], "JDK")
    _executable(Path(toolchain["gradle"]), toolchain["gradle_sha256"], "Gradle")
    _executable(Path(toolchain["browser"]), toolchain["browser_sha256"], "Chromium")

    repository = Path(repository)
    approved = [case["id"] for case in full_browser_consumer.contract(repository, lane_id)["cases"]]
    if not isinstance(selected, dict) or selected.get("case_ids") != approved:
        raise ValueError(f"signed browser lane selects a different approved case suite: {lane_id}")
    if (not isinstance(gate_result, dict) or gate_result.get("gate") != "staged-consumer"
            or gate_result.get("status") != "PASSED"
            or gate_result.get("complete_selected_suite") is not True
            or gate_result.get("selected_cases") != len(approved)
            or gate_result.get("archive_sha256") != archive_digest):
        raise ValueError("generic browser staged-consumer gate differs from signed selection")

    archive = Path(archive)
    if archive.is_symlink() or independent_gates.archive_digest(archive) != archive_digest:
        raise ValueError("signed browser archive digest differs from transported archive")
    receipt = independent_gates._json(archive / "receipt.json")
    if receipt.get("runtime_identity") != runtime or receipt.get("toolchain") != toolchain:
        raise ValueError("browser runtime or toolchain differs from signed lane")
    for short in ("core", "facade"):
        for name in ("karma-selected.js", "linked-executable.js"):
            if hashlib.sha256((archive / short / name).read_bytes()).hexdigest() != bundles[short]:
                raise ValueError("browser selected bundle differs from independent signed hash")

    public = full_browser_consumer.verify(
        repository, candidate_sha, lane_id, archive, archive_digest,
        Path(toolchain["browser"]), hashes)
    if public != {"status": "PASSED", "lane": lane_id,
                  "selected_cases": len(approved), "archive_sha256": archive_digest,
                  "candidate_sha": candidate_sha}:
        raise ValueError("public browser verifier differs from signed lane or generic gate")
    return public
