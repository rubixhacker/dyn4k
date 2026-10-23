from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "qualification"))
import full_corpus
import candidate_coverage


ARTIFACT = "dyn4k-core/build/libs/dyn4k-core-jvm-0.1.0-alpha.1.jar"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture(ledger: dict, root: Path, origin: Path, upstream: Path,
            result_path: Path, binding_path: Path) -> dict:
    source = ledger["candidate_source"]
    result = json.loads(result_path.read_text())
    binding = json.loads(binding_path.read_text())
    version = 2 if binding.get("schema") == 2 else 1
    receipt = {"schema_version": version, "kind": "full-common-corpus",
               "candidate_revision": source["revision"], "candidate_tree": source["tree"],
               "candidate_artifact": source["artifact"],
               "candidate_artifact_sha256": source["artifact_sha256"],
               "origin": str(origin.resolve()), "upstream": str(upstream.resolve()),
               "result_path": str(result_path.resolve()), "result_sha256": digest(result_path),
               "binding_path": str(binding_path.resolve()), "binding_sha256": digest(binding_path),
               "manifest_sha256": digest(origin / full_corpus.MANIFEST_PATH),
               "map_sha256": digest(origin / full_corpus.MAP_PATH),
               "total_cases": result.get("total_cases"),
               "groups": [{"id": row["id"], "expected": row["expected"],
                           "reported": row["reported"]} for row in result.get("groups", [])]}
    if version == 2:
        receipt["node_runtimes"] = {
            row["id"]: row.get("node_runtime") for row in result.get("groups", [])
            if row["id"] in full_corpus.NODE_GROUPS}
    error = verify(receipt, ledger, root)
    if error:
        raise ValueError(error)
    return receipt


def verify(receipt: dict, ledger: dict, root: Path) -> str | None:
    try:
        source = ledger["candidate_source"]
        version = receipt.get("schema_version")
        required = {"schema_version": version, "kind": "full-common-corpus",
                    "candidate_revision": source["revision"], "candidate_tree": source["tree"],
                    "candidate_artifact": source["artifact"],
                    "candidate_artifact_sha256": source["artifact_sha256"]}
        if version not in (1, 2) or any(receipt.get(key) != value
                                        for key, value in required.items()):
            return "full common receipt candidate source or artifact differs"
        if source["artifact"] != ARTIFACT or digest(root / ARTIFACT) != source["artifact_sha256"]:
            return "full common receipt candidate JAR missing or changed"
        origin = Path(receipt["origin"])
        upstream = Path(receipt["upstream"])
        result_path = Path(receipt["result_path"])
        binding_path = Path(receipt["binding_path"])
        if (not origin.is_absolute() or not upstream.is_absolute() or not result_path.is_absolute()
                or not binding_path.is_absolute()):
            return "full common receipt paths must be absolute"
        if (candidate_coverage.git(origin, "rev-parse", "HEAD") != source["revision"]
                or candidate_coverage.git(origin, "rev-parse", "HEAD^{tree}") != source["tree"]
                or digest(origin / ARTIFACT) != source["artifact_sha256"]):
            return "full common receipt source worktree or artifact differs"
        if (digest(result_path) != receipt["result_sha256"]
                or digest(origin / full_corpus.MANIFEST_PATH) != receipt["manifest_sha256"]
                or digest(origin / full_corpus.MAP_PATH) != receipt["map_sha256"]):
            return "full common result, manifest, or map missing or changed"
        if digest(binding_path) != receipt["binding_sha256"]:
            return "full common binding missing or changed"
        manifest_path = origin / full_corpus.MANIFEST_PATH
        map_path = origin / full_corpus.MAP_PATH
        manifest = json.loads(manifest_path.read_text())
        with map_path.open(newline="") as stream:
            mapping = list(csv.DictReader(stream, delimiter="\t"))
        binding = json.loads(binding_path.read_text())
        recorded = json.loads(result_path.read_text())
        if version == 2 and (binding.get("schema") != 2 or recorded.get("schema") != 2):
            return "full common actual Node runtime proof format differs"
        if version == 1 and binding.get("schema", 1) == 2:
            return "full common receipt omits actual Node runtime proof format"
        reports = {group["id"]: sorted(origin.glob(group["pattern"]))
                   for group in full_corpus.GROUPS}
        environment = binding["environment"]
        paths = [str(Path(entry["path"]).parent) for entry in environment["executables"].values()
                 if isinstance(entry, dict)]
        with patch.dict(os.environ, {"JAVA_HOME": environment["java_home"],
                                  "ANDROID_HOME": environment["android_home"],
                                  "ANDROID_SDK_ROOT": environment["android_home"],
                                  "PATH": os.pathsep.join([*paths, os.environ.get("PATH", "")])}):
            observed = full_corpus.verify_reports(
                origin, manifest, source["revision"], binding, reports,
                mapping=mapping, upstream=upstream, require_checkout=True,
                manifest_path=manifest_path, mapping_path=map_path)
        if recorded != observed or observed["status"] != "PASSED":
            return "full common report differs from replay or has missing host report"
        if version == 2:
            runtimes = {row["id"]: row.get("node_runtime") for row in observed["groups"]
                        if row["id"] in full_corpus.NODE_GROUPS}
            if (set(runtimes) != full_corpus.NODE_GROUPS or
                    receipt.get("node_runtimes") != runtimes or
                    any(row is None or row.get("status") != "OBSERVED_UNSIGNED"
                        for row in runtimes.values())):
                return "full common actual Node runtime proof differs"
        groups = [{"id": row["id"], "expected": row["expected"],
                   "reported": row["reported"]} for row in observed["groups"]]
        required_group_ids = [group["id"] for group in full_corpus.GROUPS]
        if ([group["id"] for group in groups] != required_group_ids
                or len(groups) != len(required_group_ids)
                or receipt.get("groups") != groups):
            return "full common host counts or source case identities differ"
        required_total = sum(len(full_corpus.expected_cases(manifest, group))
                             for group in full_corpus.GROUPS)
        if (sum(group["expected"] for group in groups) != required_total
                or receipt.get("total_cases") != required_total):
            return "full common host counts or source case identities differ"
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        return f"full common receipt replay failed: {error}"
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Bind the complete twelve-host corpus to an exact candidate source and artifact.")
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--origin", type=Path, required=True)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("common receipt output exists")
    ledger = json.loads(args.ledger.read_text())
    receipt = capture(ledger, args.root, args.origin, args.upstream, args.result, args.binding)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": "PASSED", "total_cases": receipt["total_cases"],
                      "groups": len(receipt["groups"])}))


if __name__ == "__main__":
    main()
