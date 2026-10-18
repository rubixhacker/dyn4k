from __future__ import annotations

import argparse
import csv
from contextlib import contextmanager
import hashlib
import json
import math
import os
import re
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import full_corpus


PACKAGE = re.compile(r"^package\s+([\w.]+)", re.MULTILINE)
CLASS = re.compile(r"^(?:(?:internal|private|public|open|abstract|data)\s+)*class\s+(\w+)")
FUNCTION = re.compile(r"\bfun\s+([A-Za-z_][A-Za-z_0-9]*)\s*\(")
TEAMCITY = re.compile(r"^##teamcity\[(\w+) name='([^']*)'")
MODULES = ("dyn4k-core", "dyn4k")
TARGETS = ("js", "wasmJs", "wasmWasi")
VERSION = "0.1.0-alpha.1"
COMMON_CORPUS_CANDIDATE = "0681a8cd2e3f12327296a58da68bc8338224ea73"
CORPUS_GENERATOR_SHA256 = "0357f793b8869a3f8887b560c3f710e7334a6036867cf9ae16219622bd08f0db"
CONSUMER = Path("consumers/qualification/browser-wasi")
PHYSICS_CONSUMER_SOURCE = CONSUMER / "src/commonTest/kotlin/qualification/StagedWorldTest.kt"
PHYSICS_CONSUMER_SHA256 = "e5a5a5f1a8e1e7cf3286d0f7be92795e14ad153ea4b1b5117fb7f560ee7a0189"
CONSUMER_BUILD_SHA256 = "ff37cf87e35a9346f0d25fcb85d9e3db0747f15561c3d985552dd4512ddfbbb7"
CONSUMER_SETTINGS_SHA256 = "842383eb0023b5edd4ca9d2394ed3d81b1fcf0ced275ff24842aa9844f9d8a63"
CONSUMER_YARN_LOCK_SHA256 = "521d87b1dc27f4f3ef947115945bd01eefcae1ae6fbfdede75c8f9e15f059263"
CONSUMER_YARN_LOCK_FIXTURE = Path("tools/qualification/browser_wasi/fixtures/consumer-yarn.lock")
CONSUMER_LOCK_SOURCE_BASE = "d7a06e57fa7d940e81b3fe90b54d64fd4f3610b9"
RUNTIME_VERSIONS = {
    "chromium": {"minimum": "119.0.6045.105", "current": "155.0.8059.84"},
    "firefox": {"minimum": "120.0.1", "current": "158.0"},
    "wasmtime": {"minimum": "37.0.3", "current": "49.0.3"},
}
KARMA_EXECUTABLE_SUFFIX_SHA256 = {
    "js": "30e32fd8e9d76f66150967c36e0757749a0723eebccf936752b200d21892457e",
    "wasmJs": "7dc95f1876442be2141473ba1a99b11ad3005a70f704b5c5ce48cc011aadc203",
}
KARMA_HELPER_SHA256 = {
    "runner": "15261c8d909c161dfc3004934d1f2542f96abcb78071b6f3663aa927773aba18",
    "context": "0451957d938729d37d045f2eb855ea0b2afa50815ff2ed9488dd18e7135fc69d",
    "debug": "695977572217887870de5bf75b6c4ba3be2b6780e20a0f2dd83af1c8660ce03e",
}
KARMA_REPORTER_SHA256 = "7c3232f60952aff254847ae62a866385735e3094197454d755100e962c2f2347"
COLLISION_DIAGNOSTIC_CLASS = (
    "org.dyn4j.collision.narrowphase.WindowsCollisionIntermediateDiagnosticTest"
)
COLLISION_DIAGNOSTIC_METHODS = {
    "CapsuleSlice": ("capsuleSlice", "detectGjk"),
    "CirclePolygon": ("circlePolygon", "detectGjk"),
    "CircleSegment": ("circleSegment", "detectGjk"),
    "CircleSlice": ("circleSlice", "detectGjk"),
    "PolygonCapsule": ("polygonCapsule", "detectSat"),
    "PolygonPolygon": ("polygonPolygon", "detectSat"),
}
COLLISION_DIAGNOSTIC_PREFIX_FIELDS = (
    "provider", "fixture", "method", "phase", "order", "step", "algorithm",
    "a.transform", "b.transform", "a.center.local", "b.center.local",
    "a.center.world", "b.center.world", "hit", "booleanHit",
    "penetration.normal", "penetration.depth", "selection", "clipped",
    "manifold.normal", "manifold.count", "a.shape.local", "b.shape.local",
    "a.polygon.edgeArithmetic", "b.polygon.edgeArithmetic", "a.foci.world",
    "b.foci.world", "a.axes.withB", "b.axes.withA",
    "gjk.initial.centerDirection", "gjk.initial.effectiveDirection",
    "clip.probe.feature.a", "clip.probe.feature.b",
) + tuple(f"support.{i}.{field}" for i in range(6) for field in (
    "direction", "a", "b.negated", "minkowski"))
COLLISION_DIAGNOSTIC_SAT_FIELDS = (
    "sat.replay.hit", "sat.replay.matchesResult", "sat.candidates",
    "sat.winner.source", "sat.winner.index",
)
COLLISION_DIAGNOSTIC_SAT_HIT_FIELDS = (
    "sat.winner.preOrientation", "sat.winner.centerDot",
    "sat.winner.orientationFlip", "sat.winner.finalAxis", "sat.winner.depth",
)
COLLISION_DIAGNOSTIC_EPA_FIELDS = (
    "epa.replay.identity", "epa.replay.simplex", "epa.replay.iteration",
    "epa.replay.stop", "epa.replay.epsilon", "epa.replay.maxIterations",
    "epa.iteration.schema", "epa.iteration.records",
    "epa.queue.reconstructedMatches", "epa.edge.a", "epa.edge.b",
    "epa.edge.normal", "epa.edge.distance", "epa.terminal.support",
    "epa.terminal.projection", "epa.terminal.delta",
    "epa.replay.normalMatchesResult", "epa.replay.depthMatchesResult",
)
COLLISION_DIAGNOSTIC_EPA_SCHEMA = (
    "index:edgeId:edgeA:edgeB:normalBefore:normalAfter:distance:support:"
    "projection:delta:stop:equalDistanceEdgeIds:mirrorMatches"
)
DIAGNOSTIC_INTEGER = r"-?(?:0|[1-9]\d*)"
DIAGNOSTIC_DECIMAL = r"(?:NaN|-?Infinity|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)"
DIAGNOSTIC_NUMBER = rf"{DIAGNOSTIC_DECIMAL}@{DIAGNOSTIC_INTEGER}"
DIAGNOSTIC_VECTOR = rf"{DIAGNOSTIC_NUMBER},{DIAGNOSTIC_NUMBER}"
DIAGNOSTIC_VECTORS = rf"{DIAGNOSTIC_VECTOR}(?:;{DIAGNOSTIC_VECTOR})*"
DIAGNOSTIC_BOOLEAN = r"(?:true|false)"
DIAGNOSTIC_FEATURE = (
    rf"(?:point:{DIAGNOSTIC_INTEGER}:{DIAGNOSTIC_VECTOR}|"
    rf"edge:{DIAGNOSTIC_INTEGER}:{DIAGNOSTIC_INTEGER}:{DIAGNOSTIC_VECTOR}:"
    rf"{DIAGNOSTIC_INTEGER}:{DIAGNOSTIC_VECTOR}:{DIAGNOSTIC_INTEGER}:"
    rf"{DIAGNOSTIC_VECTOR}:{DIAGNOSTIC_VECTOR}|unknown:{DIAGNOSTIC_INTEGER})"
)
DIAGNOSTIC_POLYGON_EDGE = (
    rf"{DIAGNOSTIC_INTEGER}:" + ":".join((DIAGNOSTIC_NUMBER,) * 7) +
    rf":{DIAGNOSTIC_VECTOR}:{DIAGNOSTIC_NUMBER}:{DIAGNOSTIC_VECTOR}:{DIAGNOSTIC_VECTOR}"
)
DIAGNOSTIC_SHAPE_BASE = (
    rf"center={DIAGNOSTIC_VECTOR}\|radius={DIAGNOSTIC_NUMBER}"
)
DIAGNOSTIC_SHAPE = (
    rf"(?:kind=Circle\|{DIAGNOSTIC_SHAPE_BASE}\|circle\.radius={DIAGNOSTIC_NUMBER}|"
    rf"kind=Capsule\|{DIAGNOSTIC_SHAPE_BASE}\|capsule\.length={DIAGNOSTIC_NUMBER}"
    rf"\|capsule\.capRadius={DIAGNOSTIC_NUMBER}"
    rf"\|capsule\.localFoci=(?:null|{DIAGNOSTIC_VECTORS})"
    rf"\|capsule\.localAxis={DIAGNOSTIC_VECTOR}|"
    rf"kind=Slice\|{DIAGNOSTIC_SHAPE_BASE}\|slice\.radius={DIAGNOSTIC_NUMBER}"
    rf"\|slice\.theta={DIAGNOSTIC_NUMBER}\|slice\.circleCenter={DIAGNOSTIC_VECTOR}"
    rf"\|slice\.rotation={DIAGNOSTIC_VECTOR}"
    rf"\|slice\.upperEdge={DIAGNOSTIC_FEATURE}"
    rf"\|slice\.lowerEdge={DIAGNOSTIC_FEATURE}|"
    rf"kind=Segment\|{DIAGNOSTIC_SHAPE_BASE}\|segment\.length={DIAGNOSTIC_NUMBER}"
    rf"\|vertices=(?:null|{DIAGNOSTIC_VECTORS})"
    rf"\|normals=(?:null|{DIAGNOSTIC_VECTORS})|"
    rf"kind=Polygon\|{DIAGNOSTIC_SHAPE_BASE}"
    rf"\|vertices=(?:null|{DIAGNOSTIC_VECTORS})"
    rf"\|normals=(?:null|{DIAGNOSTIC_VECTORS}))"
)
DIAGNOSTIC_INTERVAL = rf"{DIAGNOSTIC_VECTOR}"
DIAGNOSTIC_SAT_CANDIDATE = (
    rf"[01]:{DIAGNOSTIC_INTEGER}:(?:zero:{DIAGNOSTIC_VECTOR}|"
    rf"separated:{DIAGNOSTIC_VECTOR}:{DIAGNOSTIC_INTERVAL}:{DIAGNOSTIC_INTERVAL}|"
    rf"{DIAGNOSTIC_VECTOR}:{DIAGNOSTIC_INTERVAL}:{DIAGNOSTIC_INTERVAL}:"
    rf"{DIAGNOSTIC_NUMBER}:{DIAGNOSTIC_BOOLEAN}:{DIAGNOSTIC_BOOLEAN}:"
    rf"(?:na|{DIAGNOSTIC_NUMBER}):(?:na|{DIAGNOSTIC_NUMBER}):"
    rf"{DIAGNOSTIC_NUMBER}:{DIAGNOSTIC_VECTOR}:{DIAGNOSTIC_BOOLEAN})"
)
DIAGNOSTIC_EPA_RECORD = (
    rf"{DIAGNOSTIC_INTEGER}:(?:na|{DIAGNOSTIC_INTEGER}):"
    rf"{DIAGNOSTIC_VECTOR}:{DIAGNOSTIC_VECTOR}:{DIAGNOSTIC_VECTOR}:"
    rf"{DIAGNOSTIC_VECTOR}:{DIAGNOSTIC_NUMBER}:{DIAGNOSTIC_VECTOR}:"
    rf"{DIAGNOSTIC_NUMBER}:{DIAGNOSTIC_NUMBER}:"
    rf"(?:continue|epsilon|iterationLimit):"
    rf"(?:na|{DIAGNOSTIC_INTEGER}(?:,{DIAGNOSTIC_INTEGER})*)?:{DIAGNOSTIC_BOOLEAN}"
)
DIAGNOSTIC_VALUE_PATTERNS = {
    **dict.fromkeys(("a.transform", "b.transform"),
                    ",".join((DIAGNOSTIC_NUMBER,) * 6)),
    **dict.fromkeys(("a.center.local", "b.center.local", "a.center.world",
                     "b.center.world", "penetration.normal", "gjk.initial.centerDirection",
                     "gjk.initial.effectiveDirection", "sat.winner.preOrientation",
                     "sat.winner.finalAxis"), DIAGNOSTIC_VECTOR),
    **dict.fromkeys(("manifold.normal", "epa.edge.a", "epa.edge.b", "epa.edge.normal",
                     "epa.terminal.support"), rf"(?:na|{DIAGNOSTIC_VECTOR})"),
    **dict.fromkeys(("a.foci.world", "b.foci.world", "a.axes.withB", "b.axes.withA"),
                    rf"(?:null|{DIAGNOSTIC_VECTORS})"),
    **dict.fromkeys(("a.shape.local", "b.shape.local"), DIAGNOSTIC_SHAPE),
    **dict.fromkeys(("a.polygon.edgeArithmetic", "b.polygon.edgeArithmetic"),
                    rf"(?:na|{DIAGNOSTIC_POLYGON_EDGE}(?:;{DIAGNOSTIC_POLYGON_EDGE})*)"),
    **dict.fromkeys(("clip.probe.feature.a", "clip.probe.feature.b"),
                    rf"(?:na|{DIAGNOSTIC_FEATURE})"),
    **dict.fromkeys(("penetration.depth", "sat.winner.centerDot", "sat.winner.depth",
                     "epa.replay.epsilon"), DIAGNOSTIC_NUMBER),
    **dict.fromkeys(("epa.edge.distance", "epa.terminal.projection",
                     "epa.terminal.delta"), rf"(?:na|{DIAGNOSTIC_NUMBER})"),
    **dict.fromkeys(("epa.replay.iteration", "epa.replay.maxIterations",
                     "sat.winner.index", "step"), DIAGNOSTIC_INTEGER),
    **dict.fromkeys(("hit", "sat.replay.hit", "sat.replay.matchesResult",
                     "sat.winner.orientationFlip", "epa.queue.reconstructedMatches"),
                    DIAGNOSTIC_BOOLEAN),
    **dict.fromkeys(("booleanHit", "clipped", "epa.replay.normalMatchesResult",
                     "epa.replay.depthMatchesResult"), rf"(?:na|{DIAGNOSTIC_BOOLEAN})"),
    "manifold.count": r"(?:na|[012])",
    "sat.winner.source": r"(?:a|b|[01])",
    "selection": r"(?:unavailable|epaSourceReplay|satSourceReplay)",
    "epa.replay.stop": r"(?:notRun|epsilon|iterationLimit)",
    "epa.replay.identity": "unobserved",
    "epa.replay.simplex": rf"(?:{DIAGNOSTIC_VECTORS})?",
    "epa.iteration.records": rf"(?:{DIAGNOSTIC_EPA_RECORD}(?:;{DIAGNOSTIC_EPA_RECORD})*)?",
    "sat.candidates": rf"{DIAGNOSTIC_SAT_CANDIDATE}(?:;{DIAGNOSTIC_SAT_CANDIDATE})*",
}
DIAGNOSTIC_NUMBER_PARTS = re.compile(rf"({DIAGNOSTIC_DECIMAL})@({DIAGNOSTIC_INTEGER})")


def verify_collision_value(key: str, value: str) -> None:
    pattern = DIAGNOSTIC_VALUE_PATTERNS.get(key)
    if pattern is None and re.fullmatch(r"support\.[0-5]\.(?:direction|a|b\.negated|minkowski)", key):
        pattern = DIAGNOSTIC_VECTOR
    if pattern is None and re.fullmatch(r"manifold\.point\.[01]\.(?:position|depth)", key):
        pattern = DIAGNOSTIC_VECTOR if key.endswith("position") else DIAGNOSTIC_NUMBER
    if pattern is None and re.fullmatch(r"manifold\.point\.[01]\.id", key):
        pattern = (rf"(?:distance|indexed:{DIAGNOSTIC_INTEGER}:"
                   rf"{DIAGNOSTIC_INTEGER}:{DIAGNOSTIC_INTEGER}:{DIAGNOSTIC_BOOLEAN})")
    if pattern is None:
        return
    if re.fullmatch(pattern, value) is None:
        raise ValueError(f"collision diagnostic {key} has incomplete numeric syntax")
    for match in DIAGNOSTIC_NUMBER_PARTS.finditer(value):
        decimal, bits_text = match.groups()
        bits = int(bits_text)
        if not -(1 << 63) <= bits < (1 << 63):
            raise ValueError(f"collision diagnostic {key} has invalid raw bits")
        parsed = float(decimal)
        if math.isinf(parsed) and decimal not in ("Infinity", "-Infinity"):
            raise ValueError(f"collision diagnostic {key} finite decimal overflows Double")
        if parsed == 0:
            if any(digit in "123456789" for digit in
                   re.split(r"[eE]", decimal, maxsplit=1)[0]):
                raise ValueError(f"collision diagnostic {key} finite decimal underflows Double")
            if decimal not in ("0", "0.0", "-0", "-0.0"):
                raise ValueError(f"collision diagnostic {key} has non-source zero spelling")
        raw = struct.unpack(">q", struct.pack(">d", parsed))[0]
        if decimal == "NaN":
            if bits & 0x7ff0000000000000 != 0x7ff0000000000000 or bits & 0xfffffffffffff == 0:
                raise ValueError(f"collision diagnostic {key} has invalid NaN bits")
        # Kotlin/JS prints negative zero as "0"; Wasm keeps the minus sign.
        elif raw != bits and not (decimal == "0" and bits == -(1 << 63)):
            raise ValueError(f"collision diagnostic {key} has mismatched raw bits")


def common_corpus_cases(root: Path, candidate_sha: str, module: str) -> set[tuple[str, str]]:
    if module not in MODULES:
        raise ValueError(f"unknown corpus module: {module}")
    inputs = (full_corpus.MANIFEST_PATH, full_corpus.MAP_PATH, full_corpus.PAIR_PATH)
    for relative in inputs:
        committed = full_corpus.committed_bytes(root, candidate_sha, relative)
        if (root / relative).read_bytes() != committed:
            raise ValueError(f"candidate commit bytes differ: {relative}")
    manifest = json.loads((root / full_corpus.MANIFEST_PATH).read_bytes())
    with (root / full_corpus.MAP_PATH).open(newline="") as stream:
        mapping = list(csv.DictReader(stream, delimiter="\t"))
    if ((manifest.get("schema"), manifest.get("kind"), manifest.get("policy")) !=
            (1, "full-common-corpus", "production")):
        raise ValueError("full common corpus manifest is invalid")
    if full_corpus.digest((root / full_corpus.MAP_PATH).read_bytes()) != full_corpus.REVIEWED_MAP_SHA256:
        raise ValueError("reviewed original map hash differs")
    if full_corpus.digest((root / full_corpus.PAIR_PATH).read_bytes()) != full_corpus.REVIEWED_PAIRS_SHA256:
        raise ValueError("reviewed pair map hash differs")
    if full_corpus.paired_bytes(mapping) != (root / full_corpus.PAIR_PATH).read_bytes():
        raise ValueError("reviewed pair map differs from original map")
    if manifest != full_corpus.make_manifest(full_corpus.scan_sources(root), mapping,
                                             production=True, repository=root):
        raise ValueError("full common corpus differs from source tree or reviewed map")
    cases = {(case["classname"], case["method"]) for case in manifest["cases"]
             if case["module"] == module and case["source_set"] == "commonTest"}
    required = 2465 if module == "dyn4k-core" else 58
    if len(cases) != required:
        raise ValueError(f"full common corpus count differs: {module} {len(cases)}")
    return cases


def source_cases(source_root: Path) -> set[tuple[str, str]]:
    cases: set[tuple[str, str]] = set()
    annotations = 0
    for source in sorted(source_root.rglob("*.kt")):
        content = source.read_text()
        package_match = PACKAGE.search(content)
        if not package_match:
            raise ValueError(f"package missing: {source}")
        package = package_match.group(1)
        class_name = None
        waiting = False
        for line in content.splitlines():
            match = CLASS.match(line)
            if match:
                class_name = match.group(1)
            if "@Test" in line:
                annotations += line.count("@Test")
                waiting = True
            if waiting:
                function = FUNCTION.search(line)
                if function:
                    if not class_name:
                        raise ValueError(f"test class missing: {source}")
                    case = (f"{package}.{class_name}", function.group(1))
                    if case in cases:
                        raise ValueError(f"duplicate test: {case}")
                    cases.add(case)
                    waiting = False
        if waiting:
            raise ValueError(f"test function missing: {source}")
    if not cases or len(cases) != annotations:
        raise ValueError(f"test inventory incomplete: {len(cases)} functions, {annotations} annotations")
    return cases


def verify_collision_diagnostics(suite: ET.Element) -> dict[str, object]:
    output = suite.findtext("system-out") or ""
    rows = [line for line in output.splitlines()
            if "DYN4K_COLLISION_DIAGNOSTIC" in line]
    if len(rows) != 72:
        raise ValueError(f"collision diagnostic row count differs: {len(rows)}")
    expected: dict[tuple[str, str, str, str, str], str] = {}
    for fixture, (_, detect_method) in COLLISION_DIAGNOSTIC_METHODS.items():
        for step in range(12):
            method = detect_method if step < 4 else "getClipManifold"
            phase = ("center" if step < 2 or 4 <= step < 8 else "shifted")
            order = "forward" if step % 2 == 0 else "reverse"
            algorithm = (("gjk" if detect_method == "detectGjk" else "sat")
                         if step < 4 else "gjk" if step % 4 < 2 else "sat")
            expected[(fixture, method, phase, order, str(step))] = algorithm
    seen: set[tuple[str, str, str, str, str]] = set()
    for row in rows:
        parts = row.split("\t")
        if parts[:2] != ["[log] DYN4K_COLLISION_DIAGNOSTIC", "v2"]:
            raise ValueError("collision diagnostic version or row prefix differs")
        if any("=" not in item for item in parts[2:]):
            raise ValueError("collision diagnostic field is incomplete")
        pairs = [item.split("=", 1) for item in parts[2:]]
        keys = [key for key, _ in pairs]
        fields = dict(pairs)
        if len(keys) != len(fields) or any(not key for key in keys):
            raise ValueError("collision diagnostic has duplicate or empty field names")
        identity = tuple(fields.get(key, "") for key in
                         ("fixture", "method", "phase", "order", "step"))
        algorithm = expected.get(identity)
        if algorithm is None or identity in seen or fields.get("algorithm") != algorithm:
            raise ValueError("collision diagnostic identity differs or repeats")
        seen.add(identity)
        if (fields.get("provider") != "dyn4k" or fields.get("hit") not in ("true", "false")
                or fields.get("epa.iteration.schema") != COLLISION_DIAGNOSTIC_EPA_SCHEMA
                or fields.get("epa.replay.depthMatchesResult") not in ("true", "false", "na")):
            raise ValueError("collision diagnostic required values differ")
        if identity[1] == "getClipManifold":
            if (fields.get("booleanHit") != "na" or
                    fields.get("clipped") not in ("true", "false") or
                    fields.get("manifold.count") not in ("0", "1", "2")):
                raise ValueError("collision diagnostic manifold values differ")
            point_count = int(fields["manifold.count"])
            if (fields["clipped"] == "true") != (point_count > 0):
                raise ValueError("collision diagnostic manifold point count differs")
        else:
            if (fields.get("booleanHit") not in ("true", "false") or
                    fields.get("clipped") != "na" or fields.get("manifold.count") != "na"):
                raise ValueError("collision diagnostic detect values differ")
            point_count = 0
        sat_fields: tuple[str, ...] = ()
        if algorithm == "sat":
            if fields.get("sat.replay.hit") not in ("true", "false"):
                raise ValueError("collision diagnostic SAT replay result differs")
            sat_fields = COLLISION_DIAGNOSTIC_SAT_FIELDS
            if fields["sat.replay.hit"] == "true":
                sat_fields += COLLISION_DIAGNOSTIC_SAT_HIT_FIELDS
        point_fields = tuple(f"manifold.point.{i}.{part}" for i in range(point_count)
                             for part in ("position", "depth", "id"))
        if keys != list(COLLISION_DIAGNOSTIC_PREFIX_FIELDS + sat_fields +
                        COLLISION_DIAGNOSTIC_EPA_FIELDS + point_fields):
            raise ValueError("collision diagnostic v2 row fields differ")
        if any(not value for key, value in pairs if key not in (
                "epa.replay.simplex", "epa.iteration.records", "sat.candidates")):
            raise ValueError("collision diagnostic v2 row has empty required content")
        for key, value in pairs:
            verify_collision_value(key, value)
        for i in range(point_count):
            point_id = fields[f"manifold.point.{i}.id"]
            if point_id != "distance" and re.fullmatch(
                    r"indexed:\d+:\d+:\d+:(?:true|false)", point_id) is None:
                raise ValueError("collision diagnostic manifold point identity differs")
    if seen != set(expected):
        raise ValueError("collision diagnostic identities are incomplete")
    return {"diagnostic_rows": len(rows),
            "diagnostic_sha256": hashlib.sha256("\n".join(rows).encode()).hexdigest()}


def verify_reports(
    report_dir: Path,
    expected: set[tuple[str, str]],
    task_name: str,
    runtime_marker: str,
    require_collision_diagnostics: bool = False,
) -> dict[str, object]:
    selected = re.fullmatch(r"(ChromeHeadless|Firefox)(\d+)", runtime_marker)
    if selected is None:
        raise ValueError(f"invalid selected browser marker: {runtime_marker}")
    files = sorted(report_dir.glob("TEST-*.xml"))
    if not files:
        raise ValueError(f"missing XML reports: {report_dir}")
    observed: list[tuple[str, str]] = []
    diagnostic_suites: list[ET.Element] = []
    failures = 0
    skipped = 0
    for path in files:
        suite = ET.parse(path).getroot()
        if suite.tag != "testsuite":
            raise ValueError(f"invalid test suite: {path}")
        if suite.attrib.get("name") == f"{task_name}.{COLLISION_DIAGNOSTIC_CLASS}":
            diagnostic_suites.append(suite)
        cases = suite.findall("testcase")
        counts = {key: int(suite.attrib[key]) for key in ("tests", "failures", "errors", "skipped")}
        actual_failures = sum(case.find("failure") is not None for case in cases)
        actual_errors = sum(case.find("error") is not None for case in cases)
        actual_skips = sum(case.find("skipped") is not None for case in cases)
        if counts != {"tests": len(cases), "failures": actual_failures,
                      "errors": actual_errors, "skipped": actual_skips}:
            raise ValueError(f"report counts differ from cases: {path}")
        failures += actual_failures + actual_errors
        skipped += actual_skips
        for case in cases:
            name = case.attrib.get("name", "")
            class_name = case.attrib.get("classname", "")
            parts = name.rsplit("[", 1)
            platform = parts[1][:-1].split(", ") if len(parts) == 2 and name.endswith("]") else []
            observed_browser = re.fullmatch(
                r"(ChromeHeadless|Firefox)(\d+(?:\.\d+)*)", platform[2]
            ) if len(platform) == 4 and platform[1] == "browser" else None
            if (observed_browser is None or observed_browser.group(1) != selected.group(1)
                    or observed_browser.group(2).split(".", 1)[0] != selected.group(2)):
                raise ValueError(f"wrong runtime or missing runtime identity: {name}")
            prefix = f"{task_name}."
            if not class_name.startswith(prefix):
                raise ValueError(f"wrong test task: {class_name}")
            observed.append((class_name[len(prefix):], name.split("[", 1)[0]))
    if failures:
        raise ValueError(f"{failures} failed tests")
    if skipped:
        raise ValueError(f"{skipped} skipped tests")
    if not observed or len(observed) != len(set(observed)):
        raise ValueError("zero or duplicate test identities")
    if set(observed) != expected:
        raise ValueError(
            f"missing or unexpected tests: missing={sorted(expected - set(observed))[:5]} "
            f"unexpected={sorted(set(observed) - expected)[:5]}"
        )
    result: dict[str, object] = {
        "expected": len(expected), "executed": len(observed), "failures": 0,
        "skipped": 0, "cases": sorted([list(case) for case in observed]),
        "report_files": [str(path) for path in files],
    }
    diagnostic_cases = {(COLLISION_DIAGNOSTIC_CLASS, method)
                        for method, _ in COLLISION_DIAGNOSTIC_METHODS.values()}
    if require_collision_diagnostics:
        if not diagnostic_cases.issubset(expected) or len(diagnostic_suites) != 1:
            raise ValueError("collision diagnostic six-case suite is incomplete")
        result.update(verify_collision_diagnostics(diagnostic_suites[0]))
    return result


def verify_wasmtime_output(
    output: str, expected: set[tuple[str, str]]
) -> dict[str, object]:
    suites: list[str] = []
    active: tuple[str, str] | None = None
    finished: list[tuple[str, str]] = []
    failures = 0
    skipped = 0
    for line in output.splitlines():
        event = TEAMCITY.match(line)
        if not event:
            continue
        kind, name = event.groups()
        if kind == "testSuiteStarted":
            suites.append(name)
        elif kind == "testSuiteFinished":
            if not suites or suites.pop() != name or active:
                raise ValueError("unbalanced test suite")
        elif kind == "testStarted":
            if len(suites) != 2 or active:
                raise ValueError("overlapping or unscoped test")
            active = (f"{suites[0]}.{suites[1]}", name)
        elif kind == "testFinished":
            if not active or active[1] != name:
                raise ValueError("test finish differs from start")
            finished.append(active)
            active = None
        elif kind == "testFailed":
            failures += 1
        elif kind == "testIgnored":
            skipped += 1
    if active or suites:
        raise ValueError("unfinished tests or suites")
    if failures or skipped:
        raise ValueError(f"{failures} failed and {skipped} skipped tests")
    if not finished or len(finished) != len(set(finished)):
        raise ValueError("zero or duplicate test identities")
    if set(finished) != expected:
        raise ValueError(
            f"missing or unexpected tests: missing={sorted(expected - set(finished))[:5]} "
            f"unexpected={sorted(set(finished) - expected)[:5]}"
        )
    return {"expected": len(expected), "executed": len(finished), "failures": 0,
            "skipped": 0, "cases": sorted([list(case) for case in finished])}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_consumer_physics_contract(source: Path) -> str:
    if (not source.is_file() or sha256(source) != PHYSICS_CONSUMER_SHA256
            or ("qualification.StagedWorldTest",
                "stagedModulesShareBodiesAndDeliverCollisionCallbacks") not in source_cases(source.parent)):
        raise ValueError("staged physics contract differs from reviewed assertions")
    return PHYSICS_CONSUMER_SHA256


def command(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, env=env, text=True, capture_output=True, check=False)


def is_pinned_consumer_lock(root: Path, problem: str) -> bool:
    relative = CONSUMER / "kotlin-js-store/yarn.lock"
    lock = root / relative
    return (problem == f"untracked candidate input: {relative}"
            and lock.is_file() and not lock.is_symlink()
            and not lock.parent.is_symlink()
            and sha256(lock) == CONSUMER_YARN_LOCK_SHA256)


def reviewed_consumer_lock(root: Path, expected_sha: str) -> bytes | None:
    if expected_sha == CONSUMER_LOCK_SOURCE_BASE:
        return None
    descendant = command(["git", "merge-base", "--is-ancestor",
                          CONSUMER_LOCK_SOURCE_BASE, expected_sha], root)
    if descendant.returncode:
        return None
    fixture = root / CONSUMER_YARN_LOCK_FIXTURE
    if not fixture.is_file() or fixture.is_symlink():
        raise ValueError("reviewed consumer lock fixture is absent or not regular")
    raw = fixture.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CONSUMER_YARN_LOCK_SHA256:
        raise ValueError("reviewed consumer lock fixture bytes differ")
    tree = command(["git", "ls-tree", expected_sha, "--",
                    str(CONSUMER_YARN_LOCK_FIXTURE)], root)
    match = re.fullmatch(
        r"100644 blob ([0-9a-f]+)\t" + re.escape(str(CONSUMER_YARN_LOCK_FIXTURE)) + r"\n",
        tree.stdout) if tree.returncode == 0 else None
    if match is None:
        raise ValueError("reviewed consumer lock fixture is not committed as a regular file")
    object_format = command(["git", "rev-parse", "--show-object-format"], root)
    if object_format.returncode or object_format.stdout.strip() not in ("sha1", "sha256"):
        raise ValueError("candidate Git object format is unavailable")
    blob = b"blob " + str(len(raw)).encode() + b"\0" + raw
    if hashlib.new(object_format.stdout.strip(), blob).hexdigest() != match.group(1):
        raise ValueError("committed reviewed consumer lock fixture bytes differ")
    return raw


def prepare_consumer_lock(root: Path, expected_sha: str) -> None:
    raw = reviewed_consumer_lock(root, expected_sha)
    if raw is None:
        return
    lock = root / CONSUMER / "kotlin-js-store/yarn.lock"
    if lock.parent.is_symlink() or lock.is_symlink():
        raise ValueError("generated consumer lock path is symlinked")
    if lock.exists():
        if not lock.is_file() or sha256(lock) != CONSUMER_YARN_LOCK_SHA256:
            raise ValueError("generated consumer lock differs from reviewed bytes")
        return
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock.parent.is_symlink():
        raise ValueError("generated consumer lock parent is symlinked")
    with lock.open("xb") as stream:
        stream.write(raw)
    if sha256(lock) != CONSUMER_YARN_LOCK_SHA256:
        raise ValueError("generated consumer lock copy differs from reviewed bytes")


def candidate_identity(root: Path, expected_sha: str) -> None:
    if not full_corpus.SHA40.fullmatch(expected_sha):
        raise ValueError("candidate SHA is invalid")
    head = command(["git", "rev-parse", "HEAD"], root)
    if head.returncode or head.stdout.strip() != expected_sha:
        raise ValueError(f"source SHA differs: {head.stdout.strip()}")
    ancestor = command(["git", "merge-base", "--is-ancestor", COMMON_CORPUS_CANDIDATE,
                        expected_sha], root)
    if ancestor.returncode:
        raise ValueError("candidate does not descend from committed full corpus")
    consumer_generated = tuple(
        f"untracked candidate input: {CONSUMER}/{directory}/"
        for directory in ("build", ".gradle", ".kotlin")
    )
    problems = [problem for problem in full_corpus.candidate_checkout_problems(root, expected_sha)
                if not problem.startswith(consumer_generated)
                and not is_pinned_consumer_lock(root, problem)]
    if problems:
        raise ValueError(f"source checkout is dirty: {problems[:5]}")
    reviewed_consumer_lock(root, expected_sha)
    object_format = command(["git", "rev-parse", "--show-object-format"], root)
    if object_format.returncode or object_format.stdout.strip() not in ("sha1", "sha256"):
        raise ValueError("candidate Git object format is unavailable")
    sources = command(["git", "ls-tree", "-r", "-z", expected_sha, "--",
                       "dyn4k-core/src", "dyn4k/src", f"{CONSUMER}/src"], root)
    if sources.returncode or not sources.stdout:
        raise ValueError("candidate committed source inventory is unavailable")
    for record in sources.stdout.rstrip("\0").split("\0"):
        metadata, relative = record.split("\t", 1)
        mode, kind, committed_digest = metadata.split()
        if mode not in ("100644", "100755") or kind != "blob":
            raise ValueError(f"candidate source file is not regular: {relative}")
        raw = (root / relative).read_bytes()
        blob = b"blob " + str(len(raw)).encode() + b"\0" + raw
        if hashlib.new(object_format.stdout.strip(), blob).hexdigest() != committed_digest:
            raise ValueError(f"committed source bytes differ: {relative}")
    if sha256(root / "tools/qualification/full_corpus.py") != CORPUS_GENERATOR_SHA256:
        raise ValueError("reviewed corpus generator differs")
    core = common_corpus_cases(root, expected_sha, "dyn4k-core")
    facade = common_corpus_cases(root, expected_sha, "dyn4k")
    manifest = json.loads((root / full_corpus.MANIFEST_PATH).read_bytes())
    counts = manifest["counts"]
    if (counts["total_methods"] != 2526 or counts["unresolved_mappings"] != 0
            or len(manifest["cases"]) != 2526
            or len([case for case in manifest["cases"] if case["source_set"] == "jvmTest"]) != 3
            or core != source_cases(root / "dyn4k-core/src/commonTest/kotlin")
            or facade != source_cases(root / "dyn4k/src/commonTest/kotlin")):
        raise ValueError("candidate corpus suite or source inventory differs")
    if (sha256(root / CONSUMER / "build.gradle.kts") != CONSUMER_BUILD_SHA256
            or sha256(root / CONSUMER / "settings.gradle.kts") != CONSUMER_SETTINGS_SHA256):
        raise ValueError("staged consumer dependency pins differ")
    verify_consumer_physics_contract(root / PHYSICS_CONSUMER_SOURCE)
    if source_cases(root / CONSUMER / "src/commonTest/kotlin") != {
        ("qualification.StagedWorldTest", "stagedModulesShareBodiesAndDeliverCollisionCallbacks")
    }:
        raise ValueError("staged consumer test inventory differs")


def staged_files(root: Path) -> dict[str, str]:
    staging = root / "build/staging-repository/io/github/rubixhacker"
    license_bytes = (root / "LICENSE.md").read_bytes()
    hashes: dict[str, str] = {}
    for module in MODULES:
        root_publication = staging / module / VERSION
        for extension in ("jar", "module", "pom"):
            path = root_publication / f"{module}-{VERSION}.{extension}"
            if not path.is_file():
                raise ValueError(f"missing staged artifact: {path}")
            hashes[str(path.relative_to(root))] = sha256(path)
        for classifier in ("sources.jar", "license.md"):
            path = root_publication / f"{module}-{VERSION}-{classifier}"
            if not path.is_file():
                raise ValueError(f"missing staged artifact: {path}")
            if classifier == "license.md" and path.read_bytes() != license_bytes:
                raise ValueError(f"staged license differs from source: {path}")
            hashes[str(path.relative_to(root))] = sha256(path)
        for target in TARGETS:
            publication = f"{module}-{target.lower().replace('wasmjs', 'wasm-js').replace('wasmwasi', 'wasm-wasi')}"
            directory = staging / publication / VERSION
            for extension in ("klib", "module", "pom"):
                path = directory / f"{publication}-{VERSION}.{extension}"
                if not path.is_file():
                    raise ValueError(f"missing staged artifact: {path}")
                hashes[str(path.relative_to(root))] = sha256(path)
            for classifier in ("sources.jar", "license.md"):
                path = directory / f"{publication}-{VERSION}-{classifier}"
                if not path.is_file():
                    raise ValueError(f"missing staged artifact: {path}")
                if classifier == "license.md" and path.read_bytes() != license_bytes:
                    raise ValueError(f"staged license differs from source: {path}")
                hashes[str(path.relative_to(root))] = sha256(path)
    return hashes


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def sealed_lane(lane: dict[str, object]) -> dict[str, object]:
    content = {key: value for key, value in lane.items() if key != "receipt_seal_sha256"}
    return {**content, "receipt_seal_sha256": full_corpus.canonical_digest(content)}


def stage(root: Path, sha: str, output: Path) -> int:
    output.mkdir(parents=True, exist_ok=True)
    result: dict[str, object] = {"candidate_sha": sha, "status": "FAILED"}
    try:
        candidate_identity(root, sha)
        prepare_consumer_lock(root, sha)
        candidate_identity(root, sha)
        for module in MODULES:
            common_corpus_cases(root, sha, module)
        tasks = [f":{module}:publish{publication}PublicationToStagingRepository"
                 for module in MODULES
                 for publication in ("KotlinMultiplatform", "Js", "WasmJs", "WasmWasi")]
        args = [str(root / "gradlew"), *tasks, "--rerun-tasks", "--console=plain", "--no-daemon"]
        env = dict(os.environ, JAVA_HOME=os.environ.get("JAVA_HOME", "/tmp/dyn4k-tools/jdk21"),
                   YARN_OFFLINE="true")
        completed = command(args, root, env)
        log = output / "stage-console.log"
        log.write_text(completed.stdout + completed.stderr)
        result.update(command=args, exit_code=completed.returncode, console=str(log),
                      console_sha256=sha256(log),
                      manifest_sha256=sha256(root / full_corpus.MANIFEST_PATH),
                      source_tree_sha256=json.loads((root / full_corpus.MANIFEST_PATH).read_text())[
                          "source_tree_sha256"])
        if completed.returncode:
            raise ValueError("staging command failed")
        candidate_identity(root, sha)
        result["artifacts"] = staged_files(root)
        result["status"] = "PASSED"
    except (OSError, ValueError) as error:
        result["reason"] = str(error)
    write_json(output / "stage.json", result)
    return 0 if result["status"] == "PASSED" else 1


def verified_stage(root: Path, sha: str, receipt: Path) -> dict[str, str]:
    recorded = json.loads(receipt.read_text())
    if recorded.get("candidate_sha") != sha or recorded.get("status") != "PASSED":
        raise ValueError("staging receipt does not bind this passing candidate")
    actual = staged_files(root)
    if recorded.get("artifacts") != actual:
        raise ValueError("staged artifact hashes differ from receipt")
    console = Path(str(recorded.get("console", ""))).resolve()
    if (not console.is_file() or recorded.get("console_sha256") != sha256(console)
            or recorded.get("exit_code") != 0 or recorded.get("manifest_sha256") !=
            sha256(root / full_corpus.MANIFEST_PATH)):
        raise ValueError("staging console or manifest differs from receipt")
    return actual


def audit_lane_receipt(receipt: Path) -> dict[str, object]:
    lane = json.loads(receipt.read_text())
    if (lane.get("receipt_seal_sha256") is not None and
            sealed_lane(lane)["receipt_seal_sha256"] != lane["receipt_seal_sha256"]):
        raise ValueError("lane receipt seal differs")
    if lane.get("status") not in ("PASSED", "FAILED"):
        raise ValueError("invalid lane status")
    modules = lane.get("modules", {})
    if not isinstance(modules, dict):
        raise ValueError("invalid lane modules")
    lane_dir = receipt.parent.resolve()

    def check(path_text: object, digest: object) -> None:
        path = Path(str(path_text)).resolve()
        if not isinstance(digest, str) or not path.is_relative_to(lane_dir) or not path.is_file():
            raise ValueError(f"missing or external evidence digest: {path}")
        if sha256(path) != digest:
            raise ValueError(f"evidence digest differs: {path}")

    for module in modules.values():
        if not isinstance(module, dict):
            raise ValueError("invalid module receipt")
        for field, digest_field in (
            ("gradle_console", "gradle_console_sha256"),
            ("gradle_stdout", "gradle_stdout_sha256"),
            ("gradle_stderr", "gradle_stderr_sha256"),
            ("raw_console", "raw_console_sha256"),
            ("raw_stdout", "raw_stdout_sha256"),
            ("raw_stderr", "raw_stderr_sha256"),
            ("linked_executable", "linked_sha256"),
            ("karma_config", "karma_config_sha256"),
            ("karma_reporter_attestation", "karma_reporter_attestation_sha256"),
            ("karma_reporter_retained", "karma_reporter_sha256"),
            ("browser_attestation", "browser_attestation_sha256"),
            ("result_json", "result_json_sha256"),
        ):
            if field in module:
                check(module[field], module.get(digest_field))
        for report in module.get("raw_xml", []):
            if not isinstance(report, dict):
                raise ValueError("invalid raw XML receipt")
            check(report.get("path"), report.get("sha256"))
        if "result_json" in module:
            saved = json.loads(Path(str(module["result_json"])).read_text())
            recorded = {key: value for key, value in module.items()
                        if key not in ("result_json", "result_json_sha256")}
            if saved != recorded:
                raise ValueError("module result differs from lane receipt")
        if "browser_attestation" in module and module.get("status") == "PASSED":
            launches = [json.loads(line) for line in Path(str(module["browser_attestation"]))
                        .read_text().splitlines()]
            if not launches or launches != module.get("browser_processes"):
                raise ValueError("browser process attestations differ from lane receipt")
            if any(launch.get("selected_sha256") != lane.get("runtime_sha256")
                   or launch.get("runtime") != lane.get("runtime") for launch in launches):
                raise ValueError("browser process selected a different runtime")
        if module.get("status") == "PASSED":
            required = {"gradle_console", "linked_executable"}
            if lane.get("target") == "wasmWasi":
                required.add("raw_console")
            else:
                required.update(("browser_attestation", "karma_port", "karma_config",
                                 "karma_config_sha256", "karma_reporter_attestation",
                                 "karma_reporter_attestation_sha256",
                                 "karma_reporter_retained", "karma_reporter_sha256",
                                 "karma_reporter_source", "karma_reporter_source_sha256"))
            if not required.issubset(module) or (lane.get("target") != "wasmWasi"
                                                 and not module.get("raw_xml")):
                raise ValueError("passing module has missing raw evidence digest")
    if lane["status"] == "PASSED" and (
        set(modules) != {*MODULES, "consumer"}
        or any(module.get("status") != "PASSED" for module in modules.values())
    ):
        raise ValueError("passing lane has incomplete module receipts")
    if lane["status"] == "PASSED":
        if not lane.get("receipt_seal_sha256"):
            raise ValueError("passing lane has no receipt seal")
        root = Path(str(lane.get("candidate_root", ""))).resolve()
        sha = lane.get("candidate_sha")
        if not isinstance(sha, str):
            raise ValueError("passing lane has no candidate SHA")
        candidate_identity(root, sha)
        stage_receipt = Path(str(lane.get("staging_receipt", ""))).resolve()
        if (not stage_receipt.is_file() or lane.get("staging_receipt_sha256") !=
                sha256(stage_receipt) or lane.get("artifact_hashes") !=
                verified_stage(root, sha, stage_receipt)):
            raise ValueError("passing lane has no matching staged artifacts")
        binary = Path(str(lane.get("runtime_binary", ""))).resolve()
        if sha256(binary) != lane.get("runtime_sha256"):
            raise ValueError("runtime binary digest differs")
        version = runtime_version(binary, lane.get("target"), lane.get("runtime"),
                                  lane.get("expected_runtime_version"),
                                  lane.get("version_role"))
        if version != lane.get("runtime_version"):
            raise ValueError("runtime version differs from receipt")
        target = lane["target"]
        configuration = lane.get("configuration")
        if target not in TARGETS or configuration not in ("development", "production"):
            raise ValueError("passing lane has invalid target or configuration")
        manifest = json.loads((root / full_corpus.MANIFEST_PATH).read_bytes())
        if (lane.get("manifest_sha256") != sha256(root / full_corpus.MANIFEST_PATH)
                or lane.get("source_tree_sha256") != manifest["source_tree_sha256"]
                or lane.get("original_map_sha256") != sha256(root / full_corpus.MAP_PATH)
                or lane.get("reviewed_pairs_sha256") != sha256(root / full_corpus.PAIR_PATH)):
            raise ValueError("source map or manifest differs from receipt")
        for name, module in modules.items():
            expected = (common_corpus_cases(root, sha, name) if name in MODULES else
                        source_cases(test_source(root, "consumer")))
            if name == "consumer":
                verify_consumer_physics_contract(root / PHYSICS_CONSUMER_SOURCE)
            if (module.get("candidate_sha") != sha or module.get("target") != target
                    or module.get("runtime") != lane["runtime"]
                    or module.get("configuration") != configuration
                    or module.get("runtime_sha256") != lane["runtime_sha256"]
                    or module.get("staging_receipt") != str(stage_receipt)
                    or module.get("gradle_exit_code") != 0):
                raise ValueError(f"passing {name} identity or Gradle result differs")
            if not all(key in module for key in ("gradle_stdout", "gradle_stderr")):
                raise ValueError(f"passing {name} has no separate Gradle streams")
            console = Path(module["gradle_console"]).read_text()
            if console != (Path(module["gradle_stdout"]).read_text() +
                           Path(module["gradle_stderr"]).read_text()):
                raise ValueError(f"passing {name} Gradle streams differ")
            if "BUILD SUCCESSFUL" not in console:
                raise ValueError(f"passing {name} has no successful Gradle console")
            started = module.get("started_ns")
            finished = module.get("finished_ns")
            if (type(started) is not int or type(finished) is not int
                    or started <= 0 or finished < started):
                raise ValueError(f"passing {name} has no fresh invocation window")
            if module.get("gradle_command") != gradle_command(root, name, target, configuration):
                raise ValueError(f"passing {name} Gradle configuration or task differs")
            source = linked_file(test_project(root, name), target, configuration, name)
            if module.get("linked_source") != str(source):
                raise ValueError(f"passing {name} linked source configuration differs")
            linked = Path(module["linked_executable"]).resolve()
            if linked != (lane_dir / name / f"linked-executable{source.suffix}"):
                raise ValueError(f"passing {name} retained linked executable differs")
            verify_linked_source_digest(source, linked, module.get("linked_source_sha256"),
                                        module.get("linked_sha256"), target)
            if target == "wasmWasi":
                if not all(key in module for key in ("raw_stdout", "raw_stderr")):
                    raise ValueError(f"passing {name} has no separate Wasmtime streams")
                if Path(module["raw_console"]).read_text() != (
                        Path(module["raw_stdout"]).read_text() +
                        Path(module["raw_stderr"]).read_text()):
                    raise ValueError(f"passing {name} Wasmtime streams differ")
                command_expected = [str(binary), "run", "-W", "gc=y", "-W",
                                    "exceptions=y", "-W", "function-references=y",
                                    "--invoke", "startUnitTests", str(linked)]
                if module.get("command") != command_expected or module.get("exit_code") != 0:
                    raise ValueError(f"passing {name} Wasmtime invocation differs")
                observed = verify_wasmtime_output(Path(module["raw_stdout"]).read_text(),
                                                  expected)
            else:
                port = module["karma_port"]
                config_path = lane_dir / name / "karma.conf.js"
                if (type(port) is not int or not 1 <= port <= 65535
                        or module["karma_config"] != str(config_path)):
                    raise ValueError(f"passing {name} Karma port configuration differs")
                config_text = config_path.read_text()
                port_setter = f"config.set({{port: {port}}});"
                if (re.findall(r"(?m)^config\.set\(\{port: ([0-9]+)\}\);$", config_text)
                        != [str(port)] or re.search(
                            rf"(?m)^{re.escape(port_setter)}\s*\}}\s*\Z", config_text
                        ) is None):
                    raise ValueError(f"passing {name} Karma port configuration differs")
                header = re.match(
                    r"\s*module\.exports = function\(config\) \{\s*config\.set\(\{",
                    config_text,
                )
                block = (config_text[header.end():].partition("});") if header else
                         ("", "", ""))
                normalized_suffix = block[2].replace(
                    port_setter, "config.set({port: <PORT>});", 1
                )
                if (not block[1] or hashlib.sha256(normalized_suffix.encode()).hexdigest() !=
                        KARMA_EXECUTABLE_SUFFIX_SHA256[target]):
                    raise ValueError(f"passing {name} Karma executable configuration differs")
                try:
                    config = json.loads("{" + block[0] + "}") if block[1] else None
                except json.JSONDecodeError:
                    config = None
                package_root = root if name in MODULES else test_project(root, name)
                package = source.stem
                if target == "js":
                    test_input = (source if configuration == "production" else
                                  package_root / "build/js/packages" / package / "kotlin" /
                                  source.name)
                else:
                    test_input = (package_root / "build/wasm/packages" / package /
                                  "static/load.mjs")
                browser = "ChromeHeadless" if lane["runtime"] == "chromium" else "FirefoxHeadless"
                files = config.get("files") if isinstance(config, dict) else None
                if (not isinstance(files, list) or len(files) != 2
                        or not isinstance(files[0], str)):
                    raise ValueError(f"passing {name} Karma generated settings differ")
                if target == "js":
                    runner_input = (package_root / "build/js/node_modules/kotlin-web-helpers"
                                    / "dist/kotlin-test-karma-runner.js")
                else:
                    runner_input = Path(files[0])
                    try:
                        tooling_parts = runner_input.relative_to(
                            Path.home() / ".kotlin/kotlin-npm-tooling/yarn").parts
                    except ValueError:
                        tooling_parts = ()
                    if (len(tooling_parts) != 5
                            or re.fullmatch(r"[0-9a-f]{32}", tooling_parts[0]) is None
                            or tooling_parts[1:] != ("node_modules", "kotlin-web-helpers",
                                                    "dist", "kotlin-test-karma-runner.js")):
                        raise ValueError(f"passing {name} Karma generated settings differ")
                if (not runner_input.is_file()
                        or sha256(runner_input) != KARMA_HELPER_SHA256["runner"]):
                    raise ValueError(f"passing {name} Karma helper bytes differ")
                reporter_source = runner_input.with_name("karma-kotlin-reporter.js").resolve()
                reporter_attestation = lane_dir / name / "reporter-producer.json"
                reporter_retained = lane_dir / name / "karma-kotlin-reporter.js"
                if (module["karma_reporter_attestation"] != str(reporter_attestation)
                        or module["karma_reporter_retained"] != str(reporter_retained)
                        or module["karma_reporter_source"] != str(reporter_source)
                        or module["karma_reporter_source_sha256"] != KARMA_REPORTER_SHA256
                        or module["karma_reporter_sha256"] != KARMA_REPORTER_SHA256
                        or not started <= reporter_attestation.stat().st_mtime_ns <= finished
                        or json.loads(reporter_attestation.read_text()) != {
                            "path": str(reporter_source), "sha256": KARMA_REPORTER_SHA256,
                        } or not reporter_source.is_file()
                        or sha256(reporter_source) != KARMA_REPORTER_SHA256
                        or sha256(reporter_retained) != KARMA_REPORTER_SHA256):
                    raise ValueError(f"passing {name} Kotlin reporter producer differs")
                package_dir = package_root / f"build/{'js' if target == 'js' else 'wasm'}" / "packages" / package
                expected_config = {
                    "singleRun": True,
                    "autoWatch": False,
                    "basePath": str(package_dir),
                    "files": [str(runner_input), str(test_input)],
                    "frameworks": ["webpack-output", "mocha", "webpack"],
                    "client": {"args": []},
                    "browsers": [browser],
                    "customLaunchers": {},
                    "failOnFailingTestSuite": False,
                    "failOnEmptyTestSuite": False,
                    "reporters": ["karma-kotlin-reporter"],
                    "preprocessors": {str(runner_input): ["webpack", "sourcemap"],
                                      str(test_input): ["webpack", "sourcemap"]},
                    "proxies": {},
                    "webpackCopy": [],
                }
                if target == "wasmJs":
                    context_file = runner_input.parent / "static/context.html"
                    debug_file = runner_input.parent / "static/debug.html"
                    if (not context_file.is_file() or not debug_file.is_file()
                            or sha256(context_file) != KARMA_HELPER_SHA256["context"]
                            or sha256(debug_file) != KARMA_HELPER_SHA256["debug"]):
                        raise ValueError(f"passing {name} Karma helper bytes differ")
                    expected_config["customContextFile"] = str(context_file)
                    expected_config["customDebugFile"] = str(debug_file)
                try:
                    matching_config = (json.dumps(config, sort_keys=True, allow_nan=False) ==
                                       json.dumps(expected_config, sort_keys=True, allow_nan=False))
                except (TypeError, ValueError):
                    matching_config = False
                if not matching_config:
                    raise ValueError(f"passing {name} Karma generated settings differ")
                production_marker = f"qualification test input: {source}"
                markers = [line for line in Path(module["gradle_stdout"]).read_text().splitlines()
                           if line.startswith("qualification test input:")]
                if markers != ([production_marker] if configuration == "production" else []):
                    raise ValueError(f"passing {name} browser configuration input differs")
                marker = ("ChromeHeadless" if lane["runtime"] == "chromium" else
                          "Firefox") + lane["expected_runtime_version"].split(".")[0]
                observed = verify_reports(Path(module["raw_xml"][0]["path"]).parent,
                                          expected, f"{target}BrowserTest", marker,
                                          require_collision_diagnostics=name == "dyn4k-core")
                if {str(path) for path in observed["report_files"]} != {
                        item["path"] for item in module["raw_xml"]}:
                    raise ValueError(f"passing {name} XML inventory differs")
                for item in module["raw_xml"]:
                    if not started <= Path(item["path"]).stat().st_mtime_ns <= finished:
                        raise ValueError(f"passing {name} browser report is stale")
                launches = verify_browser_launches(
                    Path(module["browser_attestation"]), binary,
                    module.get("browser_token"), lane["runtime"])
                if launches != module.get("browser_processes"):
                    raise ValueError(f"passing {name} browser process record differs")
            compared = ("expected", "executed", "failures", "skipped", "cases")
            if target != "wasmWasi" and name == "dyn4k-core":
                compared += ("diagnostic_rows", "diagnostic_sha256")
            for field in compared:
                if module.get(field) != observed[field]:
                    raise ValueError(f"passing {name} raw case result differs: {field}")
    return lane


def runtime_version(binary: Path, target: str, runtime: str, expected: str, role: str) -> str:
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise ValueError(f"runtime binary unavailable: {binary}")
    observed = command([str(binary), "--version"], binary.parent)
    output = (observed.stdout + observed.stderr).strip()
    prefixes = {"chromium": "Google Chrome for Testing ",
                "firefox": "Mozilla Firefox ", "wasmtime": "wasmtime "}
    if runtime not in prefixes or observed.returncode or not output.startswith(prefixes[runtime]):
        raise ValueError(f"wrong runtime binary: {output}")
    version = output[len(prefixes[runtime]):].split()[0]
    if version != expected:
        raise ValueError(f"wrong runtime version: {output}")
    if runtime not in RUNTIME_VERSIONS or (target == "wasmWasi") != (runtime == "wasmtime"):
        raise ValueError(f"wrong target/runtime pair: {target}/{runtime}")
    if role not in ("minimum", "current"):
        raise ValueError(f"wrong version role: {role}")
    if expected != RUNTIME_VERSIONS[runtime][role]:
        raise ValueError(f"selected {role} version differs from pinned matrix: {expected}")
    return output


def verify_browser_launches(attestation: Path, binary: Path, token: str,
                            runtime: str) -> list[dict[str, object]]:
    if not attestation.is_file():
        raise ValueError(f"missing browser process attestation: {attestation}")
    records = [json.loads(line) for line in attestation.read_text().splitlines()]
    if not records:
        raise ValueError("zero browser process attestations")
    selected = binary.resolve()
    allowed = {selected}
    if runtime == "firefox":
        allowed.add(selected.with_name("firefox-bin"))
    for record in records:
        image = Path(str(record.get("process_executable", ""))).resolve()
        if (record.get("token") != token or record.get("runtime") != runtime
                or record.get("selected_binary") != str(selected)
                or record.get("selected_sha256") != sha256(selected)
                or image not in allowed or not isinstance(record.get("pid"), int)
                or record.get("process_sha256") != sha256(image)):
            raise ValueError("browser process image differs from selected executable")
    return records


def test_source(root: Path, module: str) -> Path:
    if module == "consumer":
        return root / CONSUMER / "src/commonTest/kotlin"
    return root / module / "src/commonTest/kotlin"


def test_project(root: Path, module: str) -> Path:
    return root / CONSUMER if module == "consumer" else root / module


def linked_file(project: Path, target: str, configuration: str, module: str) -> Path:
    kind = "Production" if configuration == "production" else "Development"
    suffix = "optimized" if target != "js" and configuration == "production" else "kotlin"
    basename = ("dyn4k-browser-wasi-consumer" if module == "consumer"
                else f"dyn4k-{module}") + "-test"
    extension = ".wasm" if target == "wasmWasi" else ".mjs" if target == "wasmJs" else ".js"
    return (project / "build/compileSync" / target / "test" /
            f"test{kind}Executable" / suffix / f"{basename}{extension}")


def capture_linked_executable(source: Path, retained: Path) -> str:
    if not source.is_file():
        raise ValueError(f"missing linked test executable: {source}")
    before = sha256(source)
    shutil.copy2(source, retained)
    copied = sha256(retained)
    if before != copied or sha256(source) != copied:
        raise ValueError("linked source and retained executable digest differ during capture")
    return copied


def verify_linked_source_digest(source: Path, retained: Path, source_digest: object,
                                retained_digest: object, target: str) -> None:
    if (not isinstance(source_digest, str) or source_digest != retained_digest
            or not retained.is_file() or sha256(retained) != retained_digest):
        raise ValueError("linked source and retained executable digest differ")
    if target != "wasmWasi" and (not source.is_file() or sha256(source) != source_digest):
        raise ValueError("linked source digest differs")


def verify_firefox_launcher_graph(root: Path) -> None:
    declaration = 'devNpm("karma-firefox-launcher", "^2.1.3")'
    for module in MODULES:
        if declaration not in (root / module / "build.gradle.kts").read_text():
            raise ValueError(f"Firefox launcher is not declared by {module}")
    lock = (root / "kotlin-js-store/yarn.lock").read_text()
    for selector in ("karma-firefox-launcher@^2.1.3:", "is-wsl@^2.2.0:",
                     "is-docker@^2.0.0:", "which@^3.0.0:"):
        if selector not in lock:
            raise ValueError(f"Firefox launcher lock graph lacks {selector}")


def gradle_test_task(module: str, target: str, configuration: str) -> str:
    prefix = ":" if module == "consumer" else f":{module}:"
    if target != "wasmWasi":
        return f"{prefix}{target}BrowserTest"
    kind = "Production" if configuration == "production" else "Development"
    optimize = "Optimize" if configuration == "production" else ""
    return f"{prefix}compileTest{kind}ExecutableKotlinWasmWasi{optimize}"


def gradle_command(root: Path, module: str, target: str,
                   configuration: str) -> list[str]:
    args = [str(root / "gradlew")]
    if module == "consumer":
        args += ["-p", str(test_project(root, module)),
                 f"-PqualificationRepository={root / 'build/staging-repository'}"]
    if target != "wasmWasi":
        args.append("kotlinUpgradeYarnLock" if target == "js" else
                    "kotlinWasmUpgradeYarnLock")
    args += [gradle_test_task(module, target, configuration), "--rerun-tasks",
             "--console=plain", "--no-daemon"]
    if configuration == "production" and target != "wasmWasi":
        args.append("-PqualificationProduction=true")
    return args


@contextmanager
def isolated_karma_port(project_root: Path, reporter_source: Path):
    config_dir = project_root / "karma.config.d"
    if config_dir.exists():
        raise ValueError(f"Karma configuration directory is already present: {config_dir}")
    reporter = reporter_source.read_bytes()
    if not reporter or len(reporter) > 256 * 1024:
        raise ValueError("browser reporter source is empty or oversized")
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    content = f"config.set({{port: {port}}});\n"
    config_dir.mkdir()
    reporter_file = config_dir / "qualification-browser-reporter.js"
    config_file = config_dir / "qualification-port.js"
    try:
        reporter_file.write_bytes(reporter)
        config_file.write_text(content)
        yield port
    finally:
        if config_file.is_file() and config_file.read_text() == content:
            config_file.unlink()
        if reporter_file.is_file() and reporter_file.read_bytes() == reporter:
            reporter_file.unlink()
        if config_dir.is_dir() and not any(config_dir.iterdir()):
            config_dir.rmdir()


def run_lane(root: Path, sha: str, receipt: Path, output: Path, target: str,
             runtime: str, role: str, configuration: str, binary: Path,
             expected_version: str) -> int:
    if output.exists() and any(output.iterdir()):
        print(f"lane output already contains evidence: {output}", file=sys.stderr)
        return 1
    output.mkdir(parents=True, exist_ok=True)
    lane: dict[str, object] = {"candidate_sha": sha, "target": target,
                               "runtime": runtime, "version_role": role,
                               "configuration": configuration, "status": "FAILED"}
    try:
        candidate_identity(root, sha)
        prepare_consumer_lock(root, sha)
        candidate_identity(root, sha)
        lane["artifact_hashes"] = verified_stage(root, sha, receipt)
        if target == "js" and runtime == "firefox":
            verify_firefox_launcher_graph(root)
        lane.update(candidate_root=str(root), staging_receipt=str(receipt),
                    staging_receipt_sha256=sha256(receipt),
                    manifest_sha256=sha256(root / full_corpus.MANIFEST_PATH),
                    original_map_sha256=sha256(root / full_corpus.MAP_PATH),
                    reviewed_pairs_sha256=sha256(root / full_corpus.PAIR_PATH),
                    source_tree_sha256=json.loads((root / full_corpus.MANIFEST_PATH).read_text())[
                        "source_tree_sha256"])
        lane["runtime_version"] = runtime_version(binary, target, runtime, expected_version, role)
        lane["runtime_binary"] = str(binary.resolve())
        lane["runtime_sha256"] = sha256(binary)
        lane["expected_runtime_version"] = expected_version
        if target not in TARGETS or configuration not in ("development", "production"):
            raise ValueError("unknown target or configuration")
        results: dict[str, object] = {}
        lane["modules"] = results
        for module in (*MODULES, "consumer"):
            project = test_project(root, module)
            expected = (common_corpus_cases(root, sha, module) if module in MODULES else
                        source_cases(test_source(root, module)))
            if module == "consumer":
                lane["consumer_physics_source_sha256"] = verify_consumer_physics_contract(
                    root / PHYSICS_CONSUMER_SOURCE
                )
            module_output = output / module
            module_output.mkdir(exist_ok=True)
            env = dict(os.environ, JAVA_HOME=os.environ.get("JAVA_HOME", "/tmp/dyn4k-tools/jdk21"),
                       YARN_OFFLINE="true")
            attestation = module_output / "browser-launches.jsonl"
            reporter_attestation = module_output / "reporter-producer.json"
            token = secrets.token_hex(16)
            launcher = root / "tools/qualification/browser_wasi/browser_launcher.py"
            if runtime == "chromium":
                env.update(DYN4K_BROWSER="chromium", CHROME_BIN=str(launcher))
            elif runtime == "firefox":
                env.update(DYN4K_BROWSER="firefox", FIREFOX_BIN=str(launcher))
            if runtime != "wasmtime":
                env.update(DYN4K_BROWSER_SELECTED_BINARY=str(binary),
                           DYN4K_BROWSER_ATTESTATION=str(attestation),
                           DYN4K_BROWSER_TOKEN=token, DYN4K_BROWSER_RUNTIME=runtime,
                           DYN4K_BROWSER_REPORTER_ATTESTATION=str(reporter_attestation))
            gradle = gradle_command(root, module, target, configuration)
            report_dir = project / "build/test-results" / f"{target}BrowserTest"
            if target != "wasmWasi" and report_dir.exists():
                shutil.rmtree(report_dir)
            started_ns = time.time_ns()
            if target == "wasmWasi":
                built = command(gradle, root, env)
                karma_port = None
            else:
                with isolated_karma_port(
                    project, root / "tools/qualification/browser_wasi/browser-karma-reporter.js"
                ) as karma_port:
                    built = command(gradle, root, env)
            finished_ns = time.time_ns()
            console = module_output / "gradle-console.log"
            console.write_text(built.stdout + built.stderr)
            stdout = module_output / "gradle-stdout.log"
            stderr = module_output / "gradle-stderr.log"
            stdout.write_text(built.stdout)
            stderr.write_text(built.stderr)
            evidence: dict[str, object] = {
                "status": "FAILED", "gradle_command": gradle,
                "gradle_exit_code": built.returncode, "gradle_console": str(console),
                "gradle_console_sha256": sha256(console),
                "gradle_stdout": str(stdout), "gradle_stdout_sha256": sha256(stdout),
                "gradle_stderr": str(stderr), "gradle_stderr_sha256": sha256(stderr),
                "started_ns": started_ns, "finished_ns": finished_ns,
                "candidate_sha": sha,
                "target": target, "runtime": runtime, "configuration": configuration,
                "staging_receipt": str(receipt), "runtime_sha256": lane["runtime_sha256"],
                "browser_token": token if runtime != "wasmtime" else None,
                "karma_port": karma_port,
            }
            results[module] = evidence
            try:
                if built.returncode:
                    raise ValueError(f"{module} Gradle task failed: {console}")
                linked = linked_file(project, target, configuration, module)
                if not linked.is_file():
                    raise ValueError(f"missing linked test executable: {linked}")
                if target != "wasmWasi":
                    package = linked.stem
                    package_root = root if module in MODULES else project
                    karma_generated = (package_root / "build" /
                                       ("js" if target == "js" else "wasm") /
                                       "packages" / package / "karma.conf.js")
                    if (not karma_generated.is_file() or
                            f"config.set({{port: {karma_port}}});" not in
                            karma_generated.read_text()):
                        raise ValueError("browser test did not load isolated Karma port")
                    frozen_karma = module_output / "karma.conf.js"
                    shutil.copy2(karma_generated, frozen_karma)
                    evidence.update(karma_config=str(frozen_karma),
                                    karma_config_sha256=sha256(frozen_karma))
                    if (not reporter_attestation.is_file() or not
                            started_ns <= reporter_attestation.stat().st_mtime_ns <= finished_ns):
                        raise ValueError("browser Kotlin reporter producer attestation is missing")
                    attested = json.loads(reporter_attestation.read_text())
                    reporter_source = Path(str(attested.get("path", ""))).resolve()
                    if (attested != {"path": str(reporter_source),
                                     "sha256": KARMA_REPORTER_SHA256}
                            or not reporter_source.is_file()
                            or sha256(reporter_source) != KARMA_REPORTER_SHA256):
                        raise ValueError("browser Kotlin reporter producer bytes differ")
                    retained_reporter = module_output / "karma-kotlin-reporter.js"
                    shutil.copy2(reporter_source, retained_reporter)
                    if (sha256(retained_reporter) != KARMA_REPORTER_SHA256
                            or sha256(reporter_source) != KARMA_REPORTER_SHA256):
                        raise ValueError("browser Kotlin reporter producer changed during capture")
                    evidence.update(
                        karma_reporter_attestation=str(reporter_attestation),
                        karma_reporter_attestation_sha256=sha256(reporter_attestation),
                        karma_reporter_source=str(reporter_source),
                        karma_reporter_source_sha256=KARMA_REPORTER_SHA256,
                        karma_reporter_retained=str(retained_reporter),
                        karma_reporter_sha256=sha256(retained_reporter),
                    )
                    marker = f"qualification test input: {linked}"
                    markers = [line for line in built.stdout.splitlines()
                               if line.startswith("qualification test input:")]
                    if markers != ([marker] if configuration == "production" else []):
                        raise ValueError(f"browser configuration did not select input: {linked}")
                frozen_linked = module_output / f"linked-executable{linked.suffix}"
                linked_digest = capture_linked_executable(linked, frozen_linked)
                evidence.update(linked_source=str(linked),
                                linked_source_sha256=linked_digest,
                                linked_executable=str(frozen_linked),
                                linked_sha256=linked_digest)
                if target == "wasmWasi":
                    invocation = [str(binary), "run", "-W", "gc=y", "-W", "exceptions=y",
                                  "-W", "function-references=y", "--invoke", "startUnitTests",
                                  str(frozen_linked)]
                    observed = command(invocation, root)
                    raw = module_output / "wasmtime-console.log"
                    raw.write_text(observed.stdout + observed.stderr)
                    raw_stdout = module_output / "wasmtime-stdout.log"
                    raw_stderr = module_output / "wasmtime-stderr.log"
                    raw_stdout.write_text(observed.stdout)
                    raw_stderr.write_text(observed.stderr)
                    evidence.update(command=invocation, exit_code=observed.returncode,
                                    raw_console=str(raw), raw_console_sha256=sha256(raw),
                                    raw_stdout=str(raw_stdout), raw_stdout_sha256=sha256(raw_stdout),
                                    raw_stderr=str(raw_stderr), raw_stderr_sha256=sha256(raw_stderr))
                    if observed.returncode:
                        raise ValueError(f"{module} Wasmtime tests failed: {raw}")
                    evidence.update(verify_wasmtime_output(observed.stdout, expected))
                else:
                    xml_dir = module_output / "xml"
                    xml_dir.mkdir(exist_ok=True)
                    copied = []
                    for report in sorted(report_dir.glob("TEST-*.xml")):
                        if not started_ns <= report.stat().st_mtime_ns <= finished_ns:
                            raise ValueError(f"stale browser report: {report}")
                        copy = xml_dir / report.name
                        shutil.copy2(report, copy)
                        copied.append({"path": str(copy), "sha256": sha256(copy)})
                    evidence["raw_xml"] = copied
                    if attestation.is_file():
                        evidence.update(browser_attestation=str(attestation),
                                        browser_attestation_sha256=sha256(attestation))
                    marker = ("ChromeHeadless" if runtime == "chromium" else "Firefox") + expected_version.split(".")[0]
                    evidence.update(verify_reports(
                        xml_dir, expected, f"{target}BrowserTest", marker,
                        require_collision_diagnostics=module == "dyn4k-core",
                    ))
                    launches = verify_browser_launches(attestation, binary, token, runtime)
                    for launch in launches:
                        runtime_version(Path(str(launch["process_executable"])), target, runtime,
                                        expected_version, role)
                    evidence["browser_processes"] = launches
                if sha256(binary) != lane["runtime_sha256"]:
                    raise ValueError(f"runtime binary changed during {module} execution")
                runtime_version(binary, target, runtime, expected_version, role)
                evidence["status"] = "PASSED"
            finally:
                result_path = module_output / "result.json"
                write_json(result_path, evidence)
                evidence["result_json"] = str(result_path)
                evidence["result_json_sha256"] = sha256(result_path)
        candidate_identity(root, sha)
        lane["status"] = "PASSED"
    except (OSError, ValueError, json.JSONDecodeError) as error:
        lane["reason"] = str(error)
    write_json(output / "lane.json", sealed_lane(lane))
    try:
        audit_lane_receipt(output / "lane.json")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        lane["status"] = "FAILED"
        lane["reason"] = f"lane receipt audit failed: {error}"
        write_json(output / "lane.json", sealed_lane(lane))
    return 0 if lane["status"] == "PASSED" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("candidate", "stage", "run", "audit"))
    parser.add_argument("--root", type=Path)
    parser.add_argument("--candidate-sha")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--target", choices=TARGETS)
    parser.add_argument("--runtime", choices=("chromium", "firefox", "wasmtime"))
    parser.add_argument("--version-role", choices=("minimum", "current"))
    parser.add_argument("--configuration", choices=("development", "production"))
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--expected-version")
    arguments = parser.parse_args()
    if arguments.action == "audit":
        if arguments.receipt is None:
            parser.error("audit requires --receipt pointing to lane.json")
        try:
            audit_lane_receipt(arguments.receipt.resolve())
        except (OSError, ValueError, json.JSONDecodeError) as error:
            print(error, file=sys.stderr)
            return 1
        return 0
    if arguments.action == "candidate":
        if arguments.root is None or arguments.candidate_sha is None:
            parser.error("candidate requires root and candidate-sha")
        try:
            root = arguments.root.resolve()
            candidate_identity(root, arguments.candidate_sha)
            manifest = json.loads((root / full_corpus.MANIFEST_PATH).read_bytes())
        except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
            print(error, file=sys.stderr)
            return 1
        print(json.dumps({"candidate_sha": arguments.candidate_sha,
                          "manifest_sha256": sha256(root / full_corpus.MANIFEST_PATH),
                          "source_tree_sha256": manifest["source_tree_sha256"],
                          "suite_methods": manifest["counts"]["total_methods"],
                          "status": "VERIFIED"}, sort_keys=True))
        return 0
    if any(value is None for value in (arguments.root, arguments.candidate_sha, arguments.output)):
        parser.error("stage and run require root, candidate-sha, and output")
    if arguments.action == "stage":
        return stage(arguments.root.resolve(), arguments.candidate_sha, arguments.output.resolve())
    required = (arguments.receipt, arguments.target, arguments.runtime, arguments.version_role,
                arguments.configuration, arguments.binary, arguments.expected_version)
    if any(value is None for value in required):
        parser.error("run requires receipt, target, runtime, version-role, configuration, binary, and expected-version")
    return run_lane(arguments.root.resolve(), arguments.candidate_sha, arguments.receipt.resolve(),
                    arguments.output.resolve(), arguments.target, arguments.runtime,
                    arguments.version_role, arguments.configuration, arguments.binary.resolve(),
                    arguments.expected_version)


if __name__ == "__main__":
    sys.exit(main())
