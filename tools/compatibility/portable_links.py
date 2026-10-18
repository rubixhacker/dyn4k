from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import candidate_coverage
import common_corpus_receipt


MAP = Path("tools/qualification/full-common-original-map.tsv")
MANIFEST = Path("tools/qualification/full-common-corpus.json")
ANONYMOUS_CASES = {
    "org.dyn4j.collision.Filter$1|type": "org.dyn4j.collision.DefaultFilterTest#filter",
    "org.dyn4j.collision.manifold.ManifoldPointId$1|type":
        "org.dyn4j.collision.manifold.ManifoldPointIdTest#create",
    "org.dyn4j.world.ValueMixer$1|type": "org.dyn4j.world.ValueMixerTest#mixFriction",
    "org.dyn4j.collision.broadphase.DynamicAABBTree$1|type":
        "org.dyn4j.collision.broadphase.CollisionBodyBroadphaseTest#optimize[tree_tracked]",
}


def common_status(sources: list[dict]) -> str:
    common = any("/commonMain/" in source["path"] for source in sources)
    jvm = any("/jvmMain/" in source["path"] for source in sources)
    return ("common-expect-and-jvm-actual" if common and jvm else
            "common" if common else "jvm-only")


def make(ledger: dict, gate: dict, root: Path, upstream: Path) -> dict:
    root = root.resolve()
    upstream = upstream.resolve()
    error = common_corpus_receipt.verify(gate, ledger, root)
    if error:
        raise ValueError(error)
    if candidate_coverage.git(upstream, "rev-parse", "HEAD") != ledger["baseline"]["commit"]:
        raise ValueError("pinned original source revision differs")
    production = {row["id"]: row for row in ledger["production"]}
    tests = {row["id"]: row for row in ledger["tests"]}
    if len(production) != 268 or len(tests) != 199:
        raise ValueError("pinned production or Java test identity count differs")
    for section in (production, tests):
        for name, row in section.items():
            if not (upstream / name).is_file() or candidate_coverage.digest(upstream / name) != row["sha256"]:
                raise ValueError(f"pinned original source hash differs: {name}")
    with (root / MAP).open(newline="") as stream:
        mappings = list(csv.DictReader(stream, delimiter="\t"))
    manifest = json.loads((root / MANIFEST).read_text())
    counts = manifest["counts"]
    if (mappings != manifest["original_mappings"] or len(mappings) != 2385
            or counts["mapped_original_identities"] != 2353
            or counts["jvm_only_original_identities"] != 32
            or counts["mapped_original_methods"] != 2253
            or counts["related_supplemental_methods"] != 5):
        raise ValueError("sealed original-to-common mapping differs")
    source_cache = {}
    source_lines = {}
    def checked_source(record: dict) -> None:
        path, checksum = record["path"], record["sha256"]
        if path not in source_cache:
            source_cache[path] = (candidate_coverage.digest(root / path),
                                  candidate_coverage.committed_sha(root,
                                      ledger["candidate_source"]["revision"], path))
        if source_cache[path] != (checksum, checksum):
            raise ValueError(f"candidate source hash differs: {path}")
        source_lines.setdefault(path, (root / path).read_text().splitlines())

    def declaration_anchors(row: dict, sources: list[dict]) -> list[dict]:
        identity = row["id"]
        owner, member, *_ = identity.split("|")
        short_type = owner.rsplit(".", 1)[-1].rsplit("$", 1)[-1]
        markers = []
        enum_owner = any(re.search(r"\benum\s+class\s+" + re.escape(short_type) + r"\b", line)
                         for source in sources for line in source_lines[source["path"]])
        if owner.endswith(".package-info"):
            package = owner.removesuffix(".package-info")
            markers.append((re.compile(r"^\s*package\s+" + re.escape(package) + r"\s*$"),
                            "package-declaration"))
        elif owner in candidate_coverage.ANONYMOUS_BEHAVIORS:
            marker = candidate_coverage.ANONYMOUS_BEHAVIORS[owner][1]
            markers.append((re.compile(re.escape(marker)), "anonymous-expression"))
        elif member == "type":
            markers.append((re.compile(r"\b(?:class|interface|object)\s+" +
                                       re.escape(short_type) + r"\b"), "type-declaration"))
        elif enum_owner and member in {"values", "valueOf"}:
            markers.append((re.compile(r"\benum\s+class\s+" +
                                       re.escape(short_type) + r"\b"),
                            "compiler-generated-enum-member"))
        elif enum_owner and not identity.split("|", 2)[2].strip():
            markers.append((re.compile(r"\b" + re.escape(member) + r"\b"), "enum-entry"))
        else:
            simple = member.rsplit(".", 1)[-1]
            if simple == short_type:
                markers.append((re.compile(r"\bconstructor\s*\("), "constructor-declaration"))
                markers.append((re.compile(r"\b(?:class|interface|object)\s+" +
                                           re.escape(short_type) + r"\b"), "primary-constructor-owner"))
            else:
                markers.append((re.compile(r"\b(?:fun(?:\s+<.*>)?|val|var)\s+" +
                                           re.escape(simple) + r"\b"), "member-declaration"))
                if simple.startswith(("get", "set", "is")):
                    stem = simple[3:] if simple[:3] in ("get", "set") else simple[2:]
                    if stem:
                        property_name = stem[0].lower() + stem[1:]
                        markers.append((re.compile(r"\b(?:val|var)\s+" +
                                                   re.escape(property_name) + r"\b"),
                                        "property-backed-member"))
        anchors = []
        for source in sources:
            for line_number, line in enumerate(source_lines[source["path"]], 1):
                if line.lstrip().startswith(("//", "*")):
                    continue
                for marker, relation in markers:
                    if marker.search(line):
                        anchors.append({"path": source["path"], "sha256": source["sha256"],
                                        "line": line_number, "text": line.strip(),
                                        "relation": relation})
                        break
        return anchors

    cases = {(case["classname"], case["method"]): case for case in manifest["cases"]}
    if len(cases) != len(manifest["cases"]):
        raise ValueError("common test method identity is duplicate")
    by_original = {row["original"]: row for row in mappings}
    by_test = defaultdict(list)
    for mapping in mappings:
        source_name = mapping["original_source"]
        if source_name not in tests or mapping["original_sha256"] != tests[source_name]["sha256"]:
            raise ValueError(f"original Java test input differs: {source_name}")
        if mapping["disposition"] == "PORTABLE":
            case = cases.get((mapping["classname"], mapping["method"]))
            if (case is None or mapping["original"] not in case["originals"]
                    or case["kind"] != "mapped-original"
                    or len(case["hosts"]) != 6):
                raise ValueError(f"reviewed portable case or host set differs: {mapping['original']}")
            checked_source({"path": case["path"], "sha256": case["sha256"]})
            by_test[source_name].append(mapping)
        elif mapping["disposition"] != "JVM_ONLY":
            raise ValueError(f"unreviewed original case: {mapping['original']}")

    def test_link(mapping: dict, relation: str) -> dict:
        case = cases[mapping["classname"], mapping["method"]]
        return {"original": mapping["original"], "original_source": mapping["original_source"],
                "original_source_sha256": mapping["original_sha256"],
                "original_line": int(mapping["original_line"]),
                "candidate_class": case["classname"], "candidate_method": case["method"],
                "candidate_test_source": case["path"],
                "candidate_test_source_sha256": case["sha256"],
                "candidate_test_line": case["line"], "hosts": case["hosts"],
                "relation": relation}

    def owner_test(source_file: str) -> str:
        return source_file.replace("src/main/java/", "src/test/java/").replace(".java", "Test.java")

    production_links = []
    for row in ledger["production"]:
        candidate = row.get("candidate")
        if not isinstance(candidate, dict):
            raise ValueError(f"candidate implementation mapping is missing: {row['id']}")
        for source in candidate["sources"]:
            checked_source(source)
        related = by_test.get(owner_test(row["id"]), [])
        production_links.append({"id": row["id"], "original_sha256": row["sha256"],
                                 "candidate_sources": candidate["sources"],
                                 "candidate_source_identity": candidate["identity"],
                                 "mapped_baseline_ids": candidate.get("mapped_baseline_ids"),
                                 "common_source_status": common_status(candidate["sources"]),
                                 "behavior_tests": [test_link(mapping, "owner-test-context")
                                                    for mapping in related],
                                 "link_status": ("package-documentation-only" if row["id"].endswith("/package-info.java")
                                                 else "owner-test-context" if related else "no-direct-original-test"),
                                 "qualification_status": "UNPASSED"})

    declaration_links = []
    for row in ledger["declarations"]:
        candidate = row.get("candidate")
        if not isinstance(candidate, dict):
            raise ValueError(f"candidate declaration mapping is missing: {row['id']}")
        for source in candidate["sources"]:
            checked_source(source)
        related = by_test.get(owner_test(row["source_file"]), [])
        member = row["id"].split("|")[1]
        direct = [mapping for mapping in related
                  if mapping["original"].split("#", 1)[1].split("[", 1)[0].lower() == member.lower()]
        if row["id"] in ANONYMOUS_CASES:
            direct = [by_original[ANONYMOUS_CASES[row["id"]]]]
            status = "reviewed-anonymous-behavior"
        elif row["id"].endswith(".package-info|type"):
            status = "package-documentation-only"
        elif direct:
            status = "name-matched-original-case"
        elif related:
            status = "owner-test-context"
        else:
            status = "no-direct-original-test"
        declaration_links.append({"id": row["id"], "original_source": row["source_file"],
                                  "original_source_sha256": production[row["source_file"]]["sha256"],
                                  "baseline_signature": row["signature"],
                                  "baseline_flags": row.get("flags"),
                                  "candidate_sources": candidate["sources"],
                                  "candidate_declaration_anchors": declaration_anchors(row, candidate["sources"]),
                                  "common_source_status": common_status(candidate["sources"]),
                                  "behavior_tests": [test_link(mapping, "name-matched-original-case"
                                                               if status == "name-matched-original-case"
                                                               else "reviewed-anonymous-behavior")
                                                     for mapping in direct],
                                  "owner_context_cases": len(related),
                                  "link_status": status,
                                  "qualification_status": "UNPASSED"})
    return {"schema_version": 1, "candidate_revision": ledger["candidate_source"]["revision"],
            "candidate_tree": ledger["candidate_source"]["tree"],
            "candidate_artifact_sha256": ledger["candidate_source"]["artifact_sha256"],
            "common_gate_result_sha256": gate["result_sha256"],
            "common_gate_binding_sha256": gate["binding_sha256"],
            "original_identity_counts": {"portable": 2353, "jvm_only": 32,
                                         "mapped_common_methods": 2253,
                                         "related_body_supplements": 5},
            "production_link_counts": dict(sorted(Counter(row["link_status"]
                                                  for row in production_links).items())),
            "declaration_link_counts": dict(sorted(Counter(row["link_status"]
                                                   for row in declaration_links).items())),
            "declaration_anchor_counts": dict(sorted(Counter(
                "anchored" if row["candidate_declaration_anchors"] else "source-file-only"
                for row in declaration_links).items())),
            "qualification_status": "MAPPED_UNPASSED",
            "production": production_links, "declarations": declaration_links}


def check(report: dict, ledger: dict, gate: dict, root: Path, upstream: Path) -> str | None:
    try:
        if report != make(ledger, gate, root, upstream):
            return "portable links differ from pinned source, candidate, or executed gate"
    except (OSError, ValueError, KeyError, TypeError) as error:
        return f"portable links replay failed: {error}"
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Map every declaration and implementation to reviewed common test context.")
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("portable link output exists")
    report = make(json.loads(args.ledger.read_text()), json.loads(args.gate.read_text()),
                  args.root, args.upstream)
    encoded = (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if args.output.suffix == ".gz":
        with args.output.open("wb") as output:
            with gzip.GzipFile(filename="", mode="wb", fileobj=output,
                               compresslevel=9, mtime=0) as stream:
                stream.write(encoded)
    else:
        args.output.write_bytes(encoded)
    print(json.dumps({"production": report["production_link_counts"],
                      "declarations": report["declaration_link_counts"]}, sort_keys=True))


if __name__ == "__main__":
    main()
