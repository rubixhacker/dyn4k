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
OS_SELECTION = {"schema": 1, "roles": {
    target: {"minimum": minimum, "current": current,
             "minimum_source": "https://support.apple.com/100100",
             "current_source": "https://support.apple.com/100100"}
    for target, minimum, current in (
        ("iosArm64", "15.8.8", "26.7"), ("tvosArm64", "15.6", "26.7"),
        ("watchosArm64", "8.8.2", "26.6"),
        ("watchosDeviceArm64", "26.6", "27.0"))}}


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
        device["result"]["devices"][0]["deviceProperties"]["osVersionNumber"] = "15.8.8"
        raw = json.dumps(device).encode()
        self.assertEqual("physical", apple.select_device(
            raw, lane, "physical-1", "iPhone13,4", "15.8.8", OS_SELECTION)["kind"])
        device["result"]["devices"][0]["hardwareProperties"]["reality"] = "simulated"
        with self.assertRaisesRegex(ValueError, "simulator"):
            apple.select_device(json.dumps(device).encode(), lane, "physical-1", "iPhone13,4", "15.8.8", OS_SELECTION)
        device["result"]["devices"][0]["hardwareProperties"]["reality"] = "physical"
        with self.assertRaisesRegex(ValueError, "identity"):
            apple.select_device(json.dumps(device).encode(), lane, "physical-1", "iPhone13,4", "16.0", OS_SELECTION)
        device["result"]["devices"][0]["hardwareProperties"]["cpuType"]["name"] = "arm64_32"
        with self.assertRaisesRegex(ValueError, "ABI"):
            apple.select_device(json.dumps(device).encode(), lane, "physical-1", "iPhone13,4", "15.8.8", OS_SELECTION)

    def test_watchos_minimum_and_pointer_width_are_distinct(self):
        ilp32, _ = apple.lane_contract(ROOT, WATCH_ILP32)
        lp64, _ = apple.lane_contract(ROOT, WATCH_LP64)
        self.assertEqual(8, apple.TARGETS[ilp32["target"]][2])
        self.assertEqual(26, apple.TARGETS[lp64["target"]][2])
        self.assertEqual("ILP32", apple.TARGETS[ilp32["target"]][3])
        self.assertEqual("LP64", apple.TARGETS[lp64["target"]][3])
        with self.assertRaisesRegex(ValueError, "minimum/current"):
            apple.expected_os(lp64, "8.0", OS_SELECTION)
        with self.assertRaisesRegex(ValueError, "minimum/current"):
            apple.expected_os(ilp32, "26.0", OS_SELECTION)

    def test_watchos_single_target_bundle_does_not_claim_an_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            apple.record_info_plist(bundle, "example.watch", "watchOS", "8.8.2")
            info = apple.plistlib.loads((bundle / "Info.plist").read_bytes())
            self.assertTrue(info["WKApplication"])
            self.assertTrue(info["WKWatchOnly"])
            self.assertNotIn("WKWatchKitApp", info)
            self.assertEqual("Dyn4kTests", info["CFBundleExecutable"])

    def test_os_roles_require_latest_minimum_patch_and_distinct_current(self):
        minimum, _ = apple.lane_contract(ROOT, IOS_MINIMUM)
        current, _ = apple.lane_contract(ROOT, IOS_MINIMUM.replace(":minimum:", ":current:"))
        with self.assertRaisesRegex(ValueError, "selected|minimum/current"):
            apple.expected_os(minimum, "15.0", OS_SELECTION)
        with self.assertRaisesRegex(ValueError, "selected|minimum/current"):
            apple.expected_os(current, "15.0", OS_SELECTION)
        self.assertEqual("15.8.8", apple.expected_os(minimum, "15.8.8", OS_SELECTION))
        self.assertEqual("26.7", apple.expected_os(current, "26.7", OS_SELECTION))
        with tempfile.TemporaryDirectory() as directory:
            selected = Path(directory) / "roles.json"
            selected.write_bytes(apple.encoded(OS_SELECTION))
            self.assertEqual(OS_SELECTION, apple.load_os_selection(
                selected, apple.sha(selected.read_bytes())))
            altered = json.loads(selected.read_text())
            altered["roles"]["iosArm64"]["minimum"] = "15.0"
            selected.write_bytes(apple.encoded(altered))
            with self.assertRaisesRegex(ValueError, "maintenance patch"):
                apple.load_os_selection(selected, apple.sha(selected.read_bytes()))
            altered["roles"]["iosArm64"] = dict(OS_SELECTION["roles"]["iosArm64"])
            altered["roles"]["iosArm64"]["current"] = "15.8.8"
            selected.write_bytes(apple.encoded(altered))
            with self.assertRaisesRegex(ValueError, "distinct"):
                apple.load_os_selection(selected, apple.sha(selected.read_bytes()))

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
            self.assertEqual("UNAUTHENTICATED", replay["status"])
            self.assertFalse(replay["observed"])
            self.assertEqual(0, replay["selected_cases"])
            receipt = json.loads((archive / "receipt.json").read_text())
            receipt["lane"] = WATCH_ILP32
            (archive / "receipt.json").write_text(json.dumps(receipt))
            changed = apple.independent_gates.archive_digest(archive)
            with self.assertRaisesRegex(ValueError, "misbound|differs"):
                apple.verify(ROOT, candidate, IOS_MINIMUM, archive, changed, {}, "", {})

    def test_unavailable_receipt_cannot_be_forged_into_an_observation(self):
        candidate = "433d2b5a3137b52f8ff07460086c8e4eadb6ef34"
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "archive"
            archive.mkdir()
            receipt = {"schema": 1, "status": "UNAVAILABLE", "candidate_sha": candidate,
                       "lane": IOS_MINIMUM, "reason": "made up", "observed_by":
                       "full_apple_device_consumer.py", "observed_at_ns": 1}
            (archive / "receipt.json").write_bytes(apple.encoded(receipt))
            digest = apple.independent_gates.archive_digest(archive)
            replay = apple.verify(ROOT, candidate, IOS_MINIMUM, archive, digest, {}, "", {})
            self.assertEqual("UNAUTHENTICATED", replay["status"])
            self.assertFalse(replay["observed"])

    def test_archive_rejects_symlink_root_and_hardlinked_receipt(self):
        candidate = "433d2b5a3137b52f8ff07460086c8e4eadb6ef34"
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "archive"
            result = apple.unavailable(archive, candidate, IOS_MINIMUM, "no device")
            alias = Path(directory) / "alias"
            alias.symlink_to(archive, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symbolic"):
                apple.verify(ROOT, candidate, IOS_MINIMUM, alias,
                             result["archive_sha256"], {}, "", {})
            alias.unlink()
            hardlink = Path(directory) / "receipt-link.json"
            hardlink.hardlink_to(archive / "receipt.json")
            with self.assertRaisesRegex(ValueError, "hardlink"):
                apple.verify(ROOT, candidate, IOS_MINIMUM, archive,
                             result["archive_sha256"], {}, "", {})


if __name__ == "__main__":
    unittest.main()
