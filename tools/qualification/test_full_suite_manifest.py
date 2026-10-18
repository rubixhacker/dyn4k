import copy
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import full_suite_manifest


ROOT = Path(__file__).resolve().parents[2]


class FullSuiteManifestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / full_suite_manifest.MANIFEST_PATH).read_text())

    def test_every_lane_selects_complete_portable_suite_and_jvm_only_cases(self):
        full_suite_manifest.validate_manifest(self.manifest, ROOT)
        self.assertEqual(112, len(self.manifest["lanes"]))
        self.assertEqual(2526, len(self.manifest["cases"]))
        linux = full_suite_manifest.select_lane(self.manifest, "linuxX64:Linux x64:minimum:debug-g", ROOT)
        jvm = full_suite_manifest.select_lane(self.manifest, "jvm:Java:minimum:no-optimize", ROOT)
        self.assertEqual(2523, len(linux["case_ids"]))
        self.assertEqual(2526, len(jvm["case_ids"]))
        self.assertEqual(set(linux["case_ids"]), set(jvm["case_ids"]) -
                         {case["id"] for case in self.manifest["cases"] if case["scope"] == "jvm-only"})
        self.assertEqual(len(linux["case_ids"]), len(set(linux["case_ids"])))
        self.assertIn("numerical-parity", linux["required_gates"])
        self.assertIn("unchanged-java-corpus", jvm["required_gates"])
        self.assertNotIn("unchanged-java-corpus", linux["required_gates"])

    def test_reviewed_geometry_originals_assign_upstream_math_methods_to_geometry(self):
        expected = {
            "UpstreamMatrix22CoverageTest": 27,
            "UpstreamMatrix33CoverageTest": 26,
            "UpstreamRotationCoverageTest": 19,
            "UpstreamTransformCoverageTest": 12,
            "UpstreamVector2CoverageTest": 27,
            "UpstreamVector3CoverageTest": 21,
        }
        selected = [case for case in self.manifest["cases"]
                    if case["classname"].removeprefix("org.dyn4j.coverage.") in expected]
        self.assertEqual(expected, Counter(case["classname"].split(".")[-1]
                                           for case in selected))
        self.assertEqual(132, len(selected))
        self.assertTrue(all(case["originals"] and
                            all(original.startswith("org.dyn4j.geometry.")
                                for original in case["originals"])
                            for case in selected))
        self.assertEqual({"geometry"}, {case["area"] for case in selected})

    def test_six_windows_collision_diagnostics_are_portable_supplements(self):
        diagnostic = [case for case in self.manifest["cases"] if
                      case["classname"] ==
                      "org.dyn4j.collision.narrowphase.WindowsCollisionIntermediateDiagnosticTest"]
        self.assertEqual({"capsuleSlice", "circlePolygon", "circleSegment",
                          "circleSlice", "polygonCapsule", "polygonPolygon"},
                         {case["method"] for case in diagnostic})
        self.assertEqual(6, len(diagnostic))
        self.assertTrue(all(case["area"] == "collision" and
                            case["scope"] == "portable" and
                            case["kind"] == "supplemental" and
                            not case["originals"] for case in diagnostic))

    def test_five_rotation_observation_isolation_cases_are_portable_supplements(self):
        cases = [case for case in self.manifest["cases"] if
                 case["classname"] == "org.dyn4j.geometry.RotationObservationIsolationTest"]
        self.assertEqual({"failedWorldObservationCannotBeClearedByAnotherStep",
                          "foreignWorldStepFailsCaptureAfterBothWorldsComplete",
                          "nestedObservationRestoresOuterScope",
                          "observedRotationMatchesOrdinaryRotation",
                          "stepCallbackCannotConsumeOperationRecordsBeforeStepEnds"},
                         {case["method"] for case in cases})
        self.assertEqual(5, len(cases))
        self.assertTrue(all(case["scope"] == "portable" and
                            case["kind"] == "supplemental" and
                            not case["originals"] for case in cases))

    def test_missing_area_case_extra_case_and_duplicate_case_fail(self):
        for mutation in ("area", "missing", "extra", "duplicate"):
            changed = copy.deepcopy(self.manifest)
            if mutation == "area":
                changed["areas"].remove("joints")
            elif mutation == "missing":
                changed["cases"].pop()
            elif mutation == "extra":
                changed["cases"].append({**changed["cases"][0], "id": "extra"})
            else:
                changed["cases"].append(changed["cases"][0])
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                full_suite_manifest.validate_manifest(changed, ROOT)

    def test_source_map_platform_lane_pass_and_gate_mutations_fail(self):
        changes = (
            lambda m: m["bindings"].update(source_tree_sha256="0" * 64),
            lambda m: m["bindings"].update(original_map_sha256="0" * 64),
            lambda m: m["cases"][0].update(scope="jvm-only"),
            lambda m: m["targets"].pop("watchosDeviceArm64"),
            lambda m: m["lanes"].pop("jvm:Java:minimum:no-optimize"),
            lambda m: m["cases"][0].update(status="PASSED"),
            lambda m: m["lanes"]["jvm:Java:minimum:no-optimize"]["required_gates"].remove("numerical-parity"),
        )
        for index, change in enumerate(changes):
            changed = copy.deepcopy(self.manifest)
            change(changed)
            with self.subTest(index=index), self.assertRaises(ValueError):
                full_suite_manifest.validate_manifest(changed, ROOT)

    def test_changed_source_and_reviewed_map_fail_against_frozen_manifest(self):
        corpus = json.loads((ROOT / full_suite_manifest.CORPUS_PATH).read_text())
        copied = [full_suite_manifest.CORPUS_PATH,
                  "tools/qualification/full-common-original-map.tsv",
                  "tools/qualification/full-common-reviewed-pairs.tsv"]
        copied += [item["path"] for item in corpus["source_files"]]
        copied += [path for paths in full_suite_manifest.GATE_SOURCES.values()
                   for path in paths]
        with tempfile.TemporaryDirectory() as scratch:
            repository = Path(scratch)
            for relative in copied:
                path = repository / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((ROOT / relative).read_bytes())
            full_suite_manifest.validate_manifest(self.manifest, repository)
            source = repository / corpus["source_files"][0]["path"]
            source.write_bytes(source.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "source"):
                full_suite_manifest.validate_manifest(self.manifest, repository)
            source.write_bytes((ROOT / corpus["source_files"][0]["path"]).read_bytes())
            mapping = repository / "tools/qualification/full-common-original-map.tsv"
            mapping.write_bytes(mapping.read_bytes() + b"\n")
            with self.assertRaises(ValueError):
                full_suite_manifest.validate_manifest(self.manifest, repository)

    def test_platform_expectation_helpers_are_bound_to_source_digest(self):
        corpus = json.loads((ROOT / full_suite_manifest.CORPUS_PATH).read_text())
        helpers = [
            f"dyn4k-core/src/{source_set}/kotlin/org/dyn4j/world/WorldNestedViewRuntime.kt"
            for source_set in ("androidHostTest", "jsTest", "nativeTest", "wasmJsTest",
                               "wasmWasiTest")
        ]
        bound_paths = {item["path"] for item in corpus["source_files"]}
        self.assertTrue(set(helpers) <= bound_paths, set(helpers) - bound_paths)

        copied = [full_suite_manifest.CORPUS_PATH,
                  "tools/qualification/full-common-original-map.tsv",
                  "tools/qualification/full-common-reviewed-pairs.tsv"]
        copied += [item["path"] for item in corpus["source_files"]]
        copied += [path for paths in full_suite_manifest.GATE_SOURCES.values()
                   for path in paths]
        with tempfile.TemporaryDirectory() as scratch:
            repository = Path(scratch)
            for relative in copied:
                path = repository / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((ROOT / relative).read_bytes())
            full_suite_manifest.validate_manifest(self.manifest, repository)
            for relative in helpers:
                with self.subTest(helper=relative):
                    source = repository / relative
                    source.write_bytes(source.read_bytes() + b"\n")
                    with self.assertRaisesRegex(ValueError, "source"):
                        full_suite_manifest.validate_manifest(self.manifest, repository)
                    source.write_bytes((ROOT / relative).read_bytes())


if __name__ == "__main__":
    unittest.main()
