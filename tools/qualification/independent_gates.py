#!/usr/bin/env python3
import argparse
import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from functools import lru_cache
from pathlib import Path
import xml.etree.ElementTree as ET

import qualify
import artifact


APPROVED_MANIFEST_SHA256 = "bf94699fb2b7bc5f68070b2baa67a24747a7891c6c6d6e864ed7a17aa9a51240"
APPROVED_MANIFEST_REVISION = "fa5a5d98fc5f85e27f1e30d2b0565caec9f8b3b9"
MANIFEST_PATH = "tools/qualification/full-suite-manifest.json"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
LANE_GATES = frozenset(("staged-artifacts", "staged-consumer", "numerical-parity",
                        "physical-correctness", "unchanged-java-corpus",
                        "java-source-compatibility", "duplicate-provider"))
GLOBAL_GATES = frozenset(("migration-journeys", "performance-resource",
                          "publication-contract", "independent-review"))
PRODUCER_SCOPED_GATES = frozenset(("unchanged-java-corpus", "java-source-compatibility",
                                   "migration-journeys", "performance-resource",
                                   "independent-review"))
APPROVED_POLICY = {
    "tools/numerical/fixtures.json": "658f3216584a9842b9d9826767521f6bca1a9df0ed006b447a72a47d4915065c",
    "tools/numerical/compare.py": "4310fe9ddad700bd591b7708cc1a61e9b307029ca97f5240b608a61fe0430fa3",
    "tools/numerical/physical.py": "98ff243a02eece8a47a4faeda06385696174b2b10836e4e1315d6a13e22ee5ba",
    "tools/numerical/weld-pulley-physical-declaration.json": "9794a4ef64c93f6ff76afb03d98784b27be68fe413256362abf1a3f84cf96368",
    "tools/numerical/weld-pulley-physical-manifest.json": "5531b263fbd5a7684db0ea9fbef167c8d8772104949ce01ba4de7606498aecab",
    "tools/numerical/weld_pulley_quality.py": "f8c7cb7449b5d007e5c7dabb20e08deda93974b3cd8a4bedf0cd96f1640c2c87",
}
APPROVED_MIGRATION = {
    "tools/migration/journeys.py": "f5111af3f263691446eae984904232d26a1d9392d6fa26881225bf8c9079b9b9",
    "tools/migration/validate_scene.py": "fa50bf08f0af86c173a4ec8775c4b6febb4b4c98099afd5dcb872ce97639ce6e",
    "tools/migration/validate_plain.py": "7fac38d996ff369c95d44a944050439df54f715924b825406136b7591d5b3f38",
}
MIGRATION_DEPENDENCIES = {
    "annotations-13.0.jar": "ace2a10dc8e2d5fd34925ecac03e4988b2c0f851650c94b8cef49ba1bd111478",
    "kotlin-stdlib-2.4.20.jar": "2226de463d309d4a5500a481320b3dea515a6981dcae1def531fbc158884e25f",
}
REVIEWED_FULL_CI_REVISION = "00d2f949fd485287b737e905808bfb65be942733"
REVIEWED_FULL_CI_SHA256 = "f8e0bda794d141b1418b76ccd712306b9c9f1d587446fe79fcb4697b57885ad7"
NUMERICAL_SOURCE_HASH_METHOD = "SHA-256 of git archive --format=tar HEAD"
PROSPECTIVE_CASE_COUNT = 318
JOINT_PHYSICAL_CASES = ("weld-spring-equal", "pulley-taut")
JOINT_PHYSICAL_STEPS = 36000
PROSPECTIVE_POLICY_REVISION = "7213238591db1611da86cdec075978190ca6d52f"
PROSPECTIVE_POLICY_PATH = "tools/numerical/portable/prospective_policy_catalog.json"
PROSPECTIVE_POLICY_SHA256 = "5c8e2ca48a2128b99b2f52188f0f556c3dad3030bde00975bc80d2a25b0c74bb"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def load_approved_manifest(repository):
    raw = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "show",
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
        if relative == "receipt.json":
            raise ValueError("receipt cannot inventory itself")
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
        if path.stat().st_mtime_ns != mtime:
            raise ValueError(f"raw file filesystem timestamp differs: {relative}")
    actual = _archive_paths(root)
    if actual != seen | {"receipt.json"}:
        raise ValueError("archive has unlisted, missing, or duplicate files")
    return digest({"receipt": receipt, "files": sorted(files, key=lambda item: item["path"])})


def archive_digest(root):
    root = Path(root)
    paths = _archive_paths(root)
    if "receipt.json" not in paths:
        raise ValueError("raw receipt is absent")
    return digest([{"path": name, "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest(),
                    "mtime_ns": (root / name).stat().st_mtime_ns}
                   for name in sorted(paths)])


def consumer_contract(manifest, lane_id):
    lane = manifest["lanes"][lane_id]
    scopes = set(lane["case_scopes"])
    cases = [item for item in manifest["cases"] if item["scope"] in scopes]
    if not cases or len({item["id"] for item in cases}) != len(cases):
        raise ValueError("approved staged consumer case contract is empty or duplicated")
    return {"target": lane["target"], "runtime": lane["runtime"],
            "version": lane["version"], "configuration": lane["configuration"],
            "cases": cases}


def _policy_binding(repository, candidate_sha):
    return _source_binding(repository, candidate_sha, APPROVED_POLICY,
                           "numerical approved policy/checker")


def verified_numerical_source_sha256(repository, candidate_sha):
    if not isinstance(candidate_sha, str) or not SHA40.fullmatch(candidate_sha):
        raise ValueError("numerical source requires an exact candidate commit")
    archive = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "archive",
         "--format=tar", candidate_sha], stderr=subprocess.PIPE)
    return hashlib.sha256(archive).hexdigest()


@lru_cache(maxsize=4)
def approved_prospective_catalog(repository):
    raw = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "show",
         f"{PROSPECTIVE_POLICY_REVISION}:{PROSPECTIVE_POLICY_PATH}"],
        stderr=subprocess.PIPE)
    if hashlib.sha256(raw).hexdigest() != PROSPECTIVE_POLICY_SHA256:
        raise ValueError("adopted prospective policy catalog differs")
    catalog = json.loads(raw, object_pairs_hook=_strict_object)
    cases = catalog.get("cases")
    if (not isinstance(cases, dict) or len(cases) != PROSPECTIVE_CASE_COUNT
            or any(not isinstance(name, str) or not name for name in cases)):
        raise ValueError("adopted prospective case inventory differs")
    return catalog


def approved_prospective_cases(repository):
    return tuple(sorted(approved_prospective_catalog(str(repository))["cases"]))


def _missing_numerical_subgates(repository):
    cases = {case: {"rule": "NOT_RUN", "arithmetic": "NOT_RUN", "status": "NOT_RUN"}
             for case in approved_prospective_cases(str(repository))}
    return {"frozen-traces": {"status": "NOT_RUN", "required_cases": 14},
            "prospective-rule-arithmetic": {
                "status": "NOT_RUN", "required_cases": PROSPECTIVE_CASE_COUNT,
                "reason": "318 per-case rule comparisons and target arithmetic audits are absent",
                "reference_diagnostic": "41 failed derived rules, 4 unpassed premises, 1 failed physical case under operative fixed-32-ulps policy",
                "cases": cases}}


def _missing_physical_profiles():
    return {"default-sleep-wake": {"candidate_status": "NOT_RUN",
                                   "approved_reference_status": "FAILED_125847_OF_126000"},
            "configured-sleep-wake": {"candidate_status": "NOT_RUN",
                                      "approved_reference_status": "PASSED"},
            "weld-pulley": {"candidate_status": "NOT_RUN",
                            "required_cases": len(JOINT_PHYSICAL_CASES),
                            "steps_per_case": JOINT_PHYSICAL_STEPS,
                            "approved_reference_status": "PASSED_BASELINE_ONLY",
                            "legacy_pulley_diagnostic": "39 old-reference samples exceeded the 0.005 m solver tolerance; observed maximum extension 0.1208278904872957 m",
                            "reason": "candidate Weld and Pulley physical traces are absent"},
            "nominal": {"candidate_status": "NOT_RUN",
                        "reason": "candidate nominal physical quality evidence is absent"}}


def _source_binding(repository, candidate_sha, approved_paths, label):
    for relative, approved in approved_paths.items():
        local = Path(__file__).resolve().parents[2] / relative
        committed = subprocess.check_output(
            ["git", "--no-replace-objects", "-C", str(repository), "show", f"{candidate_sha}:{relative}"],
            stderr=subprocess.PIPE)
        if (hashlib.sha256(local.read_bytes()).hexdigest() != approved
                or hashlib.sha256(committed).hexdigest() != approved):
            raise ValueError(f"{label} blob differs: {relative}")
    return dict(approved_paths)


def _numerical_modules(directory):
    compare_spec = importlib.util.spec_from_file_location(
        "dyn4k_approved_compare", directory / "compare.py")
    compare = importlib.util.module_from_spec(compare_spec)
    compare_spec.loader.exec_module(compare)
    previous = sys.modules.get("compare")
    sys.modules["compare"] = compare
    try:
        physical_spec = importlib.util.spec_from_file_location(
            "dyn4k_approved_physical", directory / "physical.py")
        physical = importlib.util.module_from_spec(physical_spec)
        physical_spec.loader.exec_module(physical)
    finally:
        if previous is None:
            del sys.modules["compare"]
        else:
            sys.modules["compare"] = previous
    return compare, physical


def _joint_quality_module(directory):
    compare, _ = _numerical_modules(directory)
    previous = sys.modules.get("compare")
    sys.modules["compare"] = compare
    try:
        specification = importlib.util.spec_from_file_location(
            "dyn4k_approved_joint_quality", directory / "weld_pulley_quality.py")
        quality = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(quality)
    finally:
        if previous is None:
            del sys.modules["compare"]
        else:
            sys.modules["compare"] = previous
    return quality


def verify_joint_physical_cases(root, receipt, candidate_sha,
                                expected_artifact_hashes, source_sha):
    directory = Path(__file__).resolve().parents[1] / "numerical"
    declaration = _json(directory / "weld-pulley-physical-declaration.json")
    manifest = _json(directory / "weld-pulley-physical-manifest.json")
    quality = _joint_quality_module(directory)
    rows = receipt.get("joint_physical_cases")
    if rows is None:
        raise ValueError("36,000-step candidate Weld and Pulley traces are absent")
    if (not isinstance(rows, list) or len(rows) != len(JOINT_PHYSICAL_CASES)
            or {row.get("case") for row in rows if isinstance(row, dict)}
            != set(JOINT_PHYSICAL_CASES)):
        raise ValueError("candidate Weld/Pulley case identities or counts differ")
    if (declaration.get("steps_per_case") != JOINT_PHYSICAL_STEPS
            or set(manifest.get("cases", {})) != set(JOINT_PHYSICAL_CASES)):
        raise ValueError("approved Weld/Pulley declaration or case set differs")
    failures = {}
    for row in rows:
        case = row["case"]
        reference = directory / "references" / manifest["cases"][case]["file"]
        baseline = quality.audit_quality(declaration, manifest, case, reference)
        if baseline["status"] != "PHYSICAL_PASSED":
            raise ValueError(f"{case} approved baseline physical archive differs")
        trace = _file_path(root, row.get("candidate"))
        capture = _json(_file_path(root, row.get("capture_receipt")))
        raw = trace.read_bytes()
        counts = manifest["cases"][case]["counts"]
        required_capture = {
            "case": case, "candidate_commit": candidate_sha,
            "source_hash_method": NUMERICAL_SOURCE_HASH_METHOD,
            "source_sha256": source_sha,
            "artifact_sha256": expected_artifact_hashes["dyn4k-core"],
            "trace_sha256": hashlib.sha256(raw).hexdigest(),
            "expected_counts": counts, "executed_counts": counts, "skipped": 0}
        if any(capture.get(key) != value for key, value in required_capture.items()):
            raise ValueError(f"{case} candidate physical capture identity or counts differ")
        records = iter(_numerical_modules(directory)[0].records(trace))
        try:
            _, header = next(records)
        except StopIteration as error:
            raise ValueError(f"{case} candidate physical trace is empty") from error
        if header != {"kind": "inputs", "case": case,
                       "declaration_sha256": manifest["declaration_sha256"],
                       "candidate_commit": candidate_sha, "source_sha256": source_sha,
                       "artifact_sha256": expected_artifact_hashes["dyn4k-core"],
                       "step_seconds": declaration["step_seconds"],
                       "steps": JOINT_PHYSICAL_STEPS}:
            raise ValueError(f"{case} candidate physical input or source identity differs")
        failed = {metric: 0 for metric in declaration["cases"][case]["metrics"]}
        for step in range(1, JOINT_PHYSICAL_STEPS + 1):
            for order, callback in enumerate(quality.CALLBACKS):
                try:
                    _, event = next(records)
                except StopIteration as error:
                    raise ValueError(f"{case} missing callback at step {step}") from error
                if event != {"kind": "event", "step": step, "order": order,
                             "callback": callback}:
                    raise ValueError(f"{case} callback identity or order differs")
            try:
                _, state = next(records)
            except StopIteration as error:
                raise ValueError(f"{case} missing state at step {step}") from error
            if state.keys() != {"kind", "step", "state"} or state["kind"] != "state" or state["step"] != step:
                raise ValueError(f"{case} state identity or order differs")
            metrics = quality.weld(state["state"]) if case == "weld-spring-equal" else quality.pulley(state["state"])
            for metric, (lower, upper) in metrics.items():
                ceiling = quality.limit(declaration, case, metric)
                if lower <= ceiling < upper:
                    raise ValueError(f"{case} physical metric straddles approved limit")
                if lower > ceiling:
                    failed[metric] += 1
        if next(records, None) is not None:
            raise ValueError(f"{case} candidate physical trace has extra records")
        failures[case] = failed
    return {"candidate_status": "FAILED" if any(any(row.values()) for row in failures.values()) else "PASSED",
            "required_cases": 2, "steps_per_case": JOINT_PHYSICAL_STEPS,
            "approved_reference_status": "PASSED_BASELINE_ONLY",
            "legacy_pulley_diagnostic": "39 old-reference samples exceeded the 0.005 m solver tolerance; observed maximum extension 0.1208278904872957 m",
            "failures": failures}


def verify_prospective_case_subgates(root, receipt, repository, candidate_sha,
                                     expected_artifact_hashes, source_sha):
    catalog = approved_prospective_catalog(str(repository))
    expected = set(catalog["cases"])
    rows = receipt.get("prospective_cases")
    if (not isinstance(rows, list) or len(rows) != PROSPECTIVE_CASE_COUNT
            or {row.get("id") for row in rows if isinstance(row, dict)} != expected):
        raise ValueError("318 prospective rule/arithmetic raw case identities are missing or duplicated")
    if receipt.get("prospective_catalog_sha256") != PROSPECTIVE_POLICY_SHA256:
        raise ValueError("adopted prospective catalog identity differs")
    portable = "tools/numerical/portable"
    for filename in ("prospective_policy_catalog.json", "prospective_compare.py",
                     "cases.py", "orthogonality.py", "reference_diagnostic.py", "receipt.py"):
        relative = f"{portable}/{filename}"
        approved = subprocess.check_output(
            ["git", "--no-replace-objects", "-C", str(repository), "show",
             f"{PROSPECTIVE_POLICY_REVISION}:{relative}"], stderr=subprocess.PIPE)
        committed = subprocess.check_output(
            ["git", "--no-replace-objects", "-C", str(repository), "show",
             f"{candidate_sha}:{relative}"], stderr=subprocess.PIPE)
        if committed != approved:
            raise ValueError(f"prospective policy/checker blob differs: {relative}")
    archive = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "archive", candidate_sha,
         portable, "tools/numerical/compare.py", "tools/numerical/fixtures.json"],
        stderr=subprocess.PIPE)
    with tempfile.TemporaryDirectory(prefix="dyn4k-prospective-checker-") as temporary:
        with tarfile.open(fileobj=io.BytesIO(archive)) as package:
            package.extractall(temporary, filter="data")
        package_path = str(Path(temporary) / portable)
        names = ("prospective_compare", "cases", "orthogonality", "reference_diagnostic",
                 "receipt", "compare")
        prior = {name: sys.modules.get(name) for name in names}
        previous_bytecode = sys.dont_write_bytecode
        for name in names:
            sys.modules.pop(name, None)
        sys.path.insert(0, package_path)
        try:
            import prospective_compare
            declared = {case["id"]: case for case in prospective_compare.declared_cases()
                        if case["id"] in expected}
            if set(declared) != expected:
                raise ValueError("prospective executable case declarations differ")
            cases = {}
            for row in rows:
                case_id = row["id"]
                if set(row) != {"id", "reference", "candidate", "capture_receipt", "arithmetic_audit"}:
                    raise ValueError(f"{case_id} prospective raw fields differ")
                reference = _file_path(root, row["reference"])
                candidate = _file_path(root, row["candidate"])
                capture = _json(_file_path(root, row["capture_receipt"]))
                arithmetic = _json(_file_path(root, row["arithmetic_audit"]))
                required = {"case_id": case_id, "candidate_commit": candidate_sha,
                            "source_hash_method": NUMERICAL_SOURCE_HASH_METHOD,
                            "source_sha256": source_sha,
                            "artifact_sha256": expected_artifact_hashes["dyn4k-core"],
                            "trace_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
                            "expected_steps": declared[case_id]["steps"],
                            "executed_steps": declared[case_id]["steps"], "skipped": 0}
                if any(capture.get(key) != value for key, value in required.items()):
                    raise ValueError(f"{case_id} prospective capture source, artifact, or step identity differs")
                if (arithmetic.get("case_id") != case_id
                        or arithmetic.get("candidate_commit") != candidate_sha
                        or arithmetic.get("trace_sha256") != required["trace_sha256"]):
                    raise ValueError(f"{case_id} target arithmetic raw audit identity differs")
                prospective_compare.verify_reference_inventory(reference, case_id, catalog)
                compared = prospective_compare.compare_policy_case(
                    reference, candidate, declared[case_id], catalog)
                rule = compared["status"]
                cases[case_id] = {"rule": rule,
                                  "arithmetic": "NOT_RUN",
                                  "status": "FAILED" if rule.startswith("FAILED") else "NOT_RUN"}
            return {"status": "FAILED" if any(item["status"] == "FAILED" for item in cases.values()) else "NOT_RUN",
                    "required_cases": PROSPECTIVE_CASE_COUNT,
                    "reason": "target arithmetic audits lack an approved independent raw oracle",
                    "cases": cases}
        finally:
            sys.path.pop(0)
            source_parent = str(Path(temporary) / "tools/numerical")
            if source_parent in sys.path:
                sys.path.remove(source_parent)
            sys.dont_write_bytecode = previous_bytecode
            for name in names:
                sys.modules.pop(name, None)
                if prior[name] is not None:
                    sys.modules[name] = prior[name]


def _producer_scope(gate, candidate_sha, scopes):
    scope = scopes.get(gate) if isinstance(scopes, dict) else None
    if not isinstance(scope, dict) or set(scope) != {
            "candidate_sha", "target", "runtime", "runtime_identity", "artifact_hashes"}:
        raise ValueError(f"{gate} independent producing artifact/runtime scope is missing")
    if scope["candidate_sha"] != candidate_sha:
        raise ValueError(f"{gate} producing source commit differs from exact candidate")
    expected_target = "source" if gate == "independent-review" else "jvm"
    expected_runtime = "codex" if gate == "independent-review" else "Java"
    if (scope["target"] != expected_target or scope["runtime"] != expected_runtime
            or not isinstance(scope["runtime_identity"], str)
            or not scope["runtime_identity"]):
        raise ValueError(f"{gate} producing target or runtime identity differs")
    hashes = scope["artifact_hashes"]
    required = (set() if gate == "independent-review" else
                {"dyn4k-core"} if gate == "migration-journeys" else
                set(qualify.MODULES))
    if (not isinstance(hashes, dict) or set(hashes) != required
            or any(not SHA64.fullmatch(str(value)) for value in hashes.values())):
        raise ValueError(f"{gate} producing artifact hashes are incomplete")
    return scope


def _binding(root, receipt, candidate_sha, lane_id, lane, repository,
             expected_artifact_hashes, expected_runtime_identity, gate,
             expected_producer_scopes):
    if receipt.get("schema") != 1 or receipt.get("candidate_sha") != candidate_sha:
        raise ValueError("raw candidate SHA differs")
    source_tree = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "rev-parse", f"{candidate_sha}^{{tree}}"],
        text=True, stderr=subprocess.PIPE).strip()
    if receipt.get("source_tree") != source_tree:
        raise ValueError("raw Git source tree differs from exact candidate")
    if gate not in GLOBAL_GATES or receipt.get("lane") is not None:
        if receipt.get("lane") != lane_id:
            raise ValueError("raw lane differs")
        for key in ("target", "runtime", "version", "configuration"):
            if receipt.get(key) != lane.get(key):
                raise ValueError(f"raw {key} differs from selected lane")
        if gate not in PRODUCER_SCOPED_GATES and (
                not isinstance(expected_runtime_identity, str) or not expected_runtime_identity
                or receipt.get("runtime_identity") != expected_runtime_identity):
            raise ValueError("raw runtime identity differs from independent selection")
    if gate in PRODUCER_SCOPED_GATES:
        scope = _producer_scope(gate, candidate_sha, expected_producer_scopes)
        if (receipt.get("producer_scope") != scope
                or receipt.get("runtime_identity") != scope["runtime_identity"]):
            raise ValueError("raw producing artifact/runtime scope differs from independent selection")
        selected_hashes = scope["artifact_hashes"]
    else:
        if (not isinstance(expected_artifact_hashes, dict)
                or set(expected_artifact_hashes) != set(qualify.MODULES)
                or any(not SHA64.fullmatch(str(value)) for value in expected_artifact_hashes.values())):
            raise ValueError("independently audited target binary hashes are missing")
        selected_hashes = expected_artifact_hashes
    if receipt.get("artifact_hashes") != selected_hashes:
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


def _process_proof(root, process, gate, lane_id):
    command = process["command"]
    executable = Path(command[0]).name.lower()
    allowed = {"gradlew", "gradle", "adb", "xcrun", "node", "wasmtime",
               "podman", "python", "python3", "java", "javac", "codex"}
    if executable not in allowed:
        raise ValueError(f"raw {gate} command has no recognized execution launcher")
    if executable in {"python", "python3"} and not any(
            arg.endswith((".py", ".sh")) for arg in command[1:]):
        raise ValueError(f"raw {gate} Python command lacks an executable verifier")
    if gate in ("staged-consumer", "duplicate-provider", "staged-artifacts",
                "publication-contract"):
        if executable not in {"gradlew", "gradle", "adb", "xcrun", "node",
                              "wasmtime", "podman"}:
            raise ValueError(f"raw {gate} command does not launch a consumer or staging task")
        if "stdout" not in process:
            raise ValueError(f"raw {gate} process output is missing")
        output = _file_path(root, process["stdout"]).read_text()
        if f"QUALIFICATION_LANE={lane_id}" not in output.splitlines():
            raise ValueError(f"raw {gate} output lacks exact lane execution marker")
        if executable in {"gradlew", "gradle"}:
            if not re.search(r"(?m)^> Task :[^\s]+", output):
                raise ValueError(f"raw {gate} Gradle task output is absent")
            expected = "BUILD FAILED" if process["exit_code"] != 0 else "BUILD SUCCESSFUL"
            if expected not in output:
                raise ValueError(f"raw {gate} Gradle outcome is absent")
        elif "QUALIFICATION_PROCESS_EXIT=" + str(process["exit_code"]) not in output.splitlines():
            raise ValueError(f"raw {gate} runtime exit marker is absent")
    return executable


def _process_file_binding(root, process, relative, label):
    path = _file_path(root, relative)
    marker = f"QUALIFICATION_{label}_SHA256={hashlib.sha256(path.read_bytes()).hexdigest()}"
    output = _file_path(root, process["stdout"]).read_text()
    if marker not in output.splitlines():
        raise ValueError(f"raw process output does not bind {relative}")


def _duplicate_provider(root, receipt, process):
    graph_path = _file_path(root, receipt.get("provider_graph"))
    _process_file_binding(root, process, receipt["provider_graph"], "PROVIDER_GRAPH")
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
    if not any("dependenc" in arg.lower() or "provider" in arg.lower()
               for arg in process["command"][1:]):
        raise ValueError("raw command does not run provider dependency diagnosis")
    task = process["command"][-1].split(":")[-1]
    output = _file_path(root, process["stdout"]).read_text()
    if not any(line.startswith("> Task :") and line.split(":")[-1].split()[0] == task
               for line in output.splitlines()):
        raise ValueError("raw provider task output differs from executed command")
    return "raw provider graph, command output, and failing diagnostic agree"


def _external_unavailable(receipt, candidate_sha, lane_id, gate):
    reason = receipt.get("reason")
    if (receipt.get("schema") != 1 or receipt.get("candidate_sha") != candidate_sha
            or (gate not in GLOBAL_GATES and receipt.get("lane") != lane_id)
            or (receipt.get("lane") is not None and receipt.get("lane") != lane_id)
            or not isinstance(reason, str) or not reason.strip()
            or not isinstance(receipt.get("observed_by"), str) or not receipt["observed_by"]
            or type(receipt.get("observed_at_ns")) is not int
            or receipt["observed_at_ns"] <= 0):
        raise ValueError("external unavailability observation is incomplete or misbound")
    return _result(gate, "UNAVAILABLE", reason,
                   observation_sha256=digest(receipt))


def _validated_all_target_hashes(hashes):
    targets = {row["target"] for row in qualify.matrix()}
    if (not isinstance(hashes, dict) or set(hashes) != targets
            or any(not isinstance(value, dict) or set(value) != set(qualify.MODULES)
                   or any(not SHA64.fullmatch(str(sha)) for sha in value.values())
                   for value in hashes.values())):
        raise ValueError("independently audited 21-target binary hash map is incomplete")
    return hashes


def _staged_publication(root, candidate_sha, lane, expected_artifact_hashes,
                        repository, expected_all_target_hashes=None):
    staging = root / "staged"
    if not staging.is_dir() or staging.is_symlink():
        raise ValueError("full staged repository is missing")
    audit = qualify.audit_staging(staging, candidate_sha)
    if audit["status"] != "PASSED":
        raise ValueError("full staged publication audit failed: " + "; ".join(audit["errors"][:4]))
    license_bytes = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "show", f"{candidate_sha}:LICENSE.md"],
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
    if expected_all_target_hashes is not None:
        _validated_all_target_hashes(expected_all_target_hashes)
        if expected_all_target_hashes[lane["target"]] != expected_artifact_hashes:
            raise ValueError("selected target hashes differ from all-target audit")
        selected = expected_all_target_hashes
    else:
        selected = {lane["target"]: expected_artifact_hashes}
    for target, hashes in selected.items():
        for module in qualify.MODULES:
            binary = staging / qualify.target_binary_path(module, target)
            if not binary.is_file() or binary.is_symlink():
                raise ValueError(f"staged target binary is missing: {target}/{module}")
            if qualify.digest(binary) != hashes[module]:
                raise ValueError(f"staged target binary differs from independent audit: {target}/{module}")
    return f"full staged audit verified {len(audit['artifacts'])} publication files"


def _migration_journeys(root, candidate_sha, expected_artifact_hashes):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "migration"))
    try:
        import journeys
        import validate_plain
        import validate_scene
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
    source_manifest = _file_path(root, "evidence/sources.sha256").read_bytes()
    if hashlib.sha256(source_manifest).hexdigest() != journeys.SOURCE_MANIFEST_SHA256:
        raise ValueError("42 unchanged sample source identities differ from pinned manifest")
    source_rows = source_manifest.decode().splitlines()
    if len(source_rows) != 42 or len(set(source_rows)) != 42:
        raise ValueError("42 unchanged Java source records are incomplete")
    source_paths = []
    for row in source_rows:
        match = re.fullmatch(r"([0-9a-f]{64})  (.+\.java)", row)
        if match is None:
            raise ValueError("unchanged Java source manifest row is invalid")
        source_paths.append(match[2])
        if hashlib.sha256(_file_path(root, "evidence/sources/" + match[2]).read_bytes()).hexdigest() != match[1]:
            raise ValueError(f"unchanged Java source bytes differ: {match[2]}")
    if source_paths != sorted(source_paths):
        raise ValueError("unchanged Java source manifest is not sorted")
    sample_check = _json(_file_path(root, "evidence/sample-check.json"))
    if (sample_check.get("status") != "PASSED" or sample_check.get("revision") != journeys.SAMPLE_REVISION
            or sample_check.get("java_source_count") != 42
            or sample_check.get("manifest_sha256") != journeys.SOURCE_MANIFEST_SHA256):
        raise ValueError("migration post-run sample check differs")
    for provider in journeys.PROVIDERS:
        compiled = _json(root / "evidence" / provider / "compile" / "compile.json")
        jar_hashes = dict(journeys.PINNED_JARS)
        if provider == "candidate":
            jar_hashes.pop("dyn4j-6.0.0.jar")
            jar_hashes[journeys.CANDIDATE_JAR] = expected_artifact_hashes["dyn4k-core"]
            jar_hashes.update(MIGRATION_DEPENDENCIES)
        if (not isinstance(compiled.get("artifacts"), list)
                or {item.get("name"): item.get("sha256") for item in compiled["artifacts"]
                    if isinstance(item, dict)} != jar_hashes
                or len(compiled["artifacts"]) != len(jar_hashes)):
            raise ValueError(f"{provider} resolved dependency inventory differs")
        for name, expected_hash in jar_hashes.items():
            binary = _file_path(root, f"evidence/resolved/{provider}/{name}")
            if hashlib.sha256(binary.read_bytes()).hexdigest() != expected_hash:
                raise ValueError(f"{provider} resolved dependency differs: {name}")
        if (compiled.get("status") != "PASSED" or compiled.get("exit_code") != 0
                or compiled.get("source_count") != 42
                or compiled.get("source_manifest_sha256") != journeys.SOURCE_MANIFEST_SHA256
                or not isinstance(compiled.get("command"), list)
                or Path(compiled["command"][0]).name != "javac"
                or "--release" not in compiled["command"]
                or "8" not in compiled["command"]
                or not all(any(arg.endswith(path) for arg in compiled["command"])
                           for path in source_paths)
                or not all(any(name in arg for arg in compiled["command"])
                           for name in jar_hashes)
                or not (root / "evidence" / provider / "compile" / "javac.log").is_file()):
            raise ValueError(f"{provider} unchanged Java compilation lacks raw success evidence")
        classes = list((root / "evidence" / provider / "compile" / "classes").rglob("*.class"))
        if (not classes or len(classes) != compiled.get("class_count")
                or any(path.is_symlink() or not path.is_file() or path.stat().st_size == 0
                       or path.read_bytes()[:4] != b"\xca\xfe\xba\xbe" for path in classes)):
            raise ValueError(f"{provider} compiled class outputs differ")
        if not _file_path(root, f"evidence/{provider}/compile/javac-version.log").read_text().strip():
            raise ValueError(f"{provider} javac version output is missing")
        observer = _json(_file_path(root, f"evidence/{provider}/observer-build.json"))
        if (observer.get("status") != "PASSED" or observer.get("exit_code") != 0
                or len(observer.get("commands", [])) != 3
                or any(step.get("exit_code") != 0 for step in observer["commands"])):
            raise ValueError(f"{provider} observer build lacks raw command evidence")
    instrumentation = _file_path(root, "evidence/instrumentation/javassist-3.30.2-GA.jar")
    if hashlib.sha256(instrumentation.read_bytes()).hexdigest() != journeys.JAVASSIST_SHA256:
        raise ValueError("migration observer instrumentation differs from pinned JAR")
    for case in cases:
        for mode in ("plain", "observed"):
            observation = case.get(mode)
            if (not isinstance(observation, dict) or observation.get("status") != "PASSED"
                    or observation.get("exit_code") != 0):
                raise ValueError(f"{case['provider']} {case['scene']} {mode} did not execute")
            directory = root / "evidence" / case["provider"] / case["scene"] / mode
            invocation = _json(directory / "invocation.json")
            command = invocation.get("command")
            if (not isinstance(command, list) or command[:2] != ["podman", "run"]
                    or not any(arg.endswith("run-plain-scene.sh" if mode == "plain" else "run-scene.sh") for arg in command)
                    or case["scene"] not in command
                    or not _file_path(root, (directory / "container.log").relative_to(root).as_posix()).read_text().strip()):
                raise ValueError(f"{case['scene']} {mode} raw container invocation is missing")
            validation_name = "plain-validation.json" if mode == "plain" else "validation.json"
            validation = _json(directory / "evidence" / case["scene"] / validation_name)
            if validation != observation.get("validation"):
                raise ValueError(f"{case['scene']} {mode} raw validation differs from summary")
            if (validation.get("failed", validation.get("failed_checks")) != 0
                    or validation.get("unexecuted", validation.get("unexecuted_checks")) != 0
                    or validation.get("executed", validation.get("executed_checks", 0)) <= 0):
                raise ValueError(f"{case['scene']} {mode} raw validation has incomplete checks")
            evidence = directory / "evidence" / case["scene"]
            if mode == "plain":
                replay = validate_plain.validate(case["scene"], evidence)
            else:
                log_text = _file_path(root, (evidence / "observer.log").relative_to(root).as_posix()).read_text()
                input_text = _file_path(root, (evidence / "inputs.log").relative_to(root).as_posix()).read_text()
                samples, errors = [], []
                for number, line in enumerate(log_text.splitlines(), 1):
                    if line.startswith("OBS_JSON "):
                        try:
                            samples.append(json.loads(line[len("OBS_JSON "):]))
                        except (ValueError, TypeError) as error:
                            errors.append(f"line {number}: {error}")
                checks = validate_scene.checks_for(case["scene"], log_text, input_text, samples, errors)
                replay = {"scene": case["scene"], "expected_checks": len(checks),
                          "executed_checks": sum(item["status"] != "skipped" for item in checks),
                          "passed_checks": sum(item["status"] == "passed" for item in checks),
                          "failed_checks": sum(item["status"] == "failed" for item in checks),
                          "unexecuted_checks": sum(item["status"] == "skipped" for item in checks),
                          "samples": len(samples), "checks": checks, "parse_errors": errors}
            if replay != validation or replay.get("failed", replay.get("failed_checks")) != 0:
                raise ValueError(f"{case['scene']} {mode} raw scene, input, physics, or CCD evidence differs")
    candidate_jar = root / "evidence" / "resolved" / "candidate" / journeys.CANDIDATE_JAR
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
        if turn_models != {"gpt-6-sol"} or len(session_ids) != 1:
            raise ValueError(f"{kind} raw session does not prove one Sol review")
        final_reviews = []
        observed_findings = []
        for item in messages:
            if item.get("type") != "response_item":
                continue
            payload = item.get("payload", {})
            if isinstance(payload.get("findings"), list):
                observed_findings.extend(payload["findings"])
            if payload.get("type") != "message" or payload.get("role") != "assistant":
                continue
            for part in payload.get("content", []):
                if part.get("type") != "output_text":
                    continue
                try:
                    value = json.loads(part.get("text", ""), object_pairs_hook=_strict_object)
                except (ValueError, TypeError):
                    continue
                if isinstance(value, dict) and value.get("kind") == "independent-review-result":
                    final_reviews.append(value)
                elif isinstance(value, dict) and isinstance(value.get("findings"), list):
                    observed_findings.extend(value["findings"])
        if len(final_reviews) != 1:
            raise ValueError(f"{kind} raw final review output is absent or ambiguous")
        raw_review = final_reviews[0]
        if (raw_review.get("review_kind") != kind
                or raw_review.get("candidate_sha") != candidate_sha
                or raw_review.get("findings") != report.get("findings")
                or raw_review.get("verdict") != report.get("verdict")
                or raw_review.get("assessment") != report.get("assessment")
                or raw_review.get("reviewed_paths") != report.get("reviewed_paths")):
            raise ValueError(f"{kind} raw review findings differ from report or exact final head")
        required_paths = ({"AGENTS.md", "docs/agents/writing.md"} if kind == "standards"
                          else {"docs/specs/complete-port.md",
                                "docs/planning/acceptance-implementation.md"})
        reviewed_paths = raw_review.get("reviewed_paths")
        if (not isinstance(raw_review.get("assessment"), str)
                or len(raw_review["assessment"].strip()) < 40
                or not isinstance(reviewed_paths, list)
                or not required_paths <= set(reviewed_paths)
                or len(reviewed_paths) != len(set(reviewed_paths))):
            raise ValueError(f"{kind} raw review has no substantive standards or spec assessment")
        for path in reviewed_paths:
            _file_path_name(path)
            subprocess.check_output(["git", "--no-replace-objects", "-C", str(repository), "show",
                                     f"{candidate_sha}:{path}"], stderr=subprocess.PIPE)
        session_id = next(iter(session_ids))
        if report.get("session_id") != session_id or session_id in sessions:
            raise ValueError("independent reviews repeat or misstate session identity")
        sessions.add(session_id)
        findings = raw_review.get("findings")
        if not isinstance(findings, list):
            raise ValueError(f"{kind} actionable findings are missing")
        final_by_id = {finding.get("id"): finding for finding in findings
                       if isinstance(finding, dict)}
        for observed in observed_findings:
            if (not isinstance(observed, dict) or observed.get("id") not in final_by_id
                    or (observed.get("severity") is not None
                        and observed["severity"] != final_by_id[observed["id"]].get("severity"))):
                raise ValueError(f"{kind} raw actionable finding is absent from final review")
        ids = [finding.get("id") for finding in findings if isinstance(finding, dict)]
        if len(ids) != len(findings) or len(set(ids)) != len(ids):
            raise ValueError(f"{kind} finding identities are invalid")
        for finding in findings:
            if (not isinstance(finding.get("severity"), str)
                    or not isinstance(finding.get("description"), str)
                    or not finding["description"].strip()):
                raise ValueError(f"{kind} raw finding lacks actionable details")
            resolution = finding.get("resolution")
            if (not isinstance(resolution, dict)
                    or resolution.get("status") != "RESOLVED"
                    or resolution.get("candidate_sha") != candidate_sha
                    or not isinstance(resolution.get("evidence"), str)
                    or not resolution["evidence"].strip()):
                raise ValueError(f"{kind} actionable finding is unresolved")
            evidence = resolution["evidence"]
            _file_path_name(evidence)
            committed = subprocess.check_output(
                ["git", "--no-replace-objects", "-C", str(repository), "show", f"{candidate_sha}:{evidence}"],
                stderr=subprocess.PIPE)
            if hashlib.sha256(committed).hexdigest() != resolution.get("evidence_sha256"):
                raise ValueError(f"{kind} resolution evidence differs from exact final head")
        if raw_review.get("verdict") != "PASSED":
            raise ValueError(f"{kind} raw reviewer verdict is not PASSED")
        reports.append(report)
    return f"{len(reports)} distinct Sol reviews verified against final head"


def _bounded_bundle(root, candidate_sha, lane, expected_artifact_hashes, repository):
    manifest = json.loads(subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "show",
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


def _staged_consumer(root, receipt, candidate_sha, lane_id, lane,
                     expected_artifact_hashes, repository, process, manifest):
    target = lane["target"]
    if target in ("js", "wasmJs", "wasmWasi"):
        suffix = {"js": "jsNode", "wasmJs": "wasmJsNode",
                  "wasmWasi": "wasmWasiNode"}[target]
    else:
        suffix = target
    group_id = f"consumer-{suffix}"
    foundation = json.loads(subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "show",
         f"{candidate_sha}:tools/qualification/foundation-probes.json"],
        stderr=subprocess.PIPE))
    group = next((item for item in foundation["groups"] if item["id"] == group_id), None)
    foundation_route = group is not None and lane["runtime"] in ("Java", "Node.js", "Linux x64", "macOS ARM64", "Windows x64", "iOS simulator ARM64", "iOS simulator x64", "tvOS simulator ARM64", "watchOS simulator ARM64")
    if foundation_route:
        if receipt.get("consumer_group") != group_id:
            raise ValueError("frozen staged consumer group differs")
        task = Path(group["report_pattern"]).parent.name
        if not any(arg.endswith(":" + task) or arg == task for arg in process["command"][1:]):
            raise ValueError("raw command does not execute exact consumer task")
        output = _file_path(root, process["stdout"]).read_text()
        if not any(line.startswith("> Task :") and line.split(":")[-1].split()[0] == task
                   for line in output.splitlines()):
            raise ValueError("raw consumer task output differs from executed command")
        expected = set(qualify.expected_probe_cases(foundation, group))
    else:
        contract = consumer_contract(manifest, lane_id)
        if (receipt.get("consumer_group") != "full-suite"
                or receipt.get("consumer_contract_sha256") != digest(contract)
                or lane_id not in process["command"]):
            raise ValueError("full staged consumer command or approved lane contract differs")
        expected = {item["id"] for item in contract["cases"]}
    graph = _file_path(root, receipt.get("provider_graph")).read_text()
    _process_file_binding(root, process, receipt["provider_graph"], "PROVIDER_GRAPH")
    providers = set(re.findall(r"io\.github\.rubixhacker:([^:\s]+):", graph))
    expected_providers = {qualify.target_publication_name(module, target)
                          for module in qualify.MODULES}
    if "org.dyn4j:dyn4j" in graph or not expected_providers <= providers:
        raise ValueError("external consumer provider graph is incomplete or duplicated")
    binaries = receipt.get("resolved_artifacts")
    if not isinstance(binaries, dict) or set(binaries) != set(qualify.MODULES):
        raise ValueError("both resolved external consumer binaries are required")
    for module, relative in binaries.items():
        _process_file_binding(root, process, relative,
                              "RESOLVED_" + module.upper().replace("-", "_"))
        if hashlib.sha256(_file_path(root, relative).read_bytes()).hexdigest() != expected_artifact_hashes[module]:
            raise ValueError(f"resolved external consumer artifact differs: {module}")
    reports = receipt.get("consumer_xml")
    if not isinstance(reports, list) or not reports or len(reports) != len(set(reports)):
        raise ValueError("raw staged consumer XML report paths are missing or duplicate")
    observed = []
    for relative in reports:
        _process_file_binding(root, process, relative, "CONSUMER_XML")
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
            identity = ((case.get("classname"), case.get("name"))
                        if foundation_route else case.get("id"))
            if (not identity or not 0 <= float(case.get("time", "nan")) < float("inf")
                    or (foundation_route and not all(identity))):
                raise ValueError("staged consumer XML case identity or time is invalid")
            observed.append(identity)
    if len(observed) != len(set(observed)) or set(observed) != expected:
        raise ValueError("staged consumer case identities or counts differ from frozen manifest")
    return f"{len(observed)} raw external consumer cases and both resolved artifacts verified"


def _java_full_ci(root, receipt, gate, candidate_sha, repository,
                  expected_artifact_hashes):
    if receipt.get("producer") != "reviewed-full-ci":
        raise ValueError(f"{gate} requires the reviewed full_ci raw archive contract")
    relative = receipt.get("full_ci_archive")
    _file_path_name(relative)
    archive = root / relative
    manifest_file = _file_path(root, f"{relative}/lane-manifest.json")
    manifest_sha = receipt.get("full_ci_manifest_sha256")
    if (not SHA64.fullmatch(str(manifest_sha))
            or hashlib.sha256(manifest_file.read_bytes()).hexdigest() != manifest_sha):
        raise ValueError("reviewed full_ci manifest differs from independently pinned receipt")
    verified_source = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "show",
         f"{REVIEWED_FULL_CI_REVISION}:tools/compatibility/full_ci.py"],
        stderr=subprocess.PIPE)
    if hashlib.sha256(verified_source).hexdigest() != REVIEWED_FULL_CI_SHA256:
        raise ValueError("reviewed full_ci verifier source differs")
    evidence = _json(_file_path(root, f"{relative}/result.json"))
    if evidence.get("archives", {}).get("staged_jvm_jar") != expected_artifact_hashes["dyn4k-core"]:
        raise ValueError("reviewed Java corpus core JAR differs from independent staging audit")
    resolved = receipt.get("resolved_artifacts")
    if (not isinstance(resolved, dict) or set(resolved) != set(qualify.MODULES)
            or any(hashlib.sha256(_file_path(root, path).read_bytes()).hexdigest()
                   != expected_artifact_hashes[module]
                   for module, path in resolved.items())):
        raise ValueError("Java corpus resolved publications differ from independent staging audit")
    with tempfile.TemporaryDirectory(prefix="dyn4k-reviewed-full-ci-") as temporary:
        source_archive = subprocess.check_output(
            ["git", "--no-replace-objects", "-C", str(repository), "archive", REVIEWED_FULL_CI_REVISION,
             "tools/compatibility", "tools/baseline", "dyn4k-core/src/jvmConsumer/java"],
            stderr=subprocess.PIPE)
        with tarfile.open(fileobj=io.BytesIO(source_archive)) as package:
            package.extractall(temporary, filter="data")
        command = [sys.executable,
                   str(Path(temporary) / "tools/compatibility/full_ci.py"),
                   "verify", "--candidate-sha", candidate_sha,
                   "--output", str(archive.resolve()),
                   "--manifest-sha256", manifest_sha]
        checked = subprocess.run(command, capture_output=True, text=True,
                                 timeout=120, check=False)
    if checked.returncode != 0:
        raise ValueError("reviewed full_ci/strict raw verifier rejected archive: "
                         + checked.stdout[-1000:] + checked.stderr[-300:])
    verified = json.loads(checked.stdout, object_pairs_hook=_strict_object)
    if verified.get("status") != "PASSED" or verified.get("corpus_files") != 24:
        raise ValueError("reviewed full_ci/strict verifier did not pass full Java corpus")
    return ("2,385 unchanged Java cases across 12 compile/runtime routes and "
            "216-type strict source compatibility verified by reviewed full_ci")


def _numerical_entries(root, receipt, candidate_sha, expected_artifact_hashes, repository,
                       physical_only=False):
    numerical_dir = Path(__file__).resolve().parents[1] / "numerical"
    compare, physical = _numerical_modules(numerical_dir)
    catalog = _json(numerical_dir / "fixtures.json")
    selected = {item["key"] for item in catalog["fixtures"]
                if not physical_only or "physical_phase_ceilings_m" in compare.load_fixture(item["key"])}
    entries = receipt.get("fixtures")
    if not isinstance(entries, list) or {item.get("key") for item in entries
                                         if isinstance(item, dict)} != selected or len(entries) != len(selected):
        raise ValueError("frozen numerical fixture identities or counts differ")
    source_sha = verified_numerical_source_sha256(repository, candidate_sha)
    physical_profiles = {"default-sleep-wake": {"states": 0, "failures": 0},
                         "configured-sleep-wake": {"states": 0, "failures": 0}}
    for item in entries:
        fixture = compare.load_fixture(item["key"])
        reference = _file_path(root, item.get("reference"))
        candidate = _file_path(root, item.get("candidate"))
        capture = _file_path(root, item.get("capture_receipt"))
        if _json(capture).get("source_hash_method") != NUMERICAL_SOURCE_HASH_METHOD:
            raise ValueError(f"{item['key']} numerical producer source digest method differs")
        result = compare.compare(fixture, reference, candidate, capture,
                                 source_sha, expected_artifact_hashes["dyn4k-core"],
                                 candidate_sha)
        if result["status"] == "UNPASSED" and not physical_only:
            raise IncompleteEvidence(
                f"{item['key']} has unapproved comparison channels: {result['unpassed_channels']}")
        if result["status"] not in (("PASSED", "UNPASSED") if physical_only else ("PASSED",)):
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
            if states != fixture["counts"]["state"]:
                raise ValueError(f"{item['key']} physical state count differs")
            physical_profiles[fixture["profile"]]["states"] += states
            physical_profiles[fixture["profile"]]["failures"] += failed
    if physical_only:
        physical_profiles["default-sleep-wake"]["candidate_status"] = (
            "FAILED" if physical_profiles["default-sleep-wake"]["failures"] else "PASSED")
        physical_profiles["configured-sleep-wake"]["candidate_status"] = (
            "FAILED" if physical_profiles["configured-sleep-wake"]["failures"] else "PASSED")
        physical_profiles["weld-pulley"] = verify_joint_physical_cases(
            root, receipt, candidate_sha, expected_artifact_hashes, source_sha)
        physical_profiles["nominal"] = {"candidate_status": "NOT_RUN", "reason": "candidate nominal analytic physical evidence is absent"}
        return physical_profiles
    subgates = _missing_numerical_subgates(repository)
    subgates["frozen-traces"] = {"status": "PASSED", "required_cases": len(entries)}
    subgates["prospective-rule-arithmetic"] = verify_prospective_case_subgates(
        root, receipt, repository, candidate_sha, expected_artifact_hashes, source_sha)
    return subgates


class IncompleteEvidence(Exception):
    pass


def _performance_resource(root, candidate_sha, expected_artifact_hashes):
    performance_dir = Path(__file__).resolve().parents[1] / "performance"
    sys.path.insert(0, str(performance_dir))
    try:
        import verify_candidate_archive
        raw = verify_candidate_archive.audit_raw_archive(root / "evidence")
        identity = _json(root / "evidence" / "candidate-identity-at-pilot.json")
        if identity.get("source_commit") != candidate_sha:
            raise ValueError("performance raw identity differs from exact candidate")
        observed_hashes = identity.get("sha256")
        if not isinstance(observed_hashes, dict):
            raise ValueError("performance producing JVM binary inventory is missing")
        for module in qualify.MODULES:
            matching = [value for path, value in observed_hashes.items()
                        if path.endswith(f"/{module}-jvm-0.1.0-alpha.1.jar")]
            if matching != [expected_artifact_hashes[module]]:
                raise ValueError(f"performance producing {module} JAR differs from independent audit")
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
             expected_artifact_hashes=None, expected_runtime_identity=None,
             expected_archive_digests=None, expected_all_target_hashes=None,
             expected_producer_scopes=None):
    repository = Path(repository)
    if digest(manifest) != APPROVED_MANIFEST_SHA256:
        raise ValueError("manifest differs from independently approved complete suite")
    if not isinstance(candidate_sha, str) or not SHA40.fullmatch(candidate_sha):
        raise ValueError("candidate SHA must be an exact commit")
    actual = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "rev-parse", "--verify",
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
    if expected_archive_digests is None:
        expected_archive_digests = {}
    if not isinstance(expected_archive_digests, dict) or set(expected_archive_digests) - set(names):
        raise ValueError("independent archive digest map has an unknown gate")
    if expected_producer_scopes is None:
        expected_producer_scopes = {}
    if (not isinstance(expected_producer_scopes, dict)
            or set(expected_producer_scopes) - (set(names) & PRODUCER_SCOPED_GATES)):
        raise ValueError("independent producing scope map has an unknown gate")
    for gate in names:
        gates[gate] = evaluate_gate(gate, archives.get(gate), candidate_sha,
                                    lane_id, lane, repository,
                                    expected_artifact_hashes,
                                    expected_runtime_identity,
                                    expected_archive_digests.get(gate),
                                    expected_all_target_hashes, manifest,
                                    expected_producer_scopes)
    statuses = {item["status"] for item in gates.values()}
    status = next((state for state in ("FAILED", "UNAVAILABLE", "NOT_RUN")
                   if state in statuses), "PASSED")
    result = {"schema": 1, "kind": "independent-gate-verification",
              "candidate_sha": candidate_sha, "lane": lane_id,
              "manifest_sha256": digest(manifest),
              "approved_numerical_blobs": dict(APPROVED_POLICY),
              "approved_migration_blobs": dict(APPROVED_MIGRATION),
              "reviewed_full_ci_revision": REVIEWED_FULL_CI_REVISION,
              "expected_artifact_hashes": expected_artifact_hashes,
              "expected_all_target_hashes": expected_all_target_hashes,
              "expected_producer_scopes": expected_producer_scopes,
              "expected_archive_digests": expected_archive_digests,
              "expected_runtime_identity": expected_runtime_identity,
              "gates": gates, "status": status}
    result["result_sha256"] = digest(result)
    return result


def evaluate_gate(gate, archive, candidate_sha, lane_id, lane, repository,
                  expected_artifact_hashes, expected_runtime_identity,
                  expected_archive_digest=None, expected_all_target_hashes=None,
                  manifest=None, expected_producer_scopes=None):
    if archive is None:
        if gate == "physical-correctness":
            return _result(gate, "NOT_RUN", "no raw candidate physical archive supplied",
                           profiles=_missing_physical_profiles())
        if gate == "numerical-parity":
            return _result(gate, "NOT_RUN", "no raw candidate numerical archive supplied",
                           subgates=_missing_numerical_subgates(repository))
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
        if receipt.get("status") == "PASSED":
            if not SHA64.fullmatch(str(expected_archive_digest or "")):
                raise ValueError("independent archive provenance digest is missing")
            if archive_digest(root) != expected_archive_digest:
                raise ValueError("independent archive provenance digest differs")
        archive_sha = _inventory(root, receipt)
        process = _binding(root, receipt, candidate_sha, lane_id, lane,
                           repository, expected_artifact_hashes,
                           expected_runtime_identity, gate, expected_producer_scopes)
        if receipt.get("status") not in ("PASSED", "FAILED", "NOT_RUN"):
            raise ValueError("reported gate status is invalid")
        if receipt["status"] == "NOT_RUN":
            return _result(gate, "NOT_RUN", "producer records no execution",
                           archive_sha256=archive_sha)
        if receipt["status"] == "FAILED":
            if process["exit_code"] == 0:
                raise ValueError("producer reports failure but raw process exited successfully")
            _process_proof(root, process, gate, lane_id)
            return _result(gate, "FAILED", f"raw command exited {process['exit_code']}",
                           archive_sha256=archive_sha)
        _process_proof(root, process, gate, lane_id)
        if gate == "duplicate-provider":
            reason = _duplicate_provider(root, receipt, process)
            return _result(gate, "PASSED", reason, archive_sha256=archive_sha)
        if process["exit_code"] != 0:
            return _result(gate, "FAILED", f"raw command exited {process['exit_code']}",
                           archive_sha256=archive_sha)
        if gate in ("staged-artifacts", "publication-contract"):
            if gate == "publication-contract" and expected_all_target_hashes is None:
                raise ValueError("independently audited 21-target binary hash map is missing")
            if gate == "publication-contract":
                _validated_all_target_hashes(expected_all_target_hashes)
            reason = _staged_publication(root, candidate_sha, lane,
                                         expected_artifact_hashes, repository,
                                         expected_all_target_hashes if gate == "publication-contract" else None)
            return _result(gate, "PASSED", reason, archive_sha256=archive_sha)
        if gate == "staged-consumer":
            reason = _staged_consumer(root, receipt, candidate_sha, lane_id, lane,
                                      expected_artifact_hashes, repository, process, manifest)
            return _result(gate, "PASSED", reason, archive_sha256=archive_sha)
        if gate in ("unchanged-java-corpus", "java-source-compatibility"):
            reason = _java_full_ci(root, receipt, gate, candidate_sha,
                                   repository, expected_producer_scopes[gate]["artifact_hashes"])
            return _result(gate, "PASSED", reason, archive_sha256=archive_sha)
        if gate == "migration-journeys":
            _source_binding(repository, candidate_sha, APPROVED_MIGRATION,
                            "migration raw validator")
            reason = _migration_journeys(root, candidate_sha,
                                         expected_producer_scopes[gate]["artifact_hashes"])
            return _result(gate, "PASSED", reason, archive_sha256=archive_sha)
        if gate in ("numerical-parity", "physical-correctness"):
            policy = _policy_binding(repository, candidate_sha)
            reason = _numerical_entries(
                root, receipt, candidate_sha, expected_artifact_hashes, repository,
                physical_only=gate == "physical-correctness")
            if gate == "physical-correctness":
                status = ("FAILED" if any(row["candidate_status"] == "FAILED" for row in reason.values())
                          else "NOT_RUN")
                return _result(gate, status,
                               "default, configured, nominal, and joint physical obligations are reported separately",
                               profiles=reason, archive_sha256=archive_sha, policy_sha256=policy)
            status = reason["prospective-rule-arithmetic"]["status"]
            return _result(gate, status,
                           "14 frozen traces and 318 prospective rule/arithmetic cases are separate obligations",
                           subgates=reason, archive_sha256=archive_sha,
                           policy_sha256=policy)
        if gate == "performance-resource":
            reason = _performance_resource(root, candidate_sha,
                                           expected_producer_scopes[gate]["artifact_hashes"])
            return _result(gate, "PASSED", reason, archive_sha256=archive_sha)
        if gate == "independent-review":
            reason = _independent_review(root, candidate_sha, repository)
            return _result(gate, "PASSED", reason, archive_sha256=archive_sha)
        raise ValueError(f"unknown approved gate route: {gate}")
    except IncompleteEvidence as error:
        return _result(gate, "NOT_RUN", str(error))
    except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError,
            json.JSONDecodeError, subprocess.CalledProcessError,
            zipfile.BadZipFile, ET.ParseError) as error:
        if gate == "numerical-parity":
            return _result(gate, "FAILED", str(error),
                           subgates=_missing_numerical_subgates(repository))
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
    parser.add_argument("--expected-all-target-artifacts", type=Path)
    parser.add_argument("--expected-producer-scopes", type=Path)
    parser.add_argument("--expected-archive-digests", type=Path)
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
    all_hashes = (json.loads(args.expected_all_target_artifacts.read_text())
                  if args.expected_all_target_artifacts else None)
    producer_scopes = (json.loads(args.expected_producer_scopes.read_text())
                       if args.expected_producer_scopes else None)
    archive_digests = (json.loads(args.expected_archive_digests.read_text())
                       if args.expected_archive_digests else None)
    result = evaluate(manifest, args.candidate_sha, args.lane, archives,
                      args.repository, hashes, args.expected_runtime_identity,
                      archive_digests, all_hashes, producer_scopes)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
