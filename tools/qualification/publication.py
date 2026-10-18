#!/usr/bin/env python3
import argparse
import json
import shutil
from pathlib import Path

import qualify


def files_in(bundle):
    paths = [path for path in bundle.rglob("*") if path.is_file()]
    if any(path.is_symlink() for path in bundle.rglob("*")):
        raise ValueError("publication bundle contains a symbolic link")
    return {path.relative_to(bundle).as_posix(): qualify.digest(path) for path in paths
            if path.relative_to(bundle).as_posix() != "manifest.json"}


def package(repository, audit_path, destination):
    audit = qualify.load_json_strict(audit_path)
    if audit.get("status") != "PASSED":
        raise ValueError("staged publication audit did not pass")
    qualify.verify_audit_against_staging(audit, repository)
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copy2(repository / "LICENSE.md", destination / "LICENSE.md")
    shutil.copy2(audit_path, destination / "artifact-audit.json")
    staged_source = repository / "build/staging-repository"
    staged_destination = destination / "build/staging-repository"
    for item in audit["artifacts"]:
        relative = Path(item["path"])
        source = staged_source / relative
        target = staged_destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if relative.parts[0] != ".qualification":
            checksum = source.with_name(source.name + ".sha256")
            shutil.copy2(checksum, target.with_name(target.name + ".sha256"))
    manifest = {"candidate_sha": audit["candidate_sha"], "targets": audit["targets"],
                "files": files_in(destination)}
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    verify(destination, audit["candidate_sha"], qualify.digest(manifest_path))
    return manifest


def verify(bundle, candidate_sha, expected_manifest_sha256):
    if (not qualify.SHA64.fullmatch(str(expected_manifest_sha256))
            or qualify.digest(bundle / "manifest.json") != expected_manifest_sha256):
        raise ValueError("trusted manifest SHA-256 differs from downloaded bundle")
    manifest = qualify.load_json_strict(bundle / "manifest.json")
    audit = qualify.load_json_strict(bundle / "artifact-audit.json")
    if (not qualify.SHA40.fullmatch(candidate_sha)
            or manifest.get("candidate_sha") != candidate_sha
            or audit.get("candidate_sha") != candidate_sha
            or audit.get("status") != "PASSED"
            or manifest.get("targets") != audit.get("targets")):
        raise ValueError("publication bundle candidate, targets, or audit status differs")
    if manifest.get("files") != files_in(bundle):
        raise ValueError("publication bundle files or bytes differ from manifest")
    qualify.verify_audit_against_staging(audit, bundle, allow_pinned_content_contract=True)
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("package", "verify"))
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest-sha256")
    args = parser.parse_args()
    if args.action == "package":
        if args.audit is None:
            parser.error("package needs --audit")
        repository = Path(__file__).resolve().parents[2]
        qualify.require_clean_checkout(repository, args.candidate_sha)
        result = package(repository, args.audit, args.output)
    else:
        if args.manifest_sha256 is None:
            parser.error("verify needs the trusted manifest SHA-256")
        result = verify(args.output, args.candidate_sha, args.manifest_sha256)
    print(json.dumps({"candidate_sha": result["candidate_sha"],
                      "targets": result["targets"], "files": len(result["files"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
