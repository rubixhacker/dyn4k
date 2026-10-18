import hashlib
import pathlib
import re
import subprocess
import sys
import xml.etree.ElementTree as ET


UPSTREAM_REVISION = "058bf6d982a0fb89b54050f929f6ea9dae53b714"
MAP_PATH = pathlib.Path(__file__).with_name("source-case-map.tsv")
HEADER = "source\tsource_sha256\tdeclaration_line\toriginal_case\tdisposition\tportable_case"
VARIANTS = ("sap_untracked", "sap_tracked", "tree_untracked", "tree_tracked", "brute_force")

ROOT_METHOD_PREFIXES = {
    "PenetrationTest": "penetration",
    "SeparationTest": "separation",
    "RaycastTest": "raycast",
    "ContainmentTest": "containment",
    "TimeOfImpactTest": "timeOfImpact",
}
REST_METHODS = {
    "AbstractFallbackConditionTest": ("NarrowphaseModelCoverageTest", "abstractFallbackCondition"),
    "EpaTest": ("NarrowphaseModelCoverageTest", "epa"),
    "ExpandingSimplexEdgeTest": ("NarrowphaseModelCoverageTest", "expandingSimplexEdge"),
    "ExpandingSimplexTest": ("NarrowphaseModelCoverageTest", "expandingSimplex"),
    "FallbackNarrowphaseDetectorTest": ("FallbackCoverageTest", "fallback"),
    "GjkTest": ("GjkCoverageTest", ""),
    "LinkPostProcessorTest": ("LinkPostProcessorCoverageTest", ""),
    "MinkowskiSumPointTest": ("NarrowphaseModelCoverageTest", "minkowskiSumPoint"),
    "MinkowskiSumTest": ("NarrowphaseModelCoverageTest", "minkowskiSum"),
    "PairwiseTypedFallbackConditionTest": ("FallbackCoverageTest", "pairwiseTyped"),
    "SatTest": ("SatCoverageTest", ""),
    "SegmentDetectorTest": ("SegmentDetectorCoverageTest", ""),
    "SingleTypedFallbackConditionTest": ("FallbackCoverageTest", "singleTyped"),
    "ClippingManifoldSolverTest": ("ClippingManifoldCoverageTest", ""),
    "IndexedManifoldPointIdTest": ("ManifoldModelCoverageTest", "indexedManifoldPointId"),
    "ManifoldPointIdTest": ("ManifoldModelCoverageTest", "manifoldPointId"),
    "ManifoldPointTest": ("ManifoldModelCoverageTest", "manifoldPoint"),
    "ManifoldTest": ("ManifoldModelCoverageTest", "manifold"),
    "ConservativeAdvancementTest": ("ConservativeAdvancementCoverageTest", ""),
}
JVM_ONLY_ITEM_METHODS = {
    (class_name, method)
    for class_name in ("CollisionBodyAABBProducerTest", "CollisionItemAABBProducerTest")
    for method in ("computeNull", "computeNullBody", "computeNullBoth", "computeNullResult")
}


def validate_root(root):
    revision = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if revision != UPSTREAM_REVISION:
        raise ValueError("unpinned upstream revision: " + revision)


def portable_case(class_name, method, variant):
    if class_name in ROOT_METHOD_PREFIXES and not variant:
        prefix = ROOT_METHOD_PREFIXES[class_name]
        return "PORTABLE", "DetectionResultCoverageTest." + prefix + method[0].upper() + method[1:]
    if class_name in REST_METHODS and not variant:
        target, prefix = REST_METHODS[class_name]
        name = method if not prefix else prefix + method[0].upper() + method[1:]
        return "PORTABLE", target + "." + name
    if class_name == "CollisionBodyBroadphaseTest" and variant:
        return "PORTABLE", "CollisionBodyBroadphaseCoverageTest." + method + "_" + variant[1:-1]
    if (class_name, method) in JVM_ONLY_ITEM_METHODS and not variant:
        return "JVM_ONLY", ""
    if class_name == "CollisionItemBroadphaseTest" and variant:
        return "PORTABLE", "ItemBroadphaseCoverageTest." + method + "_" + variant[1:-1]
    if not variant:
        return "PORTABLE", "ItemBroadphaseCoverageTest." + class_name + "_" + method
    return "UNMAPPED", ""


def verify_portfolio(rows):
    if len(rows) != 471:
        raise ValueError("expected 471 original detection identities, found " + str(len(rows)))
    identities = [row[3] for row in rows]
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate original detection identity")
    dispositions = {name: sum(row[4] == name for row in rows) for name in ("PORTABLE", "JVM_ONLY", "UNMAPPED")}
    if dispositions != {"PORTABLE": 463, "JVM_ONLY": 8, "UNMAPPED": 0}:
        raise ValueError("unexpected portfolio dispositions: " + repr(dispositions))
    mapped = [row[5] for row in rows if row[4] == "PORTABLE"]
    if len(set(mapped)) != 463:
        raise ValueError("portable common case identities are not unique")
    return dispositions


def declaration_line(text, method):
    matches = list(re.finditer(r"\bpublic\s+void\s+" + re.escape(method) + r"\s*\(", text))
    return str(text[: matches[0].start()].count("\n") + 1) if matches else "INHERITED_OR_MISSING"


def remap_existing(root):
    validate_root(root)
    lines = MAP_PATH.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != HEADER:
        raise ValueError("unexpected source case map header")
    output = [HEADER]
    rows = []
    for line in lines[1:]:
        fields = line.split("\t")
        if len(fields) == 5:
            fields.append("")
        if len(fields) != 6:
            raise ValueError("malformed source case map row: " + line)
        source, source_sha, old_line, identity, _, _ = fields
        data = (root / source).read_bytes()
        actual_sha = hashlib.sha256(data).hexdigest()
        if actual_sha != source_sha:
            raise ValueError((source, "pinned source hash changed", actual_sha, source_sha))
        text = data.decode("utf-8")
        if declaration_line(text, identity.rsplit("#", 1)[1].split("[", 1)[0]) != old_line:
            raise ValueError((identity, "pinned declaration line changed", old_line))
        original_class, raw_method = identity.rsplit("#", 1)
        method, _, suffix = raw_method.partition("[")
        variant = "[" + suffix if suffix else ""
        class_name = original_class.rsplit(".", 1)[-1]
        disposition, portable = portable_case(class_name, method, variant)
        row = [source, source_sha, old_line, identity, disposition, portable]
        rows.append(row)
        output.append("\t".join(row).rstrip("\t"))
    verify_portfolio(rows)
    MAP_PATH.write_text("\n".join(output) + "\n", encoding="utf-8")
    return rows


def cases(directory):
    result = {}
    for xml in sorted(directory.glob("TEST-*.xml")):
        suite = ET.parse(xml).getroot()
        if any(int(suite.attrib.get(key, "0")) for key in ("failures", "errors", "skipped")):
            raise ValueError((xml, "failed, errored, or skipped original case"))
        name = suite.attrib["name"]
        seen = []
        values = []
        for test in suite.findall("testcase"):
            raw = test.attrib["name"]
            method, _, suffix = raw.partition("[")
            variant = ""
            if suffix:
                if suffix not in seen:
                    seen.append(suffix)
                index = seen.index(suffix)
                if index >= len(VARIANTS):
                    raise ValueError((name, raw))
                variant = "[" + VARIANTS[index] + "]"
            identity = name + "#" + method + variant
            values.append((identity, method, variant, test))
        if len(values) != int(suite.attrib["tests"]):
            raise ValueError((name, "suite count mismatch"))
        result[name] = values
    return result


if len(sys.argv) == 3 and sys.argv[1] == "--remap-map":
    rows = remap_existing(pathlib.Path(sys.argv[2]))
    print("remapped", len(rows), "original identities; portable=463 JVM_ONLY=8 UNMAPPED=0")
    raise SystemExit(0)

if len(sys.argv) != 4:
    raise SystemExit("usage: build-case-map.py UPSTREAM_ROOT BASELINE_XML_DIR CANDIDATE_XML_DIR")

root = pathlib.Path(sys.argv[1])
baseline = pathlib.Path(sys.argv[2])
candidate = pathlib.Path(sys.argv[3])
validate_root(root)
before = cases(baseline)
after = cases(candidate)
if len(before) != 37 or sum(len(values) for values in before.values()) != 471:
    raise ValueError("original detection corpus count changed")
if before.keys() != after.keys():
    raise ValueError("baseline and candidate suite sets differ")
for name in before:
    if [value[0] for value in before[name]] != [value[0] for value in after[name]]:
        raise ValueError((name, "baseline and candidate case identities differ"))

rows = []
for name, values in sorted(before.items()):
    source = pathlib.Path("src/test/java") / pathlib.Path(*name.split(".")).with_suffix(".java")
    data = (root / source).read_bytes()
    source_sha = hashlib.sha256(data).hexdigest()
    text = data.decode("utf-8")
    class_name = name.split(".")[-1]
    for identity, method, variant, _ in sorted(values):
        disposition, portable = portable_case(class_name, method, variant)
        rows.append((str(source), source_sha, declaration_line(text, method), identity, disposition, portable))
verify_portfolio(rows)
print(HEADER)
for row in rows:
    print("\t".join(row).rstrip("\t"))
