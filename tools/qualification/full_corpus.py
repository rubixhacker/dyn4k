import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path


ORIGINAL_REVISION = "058bf6d982a0fb89b54050f929f6ea9dae53b714"
HOSTS = (
    ("jvm", "jvmTest", "[jvm]"),
    ("linuxX64", "linuxX64Test", "[linuxX64]"),
    ("jsNode", "jsNodeTest", "[js, node]"),
    ("wasmJsNode", "wasmJsNodeTest", "[wasmJs, node]"),
    ("wasmWasiNode", "wasmWasiNodeTest", "[wasmWasi, node]"),
    ("androidHost", "testAndroidHostTest", ""),
)
GROUPS = tuple({"id": ("core-" if module == "dyn4k-core" else "") + host,
                "module": module, "host": host, "suffix": suffix,
                "class_prefix": "" if host in ("jvm", "androidHost") else task + ".",
                "pattern": f"{module}/build/test-results/{task}/TEST-*.xml"}
               for host, task, suffix in HOSTS
               for module in ("dyn4k-core", "dyn4k"))
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
TOKEN = re.compile(r"\bclass\s+([A-Za-z_]\w*)|@Test\b|\bfun\s+([A-Za-z_]\w*)|[{}]")
PACKAGE = re.compile(r"(?m)^\s*package\s+([A-Za-z_][\w.]*)\s*$")
REVIEW_DOCS = {
    "integrated_collision_model": "portable-collision-model-coverage.md",
    "integrated_polygon": "portable-polygon-coverage.md",
    "integrated_body": "portable-body-coverage.md",
    "integrated_joint_core": "portable-joints-core.md",
    "integrated_joint_modes": "portable-joints-modes.md",
    "integrated_epsilon": "portable-epsilon-coverage.md",
    "pending_shape_pairs_a": "portable-shape-pairs-a.md",
    "pending_shape_pairs_b": "portable-shape-pairs-b.md",
    "pending_world_core": "portable-world-core.md",
    "pending_world_support": "portable-world-support-contact.md",
    "pending_simulation": "portable-simulation-coverage.md",
    "pending_broadphase_body": "portable-detection-body.md",
    "pending_broadphase_item": "portable-detection-item.md",
    "pending_detection": "portable-detection-coverage.md",
}
BODY_RELATED_SUPPLEMENTS = {
    "BodyValueCoverageTest.controlledWrongForceGetterFailsThePortableOracle":
        "org.dyn4j.dynamics.ForceTest#createSuccess",
    "PhysicsBodyCoverageTest.atRestTimeResetsAndDisabledDetectionKeepsBodyAwake":
        "org.dyn4j.dynamics.AbstractPhysicsBodyTest#updateAtRestTime",
    "PhysicsBodyCoverageTest.bodyCopyDuplicatesProtectedStateAndPendingCollections":
        "org.dyn4j.dynamics.BodyTest#copy",
    "PhysicsBodyCoverageTest.fixtureMassCompositionIgnoresZeroDensity":
        "org.dyn4j.dynamics.AbstractPhysicsBodyTest#setMass",
    "PhysicsBodyCoverageTest.fixtureViewAndMassAreLiveAcrossRemoval":
        "org.dyn4j.dynamics.AbstractPhysicsBodyTest#addFixtureByConvexBodyFixture",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical_digest(value):
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode())


def mask_noncode(source):
    result = list(source)
    index = 0
    while index < len(source):
        end = index
        if source.startswith("//", index):
            end = source.find("\n", index)
            if end < 0:
                end = len(source)
        elif source.startswith("/*", index):
            end = source.find("*/", index + 2)
            if end < 0:
                raise ValueError("unterminated block comment")
            end += 2
        elif source.startswith('"""', index):
            end = source.find('"""', index + 3)
            if end < 0:
                raise ValueError("unterminated raw string")
            end += 3
        elif source[index] in ('"', "'"):
            quote = source[index]
            end = index + 1
            while end < len(source):
                if source[end] == "\\":
                    end += 2
                elif source[end] == quote:
                    end += 1
                    break
                else:
                    end += 1
            if end > len(source) or source[end - 1] != quote:
                raise ValueError("unterminated string")
        if end > index:
            for offset in range(index, end):
                if source[offset] != "\n":
                    result[offset] = " "
            index = end
        else:
            index += 1
    return "".join(result)


def scan_sources(repository):
    repository = Path(repository)
    cases = []
    for module in ("dyn4k-core", "dyn4k"):
        for source_set in ("commonTest", "jvmTest"):
            root = repository / module / "src" / source_set / "kotlin"
            for path in sorted(root.rglob("*.kt")):
                raw = path.read_bytes()
                code = mask_noncode(raw.decode("utf-8"))
                package = PACKAGE.search(code)
                tokens = list(TOKEN.finditer(code))
                annotations = len(re.findall(r"@Test\b", code))
                depth = 0
                classes = []
                pending_class = None
                pending_test = False
                discovered = 0
                for token in tokens:
                    if token.group(1):
                        pending_class = token.group(1)
                    elif token.group(0) == "{":
                        depth += 1
                        if pending_class:
                            classes.append((pending_class, depth))
                            pending_class = None
                    elif token.group(0) == "}":
                        if classes and classes[-1][1] == depth:
                            classes.pop()
                        depth -= 1
                        if depth < 0:
                            raise ValueError(f"unbalanced source braces: {path}")
                    elif token.group(0) == "@Test":
                        if pending_test:
                            raise ValueError(f"consecutive test annotations: {path}")
                        pending_test = True
                    elif token.group(2) and pending_test:
                        if not package or not classes:
                            raise ValueError(f"test has no package or class: {path}")
                        classname = package.group(1) + "." + "$".join(
                            item[0] for item in classes)
                        relative = path.relative_to(repository).as_posix()
                        cases.append({"module": module, "source_set": source_set,
                                      "classname": classname, "method": token.group(2),
                                      "path": relative, "sha256": digest(raw),
                                      "line": code.count("\n", 0, token.start()) + 1,
                                      "hosts": ["jvm"] if source_set == "jvmTest"
                                      else [host for host, _, _ in HOSTS]})
                        pending_test = False
                        discovered += 1
                if pending_test or discovered != annotations:
                    raise ValueError(f"unresolved test annotation in {path}")
    if not cases or len({(c["module"], c["classname"], c["method"])
                         for c in cases}) != len(cases):
        raise ValueError("empty or duplicate common test inventory")
    return sorted(cases, key=lambda c: (c["module"], c["classname"], c["method"]))


def scan_test_tree(repository):
    repository = Path(repository)
    files = []
    for module in ("dyn4k-core", "dyn4k"):
        for source_set in ("commonTest", "jvmTest"):
            root = repository / module / "src" / source_set
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    files.append({"path": path.relative_to(repository).as_posix(),
                                  "sha256": digest(path.read_bytes())})
    return sorted(files, key=lambda item: item["path"])


def source_tree_digest(source_files):
    return canonical_digest([(item["path"], item["sha256"]) for item in source_files])


def expected_cases(manifest, group):
    return {(group["class_prefix"] + case["classname"],
             case["method"] + group["suffix"])
            for case in manifest["cases"]
            if case["module"] == group["module"] and group["host"] in case["hosts"]}


def make_manifest(cases, mappings, production=False, repository=None):
    by_identity = {(case["module"], case["classname"], case["method"]): case
                   for case in cases}
    destinations = defaultdict(list)
    unresolved = []
    jvm_only = []
    for mapping in mappings:
        status = mapping["disposition"]
        if status == "JVM_ONLY":
            jvm_only.append(mapping)
        elif status == "PORTABLE":
            key = ("dyn4k-core", mapping["classname"], mapping["method"])
            if key not in by_identity or by_identity[key]["source_set"] != "commonTest":
                unresolved.append({"original": mapping["original"],
                                   "reason": "mapped common method is absent"})
            else:
                destinations[key].append(mapping["original"])
        else:
            unresolved.append({"original": mapping["original"],
                               "reason": mapping.get("reason", "unmapped")})
    decorated = []
    original_ids = {mapping["original"] for mapping in mappings}
    related_found = set()
    for case in cases:
        key = (case["module"], case["classname"], case["method"])
        related_key = case["classname"].split(".")[-1] + "." + case["method"]
        related = BODY_RELATED_SUPPLEMENTS.get(related_key)
        if related and case["module"] == "dyn4k-core" and related in original_ids:
            related_found.add(related_key)
        else:
            related = None
        decorated.append({**case, "originals": sorted(destinations.get(key, [])),
                          "related_original": related,
                          "kind": "mapped-original" if destinations.get(key)
                          else "platform-only" if case["source_set"] != "commonTest"
                          else "supplemental"})
    if production and len(related_found) != len(BODY_RELATED_SUPPLEMENTS):
        unresolved.append({"reason": "reviewed Body supplemental links are absent"})
    source_files = (scan_test_tree(repository) if repository is not None else
                    [{"path": path, "sha256": sha} for path, sha in sorted({
                        (case["path"], case["sha256"]) for case in cases})])
    return {"schema": 1, "kind": "full-common-corpus",
            "policy": "production" if production else "fixture",
            "source_tree_sha256": source_tree_digest(source_files),
            "source_files": source_files, "cases": decorated,
            "original_mappings": mappings, "jvm_only": jvm_only,
            "unresolved": unresolved,
            "counts": {"total_methods": len(cases),
                       "mapped_original_methods": len(destinations),
                       "mapped_original_identities": sum(len(v) for v in destinations.values()),
                       "reviewed_source_linked_methods": len(destinations) + len(related_found),
                       "related_supplemental_methods": len(related_found),
                       "supplemental_methods": sum(c["kind"] == "supplemental" for c in decorated),
                       "platform_only_methods": sum(c["kind"] == "platform-only" for c in decorated),
                       "jvm_only_original_identities": len(jvm_only),
                       "unresolved_mappings": len(unresolved)}}


def review_provenance(repository, owner, source_class, reference=None):
    if reference:
        path = reference
    elif owner == "pending_core_combined":
        shape_classes = {"AbstractShapeTest", "PolygonTest", "TriangleTest", "LinkTest",
                         "CapsuleTest", "EllipseTest", "HalfEllipseTest", "SliceTest",
                         "CircleTest", "RectangleTest", "RayTest", "SegmentTest",
                         "MassTest", "IntervalTest", "AABBTest", "FeatureTest",
                         "WoundTest", "RobustGeometryTest"}
        name = source_class.split(".")[-1]
        document = ("portable-geometry-factory.md" if name == "GeometryTest"
                    else "portable-geometry-shapes.md" if name in shape_classes
                    else "portable-foundation-coverage.md")
        path = "docs/verification/" + document
    else:
        path = "docs/verification/" + REVIEW_DOCS[owner]
    if not (Path(repository) / path).is_file():
        raise ValueError(f"missing reviewed report: {path}")
    return path, digest((Path(repository) / path).read_bytes())


def jvm_only_reason(original):
    source_class, method = original.split("#", 1)
    if original == "org.dyn4j.VersionTest#main":
        return "Captures System.out through Java PrintStream and ByteArrayOutputStream"
    if source_class.endswith(("CollisionBodyAABBProducerTest", "CollisionItemAABBProducerTest")):
        return "Calls a Java producer with null body, fixture, or result arguments"
    if source_class.endswith(("DistanceJointTest", "PulleyJointTest")):
        return "Passes null to a constructor body argument that is nonnull in common Kotlin"
    if method.endswith("NullArray") or method == "nullArray":
        return "Passes a null Java vararg array unavailable in common Kotlin"
    if source_class.endswith("Matrix22Test"):
        return "Passes null to a Java constructor parameter that is nonnull in common Kotlin"
    if "NullPoint" in method or method == "createNullPoints":
        return "Passes null to a geometry point parameter that is nonnull in common Kotlin"
    raise ValueError(f"unreviewed JVM-only disposition: {original}")


def reconcile_originals(repository, upstream, audit):
    repository, upstream = Path(repository), Path(upstream)
    revision = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"],
                                       text=True).strip()
    if revision != ORIGINAL_REVISION:
        raise ValueError("upstream source revision differs from pinned baseline")
    with Path(audit).open(newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    if len(rows) != 2385 or len({row["original_identity"] for row in rows}) != 2385:
        raise ValueError("reviewed original audit must have 2,385 unique executions")
    cases = [case for case in scan_sources(repository) if case["module"] == "dyn4k-core"]
    by_short = defaultdict(list)
    for case in cases:
        by_short[(case["classname"].split(".")[-1], case["method"])].append(case)
    overrides = {}
    detection = repository / "dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/collision/detection/resources/source-case-map.tsv"
    with detection.open(newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            if row["disposition"] == "PORTABLE":
                overrides[row["original_case"]] = (row["portable_case"].replace("#", "."),
                                                    detection.relative_to(repository).as_posix())
    support = repository / "docs/verification/portable-world-support-contact.md"
    for line in support.read_text().splitlines():
        columns = line.split("|")
        if len(columns) < 4:
            continue
        original = re.search(r"`(org\.dyn4j\.[\w.]+)`", columns[1])
        target = re.search(r"`(org\.dyn4j\.[\w.]+)`", columns[2])
        if original and target and "Test." in original.group(1):
            source_class, method = original.group(1).rsplit(".", 1)
            overrides[source_class + "#" + method] = (
                target.group(1), support.relative_to(repository).as_posix())
    mappings = []
    for row in rows:
        original = row["original_identity"]
        source_class, expanded_method = original.split("#", 1)
        method = expanded_method.split("[", 1)[0]
        source_path = "src/test/java/" + source_class.replace(".", "/") + ".java"
        source_file = upstream / source_path
        if not source_file.is_file():
            raise ValueError(f"missing pinned Java source: {source_path}")
        source_bytes = source_file.read_bytes()
        java = mask_noncode(source_bytes.decode("utf-8"))
        function = re.search(r"\bvoid\s+" + re.escape(method) + r"\s*\(", java)
        line = java.count("\n", 0, function.start()) + 1 if function else 0
        item = {"original": original, "original_source": source_path,
                "original_sha256": digest(source_bytes), "original_line": line,
                "disposition": "JVM_ONLY" if row["disposition"] == "JVM_ONLY" else "UNMAPPED",
                "review": row["owner"]}
        if row["disposition"] == "JVM_ONLY":
            item["reason"] = jvm_only_reason(original)
            item["review"], item["review_sha256"] = review_provenance(
                repository, row["owner"], source_class)
            mappings.append(item)
            continue
        selected = None
        reference = None
        direct = row["counterpart_or_reason"] if row["disposition"] == "PORTABLE" else None
        override = overrides.get(original)
        if override:
            direct, reference = override
        elif source_class == "org.dyn4j.geometry.GeometryTest":
            direct = "GeometryFactoryCoverageTest." + method
            reference = "docs/verification/portable-geometry-factory.md"
        if direct:
            names = re.findall(r"(?:[A-Za-z_]\w*\.)+[A-Za-z_]\w*", direct)
            if names:
                classname, target_method = names[0].rsplit(".", 1)
                candidates = by_short.get((classname.split(".")[-1], target_method), [])
                if "." in classname and classname.startswith("org."):
                    candidates = [case for case in candidates if case["classname"] == classname]
                if len(candidates) == 1:
                    selected = candidates[0]
        if selected is None:
            candidates = [case for case in cases if case["method"] == method]
            original_short = source_class.split(".")[-1]
            original_stem = original_short.removesuffix("Test").removeprefix("Abstract")
            ranked = []
            for case in candidates:
                short = case["classname"].split(".")[-1]
                stem = (short.removesuffix("Test").removesuffix("Coverage")
                        .removesuffix("Core").removeprefix("Upstream").removeprefix("Abstract"))
                score = 0
                if short == original_short:
                    score = 5
                elif stem == original_stem:
                    score = 4
                elif short in ("CollisionWorldCoreCoverageTest", "PhysicsWorldCoreCoverageTest"):
                    if original_short in ("AbstractCollisionWorldTest", "AbstractPhysicsWorldTest") and stem == original_stem.removesuffix("World") + "World":
                        score = 3
                if score:
                    ranked.append((score, case))
            if ranked:
                highest = max(score for score, _ in ranked)
                leaders = [case for score, case in ranked if score == highest]
                if len(leaders) == 1:
                    selected = leaders[0]
        if selected:
            item.update(disposition="PORTABLE", classname=selected["classname"],
                        method=selected["method"], review=reference or row["owner"])
        else:
            item["reason"] = "no unique reviewed common destination"
        item["review"], item["review_sha256"] = review_provenance(
            repository, row["owner"], source_class, reference)
        mappings.append(item)
    return mappings


def verify_reports(repository, manifest, candidate_sha, binding, reports,
                   mapping=None, upstream=None, require_checkout=False):
    repository = Path(repository)
    problems = []
    if manifest.get("kind") != "full-common-corpus" or manifest.get("schema") != 1:
        problems.append("full corpus manifest is invalid")
    if not SHA40.fullmatch(candidate_sha):
        problems.append("candidate SHA is invalid")
    if binding.get("candidate_sha") != candidate_sha:
        problems.append("candidate SHA differs from report binding")
    if binding.get("manifest_sha256") != canonical_digest(manifest):
        problems.append("manifest hash differs from report binding")
    started = binding.get("started_ns")
    finished = binding.get("finished_ns")
    if (type(started) is not int or type(finished) is not int
            or started <= 0 or finished < started):
        problems.append("fresh report invocation window is invalid")
    command = binding.get("command")
    required_tasks = {f":{module}:{task}" for _, task, _ in HOSTS
                      for module in ("dyn4k-core", "dyn4k")}
    if (not isinstance(command, list) or not command
            or "--rerun-tasks" not in command or not required_tasks.issubset(command)
            or binding.get("exit_code") != 0):
        problems.append("complete fresh Gradle invocation is missing or failed")
    if mapping is not None and mapping != manifest.get("original_mappings"):
        problems.append("reviewed original map differs from manifest")
    if upstream is not None:
        revision = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"],
                                           text=True).strip()
        if revision != ORIGINAL_REVISION:
            problems.append("pinned original source revision differs")
        original_rows = manifest.get("original_mappings", [])
        identities = [item.get("original") for item in original_rows]
        if len(identities) != len(set(identities)):
            problems.append("duplicate reviewed original identity")
        original_files = {}
        review_files = {}
        for item in original_rows:
            path = item.get("original_source", "")
            review = item.get("review", "")
            if path not in original_files:
                source_file = Path(upstream) / path
                original_files[path] = source_file.read_bytes() if source_file.is_file() else None
            if review not in review_files:
                review_file = repository / review
                review_files[review] = review_file.read_bytes() if review_file.is_file() else None
            raw = original_files[path]
            if raw is None or digest(raw) != item.get("original_sha256"):
                problems.append(f"pinned original source hash differs: {path}")
            else:
                lines = raw.decode("utf-8").splitlines()
                line = int(item.get("original_line", 0))
                method = item.get("original", "").split("#")[-1].split("[")[0]
                if not 1 <= line <= len(lines) or not re.search(
                        r"\bvoid\s+" + re.escape(method) + r"\s*\(", lines[line - 1]):
                    problems.append(f"original declaration line differs: {item.get('original')}")
            if review_files[review] is None or digest(review_files[review]) != item.get("review_sha256"):
                problems.append(f"reviewed mapping report hash differs: {review}")
    if require_checkout:
        head = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"],
                                       text=True).strip()
        if head != candidate_sha:
            problems.append("candidate SHA differs from checkout")
        dirty = subprocess.check_output(["git", "-C", str(repository), "status",
                                         "--porcelain=v1", "--untracked-files=no"],
                                        text=True).strip()
        if dirty:
            problems.append("tracked source tree is dirty")
    try:
        scanned = scan_sources(repository)
        regenerated = make_manifest(scanned, mapping if mapping is not None
                                    else manifest["original_mappings"],
                                    manifest.get("policy") == "production", repository)
        if regenerated != manifest:
            problems.append("source inventory or reviewed mapping differs from manifest")
        tree = source_tree_digest(scan_test_tree(repository))
        if tree != manifest.get("source_tree_sha256") or tree != binding.get("source_tree_sha256"):
            problems.append("source tree hash differs from report binding")
    except (KeyError, OSError, UnicodeError, ValueError) as error:
        problems.append(f"source inventory invalid: {error}")
    counts = manifest.get("counts", {})
    if counts.get("unresolved_mappings") != 0 or manifest.get("unresolved"):
        problems.append("unresolved original mappings")
    if manifest.get("policy") == "production":
        if (len(manifest["original_mappings"]) != 2385
                or counts.get("mapped_original_methods") != 2253
                or counts.get("reviewed_source_linked_methods") != 2258
                or counts.get("related_supplemental_methods") != 5
                or counts.get("mapped_original_identities") != 2353
                or counts.get("jvm_only_original_identities") != 32):
            problems.append("reviewed original mapping totals differ from frozen corpus")
    group_ids = {group["id"] for group in GROUPS}
    if set(reports) != group_ids or set(binding.get("reports", {})) != group_ids:
        problems.append("all six core and facade report groups are required")
    groups = []
    total = 0
    for group in GROUPS:
        group_id = group["id"]
        expected = expected_cases(manifest, group)
        paths = reports.get(group_id, [])
        bound = binding.get("reports", {}).get(group_id, {})
        names = {str(Path(path).relative_to(repository)) for path in paths}
        if not paths or len(names) != len(paths) or set(bound) != names:
            problems.append(f"missing or extra report files: {group_id}")
        seen = Counter()
        failures = errors = skipped = 0
        hashes = {}
        for path in paths:
            path = Path(path)
            name = str(path.relative_to(repository))
            try:
                raw = path.read_bytes()
                file_hash = digest(raw)
                hashes[name] = file_hash
                if bound.get(name) != file_hash:
                    problems.append(f"report hash differs from source binding: {name}")
                if (type(started) is int and type(finished) is int
                        and not started <= path.stat().st_mtime_ns <= finished):
                    problems.append(f"report predates or postdates invocation: {name}")
                suite = ET.fromstring(raw)
                if suite.tag != "testsuite":
                    raise ValueError("XML root is not testsuite")
                suite_cases = list(suite.iter("testcase"))
                observed = {"tests": len(suite_cases),
                            "failures": sum(c.find("failure") is not None for c in suite_cases),
                            "errors": sum(c.find("error") is not None for c in suite_cases),
                            "skipped": sum(c.find("skipped") is not None for c in suite_cases)}
                for key, value in observed.items():
                    if suite.get(key) is None or int(suite.get(key)) != value:
                        raise ValueError(f"XML {key} count differs from cases")
                duration = float(suite.get("time", "nan"))
                if not 0 <= duration < float("inf"):
                    raise ValueError("suite duration is invalid")
                for case in suite_cases:
                    classname, method = case.get("classname"), case.get("name")
                    if not classname or not method or not 0 <= float(case.get("time", "nan")) < float("inf"):
                        raise ValueError("case identity or duration is invalid")
                    seen[classname, method] += 1
                failures += observed["failures"]
                errors += observed["errors"]
                skipped += observed["skipped"]
            except (OSError, ET.ParseError, TypeError, ValueError) as error:
                problems.append(f"invalid XML {name}: {error}")
        missing = sorted(expected - set(seen))
        extra = sorted(set(seen) - expected)
        duplicates = sorted(case for case, count in seen.items() if count != 1)
        if missing:
            problems.append(f"missing {len(missing)} expected cases in {group_id}: {missing[:3]}")
        if extra:
            problems.append(f"unexpected {len(extra)} cases in {group_id}: {extra[:3]}")
        if duplicates:
            problems.append(f"duplicate cases in {group_id}: {duplicates[:3]}")
        if failures or errors or skipped:
            problems.append(f"failed, errored, or skipped cases in {group_id}")
        total += sum(seen.values())
        groups.append({"id": group_id, "expected": len(expected), "reported": sum(seen.values()),
                       "mapped_original_methods": sum(c["kind"] == "mapped-original"
                                                      for c in manifest["cases"]
                                                      if c["module"] == group["module"]
                                                      and group["host"] in c["hosts"]),
                       "supplemental_cases": sum(c["kind"] == "supplemental"
                                                 for c in manifest["cases"]
                                                 if c["module"] == group["module"]
                                                 and group["host"] in c["hosts"]),
                       "platform_only_cases": sum(c["kind"] == "platform-only"
                                                  for c in manifest["cases"]
                                                  if c["module"] == group["module"]
                                                  and group["host"] in c["hosts"]),
                       "failures": failures, "errors": errors, "skipped": skipped,
                       "report_sha256": hashes})
    result = {"schema": 1, "kind": "full-common-corpus-verification",
              "candidate_sha": candidate_sha, "source_tree_sha256": manifest.get("source_tree_sha256"),
              "manifest_sha256": canonical_digest(manifest),
              "status": "UNPASSED" if problems else "PASSED", "problems": problems,
              "total_cases": total, "mapped_original_methods": counts.get("mapped_original_methods"),
              "reviewed_source_linked_methods": counts.get("reviewed_source_linked_methods"),
              "supplemental_cases": counts.get("supplemental_methods"),
              "platform_only_cases": counts.get("platform_only_methods"),
              "jvm_only_original_identities": counts.get("jvm_only_original_identities"),
              "groups": groups}
    return result


def main():
    parser = argparse.ArgumentParser(description="Source-derived full common corpus gate")
    sub = parser.add_subparsers(dest="operation", required=True)
    inventory = sub.add_parser("inventory")
    inventory.add_argument("--repository", type=Path, default=Path("."))
    inventory.add_argument("--mapping", type=Path, required=True)
    inventory.add_argument("--output", type=Path, required=True)
    inventory.add_argument("--report", type=Path)
    reconcile = sub.add_parser("reconcile")
    reconcile.add_argument("--repository", type=Path, default=Path("."))
    reconcile.add_argument("--upstream", type=Path, required=True)
    reconcile.add_argument("--audit", type=Path, required=True)
    reconcile.add_argument("--output", type=Path, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--repository", type=Path, default=Path("."))
    verify.add_argument("--candidate-sha", required=True)
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--mapping", type=Path, required=True)
    verify.add_argument("--upstream", type=Path, required=True)
    verify.add_argument("--binding", type=Path, required=True)
    verify.add_argument("--output", type=Path, required=True)
    run = sub.add_parser("run")
    run.add_argument("--repository", type=Path, default=Path("."))
    run.add_argument("--candidate-sha", required=True)
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--mapping", type=Path, required=True)
    run.add_argument("--upstream", type=Path, required=True)
    run.add_argument("--binding", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--log", type=Path, required=True)
    run.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.operation == "reconcile":
        mappings = reconcile_originals(args.repository, args.upstream, args.audit)
        fields = ("original", "original_source", "original_sha256", "original_line",
                  "disposition", "classname", "method", "reason", "review",
                  "review_sha256")
        with args.output.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t",
                                    lineterminator="\n")
            writer.writeheader()
            writer.writerows(mappings)
        print(json.dumps({"total": len(mappings), "dispositions": dict(Counter(
            row["disposition"] for row in mappings))}, sort_keys=True))
        return 0 if all(row["disposition"] != "UNMAPPED" for row in mappings) else 1
    if args.operation == "inventory":
        with args.mapping.open(newline="") as stream:
            mappings = list(csv.DictReader(stream, delimiter="\t"))
        manifest = make_manifest(scan_sources(args.repository), mappings,
                                 production=True, repository=args.repository)
        args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        if args.report:
            groups = [{"id": group["id"], "expected": len(expected_cases(manifest, group)),
                       "module": group["module"], "host": group["host"]}
                      for group in GROUPS]
            report = {"schema": 1, "kind": "full-common-corpus-inventory",
                      "qualification_status": "NOT_RUN",
                      "inventory_status": "UNPASSED" if manifest["unresolved"] else "MAPPED",
                      "source_tree_sha256": manifest["source_tree_sha256"],
                      "manifest_sha256": canonical_digest(manifest),
                      "map_file_sha256": digest(args.mapping.read_bytes()),
                      "counts": manifest["counts"], "source_files": len(manifest["source_files"]),
                      "original_source_files": len({row["original_source"] for row in mappings}),
                      "review_reports": len({row["review"] for row in mappings}),
                      "expected_host_executions": sum(group["expected"] for group in groups),
                      "groups": groups, "unresolved": manifest["unresolved"]}
            args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps(manifest["counts"], sort_keys=True))
        return 0 if not manifest["unresolved"] else 1
    manifest = json.loads(args.manifest.read_text())
    with args.mapping.open(newline="") as stream:
        mapping = list(csv.DictReader(stream, delimiter="\t"))
    if manifest.get("policy") != "production":
        raise ValueError("production full corpus manifest is required")
    if args.operation == "run":
        command = args.command[1:] if args.command and args.command[0] == "--" else args.command
        required_tasks = {f":{module}:{task}" for _, task, _ in HOSTS
                          for module in ("dyn4k-core", "dyn4k")}
        if (not command or command[0] != "./gradlew" or "--rerun-tasks" not in command
                or not required_tasks.issubset(command)):
            raise ValueError("run command must rerun all twelve Gradle host tasks")
        repository = args.repository.resolve()
        head = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"],
                                       text=True).strip()
        dirty = subprocess.check_output(["git", "-C", str(repository), "status",
                                         "--porcelain=v1", "--untracked-files=no"],
                                        text=True).strip()
        if head != args.candidate_sha or dirty:
            raise ValueError("candidate SHA or tracked checkout differs before run")
        if make_manifest(scan_sources(repository), mapping, production=True,
                         repository=repository) != manifest:
            raise ValueError("source inventory or reviewed map differs before run")
        if subprocess.check_output(["git", "-C", str(args.upstream), "rev-parse", "HEAD"],
                                   text=True).strip() != ORIGINAL_REVISION:
            raise ValueError("upstream source revision differs from pinned baseline")
        for group in GROUPS:
            for path in repository.glob(group["pattern"]):
                path.unlink()
        started = time.time_ns()
        completed = subprocess.run(command, cwd=repository, text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   check=False)
        finished = time.time_ns()
        args.log.write_text(completed.stdout)
        report_paths = {group["id"]: sorted(repository.glob(group["pattern"]))
                        for group in GROUPS}
        binding = {"schema": 1, "candidate_sha": args.candidate_sha,
                   "manifest_sha256": canonical_digest(manifest),
                   "source_tree_sha256": manifest["source_tree_sha256"],
                   "started_ns": started, "finished_ns": finished,
                   "command": command, "exit_code": completed.returncode,
                   "log": str(args.log), "log_sha256": digest(completed.stdout.encode()),
                   "reports": {group_id: {
                       str(path.relative_to(repository)): digest(path.read_bytes())
                       for path in paths} for group_id, paths in report_paths.items()}}
        args.binding.write_text(json.dumps(binding, indent=2, sort_keys=True) + "\n")
    else:
        binding = json.loads(args.binding.read_text())
    reports = {group["id"]: sorted(args.repository.glob(group["pattern"])) for group in GROUPS}
    result = verify_reports(args.repository, manifest, args.candidate_sha,
                            binding, reports, mapping=mapping, upstream=args.upstream,
                            require_checkout=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "problems": result["problems"]}))
    return 0 if result["status"] == "PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
