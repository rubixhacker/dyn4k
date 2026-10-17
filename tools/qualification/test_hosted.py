import hashlib
import os
import platform
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import hosted
import qualify


class HostedQualificationTests(unittest.TestCase):
    def test_staged_web_publications_bind_klib_binaries(self):
        for target in ("js", "wasmJs", "wasmWasi"):
            for module in qualify.MODULES:
                self.assertTrue(qualify.target_binary_path(module, target).endswith(".klib"))

    @unittest.skipUnless(platform.system() == "Linux", "Linux host probe")
    def test_wrong_host_is_reported_without_mac_commands(self):
        self.assertEqual("Linux", hosted.discover_runtime("macosArm64")["system"])

    def test_frozen_native_groups_pin_source_and_staged_consumer_cases(self):
        manifest = qualify.load_json_strict(Path(__file__).with_name("foundation-probes.json"))
        groups = {group["id"]: group for group in manifest["groups"]}
        for target in hosted.NATIVE_TARGETS:
            self.assertEqual(30, len(qualify.expected_probe_cases(manifest, groups[target])))
            self.assertEqual(2, len(qualify.expected_probe_cases(manifest, groups[f"core-{target}"])))
            self.assertEqual(2, len(qualify.expected_probe_cases(
                manifest, groups[f"consumer-{target}"])))
        self.assertEqual(32, len(qualify.expected_probe_cases(manifest, groups["jvm"])))
        self.assertEqual(
            [("jsBrowserTest.qualification.StagedGeometryTest",
              "namedConstructorsResolveFromPublishedCommonAndPlatformVariants[js, browser, Safari26.6.2, MacOS10.15.7]"),
             ("jsBrowserTest.qualification.StagedGeometryTest",
              "stagedRootCoordinatesResolveAndTransformSharedObjects[js, browser, Safari26.6.2, MacOS10.15.7]")],
            qualify.expected_probe_cases(manifest, groups["consumer-jsSafari"]))

    def test_stale_or_partial_staged_consumer_xml_fails(self):
        manifest = qualify.load_json_strict(Path(__file__).with_name("foundation-probes.json"))
        group = next(group for group in manifest["groups"] if group["id"] == "consumer-macosArm64")
        with tempfile.TemporaryDirectory() as root:
            previous = Path.cwd()
            os.chdir(root)
            try:
                report = Path("report.xml")
                report.write_text('<testsuite tests="1" failures="0" errors="0" skipped="0">'
                                  '<testcase classname="macosArm64Test.qualification.StagedGeometryTest" '
                                  'name="stagedRootCoordinatesResolveAndTransformSharedObjects[macosArm64]" '
                                  'time="0"/></testsuite>')
                selected = {**manifest, "groups": [dict(group, report_pattern="report.xml")]}
                stale = qualify.run_probe(["python3", "-c", "pass"], ["report.xml"],
                                          "a" * 40, Path(root) / "stale.json", selected)
                self.assertEqual("PROBE_FAILED", stale["status"])
                self.assertIn("missing report", stale["reason"])
                partial = qualify.run_probe(
                    ["python3", "-c", "from pathlib import Path; Path('report.xml').write_text(" +
                     repr('<testsuite tests="0" failures="0" errors="0" skipped="0"/>') + ")"],
                    ["report.xml"], "a" * 40, Path(root) / "partial.json", selected)
                self.assertEqual("PROBE_FAILED", partial["status"])
                self.assertIn("partial", partial["reason"])
            finally:
                os.chdir(previous)

    def test_safari_report_requires_the_frozen_browser_case_identity(self):
        manifest = qualify.load_json_strict(Path(__file__).with_name("foundation-probes.json"))
        group = next(group for group in manifest["groups"] if group["id"] == "consumer-jsSafari")
        cases = qualify.expected_probe_cases(manifest, group)
        with tempfile.TemporaryDirectory() as root:
            previous = Path.cwd()
            os.chdir(root)
            try:
                selected = {**manifest, "groups": [dict(group, report_pattern="report.xml")]}
                wrong_runtime = [(classname, name.replace("Safari26.6.2", "Safari26.6.3"))
                                 for classname, name in cases]
                unexpected = [*cases, (cases[0][0], "unexpectedCase[js, browser, Safari26.6.2, MacOS10.15.7]")]
                for observed, expected_status in ((cases, "PROBE_PASSED"),
                                                  (wrong_runtime, "PROBE_FAILED"),
                                                  (unexpected, "PROBE_FAILED")):
                    suite = ET.Element("testsuite", tests=str(len(observed)), failures="0", errors="0",
                                       skipped="0", time="0.1")
                    for classname, name in observed:
                        ET.SubElement(suite, "testcase", classname=classname,
                                      name=name, time="0.1")
                    xml = ET.tostring(suite, encoding="unicode")
                    command = ["python3", "-c", "from pathlib import Path; "
                               "Path('report.xml').write_text(" + repr(xml) + ")"]
                    result = qualify.run_probe(command, ["report.xml"], "a" * 40,
                                               Path(root) / "result.json", selected)
                    self.assertEqual(expected_status, result["status"])
                    self.assertEqual(len(observed), result["executed"])
            finally:
                os.chdir(previous)

    def test_runtime_identity_rejects_wrong_host_and_xcode(self):
        mac = {"system": "Darwin", "machine": "arm64", "os_version": "26.6.2",
               "xcode_version": "26.4.1", "simulators": {"iOS": ["iPhone 17"]}}
        self.assertEqual("READY", hosted.runtime_status("iosSimulatorArm64", mac)[0])
        self.assertEqual("FAILED", hosted.runtime_status(
            "iosSimulatorArm64", {**mac, "machine": "x86_64"})[0])
        self.assertEqual("FAILED", hosted.runtime_status(
            "iosSimulatorArm64", {**mac, "xcode_version": "26.6"})[0])
        self.assertEqual("FAILED", hosted.runtime_status(
            "mingwX64", {"system": "Windows", "machine": "AMD64",
                          "os_version": "10.0.19045"})[0])

    def test_absent_simulator_or_safari_is_unavailable(self):
        mac = {"system": "Darwin", "machine": "arm64", "os_version": "26.6.2",
               "xcode_version": "26.4.1", "simulators": {}}
        self.assertEqual("UNAVAILABLE", hosted.runtime_status("iosSimulatorArm64", mac)[0])
        self.assertEqual("UNAVAILABLE", hosted.runtime_status(
            "jsSafari", {**mac, "safari_version": "", "safaridriver_version": ""})[0])

    def test_staged_target_requires_both_matching_binary_checksums(self):
        with tempfile.TemporaryDirectory() as root:
            staging = Path(root)
            for module in qualify.MODULES:
                binary = staging / qualify.target_binary_path(module, "mingwX64")
                binary.parent.mkdir(parents=True, exist_ok=True)
                binary.write_bytes(module.encode())
                binary.with_name(binary.name + ".sha256").write_text(
                    hashlib.sha256(module.encode()).hexdigest() + "\n")
            self.assertEqual(set(qualify.MODULES), set(hosted.target_hashes(staging, "mingwX64")))
            broken = staging / qualify.target_binary_path("dyn4k", "mingwX64")
            broken.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "checksum"):
                hosted.target_hashes(staging, "mingwX64")
            broken.unlink()
            with self.assertRaisesRegex(ValueError, "missing"):
                hosted.target_hashes(staging, "mingwX64")

    def test_hosted_summary_rejects_stale_missing_and_partial_probes(self):
        sha = "a" * 40
        runtime = {"system": "Darwin", "machine": "arm64", "os_version": "26.6.2",
                   "xcode_version": "26.4.1", "simulators": {}}
        manifest = qualify.load_json_strict(Path(__file__).with_name("foundation-probes.json"))
        good = {"candidate_sha": sha, "status": "PROBE_PASSED", "expected": 32,
                "executed": 32, "failures": 0, "skipped": 0, "exit_code": 0}
        consumer = {**good, "expected": 2, "executed": 2}
        hashes = {"dyn4k-core": "b" * 64, "dyn4k": "c" * 64}
        self.assertEqual("PROBE_PASSED", hosted.hosted_status(
            "macosArm64", sha, runtime, good, consumer, hashes, manifest)[0])
        for source, staged in (({**good, "candidate_sha": "d" * 40}, consumer),
                               (None, consumer), ({**good, "executed": 30}, consumer),
                               (good, {**consumer, "status": "PROBE_FAILED"}),
                               (good, None)):
            self.assertEqual("PROBE_FAILED", hosted.hosted_status(
                "macosArm64", sha, runtime, source, staged, hashes, manifest)[0])

    def test_bounded_result_cannot_promote_full_lane(self):
        sha = "a" * 40
        manifest = qualify.load_json_strict(Path(__file__).with_name("foundation-probes.json"))
        def frozen_digest(ids):
            return qualify.manifest_digest({**manifest, "groups": [group for group in manifest["groups"]
                                                            if group["id"] in ids]})
        source = {"candidate_sha": sha, "status": "PROBE_PASSED", "expected": 32,
                  "executed": 32, "failures": 0, "skipped": 0, "exit_code": 0,
                  "manifest_sha256": frozen_digest(("core-macosArm64", "macosArm64"))}
        consumer = {**source, "expected": 2, "executed": 2,
                    "manifest_sha256": frozen_digest(("consumer-macosArm64",))}
        probe = {"candidate_sha": sha, "target": "macosArm64", "status": "PROBE_PASSED",
                 "runtime": {"system": "Darwin", "machine": "arm64", "os_version": "26.6.2",
                             "xcode_version": "26.4.1", "simulators": {}},
                 "source_probe": source, "consumer_probe": consumer,
                 "artifact_hashes": {"dyn4k-core": "b" * 64, "dyn4k": "c" * 64}}
        self.assertEqual("PROBE_PASSED", qualify.validate_hosted_probe(probe, sha)["status"])
        with self.assertRaisesRegex(ValueError, "candidate"):
            qualify.validate_hosted_probe({**probe, "candidate_sha": "d" * 40}, sha)
        with self.assertRaisesRegex(ValueError, "runtime"):
            qualify.validate_hosted_probe({**probe, "runtime": {**probe["runtime"],
                                                              "machine": "x86_64"}}, sha)
        lane = next(case for case in qualify.expand(qualify.matrix())
                    if case["target"] == "macosArm64")
        self.assertEqual("NOT_RUN", qualify.evaluate(lane, None, sha)["status"])


if __name__ == "__main__":
    unittest.main()
