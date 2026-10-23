import re
import struct
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/windows-collision-focus.yml"
PRODUCER = ROOT / "tools/diagnostic/windows_collision/run-focused-controls.ps1"
HELPER = ROOT / "tools/compatibility/windows_collision_focus.py"
sys.path.insert(0, str(ROOT))
from tools.compatibility import windows_collision_focus as focus
from tools.compatibility.test_qualification_workflow import workflow_event_blocks


FIXTURE_SHAPES = {
    "CapsuleSlice": ("Capsule", "Slice"),
    "CirclePolygon": ("Circle", "Polygon"),
    "CircleSegment": ("Circle", "Segment"),
    "CircleSlice": ("Circle", "Slice"),
    "PolygonCapsule": ("Polygon", "Capsule"),
    "PolygonPolygon": ("Polygon", "Polygon"),
}
EPA_SCHEMA = (
    "index:edgeId:edgeA:edgeB:normalBefore:normalAfter:distance:support:"
    "projection:delta:stop:equalDistanceEdgeIds:mirrorMatches"
)


def number(value):
    value = float(value)
    bits = struct.unpack(">Q", struct.pack(">d", value))[0]
    if bits >= 1 << 63:
        bits -= 1 << 64
    return f"{value!r}@{bits}"


def vector(x=0.0, y=0.0):
    return f"{number(x)},{number(y)}"


def shape(kind):
    parts = [f"kind={kind}", f"center={vector()}", f"radius={number(1.0)}"]
    if kind == "Circle":
        parts.append(f"circle.radius={number(1.0)}")
    elif kind == "Capsule":
        parts.extend((f"capsule.length={number(1.0)}", f"capsule.capRadius={number(0.25)}",
                      f"capsule.localFoci={vector(-0.25)};{vector(0.25)}",
                      f"capsule.localAxis={number(1.0)},{number(0.0)}"))
    elif kind == "Slice":
        parts.extend((f"slice.radius={number(0.5)}", f"slice.theta={number(0.8)}",
                      f"slice.circleCenter={vector()}",
                      f"slice.rotation={number(1.0)},{number(0.0)}",
                      f"slice.upperEdge=edge:0:0:{vector(0.0, 1.0)}:1:{vector(1.0, 0.0)}:0:{vector(0.0, 1.0)}:{vector(1.0, 0.0)}",
                      f"slice.lowerEdge=edge:0:0:{vector(0.0, -1.0)}:1:{vector(1.0, 0.0)}:0:{vector(0.0, -1.0)}:{vector(1.0, 0.0)}"))
    elif kind == "Segment":
        parts.extend((f"segment.length={number(1.0)}",
                      f"vertices={vector(-0.5)};{vector(0.5)}",
                      f"normals={vector(1, 0)};{vector(0, 1)}"))
    elif kind == "Polygon":
        points = (vector(0, 0), vector(1, 0), vector(1, 1), vector(0, 1))
        normals = (vector(0, -1), vector(1, 0), vector(0, 1), vector(-1, 0))
        parts.extend((f"vertices={';'.join(points)}", f"normals={';'.join(normals)}"))
    return "|".join(parts)


def polygon_edges(kind):
    if kind != "Polygon":
        return "na"
    return ";".join(":".join((str(index), number(1), number(0), number(0), number(1), number(1),
                               number(1), number(1), f"{number(0)},{number(-1)}", number(1),
                               vector(0, -1), vector(0, -1))) for index in range(4))


def record(fixture, step, provider):
    shape_a, shape_b = FIXTURE_SHAPES[fixture]
    if step < 4:
        algorithm = "gjk" if fixture not in ("PolygonCapsule", "PolygonPolygon") else "sat"
        method = "detectGjk" if algorithm == "gjk" else "detectSat"
        phase = "center" if step < 2 else "shifted"
        order = "forward" if step % 2 == 0 else "reverse"
    else:
        slot = step - 4
        phase = "center" if slot < 4 else "shifted"
        algorithm = "gjk" if slot % 4 < 2 else "sat"
        method = "getClipManifold"
        order = "forward" if slot % 2 == 0 else "reverse"
    if order == "reverse":
        shape_a, shape_b = shape_b, shape_a
    hit = step % 5 != 0
    fields = {
        "provider": provider, "fixture": fixture, "method": method, "phase": phase,
        "order": order, "step": str(step), "algorithm": algorithm,
        "a.transform": ",".join((number(1), number(-0.0), number(0), number(0), number(1), number(0))),
        "b.transform": ",".join((number(1), number(-0.0), number(0), number(0), number(1), number(0))),
        "a.center.local": vector(), "b.center.local": vector(),
        "a.center.world": vector(), "b.center.world": vector(),
        "hit": str(hit).lower(), "booleanHit": "na" if method == "getClipManifold" else str(hit).lower(),
        "penetration.normal": vector(1, 0), "penetration.depth": number(0.5),
        "selection": "satSourceReplay" if algorithm == "sat" else "epaSourceReplay" if hit else "unavailable",
        "clipped": str(hit).lower() if method == "getClipManifold" else "na",
        "manifold.normal": vector(1, 0) if method == "getClipManifold" else "na",
        "manifold.count": "1" if method == "getClipManifold" and hit else "0" if method == "getClipManifold" else "na",
        "a.shape.local": shape(shape_a), "b.shape.local": shape(shape_b),
        "a.polygon.edgeArithmetic": polygon_edges(shape_a),
        "b.polygon.edgeArithmetic": polygon_edges(shape_b),
        "a.foci.world": "null", "b.foci.world": "null",
        "a.axes.withB": "null", "b.axes.withA": "null",
        "gjk.initial.centerDirection": vector(), "gjk.initial.effectiveDirection": vector(1, 0),
        "clip.probe.feature.a": "na" if not hit else f"point:0:{vector(1, 0)}",
        "clip.probe.feature.b": "na" if not hit else f"point:0:{vector(-1, 0)}",
        "epa.replay.identity": "unobserved",
        "epa.replay.simplex": ";".join((vector(1, 0), vector(-1, 0), vector(0, 1))) if algorithm == "gjk" and hit else "",
        "epa.replay.iteration": "1" if algorithm == "gjk" and hit else "0",
        "epa.replay.stop": "epsilon" if algorithm == "gjk" and hit else "notRun",
        "epa.replay.epsilon": number(1e-8), "epa.replay.maxIterations": "100",
        "epa.iteration.schema": EPA_SCHEMA,
        "epa.iteration.records": "1:0:" + ":".join((
            vector(1, 0), vector(-1, 0), vector(0, 1), vector(0, 1), number(1),
            vector(1, 0), number(1), number(0), "epsilon", "0", "true"))
            if algorithm == "gjk" and hit else "",
        "epa.queue.reconstructedMatches": "true",
        "epa.edge.a": vector(1, 0) if algorithm == "gjk" and hit else "na",
        "epa.edge.b": vector(-1, 0) if algorithm == "gjk" and hit else "na",
        "epa.edge.normal": vector(0, 1) if algorithm == "gjk" and hit else "na",
        "epa.edge.distance": number(1) if algorithm == "gjk" and hit else "na",
        "epa.terminal.support": vector(1, 0) if algorithm == "gjk" and hit else "na",
        "epa.terminal.projection": number(1) if algorithm == "gjk" and hit else "na",
        "epa.terminal.delta": number(0) if algorithm == "gjk" and hit else "na",
        "epa.replay.normalMatchesResult": str(hit).lower() if algorithm == "gjk" and hit else "na",
        "epa.replay.depthMatchesResult": str(hit).lower() if algorithm == "gjk" and hit else "na",
    }
    for index in range(6):
        fields[f"support.{index}.direction"] = vector(1, 0)
        fields[f"support.{index}.a"] = vector(1, 0)
        fields[f"support.{index}.b.negated"] = vector(-1, 0)
        fields[f"support.{index}.minkowski"] = vector(2, 0)
    if algorithm == "sat":
        fields.update({
            "sat.replay.hit": str(hit).lower(), "sat.replay.matchesResult": "true",
            "sat.candidates": f"0:0:{vector(1, 0)}:{number(0)},{number(1)}:{number(0)},{number(1)}:{number(1)}:false:false:na:na:{number(1)}:{vector(1, 0)}:true" if hit else
                f"0:0:separated:{vector(1, 0)}:{number(0)},{number(1)}:{number(2)},{number(3)}",
            "sat.winner.source": "a" if hit else "0", "sat.winner.index": "0",
        })
        if hit:
            fields.update({
                "sat.winner.preOrientation": vector(1, 0), "sat.winner.centerDot": number(1),
                "sat.winner.orientationFlip": "false", "sat.winner.finalAxis": vector(1, 0),
                "sat.winner.depth": number(1),
            })
    if method == "getClipManifold" and hit:
        fields.update({"manifold.point.0.position": vector(), "manifold.point.0.depth": number(0.5),
                       "manifold.point.0.id": "distance"})
    return "\t".join(("DYN4K_COLLISION_DIAGNOSTIC", "v2") + tuple(
        f"{key}={value}" for key, value in fields.items()))


HISTORICAL_FAILURES = {
    ("CapsuleSliceTest", "detectGjk"),
    ("CapsuleSliceTest", "getClipManifold"),
    ("CirclePolygonTest", "detectGjk"),
    ("CircleSegmentTest", "detectGjk"),
    ("CircleSliceTest", "detectGjk"),
    ("PolygonCapsuleTest", "detectSat"),
    ("PolygonCapsuleTest", "getClipManifold"),
    ("PolygonPolygonTest", "detectSat"),
    ("PolygonPolygonTest", "getClipManifold"),
}


def write_reports(directory, omit=None, original_case_mutation=None):
    native_rows = []
    for fixture_name in (
            "CapsuleSlice", "CirclePolygon", "CircleSegment", "CircleSlice",
            "PolygonCapsule", "PolygonPolygon"):
        for step in range(12):
            native_rows.append(record(fixture_name, step, "dyn4k"))
    for suite, filename in focus.SUITES.items():
        if filename == omit:
            continue
        attributes = {"name": f"{focus.TARGET}.{suite}"}
        root = ET.Element("testsuite", attributes)
        if suite.endswith("WindowsCollisionIntermediateDiagnosticTest"):
            for case in sorted(focus.DIAGNOSTIC_CASES):
                ET.SubElement(root, "testcase", {"name": case})
            output = ET.SubElement(root, "system-out")
            output.text = "\n".join(native_rows)
        else:
            class_name = suite.rsplit(".", 1)[-1]
            case_ids = sorted(focus.ORIGINAL_CASES[suite])
            mutation = original_case_mutation or {}
            if mutation.get("kind") == "empty" and mutation.get("suite") == suite:
                case_ids = []
            elif mutation.get("kind") == "missing" and mutation.get("suite") == suite:
                case_ids.remove(mutation["case"])
            for case_id in case_ids:
                case = ET.SubElement(root, "testcase", {"name": case_id})
                if (mutation.get("kind") == "skipped" and mutation.get("suite") == suite
                        and mutation.get("case") == case_id):
                    ET.SubElement(case, "skipped")
                if (class_name, case_id.split("[", 1)[0]) in HISTORICAL_FAILURES:
                    ET.SubElement(case, "failure", {"message": "preserved assertion failure"})
        ET.ElementTree(root).write(directory / filename, encoding="utf-8", xml_declaration=True)
    java_rows = [row.replace("provider=dyn4k", "provider=dyn4j-6.0.0", 1)
                 for row in native_rows]
    return native_rows, java_rows


def require_workflow_contract(workflow, helper, producer):
    triggers = list(workflow_event_blocks(workflow))
    if triggers != ["workflow_dispatch"]:
        raise AssertionError(f"Expected workflow_dispatch only, found {triggers}")
    delegated_call = (
        "& (Join-Path $PWD 'tools/diagnostic/windows_collision/run-focused-controls.ps1') "
        "-Route $env:DYN4K_COLLISION_ROUTE"
    )
    if delegated_call not in workflow:
        raise AssertionError("The workflow must invoke the focused controls producer")
    if "DYN4K_COLLISION_ROUTE: ${{ inputs.route }}" not in workflow:
        raise AssertionError("The workflow must pass the selected route to the producer")
    if "tools/compatibility/windows_collision_focus.py" not in producer:
        raise AssertionError("The producer must invoke the shared report validator")
    if "if actual_names != expected_names:" not in helper:
        raise AssertionError("The shared validator must reject an incomplete report set")
    if "len(records) != 72" not in helper:
        raise AssertionError("The shared validator must require 72 rows")
    if "native_identities != java_identities" not in helper:
        raise AssertionError("The shared validator must compare trace identities")
    if "ORIGINAL_CASES" not in helper or "contains skipped cases" not in helper:
        raise AssertionError("The shared validator must check original cases and reject skips")
    if "--collection-status $collectionStatus" not in producer:
        raise AssertionError("The producer must report collection status")
    if "--validation-status $validationStatus" not in producer:
        raise AssertionError("The producer must report validation status")
    for evidence in (
            "gradle-console.log", "gradle-exit-code.txt", "java-console.log",
            "java-exit-code.txt", "baseline-source-revision.txt",
            "runner-runtime-identity.txt", "sha256-inventory.txt",
            "collection-status.txt", "validation-status.txt"):
        if evidence not in producer:
            raise AssertionError(f"The producer must record {evidence}")


class WindowsCollisionFocusWorkflowContractTest(unittest.TestCase):
    def setUp(self):
        self.workflow = WORKFLOW.read_text()
        self.producer = PRODUCER.read_text()
        self.helper = HELPER.read_text()

    def test_workflow_is_manual_scoped_and_uses_exact_windows_target(self):
        require_workflow_contract(self.workflow, self.helper, self.producer)
        self.assertIn("runs-on: windows-2025", self.workflow)
        self.assertIn("ref: ${{ github.sha }}", self.workflow)
        self.assertIn("actions/setup-java@v4", self.workflow)
        self.assertIn("java-version: '21'", self.workflow)
        self.assertIn("gradle/actions/setup-gradle@v4", self.workflow)
        self.assertIn("${{ runner.temp }}/windows-collision-focus/", self.workflow)
        self.assertIn("Join-Path $env:RUNNER_TEMP 'windows-collision-focus'", self.producer)
        selected = set(re.findall(r"--tests '([^']+)'", self.producer))
        expected_classes = set(focus.SUITES)
        self.assertEqual(expected_classes, selected)
        self.assertIn(":dyn4k-core:mingwX64Test", self.producer)
        self.assertIn("--no-daemon --rerun-tasks --console=plain", self.producer)
        self.assertIn("run-java-control.ps1", self.producer)
        self.assertIn("-PwindowsCollisionPrecisionDiagnostic=true", self.producer)
        self.assertIn("204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e", self.producer)
        self.assertIn("058bf6d982a0fb89b54050f929f6ea9dae53b714", self.producer)
        self.assertIn("kotlin-native-prebuilt-windows-x86_64-2.4.20", self.producer)

    def test_frozen_original_case_ids_match_all_six_kotlin_test_sources(self):
        for suite, case_ids in focus.ORIGINAL_CASES.items():
            source = ROOT / "dyn4k-core/src/commonTest/kotlin" / Path(*suite.split("."))
            source = source.with_suffix(".kt")
            source_methods = set(re.findall(r"@Test\s+fun\s+(\w+)\s*\(", source.read_text()))
            expected_methods = {case_id.split("[", 1)[0] for case_id in case_ids}
            with self.subTest(suite=suite):
                self.assertEqual(expected_methods, source_methods)

    def test_adversarial_trigger_and_missing_validation_mutations_fail(self):
        with self.assertRaises(AssertionError):
            require_workflow_contract(
                self.workflow.replace("  workflow_dispatch:\n", "  workflow_dispatch:\n  push:\n", 1),
                self.helper, self.producer,
            )
        nested_push = self.workflow.replace(
            "      route:\n", "      push:\n        description: Input named push\n      route:\n", 1)
        require_workflow_contract(nested_push, self.helper, self.producer)
        with self.assertRaises(AssertionError):
            require_workflow_contract(
                self.workflow.replace("run-focused-controls.ps1", "other-controls.ps1", 1),
                self.helper, self.producer,
            )
        with self.assertRaises(AssertionError):
            require_workflow_contract(self.workflow, self.helper.replace(
                "if actual_names != expected_names:", "if actual_names == expected_names:", 1),
                self.producer)
        with self.assertRaises(AssertionError):
            require_workflow_contract(self.workflow, self.helper.replace(
                "len(records) != 72", "len(records) != 71", 1), self.producer)
        with self.assertRaises(AssertionError):
            require_workflow_contract(
                self.workflow, self.helper,
                self.producer.replace("baseline-source-revision.txt", "baseline-revision.txt", 1),
            )

    def test_empty_skipped_and_missing_original_cases_fail_the_shared_helper(self):
        suite = "org.dyn4j.coverage.collision.shapes.a.CapsuleSliceTest"
        case_id = "detectGjk[mingwX64]"
        scenarios = (
            ("empty", {"kind": "empty", "suite": suite}, "case set mismatch"),
            ("skipped", {"kind": "skipped", "suite": suite, "case": case_id},
             "contains skipped cases"),
            ("missing", {"kind": "missing", "suite": suite, "case": case_id},
             "case set mismatch"),
        )
        for name, mutation, expected_error in scenarios:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                _, java_rows = write_reports(directory, original_case_mutation=mutation)
                java_tsv = directory / "java.tsv"
                java_tsv.write_text("\n".join(java_rows) + "\n", encoding="utf-8")
                result = subprocess.run(
                    [sys.executable, str(HELPER), "validate", "--native-directory", str(directory),
                     "--java-tsv", str(java_tsv), "--native-tsv", str(directory / "native.tsv")],
                    check=False, capture_output=True, text=True,
                )
                self.assertNotEqual(0, result.returncode)
                self.assertIn(expected_error, result.stderr)
                self.assertFalse((directory / "native.tsv").exists())

    def test_shared_workflow_extractor_produces_all_rows_and_exact_identity_parity(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            native_rows, java_rows = write_reports(directory)
            java_fields = java_rows[0].split("\t")
            depth_index = next(i for i, field in enumerate(java_fields)
                               if field.startswith("penetration.depth="))
            java_fields[depth_index] = f"penetration.depth={number(0.75)}"
            java_rows[0] = "\t".join(java_fields)
            java_tsv = directory / "java.tsv"
            java_tsv.write_text("\n".join(java_rows) + "\n", encoding="utf-8")
            native_tsv = directory / "native.tsv"
            result = subprocess.run(
                [sys.executable, str(HELPER), "validate", "--native-directory", str(directory),
                 "--java-tsv", str(java_tsv), "--native-tsv", str(native_tsv)],
                check=False, capture_output=True, text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("suites=7 diagnosticCases=6 nativeRows=72 javaRows=72 identityParity=exact",
                          result.stdout)
            self.assertEqual(native_rows, native_tsv.read_text(encoding="utf-8").splitlines())
            failure_count = sum(
                1 for report in directory.glob("TEST-*.xml")
                for case in ET.parse(report).getroot().findall("testcase")
                if case.find("failure") is not None
            )
            self.assertEqual(9, failure_count, "keep the preserved original assertion failures visible")

    def test_native_and_java_rows_require_complete_method_algorithm_schemas(self):
        native_rows = [record(fixture, step, "dyn4k")
                       for fixture in FIXTURE_SHAPES for step in range(12)]
        java_rows = [record(fixture, step, "dyn4j-6.0.0")
                     for fixture in FIXTURE_SHAPES for step in range(12)]
        for rows, provider in ((native_rows, "dyn4k"), (java_rows, "dyn4j-6.0.0")):
            with self.subTest(provider=provider):
                self.assertEqual(72, len(focus._records(rows, provider, provider)[0]))
                scenarios = (
                    ("scalar", "a.shape.local", "fixture=CapsuleSlice"),
                    ("sat", "sat.candidates", "algorithm=sat"),
                    ("epa", "epa.iteration.records", "algorithm=gjk"),
                )
                for label, field, selector in scenarios:
                    mutated = list(rows)
                    index = next(i for i, row in enumerate(mutated) if selector in row)
                    original_identity = tuple(
                        part.split("=", 1)[1]
                        for part in mutated[index].split("\t")[2:]
                        if part.split("=", 1)[0] in focus.IDENTITY_FIELDS
                    )
                    mutated[index] = "\t".join(
                        part for part in mutated[index].split("\t")
                        if not part.startswith(field + "=")
                    )
                    mutated_identity = tuple(
                        part.split("=", 1)[1]
                        for part in mutated[index].split("\t")[2:]
                        if part.split("=", 1)[0] in focus.IDENTITY_FIELDS
                    )
                    self.assertEqual(original_identity, mutated_identity)
                    with self.subTest(missing=label), self.assertRaises(ValueError):
                        focus._records(mutated, provider, provider)

                mutated = list(rows)
                first = mutated[0].split("\t")
                original_identity = tuple(
                    part.split("=", 1)[1]
                    for part in first[2:]
                    if part.split("=", 1)[0] in focus.IDENTITY_FIELDS
                )
                for index, part in enumerate(first):
                    if part.startswith("a.transform="):
                        key, values = part.split("=", 1)
                        scalar, bits = values.split(",", 1)[0].split("@", 1)
                        first[index] = f"{key}={scalar}@{int(bits) + 1}," + values.split(",", 1)[1]
                        break
                mutated[0] = "\t".join(first)
                mutated_identity = tuple(
                    part.split("=", 1)[1]
                    for part in first[2:]
                    if part.split("=", 1)[0] in focus.IDENTITY_FIELDS
                )
                self.assertEqual(original_identity, mutated_identity)
                with self.subTest(malformed="numeric-bits"), self.assertRaises(ValueError):
                    focus._records(mutated, provider, provider)

                duplicate = list(rows)
                duplicate[0] += "\t" + next(
                    part for part in duplicate[0].split("\t") if part.startswith("a.shape.local=")
                )
                with self.subTest(malformed="duplicate-key"), self.assertRaises(ValueError):
                    focus._records(duplicate, provider, provider)

    def test_actual_workflow_validator_exits_nonzero_when_a_report_is_missing(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            _, java_rows = write_reports(
                directory,
                omit="TEST-mingwX64Test.org.dyn4j.collision.narrowphase.WindowsCollisionIntermediateDiagnosticTest.xml",
            )
            java_tsv = directory / "java.tsv"
            java_tsv.write_text("\n".join(java_rows) + "\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(HELPER), "validate", "--native-directory", str(directory),
                 "--java-tsv", str(java_tsv), "--native-tsv", str(directory / "native.tsv")],
                check=False, capture_output=True, text=True,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("Native XML report set mismatch", result.stderr)
            self.assertFalse((directory / "native.tsv").exists())

    def test_evidence_collection_keeps_failure_and_always_upload_controls(self):
        for evidence in (
                "gradle-console.log", "gradle-exit-code.txt", "java-console.log",
                "java-exit-code.txt", "baseline-source-revision.txt",
                "runner-runtime-identity.txt", "sha256-inventory.txt",
                "collection-status.txt", "validation-status.txt"):
            with self.subTest(evidence=evidence):
                self.assertIn(evidence, self.producer)
        self.assertIn("if: always()", self.workflow)
        self.assertIn("actions/upload-artifact@v4", self.workflow)
        self.assertIn("if-no-files-found: error", self.workflow)
        self.assertIn("windows_collision_focus.py status", self.producer)
        self.assertIn("if-no-files-found: error", self.workflow)
        self.assertLess(self.producer.index("run-java-control.ps1"),
                        self.producer.index("windows_collision_focus.py status"))
        self.assertIn("if ($statusExit -ne 0 -or $scalarExit -ne 0 -or -not $routeControlExit)",
                      self.producer)
        self.assertIn('throw "Focused controls failed:', self.producer)
        self.assertNotIn("full_corpus", self.workflow)
        self.assertNotIn("staging-repository", self.workflow)

    def test_native_report_errors_do_not_short_circuit_later_evidence_collection(self):
        copy_catch = self.producer.index('"Native XML copy failed for')
        java_control = self.producer.index("run-java-control.ps1")
        runner_identity = self.producer.index("runner-runtime-identity.txt")
        inventory = self.producer.index("sha256-inventory.txt")
        status_decision = self.producer.index("windows_collision_focus.py status")
        upload = self.workflow.index("Upload Windows collision evidence")
        self.assertLess(copy_catch, java_control)
        self.assertLess(java_control, runner_identity)
        self.assertLess(runner_identity, inventory)
        self.assertLess(inventory, status_decision)
        self.assertLess(self.workflow.index("run-focused-controls.ps1"),
                        self.workflow.index("Upload Windows collision evidence"))
        self.assertIn("$collectionStatus = 1", self.producer[copy_catch:java_control])
        self.assertIn("if: always()", self.workflow[upload:])

    def test_gradle_exit_is_written_once_and_collection_error_fails_final_status(self):
        capture = self.producer.index("$gradleExit = [string]$LASTEXITCODE")
        raw_write_line = "Set-Content -Path $gradleExitFile -Value $gradleExit"
        raw_write = self.producer.index(raw_write_line)
        self.assertLess(capture, raw_write)
        self.assertEqual(1, self.producer.count(raw_write_line))
        self.assertIn("gradle-exit-code.txt", self.producer)
        self.assertNotIn("$gradleExit =", self.producer[raw_write:])
        self.assertIn("--gradle-exit-code $gradleExit", self.producer)

        collector_failure = subprocess.run(
            [sys.executable, str(HELPER), "status", "--gradle-exit-code", "0",
             "--java-exit-code", "0", "--collection-status", "1",
             "--validation-status", "0"],
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(1, collector_failure.returncode)
        self.assertIn("gradle=0 java=0 collection=1 validation=0", collector_failure.stdout)

        assertion_failure = subprocess.run(
            [sys.executable, str(HELPER), "status", "--gradle-exit-code", "1",
             "--java-exit-code", "0", "--collection-status", "0",
             "--validation-status", "0"],
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(1, assertion_failure.returncode)
        self.assertIn("gradle=1", assertion_failure.stdout)


if __name__ == "__main__":
    unittest.main()
