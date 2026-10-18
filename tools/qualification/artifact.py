#!/usr/bin/env python3
import hashlib
import json
import math
import os
import platform
import shutil
import argparse
import sys
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import qualify


def verify_full_hosted(bundle, candidate_sha, repository):
    import full_hosted

    bundle = Path(bundle)
    repository = Path(repository)
    if bundle.is_dir():
        result = qualify.load_json_strict(bundle / "receipt.json")
        if not isinstance(result, dict):
            raise ValueError("full hosted receipt must be an object")
        if result.get("candidate_sha") != candidate_sha:
            raise ValueError("full hosted candidate differs from requested source")
        full_hosted.verify_raw_files(bundle, result, candidate_repository=repository)
        result = dict(result)
        result["_verified_receipt_sha256"] = qualify.digest(bundle / "receipt.json")
        return result
    if not bundle.is_file() or bundle.suffix != ".tar":
        raise ValueError("full hosted bundle must be a directory or transport tar")
    result = full_hosted.verify_transport_archive(
        bundle, candidate_sha, candidate_repository=repository)
    with tarfile.open(bundle, "r") as archive:
        receipt_file = archive.extractfile("receipt.json")
        if receipt_file is None:
            raise ValueError("full hosted transport receipt is missing")
        receipt_sha256 = hashlib.sha256(receipt_file.read()).hexdigest()
    return {**result, "_verified_receipt_sha256": receipt_sha256,
            "_verified_transport_sha256": qualify.digest(bundle)}


def portable_path(value):
    if not isinstance(value, str) or not value:
        raise ValueError("bundle inventory path is missing")
    path = value.replace("\\", "/")
    parts = path.split("/")
    if (any(part in ("", ".", "..") for part in parts)
            or ":" in parts[0]):
        raise ValueError(f"bundle inventory path is unsafe: {value}")
    return "/".join(parts)


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
        file_key = portable_path((Path("xml") / relative).as_posix())
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
        files.append({"path": portable_path(bundled.relative_to(destination).as_posix()),
                      "sha256": qualify.digest(bundled), "mtime_ns": mtime_ns})
    if len(observed) != len(set(observed)):
        raise ValueError(f"duplicate cases in {group_id}")
    observed_set = set(observed)
    if any(identity not in observed_set for identity in expected):
        raise ValueError(f"missing selected cases in {group_id}")
    return {"selected": len(expected), "reported": len(observed)}


def check_probe(probe, manifest, groups, ids, candidate_sha):
    selected = {**manifest, "groups": [groups[group_id] for group_id in ids]}
    expected = sum(len(qualify.expected_probe_cases(manifest, groups[group_id])) for group_id in ids)
    if (probe.get("candidate_sha") != candidate_sha
            or probe.get("status") != "PROBE_PASSED"
            or probe.get("manifest_sha256") != qualify.manifest_digest(selected)
            or probe.get("expected") != expected or probe.get("executed") != expected
            or probe.get("failures") != 0 or probe.get("errors") != 0
            or probe.get("skipped") != 0
            or type(probe.get("reported")) is not int
            or probe.get("reported") < expected
            or probe.get("exit_code") != 0):
        raise ValueError(f"probe for {', '.join(ids)} differs from frozen executed suite")
    qualify.validate_probe_accounting(probe, manifest, ids)
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


def capture_staging(repository, destination, targets, candidate_sha):
    staging = repository / "build/staging-repository"
    source_license = repository / "LICENSE.md"
    if not source_license.is_file():
        raise ValueError("repository license is missing")
    shutil.copy2(source_license, destination / "LICENSE.md")
    gav = []
    files = []
    hashes = {}
    names = {module for module in qualify.MODULES}
    names.update(qualify.target_publication_name(module, target)
                 for module in qualify.MODULES for target in targets)
    metadata_names = {qualify.target_publication_name(module, target)
                      for module in qualify.MODULES for target in targets
                      if target in qualify.APPLE_TARGETS}
    for name in sorted(names):
        base = staging / qualify.GROUP.replace(".", "/") / name / qualify.VERSION
        suffixes = (".pom", ".module", "-sources.jar", "-javadoc.jar", "-license.md")
        if name in qualify.MODULES:
            suffixes += (".jar",)
        if name in metadata_names:
            suffixes += ("-metadata.jar",)
        for suffix in suffixes:
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
            elif suffix == ".module":
                metadata = qualify.load_json_strict(source)
                if (not isinstance(metadata, dict)
                        or not isinstance(metadata.get("component"), dict)
                        or metadata["component"].get("version") != qualify.VERSION):
                    raise ValueError(f"staged Gradle metadata version differs in {name}")
            target_path = destination / "staged" / source.relative_to(staging)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target_path)
            files.append({"path": portable_path(target_path.relative_to(destination).as_posix()),
                          "sha256": qualify.digest(target_path)})
            sidecar = source.with_name(source.name + ".sha256")
            if not sidecar.is_file() or sidecar.read_text().strip().lower() != qualify.digest(source):
                raise ValueError(f"staged checksum differs: {source.name}")
            sidecar_path = destination / "staged" / sidecar.relative_to(staging)
            shutil.copy2(sidecar, sidecar_path)
            files.append({"path": portable_path(sidecar_path.relative_to(destination).as_posix()),
                          "sha256": qualify.digest(sidecar_path)})
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
            binary_path = destination / "staged" / binary.relative_to(staging)
            binary_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(binary, binary_path)
            files.append({"path": portable_path(binary_path.relative_to(destination).as_posix()),
                          "sha256": qualify.digest(binary_path)})
            target_path = destination / "staged" / sidecar.relative_to(staging)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sidecar, target_path)
            files.append({"path": portable_path(target_path.relative_to(destination).as_posix()),
                          "sha256": qualify.digest(target_path)})
            hashes[target][module] = actual
    audit = qualify.audit_staging(staging, candidate_sha, targets, source_license)
    if audit["status"] != "PASSED":
        raise ValueError("staged publication is partial or invalid: " + "; ".join(audit["errors"]))
    return gav, files, hashes, audit["content_contract"]


def stage_hosted(repository, manifest, candidate_sha, target, probe_path, matrix_path, destination):
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "json").mkdir()
    result = {"candidate_sha": candidate_sha, "route": target, "status": "PROBE_FAILED",
              "reason": "raw evidence is incomplete", "expected": 0, "executed": 0,
              "reported": 0, "groups": {}, "reported_groups": {}, "files": []}
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
        result["gav"], result["staged_files"], hashes, result["staged_content_contract"] = capture_staging(
            repository, destination, (artifact_target,), candidate_sha)
        if "stage_receipt_sha256" in probe or "stage_audit_sha256" in probe:
            if not probe.get("stage_receipt_sha256") or not probe.get("stage_audit_sha256"):
                raise ValueError("hosted staging receipt and audit must both be present")
            stage_dir = repository / "build/staging-repository/.qualification" / target
            for filename, expected in (("receipt.json", probe["stage_receipt_sha256"]),
                                       ("audit.json", probe["stage_audit_sha256"]),
                                       ("stage.log", None)):
                source = stage_dir / filename
                if not source.is_file() or source.is_symlink():
                    raise ValueError(f"hosted staging {filename} is missing")
                if expected and qualify.digest(source) != expected:
                    raise ValueError(f"hosted staging {filename} bytes differ")
                destination_path = destination / "staged/.qualification" / target / filename
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination_path)
                result["staged_files"].append({
                    "path": portable_path(destination_path.relative_to(destination).as_posix()),
                    "sha256": qualify.digest(destination_path)})
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
            declared_groups = {item["id"]: item for item in probe[key]["groups"]}
            for group_id in ids:
                group = groups[group_id]
                expected = qualify.expected_probe_cases(manifest, group)
                result["expected"] += len(expected)
                counts = collect_group(repository, destination, manifest, group,
                                       started, finished, result["files"])
                if (counts["selected"] != declared_groups[group_id]["executed"]
                        or counts["reported"] != declared_groups[group_id]["reported"]):
                    raise ValueError(f"raw report counts differ from probe: {group_id}")
                result["groups"][group_id] = counts["selected"]
                result["reported_groups"][group_id] = counts["reported"]
                result["executed"] += counts["selected"]
                result["reported"] += counts["reported"]
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


def ubuntu_runtime():
    import hosted

    release = platform.freedesktop_os_release()
    return {"system": platform.system(), "machine": platform.machine(),
            "kernel_release": platform.release(),
            "distribution": release.get("ID", ""),
            "os_version": release.get("VERSION_ID", ""),
            "runner_image_os": os.environ.get("ImageOS", ""),
            "runner_image_version": os.environ.get("ImageVersion", ""),
            "github_actions": os.environ.get("GITHUB_ACTIONS") == "true",
            "java_version": hosted.tool_version(["java", "-version"], r'version "([^"]+)"')}


def check_ubuntu_runtime(runtime):
    if (not isinstance(runtime, dict) or runtime.get("system") != "Linux"
            or str(runtime.get("machine", "")).lower() not in ("x86_64", "amd64")
            or not runtime.get("distribution") or not runtime.get("os_version")
            or not runtime.get("kernel_release") or not runtime.get("java_version")):
        raise ValueError("Ubuntu bundle runtime identity is incomplete or wrong")
    if runtime.get("github_actions") and (runtime.get("distribution") != "ubuntu"
                                          or not runtime.get("runner_image_os")
                                          or not runtime.get("runner_image_version")):
        raise ValueError("Ubuntu bundle runtime runner image is missing or wrong")


def stage_ubuntu(repository, manifest, candidate_sha, evidence_dir, destination):
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "json").mkdir()
    result = {"candidate_sha": candidate_sha, "route": "ubuntu-host", "status": "PROBE_FAILED",
              "reason": "raw evidence is incomplete", "expected": 0, "executed": 0,
              "reported": 0, "groups": {}, "reported_groups": {}, "files": []}
    problems = []
    try:
        result["runtime"] = ubuntu_runtime()
        check_ubuntu_runtime(result["runtime"])
        groups = {group["id"]: group for group in manifest["groups"]}
        for name, ids in UBUNTU_PROBES.items():
            probe = copy_json(evidence_dir / name, destination)
            started, finished = check_probe(probe, manifest, groups, ids, candidate_sha)
            declared_groups = {item["id"]: item for item in probe["groups"]}
            for group_id in ids:
                group = groups[group_id]
                result["expected"] += len(qualify.expected_probe_cases(manifest, group))
                counts = collect_group(repository, destination, manifest, group,
                                       started, finished, result["files"])
                if (counts["selected"] != declared_groups[group_id]["executed"]
                        or counts["reported"] != declared_groups[group_id]["reported"]):
                    raise ValueError(f"raw report counts differ from probe: {group_id}")
                result["groups"][group_id] = counts["selected"]
                result["reported_groups"][group_id] = counts["reported"]
                result["executed"] += counts["selected"]
                result["reported"] += counts["reported"]
        (result["gav"], result["staged_files"], result["artifact_hashes"],
         result["staged_content_contract"]) = capture_staging(
            repository, destination, ("jvm", "linuxX64", "js", "wasmJs", "wasmWasi", "android"), candidate_sha)
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


def verify_bundle(bundle, manifest, candidate_sha, require_matrix=True):
    summary = qualify.load_json_strict(bundle / "verification.json")
    if not isinstance(summary, dict):
        raise ValueError("bundle verification JSON is not an object")
    if summary.get("candidate_sha") != candidate_sha:
        raise ValueError("bundle candidate SHA differs from requested candidate")
    if summary.get("status") != "PROBE_PASSED":
        raise ValueError(summary.get("reason", "bundle did not pass"))
    route = summary.get("route")
    if route == "ubuntu-host":
        check_ubuntu_runtime(summary.get("runtime"))
        selections = UBUNTU_PROBES
    else:
        import hosted
        if route not in hosted.TARGETS:
            raise ValueError("unknown bundle route")
        name = f"hosted-{route}"
        top = qualify.load_json_strict(bundle / "json" / f"{name}.json")
        qualify.validate_hosted_probe(top, candidate_sha)
        if top.get("status") != "PROBE_PASSED":
            raise ValueError(f"hosted top status is {top.get('status')}, not PROBE_PASSED")
        if summary.get("runtime") != top.get("runtime"):
            raise ValueError("bundle runtime differs from hosted observation")
        selections = {f"{name}-consumer.json": (f"consumer-{route}",)}
        if route != "jsSafari":
            selections[f"{name}-source.json"] = (f"core-{route}", route)
    groups = {group["id"]: group for group in manifest["groups"]}
    found = {}
    found_reported = {}
    files = []
    recorded = summary.get("files")
    if (not isinstance(recorded, list) or not recorded
            or any(not isinstance(item, dict) for item in recorded)):
        raise ValueError("bundle raw file inventory is missing")
    normalized_recorded = [{**item, "path": portable_path(item.get("path"))}
                           for item in recorded]
    recorded_times = {item["path"]: item.get("mtime_ns") for item in normalized_recorded}
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
            declared_groups = {item["id"]: item for item in probe["groups"]}
            for group_id in ids:
                counts = collect_group(bundle / "xml", scratch, manifest, groups[group_id],
                                       started, finished, files, recorded_times)
                if (counts["selected"] != declared_groups[group_id]["executed"]
                        or counts["reported"] != declared_groups[group_id]["reported"]):
                    raise ValueError(f"bundled report counts differ from probe: {group_id}")
                found[group_id] = counts["selected"]
                found_reported[group_id] = counts["reported"]
    if (found != summary.get("groups") or sum(found.values()) != summary.get("executed")
            or found_reported != summary.get("reported_groups")
            or sum(found_reported.values()) != summary.get("reported")):
        raise ValueError("bundle counts differ from raw XML")
    if summary.get("expected") != sum(found.values()):
        raise ValueError("bundle expected count differs from frozen cases")
    if sorted(files, key=lambda item: item["path"]) != sorted(normalized_recorded,
                                                              key=lambda item: item["path"]):
        raise ValueError("bundle XML hashes differ from verification")
    actual_paths = {path.relative_to(bundle).as_posix() for path in (bundle / "xml").rglob("*.xml")}
    if actual_paths != {item["path"] for item in files}:
        raise ValueError("bundle contains unlisted XML")
    staged_files = summary.get("staged_files")
    if not isinstance(staged_files, list) or not staged_files:
        raise ValueError("staged GAV provenance is missing")
    if any(not isinstance(item, dict) for item in staged_files):
        raise ValueError("staged GAV provenance is invalid")
    staged_files = [{**item, "path": portable_path(item.get("path"))}
                    for item in staged_files]
    if len({item["path"] for item in staged_files}) != len(staged_files):
        raise ValueError("staged GAV provenance has duplicate paths")
    for item in staged_files:
        path = bundle / item["path"]
        if not path.is_file() or path.is_symlink() or qualify.digest(path) != item["sha256"]:
            raise ValueError("staged GAV descriptor or checksum differs from bundle")
    staged_paths = {path.relative_to(bundle).as_posix() for path in (bundle / "staged").rglob("*")
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
    license_file = bundle / "LICENSE.md"
    if not license_file.is_file() or license_file.is_symlink():
        raise ValueError("bundle source license is missing")
    staged_audit = qualify.audit_staging(bundle / "staged", candidate_sha, targets, license_file,
                                         content_contract=summary.get("staged_content_contract"))
    if staged_audit["status"] != "PASSED":
        raise ValueError("bundled staged publication is partial or invalid: " + "; ".join(staged_audit["errors"]))
    if route != "ubuntu-host" and ("stage_receipt_sha256" in top or "stage_audit_sha256" in top):
        if not top.get("stage_receipt_sha256") or not top.get("stage_audit_sha256"):
            raise ValueError("bundled hosted stage identity is incomplete")
        stage_dir = bundle / "staged/.qualification" / route
        receipt_path = stage_dir / "receipt.json"
        audit_path = stage_dir / "audit.json"
        console_path = stage_dir / "stage.log"
        if (not receipt_path.is_file() or qualify.digest(receipt_path) != top["stage_receipt_sha256"]
                or not audit_path.is_file() or qualify.digest(audit_path) != top["stage_audit_sha256"]):
            raise ValueError("bundled hosted stage receipt or audit bytes differ")
        verified = qualify.audit_staging(bundle / "staged", candidate_sha, targets,
                                         license_file, receipt_path, console_path,
                                         content_contract=summary.get("staged_content_contract"))
        if verified != qualify.load_json_strict(audit_path) or verified["status"] != "PASSED":
            raise ValueError("bundled hosted stage task outcome or artifact audit differs")
    observed_hashes = {}
    for target in targets:
        observed_hashes[target] = {}
        for module in qualify.MODULES:
            relative = qualify.target_binary_path(module, target) + ".sha256"
            sidecar = bundle / "staged" / relative
            digest = sidecar.read_text().strip().lower()
            if not qualify.SHA64.fullmatch(digest):
                raise ValueError("bundled staged binary checksum is invalid")
            binary = bundle / "staged" / qualify.target_binary_path(module, target)
            if (not binary.is_file() or binary.is_symlink()
                    or qualify.digest(binary) != digest):
                raise ValueError(f"bundled staged binary checksum differs or binary is missing: {module} {target}")
            observed_hashes[target][module] = digest
    expected_hashes = (summary.get("artifact_hashes") if route == "ubuntu-host"
                       else {targets[0]: summary.get("artifact_hashes")})
    if observed_hashes != expected_hashes:
        raise ValueError("bundled staged binary hashes differ")
    matrix_name = "runtime-matrix.json" if route == "ubuntu-host" else f"matrix-{route}.json"
    matrix_path = bundle / "json" / matrix_name
    if matrix_path.is_file():
        matrix = qualify.load_json_strict(matrix_path)
        expected_lanes = {case["id"] for case in qualify.expand(qualify.matrix())}
        if (len(expected_lanes) != 112 or matrix.get("candidate_sha") != candidate_sha
                or matrix.get("total") != len(expected_lanes)):
            raise ValueError("bundle runtime matrix candidate or size differs")
        lanes = matrix.get("lanes")
        if not isinstance(lanes, list) or len(lanes) != len(expected_lanes):
            raise ValueError("bundle matrix lane set is incomplete")
        if any(not isinstance(lane, dict) or not isinstance(lane.get("id"), str)
               for lane in lanes):
            raise ValueError("bundle matrix lane identity is invalid")
        lane_ids = [lane["id"] for lane in lanes]
        if len(set(lane_ids)) != len(lane_ids) or set(lane_ids) != expected_lanes:
            raise ValueError("bundle matrix lane IDs are missing, duplicate, or unknown")
        statuses = ("PASSED", "FAILED", "UNAVAILABLE", "NOT_RUN")
        if any(lane.get("status") not in statuses for lane in lanes):
            raise ValueError("bundle matrix lane status is invalid")
        counted = {status: sum(lane["status"] == status for lane in lanes)
                   for status in statuses}
        declared = matrix.get("counts")
        if (not isinstance(declared, dict) or set(declared) != set(statuses)
                or any(type(value) is not int for value in declared.values())
                or declared != counted):
            raise ValueError("bundle matrix counts differ from lane records")
        if route != "ubuntu-host":
            bounded = matrix.get("bounded_hosted_probes", [])
            if bounded != [top]:
                raise ValueError("bundle matrix bounded observation differs from hosted probe")
    elif require_matrix:
        raise ValueError("bundle runtime matrix is missing")
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
    parser.add_argument("--full-hosted", action="store_true")
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[2]
    qualify.require_clean_checkout(repository, args.candidate_sha)
    if args.full_hosted or (args.action == "verify" and (
            args.output.suffix == ".tar" or (args.output / "receipt.json").is_file())):
        if args.action != "verify":
            parser.error("full hosted archive supports verify only")
        try:
            result = verify_full_hosted(args.output, args.candidate_sha, repository)
        except (OSError, TypeError, ValueError, ET.ParseError, tarfile.TarError) as error:
            print(f"full hosted archive failed: {error}", file=sys.stderr)
            return 1
        print(json.dumps({"target": result["target"], "status": result["status"],
                          "configurations": len(result["configurations"])}))
        return 0
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
                      "reported": result.get("reported", 0),
                      "reason": result["reason"]}))
    return 0 if result["status"] == "PROBE_PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
