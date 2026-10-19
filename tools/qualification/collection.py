#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import independent_gates
import qualify


SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
REQUIRED = ("full-ci", "full-common", "publication-ubuntu", "duplicate-provider")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_tree(repository, candidate_sha):
    if not SHA40.fullmatch(candidate_sha):
        raise ValueError("candidate SHA must be a full Git commit")
    head, tree = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "rev-parse",
         "HEAD", f"{candidate_sha}^{{tree}}"], text=True).splitlines()
    if head != candidate_sha or not SHA40.fullmatch(tree):
        raise ValueError("collector checkout differs from exact candidate")
    return tree


def artifact_route(name, candidate_sha):
    routes = {
        f"full-ci-{candidate_sha}": "full-ci",
        f"full-common-{candidate_sha}": "full-common",
        f"publication-{candidate_sha}-ubuntu": "publication-ubuntu",
        f"publication-{candidate_sha}-macos": "publication-macos",
        f"publication-{candidate_sha}-windows": "publication-windows",
        f"duplicate-provider-{candidate_sha}": "duplicate-provider",
        f"qualification-{candidate_sha}": "qualification-ubuntu",
    }
    if name in routes:
        return routes[name]
    for prefix, route in (("qualification-full-", "full-hosted-"),
                          ("qualification-", "qualification-"),
                          ("windows-failure-raw-", "windows-failure-raw-")):
        match = re.fullmatch(re.escape(prefix) + r"([0-9a-f]{40})-(.+)", name)
        if match:
            if match.group(1) != candidate_sha:
                raise ValueError(f"artifact belongs to another candidate: {name}")
            return route + match.group(2)
    if re.search(r"[0-9a-f]{40}", name):
        raise ValueError(f"unrecognized candidate artifact: {name}")
    raise ValueError(f"artifact has no exact candidate SHA: {name}")


def files_in(root):
    if root.is_symlink() or not root.is_dir():
        raise ValueError("artifact root is missing or symbolic")
    files = {}
    for base, directories, filenames in os.walk(root, followlinks=False):
        for name in directories + filenames:
            path = Path(base) / name
            relative = path.relative_to(root).as_posix()
            independent_gates._file_path_name(relative)
            if path.is_symlink():
                raise ValueError(f"symbolic artifact path: {relative}")
            if path.is_file():
                files[relative] = digest(path)
            elif not path.is_dir():
                raise ValueError(f"nonregular artifact path: {relative}")
    return dict(sorted(files.items()))


def checked_tar(path, destination):
    destination.mkdir(parents=True, exist_ok=False)
    seen = set()
    with tarfile.open(path, "r:*") as archive:
        for item in archive:
            name = item.name.removeprefix("./")
            if name in ("", "."):
                continue
            independent_gates._file_path_name(name)
            if name in seen or not (item.isfile() or item.isdir()):
                raise ValueError("archive has duplicate or nonregular members")
            seen.add(name)
            target = destination.joinpath(*name.split("/"))
            if item.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(item) as source, target.open("wb") as sink:
                shutil.copyfileobj(source, sink)
            stamp = item.pax_headers.get("dyn4k.mtime_ns")
            if stamp is not None:
                if not stamp.isdecimal():
                    raise ValueError("archive timestamp is invalid")
                os.utime(target, ns=(int(stamp), int(stamp)))
    return destination


def checked_sidecar(root, stem):
    archive = root / stem
    sidecar = root / f"{stem.removesuffix('.tar.gz')}.sha256"
    if not archive.is_file() or not sidecar.is_file():
        raise ValueError("archive or SHA-256 sidecar is missing")
    recorded = sidecar.read_text().strip().split()
    if len(recorded) != 2 or not SHA64.fullmatch(recorded[0]) or Path(recorded[1]).name != stem:
        raise ValueError("archive SHA-256 sidecar is malformed")
    if digest(archive) != recorded[0]:
        raise ValueError("archive bytes differ from SHA-256 sidecar")
    return archive


def inspect_artifact(route, root, candidate_sha, tree, extracted, repository, upstream):
    if route in ("full-ci", "full-common"):
        stem = f"{route}-{candidate_sha}.tar.gz"
        archive = checked_sidecar(root, stem)
        members = root / f"{route}-{candidate_sha}.members"
        if not members.is_file():
            raise ValueError(f"{route} archive member list is missing")
        with tarfile.open(archive, "r:*") as packed:
            if ([name.rstrip("/") for name in members.read_text().splitlines()]
                    != [name.rstrip("/") for name in packed.getnames()]):
                raise ValueError(f"{route} archive member list differs")
        unpacked = checked_tar(archive, extracted / route)
        manifest = (unpacked / "full-ci/lane-manifest.json" if route == "full-ci"
                    else unpacked / "archive-index.json")
        declared = qualify.load_json_strict(manifest)
        if declared.get("candidate_sha") != candidate_sha:
            raise ValueError(f"{route} source candidate differs")
        if route == "full-ci":
            from sys import path as python_path
            python_path.insert(0, str(Path(__file__).resolve().parents[1] / "compatibility"))
            import full_ci
            full_ci.verify_archive(unpacked / "full-ci", candidate_sha)
        else:
            import full_corpus
            result = full_corpus.verify_archive(unpacked, repository, candidate_sha,
                                                upstream=upstream, require_checkout=True)
            if result["status"] != "PASSED":
                raise ValueError("full common raw archive does not verify")
        return "PRODUCER_VERIFIED"
    if route.startswith("full-hosted-"):
        from full_hosted import verify_transport_archive
        target = route.removeprefix("full-hosted-")
        archives = list(root.glob("*.tar"))
        if len(archives) != 1:
            raise ValueError("full hosted transport archive is missing or duplicated")
        receipt = verify_transport_archive(archives[0], candidate_sha, target,
                                           repository)
        if receipt.get("candidate_sha") != candidate_sha:
            raise ValueError("full hosted source candidate differs")
        return "PRODUCER_VERIFIED"
    if route == "duplicate-provider":
        receipt = qualify.load_json_strict(root / "receipt.json")
        if (receipt.get("candidate_sha") != candidate_sha
                or receipt.get("source_tree") != tree):
            raise ValueError("duplicate provider source identity differs")
        independent_gates._inventory(root, receipt)
        if receipt.get("status") == "PASSED":
            if receipt.get("process", {}).get("exit_code") == 0:
                raise ValueError("forged provider success lacks failing exit")
            return "PRODUCER_VERIFIED"
        return "FAILED"
    if route.startswith("publication-"):
        from publication import verify
        bundles = list(root.glob("*-publication"))
        if len(bundles) != 1:
            raise ValueError("publication bundle is missing or duplicated")
        verify(bundles[0], candidate_sha, digest(bundles[0] / "manifest.json"))
        return "PRODUCER_VERIFIED"
    if route.startswith("qualification-"):
        from artifact import verify_bundle
        manifest = qualify.load_json_strict(repository /
                                            "tools/qualification/foundation-probes.json")
        verify_bundle(root, manifest, candidate_sha)
        return "PRODUCER_VERIFIED"
    identity = root / "identity.txt"
    if identity.is_file() and f"sha={candidate_sha}" not in identity.read_text().splitlines():
        raise ValueError("failed-route diagnostic source SHA differs")
    return "RETAINED_UNVERIFIED"


def unsigned_inputs(manifest, artifacts, rows):
    inputs = {lane: {"archives": {}} for lane in manifest["lanes"]}
    for (_, root), row in zip(artifacts, rows):
        if row.get("route") == "duplicate-provider" and Path(root).is_dir():
            inputs["jvm:Java:current:default"]["archives"]["duplicate-provider"] = str(
                Path(root).resolve())
    return inputs


def collect(repository, candidate_sha, artifacts, output, upstream=None):
    repository, output = Path(repository), Path(output)
    tree = source_tree(repository, candidate_sha)
    manifest = independent_gates.load_approved_manifest(repository)
    if len(manifest["lanes"]) != 112:
        raise ValueError("approved lane inventory is incomplete")
    output.mkdir(parents=True, exist_ok=False)
    extracted = output / "extracted"
    extracted.mkdir()
    artifacts = list(artifacts)
    rows, seen = [], set()
    staged_audit = None
    for name, root in artifacts:
        root = Path(root)
        row = {"name": name, "route": None, "status": "FAILED"}
        try:
            row["files"] = files_in(root)
            route = artifact_route(name, candidate_sha)
            row["route"] = route
            if route in seen:
                raise ValueError(f"duplicate producer artifact route: {route}")
            seen.add(route)
            row["status"] = inspect_artifact(route, root, candidate_sha, tree, extracted,
                                             repository, upstream)
            if route == "publication-ubuntu" and row["status"] == "PRODUCER_VERIFIED":
                staged_audit = qualify.load_json_strict(next(root.glob("*-publication")) /
                                                       "artifact-audit.json")
        except (OSError, ValueError, TypeError, KeyError, tarfile.TarError,
                zipfile.BadZipFile, ET.ParseError, subprocess.SubprocessError) as error:
            row["reason"] = str(error)
        rows.append(row)
    missing = sorted(set(REQUIRED) - seen)
    inputs = unsigned_inputs(manifest, artifacts, rows)
    (output / "assembly-inputs.json").write_text(json.dumps(inputs, indent=2) + "\n")
    if staged_audit is not None:
        (output / "staged-audit.json").write_text(json.dumps(staged_audit, indent=2) + "\n")
        target_hashes = qualify.target_binary_hashes(staged_audit["artifacts"])
    else:
        target_hashes = {}
    candidate_inputs = {"schema": 1, "candidate_sha": candidate_sha,
                        "suite_manifest_sha256": independent_gates.digest(manifest),
                        "audit_manifest_sha256": (qualify.manifest_digest(staged_audit)
                                                  if staged_audit is not None else None),
                        "status": "INCOMPLETE",
                        "lanes": {lane_id: {"target": lane["target"],
                                            "artifact_hashes": target_hashes.get(lane["target"]),
                                            "runtime_identity": None}
                                  for lane_id, lane in manifest["lanes"].items()}}
    (output / "candidate-manifest-inputs.json").write_text(
        json.dumps(candidate_inputs, indent=2) + "\n")
    report = {"schema": 1, "candidate_sha": candidate_sha, "source_tree": tree,
              "required_lanes": 112, "artifacts": rows, "missing_artifacts": missing,
              "independent_signature": "MISSING",
              "status": "FAILED" if any(row["status"] == "FAILED" for row in rows)
              else "NOT_RUN", "reason": "signed external audit and complete gate routes are absent"}
    report["external_inputs_required"] = [
        "all 112 exact-source common gate archives and runtime identities",
        "independently audited archive digests and 21-target artifact hashes",
        "complete candidate manifest bound to a verified staged audit",
        "exact staged repository bytes available to the public qualifier",
        "detached Ed25519 audit signature and pinned trusted public-key fingerprint"]
    (output / "collection.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def verify_collection(repository, candidate_sha, artifacts, output):
    report = qualify.load_json_strict(Path(output) / "collection.json")
    if (report.get("candidate_sha") != candidate_sha
            or report.get("source_tree") != source_tree(Path(repository), candidate_sha)
            or report.get("required_lanes") != 112):
        raise ValueError("collected source identity differs")
    supplied = list(artifacts)
    rows = report.get("artifacts")
    if (not isinstance(rows, list) or len(rows) != len(supplied)
            or [row.get("name") for row in rows] != [name for name, _ in supplied]):
        raise ValueError("collected producer artifact set differs")
    for row, (_, root) in zip(rows, supplied):
        if row.get("files") is not None and files_in(Path(root)) != row["files"]:
            raise ValueError(f"collected raw artifact bytes differ: {row['name']}")
    inputs = qualify.load_json_strict(Path(output) / "assembly-inputs.json")
    approved = independent_gates.load_approved_manifest(Path(repository))
    if inputs != unsigned_inputs(approved, supplied, rows):
        raise ValueError("unsigned 112-lane input map differs")
    return True


def ingest_external(repository, candidate_sha, artifacts, output, audit_inputs,
                    trusted_key_sha256=None):
    verify_collection(repository, candidate_sha, artifacts, output)
    audit_inputs, output = Path(audit_inputs), Path(output)
    names = ("archive-map.json", "audit.json", "audit.sig", "public.pem",
             "candidate-manifest.json", "staged-audit.json", "evidence.json")
    missing = [name for name in names if not (audit_inputs / name).is_file()]
    if not SHA64.fullmatch(str(trusted_key_sha256 or "")):
        missing.append("externally pinned trusted Ed25519 key SHA-256")
    if not (Path(repository) / "build/staging-repository").is_dir():
        missing.append("verified staged repository bytes at build/staging-repository")
    result = {"candidate_sha": candidate_sha, "status": "NOT_RUN",
              "missing_external_inputs": missing}
    if missing:
        (output / "audit-ingestion.json").write_text(json.dumps(result, indent=2) + "\n")
        return result
    stable = output / "external-inputs"
    stable.mkdir(exist_ok=False)
    original_hashes = {name: digest(audit_inputs / name) for name in names}
    for name in names:
        shutil.copyfile(audit_inputs / name, stable / name)
        if digest(stable / name) != original_hashes[name]:
            raise ValueError(f"external audit input changed while copied: {name}")
    supplied = qualify.load_json_strict(stable / "archive-map.json")
    approved = independent_gates.load_approved_manifest(Path(repository))
    if (supplied.get("schema") != 1 or supplied.get("candidate_sha") != candidate_sha
            or set(supplied.get("lanes", {})) != set(approved["lanes"])):
        raise ValueError("external signed archive map lacks exact 112-lane source binding")
    for name in ("candidate-manifest.json", "staged-audit.json"):
        if qualify.load_json_strict(stable / name).get("candidate_sha") != candidate_sha:
            raise ValueError(f"external {name} belongs to another candidate")
    if (output / "signed-runtime-matrix.json").exists():
        raise ValueError("signed adapter result already exists")
    command = [sys.executable, str(Path(__file__).with_name("qualify.py")), "record",
               "--candidate-sha", candidate_sha,
               "--evidence", str(stable / "evidence.json"),
               "--audit", str(stable / "staged-audit.json"),
               "--candidate-manifest", str(stable / "candidate-manifest.json"),
               "--independent-archives", str(stable / "archive-map.json"),
               "--independent-audit", str(stable / "audit.json"),
               "--independent-audit-signature", str(stable / "audit.sig"),
               "--trusted-audit-public-key", str(stable / "public.pem"),
               "--trusted-audit-key-sha256", trusted_key_sha256,
               "--output", str(output / "signed-runtime-matrix.json")]
    process = subprocess.run(command, cwd=repository, capture_output=True, check=False)
    if any(digest(audit_inputs / name) != original_hashes[name] for name in names):
        raise ValueError("external audit input changed during verification")
    verify_collection(repository, candidate_sha, artifacts, output)
    (output / "signed-adapter.stdout").write_bytes(process.stdout)
    (output / "signed-adapter.stderr").write_bytes(process.stderr)
    result.update(status="FAILED" if process.returncode and not
                  (output / "signed-runtime-matrix.json").is_file() else "NOT_RUN",
                  adapter_exit=process.returncode, missing_external_inputs=[],
                  trusted_key_sha256=trusted_key_sha256,
                  input_sha256=original_hashes)
    if (output / "signed-runtime-matrix.json").is_file():
        matrix = qualify.load_json_strict(output / "signed-runtime-matrix.json")
        if matrix.get("candidate_sha") != candidate_sha or matrix.get("total") != 112:
            raise ValueError("signed adapter returned an incomplete candidate matrix")
        result["counts"] = matrix["counts"]
        if process.returncode == 0 and matrix["counts"].get("PASSED") == 112:
            result["status"] = "PASSED"
        elif matrix["counts"].get("FAILED", 0):
            result["status"] = "FAILED"
    (output / "audit-ingestion.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--artifacts-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--upstream", type=Path)
    parser.add_argument("--audit-input-dir", type=Path)
    parser.add_argument("--trusted-key-sha256")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    artifacts = sorted((path.name, path) for path in args.artifacts_dir.iterdir())
    if args.verify:
        verify_collection(args.repository, args.candidate_sha, artifacts, args.output)
        print(json.dumps({"candidate_sha": args.candidate_sha, "transport": "VERIFIED"}))
        return 0
    if args.audit_input_dir is not None:
        try:
            result = ingest_external(args.repository, args.candidate_sha, artifacts,
                                     args.output, args.audit_input_dir, args.trusted_key_sha256)
        except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
            result = {"candidate_sha": args.candidate_sha, "status": "FAILED",
                      "reason": str(error)}
            args.output.mkdir(parents=True, exist_ok=True)
            (args.output / "audit-ingestion.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
        return 0 if result["status"] == "PASSED" else 1
    report = collect(args.repository, args.candidate_sha, artifacts, args.output,
                     args.upstream)
    print(json.dumps({key: report[key] for key in ("candidate_sha", "status", "missing_artifacts")}))
    return 0 if report["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
