import argparse
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run
import run_full
import run_optimized


class EmulatorSerialTest(unittest.TestCase):
    def test_default_and_selected_adb_route(self):
        sdk = Path("/sdk")
        self.assertEqual(run.adb_for_serial(sdk, "emulator-5558"),
                         ["/sdk/platform-tools/adb", "-P", "5038", "-s", "emulator-5558"])
        self.assertEqual(run.adb_for_serial(sdk, "emulator-5562")[-2:],
                         ["-s", "emulator-5562"])

    def test_rejects_unselected_and_malformed_serial_before_adb(self):
        for serial in ("emulator-5560", "device-5562", "emulator-5563", "emulator-5562 ",
                       "emulator-5562;id", "", "emulator-65562"):
            with self.subTest(serial=serial), self.assertRaises(argparse.ArgumentTypeError):
                run.adb_for_serial(Path("/sdk"), serial)

    def test_all_installed_runners_reject_bad_serial_before_inputs(self):
        for module, extra in ((run, ["--build-type", "debug"]),
                              (run_optimized, ["--provider-graph", "/missing", "--build-type", "debug",
                                               "--expected-api", "37"]),
                              (run_full, ["--build-type", "debug", "--expected-api", "37",
                                          "--provider-artifacts", "/missing", "--build-receipt", "/missing"])):
            error = io.StringIO()
            with self.subTest(module=module.__name__), contextlib.redirect_stderr(error), patch("sys.argv", [module.__name__,
                    "--prepared", "/missing", "--output", "/missing", *extra,
                    "--emulator-serial", "device-5562"]), self.assertRaises(SystemExit) as failure:
                module.main()
            self.assertEqual(failure.exception.code, 2)
            self.assertIn("Android emulator serial must", error.getvalue())

    def test_all_installed_runners_accept_default_and_selected_serial(self):
        for module, extra in ((run, ["--build-type", "debug"]),
                              (run_optimized, ["--provider-graph", "/missing", "--build-type", "debug",
                                               "--expected-api", "37"]),
                              (run_full, ["--build-type", "debug", "--expected-api", "37",
                                          "--provider-artifacts", "/missing", "--build-receipt", "/missing"])):
            for serial_args in ([], ["--emulator-serial", "emulator-5562"]):
                with self.subTest(module=module.__name__, serial_args=serial_args), patch(
                        "sys.argv", [module.__name__, "--prepared", "/missing", "--output",
                                     "/missing", *extra, *serial_args]), self.assertRaises(FileNotFoundError):
                    module.main()

    def test_lane_result_binds_selected_serial_before_install(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            apk = root / "app.apk"
            apk.write_bytes(b"app")
            prepared = {"candidate_commit": "candidate", "build_jdk": "jdk",
                        "root_build": {}, "staged": {}, "baseline_jar": {},
                        "staged_roots": {}, "consumer_sources": {},
                        "generated_consumer_sources": {}, "portable_jar": {}}
            with patch.object(run, "apk_path", return_value=apk), patch.object(
                    run, "verify_consumer_sources", side_effect=ValueError("stop before install")), patch.object(
                    run, "command", return_value="") as command:
                result = run.run_lane(root, prepared, set(), "candidate", "debug", "37", root,
                                      run.adb_for_serial(root, "emulator-5562"), apk, "hash")
            self.assertEqual(result["emulator_serial"], "emulator-5562")
            self.assertEqual(json.loads((root / "candidate-debug/result.json").read_text())[
                "emulator_serial"], "emulator-5562")
            self.assertNotIn("install", str(command.call_args_list))


if __name__ == "__main__":
    unittest.main()
