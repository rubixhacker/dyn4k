#!/usr/bin/env python3
"""Prepare an independently observed 112-lane audit for detached signing."""

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

import independent_adapter
import independent_gates
import qualify


SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
ROUTE_FIELDS = {
    "jvm": {"expected_java_executable_sha256", "expected_gradle_executable_sha256",
            "expected_runtime_java_executable_sha256", "expected_mode_publication_path",
            "expected_mode_publication_digest"},
    "android-jvm": {"expected_android_source_toolchain_sha256"},
    "klib": {"expected_klib_toolchain", "expected_klib_executables"},
    "browser": {"expected_browser_toolchain", "expected_browser_bundles"},
    "wasm-node": {"expected_wasm_runtime", "expected_wasm_runtime_binary"},
    "native-host": {"expected_native_selection", "expected_native_host",
                    "expected_native_toolchain", "expected_native_host_executables",
                    "expected_execution_witness"},
    "android-native": {"expected_android_native_guest", "expected_android_native_toolchain",
                       "expected_android_native_executables", "expected_android_native_adb",
                       "expected_android_native_serial", "expected_android_native_replay_output",
                       "expected_android_native_executable_paths", "expected_execution_witness"},
    "apple-device": {"expected_apple_device", "expected_apple_device_toolchain",
                     "expected_apple_device_executable_paths",
                     "expected_apple_device_executable_hashes", "expected_apple_os_roles"},
}
CROSS_FIELDS = {"expected_native_build_archive_sha256", "expected_native_build_host",
                "expected_native_build_executables"}
OPTIONAL_FIELDS = {"expected_producer_scopes", "expected_unavailability", "expected_not_run",
                   "expected_execution_witness", "expected_klib_native_executables",
                   "expected_browser_responses"}


def canonical_json(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _load(path):
    return independent_adapter._decode(Path(path).read_bytes())


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _snapshot(path):
    root = Path(path)
    if (not root.is_absolute() or not root.is_dir() or root.is_symlink()
            or root.resolve() != root):
        raise ValueError(f"archive path is absent, relative, or symbolic: {root}")
    files = {}
    for item in root.rglob("*"):
        if item.is_symlink() or not item.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"archive has a symbolic or escaping member: {item}")
        if item.is_file():
            relative = item.relative_to(root).as_posix()
            files[relative] = {"sha256": _sha(item), "mtime_ns": item.stat().st_mtime_ns}
        elif not item.is_dir():
            raise ValueError(f"archive has a nonregular member: {item}")
    return {"path": str(root), "files": files,
            "snapshot_sha256": independent_gates.digest(files)}


def _write_new(directory, name, value):
    path = directory / name
    with path.open("xb") as output:
        output.write(canonical_json(value))
    return path


def _inputs(repository, candidate_sha, candidate_path, staged_path):
    repository = Path(repository)
    if not SHA40.fullmatch(str(candidate_sha)):
        raise ValueError("candidate SHA must identify an exact commit")
    head = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "rev-parse", "HEAD"],
        text=True).strip()
    if head != candidate_sha:
        raise ValueError("candidate differs from repository HEAD")
    qualify.require_clean_checkout(repository, candidate_sha)
    suite = independent_gates.load_approved_manifest(repository)
    if len(suite["lanes"]) != 112 or independent_gates.digest(suite) != independent_gates.APPROVED_MANIFEST_SHA256:
        raise ValueError("approved 112-lane suite digest differs")
    candidate = _load(candidate_path)
    staged = _load(staged_path)
    if (not isinstance(candidate, dict) or not isinstance(staged, dict)
            or candidate.get("candidate_sha") != candidate_sha
            or staged.get("candidate_sha") != candidate_sha
            or staged.get("status") != "PASSED"
            or candidate.get("suite_manifest_sha256") != independent_gates.digest(suite)
            or candidate.get("audit_manifest_sha256") != qualify.manifest_digest(staged)
            or not isinstance(candidate.get("lanes"), dict)
            or set(candidate["lanes"]) != set(suite["lanes"])):
        raise ValueError("candidate manifest or staged audit differs from exact candidate")
    qualify.verify_audit_against_staging(staged, repository)
    hashes = qualify.target_binary_hashes(staged.get("artifacts", []))
    if (set(hashes) != qualify.matrix_targets()
            or any(set(pair) != set(qualify.MODULES)
                   or any(type(value) is not str or not SHA64.fullmatch(value)
                          for value in pair.values()) for pair in hashes.values())):
        raise ValueError("staged audit lacks all 21 target binary hashes")
    return suite, candidate, staged, hashes


def prepare(repository, candidate_sha, candidate_manifest_path, staged_audit_path,
            observations_path, output_dir, trusted_key_sha256, performance_key=None):
    repository = Path(repository)
    if not SHA64.fullmatch(str(trusted_key_sha256)):
        raise ValueError("trusted public key fingerprint is invalid")
    suite, candidate, staged, all_hashes = _inputs(
        repository, candidate_sha, candidate_manifest_path, staged_audit_path)
    observations = _load(observations_path)
    if (not isinstance(observations, dict)
            or set(observations) != {"schema", "candidate_sha", "lanes"}
            or observations["schema"] != 1 or observations["candidate_sha"] != candidate_sha
            or not isinstance(observations["lanes"], dict)
            or set(observations["lanes"]) != set(suite["lanes"])):
        raise ValueError("independent observations differ from exact candidate or 112 lanes")
    routes = __import__("full_signed_routes").route_table(repository, suite)
    archive_map = {"schema": 1, "candidate_sha": candidate_sha, "lanes": {}}
    audit = {"schema": 1, "candidate_sha": candidate_sha,
             "suite_manifest_sha256": independent_gates.digest(suite),
             "candidate_manifest_sha256": qualify.manifest_digest(candidate),
             "staged_audit_sha256": qualify.manifest_digest(staged),
             "candidate_manifest_bytes_sha256": _sha(candidate_manifest_path),
             "staged_audit_bytes_sha256": _sha(staged_audit_path),
             "trusted_audit_key_sha256": trusted_key_sha256,
             "expected_all_target_hashes": all_hashes, "lanes": {},
             "archive_snapshots": {}, "preflight_results": {}}
    for lane_id in suite["lanes"]:
        observed = observations["lanes"][lane_id]
        if (not isinstance(observed, dict)
                or set(observed) != {"archives", "signed_fields"}
                or not isinstance(observed["archives"], dict)
                or not isinstance(observed["signed_fields"], dict)):
            raise ValueError(f"independent lane observation is invalid: {lane_id}")
        lane = candidate["lanes"][lane_id]
        target = suite["lanes"][lane_id]["target"]
        if (not isinstance(lane, dict)
                or type(lane.get("runtime_identity")) is not str
                or not lane["runtime_identity"]):
            raise ValueError(f"candidate lane artifact or runtime differs from staging: {lane_id}")
        binding = lane.get("jvm_mode_publication") if routes[lane_id] == "jvm" else None
        if binding is not None:
            case = {"id": lane_id, "target": target,
                    "configuration": suite["lanes"][lane_id]["configuration"]}
            if (not isinstance(binding, dict)
                    or lane.get("artifact_hashes") != binding.get("artifact_hashes")
                    or qualify.verify_jvm_mode_publication(
                        binding, case, candidate_sha, lane["artifact_hashes"]) is not True):
                raise ValueError(f"candidate JVM mode publication is unverified: {lane_id}")
        elif lane.get("artifact_hashes") != all_hashes[target]:
            raise ValueError(f"candidate lane artifact or runtime differs from staging: {lane_id}")
        paths = observed["archives"]
        gate_names = set(suite["lanes"][lane_id]["required_gates"] + suite["global_gates"])
        if set(paths) - gate_names or any(type(path) is not str for path in paths.values()):
            raise ValueError(f"archive map has an inapplicable gate: {lane_id}")
        cross = False
        if (routes[lane_id] == "native-host" and target == "linuxArm64"
                and "staged-consumer" in paths):
            try:
                cross_receipt = _load(Path(paths["staged-consumer"]) / "receipt.json")
            except (OSError, ValueError, TypeError):
                cross_receipt = None
            cross = isinstance(cross_receipt, dict) and cross_receipt.get("schema") == 3
        fields = observed["signed_fields"]
        route_fields = set(ROUTE_FIELDS[routes[lane_id]])
        if cross:
            route_fields.remove("expected_native_host_executables")
            route_fields |= CROSS_FIELDS
        allowed = OPTIONAL_FIELDS | route_fields
        if set(fields) - allowed:
            raise ValueError(f"unrecognized signed route field: {lane_id}")
        if binding is not None and (
                fields.get("expected_mode_publication_path", binding.get("publication_archive"))
                != binding.get("publication_archive")
                or fields.get("expected_mode_publication_digest", binding.get("archive_digest"))
                != binding.get("archive_digest")):
            raise ValueError(f"signed JVM mode publication differs from candidate: {lane_id}")
        expected = {"expected_artifact_hashes": lane["artifact_hashes"],
                    "expected_runtime_identity": lane["runtime_identity"],
                    "expected_archive_digests": {}}
        expected.update(fields)
        if binding is not None:
            expected["expected_mode_publication_path"] = binding["publication_archive"]
            expected["expected_mode_publication_digest"] = binding["archive_digest"]
        snapshots = {}
        for gate, path in paths.items():
            snapshots[gate] = _snapshot(path)
            try:
                receipt = _load(Path(path) / "receipt.json")
            except (OSError, ValueError, TypeError):
                receipt = None
            if isinstance(receipt, dict) and receipt.get("status") == "PASSED" and gate == "staged-consumer":
                required = set(route_fields)
                if lane_id.startswith("linuxX64:"):
                    required |= {"expected_klib_native_executables", "expected_execution_witness"}
                if lane_id.startswith("wasmJs:"):
                    required |= {"expected_browser_responses", "expected_execution_witness"}
                if not required <= set(fields):
                    raise ValueError(f"signed route fields are incomplete: {lane_id}")
            if isinstance(receipt, dict) and receipt.get("status") == "UNAVAILABLE":
                if gate != "staged-consumer" or fields.get("expected_unavailability") != receipt:
                    raise ValueError(f"unavailability has no independent signed observation: {lane_id} {gate}")
            try:
                if gate == "staged-consumer" and routes[lane_id] == "wasm-node":
                    import full_wasm_node_consumer

                    measured = full_wasm_node_consumer.archive_digest(path)
                else:
                    measured = independent_gates.archive_digest(path)
                expected["expected_archive_digests"][gate] = measured
            except ValueError:
                pass
        archive_map["lanes"][lane_id] = paths
        audit["lanes"][lane_id] = expected
        audit["archive_snapshots"][lane_id] = snapshots
        result = independent_gates.evaluate(
            suite, candidate_sha, lane_id, {gate: Path(path) for gate, path in paths.items()},
            repository, expected["expected_artifact_hashes"],
            expected["expected_runtime_identity"], expected["expected_archive_digests"],
            all_hashes, expected.get("expected_producer_scopes"), performance_key, expected)
        for gate, path in paths.items():
            try:
                receipt = _load(Path(path) / "receipt.json")
            except (OSError, ValueError, TypeError):
                receipt = None
            if (isinstance(receipt, dict) and receipt.get("status") == "PASSED"
                    and result["gates"][gate]["status"] == "NOT_RUN"):
                raise ValueError(f"reported PASSED lacks public verifier prerequisites: {lane_id} {gate}")
        audit["preflight_results"][lane_id] = {
            "result_sha256": result["result_sha256"], "status": result["status"],
            "gates": {gate: value["status"] for gate, value in result["gates"].items()}}
    audit["archive_map_sha256"] = hashlib.sha256(canonical_json(archive_map)).hexdigest()
    audit["observations_sha256"] = _sha(observations_path)
    audit["performance_key_sha256"] = _sha(performance_key) if performance_key else None
    request = {"schema": 1, "kind": "detached-independent-audit-signing-request",
               "candidate_sha": candidate_sha,
               "trusted_audit_key_sha256": trusted_key_sha256,
               "audit_sha256": hashlib.sha256(canonical_json(audit)).hexdigest(),
               "archive_map_sha256": audit["archive_map_sha256"],
               "candidate_manifest_bytes_sha256": audit["candidate_manifest_bytes_sha256"],
               "staged_audit_bytes_sha256": audit["staged_audit_bytes_sha256"],
               "observations_bytes_sha256": _sha(observations_path),
               "performance_key_sha256": audit["performance_key_sha256"]}
    output = Path(output_dir)
    output.mkdir(mode=0o700)
    os.chmod(output, 0o700)
    _write_new(output, "archive-map.json", archive_map)
    _write_new(output, "audit.json", audit)
    _write_new(output, "signing-request.json", request)
    return output


def finalize(repository, candidate_sha, prepared_dir, candidate_manifest_path,
             staged_audit_path, signature_path, public_key_path, trusted_key_sha256,
             observations_path, performance_key=None):
    prepared = Path(prepared_dir)
    if signature_path is None or not Path(signature_path).is_file():
        raise ValueError("detached audit signature is missing")
    if public_key_path is None or not Path(public_key_path).is_file():
        raise ValueError("trusted public key is missing")
    if not SHA64.fullmatch(str(trusted_key_sha256)):
        raise ValueError("trusted public key fingerprint is invalid")
    request = _load(prepared / "signing-request.json")
    audit_path = prepared / "audit.json"
    map_path = prepared / "archive-map.json"
    if (request.get("candidate_sha") != candidate_sha
            or request.get("candidate_manifest_bytes_sha256") != _sha(candidate_manifest_path)
            or request.get("staged_audit_bytes_sha256") != _sha(staged_audit_path)):
        raise ValueError("candidate or staged audit bytes changed after signing request")
    if request.get("audit_sha256") != _sha(audit_path):
        raise ValueError("audit bytes changed after signing request")
    if request.get("archive_map_sha256") != _sha(map_path):
        raise ValueError("archive map bytes changed after signing request")
    audit = independent_adapter._signed_audit(
        audit_path, signature_path, public_key_path, trusted_key_sha256)
    if canonical_json(audit) != audit_path.read_bytes():
        raise ValueError("signed audit bytes are not canonical")
    if (audit.get("candidate_manifest_bytes_sha256") != _sha(candidate_manifest_path)
            or audit.get("staged_audit_bytes_sha256") != _sha(staged_audit_path)
            or request.get("candidate_manifest_bytes_sha256")
            != audit.get("candidate_manifest_bytes_sha256")
            or request.get("staged_audit_bytes_sha256")
            != audit.get("staged_audit_bytes_sha256")):
        raise ValueError("signed candidate or staged input bytes differ")
    if (audit.get("archive_map_sha256") != _sha(map_path)
            or audit.get("candidate_sha") != candidate_sha
            or audit.get("trusted_audit_key_sha256") != trusted_key_sha256
            or request.get("trusted_audit_key_sha256") != trusted_key_sha256
            or audit.get("observations_sha256") != request.get("observations_bytes_sha256")):
        raise ValueError("signed audit differs from signing request")
    if observations_path is None or _sha(observations_path) != audit["observations_sha256"]:
        raise ValueError("independent observation bytes changed")
    if audit.get("performance_key_sha256") != (_sha(performance_key) if performance_key else None):
        raise ValueError("performance key bytes changed")
    mapped = _load(map_path)
    for lane_id, entries in audit["archive_snapshots"].items():
        for gate, recorded in entries.items():
            if (mapped["lanes"][lane_id].get(gate) != recorded["path"]
                    or _snapshot(recorded["path"]) != recorded):
                raise ValueError(f"archive bytes or timestamps changed: {lane_id} {gate}")
    result = independent_adapter.assemble_lanes(
        repository, candidate_sha, map_path, audit_path, signature_path,
        public_key_path, trusted_key_sha256, candidate_manifest_path,
        staged_audit_path, performance_key=performance_key)
    for lane_id, entries in audit["archive_snapshots"].items():
        for gate, recorded in entries.items():
            if _snapshot(recorded["path"]) != recorded:
                raise ValueError(
                    f"archive bytes or timestamps changed after public assembly: {lane_id} {gate}")
    for lane_id, expected in audit["preflight_results"].items():
        if result["independent_gates"][lane_id]["result_sha256"] != expected["result_sha256"]:
            raise ValueError(f"public verifier output changed after audit: {lane_id}")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("prepare", "finalize"):
        command = sub.add_parser(action)
        command.add_argument("--repository", type=Path, required=True)
        command.add_argument("--candidate-sha", required=True)
        command.add_argument("--candidate-manifest", type=Path, required=True)
        command.add_argument("--staged-audit", type=Path, required=True)
        command.add_argument("--performance-key", type=Path)
        if action == "prepare":
            command.add_argument("--observations", type=Path, required=True)
            command.add_argument("--output-dir", type=Path, required=True)
            command.add_argument("--trusted-key-sha256", required=True)
        else:
            command.add_argument("--prepared-dir", type=Path, required=True)
            command.add_argument("--observations", type=Path, required=True)
            command.add_argument("--signature", type=Path, required=True)
            command.add_argument("--trusted-public-key", type=Path, required=True)
            command.add_argument("--trusted-key-sha256", required=True)
            command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "prepare":
            output = prepare(args.repository, args.candidate_sha, args.candidate_manifest,
                             args.staged_audit, args.observations, args.output_dir,
                             args.trusted_key_sha256, args.performance_key)
            print(output / "signing-request.json")
        else:
            result = finalize(args.repository, args.candidate_sha, args.prepared_dir,
                              args.candidate_manifest, args.staged_audit, args.signature,
                              args.trusted_public_key, args.trusted_key_sha256,
                              args.observations, args.performance_key)
            Path(args.output).write_bytes(canonical_json(result))
            print(json.dumps(result["counts"], sort_keys=True))
            return 0 if result["status"] == "PASSED" else 1
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
