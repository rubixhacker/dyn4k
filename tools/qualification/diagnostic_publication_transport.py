#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

import publication
import qualify
import stage
from test_publication import PublicationAuditTests


ROOT = Path(__file__).resolve().parents[2]
HIDDEN = (
    "build/staging-repository/.qualification/windows/receipt.json",
    "build/staging-repository/.qualification/windows/stage.log",
)


def prepare(candidate):
    temp = Path(os.environ["RUNNER_TEMP"])
    fixture_root = temp / "fixture-root"
    fixture_root.mkdir()
    fixture = PublicationAuditTests()
    staging = fixture.stage(fixture_root)
    stage_dir = staging / ".qualification/windows"
    stage_dir.mkdir(parents=True)
    targets = ("js", "jvm")
    tasks = stage.publication_tasks(targets)
    console = stage_dir / "stage.log"
    console.write_text("".join(f"> Task {task}\n" for task in tasks) + "BUILD SUCCESSFUL\n")
    receipt = stage_dir / "receipt.json"
    receipt.write_text(json.dumps({
        "candidate_sha": candidate,
        "repository": str(ROOT),
        "targets": list(targets),
        "tasks": tasks,
        "command": fixture.publication_command(tasks),
        "status": "PASSED",
        "exit_code": 0,
        "console_sha256": hashlib.sha256(console.read_bytes()).hexdigest(),
    }))
    audit = qualify.audit_staging(staging, candidate, targets, fixture_root / "LICENSE.md",
                                  receipt, console)
    if audit["status"] != "PASSED":
        raise ValueError(f"fixture staging audit failed: {audit['errors']}")
    audit_path = temp / "artifact-audit.json"
    audit_path.write_text(json.dumps(audit))
    bundle = temp / "hosted-publication"
    publication.package(fixture_root, audit_path, bundle)
    for name in HIDDEN:
        if not (bundle / name).is_file():
            raise ValueError(f"publication fixture lacks {name}")
    shutil.copytree(stage_dir, ROOT / "build/staging-repository/.qualification/windows",
                    dirs_exist_ok=True)
    digest = hashlib.sha256((bundle / "manifest.json").read_bytes()).hexdigest()
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"manifest_sha256={digest}\n")
    print(json.dumps({"status": "PACKAGED", "manifest_sha256": digest,
                      "declared_files": len(json.loads((bundle / "manifest.json").read_text())["files"])}))


def verify(candidate):
    temp = Path(os.environ["RUNNER_TEMP"])
    manifests = list((temp / "downloaded").rglob("manifest.json"))
    if len(manifests) != 1:
        raise ValueError(f"downloaded manifest count differs: {len(manifests)}")
    bundle = manifests[0].parent
    digest = os.environ["EXPECTED_MANIFEST_SHA256"]
    manifest = publication.verify(bundle, candidate, digest)
    for name in HIDDEN:
        if not (bundle / name).is_file():
            raise ValueError(f"downloaded publication lacks {name}")
    print(json.dumps({"status": "PASSED_DOWNLOADED_PUBLICATION",
                      "manifest_sha256": digest, "verified_files": len(manifest["files"]),
                      "hidden_files": list(HIDDEN)}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "verify"))
    parser.add_argument("--candidate-sha", required=True)
    args = parser.parse_args()
    if not qualify.SHA40.fullmatch(args.candidate_sha):
        parser.error("candidate SHA must be full length")
    if args.action == "prepare":
        prepare(args.candidate_sha)
    else:
        verify(args.candidate_sha)


if __name__ == "__main__":
    main()
