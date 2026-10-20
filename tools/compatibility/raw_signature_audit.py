from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "baseline"))
import verify as oracle
import candidate_coverage
import common_corpus_receipt
import signature_index


ANONYMOUS_CASES = {
    "org.dyn4j.collision.Filter$1": "org.dyn4j.collision.DefaultFilterTest#filter",
    "org.dyn4j.collision.manifold.ManifoldPointId$1": "org.dyn4j.collision.manifold.ManifoldPointIdTest#create",
    "org.dyn4j.world.ValueMixer$1": "org.dyn4j.world.ValueMixerTest#mixFriction",
    "org.dyn4j.collision.broadphase.DynamicAABBTree$1":
        "org.dyn4j.collision.broadphase.CollisionBodyBroadphaseTest#optimize[tree_tracked]",
}
CATEGORIES = {"strict-source-visible": 110, "internal-type-header": 26,
              "package-documentation": 16, "anonymous-behavior": 4}
BASELINE_JAR = Path("/tmp/dyn4k-baseline-cache/dyn4j-6.0.0.jar")
MAP = Path("tools/qualification/full-common-original-map.tsv")
MANIFEST = Path("tools/qualification/full-common-corpus.json")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> str:
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def checked_common_gate(ledger: dict, root: Path) -> dict:
    record = ledger["review_receipts"]["common_corpus"]
    name = record.get("path")
    if (not isinstance(name, str) or not name or Path(name).is_absolute()
            or ".." in Path(name).parts):
        raise ValueError("common behavior gate path is missing or unsafe")
    base = root.resolve()
    path = (base / name).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise ValueError("common behavior gate path is missing or unsafe")
    data = path.read_bytes()
    if digest(data) != record.get("sha256"):
        raise ValueError("common behavior gate hash differs")
    gate = json.loads(data)
    if not isinstance(gate, dict):
        raise ValueError("common behavior gate is invalid")
    gate_error = common_corpus_receipt.verify(gate, ledger, root)
    if gate_error:
        raise ValueError(f"common behavior gate differs: {gate_error}")
    return gate


def checked_original_sources(ledger: dict, source: Path) -> None:
    if candidate_coverage.git(source, "rev-parse", "HEAD") != ledger["baseline"]["commit"]:
        raise ValueError("pinned source revision differs")
    for section in ("production", "tests"):
        for row in ledger[section]:
            path = source / row["id"]
            if not path.is_file() or candidate_coverage.digest(path) != row["sha256"]:
                raise ValueError(f"pinned source hash differs: {row['id']}")


def package_documentation(source: Path, row: dict) -> bool:
    text = (source / row["source_file"]).read_text()
    without_comments = re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.DOTALL)
    package = row["id"].split("|")[0].removesuffix(".package-info")
    return re.fullmatch(r"\s*package\s+" + re.escape(package) + r"\s*;\s*",
                        without_comments) is not None


def checked_anonymous_case(root: Path, name: str) -> dict:
    with (root / MAP).open(newline="") as stream:
        matches = [row for row in csv.DictReader(stream, delimiter="\t")
                   if row["original"] == ANONYMOUS_CASES[name]]
    if len(matches) != 1 or matches[0]["disposition"] != "PORTABLE":
        raise ValueError(f"anonymous behavior has no reviewed original case: {name}")
    mapping = matches[0]
    manifest = json.loads((root / MANIFEST).read_text())
    if len(manifest["original_mappings"]) != 2385 or mapping not in manifest["original_mappings"]:
        raise ValueError(f"anonymous behavior mapping differs from sealed common corpus: {name}")
    cases = [case for case in manifest["cases"]
             if case["classname"] == mapping["classname"] and case["method"] == mapping["method"]]
    if len(cases) != 1 or set(cases[0]["hosts"]) != {
            "jvm", "linuxX64", "jsNode", "wasmJsNode", "wasmWasiNode", "androidHost"}:
        raise ValueError(f"anonymous behavior common case or host set differs: {name}")
    case = cases[0]
    if candidate_coverage.digest(root / case["path"]) != case["sha256"]:
        raise ValueError(f"anonymous behavior candidate source differs: {name}")
    return {"original": mapping["original"], "common_class": case["classname"],
            "common_method": case["method"], "test_source": case["path"],
            "test_source_sha256": case["sha256"], "line": case["line"],
            "hosts": case["hosts"]}


def classify(ledger: dict, signature: dict, strict: dict, root: Path,
             baseline_source: Path) -> dict:
    root = root.resolve()
    checked_original_sources(ledger, baseline_source)
    source = ledger["candidate_source"]
    jar = root / source["artifact"]
    if (candidate_coverage.digest(jar) != source["artifact_sha256"]
            or source["artifact_sha256"] == ledger["baseline"]["binary_sha256"]
            or signature.get("baseline") != ledger["baseline"]
            or signature.get("candidate_commit") != source["revision"]
            or signature.get("source_tree") != source["tree"]
            or signature.get("artifact_sha256") != source["artifact_sha256"]):
        raise ValueError("signature candidate source or artifact identity differs")
    if (strict.get("baseline_sha256") != ledger["baseline"]["binary_sha256"]
            or strict.get("candidate_sha256") != source["artifact_sha256"]
            or strict.get("compared_baseline_declarations") != 3078
            or len(strict.get("compared_api_types", [])) != 216
            or any(strict.get(key) for key in ("missing_types", "signature_mismatches",
                                               "added_member_risks", "inventory_errors",
                                               "fixture_failures", "fixture_errors"))):
        raise ValueError("strict source-visible comparison is missing, changed, or failed")
    rows = ledger["declarations"]
    by_id = {row["id"]: row for row in rows}
    outcomes = signature["index"]["outcomes"]
    if (len(by_id) != 3508 or set(by_id) != set(outcomes)
            or signature["index"].get("checked_identities") != 3508):
        raise ValueError("raw signature identity inventory differs")
    classes = {entry["name"]: entry for entry in signature["index"]["classes"]}
    type_rows = {row["id"].split("|")[0]: row for row in rows if row["id"].endswith("|type")}
    visible = set(strict["compared_api_types"])
    compatible = strict["compatible_differences"]
    audited = []
    gate = checked_common_gate(ledger, root)
    for identity in sorted(by_id):
        if outcomes[identity]["passed"]:
            continue
        row = by_id[identity]
        candidate = row.get("candidate")
        if not isinstance(candidate, dict):
            raise ValueError(f"candidate source mapping is missing: {identity}")
        source_error = candidate_coverage.check_source_candidate(candidate, root)
        if source_error:
            raise ValueError(f"candidate source differs: {identity}: {source_error}")
        name = identity.split("|")[0]
        if name not in classes:
            raise ValueError(f"raw javap class record is missing: {name}")
        class_record = classes[name]
        candidate_header = next((line.strip() for line in class_record["raw_stdout"][0].splitlines()
                                 if line.strip().endswith("{")), None)
        differences = [entry for entry in compatible if entry.startswith(name + ":") and
                       (("compatible type difference" in entry) if identity.endswith("|type")
                        else row["signature"] in entry)]
        behavior = None
        if name.endswith(".package-info"):
            if not identity.endswith("|type") or not package_documentation(baseline_source, row):
                raise ValueError(f"pinned source package documentation differs: {identity}")
            category = "package-documentation"
            rule = "package-documentation-only"
            interpretation = "Pinned Java source declares only its package and comments; no Kotlin package-info class is asserted."
        elif name in ANONYMOUS_CASES:
            if not identity.endswith("|type"):
                raise ValueError(f"anonymous behavior member needs review: {identity}")
            path, marker = candidate_coverage.ANONYMOUS_BEHAVIORS[name]
            if (not any(item["path"] == path for item in candidate["sources"])
                    or marker not in (root / path).read_text()):
                raise ValueError(f"candidate anonymous behavior source differs: {identity}")
            behavior = checked_anonymous_case(root, name)
            category = "anonymous-behavior"
            rule = "anonymous-class-replaced"
            interpretation = "Generated Java anonymous type maps to the cited Kotlin expression and reviewed executable case; the raw class name is absent."
        elif len(differences) == 1:
            category = "strict-source-visible"
            before, after = differences[0].split(" -> ", 1)
            if identity.endswith("|type"):
                old = before.split("compatible type difference: ", 1)[1]
                if (name == "org.dyn4j.BinarySearchTree"
                        and after == old + ", kotlin.jvm.internal.markers.KMappedMarker"):
                    rule = "kotlin-iterable-marker"
                    interpretation = "Kotlin adds KMappedMarker to the unchanged Iterable interface; the Java generic Iterable contract remains."
                else:
                    rule = "inherited-interface-spelling"
                    interpretation = "A directly spelled baseline interface is inherited by the candidate; the strict generic type-closure check accepts it."
            else:
                old = before.split("compatible member difference: ", 1)[1]
                if (after == old.replace("public ", "public final ", 1)
                        and type_rows[name]["signature"].startswith("public final class ")):
                    rule = "final-member-on-final-owner"
                    interpretation = "Kotlin marks this method final on a baseline-final class, so no Java subclass can override it."
                elif ("AbstractJoint" in name and
                      after == old.replace("java.util.List<T>", "java.util.List<? extends T>")):
                    rule = "constructor-list-wildcard-widening"
                    interpretation = "The constructor keeps its JVM descriptor and widens the List input to extends T; Java source accepts the original List<T>."
                else:
                    raise ValueError(f"unreviewed strict member modifier or generic change: {identity}")
        elif identity.endswith("|type") and name not in visible and not differences:
            category = "internal-type-header"
            if candidate_header == row["signature"].removesuffix(" {") + ", kotlin.jvm.internal.markers.KMutableIterator {":
                rule = "kotlin-mutable-iterator-marker"
                interpretation = "Package-private final iterator keeps its Iterator<T> contract; Kotlin adds KMutableIterator."
            elif candidate_header == "public " + row["signature"] and name == "org.dyn4j.dynamics.contact.SolvableContact":
                rule = "visibility-widened"
                interpretation = "The candidate makes a baseline package-private final contact class public; its declared interfaces and generic header remain."
            elif name == "org.dyn4j.world.CollisionItemAdapter" and candidate_header and (
                    candidate_header == row["signature"].replace(
                        " implements org.dyn4j.collision.CollisionItem<T, E>", "")):
                parent = classes["org.dyn4j.collision.AbstractCollisionItem"]["raw_stdout"][0]
                if "implements org.dyn4j.collision.CollisionItem<T, E>" not in parent:
                    raise ValueError("internal adapter inherited interface is absent")
                rule = "inherited-interface-spelling"
                interpretation = "The adapter inherits CollisionItem<T,E> from AbstractCollisionItem instead of repeating it in its header."
            else:
                raise ValueError(f"unreviewed internal type header: {identity}")
        else:
            raise ValueError(f"unclassified raw signature difference: {identity}")
        members = {key: value for key, value in outcomes.items()
                   if key.startswith(name + "|") and key != identity}
        if category == "strict-source-visible":
            acceptance = "source-compatible"
            acceptance_evidence = {
                "kind": "strict-source-visible-comparison",
                "strict_difference": differences[0],
                "strict_comparison_sha256": canonical(strict),
            }
        elif category == "internal-type-header":
            if not all(value["passed"] for value in members.values()):
                raise ValueError(f"internal type has a differing member: {identity}")
            acceptance = ("source-compatible" if rule == "visibility-widened"
                          else "internal-behavior-equivalent")
            acceptance_evidence = {
                "kind": "classfile-header-and-member-inventory",
                "passed_member_ids": sorted(members),
                "candidate_header": candidate_header,
                "source_sha256": [entry["sha256"] for entry in candidate["sources"]],
            }
        elif category == "package-documentation":
            package_line = "package " + name.removesuffix(".package-info")
            if not any(package_line in (root / entry["path"]).read_text()
                       and "Copyright" in (root / entry["path"]).read_text()
                       and "Redistribution and use" in (root / entry["path"]).read_text()
                       for entry in candidate["sources"]):
                raise ValueError(f"candidate package or legal notice is missing: {identity}")
            acceptance = "documentation-only"
            acceptance_evidence = {
                "kind": "pinned-package-and-legal-source",
                "baseline_source_sha256": next(item["sha256"] for item in ledger["production"]
                                                       if item["id"] == row["source_file"]),
                "candidate_sources": candidate["sources"],
            }
        else:
            acceptance = "internal-behavior-equivalent"
            acceptance_evidence = {
                "kind": "executed-original-common-case",
                "behavior_case": behavior,
                "common_gate_result_sha256": gate["result_sha256"],
                "common_gate_binding_sha256": gate["binding_sha256"],
            }
        audited.append({"id": identity, "category": category, "baseline_source": row["source_file"],
                        "baseline_source_sha256": next(item["sha256"] for item in ledger["production"]
                                                       if item["id"] == row["source_file"]),
                        "baseline_signature": row["signature"], "baseline_flags": row.get("flags"),
                        "candidate_header": candidate_header, "difference_rule": rule,
                        "candidate_sources": candidate["sources"],
                        "javap_exit_codes": class_record["process_exit_codes"],
                        "javap_stdout_sha256": [digest(value.encode()) for value in class_record["raw_stdout"]],
                        "strict_difference": differences[0] if differences else None,
                        "behavior_case": behavior, "interpretation": interpretation,
                        "raw_obligation_status": "unpassed",
                        "acceptance_disposition": acceptance,
                        "acceptance_evidence": acceptance_evidence})
    counts = Counter(row["category"] for row in audited)
    if len(audited) != 156 or dict(counts) != CATEGORIES:
        raise ValueError(f"raw difference category totals differ: {dict(counts)}")
    return {"schema_version": 1, "candidate_revision": source["revision"],
            "candidate_tree": source["tree"], "candidate_jar_sha256": source["artifact_sha256"],
            "baseline_revision": ledger["baseline"]["commit"],
            "baseline_jar_sha256": ledger["baseline"]["binary_sha256"],
            "signature_index_sha256": canonical(signature["index"]),
            "strict_comparison_sha256": canonical(strict),
            "categories": dict(sorted(counts.items())), "rows": audited}


def check(audit: dict, ledger: dict, signature: dict, strict: dict, root: Path,
          baseline_source: Path) -> str | None:
    try:
        expected = classify(ledger, signature, strict, root, baseline_source)
        if audit != expected:
            return "raw difference audit differs from pinned source and executed inventories"
        jar = root / ledger["candidate_source"]["artifact"]
        error = signature_index.validate_report(signature, ledger, jar, root)
        if error:
            return error
        dependencies = []
        for name, checksum in strict["dependency_sha256"].items():
            path = Path(name)
            if not path.is_file() or candidate_coverage.digest(path) != checksum:
                return f"strict dependency missing or changed: {name}"
            dependencies.append(path)
        if (not BASELINE_JAR.is_file()
                or candidate_coverage.digest(BASELINE_JAR) != ledger["baseline"]["binary_sha256"]):
            return "pinned baseline JAR missing or changed"
        observed = oracle.compare_jars(BASELINE_JAR, jar, dependencies=dependencies)
        if observed != strict:
            return "strict source-visible comparison differs from replay"
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        return f"raw difference audit replay failed: {error}"
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify every exact JVM signature difference without promoting raw passes.")
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--signature", type=Path, required=True)
    parser.add_argument("--strict", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--baseline-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("audit output exists")
    import gzip
    ledger = json.loads(args.ledger.read_text())
    signature = json.loads(gzip.decompress(args.signature.read_bytes()))
    strict = json.loads(args.strict.read_text())
    audit = classify(ledger, signature, strict, args.root, args.baseline_source)
    error = check(audit, ledger, signature, strict, args.root, args.baseline_source)
    if error:
        parser.error(error)
    args.output.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(json.dumps(audit["categories"], sort_keys=True))


if __name__ == "__main__":
    main()
