#!/usr/bin/env python3
import json
import math
import shutil
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

import qualify


def collect_group(repository, destination, manifest, group, started, finished, files,
                  recorded_times=None):
    group_id = group["id"]
    expected = qualify.expected_probe_cases(manifest, group)
    paths = sorted(repository.glob(group["report_pattern"]))
    if not paths:
        raise ValueError(f"missing report group {group_id}")
    observed = []
    for path in paths:
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"invalid report {path}: missing or symbolic")
        relative = path.relative_to(repository)
        file_key = str(Path("xml") / relative)
        if recorded_times is None:
            mtime_ns = path.stat().st_mtime_ns
        else:
            if file_key not in recorded_times:
                raise ValueError(f"raw report has no bound file time: {file_key}")
            mtime_ns = recorded_times[file_key]
        if type(mtime_ns) is not int or not started <= mtime_ns <= finished:
            raise ValueError(f"stale report {path}: outside bound execution")
        bundled = destination / "xml" / relative
        bundled.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, bundled)
        suite = ET.parse(bundled).getroot()
        if suite.tag != "testsuite":
            raise ValueError(f"invalid report {path}: root is not testsuite")
        cases = list(suite.iter("testcase"))
        counts = {name: int(suite.get(name, "-1")) for name in
                  ("tests", "failures", "errors", "skipped")}
        actual = {"tests": len(cases),
                  "failures": sum(case.find("failure") is not None for case in cases),
                  "errors": sum(case.find("error") is not None for case in cases),
                  "skipped": sum(case.find("skipped") is not None for case in cases)}
        if counts != actual or any(value < 0 for value in counts.values()):
            raise ValueError(f"invalid report {path}: suite counts differ from case elements")
        if counts["failures"] or counts["errors"] or counts["skipped"]:
            raise ValueError(f"invalid report {path}: failed or skipped cases")
        duration = float(suite.get("time", "nan"))
        if not math.isfinite(duration) or duration < 0:
            raise ValueError(f"invalid report {path}: suite time is invalid")
        for case in cases:
            duration = float(case.get("time", "nan"))
            identity = (case.get("classname"), case.get("name"))
            if not math.isfinite(duration) or duration < 0 or not all(identity):
                raise ValueError(f"invalid report {path}: case time or identity is invalid")
            observed.append(identity)
        files.append({"path": str(bundled.relative_to(destination)),
                      "sha256": qualify.digest(bundled), "mtime_ns": mtime_ns})
    if len(observed) != len(set(observed)) or set(observed) != set(expected):
        raise ValueError(f"partial, duplicate, or unexpected cases in {group_id}")
    return len(observed)


def check_probe(probe, manifest, groups, ids, candidate_sha):
    selected = {**manifest, "groups": [groups[group_id] for group_id in ids]}
    expected = sum(len(qualify.expected_probe_cases(manifest, groups[group_id])) for group_id in ids)
    if (probe.get("candidate_sha") != candidate_sha
            or probe.get("status") != "PROBE_PASSED"
            or probe.get("manifest_sha256") != qualify.manifest_digest(selected)
            or probe.get("expected") != expected or probe.get("executed") != expected
            or probe.get("failures") != 0 or probe.get("skipped") != 0
            or probe.get("exit_code") != 0):
        raise ValueError(f"probe for {', '.join(ids)} differs from frozen executed suite")
    started, finished = probe.get("started_at_ns"), probe.get("finished_at_ns")
    if (type(started) is not int or type(finished) is not int
            or started <= 0 or finished < started):
        raise ValueError(f"probe for {', '.join(ids)} lacks execution time")
    return started, finished


def copy_json(path, destination):
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"missing evidence JSON: {path.name}")
    data = qualify.load_json_strict(path)
    if not isinstance(data, dict):
        raise ValueError(f"evidence JSON is not an object: {path.name}")
    target = destination / "json" / path.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
    return data


def capture_staging(repository, destination, targets):
    staging = repository / "build/staging-repository"
    gav = []
    files = []
    hashes = {}
    names = {module for module in qualify.MODULES}
    names.update(qualify.target_publication_name(module, target)
                 for module in qualify.MODULES for target in targets)
    for name in sorted(names):
        base = staging / qualify.GROUP.replace(".", "/") / name / qualify.VERSION
        for suffix in (".pom", ".module"):
            source = base / f"{name}-{qualify.VERSION}{suffix}"
            if not source.is_file() or source.is_symlink():
                raise ValueError(f"staged GAV descriptor missing: {name}{suffix}")
            if suffix == ".pom":
                root = ET.parse(source).getroot()
                namespace = "{http://maven.apache.org/POM/4.0.0}"
                for key, expected in (("groupId", qualify.GROUP), ("artifactId", name),
                                      ("version", qualify.VERSION)):
                    if root.findtext(namespace + key) != expected:
                        raise ValueError(f"staged GAV differs in {name} {key}")
            else:
                metadata = qualify.load_json_strict(source)
                if (not isinstance(metadata, dict)
                        or not isinstance(metadata.get("component"), dict)
                        or metadata["component"].get("version") != qualify.VERSION):
                    raise ValueError(f"staged Gradle metadata version differs in {name}")
            target_path = destination / "staged" / source.relative_to(staging)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target_path)
            files.append({"path": str(target_path.relative_to(destination)),
                          "sha256": qualify.digest(target_path)})
        gav.append(f"{qualify.GROUP}:{name}:{qualify.VERSION}")
    for target in targets:
        hashes[target] = {}
        for module in qualify.MODULES:
            binary = staging / qualify.target_binary_path(module, target)
            sidecar = binary.with_name(binary.name + ".sha256")
            if not binary.is_file() or not sidecar.is_file() or sidecar.is_symlink():
                raise ValueError(f"staged binary or checksum missing: {module} {target}")
            actual = qualify.digest(binary)
            if sidecar.read_text().strip().lower() != actual:
                raise ValueError(f"staged binary checksum differs: {module} {target}")
            target_path = destination / "staged" / sidecar.relative_to(staging)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sidecar, target_path)
            files.append({"path": str(target_path.relative_to(destination)),
                          "sha256": qualify.digest(target_path)})
            hashes[target][module] = actual
    return gav, files, hashes


def stage_hosted(repository, manifest, candidate_sha, target, probe_path, matrix_path, destination):
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "json").mkdir()
    result = {"candidate_sha": candidate_sha, "route": target, "status": "PROBE_FAILED",
              "reason": "raw evidence is incomplete", "expected": 0, "executed": 0,
              "groups": {}, "files": []}
    problems = []
    nonpass_status = None

    try:
        probe = copy_json(probe_path, destination)
        matrix = copy_json(matrix_path, destination) if matrix_path else {"candidate_sha": candidate_sha}
        if matrix.get("candidate_sha") != candidate_sha:
            raise ValueError("matrix candidate SHA differs from bundle")
        if probe.get("candidate_sha") != candidate_sha:
            raise ValueError("hosted candidate SHA differs from bundle")
        if probe.get("target") != target:
            raise ValueError("hosted target differs from bundle")
        if probe.get("status") != "PROBE_PASSED":
            nonpass_status = probe.get("status")
            if nonpass_status not in ("PROBE_FAILED", "UNAVAILABLE", "NOT_RUN"):
                raise ValueError("hosted probe status is invalid")
            result["reason"] = probe.get("reason", "hosted probe did not pass")
            return result
        qualify.validate_hosted_probe(probe, candidate_sha, repository)
        artifact_target = "js" if target == "jsSafari" else target
        result["gav"], result["staged_files"], hashes = capture_staging(
            repository, destination, (artifact_target,))
        if hashes[artifact_target] != probe["artifact_hashes"]:
            raise ValueError("staged GAV binary hashes differ from hosted observation")
        groups = {group["id"]: group for group in manifest["groups"]}
        selections = {"consumer_probe": (f"consumer-{target}",)}
        if target != "jsSafari":
            selections["source_probe"] = (f"core-{target}", target)
        for key, ids in selections.items():
            suffix = "source" if key == "source_probe" else "consumer"
            sidecar = probe_path.with_name(probe_path.stem + f"-{suffix}.json")
            if copy_json(sidecar, destination) != probe[key]:
                problems.append(f"{suffix} JSON differs from hosted result")
            started, finished = check_probe(probe[key], manifest, groups, ids, candidate_sha)
            for group_id in ids:
                group = groups[group_id]
                expected = qualify.expected_probe_cases(manifest, group)
                result["expected"] += len(expected)
                observed = collect_group(repository, destination, manifest, group,
                                         started, finished, result["files"])
                result["groups"][group_id] = observed
                result["executed"] += observed
        if result["executed"] != result["expected"]:
            problems.append("raw executed count differs from frozen manifest")
        result["runtime"] = probe.get("runtime")
        result["artifact_hashes"] = probe.get("artifact_hashes")
    except (KeyError, OSError, TypeError, ValueError, ET.ParseError, json.JSONDecodeError) as error:
        problems.append(str(error))
    finally:
        if nonpass_status is None or problems:
            result.update(status="PROBE_FAILED" if problems else "PROBE_PASSED",
                          reason="; ".join(problems) if problems else "raw XML matches frozen cases")
        else:
            result["status"] = nonpass_status
        (destination / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


UBUNTU_PROBES = {
    "foundation-probe.json": ("core-jvm", "jvm", "core-linuxX64", "linuxX64"),
    "web-probe.json": ("core-jsNode", "jsNode", "core-wasmJsNode", "wasmJsNode",
                       "core-wasmWasiNode", "wasmWasiNode"),
    "android-host-probe.json": ("core-androidHost", "androidHost"),
    "portable-consumer-probe.json": ("consumer-jvm", "consumer-linuxX64",
                                    "consumer-jsNode", "consumer-wasmJsNode",
                                    "consumer-wasmWasiNode", "consumer-androidHost"),
}


def stage_ubuntu(repository, manifest, candidate_sha, evidence_dir, destination):
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "json").mkdir()
    result = {"candidate_sha": candidate_sha, "route": "ubuntu-host", "status": "PROBE_FAILED",
              "reason": "raw evidence is incomplete", "expected": 0, "executed": 0,
              "groups": {}, "files": []}
    problems = []
    try:
        groups = {group["id"]: group for group in manifest["groups"]}
        for name, ids in UBUNTU_PROBES.items():
            probe = copy_json(evidence_dir / name, destination)
            started, finished = check_probe(probe, manifest, groups, ids, candidate_sha)
            for group_id in ids:
                group = groups[group_id]
                result["expected"] += len(qualify.expected_probe_cases(manifest, group))
                count = collect_group(repository, destination, manifest, group,
                                      started, finished, result["files"])
                result["groups"][group_id] = count
                result["executed"] += count
        result["gav"], result["staged_files"], result["artifact_hashes"] = capture_staging(
            repository, destination, ("jvm", "linuxX64", "js", "wasmJs", "wasmWasi", "android"))
        for name in ("artifact-audit.json", "runtime-matrix.json"):
            data = copy_json(evidence_dir / name, destination)
            if data.get("candidate_sha") != candidate_sha:
                raise ValueError(f"{name} candidate SHA differs from bundle")
        provider = evidence_dir / "provider.log"
        if not provider.is_file() or provider.is_symlink() or not provider.read_bytes():
            raise ValueError("duplicate-provider diagnosis log is missing")
        shutil.copy2(provider, destination / "provider.log")
        if result["executed"] != result["expected"]:
            raise ValueError("raw executed count differs from frozen manifest")
    except (KeyError, OSError, TypeError, ValueError, ET.ParseError, json.JSONDecodeError) as error:
        problems.append(str(error))
    result["status"] = "PROBE_FAILED" if problems else "PROBE_PASSED"
    result["reason"] = "; ".join(problems) if problems else "raw XML matches frozen cases"
    (destination / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def verify_bundle(bundle, manifest, candidate_sha):
    summary = qualify.load_json_strict(bundle / "verification.json")
    if not isinstance(summary, dict):
        raise ValueError("bundle verification JSON is not an object")
    if summary.get("candidate_sha") != candidate_sha:
        raise ValueError("bundle candidate SHA differs from requested candidate")
    if summary.get("status") != "PROBE_PASSED":
        raise ValueError(summary.get("reason", "bundle did not pass"))
    route = summary.get("route")
    if route == "ubuntu-host":
        selections = UBUNTU_PROBES
    else:
        import hosted
        if route not in hosted.TARGETS:
            raise ValueError("unknown bundle route")
        name = f"hosted-{route}"
        top = qualify.load_json_strict(bundle / "json" / f"{name}.json")
        qualify.validate_hosted_probe(top, candidate_sha)
        if summary.get("runtime") != top.get("runtime"):
            raise ValueError("bundle runtime differs from hosted observation")
        selections = {f"{name}-consumer.json": (f"consumer-{route}",)}
        if route != "jsSafari":
            selections[f"{name}-source.json"] = (f"core-{route}", route)
    groups = {group["id"]: group for group in manifest["groups"]}
    found = {}
    files = []
    recorded = summary.get("files")
    if (not isinstance(recorded, list) or not recorded
            or any(not isinstance(item, dict) for item in recorded)):
        raise ValueError("bundle raw file inventory is missing")
    recorded_times = {item.get("path"): item.get("mtime_ns") for item in recorded}
    if len(recorded_times) != len(recorded):
        raise ValueError("bundle raw file inventory has duplicate paths")
    import tempfile
    with tempfile.TemporaryDirectory() as temporary:
        scratch = Path(temporary)
        for name, ids in selections.items():
            probe = qualify.load_json_strict(bundle / "json" / name)
            if route != "ubuntu-host":
                role = "consumer_probe" if name.endswith("-consumer.json") else "source_probe"
                if probe != top.get(role):
                    raise ValueError(f"bundled {role} differs from hosted observation")
            started, finished = check_probe(probe, manifest, groups, ids, candidate_sha)
            for group_id in ids:
                found[group_id] = collect_group(bundle / "xml", scratch, manifest,
                                                groups[group_id], started, finished, files,
                                                recorded_times)
    if found != summary.get("groups") or sum(found.values()) != summary.get("executed"):
        raise ValueError("bundle counts differ from raw XML")
    if summary.get("expected") != sum(found.values()):
        raise ValueError("bundle expected count differs from frozen cases")
    if sorted(files, key=lambda item: item["path"]) != sorted(summary.get("files", []),
                                                              key=lambda item: item["path"]):
        raise ValueError("bundle XML hashes differ from verification")
    actual_paths = {str(path.relative_to(bundle)) for path in (bundle / "xml").rglob("*.xml")}
    if actual_paths != {item["path"] for item in files}:
        raise ValueError("bundle contains unlisted XML")
    staged_files = summary.get("staged_files")
    if not isinstance(staged_files, list) or not staged_files:
        raise ValueError("staged GAV provenance is missing")
    for item in staged_files:
        path = bundle / item["path"]
        if not path.is_file() or path.is_symlink() or qualify.digest(path) != item["sha256"]:
            raise ValueError("staged GAV descriptor or checksum differs from bundle")
    staged_paths = {str(path.relative_to(bundle)) for path in (bundle / "staged").rglob("*")
                    if path.is_file()}
    if staged_paths != {item["path"] for item in staged_files}:
        raise ValueError("bundle contains unlisted staged provenance")
    names = []
    for item in staged_files:
        path = bundle / item["path"]
        if path.suffix != ".pom":
            continue
        name = path.parent.parent.name
        root = ET.parse(path).getroot()
        namespace = "{http://maven.apache.org/POM/4.0.0}"
        if (root.findtext(namespace + "groupId") != qualify.GROUP
                or root.findtext(namespace + "artifactId") != name
                or root.findtext(namespace + "version") != qualify.VERSION):
            raise ValueError("bundled staged GAV identity differs")
        names.append(f"{qualify.GROUP}:{name}:{qualify.VERSION}")
    if sorted(names) != sorted(summary.get("gav", [])):
        raise ValueError("bundled staged GAV set differs")
    targets = ("jvm", "linuxX64", "js", "wasmJs", "wasmWasi", "android") if route == "ubuntu-host" else (
        "js" if route == "jsSafari" else route,)
    observed_hashes = {}
    for target in targets:
        observed_hashes[target] = {}
        for module in qualify.MODULES:
            relative = qualify.target_binary_path(module, target) + ".sha256"
            sidecar = bundle / "staged" / relative
            digest = sidecar.read_text().strip().lower()
            if not qualify.SHA64.fullmatch(digest):
                raise ValueError("bundled staged binary checksum is invalid")
            observed_hashes[target][module] = digest
    expected_hashes = (summary.get("artifact_hashes") if route == "ubuntu-host"
                       else {targets[0]: summary.get("artifact_hashes")})
    if observed_hashes != expected_hashes:
        raise ValueError("bundled staged binary hashes differ")
    matrix_name = "runtime-matrix.json" if route == "ubuntu-host" else f"matrix-{route}.json"
    matrix_path = bundle / "json" / matrix_name
    if matrix_path.is_file():
        matrix = qualify.load_json_strict(matrix_path)
        if matrix.get("candidate_sha") != candidate_sha or matrix.get("total") != 112:
            raise ValueError("bundle runtime matrix candidate or size differs")
        if route != "ubuntu-host":
            bounded = matrix.get("bounded_hosted_probes", [])
            if len(bounded) != 1 or bounded[0].get("target") != route or bounded[0].get("status") != "PROBE_PASSED":
                raise ValueError("bundle matrix lacks verified bounded pass")
    elif route == "ubuntu-host":
        raise ValueError("Ubuntu runtime matrix is missing")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Package and verify complete bounded XML evidence")
    parser.add_argument("action", choices=("hosted", "ubuntu", "verify"))
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--target")
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--matrix", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[2]
    qualify.require_clean_checkout(repository, args.candidate_sha)
    manifest = qualify.load_json_strict(repository / "tools/qualification/foundation-probes.json")
    if args.action == "hosted":
        result = stage_hosted(repository, manifest, args.candidate_sha, args.target,
                              args.probe, args.matrix, args.output)
    elif args.action == "ubuntu":
        result = stage_ubuntu(repository, manifest, args.candidate_sha,
                              args.evidence_dir, args.output)
    else:
        result = verify_bundle(args.output, manifest, args.candidate_sha)
    print(json.dumps({"route": result["route"], "status": result["status"],
                      "executed": result["executed"], "expected": result["expected"],
                      "reason": result["reason"]}))
    return 0 if result["status"] == "PROBE_PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
