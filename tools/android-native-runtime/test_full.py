import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import full
from full import (build_task_marker, check_cases, graph_section, parse_list,
                  parse_test_run, source_identity, validate_deployment_output)


class FullCorpusTests(unittest.TestCase):
    @staticmethod
    def guest_records(listing, values=None):
        adb = "/trusted/adb"
        expected = {"avd_name": "dyn4k_api37_play_x64", "api": "37",
                    "fingerprint": full.EXPECTED_FINGERPRINT, "primary_abi": "x86_64",
                    "abi_list": "x86_64,armeabi-v7a", "boot_completed": "1"}
        observed = {**expected, **(values or {})}
        devices = {"command": [adb, "-P", "5038", "devices", "-l"],
                   "exit_code": 0, "stdout": listing, "stderr": b""}
        properties = {prop: {"command": [adb, "-P", "5038", "-s", "emulator-5558",
                                        "shell", "getprop", prop],
                             "exit_code": 0, "stdout": (observed[field] + "\n").encode(),
                             "stderr": b""}
                      for prop, field in full.GUEST_PROPERTIES.items()}
        return adb, devices, properties, expected

    def test_live_guest_selects_only_well_formed_task_device(self):
        listing = (b"List of devices attached\n"
                   b"emulator-5558\tdevice product:sdk model:task transport_id:1\n"
                   b"emulator-5560\tdevice product:sdk model:other transport_id:2\n"
                   b"emulator-5562\toffline\n\n")
        adb, devices, properties, expected = self.guest_records(listing)
        with patch("full.command", side_effect=[devices, *properties.values()]) as mocked:
            guest = full.guest_query(Path("."), adb)
        self.assertEqual(full.guest_values(guest), expected)
        self.assertEqual(mocked.call_count, 1 + len(properties))
        self.assertEqual(mocked.call_args_list[0].args[1], devices["command"])
        for call, record in zip(mocked.call_args_list[1:], properties.values()):
            self.assertEqual(call.args[1], record["command"])

        invalid = {
            "absent": b"List of devices attached\nemulator-5560\tdevice\n",
            "offline": b"List of devices attached\nemulator-5558\toffline\n",
            "unauthorized": b"List of devices attached\nemulator-5558\tunauthorized\n",
            "duplicate": listing + b"emulator-5558\tdevice transport_id:3\n",
            "missing state": b"List of devices attached\nemulator-5558\n",
            "malformed metadata": b"List of devices attached\nemulator-5558\tdevice extra\n",
            "wrong header": b"Devices\nemulator-5558\tdevice\n",
        }
        for name, raw in invalid.items():
            with self.subTest(name=name), patch("full.command", return_value={**devices, "stdout": raw}) as mocked:
                with self.assertRaises(ValueError):
                    full.guest_query(Path("."), adb)
                mocked.assert_called_once_with(Path("."), devices["command"])

    def test_archived_guest_replays_target_selection_and_identity(self):
        listing = (b"List of devices attached\n"
                   b"emulator-5558\tdevice product:sdk transport_id:1\n"
                   b"emulator-5560\tdevice product:sdk transport_id:2\n\n")
        adb, devices, properties, expected = self.guest_records(listing)

        def archive(root, name, raw_listing, changed=None):
            _, device_proc, observations, values = self.guest_records(raw_listing, changed)
            output = root / name
            return {"devices": full.save_command(output, "guest/devices", device_proc),
                    "observations": {prop: full.save_command(output, f"guest/{prop}", proc)
                                     for prop, proc in observations.items()},
                    "values": values}

        with tempfile.TemporaryDirectory() as temporary, patch("full.trusted_adb", return_value=adb):
            root = Path(temporary)
            full.validate_guest(archive(root, "valid", listing), root)
            invalid = {
                "absent": b"List of devices attached\nemulator-5560\tdevice\n",
                "offline": b"List of devices attached\nemulator-5558\toffline\n",
                "unauthorized": b"List of devices attached\nemulator-5558\tunauthorized\n",
                "duplicate": listing + b"emulator-5558\tdevice transport_id:3\n",
                "missing state": b"List of devices attached\nemulator-5558\n",
                "malformed metadata": b"List of devices attached\nemulator-5558\tdevice extra\n",
            }
            for name, raw in invalid.items():
                with self.subTest(name=name), self.assertRaises(ValueError):
                    full.validate_guest(archive(root, name, raw), root)

            wrong_port = archive(root, "wrong-port", listing)
            wrong_port["devices"]["command"][2] = "5037"
            with self.assertRaises(ValueError):
                full.validate_guest(wrong_port, root)
            wrong_serial = archive(root, "wrong-serial", listing)
            wrong_serial["observations"]["ro.build.version.sdk"]["command"][4] = "emulator-5560"
            with self.assertRaises(ValueError):
                full.validate_guest(wrong_serial, root)
            wrong_fingerprint = archive(root, "wrong-fingerprint", listing,
                                        {"fingerprint": "other/image"})
            with self.assertRaises(ValueError):
                full.validate_guest(wrong_fingerprint, root)

    def test_root_and_external_task_markers_match_gradle_output(self):
        self.assertEqual(build_task_marker(":dyn4k-core:linkDebugTestAndroidNativeX64"),
                         "> Task :dyn4k-core:linkDebugTestAndroidNativeX64")
        self.assertEqual(build_task_marker("linkReleaseExecutableAndroidNativeX64"),
                         "> Task :linkReleaseExecutableAndroidNativeX64")

    def test_adb_push_transfer_report_may_be_on_stderr(self):
        validate_deployment_output(b"", b"1 file pushed\n", b"", b"abc  /data/local/tmp/test\n", b"", "abc")
        with self.assertRaises(ValueError):
            validate_deployment_output(b"", b"1 file pushed\n", b"", b"def  /data/local/tmp/test\n", b"", "abc")

    def test_native_listing_and_process_require_exact_cases(self):
        listing = b"p.AlphaTest.\n  first\n  second\np.BetaTest.\n  third\n"
        names = parse_list(listing)
        self.assertEqual(names, ["p.AlphaTest.first", "p.AlphaTest.second", "p.BetaTest.third"])
        self.assertEqual(check_cases(names, set(names)), 3)
        with self.assertRaises(ValueError):
            check_cases(names[:-1], set(names))
        with self.assertRaises(ValueError):
            check_cases(names + names[:1], set(names))
        with self.assertRaises(ValueError):
            parse_list(listing + b"FORGED PASS\n")

        transcript = ("[==========] Running 3 tests from 2 test cases.\n"
                      "[ RUN      ] p.AlphaTest.first\n"
                      "[       OK ] p.AlphaTest.first (0 ms)\n"
                      "[ RUN      ] p.AlphaTest.second\n"
                      "[       OK ] p.AlphaTest.second (1 ms)\n"
                      "[ RUN      ] p.BetaTest.third\n"
                      "[       OK ] p.BetaTest.third (0 ms)\n"
                      "[==========] 3 tests from 2 test cases ran. (1 ms total)\n"
                      "[  PASSED  ] 3 tests.\n").encode()
        self.assertEqual(parse_test_run(transcript), names)
        mutants = (
            transcript.replace(b"[ RUN      ] p.BetaTest.third\n[       OK ] p.BetaTest.third (0 ms)\n", b""),
            transcript.replace(b"[ RUN      ] p.BetaTest.third", b"[ RUN      ] p.AlphaTest.first"),
            transcript + b"[  PASSED  ] 3 tests.\n",
            transcript.replace(b"[       OK ] p.BetaTest.third", b"[  FAILED  ] p.BetaTest.third"),
            transcript.replace(b"[       OK ] p.BetaTest.third", b"[  SKIPPED ] p.BetaTest.third"),
            transcript.replace(b"[  PASSED  ] 3 tests.", b"[  PASSED  ] 2 tests."),
        )
        for mutant in mutants:
            with self.subTest(mutant=mutant[-80:]), self.assertRaises(ValueError):
                parse_test_run(mutant)

    def test_dependency_provider_and_graph_changes_fail(self):
        external = (b"androidNativeX64CompileKlibraries - Compile classpath.\n"
                    b"+--- org.jetbrains.kotlin:kotlin-stdlib:2.4.20\n"
                    b"+--- io.github.rubixhacker:dyn4k-core:0.1.0-alpha.1\n"
                    b"|    \\--- io.github.rubixhacker:dyn4k-core-androidnativex64:0.1.0-alpha.1\n"
                    b"\\--- io.github.rubixhacker:dyn4k:0.1.0-alpha.1\n"
                    b"     \\--- io.github.rubixhacker:dyn4k-androidnativex64:0.1.0-alpha.1\n\n")
        self.assertIn("dyn4k-core", graph_section(external, "consumer"))
        for provider in (b"org.dyn4j:dyn4j:6.0.0", b"project :unapproved", b"example:other:1.0"):
            with self.subTest(provider=provider), self.assertRaises(ValueError):
                graph_section(external.replace(b"\n\n", b"\n+--- " + provider + b"\n\n"), "consumer")

    def test_source_checkout_drift_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            source = root / "source.kt"
            source.write_text("one\n")
            subprocess.run(["git", "-C", str(root), "add", "source.kt"], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=Test", "-c",
                            "user.email=test@example.invalid", "commit", "-q", "-m", "fixture"], check=True)
            identity = source_identity(root)
            self.assertEqual(len(identity[0]), 40)
            source.write_text("two\n")
            with self.assertRaisesRegex(ValueError, "not clean"):
                source_identity(root)
            source.write_text("one\n")
            (root / "extra.kt").write_text("extra\n")
            with self.assertRaisesRegex(ValueError, "not clean"):
                source_identity(root)


if __name__ == "__main__":
    unittest.main()
