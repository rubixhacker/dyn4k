#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

import qualify
import artifact


APPROVED_MANIFEST_SHA256 = "60e91e7cab9dcf1c1ccb41eb25fefd6c1579ad147996bb40d94f7fcba91017a3"
APPROVED_MANIFEST_REVISION = "6f983ad3a36bdc549c32f5d0883b0a47b28e1963"
MANIFEST_PATH = "tools/qualification/full-suite-manifest.json"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
LANE_GATES = frozenset(("staged-artifacts", "staged-consumer", "numerical-parity",
                        "physical-correctness", "unchanged-java-corpus",
                        "java-source-compatibility", "duplicate-provider"))
GLOBAL_GATES = frozenset(("migration-journeys", "performance-resource",
                          "publication-contract", "independent-review"))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def load_approved_manifest(repository):
    raw = subprocess.check_output(
        ["git", "-C", str(repository), "show",
         f"{APPROVED_MANIFEST_REVISION}:{MANIFEST_PATH}"], stderr=subprocess.PIPE)
    manifest = json.loads(raw)
    if digest(manifest) != APPROVED_MANIFEST_SHA256:
        raise ValueError("approved complete-suite manifest changed")
    return manifest


def _result(gate, status, reason, **details):
    return {"gate": gate, "status": status, "reason": reason, **details}


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _json(path):
    value = json.loads(path.read_text(), object_pairs_hook=_strict_object,
                       parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)))
    if not qualify.finite_json(value):
        raise ValueError(f"non-finite raw JSON observation: {path}")
    return value


def _file_path(root, relative):
    _file_path_name(relative)
    path = root.joinpath(*relative.split("/"))
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"raw archive file is missing or symbolic: {relative}")
    return path


def _archive_paths(root):
    actual = set()
    for base, directories, filenames in os.walk(root, followlinks=False):
        for name in directories + filenames:
            path = Path(base) / name
            if path.is_symlink():
                raise ValueError(f"symbolic archive path: {path.relative_to(root)}")
            relative = path.relative_to(root).as_posix()
            _file_path_name(relative)
            if path.is_file():
                actual.add(relative)
            elif not path.is_dir():
                raise ValueError(f"nonregular archive path: {relative}")
    return actual


def _file_path_name(relative):
    if (not isinstance(relative, str) or not relative or "\\" in relative
            or "\n" in relative or "\r" in relative
            or any(part in ("", ".", "..") for part in relative.split("/"))
            or ":" in relative.split("/")[0]):
        raise ValueError(f"unsafe archive path: {relative}")


def _inventory(root, receipt):
    files = receipt.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("raw file inventory is missing")
    process = receipt.get("process")
    if not isinstance(process, dict):
        raise ValueError("raw process receipt is missing")
    started, finished = process.get("started_ns"), process.get("finished_ns")
    if (type(started) is not int or type(finished) is not int
            or started <= 0 or finished < started):
        raise ValueError("raw process execution window is invalid")
    seen = set()
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("raw file inventory entry is invalid")
        relative = item.get("path")
        path = _file_path(root, relative)
        if relative in seen:
            raise ValueError(f"duplicate archive path: {relative}")
        seen.add(relative)
        if (not SHA64.fullmatch(str(item.get("sha256", "")))
                or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]):
            raise ValueError(f"raw file hash differs: {relative}")
        mtime = item.get("mtime_ns")
        if type(mtime) is not int or not started <= mtime <= finished:
            raise ValueError(f"raw file timestamp differs from execution: {relative}")
    actual = _archive_paths(root)
    if actual != seen | {"receipt.json"}:
        raise ValueError("archive has unlisted, missing, or duplicate files")
    return digest({"receipt": receipt, "files": sorted(files, key=lambda item: item["path"])})


def _binding(root, receipt, candidate_sha, lane_id, lane, repository,
             expected_artifact_hashes, expected_runtime_identity, gate):
    if receipt.get("schema") != 1 or receipt.get("candidate_sha") != candidate_sha:
        raise ValueError("raw candidate SHA differs")
    source_tree = subprocess.check_output(
        ["git", "-C", str(repository), "rev-parse", f"{candidate_sha}^{{tree}}"],
        text=True, stderr=subprocess.PIPE).strip()
    if receipt.get("source_tree") != source_tree:
        raise ValueError("raw Git source tree differs from exact candidate")
    if gate not in GLOBAL_GATES or receipt.get("lane") is not None:
        if receipt.get("lane") != lane_id:
            raise ValueError("raw lane differs")
        for key in ("target", "runtime", "version", "configuration"):
            if receipt.get(key) != lane.get(key):
                raise ValueError(f"raw {key} differs from selected lane")
        if (not isinstance(expected_runtime_identity, str) or not expected_runtime_identity
                or receipt.get("runtime_identity") != expected_runtime_identity):
            raise ValueError("raw runtime identity differs from independent selection")
    if (not isinstance(expected_artifact_hashes, dict)
            or set(expected_artifact_hashes) != set(qualify.MODULES)
            or any(not SHA64.fullmatch(str(value)) for value in expected_artifact_hashes.values())):
        raise ValueError("independently audited target binary hashes are missing")
    if receipt.get("artifact_hashes") != expected_artifact_hashes:
        raise ValueError("raw artifact hashes differ from independent staging audit")
    process = receipt.get("process")
    if (not isinstance(process, dict) or not isinstance(process.get("command"), list)
            or not process["command"] or not all(isinstance(arg, str) and arg for arg in process["command"])
            or type(process.get("exit_code")) is not int):
        raise ValueError("raw command or exit code is missing")
    for key in ("stdout", "stderr"):
        if key in process:
            _file_path(root, process[key])
    return process


def _duplicate_provider(root, receipt, process):
    graph_path = _file_path(root, receipt.get("provider_graph"))
    graph = graph_path.read_text()
    try:
        qualify.check_providers(graph)
    except ValueError as error:
        if ("duplicate org.dyn4j provider" not in str(error)
                or process["exit_code"] == 0
                or "stderr" not in process
                or "duplicate org.dyn4j provider" not in
                _file_path(root, process["stderr"]).read_text()):
            raise ValueError("duplicate provider diagnostic or failure is absent") from error
    else:
        raise ValueError("both provider coordinates are absent from raw graph")
    return "raw provider graph and failing diagnostic agree"


def _external_unavailable(receipt, candidate_sha, lane_id, gate):
    reason = receipt.get("reason")
    if (receipt.get("schema") != 1 or receipt.get("candidate_sha") != candidate_sha
            or (gate not in GLOBAL_GATES and receipt.get("lane") != lane_id)
            or not isinstance(reason, str) or not reason.strip()
            or not isinstance(receipt.get("observed_by"), str) or not receipt["observed_by"]
            or type(receipt.get("observed_at_ns")) is not int
            or receipt["observed_at_ns"] <= 0):
        raise ValueError("external unavailability observation is incomplete or misbound")
    return _result(gate, "UNAVAILABLE", reason,
                   observation_sha256=digest(receipt))


def _staged_publication(root, candidate_sha, lane, expected_artifact_hashes,
                        repository):
    staging = root / "staged"
    if not staging.is_dir() or staging.is_symlink():
        raise ValueError("full staged repository is missing")
    audit = qualify.audit_staging(staging, candidate_sha)
    if audit["status"] != "PASSED":
        raise ValueError("full staged publication audit failed: " + "; ".join(audit["errors"][:4]))
    license_bytes = subprocess.check_output(
        ["git", "-C", str(repository), "show", f"{candidate_sha}:LICENSE.md"],
        stderr=subprocess.PIPE)
    for item in audit["artifacts"]:
        path = staging / item["path"]
        if "license" in path.name.lower() and path.suffix == ".md":
            if path.read_bytes() != license_bytes:
                raise ValueError(f"staged license differs from exact candidate: {item['path']}")
        elif path.suffix == ".jar" and "sources" not in path.name and "javadoc" not in path.name:
            with zipfile.ZipFile(path) as package:
                if package.read("META-INF/LICENSE.md") != license_bytes:
                    raise ValueError(f"embedded license differs from exact candidate: {item['path']}")
    for module in qualify.MODULES:
        binary = staging / qualify.target_binary_path(module, lane["target"])
        if not binary.is_file() or binary.is_symlink():
            raise ValueError(f"staged target binary is missing: {module}")
        if qualify.digest(binary) != expected_artifact_hashes[module]:
            raise ValueError(f"staged target binary differs from independent audit: {module}")
    return f"full staged audit verified {len(audit['artifacts'])} publication files"


def _migration_journeys(root, candidate_sha, expected_artifact_hashes):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "migration"))
    try:
        import journeys
        report = journeys.verify_evidence(root / "evidence")
    finally:
        sys.path.pop(0)
    if (report.get("candidate_commit") != candidate_sha or
            report.get("source_revision") != journeys.SAMPLE_REVISION or
            report.get("source_manifest_sha256") != journeys.SOURCE_MANIFEST_SHA256 or
            report.get("expected_cases") != 10 or report.get("passed_cases") != 10 or
            report.get("failed_cases") != 0 or report.get("unavailable_cases") != 0):
        raise ValueError("migration source, candidate, or ten journey counts differ")
    cases = report.get("cases")
    if (not isinstance(cases, list) or len(cases) != 10 or
            {(case.get("provider"), case.get("scene")) for case in cases}
            != {(provider, scene) for provider in journeys.PROVIDERS
                for scene in journeys.SCENES} or
            any(case.get("status") != "PASSED" for case in cases)):
        raise ValueError("migration journey identities or outcomes differ")
    for provider in journeys.PROVIDERS:
        compiled = _json(root / "evidence" / provider / "compile" / "compile.json")
        if (compiled.get("status") != "PASSED" or compiled.get("exit_code") != 0
                or compiled.get("source_count") != 42
                or not isinstance(compiled.get("command"), list)
                or not (root / "evidence" / provider / "compile" / "javac.log").is_file()):
            raise ValueError(f"{provider} unchanged Java compilation lacks raw success evidence")
    for case in cases:
        for mode in ("plain", "observed"):
            observation = case.get(mode)
            if (not isinstance(observation, dict) or observation.get("status") != "PASSED"
                    or observation.get("exit_code") != 0):
                raise ValueError(f"{case['provider']} {case['scene']} {mode} did not execute")
            directory = root / "evidence" / case["provider"] / case["scene"] / mode
            invocation = _json(directory / "invocation.json")
            if (not isinstance(invocation.get("command"), list)
                    or not (directory / "container.log").is_file()):
                raise ValueError(f"{case['scene']} {mode} raw container invocation is missing")
            validation_name = "plain-validation.json" if mode == "plain" else "validation.json"
            validation = _json(directory / "evidence" / case["scene"] / validation_name)
            if validation != observation.get("validation"):
                raise ValueError(f"{case['scene']} {mode} raw validation differs from summary")
            if (validation.get("failed", validation.get("failed_checks")) != 0
                    or validation.get("unexecuted", validation.get("unexecuted_checks")) != 0
                    or validation.get("executed", validation.get("executed_checks", 0)) <= 0):
                raise ValueError(f"{case['scene']} {mode} raw validation has incomplete checks")
    candidate_jar = root / "evidence" / "resolved" / journeys.CANDIDATE_JAR
    if (not candidate_jar.is_file() or candidate_jar.is_symlink() or
            qualify.digest(candidate_jar) != expected_artifact_hashes["dyn4k-core"]):
        raise ValueError("migration candidate JAR differs from audited staged artifact")
    return "ten pinned migration journeys and raw evidence verified"


def _independent_review(root, candidate_sha, repository):
    reports = []
    sessions = set()
    for kind in ("standards", "spec"):
        report = _json(_file_path(root, f"{kind}.json"))
        session_path = _file_path(root, f"{kind}.jsonl")
        if (report.get("review_kind") != kind or report.get("candidate_sha") != candidate_sha
                or report.get("model") != "gpt-6-sol"):
            raise ValueError(f"{kind} review identity differs from final candidate")
        raw_session = session_path.read_text()
        messages = [json.loads(line, object_pairs_hook=_strict_object)
                    for line in raw_session.splitlines() if line]
        turn_models = {item.get("payload", {}).get("model") for item in messages
                       if item.get("type") == "turn_context"}
        session_ids = {item.get("payload", {}).get("id") for item in messages
                       if item.get("type") == "session_meta"}
        if (turn_models != {"gpt-6-sol"} or len(session_ids) != 1
                or candidate_sha not in raw_session or kind not in raw_session
                or not any(item.get("type") == "response_item" for item in messages)):
            raise ValueError(f"{kind} raw session does not prove one Sol review")
        session_id = next(iter(session_ids))
        if report.get("session_id") != session_id or session_id in sessions:
            raise ValueError("independent reviews repeat or misstate session identity")
        sessions.add(session_id)
        findings = report.get("findings")
        if not isinstance(findings, list):
            raise ValueError(f"{kind} actionable findings are missing")
        ids = [finding.get("id") for finding in findings if isinstance(finding, dict)]
        if len(ids) != len(findings) or len(set(ids)) != len(ids):
            raise ValueError(f"{kind} finding identities are invalid")
        for finding in findings:
            resolution = finding.get("resolution")
            if (not isinstance(resolution, dict)
                    or resolution.get("status") != "RESOLVED"
                    or resolution.get("candidate_sha") != candidate_sha
                    or not isinstance(resolution.get("evidence"), str)
                    or not resolution["evidence"].strip()):
                raise ValueError(f"{kind} actionable finding is unresolved")
            evidence = resolution["evidence"]
            _file_path_name(evidence)
            committed = subprocess.run(
                ["git", "-C", str(repository),
                 "cat-file", "-e", f"{candidate_sha}:{evidence}"],
                capture_output=True, check=False)
            if committed.returncode:
                raise ValueError(f"{kind} resolution evidence is absent from final head")
        reports.append(report)
    return f"{len(reports)} distinct Sol reviews verified against final head"


def _bounded_bundle(root, candidate_sha, lane, expected_artifact_hashes, repository):
    manifest = json.loads(subprocess.check_output(
        ["git", "-C", str(repository), "show",
         f"{candidate_sha}:tools/qualification/foundation-probes.json"],
        stderr=subprocess.PIPE))
    summary = artifact.verify_bundle(root, manifest, candidate_sha)
    route = summary["route"]
    target = "js" if route == "jsSafari" else route
    hashes = summary["artifact_hashes"]
    observed = hashes.get(target) if route == "ubuntu-host" else hashes
    if target != lane["target"] and route != "ubuntu-host":
        raise ValueError("bounded archive target differs from selected lane")
    if route == "ubuntu-host":
        observed = hashes.get(lane["target"])
    if observed != expected_artifact_hashes:
        raise ValueError("bounded archive artifacts differ from independent audit")
    return summary


def _staged_consumer(root, receipt, candidate_sha, lane, expected_artifact_hashes,
                     repository, process):
    target = lane["target"]
    if target in ("js", "wasmJs", "wasmWasi"):
        suffix = {"js": "jsNode", "wasmJs": "wasmJsNode",
                  "wasmWasi": "wasmWasiNode"}[target]
        if lane["runtime"] != "Node.js":
            raise ValueError("no frozen staged consumer group for selected browser or WASI runtime")
    elif target == "android":
        raise ValueError("Android host consumer does not establish Android device execution")
    else:
        suffix = target
    group_id = f"consumer-{suffix}"
    manifest = json.loads(subprocess.check_output(
        ["git", "-C", str(repository), "show",
         f"{candidate_sha}:tools/qualification/foundation-probes.json"],
        stderr=subprocess.PIPE))
    group = next((item for item in manifest["groups"] if item["id"] == group_id), None)
    if group is None or receipt.get("consumer_group") != group_id:
        raise ValueError("frozen staged consumer group is absent or misbound")
    task = Path(group["report_pattern"]).parent.name
    if not any(task in arg for arg in process["command"]):
        raise ValueError("raw command does not execute selected consumer task")
    graph = _file_path(root, receipt.get("provider_graph")).read_text()
    providers = set(re.findall(r"io\.github\.rubixhacker:([^:\s]+):", graph))
    expected_providers = {qualify.target_publication_name(module, target)
                          for module in qualify.MODULES}
    if "org.dyn4j:dyn4j" in graph or not expected_providers <= providers:
        raise ValueError("external consumer provider graph is incomplete or duplicated")
    binaries = receipt.get("resolved_artifacts")
    if not isinstance(binaries, dict) or set(binaries) != set(qualify.MODULES):
        raise ValueError("both resolved external consumer binaries are required")
    for module, relative in binaries.items():
        if hashlib.sha256(_file_path(root, relative).read_bytes()).hexdigest() != expected_artifact_hashes[module]:
            raise ValueError(f"resolved external consumer artifact differs: {module}")
    reports = receipt.get("consumer_xml")
    if not isinstance(reports, list) or not reports or len(reports) != len(set(reports)):
        raise ValueError("raw staged consumer XML report paths are missing or duplicate")
    observed = []
    for relative in reports:
        suite = ET.fromstring(_file_path(root, relative).read_bytes())
        if suite.tag != "testsuite":
            raise ValueError("raw staged consumer XML root is not testsuite")
        cases = list(suite.iter("testcase"))
        counts = {name: sum(case.find(element) is not None for case in cases)
                  for name, element in (("failures", "failure"), ("errors", "error"),
                                        ("skipped", "skipped"))}
        counts["tests"] = len(cases)
        if (any(suite.get(name) is None or int(suite.get(name)) != count
                for name, count in counts.items()) or
                any(counts[name] for name in ("failures", "errors", "skipped"))):
            raise ValueError("staged consumer XML counts or outcomes differ")
        if not 0 <= float(suite.get("time", "nan")) < float("inf"):
            raise ValueError("staged consumer XML suite time is invalid")
        for case in cases:
            identity = case.get("classname"), case.get("name")
            if not all(identity) or not 0 <= float(case.get("time", "nan")) < float("inf"):
                raise ValueError("staged consumer XML case identity or time is invalid")
            observed.append(identity)
    expected = set(qualify.expected_probe_cases(manifest, group))
    if len(observed) != len(set(observed)) or set(observed) != expected:
        raise ValueError("staged consumer case identities or counts differ from frozen manifest")
    return f"{len(observed)} raw external consumer cases and both resolved artifacts verified"


def _numerical_entries(root, receipt, candidate_sha, expected_artifact_hashes,
                       physical_only=False):
    numerical_dir = Path(__file__).resolve().parents[1] / "numerical"
    sys.path.insert(0, str(numerical_dir))
    try:
        import compare
        import physical
        catalog = _json(numerical_dir / "fixtures.json")
        selected = {item["key"] for item in catalog["fixtures"]
                    if not physical_only or "physical_phase_ceilings_m" in compare.load_fixture(item["key"])}
        entries = receipt.get("fixtures")
        if not isinstance(entries, list) or {item.get("key") for item in entries
                                             if isinstance(item, dict)} != selected or len(entries) != len(selected):
            raise ValueError("frozen numerical fixture identities or counts differ")
        source_sha = hashlib.sha256(receipt["source_tree"].encode()).hexdigest()
        for item in entries:
            fixture = compare.load_fixture(item["key"])
            reference = _file_path(root, item.get("reference"))
            candidate = _file_path(root, item.get("candidate"))
            capture = _file_path(root, item.get("capture_receipt"))
            result = compare.compare(fixture, reference, candidate, capture,
                                     source_sha, expected_artifact_hashes["dyn4k-core"],
                                     candidate_sha)
            if result["status"] == "UNPASSED":
                raise IncompleteEvidence(
                    f"{item['key']} has unapproved comparison channels: {result['unpassed_channels']}")
            if result["status"] != "PASSED":
                raise ValueError(f"{item['key']} numerical comparison {result['status']}: {result.get('reason', result.get('unpassed_channels'))}")
            if physical_only:
                phases = physical.phases_for_fixture(fixture)
                states = 0
                failed = 0
                phase_index = 0
                for _, row in compare.records(candidate):
                    if row["kind"] != "state":
                        continue
                    while row["step"] > phases[phase_index][2]:
                        phase_index += 1
                    ceiling = fixture["physical_phase_ceilings_m"][phases[phase_index][0]]
                    if physical.depth_for_state(row["state"]) > physical.Fraction(str(ceiling)):
                        failed += 1
                    states += 1
                if states != fixture["counts"]["state"] or failed:
                    raise ValueError(f"{item['key']} physical ceiling failed in {failed} of {states} states")
        return f"{len(entries)} frozen {'physical' if physical_only else 'numerical'} fixture traces verified"
    finally:
        sys.path.pop(0)


class IncompleteEvidence(Exception):
    pass


def _performance_resource(root, candidate_sha):
    performance_dir = Path(__file__).resolve().parents[1] / "performance"
    sys.path.insert(0, str(performance_dir))
    try:
        import verify_candidate_archive
        raw = verify_candidate_archive.audit_raw_archive(root / "evidence")
        identity = _json(root / "evidence" / "candidate-identity-at-pilot.json")
        if identity.get("source_commit") != candidate_sha:
            raise ValueError("performance raw identity differs from exact candidate")
        if raw.get("archive_audit") != "raw_hashes_verified":
            raise ValueError("performance raw archive audit did not verify")
        try:
            qualified = verify_candidate_archive.verify(root / "evidence")
        except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
            raise IncompleteEvidence(f"performance reference environment is unverified: {error}") from error
        if qualified.get("qualification") != "passed":
            raise IncompleteEvidence("performance raw records verified; qualification remains unpassed")
        return "sustained performance archive and reference environment verified"
    finally:
        sys.path.pop(0)


def evaluate(manifest, candidate_sha, lane_id, archives, repository,
             expected_artifact_hashes=None, expected_runtime_identity=None):
    repository = Path(repository)
    if digest(manifest) != APPROVED_MANIFEST_SHA256:
        raise ValueError("manifest differs from independently approved complete suite")
    if not isinstance(candidate_sha, str) or not SHA40.fullmatch(candidate_sha):
        raise ValueError("candidate SHA must be an exact commit")
    actual = subprocess.check_output(
        ["git", "-C", str(repository), "rev-parse", "--verify",
         f"{candidate_sha}^{{commit}}"], text=True, stderr=subprocess.PIPE).strip()
    if actual != candidate_sha:
        raise ValueError("candidate SHA does not identify the requested commit")
    lane = manifest["lanes"].get(lane_id)
    if not isinstance(lane, dict):
        raise ValueError("lane is absent from approved manifest")
    required = lane.get("required_gates")
    if (not isinstance(required, list) or not set(required) <= LANE_GATES
            or len(required) != len(set(required))
            or set(manifest.get("global_gates", [])) != GLOBAL_GATES):
        raise ValueError("approved gate routes are incomplete or duplicated")
    names = list(required) + list(manifest["global_gates"])
    if not isinstance(archives, dict) or set(archives) - set(names):
        raise ValueError("archive map has an unknown or inapplicable gate")
    gates = {}
    for gate in names:
        gates[gate] = evaluate_gate(gate, archives.get(gate), candidate_sha,
                                    lane_id, lane, repository,
                                    expected_artifact_hashes,
                                    expected_runtime_identity)
    statuses = {item["status"] for item in gates.values()}
    status = next((state for state in ("FAILED", "UNAVAILABLE", "NOT_RUN")
                   if state in statuses), "PASSED")
    result = {"schema": 1, "kind": "independent-gate-verification",
              "candidate_sha": candidate_sha, "lane": lane_id,
              "manifest_sha256": digest(manifest),
              "expected_artifact_hashes": expected_artifact_hashes,
              "expected_runtime_identity": expected_runtime_identity,
              "gates": gates, "status": status}
    result["result_sha256"] = digest(result)
    return result


def evaluate_gate(gate, archive, candidate_sha, lane_id, lane, repository,
                  expected_artifact_hashes, expected_runtime_identity):
    if archive is None:
        return _result(gate, "NOT_RUN", "no raw archive supplied")
    root = Path(archive)
    try:
        if not root.is_dir() or root.is_symlink():
            raise ValueError("raw archive directory is missing or symbolic")
        if gate == "staged-consumer" and (root / "verification.json").is_file():
            _archive_paths(root)
            summary = _bounded_bundle(root, candidate_sha, lane,
                                      expected_artifact_hashes, repository)
            return _result(gate, "NOT_RUN",
                           "bounded staged consumer verified; full lane configuration and suite remain unexecuted",
                           bounded_executed=summary["executed"])
        receipt = _json(_file_path(root, "receipt.json"))
        if not isinstance(receipt, dict):
            raise ValueError("raw archive receipt is not an object")
        if receipt.get("status") == "UNAVAILABLE":
            if {path.name for path in root.iterdir()} != {"receipt.json"}:
                raise ValueError("unavailability receipt has unexpected raw files")
            return _external_unavailable(receipt, candidate_sha, lane_id, gate)
        archive_sha = _inventory(root, receipt)
        process = _binding(root, receipt, candidate_sha, lane_id, lane,
                           repository, expected_artifact_hashes,
                           expected_runtime_identity, gate)
        if receipt.get("status") not in ("PASSED", "FAILED", "NOT_RUN"):
            raise ValueError("reported gate status is invalid")
        if receipt["status"] == "NOT_RUN":
            return _result(gate, "NOT_RUN", "producer records no execution",
                           archive_sha256=archive_sha)
        if receipt["status"] == "FAILED":
            return _result(gate, "FAILED", "producer records a failed execution",
                           archive_sha256=archive_sha)
        if gate == "duplicate-provider":
            reason = _duplicate_provider(root, receipt, process)
            return _result(gate, "PASSED", reason, archive_sha256=archive_sha)
        if process["exit_code"] != 0:
            return _result(gate, "FAILED", f"raw command exited {process['exit_code']}",
                           archive_sha256=archive_sha)
        if gate in ("staged-artifacts", "publication-contract"):
            reason = _staged_publication(root, candidate_sha, lane,
                                         expected_artifact_hashes, repository)
            return _result(gate, "PASSED", reason, archive_sha256=archive_sha)
        if gate == "staged-consumer":
            reason = _staged_consumer(root, receipt, candidate_sha, lane,
                                      expected_artifact_hashes, repository, process)
            return _result(gate, "PASSED", reason, archive_sha256=archive_sha)
        if gate == "migration-journeys":
            reason = _migration_journeys(root, candidate_sha,
                                         expected_artifact_hashes)
            return _result(gate, "PASSED", reason, archive_sha256=archive_sha)
        if gate in ("numerical-parity", "physical-correctness"):
            reason = _numerical_entries(
                root, receipt, candidate_sha, expected_artifact_hashes,
                physical_only=gate == "physical-correctness")
            return _result(gate, "PASSED", reason, archive_sha256=archive_sha)
        if gate == "performance-resource":
            reason = _performance_resource(root, candidate_sha)
            return _result(gate, "PASSED", reason, archive_sha256=archive_sha)
        if gate == "independent-review":
            reason = _independent_review(root, candidate_sha, repository)
            return _result(gate, "PASSED", reason, archive_sha256=archive_sha)
        if receipt["status"] == "PASSED":
            return _result(gate, "FAILED",
                           "reported pass lacks an independently verified full producer contract",
                           archive_sha256=archive_sha)
        return _result(gate, "FAILED", "producer reported failure",
                       archive_sha256=archive_sha)
    except IncompleteEvidence as error:
        return _result(gate, "NOT_RUN", str(error))
    except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError,
            json.JSONDecodeError, subprocess.CalledProcessError,
            zipfile.BadZipFile, ET.ParseError) as error:
        return _result(gate, "FAILED", str(error))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--lane", required=True)
    parser.add_argument("--repository", type=Path,
                        default=Path(__file__).resolve().parents[2])
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--archive", action="append", default=[], metavar="GATE=PATH")
    parser.add_argument("--expected-artifacts", type=Path)
    parser.add_argument("--expected-runtime-identity")
    args = parser.parse_args(argv)
    manifest = (json.loads(args.manifest.read_text()) if args.manifest
                else load_approved_manifest(args.repository))
    archives = {}
    for value in args.archive:
        gate, separator, path = value.partition("=")
        if not separator or not path or gate in archives:
            parser.error("each --archive must be a unique GATE=PATH")
        archives[gate] = Path(path)
    hashes = json.loads(args.expected_artifacts.read_text()) if args.expected_artifacts else None
    result = evaluate(manifest, args.candidate_sha, args.lane, archives,
                      args.repository, hashes, args.expected_runtime_identity)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
