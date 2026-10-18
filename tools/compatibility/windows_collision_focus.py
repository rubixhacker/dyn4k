import argparse
import math
import re
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


TARGET = "mingwX64Test"
SUITES = {
    "org.dyn4j.collision.narrowphase.WindowsCollisionIntermediateDiagnosticTest":
        "TEST-mingwX64Test.org.dyn4j.collision.narrowphase.WindowsCollisionIntermediateDiagnosticTest.xml",
    "org.dyn4j.coverage.collision.shapes.a.CapsuleSliceTest":
        "TEST-mingwX64Test.org.dyn4j.coverage.collision.shapes.a.CapsuleSliceTest.xml",
    "org.dyn4j.coverage.collision.shapes.a.CirclePolygonTest":
        "TEST-mingwX64Test.org.dyn4j.coverage.collision.shapes.a.CirclePolygonTest.xml",
    "org.dyn4j.coverage.collision.shapes.a.CircleSegmentTest":
        "TEST-mingwX64Test.org.dyn4j.coverage.collision.shapes.a.CircleSegmentTest.xml",
    "org.dyn4j.coverage.collision.shapes.a.CircleSliceTest":
        "TEST-mingwX64Test.org.dyn4j.coverage.collision.shapes.a.CircleSliceTest.xml",
    "org.dyn4j.coverage.collision.shapes.a.PolygonCapsuleTest":
        "TEST-mingwX64Test.org.dyn4j.coverage.collision.shapes.a.PolygonCapsuleTest.xml",
    "org.dyn4j.coverage.collision.shapes.a.PolygonPolygonTest":
        "TEST-mingwX64Test.org.dyn4j.coverage.collision.shapes.a.PolygonPolygonTest.xml",
}
ORIGINAL_CASES = {
    suite: {
        f"{method}[mingwX64]"
        for method in ("detectSat", "detectGjk", "gjkDistance", "getClipManifold")
    }
    for suite in (
        "org.dyn4j.coverage.collision.shapes.a.CapsuleSliceTest",
        "org.dyn4j.coverage.collision.shapes.a.CirclePolygonTest",
        "org.dyn4j.coverage.collision.shapes.a.CircleSegmentTest",
        "org.dyn4j.coverage.collision.shapes.a.CircleSliceTest",
        "org.dyn4j.coverage.collision.shapes.a.PolygonCapsuleTest",
        "org.dyn4j.coverage.collision.shapes.a.PolygonPolygonTest",
    )
}
DIAGNOSTIC_CASES = {
    "capsuleSlice[mingwX64]",
    "circlePolygon[mingwX64]",
    "circleSegment[mingwX64]",
    "circleSlice[mingwX64]",
    "polygonCapsule[mingwX64]",
    "polygonPolygon[mingwX64]",
}
IDENTITY_FIELDS = ("fixture", "method", "phase", "order", "step", "algorithm")
FIXTURE_SHAPES = {
    "CapsuleSlice": ("Capsule", "Slice"),
    "CirclePolygon": ("Circle", "Polygon"),
    "CircleSegment": ("Circle", "Segment"),
    "CircleSlice": ("Circle", "Slice"),
    "PolygonCapsule": ("Polygon", "Capsule"),
    "PolygonPolygon": ("Polygon", "Polygon"),
}
EPA_ITERATION_SCHEMA = (
    "index:edgeId:edgeA:edgeB:normalBefore:normalAfter:distance:support:"
    "projection:delta:stop:equalDistanceEdgeIds:mirrorMatches"
)
BASE_FIELDS = {
    "provider", *IDENTITY_FIELDS,
    "a.transform", "b.transform", "a.center.local", "b.center.local",
    "a.center.world", "b.center.world", "hit", "booleanHit",
    "penetration.normal", "penetration.depth", "selection", "clipped",
    "manifold.normal", "manifold.count", "a.shape.local", "b.shape.local",
    "a.polygon.edgeArithmetic", "b.polygon.edgeArithmetic", "a.foci.world",
    "b.foci.world", "a.axes.withB", "b.axes.withA",
    "gjk.initial.centerDirection", "gjk.initial.effectiveDirection",
    "clip.probe.feature.a", "clip.probe.feature.b",
    "epa.replay.identity", "epa.replay.simplex", "epa.replay.iteration",
    "epa.replay.stop", "epa.replay.epsilon", "epa.replay.maxIterations",
    "epa.iteration.schema", "epa.iteration.records", "epa.queue.reconstructedMatches",
    "epa.edge.a", "epa.edge.b", "epa.edge.normal", "epa.edge.distance",
    "epa.terminal.support", "epa.terminal.projection", "epa.terminal.delta",
    "epa.replay.normalMatchesResult", "epa.replay.depthMatchesResult",
}
SUPPORT_FIELDS = {
    f"support.{index}.{suffix}"
    for index in range(6)
    for suffix in ("direction", "a", "b.negated", "minkowski")
}
SAT_FIELDS = {
    "sat.replay.hit", "sat.replay.matchesResult", "sat.candidates",
    "sat.winner.source", "sat.winner.index",
}
SAT_HIT_FIELDS = {
    "sat.winner.preOrientation", "sat.winner.centerDot",
    "sat.winner.orientationFlip", "sat.winner.finalAxis", "sat.winner.depth",
}
def _integer(value, label, minimum=None):
    if not re.fullmatch(r"-?[0-9]+", value):
        raise ValueError(f"{label} is not an integer: {value!r}")
    parsed = int(value)
    if minimum is not None and parsed < minimum:
        raise ValueError(f"{label} is below {minimum}: {parsed}")
    return parsed


def _number(value, label):
    decimal, separator, raw_bits = value.rpartition("@")
    decimal_pattern = r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
    if (not separator or not re.fullmatch(decimal_pattern, decimal)
            or not re.fullmatch(r"-?[0-9]+", raw_bits)):
        raise ValueError(f"{label} is not a decimal@bits scalar: {value!r}")
    try:
        parsed = float(decimal)
        bits = int(raw_bits)
    except ValueError as error:
        raise ValueError(f"{label} has an invalid scalar encoding: {value!r}") from error
    if not math.isfinite(parsed) or not -(1 << 63) <= bits < (1 << 63):
        raise ValueError(f"{label} has a non-finite or out-of-range scalar: {value!r}")
    unsigned_bits = struct.unpack(">Q", struct.pack(">d", parsed))[0]
    expected_bits = unsigned_bits - (1 << 64) if unsigned_bits >= (1 << 63) else unsigned_bits
    if bits != expected_bits:
        raise ValueError(f"{label} decimal and raw bits disagree: {value!r}")
    return parsed


def _vector(value, label):
    parts = value.split(",")
    if len(parts) != 2:
        raise ValueError(f"{label} is not a two-component vector: {value!r}")
    return tuple(_number(part, label) for part in parts)


def _number_list(value, label, delimiter, allow_empty=False):
    if value == "" and allow_empty:
        return []
    if not value:
        raise ValueError(f"{label} is empty")
    return [_number(part, label) for part in value.split(delimiter)]


def _vector_list(value, label, allow_null=False, allow_empty=False):
    if value == "null" and allow_null:
        return None
    if value == "" and allow_empty:
        return []
    if not value:
        raise ValueError(f"{label} is empty")
    return [_vector(part, label) for part in value.split(";")]


def _boolean(value, label):
    if value not in {"true", "false"}:
        raise ValueError(f"{label} is not a boolean: {value!r}")
    return value == "true"


def _feature(value, label):
    parts = value.split(":")
    kind = parts[0]
    if kind == "point" and len(parts) == 3:
        _integer(parts[1], f"{label} index")
        _vector(parts[2], label)
    elif kind == "edge" and len(parts) == 9:
        for index in (1, 2, 4, 6):
            _integer(parts[index], f"{label} index")
        for index in (3, 5, 7, 8):
            _vector(parts[index], label)
    elif kind == "unknown" and len(parts) == 2:
        _integer(parts[1], f"{label} index")
    else:
        raise ValueError(f"{label} has an invalid feature encoding: {value!r}")


def _shape(value, label):
    fields = {}
    for item in value.split("|"):
        if "=" not in item:
            raise ValueError(f"{label} has a malformed component: {item!r}")
        key, component = item.split("=", 1)
        if key in fields:
            raise ValueError(f"{label} repeats component {key}")
        fields[key] = component
    kind = fields.get("kind")
    extras = {
        "Circle": {"circle.radius"},
        "Capsule": {"capsule.length", "capsule.capRadius", "capsule.localFoci", "capsule.localAxis"},
        "Slice": {"slice.radius", "slice.theta", "slice.circleCenter", "slice.rotation",
                  "slice.upperEdge", "slice.lowerEdge"},
        "Segment": {"segment.length", "vertices", "normals"},
        "Polygon": {"vertices", "normals"},
    }
    if kind not in extras:
        raise ValueError(f"{label} has an unknown shape kind: {kind!r}")
    expected = {"kind", "center", "radius"} | extras[kind]
    if set(fields) != expected:
        raise ValueError(f"{label} component set mismatch; missing={sorted(expected-set(fields))}, unexpected={sorted(set(fields)-expected)}")
    _vector(fields["center"], f"{label}.center")
    _number(fields["radius"], f"{label}.radius")
    if kind == "Circle":
        _number(fields["circle.radius"], f"{label}.circle.radius")
    elif kind == "Capsule":
        _number(fields["capsule.length"], f"{label}.capsule.length")
        _number(fields["capsule.capRadius"], f"{label}.capsule.capRadius")
        _vector_list(fields["capsule.localFoci"], f"{label}.capsule.localFoci")
        _vector(fields["capsule.localAxis"], f"{label}.capsule.localAxis")
    elif kind == "Slice":
        _number(fields["slice.radius"], f"{label}.slice.radius")
        _number(fields["slice.theta"], f"{label}.slice.theta")
        _vector(fields["slice.circleCenter"], f"{label}.slice.circleCenter")
        _vector(fields["slice.rotation"], f"{label}.slice.rotation")
        _feature(fields["slice.upperEdge"], f"{label}.slice.upperEdge")
        _feature(fields["slice.lowerEdge"], f"{label}.slice.lowerEdge")
    elif kind == "Segment":
        _number(fields["segment.length"], f"{label}.segment.length")
        vertices = _vector_list(fields["vertices"], f"{label}.vertices")
        normals = _vector_list(fields["normals"], f"{label}.normals")
        if len(vertices) != 2 or len(normals) != 2:
            raise ValueError(f"{label} segment vertices/normals do not match source geometry")
    else:
        vertices = _vector_list(fields["vertices"], f"{label}.vertices")
        normals = _vector_list(fields["normals"], f"{label}.normals")
        if not vertices or len(vertices) != len(normals):
            raise ValueError(f"{label} polygon vertices/normals do not pair")
    return kind, len(vertices) if kind == "Polygon" else None


def _polygon_edges(value, label, polygon, expected_count):
    if not polygon:
        if value != "na":
            raise ValueError(f"{label} must be na for a non-polygon")
        return
    if value == "na" or not value:
        raise ValueError(f"{label} must contain every polygon edge")
    edges = value.split(";")
    if len(edges) != expected_count:
        raise ValueError(f"{label} edge count mismatch: {len(edges)} != {expected_count}")
    for index, edge in enumerate(edges):
        parts = edge.split(":")
        if len(parts) != 12 or _integer(parts[0], f"{label} index", 0) != index:
            raise ValueError(f"{label} edge {index} has an invalid ordered schema")
        for scalar_index in (1, 2, 3, 4, 5, 6, 7, 9):
            _number(parts[scalar_index], f"{label} edge {index}")
        for vector_index in (8, 10, 11):
            _vector(parts[vector_index], f"{label} edge {index}")


def _epa_records(fields):
    iteration = _integer(fields["epa.replay.iteration"], "epa.replay.iteration", 0)
    maximum = _integer(fields["epa.replay.maxIterations"], "epa.replay.maxIterations", 1)
    if fields["epa.iteration.schema"] != EPA_ITERATION_SCHEMA:
        raise ValueError("EPA iteration schema does not match the source record format")
    if fields["epa.replay.identity"] != "unobserved":
        raise ValueError("EPA replay identity must use the source's unobserved marker")
    _number(fields["epa.replay.epsilon"], "epa.replay.epsilon")
    _boolean(fields["epa.queue.reconstructedMatches"], "epa.queue.reconstructedMatches")
    if iteration == 0:
        if fields["epa.replay.stop"] != "notRun" or fields["epa.iteration.records"] != "" or fields["epa.replay.simplex"] != "":
            raise ValueError("empty EPA records/simplex are only valid for an unrun replay")
        for key in ("epa.edge.a", "epa.edge.b", "epa.edge.normal", "epa.edge.distance",
                    "epa.terminal.support", "epa.terminal.projection", "epa.terminal.delta",
                    "epa.replay.normalMatchesResult", "epa.replay.depthMatchesResult"):
            if fields[key] != "na":
                raise ValueError(f"{key} must be na when EPA did not run")
        return 0
    if iteration > maximum or fields["epa.replay.stop"] not in {"epsilon", "iterationLimit"}:
        raise ValueError("EPA replay iteration/stop state is invalid")
    if fields["epa.replay.stop"] == "iterationLimit" and iteration != maximum:
        raise ValueError("EPA iterationLimit stop does not match maximum iterations")
    _vector_list(fields["epa.replay.simplex"], "epa.replay.simplex")
    _boolean(fields["epa.replay.normalMatchesResult"], "epa.replay.normalMatchesResult")
    _boolean(fields["epa.replay.depthMatchesResult"], "epa.replay.depthMatchesResult")
    _vector(fields["epa.edge.a"], "epa.edge.a")
    _vector(fields["epa.edge.b"], "epa.edge.b")
    _vector(fields["epa.edge.normal"], "epa.edge.normal")
    _number(fields["epa.edge.distance"], "epa.edge.distance")
    _vector(fields["epa.terminal.support"], "epa.terminal.support")
    _number(fields["epa.terminal.projection"], "epa.terminal.projection")
    _number(fields["epa.terminal.delta"], "epa.terminal.delta")
    rows = fields["epa.iteration.records"].split(";")
    if len(rows) != iteration:
        raise ValueError(f"EPA record count {len(rows)} does not match iteration {iteration}")
    for expected_index, row in enumerate(rows, 1):
        parts = row.split(":")
        if len(parts) != 13 or _integer(parts[0], "EPA record index", 1) != expected_index:
            raise ValueError("EPA iteration records are malformed or out of order")
        mirror_matches = _boolean(parts[12], "EPA record mirrorMatches")
        if mirror_matches:
            _integer(parts[1], "EPA edge id", 0)
            if parts[11]:
                for edge_id in parts[11].split(","):
                    _integer(edge_id, "EPA equal-distance edge id", 0)
        elif parts[1] != "na" or parts[11] != "na":
            raise ValueError("EPA mirror mismatch must use na edge IDs")
        for vector_index in (2, 3, 4, 5, 7):
            _vector(parts[vector_index], f"EPA record {expected_index}")
        for scalar_index in (6, 8, 9):
            _number(parts[scalar_index], f"EPA record {expected_index}")
        if parts[10] not in {"continue", "epsilon", "iterationLimit"}:
            raise ValueError("EPA record has an unknown stop marker")
        if expected_index < iteration and parts[10] != "continue":
            raise ValueError("EPA stop marker appears before the final record")
        if expected_index == iteration and parts[10] != fields["epa.replay.stop"]:
            raise ValueError("EPA final record stop does not match replay stop")
    return iteration


def _sat_candidates(value, replay_hit):
    if not value:
        raise ValueError("SAT candidates are empty")
    candidates = value.split(";")
    for candidate in candidates:
        parts = candidate.split(":")
        if len(parts) < 4:
            raise ValueError("SAT candidate is malformed")
        _integer(parts[0], "SAT candidate source", 0)
        if parts[0] not in {"0", "1"}:
            raise ValueError("SAT candidate source is outside the two input shapes")
        _integer(parts[1], "SAT candidate index", 0)
        if parts[2] == "zero" and len(parts) == 4:
            _vector(parts[3], "SAT zero-axis candidate")
        elif parts[2] == "separated" and len(parts) == 6:
            _vector(parts[3], "SAT separated axis")
            for interval in parts[4:6]:
                pair = interval.split(",")
                if len(pair) != 2:
                    raise ValueError("SAT interval is malformed")
                for scalar in pair:
                    _number(scalar, "SAT interval")
        elif len(parts) == 13:
            _vector(parts[2], "SAT overlap axis")
            for interval in parts[3:5]:
                pair = interval.split(",")
                if len(pair) != 2:
                    raise ValueError("SAT overlap interval is malformed")
                for scalar in pair:
                    _number(scalar, "SAT overlap interval")
            _number(parts[5], "SAT raw overlap")
            contained = _boolean(parts[6], "SAT contained")
            _boolean(parts[7], "SAT containmentFlip")
            if contained:
                _number(parts[8], "SAT maxDifference")
                _number(parts[9], "SAT minDifference")
            elif parts[8:10] != ["na", "na"]:
                raise ValueError("SAT differences must be na when intervals are not contained")
            _number(parts[10], "SAT adjusted overlap")
            _vector(parts[11], "SAT adjusted axis")
            _boolean(parts[12], "SAT selected")
        else:
            raise ValueError("SAT candidate does not match a source branch schema")
    if not replay_hit and candidates[-1].split(":")[2] != "separated":
        raise ValueError("SAT miss must end at its first separating candidate")
    if replay_hit and any(candidate.split(":")[2] == "separated" for candidate in candidates):
        raise ValueError("SAT hit cannot contain a separated candidate")


def _parse_record(record, provider):
    parts = record.split("\t")
    if len(parts) < 3 or parts[:2] != ["DYN4K_COLLISION_DIAGNOSTIC", "v2"]:
        raise ValueError("record is not a v2 collision diagnostic")
    fields = {}
    for part in parts[2:]:
        if "=" not in part:
            raise ValueError(f"record field is malformed: {part!r}")
        key, value = part.split("=", 1)
        if not key or key in fields:
            raise ValueError(f"record repeats or omits a field key: {key!r}")
        fields[key] = value
    if fields.get("provider") != provider:
        raise ValueError(f"unexpected record provider: {fields.get('provider')}")
    if set(IDENTITY_FIELDS) - set(fields):
        raise ValueError(f"record is missing identity fields: {sorted(set(IDENTITY_FIELDS)-set(fields))}")
    fixture, method, phase, order, step_text, algorithm = (fields[key] for key in IDENTITY_FIELDS)
    if fixture not in FIXTURE_SHAPES or phase not in {"center", "shifted"} or order not in {"forward", "reverse"}:
        raise ValueError("record identity contains an unknown fixture, phase, or order")
    step = _integer(step_text, "step", 0)
    if method not in {"detectSat", "detectGjk", "getClipManifold"}:
        raise ValueError(f"unknown diagnostic method: {method}")
    if (method == "detectSat" and algorithm != "sat") or (method == "detectGjk" and algorithm != "gjk") or algorithm not in {"gjk", "sat"}:
        raise ValueError(f"method/algorithm combination is invalid: {method}/{algorithm}")
    if method.startswith("detect"):
        expected_detector = "gjk" if fixture not in {"PolygonCapsule", "PolygonPolygon"} else "sat"
        if algorithm != expected_detector or step > 3:
            raise ValueError("detection row does not match its source fixture schedule")
    elif step < 4 or step > 11:
        raise ValueError("clipping row is outside its source fixture schedule")

    expected = BASE_FIELDS | SUPPORT_FIELDS
    if algorithm == "sat":
        expected |= SAT_FIELDS
        if fields.get("sat.replay.hit") == "true":
            expected |= SAT_HIT_FIELDS
    if method == "getClipManifold":
        count = _integer(fields.get("manifold.count", ""), "manifold.count", 0)
        if count > 2:
            raise ValueError(f"manifold count exceeds source limit: {count}")
        for index in range(count):
            expected |= {f"manifold.point.{index}.{suffix}" for suffix in ("position", "depth", "id")}
    if set(fields) != expected:
        missing = sorted(expected - set(fields))
        unexpected = sorted(set(fields) - expected)
        raise ValueError(f"diagnostic field schema mismatch; missing={missing}, unexpected={unexpected}")

    expected_shapes = FIXTURE_SHAPES[fixture]
    if order == "reverse":
        expected_shapes = expected_shapes[::-1]
    parsed_shapes = (_shape(fields["a.shape.local"], "a.shape.local"),
                     _shape(fields["b.shape.local"], "b.shape.local"))
    if (parsed_shapes[0][0], parsed_shapes[1][0]) != expected_shapes:
        raise ValueError(f"shape representations do not match fixture {fixture}")
    _polygon_edges(fields["a.polygon.edgeArithmetic"], "a.polygon.edgeArithmetic",
                   parsed_shapes[0][0] == "Polygon", parsed_shapes[0][1])
    _polygon_edges(fields["b.polygon.edgeArithmetic"], "b.polygon.edgeArithmetic",
                   parsed_shapes[1][0] == "Polygon", parsed_shapes[1][1])
    for key in ("a.transform", "b.transform"):
        if len(_number_list(fields[key], key, ",")) != 6:
            raise ValueError(f"{key} must contain six transform scalars")
    for key in ("a.center.local", "b.center.local", "a.center.world", "b.center.world",
                "penetration.normal", "gjk.initial.centerDirection", "gjk.initial.effectiveDirection"):
        _vector(fields[key], key)
    _number(fields["penetration.depth"], "penetration.depth")
    _boolean(fields["hit"], "hit")
    for key in ("a.foci.world", "b.foci.world", "a.axes.withB", "b.axes.withA"):
        _vector_list(fields[key], key, allow_null=True)
    hit = _boolean(fields["hit"], "hit")
    if method == "getClipManifold":
        if fields["booleanHit"] != "na":
            raise ValueError("booleanHit must be na for getClipManifold rows")
        _boolean(fields["clipped"], "clipped")
        _vector(fields["manifold.normal"], "manifold.normal")
        count = int(fields["manifold.count"])
        for index in range(count):
            _vector(fields[f"manifold.point.{index}.position"], f"manifold.point.{index}.position")
            _number(fields[f"manifold.point.{index}.depth"], f"manifold.point.{index}.depth")
            point_id = fields[f"manifold.point.{index}.id"]
            if point_id != "distance":
                match = re.fullmatch(r"indexed:(-?[0-9]+):(-?[0-9]+):(-?[0-9]+):(true|false)", point_id)
                if not match:
                    raise ValueError(f"invalid manifold point id: {point_id!r}")
    else:
        _boolean(fields["booleanHit"], "booleanHit")
        if fields["clipped"] != "na" or fields["manifold.normal"] != "na" or fields["manifold.count"] != "na":
            raise ValueError("manifold values must be na for detection rows")
    for index in range(6):
        for suffix in ("direction", "a", "b.negated", "minkowski"):
            key = f"support.{index}.{suffix}"
            _vector(fields[key], key)
    for key in ("clip.probe.feature.a", "clip.probe.feature.b"):
        if hit:
            _feature(fields[key], key)
        elif fields[key] != "na":
            raise ValueError(f"{key} must be na when the production detector misses")

    iterations = _epa_records(fields)
    expected_selection = "satSourceReplay" if algorithm == "sat" else "epaSourceReplay" if iterations else "unavailable"
    if fields["selection"] != expected_selection:
        raise ValueError(f"selection does not match trace source state: {fields['selection']}")
    if algorithm == "sat":
        replay_hit = _boolean(fields["sat.replay.hit"], "sat.replay.hit")
        _boolean(fields["sat.replay.matchesResult"], "sat.replay.matchesResult")
        _sat_candidates(fields["sat.candidates"], replay_hit)
        _integer(fields["sat.winner.index"], "sat.winner.index", 0)
        if replay_hit:
            if fields["sat.winner.source"] not in {"a", "b"}:
                raise ValueError("SAT hit winner source must be a or b")
            _vector(fields["sat.winner.preOrientation"], "sat.winner.preOrientation")
            _number(fields["sat.winner.centerDot"], "sat.winner.centerDot")
            _boolean(fields["sat.winner.orientationFlip"], "sat.winner.orientationFlip")
            _vector(fields["sat.winner.finalAxis"], "sat.winner.finalAxis")
            _number(fields["sat.winner.depth"], "sat.winner.depth")
        elif fields["sat.winner.source"] not in {"0", "1"}:
            raise ValueError("SAT miss winner source must identify the separating input")
    if method == "getClipManifold" and not hit and fields["clipped"] != "false":
        raise ValueError("a missed detector cannot produce a clipped manifold")
    return tuple(fields[key] for key in IDENTITY_FIELDS), fields


def _records(lines, provider, label):
    records = [line for line in lines if line.startswith("DYN4K_COLLISION_DIAGNOSTIC\tv2\t")]
    if len(records) != 72:
        raise ValueError(f"expected 72 {label} v2 rows, found {len(records)}")
    parsed = [_parse_record(record, provider) for record in records]
    identities = [identity for identity, _ in parsed]
    if len(set(identities)) != 72:
        raise ValueError(f"{label} v2 rows contain duplicate identities")
    expected = set()
    for fixture in FIXTURE_SHAPES:
        detector = "gjk" if fixture not in {"PolygonCapsule", "PolygonPolygon"} else "sat"
        detector_method = "detectGjk" if detector == "gjk" else "detectSat"
        for step in range(4):
            expected.add((fixture, detector_method, "center" if step < 2 else "shifted",
                          "forward" if step % 2 == 0 else "reverse", str(step), detector))
        step = 4
        for phase in ("center", "shifted"):
            for algorithm in ("gjk", "sat"):
                for order in ("forward", "reverse"):
                    expected.add((fixture, "getClipManifold", phase, order, str(step), algorithm))
                    step += 1
    if set(identities) != expected:
        raise ValueError(f"{label} trace identity schedule is incomplete or unexpected")
    return records, set(identities)


def validate(native_directory, java_tsv, native_tsv):
    native_directory = Path(native_directory)
    reports = sorted(native_directory.glob("TEST-*.xml"))
    expected_names = set(SUITES.values())
    actual_names = {path.name for path in reports}
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        unexpected = sorted(actual_names - expected_names)
        raise ValueError(f"Native XML report set mismatch; missing={missing}, unexpected={unexpected}")

    diagnostic_records = None
    for suite_name, report_name in SUITES.items():
        report_path = native_directory / report_name
        root = ET.parse(report_path).getroot()
        expected_suite_id = f"{TARGET}.{suite_name}"
        if root.tag != "testsuite" or root.attrib.get("name") != expected_suite_id:
            raise ValueError(
                f"wrong suite identity in {report_name}: {root.attrib.get('name')}"
            )
        if suite_name.endswith("WindowsCollisionIntermediateDiagnosticTest"):
            test_cases = root.findall("testcase")
            cases = {case.attrib.get("name") for case in test_cases}
            if cases != DIAGNOSTIC_CASES or len(test_cases) != 6:
                raise ValueError(f"diagnostic case set mismatch: {sorted(cases)}")
            if any(case.find("skipped") is not None for case in test_cases):
                raise ValueError("diagnostic suite contains skipped cases")
            system_output = root.find("system-out")
            if system_output is None or system_output.text is None:
                raise ValueError("diagnostic suite has no system-out trace")
            diagnostic_records = system_output.text.splitlines()
        else:
            test_cases = root.findall("testcase")
            case_ids = [case.attrib.get("name") for case in test_cases]
            expected_cases = ORIGINAL_CASES[suite_name]
            if set(case_ids) != expected_cases or len(case_ids) != len(expected_cases):
                missing = sorted(expected_cases - set(case_ids))
                unexpected = sorted(set(case_ids) - expected_cases)
                raise ValueError(
                    f"original suite case set mismatch in {suite_name}; "
                    f"missing={missing}, unexpected={unexpected}"
                )
            skipped = sorted(
                case.attrib.get("name")
                for case in test_cases
                if case.find("skipped") is not None
            )
            if skipped:
                raise ValueError(f"original suite contains skipped cases in {suite_name}: {skipped}")

    if diagnostic_records is None:
        raise ValueError("diagnostic report was not processed")
    native_rows, native_identities = _records(diagnostic_records, "dyn4k", "Native")
    java_rows, java_identities = _records(
        Path(java_tsv).read_text(encoding="utf-8").splitlines(), "dyn4j-6.0.0", "Java"
    )
    if native_identities != java_identities:
        missing_native = sorted(java_identities - native_identities)
        missing_java = sorted(native_identities - java_identities)
        raise ValueError(
            f"Native/Java identity mismatch; missing_native={missing_native}, "
            f"missing_java={missing_java}"
        )

    destination = Path(native_tsv)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="\n") as output:
        output.write("\n".join(native_rows) + "\n")
    return len(reports), len(DIAGNOSTIC_CASES), len(native_rows), len(java_rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate focused mingwX64 collision evidence.")
    commands = parser.add_subparsers(dest="command", required=True)
    validate_command = commands.add_parser("validate")
    validate_command.add_argument("--native-directory", required=True)
    validate_command.add_argument("--java-tsv", required=True)
    validate_command.add_argument("--native-tsv", required=True)
    status_command = commands.add_parser("status")
    status_command.add_argument("--gradle-exit-code", required=True)
    status_command.add_argument("--java-exit-code", required=True)
    status_command.add_argument("--collection-status", type=int, required=True)
    status_command.add_argument("--validation-status", type=int, required=True)
    args = parser.parse_args(argv)

    if args.command == "status":
        failed = (
            args.gradle_exit_code != "0"
            or args.java_exit_code != "0"
            or args.collection_status != 0
            or args.validation_status != 0
        )
        if failed:
            print(
                "WINDOWS_COLLISION_FOCUS_FAILED "
                f"gradle={args.gradle_exit_code} java={args.java_exit_code} "
                f"collection={args.collection_status} validation={args.validation_status}"
            )
            return 1
        print("WINDOWS_COLLISION_FOCUS_PASSED gradle=0 java=0 collection=0 validation=0")
        return 0

    try:
        suites, cases, native_rows, java_rows = validate(
            args.native_directory, args.java_tsv, args.native_tsv
        )
    except (OSError, ET.ParseError, ValueError) as error:
        print(f"WINDOWS_COLLISION_FOCUS_VALIDATION_FAILED: {error}", file=sys.stderr)
        return 1
    print(
        "WINDOWS_COLLISION_FOCUS_VALIDATION_OK "
        f"suites={suites} diagnosticCases={cases} nativeRows={native_rows} "
        f"javaRows={java_rows} identityParity=exact"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
