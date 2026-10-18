import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import mobile_capture
import test_capture


class MobileCaptureAdverseTest(unittest.TestCase):
    def test_adb_route_rejects_shared_owner_lease(self):
        for port, serial in ((5038, "task-device"), (5049, "emulator-5558"),
                             (5037, "task-device")):
            with self.subTest(port=port, serial=serial), self.assertRaises(ValueError):
                mobile_capture.validate_adb_route(port, serial)

    def test_adb_route_requires_explicit_isolated_serial(self):
        self.assertEqual((5049, "emulator-5570"),
                         mobile_capture.validate_adb_route(5049, "emulator-5570"))

    def test_target_abi_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "ABI"):
            mobile_capture.validate_android_identity(
                "androidNativeArm64", {"ro.product.cpu.abi": "x86_64",
                                       "ro.build.version.sdk": "37",
                                       "sys.boot_completed": "1"})

    def test_selected_simulator_must_match_target_family_and_architecture(self):
        with patch.object(mobile_capture.platform, "system", return_value="Darwin"), \
             patch.object(mobile_capture.platform, "machine", return_value="arm64"):
            with self.assertRaisesRegex(ValueError, "simulator"):
                mobile_capture.validate_simulator(
                    "iosSimulatorArm64", "wrong", {
                        "devices": {"com.apple.CoreSimulator.SimRuntime.tvOS-26-0": [
                            {"udid": "wrong", "state": "Booted", "isAvailable": True,
                             "deviceTypeIdentifier": "com.apple.CoreSimulator.SimDeviceType.Apple-TV"}]}})

    def test_simulator_console_header_pid_must_match_observed_image(self):
        with self.assertRaisesRegex(ValueError, "PID"):
            mobile_capture.simulator_protocol_bytes(
                b"io.github.rubixhacker.dyn4k.performance.iosx64: 123\nDYN4K\tCOMPLETE\tabc\n",
                "io.github.rubixhacker.dyn4k.performance.iosx64", 124)

    def test_simulator_below_policy_floor_is_rejected(self):
        with patch.object(mobile_capture.platform, "system", return_value="Darwin"), \
             patch.object(mobile_capture.platform, "machine", return_value="arm64"):
            with self.assertRaisesRegex(ValueError, "minimum"):
                mobile_capture.validate_simulator(
                    "iosSimulatorArm64", "device", {
                        "devices": {"com.apple.CoreSimulator.SimRuntime.iOS-14-9": [
                            {"udid": "device", "state": "Booted", "isAvailable": True}]}})

    def test_complete_simulator_protocol_without_header_cannot_pass(self):
        fixture = test_capture.PortableCaptureTest()
        fixture.setUpClass()
        raw = fixture.protocol()
        fixture.validate(raw)
        with self.assertRaisesRegex(ValueError, "PID header"):
            mobile_capture.simulator_protocol_bytes(
                raw, "io.github.rubixhacker.dyn4k.performance.iosx64", 123)

    def test_matching_simulator_header_still_needs_mac_origin_control(self):
        with self.assertRaisesRegex(ValueError, "Mac control"):
            mobile_capture.simulator_protocol_bytes(
                b"io.github.rubixhacker.dyn4k.performance.iosx64: 123\nDYN4K\tCOMPLETE\tabc\n",
                "io.github.rubixhacker.dyn4k.performance.iosx64", 123)

    def test_malformed_simulator_header_cannot_be_treated_as_app_output(self):
        with self.assertRaisesRegex(ValueError, "PID header"):
            mobile_capture.simulator_protocol_bytes(
                b"other.bundle: 123\nDYN4K\tCOMPLETE\tabc\n",
                "io.github.rubixhacker.dyn4k.performance.iosx64", 123)

    def test_simulator_run_keeps_full_valid_stream_unpassed(self):
        fixture = test_capture.PortableCaptureTest()
        fixture.setUpClass()
        raw = fixture.protocol()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inventory_path = root / "inventory.json"
            inventory_path.write_text("{}")
            executable = root / "Dyn4kPerformance"
            executable.write_bytes(b"test image")
            archive = root / "capture"
            args = SimpleNamespace(archive=archive, inventory=inventory_path,
                                   target="iosX64", build="development",
                                   scenario=fixture.scenario["id"], steps=1, warmup=1)
            artifacts = {"dyn4k-core": {"sha256": fixture.hashes["core"]},
                         "dyn4k": {"sha256": fixture.hashes["kotlin"]}}
            inventory = {"source_sha": fixture.source,
                         "producer_tree": fixture.producer_tree,
                         "build": "development"}
            process = {"started_ns": 1, "ended_ns": 2,
                       "bundle_id": "io.github.rubixhacker.dyn4k.performance.iosx64",
                       "image": {"pid": 123, "sha256": mobile_capture.capture.digest(executable)}}
            with patch.object(mobile_capture.capture, "required_file", return_value=inventory_path), \
                 patch.object(mobile_capture, "validate_inventory",
                              return_value=(inventory, executable, artifacts)), \
                 patch.object(mobile_capture.secrets, "token_hex", return_value=fixture.nonce), \
                 patch.object(mobile_capture, "run_simulator", return_value=(raw, b"", process)):
                self.assertEqual(mobile_capture.run(args), 1)
            result = json.loads((archive / "result.json").read_text())
            self.assertEqual(result["qualification"], "unpassed")
            self.assertNotIn("protocol", result)
            self.assertIn("PID header", result["error"])
            self.assertEqual((archive / "stdout.bin").read_bytes(), raw)

    def test_setup_command_preserves_binary_output_and_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory)
            argv = [sys.executable, "-B", "-c",
                    "import sys;sys.stdout.buffer.write(b'out\\x00');"
                    "sys.stderr.buffer.write(b'err\\xff');sys.exit(7)"]
            with self.assertRaisesRegex(ValueError, r"command failed \(7\)"):
                mobile_capture.setup_command(archive, "android-push", argv)
            self.assertEqual((archive / "setup/android-push.stdout.bin").read_bytes(), b"out\x00")
            self.assertEqual((archive / "setup/android-push.stderr.bin").read_bytes(), b"err\xff")
            record = json.loads((archive / "setup/android-push.json").read_text())
            self.assertEqual(record["argv"], argv)
            self.assertEqual(record["exit_code"], 7)
            self.assertGreater(record["ended_ns"], record["started_ns"])

    def test_setup_command_preserves_partial_timeout_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory)
            argv = ["fake-install"]
            with patch.object(mobile_capture.subprocess, "run",
                              side_effect=subprocess.TimeoutExpired(argv, 1,
                                                                    output=b"partial out",
                                                                    stderr=b"partial err")):
                with self.assertRaisesRegex(ValueError, "timed out"):
                    mobile_capture.setup_command(archive, "apple-install", argv, timeout=1)
            self.assertEqual((archive / "setup/apple-install.stdout.bin").read_bytes(), b"partial out")
            self.assertEqual((archive / "setup/apple-install.stderr.bin").read_bytes(), b"partial err")
            record = json.loads((archive / "setup/apple-install.json").read_text())
            self.assertTrue(record["timed_out"])

    def test_setup_command_records_success_and_missing_tool(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory)
            argv = [sys.executable, "-B", "-c", "import sys;sys.stdout.write('ready')"]
            self.assertEqual(mobile_capture.setup_command(archive, "apple-xcode", argv).stdout,
                             "ready")
            self.assertEqual((archive / "setup/apple-xcode.stdout.bin").read_bytes(), b"ready")
            self.assertEqual(json.loads((archive / "setup/apple-xcode.json").read_text())["exit_code"], 0)
            missing = [str(archive / "missing-tool")]
            with self.assertRaisesRegex(ValueError, "could not launch"):
                mobile_capture.setup_command(archive, "android-devices", missing)
            record = json.loads((archive / "setup/android-devices.json").read_text())
            self.assertIsNone(record["exit_code"])
            self.assertTrue(record["launch_error"])
            self.assertEqual((archive / "setup/android-devices.stderr.bin").read_bytes(), b"")

    def test_process_image_is_required_and_exact(self):
        for observed in (None, "0" * 64):
            with self.subTest(observed=observed), self.assertRaises(ValueError):
                mobile_capture.validate_process_image(observed, "1" * 64)

    def test_receipt_rejects_missing_completion(self):
        with self.assertRaisesRegex(ValueError, "completion"):
            mobile_capture.validate_completion(b"DYN4K\tRUN\tdirect_kotlin\n", "abc")


if __name__ == "__main__":
    unittest.main()
