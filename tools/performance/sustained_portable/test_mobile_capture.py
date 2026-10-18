import unittest
from unittest.mock import patch

import mobile_capture


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

    def test_simulator_console_header_is_removed_only_when_exact(self):
        self.assertEqual(b"DYN4K\tCOMPLETE\tabc\n",
                         mobile_capture.simulator_protocol_bytes(
                             b"io.github.rubixhacker.dyn4k.performance.iosx64: 123\nDYN4K\tCOMPLETE\tabc\n",
                             "io.github.rubixhacker.dyn4k.performance.iosx64", 123))

    def test_process_image_is_required_and_exact(self):
        for observed in (None, "0" * 64):
            with self.subTest(observed=observed), self.assertRaises(ValueError):
                mobile_capture.validate_process_image(observed, "1" * 64)

    def test_receipt_rejects_missing_completion(self):
        with self.assertRaisesRegex(ValueError, "completion"):
            mobile_capture.validate_completion(b"DYN4K\tRUN\tdirect_kotlin\n", "abc")


if __name__ == "__main__":
    unittest.main()
