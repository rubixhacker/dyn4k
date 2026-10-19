"""Bind signed Android lane expectations to the public full consumer replay.

The caller verifies the audit signature before passing its lane object here.
The signed lane object requires expected_artifact_hashes, expected_runtime_identity,
expected_archive_digests.staged-consumer, and
expected_android_source_toolchain_sha256. The last digest is an external
measurement of the canonical source_and_toolchain map for the exact candidate.
It must be recorded independently of the producer archive or receipt.
"""

import json
import re
from pathlib import Path

import full_android_consumer
import independent_gates
import qualify


SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
ROUTES = {
    "android:Android JVM:minimum:debug": ("21", "debug"),
    "android:Android JVM:minimum:r8-optimized": ("21", "r8-optimized"),
    "android:Android JVM:current:debug": ("37", "debug"),
    "android:Android JVM:current:r8-optimized": ("37", "r8-optimized"),
}


def _digest(value):
    return type(value) is str and SHA256.fullmatch(value) is not None


def verify_full_android_staged_consumer(repository, candidate_sha, lane_id,
                                        selected, archive, expected, gate_result):
    if lane_id not in ROUTES:
        raise ValueError(f"public full Android verifier does not cover lane: {lane_id}")
    if type(candidate_sha) is not str or SHA40.fullmatch(candidate_sha) is None:
        raise ValueError("exact Android candidate SHA is invalid")
    if not isinstance(expected, dict):
        raise ValueError("signed Android lane audit is missing")
    hashes = expected.get("expected_artifact_hashes")
    digests = expected.get("expected_archive_digests")
    runtime = expected.get("expected_runtime_identity")
    source_digest = expected.get("expected_android_source_toolchain_sha256")
    archive_digest = digests.get("staged-consumer") if isinstance(digests, dict) else None
    if (not isinstance(hashes, dict) or set(hashes) != set(full_android_consumer.MODULES)
            or any(not _digest(value) for value in hashes.values())
            or not _digest(runtime) or not _digest(archive_digest)
            or not _digest(source_digest)):
        raise ValueError("signed Android archive, artifact, runtime, or source/toolchain identity is incomplete")
    if (not isinstance(gate_result, dict) or gate_result.get("gate") != "staged-consumer"
            or gate_result.get("status") != "PASSED"
            or gate_result.get("complete_selected_suite") is not True):
        raise ValueError("generic Android staged-consumer gate did not pass")

    repository = Path(repository)
    archive = Path(archive)
    qualify.require_clean_checkout(repository, candidate_sha)
    manifest, cases = full_android_consumer.approved_cases(repository)
    approved = [case["id"] for case in cases]
    if (not isinstance(selected, dict) or selected.get("case_ids") != approved
            or manifest["lanes"].get(lane_id) is None):
        raise ValueError(f"signed Android lane selects a different approved case suite: {lane_id}")
    measured = full_android_consumer.source_and_toolchain(
        repository, {"source_hashes": full_android_consumer.original_source_hashes(repository)})
    if independent_gates.digest(measured) != source_digest:
        raise ValueError("independent Android source/toolchain digest differs")

    public = full_android_consumer.verify_archive(
        repository, archive, archive_digest, hashes["dyn4k-core"], hashes["dyn4k"], runtime)
    if (public.get("candidate_sha") != candidate_sha
            or public.get("archive_digest") != archive_digest
            or public.get("cases") != len(approved)):
        raise ValueError("public Android verifier returned a different candidate or suite")
    if public.get("gate") != gate_result:
        raise ValueError(f"public Android verifier differs from independent gate: {lane_id}")
    receipt = json.loads((archive / "receipt.json").read_text())
    runtime_record = json.loads((archive / "runtime.json").read_text())
    api, configuration = ROUTES[lane_id]
    properties = runtime_record.get("properties", {})
    if (receipt.get("lane") != lane_id or receipt.get("configuration") != configuration
            or properties.get("ro.build.version.sdk") != api
            or properties.get("ro.product.cpu.abi") != "x86_64"):
        raise ValueError(f"Android archive route differs from selected lane: {lane_id}")
    return public
