import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

import full_suite_manifest


SHA256 = re.compile(r"[0-9a-f]{64}\Z")
ED25519_DER_PREFIX = bytes.fromhex("302a300506032b6570032100")


def _strict_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _decode(raw):
    return json.loads(raw, object_pairs_hook=_strict_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(
                          ValueError(f"non-finite JSON value: {value}")))


def _load(path):
    return _decode(Path(path).read_bytes())


def _signed_audit(path, signature, public_key, key_sha256):
    if not SHA256.fullmatch(str(key_sha256)):
        raise ValueError("trusted audit key SHA-256 is missing")
    if not all(Path(item).is_file() for item in (path, signature, public_key)):
        raise ValueError("signed audit, signature, or trusted public key is missing")
    audit_bytes = Path(path).read_bytes()
    signature_bytes = Path(signature).read_bytes()
    public_bytes = Path(public_key).read_bytes()
    with tempfile.TemporaryDirectory(prefix="dyn4k-signed-audit-") as temporary:
        stable_audit = Path(temporary) / "audit.json"
        stable_signature = Path(temporary) / "audit.sig"
        stable_public = Path(temporary) / "public.pem"
        stable_audit.write_bytes(audit_bytes)
        stable_signature.write_bytes(signature_bytes)
        stable_public.write_bytes(public_bytes)
        key = subprocess.run(["openssl", "pkey", "-pubin", "-in", str(stable_public),
                              "-outform", "DER"], capture_output=True, check=False)
        if (key.returncode or len(key.stdout) != 44
                or not key.stdout.startswith(ED25519_DER_PREFIX)
                or hashlib.sha256(key.stdout).hexdigest() != key_sha256):
            raise ValueError("trusted audit public key differs from pinned fingerprint")
        verified = subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin",
                                   "-inkey", str(stable_public), "-sigfile", str(stable_signature),
                                   "-rawin", "-in", str(stable_audit)], capture_output=True,
                                  check=False)
    if verified.returncode:
        raise ValueError("independent audit signature is unverified")
    return _decode(audit_bytes)


def verify_lanes(repository, candidate_sha, suite_manifest, archive_map_path,
                 audit_path, signature_path, public_key_path, key_sha256,
                 performance_key=None, candidate_manifest=None, artifact_audit=None):
    import independent_gates
    import qualify

    repository = Path(repository)
    supplied = _load(archive_map_path)
    audit = _signed_audit(audit_path, signature_path, public_key_path, key_sha256)
    suite_sha256 = independent_gates.digest(suite_manifest)
    if (not isinstance(supplied, dict) or set(supplied) != {"schema", "candidate_sha", "lanes"}
            or supplied.get("schema") != 1
            or supplied.get("candidate_sha") != candidate_sha
            or not isinstance(supplied.get("lanes"), dict)):
        raise ValueError("independent archive map is invalid or belongs to another candidate")
    if (not isinstance(audit, dict) or audit.get("schema") != 1
            or audit.get("candidate_sha") != candidate_sha
            or audit.get("suite_manifest_sha256") != suite_sha256
            or not isinstance(audit.get("lanes"), dict)
            or set(audit["lanes"]) != set(supplied["lanes"])):
        raise ValueError("signed independent audit differs from selected candidate lanes")
    if suite_sha256 != independent_gates.APPROVED_MANIFEST_SHA256:
        raise ValueError("independent verifier and complete suite disagree")
    identities_bound = candidate_manifest is not None and artifact_audit is not None
    if identities_bound:
        if (not isinstance(candidate_manifest, dict)
                or not isinstance(artifact_audit, dict)
                or candidate_manifest.get("candidate_sha") != candidate_sha
                or artifact_audit.get("candidate_sha") != candidate_sha
                or artifact_audit.get("status") != "PASSED"
                or candidate_manifest.get("suite_manifest_sha256") != suite_sha256
                or candidate_manifest.get("audit_manifest_sha256")
                != qualify.manifest_digest(artifact_audit)
                or audit.get("candidate_manifest_sha256")
                != qualify.manifest_digest(candidate_manifest)
                or audit.get("staged_audit_sha256")
                != qualify.manifest_digest(artifact_audit)):
            raise ValueError("signed audit differs from verified candidate and staged audit")
        qualify.verify_audit_against_staging(artifact_audit, repository)
        audited_targets = qualify.target_binary_hashes(artifact_audit.get("artifacts", []))
        if not isinstance(candidate_manifest.get("lanes"), dict):
            raise ValueError("candidate manifest lanes are missing")
    all_hashes = audit.get("expected_all_target_hashes")
    if all_hashes is not None:
        targets = {row["target"] for row in qualify.matrix()}
        if (not isinstance(all_hashes, dict) or set(all_hashes) != targets
                or any(not isinstance(hashes, dict)
                       or set(hashes) != set(qualify.MODULES)
                       or any(not SHA256.fullmatch(str(value))
                              for value in hashes.values())
                       for hashes in all_hashes.values())):
            raise ValueError("signed 21-target artifact hash map is incomplete")
        if identities_bound and all_hashes != audited_targets:
            raise ValueError("signed 21-target artifact hashes differ from staged audit")
    results = {}
    for lane_id, paths in supplied["lanes"].items():
        selected = full_suite_manifest.select_lane(suite_manifest, lane_id, repository)
        if not isinstance(paths, dict) or not all(isinstance(path, str) and path
                                                   for path in paths.values()):
            raise ValueError(f"independent archive paths are invalid: {lane_id}")
        expected = audit["lanes"][lane_id]
        if not isinstance(expected, dict):
            raise ValueError(f"signed lane audit is invalid: {lane_id}")
        gate_names = set(selected["required_gates"] + selected["global_gates"])
        if identities_bound:
            lane = candidate_manifest["lanes"].get(lane_id)
            target = suite_manifest["lanes"][lane_id]["target"]
            hashes = expected.get("expected_artifact_hashes")
            runtime = expected.get("expected_runtime_identity")
            if (not isinstance(lane, dict)
                    or hashes != audited_targets.get(target)
                    or hashes != lane.get("artifact_hashes")
                    or not isinstance(runtime, str) or not runtime
                    or runtime != lane.get("runtime_identity")):
                raise ValueError(f"signed target artifacts or runtime differ from staging: {lane_id}")
            scopes = expected.get("expected_producer_scopes", {})
            if not isinstance(scopes, dict):
                raise ValueError(f"signed producer scopes are invalid: {lane_id}")
            for gate, scope in scopes.items():
                if gate not in gate_names:
                    raise ValueError(f"signed producer scope has unknown gate: {gate}")
                if not isinstance(scope, dict):
                    raise ValueError(f"signed producer scope is invalid: {gate}")
                if scope.get("target") == "jvm":
                    producing = scope.get("artifact_hashes")
                    audited_jvm = audited_targets.get("jvm", {})
                    if (not isinstance(producing, dict)
                            or any(audited_jvm.get(module) != value
                                   for module, value in producing.items())):
                        raise ValueError(f"signed JVM producer artifacts differ from staging: {gate}")
        digests = expected.get("expected_archive_digests")
        if (not isinstance(digests, dict) or set(paths) - gate_names
                or set(digests) - gate_names
                or any(not SHA256.fullmatch(str(value)) for value in digests.values())):
            raise ValueError(f"signed archive expectations are invalid: {lane_id}")
        result = independent_gates.evaluate(
            suite_manifest, candidate_sha, lane_id,
            {gate: Path(path) for gate, path in paths.items()}, repository,
            expected.get("expected_artifact_hashes"),
            expected.get("expected_runtime_identity"), digests, all_hashes,
            expected.get("expected_producer_scopes"), performance_key)
        if (result.get("result_sha256") != independent_gates.digest(
                {key: value for key, value in result.items() if key != "result_sha256"})
                or set(result.get("gates", {})) != gate_names
                or result.get("lane") != lane_id
                or result.get("candidate_sha") != candidate_sha):
            raise ValueError(f"independent verifier result is incomplete: {lane_id}")
        results[lane_id] = {"verification": result,
                            "selected_case_ids": selected["case_ids"],
                            "identities_bound": identities_bound}
    _check_global_consistency(results, suite_manifest)
    return results


def _check_global_consistency(verified, suite_manifest):
    passing = {lane: item["verification"] for lane, item in verified.items()
               if item["verification"]["status"] == "PASSED"}
    if len(passing) < 2:
        return
    for gate in suite_manifest["global_gates"]:
        identities = set()
        for result in passing.values():
            gate_result = result["gates"][gate]
            scope = result.get("expected_producer_scopes") or {}
            archive = gate_result.get("archive_sha256")
            expected = result.get("expected_archive_digests", {}).get(gate)
            if (gate_result.get("status") != "PASSED"
                    or not SHA256.fullmatch(str(archive))
                    or not SHA256.fullmatch(str(expected))):
                identities.add(("UNBOUND",))
                continue
            identities.add((gate_result["status"], archive, expected,
                            json.dumps(scope.get(gate), sort_keys=True, allow_nan=False)))
        if len(identities) != 1 or ("UNBOUND",) in identities:
            for lane in passing:
                verified[lane]["global_consistency_error"] = (
                    f"independent global gate differs across lanes: {gate}")


def apply(results, evidence, verified, evaluate_lane=None):
    for result in results:
        lane_id = result["id"]
        independent = verified.get(lane_id)
        if independent is None:
            if result["status"] == "PASSED":
                result.update(status="FAILED", reason="independent raw gate archives are missing")
            elif result["status"] == "UNAVAILABLE":
                result["availability_audit_status"] = "UNVERIFIED"
                result["reason"] = "unaudited availability report: " + result["reason"]
            continue
        gate_result = independent["verification"]
        result["independent_gate_result_sha256"] = gate_result["result_sha256"]
        gate_status = gate_result["status"]
        if independent.get("global_consistency_error"):
            result.update(status="FAILED", reason=independent["global_consistency_error"])
            continue
        if gate_status == "PASSED":
            if independent.get("identities_bound") is not True:
                result.update(status="FAILED", reason="signed candidate and staged identities are unbound")
                continue
            selected = independent["selected_case_ids"]
            lane_evidence = evidence.get(lane_id)
            observed = (lane_evidence.get("case_results")
                        if isinstance(lane_evidence, dict) else None)
            identities = ([item.get("id") for item in observed]
                          if isinstance(observed, list)
                          and all(isinstance(item, dict) for item in observed) else [])
            consumer = gate_result["gates"].get("staged-consumer", {})
            receipt_hashes = gate_result.get("expected_archive_digests")
            claimed = (lane_evidence.get("gate_results")
                       if isinstance(lane_evidence, dict) else None)
            if (not isinstance(receipt_hashes, dict)
                    or set(receipt_hashes) != set(gate_result["gates"])
                    or any(not isinstance(item, dict)
                           or item.get("status") != "PASSED"
                           for item in gate_result["gates"].values())):
                result.update(status="FAILED", reason="signed gate receipts are incomplete")
                continue
            trusted = {gate: {"status": "PASSED", "receipt_sha256": digest}
                       for gate, digest in receipt_hashes.items()}
            if claimed is not None and claimed != trusted:
                result.update(status="FAILED", reason="self-reported gate hashes differ from signed audit")
                continue
            if evaluate_lane is not None and isinstance(lane_evidence, dict):
                result.update(evaluate_lane(lane_id, {**lane_evidence,
                                                      "gate_results": trusted}))
            elif claimed is None:
                result.update(status="FAILED", reason="complete lane evidence is missing")
                continue
            if (consumer.get("complete_selected_suite") is not True
                    or not isinstance(observed, list)
                    or not all(isinstance(identity, str) for identity in identities)
                    or len(identities) != len(selected)
                    or len(set(identities)) != len(identities)
                    or set(identities) != set(selected)
                    or any(item.get("status") != "PASSED" for item in observed)):
                result.update(status="FAILED", reason="raw complete selected suite differs")
            elif result["status"] == "PASSED":
                result["reason"] = "complete selected suite and signed raw gate archives verified"
            continue
        if gate_status not in ("FAILED", "NOT_RUN", "UNAVAILABLE"):
            raise ValueError(f"independent gate status is invalid: {lane_id}")
        if gate_status == "UNAVAILABLE":
            observations = [gate for gate in gate_result.get("gates", {}).values()
                            if isinstance(gate, dict) and gate.get("status") == "UNAVAILABLE"
                            and SHA256.fullmatch(str(gate.get("observation_sha256", "")))]
            if not observations:
                result.update(status="FAILED", reason="independent unavailability lacks bound observation")
                continue
        if result["status"] != "FAILED":
            result.update(status=gate_status,
                          reason=f"independent raw gate verification: {gate_status}")
            if gate_status == "UNAVAILABLE":
                result["availability_audit_status"] = "VERIFIED"
    return results
