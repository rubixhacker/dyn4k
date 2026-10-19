import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import full_apple_device_consumer as apple


ROOT = Path(__file__).resolve().parents[2]
IOS_MINIMUM = "iosArm64:iOS physical ARM64:minimum:debug-g"
WATCH_ILP32 = "watchosArm64:watchOS physical ILP32:minimum:debug-g"
WATCH_LP64 = "watchosDeviceArm64:watchOS physical LP64:minimum:debug-g"


class PhysicalAppleConsumerTest(unittest.TestCase):
    def test_approved_matrix_has_all_sixteen_physical_lanes(self):
        lanes = apple.matrix(ROOT)
        self.assertEqual(16, len(lanes))
        self.assertEqual(4, len({lane.split(":")[0] for lane in lanes}))
        self.assertIn(WATCH_ILP32, lanes)
        self.assertIn(WATCH_LP64, lanes)
        self.assertFalse(any("Simulator" in lane for lane in lanes))

    def test_device_rejects_simulator_and_wrong_os_or_abi(self):
        lane, _ = apple.lane_contract(ROOT, IOS_MINIMUM)
        device = {"result": {"devices": [{
            "connectionProperties": {"transportType": "wired"},
            "deviceProperties": {"osVersionNumber": "15.8"},
            "hardwareProperties": {"udid": "physical-1", "productType": "iPhone13,4",
                                   "platform": "iOS", "reality": "physical",
                                   "cpuType": {"name": "arm64"}}}]}}
        raw = json.dumps(device).encode()
        self.assertEqual("physical", apple.select_device(
            raw, lane, "physical-1", "iPhone13,4", "15.8")["kind"])
        device["result"]["devices"][0]["hardwareProperties"]["reality"] = "simulated"
        with self.assertRaisesRegex(ValueError, "simulator"):
            apple.select_device(json.dumps(device).encode(), lane, "physical-1", "iPhone13,4", "15.8")
        device["result"]["devices"][0]["hardwareProperties"]["reality"] = "physical"
        with self.assertRaisesRegex(ValueError, "identity"):
            apple.select_device(json.dumps(device).encode(), lane, "physical-1", "iPhone13,4", "16.0")
        device["result"]["devices"][0]["hardwareProperties"]["cpuType"]["name"] = "arm64_32"
        with self.assertRaisesRegex(ValueError, "ABI"):
            apple.select_device(json.dumps(device).encode(), lane, "physical-1", "iPhone13,4", "15.8")

    def test_watchos_minimum_and_pointer_width_are_distinct(self):
        ilp32, _ = apple.lane_contract(ROOT, WATCH_ILP32)
        lp64, _ = apple.lane_contract(ROOT, WATCH_LP64)
        self.assertEqual(8, apple.TARGETS[ilp32["target"]][2])
        self.assertEqual(26, apple.TARGETS[lp64["target"]][2])
        self.assertEqual("ILP32", apple.TARGETS[ilp32["target"]][3])
        self.assertEqual("LP64", apple.TARGETS[lp64["target"]][3])
        with self.assertRaisesRegex(ValueError, "minimum/current"):
            apple.expected_os(lp64, "8.0")
        with self.assertRaisesRegex(ValueError, "minimum/current"):
            apple.expected_os(ilp32, "26.0")

    def test_original_event_parser_rejects_missing_duplicate_failure_and_skip(self):
        cases = [{"id": "a", "classname": "example.Core", "method": "first"},
                 {"id": "b", "classname": "example.Core", "method": "second"}]
        raw = (b"[ RUN      ] example.Core.first\n"
               b"[       OK ] example.Core.first (2 ms)\n"
               b"[ RUN      ] example.Core.second\n"
               b"[       OK ] example.Core.second (1 ms)\n"
               b"[ RUN      ] qualification.DeviceImageProofTest.copyInstalledImageToDataContainer\n"
               b"[       OK ] qualification.DeviceImageProofTest.copyInstalledImageToDataContainer (1 ms)\n"
               b"[  PASSED  ] 3 tests.\n")
        self.assertEqual(["a", "b"], apple.parse_gtest(raw, cases)[0])
        with self.assertRaises(ValueError):
            apple.parse_gtest(raw.replace(b"[  PASSED  ] 3 tests.",
                                          b"[  PASSED  ] 1 tests."), cases)
        with self.assertRaises(ValueError):
            apple.parse_gtest(raw.replace(b"second", b"first"), cases)
        with self.assertRaises(ValueError):
            apple.parse_gtest(raw.replace(b"[       OK ] example.Core.second",
                                          b"[  FAILED  ] example.Core.second"), cases)
        with self.assertRaises(ValueError):
            apple.parse_gtest(raw + b"[  SKIPPED ] example.Core.second\n", cases)
        with self.assertRaisesRegex(ValueError, "summary differs|completion"):
            apple.parse_gtest(raw.replace(
                b"[ RUN      ] qualification.DeviceImageProofTest.copyInstalledImageToDataContainer\n"
                b"[       OK ] qualification.DeviceImageProofTest.copyInstalledImageToDataContainer (1 ms)\n",
                b"").replace(b"3 tests.", b"2 tests."), cases)

    def test_installed_process_requires_exact_bundle_and_image(self):
        app = "file:///private/var/containers/Bundle/Application/A/core.app/"
        apps = {"result": {"apps": [{"bundleIdentifier": "example.core", "url": app}]}}
        launch = {"info": {"outcome": "success"}, "result": {"process": {
            "processIdentifier": 42,
            "executable": "file:////private/var/containers/Bundle/Application/A/core.app/Dyn4kTests"}}}
        self.assertEqual(42, apple.installed_process(
            json.dumps(apps).encode(), json.dumps(launch).encode(), "example.core")["pid"])
        launch["result"]["process"]["executable"] = launch["result"]["process"][
            "executable"].replace("/A/", "/B/")
        with self.assertRaisesRegex(ValueError, "installed test host"):
            apple.installed_process(json.dumps(apps).encode(), json.dumps(launch).encode(),
                                    "example.core")

    def test_unavailable_is_explicit_not_run_and_replays_without_pass(self):
        candidate = "433d2b5a3137b52f8ff07460086c8e4eadb6ef34"
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "archive"
            result = apple.unavailable(archive, candidate, IOS_MINIMUM,
                                       "physical device missing; test execution NOT_RUN")
            self.assertEqual("NOT_RUN", result["execution"])
            replay = apple.verify(ROOT, candidate, IOS_MINIMUM, archive,
                                  result["archive_sha256"], {}, "", {})
            self.assertEqual("UNAVAILABLE", replay["status"])
            self.assertEqual(0, replay["selected_cases"])
            receipt = json.loads((archive / "receipt.json").read_text())
            receipt["lane"] = WATCH_ILP32
            (archive / "receipt.json").write_text(json.dumps(receipt))
            changed = apple.independent_gates.archive_digest(archive)
            with self.assertRaisesRegex(ValueError, "misbound|differs"):
                apple.verify(ROOT, candidate, IOS_MINIMUM, archive, changed, {}, "", {})


if __name__ == "__main__":
    unittest.main()
