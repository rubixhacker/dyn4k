import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


MANIFEST = Path("tools/qualification/full-suite-manifest.json")
MODULES = ("dyn4k-core", "dyn4k")
FULL_GENERATED = Path("consumers/android-runtime/full/build/generated")
JAVA_JOURNEYS = ("GeometryConsumer", "DetectionConsumer", "CollisionModelConsumer",
                 "DynamicsConsumer", "WorldConsumer", "JointConsumer", "ContactConsumer")
KOTLIN_JOURNEY = "io.github.rubixhacker.dyn4k.full.FullKotlinJourney"
REFLECTIVE_FILTER_TYPES = (
    "CollisionModelConsumer$RootFilter", "CollisionModelConsumer$ChildFilter",
    "CollisionModelConsumer$OtherFilter",
    "org.dyn4j.collision.CollisionModelTest$RootFilter",
    "org.dyn4j.collision.CollisionModelTest$ChildFilter",
    "org.dyn4j.collision.CollisionModelTest$OtherFilter",
    "org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest$Parent",
    "org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest$Child",
    "org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest$Sibling",
    "org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest$Unrelated",
)
X86_DEXOPT_METHOD = "-keepclassmembers class org.dyn4j.geometry.Matrix22 { public double normMax(); }"
FINGERPRINTS = {
    "36": "google/sdk_gphone64_x86_64/emu64xa:16/BE4B.251210.005/14574095:user/release-keys",
    "37": "google/sdk_gphone64_x86_64/emu64xa:17/CE2A.260420.019/15611780:user/release-keys",
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_suite(root):
    qualification = str(root / "tools/qualification")
    if qualification not in sys.path:
        sys.path.insert(0, qualification)
    import full_suite_manifest

    path = root / MANIFEST
    suite = json.loads(path.read_text())
    full_suite_manifest.validate_manifest(suite, root)
    portable = [case for case in suite["cases"] if case["scope"] == "portable"]
    if len(portable) != 2518 or sum(case["module"] == "dyn4k-core" for case in portable) != 2460:
        raise ValueError("full Android common inventory has wrong method counts")
    return suite, {"path": str(path), "sha256": sha256(path),
                   "original_map_sha256": suite["bindings"]["original_map_sha256"],
                   "reviewed_pairs_sha256": suite["bindings"]["reviewed_pairs_sha256"],
                   "original_revision": suite["bindings"]["original_revision"]}


def case_id(case):
    return case["module"] + ":" + case["classname"] + "#" + case["method"]


def commit_time_ns(root):
    seconds = subprocess.check_output(["git", "-C", str(root), "show", "-s", "--format=%ct", "HEAD"],
                                      text=True).strip()
    return int(seconds) * 1_000_000_000


def verify_jvm_xml(root, suite, min_mtime_ns=None):
    expected = {case["id"] for case in suite["cases"]}
    if len(expected) != len(suite["cases"]):
        raise ValueError("duplicate frozen common case")
    actual = set()
    xml_files = {}
    for module in MODULES:
        directory = root / module / "build/test-results/jvmTest"
        reports = sorted(directory.glob("TEST-*.xml"))
        if not reports:
            raise ValueError(f"raw JVM XML absent: {directory}")
        for path in reports:
            if min_mtime_ns is not None and path.stat().st_mtime_ns < min_mtime_ns:
                raise ValueError(f"stale raw JVM XML: {path}")
            tree = ET.parse(path)
            xml = tree.getroot()
            if xml.tag != "testsuite":
                raise ValueError(f"invalid raw JVM XML root: {path}")
            cases = xml.findall("testcase")
            if int(xml.get("tests", "-1")) != len(cases) or any(
                    int(xml.get(name, "-1")) != 0 for name in ("failures", "errors", "skipped")):
                raise ValueError(f"raw JVM XML totals or outcome differ: {path}")
            for item in cases:
                if any(item.find(name) is not None for name in ("failure", "error", "skipped")):
                    raise ValueError(f"failed or skipped raw JVM case: {path}")
                method = item.get("name", "")
                if not method.endswith("[jvm]"):
                    raise ValueError(f"raw JVM case lacks task suffix: {path}")
                identity = module + ":" + item.get("classname", "") + "#" + method[:-5]
                if identity in actual:
                    raise ValueError(f"duplicate raw JVM case: {identity}")
                actual.add(identity)
            xml_files[str(path)] = sha256(path)
    if actual != expected:
        raise ValueError(f"raw JVM cases differ: missing={sorted(expected - actual)[:10]}, "
                         f"extra={sorted(actual - expected)[:10]}")
    portable = sorted(case["id"] for case in suite["cases"] if case["scope"] == "portable")
    return {"case_ids": portable, "jvm_case_count": len(actual), "xml_files": xml_files}


def verify_xml_pins(root, prepared):
    suite, binding = load_suite(root)
    if binding != prepared.get("suite_manifest"):
        raise ValueError("complete suite manifest or original link changed")
    evidence = verify_jvm_xml(root, suite, min_mtime_ns=commit_time_ns(root))
    if evidence != prepared.get("jvm_xml"):
        raise ValueError("raw JVM XML changed since preparation")
    return evidence


def full_app_inputs(suite):
    portable = [case for case in suite["cases"] if case["scope"] == "portable"]
    case_lines = ["\t".join((case["id"], case["classname"], case["method"]))
                  for case in portable]
    case_lines.extend(f"external-java:{name}#main\t{name}\tmain" for name in JAVA_JOURNEYS)
    case_lines.append(f"external-kotlin:{KOTLIN_JOURNEY}#run\t{KOTLIN_JOURNEY}\trun")
    rules = [
        "-keepattributes RuntimeVisibleAnnotations,AnnotationDefault,InnerClasses,EnclosingMethod,Signature",
        "-keep class io.github.rubixhacker.dyn4k.full.FullCorpusExecutor { public static java.util.List runAll(android.content.Context); }",
        "-keep class io.github.rubixhacker.dyn4k.full.FullActivity { public <init>(); public void onCreate(android.os.Bundle); }",
    ]
    rules.extend(f"-keep,allowoptimization class {name} {{ *; }}" for name in
                 sorted({case["classname"] for case in portable}))
    rules.append(X86_DEXOPT_METHOD)
    rules.extend(f"-keep class {name} {{ public static void main(java.lang.String[]); }}"
                 for name in JAVA_JOURNEYS)
    rules.extend(f"-keep,allowobfuscation class {name}" for name in REFLECTIVE_FILTER_TYPES)
    rules.append(f"-keep class {KOTLIN_JOURNEY} {{ public static void run(); }}")
    return {"case_asset": ("\n".join(case_lines) + "\n").encode(),
            "keep_rules": ("\n".join(rules) + "\n").encode()}


def write_full_inputs(root, suite):
    contents = full_app_inputs(suite)
    locations = {"case_asset": root / FULL_GENERATED / "assets/cases.tsv",
                 "keep_rules": root / FULL_GENERATED / "full-keep.pro"}
    for name, path in locations.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents[name])
    return {name: {"path": str(path), "sha256": sha256(path)}
            for name, path in locations.items()}


def verify_full_inputs(root, suite, pins):
    expected = full_app_inputs(suite)
    if not isinstance(pins, dict) or set(pins) != set(expected):
        raise ValueError("full app input inventory changed")
    for name, content in expected.items():
        path = root / FULL_GENERATED / ("assets/cases.tsv" if name == "case_asset" else "full-keep.pro")
        if pins[name] != {"path": str(path), "sha256": hashlib.sha256(content).hexdigest()} or \
                path.read_bytes() != content:
            raise ValueError(f"full app input changed: {name}")
