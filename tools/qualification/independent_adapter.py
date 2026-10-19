import argparse
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


def _verify_full_jvm_staged_consumer(repository, candidate_sha, lane_id, selected,
                                     paths, expected, gate_result):
    import full_jvm_consumer

    if lane_id not in full_jvm_consumer.LANES:
        raise ValueError(f"public full JVM verifier does not cover lane: {lane_id}")
    java_hash = expected.get("expected_java_executable_sha256")
    gradle_hash = expected.get("expected_gradle_executable_sha256")
    runtime_java_hash = expected.get("expected_runtime_java_executable_sha256")
    publication_path = expected.get("expected_mode_publication_path")
    publication_digest = expected.get("expected_mode_publication_digest")
    if (type(java_hash) is not str or not SHA256.fullmatch(java_hash)
            or type(gradle_hash) is not str or not SHA256.fullmatch(gradle_hash)
            or type(runtime_java_hash) is not str or not SHA256.fullmatch(runtime_java_hash)):
        raise ValueError(f"signed JVM executable SHA-256 values are missing or invalid: {lane_id}")
    if (type(publication_path) is not str or not Path(publication_path).is_absolute()
            or type(publication_digest) is not str
            or not SHA256.fullmatch(publication_digest)):
        raise ValueError(f"signed JVM mode publication is missing or invalid: {lane_id}")
    hashes = expected.get("expected_artifact_hashes")
    runtime = expected.get("expected_runtime_identity")
    digest = expected["expected_archive_digests"].get("staged-consumer")
    if (not isinstance(hashes, dict) or set(hashes) != {"dyn4k-core", "dyn4k"}
            or any(type(value) is not str or not SHA256.fullmatch(value)
                   for value in hashes.values())
            or type(runtime) is not str or not runtime
            or type(digest) is not str or not SHA256.fullmatch(digest)):
        raise ValueError(f"signed JVM archive identity is incomplete: {lane_id}")
    contract = full_jvm_consumer.selected_contract(repository, lane_id)[1]
    if selected["case_ids"] != [item["id"] for item in contract["cases"]]:
        raise ValueError(f"signed JVM lane selects a different case suite: {lane_id}")
    public = full_jvm_consumer.verify(
        paths["staged-consumer"], repository, candidate_sha, hashes, runtime, digest,
        java_hash, gradle_hash, runtime_java_hash, lane_id,
        publication_path, publication_digest)
    if public != gate_result:
        raise ValueError(f"public JVM verifier differs from independent gate: {lane_id}")


def verify_lanes(repository, candidate_sha, suite_manifest, archive_map_path,
                 audit_path, signature_path, public_key_path, key_sha256,
                 performance_key=None, candidate_manifest=None, artifact_audit=None):
    import independent_gates
    import full_android_adapter
    import full_jvm_consumer
    import full_klib_adapter
    import full_klib_consumer
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
    all_lanes = (len(suite_manifest["lanes"]) == 112
                 and set(supplied["lanes"]) == set(suite_manifest["lanes"]))
    if all_lanes:
        full_suite_manifest.validate_manifest(suite_manifest, repository)
    results = {}
    for lane_id, paths in supplied["lanes"].items():
        if all_lanes:
            lane_spec = suite_manifest["lanes"][lane_id]
            selected = {
                "case_ids": [case["id"] for case in suite_manifest["cases"]
                             if case["scope"] in lane_spec["case_scopes"]],
                "required_gates": lane_spec["required_gates"],
                "global_gates": suite_manifest["global_gates"],
            }
        else:
            selected = full_suite_manifest.select_lane(suite_manifest, lane_id, repository)
        if not isinstance(paths, dict) or not all(isinstance(path, str) and path
                                                   for path in paths.values()):
            raise ValueError(f"independent archive paths are invalid: {lane_id}")
        expected = audit["lanes"][lane_id]
        if not isinstance(expected, dict):
            raise ValueError(f"signed lane audit is invalid: {lane_id}")
        gate_names = set(selected["required_gates"] + selected["global_gates"])
        target = suite_manifest["lanes"][lane_id]["target"]
        mode_bound = False
        if identities_bound:
            lane = candidate_manifest["lanes"].get(lane_id)
            hashes = expected.get("expected_artifact_hashes")
            runtime = expected.get("expected_runtime_identity")
            if target == "jvm" and lane_id in full_jvm_consumer.LANES:
                binding = lane.get("jvm_mode_publication") if isinstance(lane, dict) else None
                mode_path = expected.get("expected_mode_publication_path")
                mode_digest = expected.get("expected_mode_publication_digest")
                if binding is not None:
                    if (not isinstance(binding, dict)
                            or hashes != lane.get("artifact_hashes")
                            or hashes != binding.get("artifact_hashes")
                            or mode_path != binding.get("publication_archive")
                            or mode_digest != binding.get("archive_digest")):
                        raise ValueError(f"signed JVM mode publication differs from candidate lane: {lane_id}")
                    case = {"id": lane_id, "target": target,
                            "configuration": suite_manifest["lanes"][lane_id]["configuration"]}
                    if qualify.verify_jvm_mode_publication(
                            binding, case, candidate_sha, hashes) is not True:
                        raise ValueError(f"JVM mode publication is unverified: {lane_id}")
                    mode_bound = True
                elif hashes != audited_targets.get(target):
                    raise ValueError(f"signed target artifacts require candidate mode publication: {lane_id}")
            if (not isinstance(lane, dict)
                    or (target != "jvm" and hashes != audited_targets.get(target))
                    or (target != "jvm" and hashes != lane.get("artifact_hashes"))
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
        consumer_gate = result["gates"]["staged-consumer"]
        if (suite_manifest["lanes"][lane_id]["target"] == "jvm"
                and consumer_gate["status"] == "PASSED"):
            if not identities_bound or not mode_bound:
                raise ValueError(f"signed JVM candidate mode publication is unbound: {lane_id}")
            _verify_full_jvm_staged_consumer(
                repository, candidate_sha, lane_id, selected, paths, expected,
                consumer_gate)
        if (lane_id in full_klib_consumer.LOCAL_LANES
                or lane_id in full_android_adapter.ROUTES) and consumer_gate["status"] == "PASSED":
            if not identities_bound:
                raise ValueError(f"signed candidate and staged identities are unbound: {lane_id}")
            if lane_id in full_klib_consumer.LOCAL_LANES:
                full_klib_adapter.verify_staged_consumer(
                    repository, candidate_sha, lane_id, selected["case_ids"],
                    paths["staged-consumer"], consumer_gate, expected,
                    audited_targets.get(suite_manifest["lanes"][lane_id]["target"]))
            else:
                full_android_adapter.verify_full_android_staged_consumer(
                    repository, candidate_sha, lane_id, selected,
                    paths["staged-consumer"], expected, consumer_gate)
        results[lane_id] = {"verification": result,
                            "selected_case_ids": selected["case_ids"],
                            "identities_bound": identities_bound and (target != "jvm" or mode_bound)}
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


def assemble_lanes(repository, candidate_sha, archive_map_path=None, audit_path=None,
                   signature_path=None, public_key_path=None, key_sha256=None,
                   candidate_manifest_path=None, staged_audit_path=None,
                   evidence_path=None, performance_key=None):
    import independent_gates
    import qualify

    repository = Path(repository)
    manifest = independent_gates.load_approved_manifest(repository)
    lane_ids = set(manifest["lanes"])
    if len(lane_ids) != 112:
        raise ValueError("assembly requires all 112 approved lanes")
    signed_inputs = (audit_path, signature_path, public_key_path, key_sha256,
                     candidate_manifest_path, staged_audit_path)
    archive_map_sha256 = None
    signed_audit_sha256 = None
    if archive_map_path is None:
        if any(item is not None for item in signed_inputs) or evidence_path or performance_key:
            raise ValueError("signed audit inputs require an archive map")
        raw = independent_gates.evaluate_assembly(
            manifest, candidate_sha,
            {lane_id: {"archives": {}} for lane_id in manifest["lanes"]}, repository)
        verified = {}
        gate_results = raw["lane_results"]
        selected_cases = raw["selected_cases"]
        evidence = {}
        candidate_manifest = None
        staged_audit = None
    else:
        archive_map_bytes = Path(archive_map_path).read_bytes()
        supplied = _decode(archive_map_bytes)
        if (not isinstance(supplied, dict) or set(supplied) != {"schema", "candidate_sha", "lanes"}
                or supplied.get("schema") != 1 or supplied.get("candidate_sha") != candidate_sha
                or not isinstance(supplied.get("lanes"), dict)
                or set(supplied["lanes"]) != lane_ids):
            raise ValueError("archive map must name all 112 approved lanes for the exact candidate")
        if any(item is None for item in signed_inputs):
            raise ValueError("archive map requires signed audit, pinned key, candidate manifest, and staged audit")
        qualify.require_clean_checkout(repository, candidate_sha)
        candidate_manifest = _load(candidate_manifest_path)
        staged_audit = _load(staged_audit_path)
        evidence = _load(evidence_path) if evidence_path else {}
        if not isinstance(evidence, dict) or set(evidence) - lane_ids:
            raise ValueError("qualification evidence has unknown lane IDs")
        archive_map_sha256 = hashlib.sha256(archive_map_bytes).hexdigest()
        with tempfile.TemporaryDirectory(prefix="dyn4k-assembly-inputs-") as temporary:
            stable = {}
            for name, source in (("archive-map.json", archive_map_path),
                                 ("audit.json", audit_path),
                                 ("audit.sig", signature_path),
                                 ("trusted.pem", public_key_path),
                                 ("performance.key", performance_key)):
                if source is not None:
                    target = Path(temporary) / name
                    target.write_bytes(archive_map_bytes if name == "archive-map.json"
                                       else Path(source).read_bytes())
                    stable[name] = target
            signed_audit_sha256 = hashlib.sha256(stable["audit.json"].read_bytes()).hexdigest()
            verified = verify_lanes(
                repository, candidate_sha, manifest, stable["archive-map.json"],
                stable["audit.json"], stable["audit.sig"], stable["trusted.pem"],
                key_sha256, stable.get("performance.key"),
                candidate_manifest, staged_audit)
        if set(verified) != lane_ids:
            raise ValueError("signed audit did not verify all 112 approved lanes")
        gate_results = {lane_id: item["verification"] for lane_id, item in verified.items()}
        selected_cases = {lane_id: len(item["selected_case_ids"])
                          for lane_id, item in verified.items()}
    cases = {item["id"]: item for item in qualify.expand(qualify.matrix())}
    if set(cases) != lane_ids:
        raise ValueError("qualification matrix differs from the approved 112 lanes")
    if verified:
        rows = [qualify.evaluate(cases[lane_id], evidence.get(lane_id), candidate_sha,
                                 candidate_manifest, manifest, staged_audit)
                for lane_id in manifest["lanes"]]
        apply(rows, evidence, verified,
              lambda lane_id, observed: qualify.evaluate(
                  cases[lane_id], observed, candidate_sha, candidate_manifest,
                  manifest, staged_audit))
    else:
        rows = [{"id": lane_id, "status": gate_results[lane_id]["status"],
                 "reason": "no signed raw gate archives supplied"}
                for lane_id in manifest["lanes"]]
    lanes = {row["id"]: row for row in rows}
    counts = {status: sum(row["status"] == status for row in rows)
              for status in ("PASSED", "FAILED", "UNAVAILABLE", "NOT_RUN")}
    status = next((state for state in ("FAILED", "UNAVAILABLE", "NOT_RUN")
                   if counts[state]), "PASSED")
    assembled = {
        "schema": 1, "kind": "independent-qualified-assembly",
        "candidate_sha": candidate_sha,
        "manifest_sha256": independent_gates.digest(manifest),
        "archive_map_sha256": archive_map_sha256,
        "signed_audit_sha256": signed_audit_sha256,
        "trusted_audit_key_sha256": key_sha256,
        "candidate_manifest_sha256": (qualify.manifest_digest(candidate_manifest)
                                      if candidate_manifest is not None else None),
        "staged_audit_sha256": (qualify.manifest_digest(staged_audit)
                                if staged_audit is not None else None),
        "required_lanes": len(lanes), "selected_cases": selected_cases,
        "lanes": lanes, "independent_gates": gate_results,
        "counts": counts, "status": status,
    }
    assembled["result_sha256"] = independent_gates.digest(assembled)
    return assembled


def main(argv=None):
    parser = argparse.ArgumentParser(description="Assemble all approved qualification lanes")
    sub = parser.add_subparsers(dest="action", required=True)
    assemble = sub.add_parser("assemble")
    assemble.add_argument("--repository", type=Path,
                          default=Path(__file__).resolve().parents[2])
    assemble.add_argument("--candidate-sha", required=True)
    assemble.add_argument("--archive-map", type=Path)
    assemble.add_argument("--signed-audit", type=Path)
    assemble.add_argument("--audit-signature", type=Path)
    assemble.add_argument("--trusted-public-key", type=Path)
    assemble.add_argument("--trusted-key-sha256")
    assemble.add_argument("--candidate-manifest", type=Path)
    assemble.add_argument("--staged-audit", type=Path)
    assemble.add_argument("--evidence", type=Path)
    assemble.add_argument("--performance-key", type=Path)
    assemble.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = assemble_lanes(
            args.repository, args.candidate_sha, args.archive_map,
            args.signed_audit, args.audit_signature, args.trusted_public_key,
            args.trusted_key_sha256, args.candidate_manifest, args.staged_audit,
            args.evidence, args.performance_key)
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
        parser.error(str(error))
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["counts"], sort_keys=True))
    return 0 if result["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
