#!/usr/bin/env python3
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

import full_corpus
import qualify


MANIFEST_PATH = "tools/qualification/full-suite-manifest.json"
CORPUS_PATH = "tools/qualification/full-common-corpus.json"
AREA_IDS = ("geometry", "collision", "dynamics", "joints", "compatibility")
LANE_GATES = ("staged-artifacts", "staged-consumer", "numerical-parity",
              "physical-correctness")
JVM_GATES = ("unchanged-java-corpus", "java-source-compatibility",
             "duplicate-provider")
GLOBAL_GATES = ("migration-journeys", "performance-resource",
                "publication-contract", "independent-review")
GATE_DESCRIPTIONS = {
    "staged-artifacts": "Both staged target binaries, metadata, sources, documentation, licenses, and hashes match the candidate.",
    "staged-consumer": "An external consumer resolves both staged modules and executes the selected target runtime and configuration.",
    "numerical-parity": "Frozen baseline comparisons pass with the approved metrics and limits on this lane.",
    "physical-correctness": "Independent physical checks pass or retain explicit failed dispositions on this lane.",
    "unchanged-java-corpus": "All applicable unchanged baseline Java tests execute on the JVM candidate.",
    "java-source-compatibility": "Unchanged Java consumers compile and run with the compatibility API and shared state.",
    "duplicate-provider": "The staged consumer rejects simultaneous dyn4j and dyn4k-core providers.",
    "migration-journeys": "The pinned unchanged sample collection compiles and completes each required observed journey.",
    "performance-resource": "Approved sustained timing, allocation, and memory probes pass on validated reference environments.",
    "publication-contract": "All target publications pass the staged artifact and checksum audit.",
    "independent-review": "Separate standards and spec reviews resolve actionable findings.",
}
GATE_SOURCES = {
    "staged-artifacts": ("tools/qualification/artifact.py",),
    "staged-consumer": ("consumers/qualification/portable/src/commonTest/kotlin/qualification/StagedGeometryTest.kt",),
    "numerical-parity": ("tools/numerical/fixtures.json",),
    "physical-correctness": ("tools/numerical/weld-pulley-physical-manifest.json",),
    "unchanged-java-corpus": (full_corpus.MAP_PATH,),
    "java-source-compatibility": ("consumers/qualification/src/main/java/qualification/JavaMigration.java",),
    "duplicate-provider": ("tools/qualification/qualify.py",),
    "migration-journeys": ("tools/migration/journeys.py",),
    "performance-resource": ("docs/research/performance-manifest-v1.json",),
    "publication-contract": ("tools/qualification/artifact.py",),
    "independent-review": ("docs/agents/writing.md", "docs/specs/complete-port.md"),
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def area_for(case):
    if case["module"] == "dyn4k":
        return "compatibility"
    name = case["classname"].removeprefix("org.dyn4j.")
    if ".joint." in name or "Joint" in name:
        return "joints"
    if name.startswith(("collision.", "coverage.collision.")) or "CollisionWorld" in name:
        return "collision"
    if name.startswith(("dynamics.", "world.", "coverage.dynamics.",
                        "coverage.world.", "coverage.simulation.")):
        return "dynamics"
    if name.startswith(("geometry.", "coverage.geometry.")):
        return "geometry"
    if (name.startswith("coverage.Upstream") and case["originals"] and
            all(original.startswith("org.dyn4j.geometry.")
                for original in case["originals"])):
        return "geometry"
    if name.startswith("coverage.") or name.startswith("UpstreamAVLTree"):
        return "compatibility"
    raise ValueError(f"unclassified corpus case: {name}")


def read_corpus(repository):
    repository = Path(repository)
    raw = (repository / CORPUS_PATH).read_bytes()
    corpus = json.loads(raw)
    if corpus.get("kind") != "full-common-corpus" or corpus.get("policy") != "production":
        raise ValueError("production common corpus is required")
    counts = corpus.get("counts", {})
    expected_counts = {"total_methods": 2526, "mapped_original_methods": 2253,
                       "mapped_original_identities": 2353,
                       "related_supplemental_methods": 5,
                       "jvm_only_original_identities": 32,
                       "supplemental_methods": 270,
                       "platform_only_methods": 3, "unresolved_mappings": 0}
    if any(counts.get(key) != value for key, value in expected_counts.items()):
        raise ValueError("frozen common corpus counts differ")
    source_files = corpus.get("source_files", [])
    scanned_files = full_corpus.scan_test_tree(repository)
    if len(source_files) != 202 or source_files != scanned_files:
        raise ValueError("common test source hash differs")
    scanned = full_corpus.scan_sources(repository)
    indexed = {(case["module"], case["classname"], case["method"]): case
               for case in scanned}
    if len(indexed) != 2526 or len(corpus["cases"]) != 2526:
        raise ValueError("common test source inventory differs")
    for case in corpus["cases"]:
        key = (case["module"], case["classname"], case["method"])
        if any(indexed.get(key, {}).get(field) != case[field] for field in
               ("source_set", "path", "sha256", "line", "hosts")):
            raise ValueError(f"common test source identity differs: {key}")
    if full_corpus.source_tree_digest(scanned_files) != corpus["source_tree_sha256"]:
        raise ValueError("common test source tree differs")
    map_raw = (repository / full_corpus.MAP_PATH).read_bytes()
    map_rows = list(csv.DictReader(io.StringIO(map_raw.decode()), delimiter="\t"))
    if map_rows != corpus["original_mappings"] or len(map_rows) != 2385:
        raise ValueError("reviewed original map differs")
    pair_raw = (repository / full_corpus.PAIR_PATH).read_bytes()
    if (digest(pair_raw) != full_corpus.REVIEWED_PAIRS_SHA256 or
            pair_raw != full_corpus.paired_bytes(map_rows)):
        raise ValueError("independently reviewed pair map differs")
    if (len(corpus["jvm_only"]) != 32 or
            {row["original"] for row in corpus["jvm_only"]} !=
            {row["original"] for row in map_rows if row["disposition"] == "JVM_ONLY"}):
        raise ValueError("JVM-only original dispositions differ")
    if full_corpus.make_manifest(scanned, map_rows, production=True,
                                 repository=repository) != corpus:
        raise ValueError("common corpus case or original disposition differs")
    return corpus, {"corpus_sha256": digest(raw),
                    "source_tree_sha256": corpus["source_tree_sha256"],
                    "original_map_sha256": digest(map_raw),
                    "reviewed_pairs_sha256": digest(pair_raw),
                    "original_revision": full_corpus.ORIGINAL_REVISION}


def build_manifest(repository):
    corpus, bindings = read_corpus(repository)
    if any(not (Path(repository) / path).is_file()
           for paths in GATE_SOURCES.values() for path in paths):
        raise ValueError("independent gate source is absent")
    cases = []
    for source in corpus["cases"]:
        scope = "portable" if source["source_set"] == "commonTest" else "jvm-only"
        cases.append({"id": f'{source["module"]}:{source["classname"]}#{source["method"]}',
                      "module": source["module"], "classname": source["classname"],
                      "method": source["method"], "area": area_for(source),
                      "scope": scope, "kind": source["kind"],
                      "source": {key: source[key] for key in ("path", "sha256", "line")},
                      "originals": source["originals"]})
    cases.sort(key=lambda case: case["id"])
    targets = {row["target"]: {"case_scopes": (["portable", "jvm-only"]
                                                   if row["target"] == "jvm" else ["portable"])}
               for row in qualify.matrix()}
    lanes = {}
    for lane in qualify.expand(qualify.matrix()):
        target = lane["target"]
        lanes[lane["id"]] = {"target": target,
                             "runtime": lane["runtime"], "version": lane["version"],
                             "configuration": lane["configuration"],
                             "case_scopes": targets[target]["case_scopes"],
                             "required_gates": list(LANE_GATES + (JVM_GATES if target == "jvm" else ())) }
    return {"schema": 1, "kind": "complete-port", "id": "full-common-0681a8cd",
            "areas": list(AREA_IDS), "bindings": bindings, "cases": cases,
            "targets": targets, "lanes": lanes,
            "independent_gates": {
                name: {"requirement": GATE_DESCRIPTIONS[name],
                       "evidence_sources": list(GATE_SOURCES[name])}
                for name in GATE_DESCRIPTIONS},
            "global_gates": list(GLOBAL_GATES),
            "counts": {"portable_methods": 2523, "jvm_only_facade_methods": 3,
                       "mapped_original_identities": 2353,
                       "body_related_supplements": 5,
                       "jvm_only_original_dispositions": 32}}


def validate_manifest(manifest, repository):
    if not isinstance(manifest, dict):
        raise ValueError("complete suite manifest must be an object")
    expected = build_manifest(repository)
    if manifest != expected:
        raise ValueError("complete suite differs from reviewed cases, lanes, bindings, or gates")
    identities = [case["id"] for case in manifest["cases"]]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate complete suite case")
    if set(manifest["areas"]) != {case["area"] for case in manifest["cases"]}:
        raise ValueError("complete suite area is empty")
    return True


def select_lane(manifest, lane_id, repository):
    validate_manifest(manifest, repository)
    if lane_id not in manifest["lanes"]:
        raise ValueError(f"unknown required lane: {lane_id}")
    lane = manifest["lanes"][lane_id]
    selected = [case["id"] for case in manifest["cases"]
                if case["scope"] in lane["case_scopes"]]
    if not selected or len(selected) != len(set(selected)):
        raise ValueError("empty or duplicate selected suite")
    return {"lane_id": lane_id, "case_ids": selected,
            "required_gates": list(lane["required_gates"]),
            "global_gates": list(manifest["global_gates"])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("generate", "validate", "select"))
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--lane-id")
    args = parser.parse_args()
    path = args.repository / MANIFEST_PATH
    if args.command == "generate":
        path.write_text(json.dumps(build_manifest(args.repository), indent=2) + "\n")
    else:
        manifest = json.loads(path.read_text())
        if args.command == "validate":
            validate_manifest(manifest, args.repository)
        else:
            print(json.dumps(select_lane(manifest, args.lane_id, args.repository)))


if __name__ == "__main__":
    main()
