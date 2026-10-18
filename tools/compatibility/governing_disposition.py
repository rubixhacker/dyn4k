from __future__ import annotations

import argparse
import gzip
import json
import re
import subprocess
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import candidate_coverage
import method_coverage
import governing_seams


def receipt(root: Path, record: dict) -> dict:
    path = method_coverage.safe_path(root, record["path"])
    if candidate_coverage.digest(path) != record["sha256"]:
        raise ValueError(f"governing input receipt differs: {record['path']}")
    content = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
    return json.loads(content)


def owner_sources(root: Path, ledger: dict, classes: set[str]) -> dict[str, list[dict]]:
    revision = ledger["candidate_source"]["revision"]
    index = candidate_coverage.source_index(root, revision)
    result = {}
    with zipfile.ZipFile(root / ledger["candidate_source"]["artifact"]) as archive:
        for owner in classes:
            name = owner + ".class"
            if name not in archive.namelist():
                continue
            source_file = candidate_coverage.class_source_file(archive.read(name))
            if source_file is None:
                continue
            package = owner.rpartition("/")[0].replace("/", ".")
            result[owner] = [candidate_coverage.source_record(root, revision, path)
                             for path in index.get((package, source_file), [])]
    return result


def parameter_descriptor(descriptor: str) -> str:
    if not descriptor.startswith("(") or ")" not in descriptor:
        raise ValueError("method descriptor is invalid")
    return descriptor.split(")", 1)[0] + ")"


def pure_forwarder(opcodes: list[int], candidate_flags: int, baseline_flags: list[str],
                   signature: str, invocation_count: int) -> bool:
    bridge = "ACC_BRIDGE" in baseline_flags
    visibility = (0x0001 if "ACC_PUBLIC" in baseline_flags else
                  0x0004 if "ACC_PROTECTED" in baseline_flags else 0)
    if (not visibility or candidate_flags & 0x0005 != visibility
            or invocation_count != 1 or len(opcodes) < 2
            or opcodes[-1] not in range(172, 178)
            or sum(opcode in range(182, 186) for opcode in opcodes) != 1):
        return False
    if bridge:
        if candidate_flags & 0x1040 != 0x1040 or " static " in signature:
            return False
    elif candidate_flags & 0x0008 == 0 or " static " not in signature:
        return False
    return all(opcode in {*range(21, 26), 178, 180, 192, *range(182, 186)}
               for opcode in opcodes[:-1])


def make(ledger: dict, root: Path, upstream: Path) -> dict:
    root = root.resolve()
    receipts = ledger["review_receipts"]
    raw = receipt(root, receipts["raw_signature"])
    links = receipt(root, receipts["portable_links"])
    coverage = receipt(root, receipts["method_coverage"])
    seams = receipt(root, receipts["governing_seams"])
    gate = receipt(root, receipts["common_corpus"])
    strict_path = method_coverage.safe_path(root, receipts["raw_signature"]["strict"])
    strict = json.loads(strict_path.read_text())
    source = ledger["candidate_source"]
    if (raw["candidate_revision"] != source["revision"]
            or raw["candidate_jar_sha256"] != source["artifact_sha256"]
            or links["candidate_revision"] != source["revision"]
            or links["candidate_artifact_sha256"] != source["artifact_sha256"]
            or coverage["candidate_revision"] != source["revision"]
            or coverage["candidate_artifact_sha256"] != source["artifact_sha256"]
            or seams["candidate_revision"] != source["revision"]
            or seams["candidate_artifact_sha256"] != source["artifact_sha256"]
            or gate["candidate_revision"] != source["revision"]
            or gate["candidate_artifact_sha256"] != source["artifact_sha256"]
            or strict["candidate_sha256"] != source["artifact_sha256"]
            or any(strict.get(key) for key in ("missing_types", "signature_mismatches",
                                               "added_member_risks", "inventory_errors",
                                               "fixture_failures", "fixture_errors"))):
        raise ValueError("governing candidate or source-visible evidence differs")
    if (len(ledger["production"]) != 268 or len(ledger["tests"]) != 199
            or len(ledger["declarations"]) != 3508
            or len(links["production"]) != 268 or len(links["declarations"]) != 3508
            or len(raw["rows"]) != 156
            or coverage["actual_executed_cases_per_lane"] != 2385
            or coverage["candidate_lanes"] != 4):
        raise ValueError("governing original or executed inventory differs")
    if candidate_coverage.git(upstream, "rev-parse", "HEAD") != ledger["baseline"]["commit"]:
        raise ValueError("governing pinned source revision differs")
    if candidate_coverage.digest(root / source["artifact"]) != source["artifact_sha256"]:
        raise ValueError("governing candidate artifact differs")
    for section in ("production", "tests"):
        for row in ledger[section]:
            if candidate_coverage.digest(upstream / row["id"]) != row["sha256"]:
                raise ValueError(f"governing pinned source differs: {row['id']}")
    raw_by_id = {row["id"]: row for row in raw["rows"]}
    link_by_id = {row["id"]: row for row in links["declarations"]}
    production_links = {row["id"]: row for row in links["production"]}
    if (len(raw_by_id) != 156 or len(link_by_id) != 3508
            or len(production_links) != 268
            or any(row["raw_obligation_status"] != "unpassed"
                   or row["acceptance_disposition"] not in {
                       "source-compatible", "internal-behavior-equivalent", "documentation-only"}
                   or not row["acceptance_evidence"] for row in raw["rows"])):
        raise ValueError("governing raw acceptance or source link inventory differs")
    java = {key: row for row in coverage["methods"]
            for key in [(row["owner"], row["name"], row["descriptor"])]}
    seam_hits = {tuple(identity.split("|", 2)) for identity in seams["observed_method_ids"]}
    if len(java) != coverage["method_count"]:
        raise ValueError("governing method identity is duplicate")
    if len(seam_hits) != len(seams["observed_method_ids"]):
        raise ValueError("governing seam method identity is duplicate")
    jdk21 = Path(receipt(root, {"path": coverage["original_corpus"],
                                "sha256": coverage["original_corpus_sha256"]})
                 ["tools"]["21"]["java"]["path"]).parent.parent
    classes, methods, invokes, opcodes = method_coverage.dispatch_inventory(
        root / source["artifact"], coverage["tools"], jdk21)
    source_by_owner = owner_sources(root, ledger, set(classes))
    source_hits = defaultdict(list)
    for key in set(seam_hits) | {key for key, hit in java.items()
                                if hit["covered_instructions"] > 0}:
        for source_record in source_by_owner.get(key[0], []):
            source_hits[source_record["path"]].append(key)

    ancestors = {}
    def lineage(owner: str) -> set[str]:
        if owner not in ancestors:
            seen, todo = set(), [owner]
            while todo:
                name = todo.pop()
                if name in seen:
                    continue
                seen.add(name)
                entry = classes.get(name)
                if entry:
                    todo.extend(([entry["parent"]] if entry["parent"] else [])
                                + entry["interfaces"])
            ancestors[owner] = seen
        return ancestors[owner]

    concrete = {owner for owner, item in classes.items() if not item["access"] & 0x400}
    subtypes = defaultdict(list)
    for owner in concrete:
        for parent in lineage(owner):
            subtypes[parent].append(owner)
    methods_by_owner_name_param = defaultdict(list)
    for key, flags in methods.items():
        if key[2].startswith("("):
            methods_by_owner_name_param[key[0], key[1], parameter_descriptor(key[2])].append(
                (key, flags))

    def hit_evidence(key: tuple[str, str, str]) -> dict | None:
        row = java.get(key)
        java_hit = row is not None and row["covered_instructions"] > 0
        if not java_hit and key not in seam_hits:
            return None
        result = {"owner": key[0], "method": key[1], "descriptor": key[2],
                  "candidate_sources": source_by_owner.get(key[0], []),
                  "execution_routes": (["unchanged-java-corpus"] if java_hit else [])
                                      + (["governing-seam-probe"] if key in seam_hits else [])}
        if java_hit:
            result.update({"covered_instructions": row["covered_instructions"],
                           "total_instructions": row["total_instructions"],
                           "unchanged_java_cases_per_lane": 2385})
        else:
            result["governing_seam_fixture_sha256"] = seams["fixture_sha256"]
        return result

    def delegated_hit(key: tuple[str, str, str], baseline_flags: list[str],
                      signature: str) -> dict | None:
        if not pure_forwarder(opcodes.get(key, []), methods.get(key, 0),
                              baseline_flags, signature, len(invokes.get(key, []))):
            return None
        for _, owner, member, descriptor in invokes.get(key, []):
            target = hit_evidence((owner, member, descriptor))
            if target is not None:
                return {"delegating_method": list(key), "target": target}
        return None

    def dispatch_evidence(owner: str, member: str, descriptor: str) -> list[dict]:
        parameter = parameter_descriptor(descriptor)
        found = {}
        for concrete_owner in subtypes.get(owner, []):
            for ancestor in lineage(concrete_owner):
                for key, flags in methods_by_owner_name_param.get(
                        (ancestor, member, parameter), []):
                    evidence = hit_evidence(key)
                    if evidence is None and flags & 0x40:
                        bridge_flags = (["ACC_PUBLIC"] if flags & 0x0001 else
                                        ["ACC_PROTECTED"] if flags & 0x0004 else [])
                        bridge = delegated_hit(key, bridge_flags + ["ACC_BRIDGE"], "")
                        evidence = bridge["target"] if bridge else None
                    if evidence is not None:
                        found[(concrete_owner, evidence["owner"], evidence["method"],
                               evidence["descriptor"])] = {
                                   "concrete_type": concrete_owner,
                                   "executed_implementation": evidence}
        return [found[key] for key in sorted(found)]

    declarations = []
    for row in ledger["declarations"]:
        identity = row["id"]
        link = link_by_id[identity]
        original = next(item for item in ledger["production"]
                        if item["id"] == row["source_file"])
        if (link["original_source_sha256"] != original["sha256"]
                or link["baseline_signature"] != row["signature"]
                or link["candidate_sources"] != row["candidate"]["sources"]
                or not link["candidate_declaration_anchors"]):
            raise ValueError(f"governing declaration source differs: {identity}")
        raw_row = raw_by_id.get(identity)
        if raw_row is None:
            surface = "byte-equal"
            raw_status = "equal"
            surface_evidence = {"kind": "replayed-javap-inventory",
                                "signature": row["signature"], "flags": row.get("flags")}
        else:
            surface = raw_row["acceptance_disposition"]
            raw_status = "unequal"
            surface_evidence = raw_row["acceptance_evidence"]
        owner, member, *extra = identity.split("|")
        owner_class = owner.replace(".", "/")
        behavior = "unresolved"
        evidence = {}
        if surface == "documentation-only":
            behavior = "documentation-only"
            evidence = {"source": original["id"], "sha256": original["sha256"],
                        "candidate_sources": link["candidate_sources"]}
        elif raw_row and raw_row["category"] == "anonymous-behavior":
            behavior = "executed-original-common-case"
            evidence = {"case": raw_row["behavior_case"],
                        "common_gate_sha256": gate["result_sha256"]}
        elif member == "type":
            behavior = "reviewed-non-executable-type"
            evidence = {"signature": row["signature"],
                        "candidate_sources": link["candidate_sources"]}
        elif not extra or not extra[0].startswith("("):
            behavior = "reviewed-non-executable-field"
            evidence = {"signature": row["signature"], "flags": row.get("flags"),
                        "source_anchors": link["candidate_declaration_anchors"]}
        else:
            descriptor = extra[0]
            key = (owner_class, "<init>" if member == owner else member, descriptor)
            observed = hit_evidence(key)
            if observed is not None:
                behavior = ("executed-java-method" if "unchanged-java-corpus" in observed["execution_routes"]
                            else "executed-governing-seam")
                evidence = observed
            elif " abstract " in " " + row["signature"] + " ":
                targets = dispatch_evidence(owner_class, member, descriptor)
                if targets:
                    behavior = "executed-concrete-dispatch"
                    evidence = {"implementations": targets,
                                "source_contract": link["candidate_declaration_anchors"],
                                "unchanged_java_cases_per_lane": 2385}
            else:
                delegated = delegated_hit(key, row.get("flags", []), row["signature"])
                if delegated is not None:
                    behavior = ("reviewed-compiler-bridge-to-executed-target"
                                if "ACC_BRIDGE" in row.get("flags", [])
                                else "reviewed-static-forwarder-to-executed-target")
                    evidence = delegated
                elif (member in {"values", "valueOf"}
                      and any(anchor["relation"] == "compiler-generated-enum-member"
                              for anchor in link["candidate_declaration_anchors"])):
                    fixture_text = governing_seams.FIXTURE.read_text()
                    short_name = owner.rsplit(".", 1)[-1]
                    call = short_name + (".values()" if member == "values" else ".valueOf(")
                    if (call not in fixture_text
                            or seams["fixture_sha256"] != candidate_coverage.digest(governing_seams.FIXTURE)
                            or len(seams["lanes"]) != 8
                            or any(entry["status"] != "passed" for entry in seams["lanes"].values())):
                        raise ValueError(f"compiler enum execution is missing: {identity}")
                    behavior = "executed-enum-source-call"
                    evidence = {"fixture": str(governing_seams.FIXTURE.relative_to(root)),
                                "fixture_sha256": seams["fixture_sha256"],
                                "java_source_call": call,
                                "source_anchors": link["candidate_declaration_anchors"],
                                "baseline_and_candidate_lanes": 8}
        declarations.append({"id": identity, "source_file": row["source_file"],
                             "source_sha256": original["sha256"],
                             "candidate_sources": link["candidate_sources"],
                             "source_status": "mapped-to-committed-kotlin-declaration",
                             "source_anchors": link["candidate_declaration_anchors"],
                             "raw_javap_status": raw_status,
                             "governing_acceptance": surface,
                             "governing_evidence": surface_evidence,
                             "behavior_status": behavior,
                             "behavior_evidence": evidence,
                             "direct_original_cases": [item["original"] for item in link["behavior_tests"]],
                             "target_qualification": "unpassed-full-matrix"})
    by_source = defaultdict(list)
    for row in declarations:
        by_source[row["source_file"]].append(row)
    module_evidence = ledger["module"]["evidence"]
    if {entry["kind"] for entry in module_evidence} != {
            "module-descriptor", "named-module-consumer", "java8-classpath"}:
        raise ValueError("governing named-module evidence inventory differs")
    for entry in module_evidence:
        path = method_coverage.safe_path(root, entry["report"])
        if (entry["status"] != "passed" or entry["target"] != "jvm"
                or candidate_coverage.digest(path) != entry["report_sha256"]):
            raise ValueError("governing named-module evidence differs")
        observed = json.loads(path.read_text())
        if (observed["kind"] != entry["kind"]
                or observed["candidate_commit"] != source["revision"]
                or observed["artifact_sha256"] != source["artifact_sha256"]
                or observed["source_sha256"] != ledger["module"]["sha256"]
                or observed["observed"]["passed"] is not True):
            raise ValueError("governing named-module outcome differs")
    production = []
    for row in ledger["production"]:
        link = production_links[row["id"]]
        if (link["original_sha256"] != row["sha256"]
                or link["candidate_sources"] != row["candidate"]["sources"]):
            raise ValueError(f"governing implementation source differs: {row['id']}")
        paths = [entry["path"] for entry in link["candidate_sources"]]
        hits = sorted({key for path in paths for key in source_hits[path]})
        abstract = [item for item in by_source[row["id"]]
                    if item["behavior_status"] == "executed-concrete-dispatch"]
        unresolved = [item["id"] for item in by_source[row["id"]]
                      if item["behavior_status"] == "unresolved"]
        if unresolved:
            status = "unresolved"
        elif row["id"].endswith("/package-info.java"):
            status = "documentation-only"
        elif row["id"] == "src/main/java/module-info.java":
            status = "executed-named-module"
        elif hits:
            status = "executed-kotlin-source"
        elif abstract:
            status = "reviewed-interface-through-concrete-dispatch"
        elif (row["id"] in {
                "src/main/java/org/dyn4j/geometry/Transformable.java",
                "src/main/java/org/dyn4j/world/listener/WorldEventListener.java"}
              and all(item["behavior_status"] == "reviewed-non-executable-type"
                      for item in by_source[row["id"]])):
            status = "reviewed-non-executable-interface"
        else:
            status = "unresolved"
        production.append({"id": row["id"], "original_sha256": row["sha256"],
                           "candidate_sources": link["candidate_sources"],
                           "source_status": "mapped-to-committed-kotlin-source",
                           "behavior_status": status,
                           "executed_method_ids": [list(key) for key in hits],
                           "behavior_evidence": module_evidence if status == "executed-named-module" else [],
                           "concrete_dispatch_contracts": len(abstract),
                           "unresolved_declaration_ids": unresolved,
                           "target_qualification": "unpassed-full-matrix"})
    behavior_counts = Counter(row["behavior_status"] for row in declarations)
    implementation_counts = Counter(row["behavior_status"] for row in production)
    raw_categories = Counter(row["acceptance_disposition"] for row in raw["rows"])
    return {"schema_version": 1, "candidate_revision": source["revision"],
            "candidate_tree": source["tree"],
            "candidate_artifact_sha256": source["artifact_sha256"],
            "baseline_revision": ledger["baseline"]["commit"],
            "dispatch_helper_sha256": candidate_coverage.digest(method_coverage.DISPATCH_HELPER),
            "input_receipts": {kind: {"path": receipts[kind]["path"],
                                      "sha256": receipts[kind]["sha256"]}
                               for kind in ("raw_signature", "portable_links", "method_coverage",
                                            "governing_seams",
                                            "common_corpus")},
            "raw_diagnostics": {"total": 3508,
                                "equal": 3508 - len(raw["rows"]),
                                "unequal": len(raw["rows"]),
                                "accepted_unequal": len(raw["rows"]),
                                "unresolved_unequal": 0,
                                "accepted_dispositions": dict(sorted(raw_categories.items()))},
            "source_compatibility": {"total": 3508,
                                     "accepted": sum(row["governing_acceptance"] != "unresolved"
                                                     for row in declarations),
                                     "unresolved": sum(row["governing_acceptance"] == "unresolved"
                                                       for row in declarations),
                                     "invalid": 0},
            "source_implementation": {"total": 268, "mapped": len(production),
                                      "accepted": len(production) - implementation_counts["unresolved"],
                                      "unresolved": implementation_counts["unresolved"], "invalid": 0,
                                      "behavior_status": dict(sorted(implementation_counts.items()))},
            "behavior_coverage": {"total": 3508,
                                  "accepted": len(declarations) - behavior_counts["unresolved"],
                                  "unresolved": behavior_counts["unresolved"], "invalid": 0,
                                  "declaration_status": dict(sorted(behavior_counts.items()))},
            "target_qualification": {"staged_common_host_groups": len(gate["groups"]),
                                     "unchanged_java_cases_per_lane": 2385,
                                     "java_compiler_runtime_lanes_per_archive": 4,
                                     "future_lanes_total": 112,
                                     "future_lanes_passed": 0,
                                     "future_lanes_unpassed": 112,
                                     "full_target_qualification": "unpassed"},
            "production": production, "declarations": declarations}


def check(report: dict, ledger: dict, root: Path, upstream: Path) -> str | None:
    try:
        expected = make(ledger, root, upstream)
        if report != expected:
            return "governing disposition differs from source, classfile, or executed evidence"
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired, zipfile.BadZipFile) as error:
        return f"governing disposition replay failed: {error}"
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Separate governing source behavior from raw JVM diagnostics and target execution.")
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("governing output exists")
    report = make(json.loads(args.ledger.read_text()), args.root, args.upstream)
    encoded = (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if args.output.suffix == ".gz":
        with args.output.open("wb") as output:
            with gzip.GzipFile(filename="", mode="wb", fileobj=output,
                               compresslevel=9, mtime=0) as stream:
                stream.write(encoded)
    else:
        args.output.write_bytes(encoded)
    print(json.dumps({"source_compatibility": report["source_compatibility"],
                      "behavior_coverage": report["behavior_coverage"],
                      "raw_diagnostics": report["raw_diagnostics"]}, sort_keys=True))


if __name__ == "__main__":
    main()
