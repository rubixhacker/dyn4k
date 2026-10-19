import json
import io
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import mobile_capture
import test_capture


class MobileCaptureAdverseTest(unittest.TestCase):
    def test_simulator_xcode_pin_accepts_26_5_and_rejects_26_4_1(self):
        self.assertEqual("Xcode 26.5\nBuild version 17F42\n",
                         mobile_capture.validate_xcode_version(
                             "Xcode 26.5\nBuild version 17F42\n"))
        with self.assertRaisesRegex(ValueError, "pinned 26.5"):
            mobile_capture.validate_xcode_version("Xcode 26.4.1\nBuild version 17E303\n")

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
                b"DYN4K\tCOMPLETE\tabc\n",
                b"io.github.rubixhacker.dyn4k.performance.iosx64: 123\n",
                "io.github.rubixhacker.dyn4k.performance.iosx64", 124)

    def test_simulator_below_policy_floor_is_rejected(self):
        with patch.object(mobile_capture.platform, "system", return_value="Darwin"), \
             patch.object(mobile_capture.platform, "machine", return_value="arm64"):
            with self.assertRaisesRegex(ValueError, "minimum"):
                mobile_capture.validate_simulator(
                    "iosSimulatorArm64", "device", {
                        "devices": {"com.apple.CoreSimulator.SimRuntime.iOS-14-9": [
                            {"udid": "device", "state": "Booted", "isAvailable": True}]}})

    def test_complete_simulator_protocol_requires_separate_os_receipt(self):
        fixture = test_capture.PortableCaptureTest()
        fixture.setUpClass()
        raw = fixture.protocol()
        fixture.validate(raw)
        with self.assertRaisesRegex(ValueError, "launch receipt"):
            mobile_capture.simulator_protocol_bytes(
                raw, b"", "io.github.rubixhacker.dyn4k.performance.iosx64", 123)

    def test_separate_os_receipt_accepts_exact_pid_and_protocol(self):
        fixture = test_capture.PortableCaptureTest()
        fixture.setUpClass()
        raw = fixture.protocol()
        self.assertEqual(mobile_capture.simulator_protocol_bytes(
            raw, b"io.github.rubixhacker.dyn4k.performance.iosx64: 123\n",
            "io.github.rubixhacker.dyn4k.performance.iosx64", 123), raw)

    def test_simulator_rejects_spoofed_or_ambiguous_os_receipt(self):
        bundle = "io.github.rubixhacker.dyn4k.performance.iosx64"
        for receipt in (b"other.bundle: 123\n", b"other.bundle: 123\n" + bundle.encode() + b": 123\n",
                        bundle.encode() + b": 123\n" + bundle.encode() + b": 124\n",
                        b"DYN4K\tCOMPLETE\tabc\n"):
            with self.subTest(receipt=receipt), self.assertRaisesRegex(ValueError, "launch receipt"):
                mobile_capture.simulator_protocol_bytes(b"DYN4K\tCOMPLETE\tabc\n",
                                                        receipt, bundle, 123)

    def test_app_stdout_cannot_spoof_os_pid_line(self):
        with self.assertRaisesRegex(ValueError, "producer stdout"):
            mobile_capture.simulator_protocol_bytes(
                b"io.github.rubixhacker.dyn4k.performance.iosx64: 123\nDYN4K\tCOMPLETE\tabc\n",
                b"io.github.rubixhacker.dyn4k.performance.iosx64: 123\n",
                "io.github.rubixhacker.dyn4k.performance.iosx64", 123)

    def test_simulator_requires_redirected_output_capability(self):
        with self.assertRaisesRegex(ValueError, "redirection"):
            mobile_capture.validate_simctl_launch_help("Usage: simctl launch [--console]")
        with self.assertRaisesRegex(ValueError, "redirection"):
            mobile_capture.validate_simctl_launch_help("--stdout=<path> --stderr=<path>")
        mobile_capture.validate_simctl_launch_help(
            "--stdout=<path> Redirect the application's standard output to a file.\n"
            "--stderr=<path> Redirect the application's standard error to a file.")

    def test_simulator_adapter_separates_os_receipt_and_app_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected = root / "selected.app"
            installed = root / "installed.app"
            data = root / "data"
            archive = root / "archive"
            for path in (selected, installed, data, archive):
                path.mkdir()
            for app in (selected, installed):
                (app / "Dyn4kPerformance").write_bytes(b"same executable")
                (app / "Info.plist").write_bytes(b"same package")
            bundle = "io.github.rubixhacker.dyn4k.performance.iosx64"
            launch_raw = (bundle + ": 123\n").encode()
            app_raw = b"DYN4K\tCOMPLETE\tnonce\n"
            args = SimpleNamespace(udid="selected-udid", target="iosX64",
                                   archive=archive, timeout=1)
            inventory = {"app_bundle": str(selected), "bundle_id": bundle,
                         "linked_sha256": mobile_capture.capture.digest(selected / "Dyn4kPerformance"),
                         "bundle_sha256": mobile_capture.validate_installed_bundle(selected, installed)}
            launches = []

            def setup(_archive, label, argv, **_kwargs):
                if label == "apple-xcode":
                    output = "Xcode 26.5\nBuild version 17F42\n"
                elif label == "apple-device-list":
                    output = '{"devices": {}}'
                elif label == "apple-architecture":
                    output = "x86_64\n"
                elif label == "apple-launch-help":
                    output = ("--stdout=<path> Redirect the application's standard output to a file.\n"
                              "--stderr=<path> Redirect the application's standard error to a file.\n")
                elif label == "apple-container":
                    output = str(installed) + "\n"
                elif label == "apple-data-container":
                    output = str(data) + "\n"
                elif label == "apple-launch":
                    launches.append(argv)
                    (archive / "setup").mkdir()
                    (archive / "setup/apple-launch.stdout.bin").write_bytes(launch_raw)
                    (archive / "setup/apple-launch.stderr.bin").write_bytes(b"")
                    Path(next(arg.split("=", 1)[1] for arg in argv if arg.startswith("--stdout="))).write_bytes(app_raw)
                    Path(next(arg.split("=", 1)[1] for arg in argv if arg.startswith("--stderr="))).write_bytes(b"app err\x00")
                    output = launch_raw.decode()
                else:
                    output = ""
                return subprocess.CompletedProcess(argv, 0, output, "")

            installed_image = installed / "Dyn4kPerformance"
            identity = mobile_capture.apple_file_identity(installed_image)
            with patch.object(mobile_capture, "setup_command", side_effect=setup), \
                 patch.object(mobile_capture, "validate_simulator", return_value={"udid": args.udid}), \
                 patch.object(mobile_capture, "apple_process_path",
                              side_effect=[installed_image, installed_image, installed_image, None]), \
                 patch.object(mobile_capture, "apple_process_vnode",
                              return_value={"pid": 123, "path": str(installed_image),
                                            "device": identity["device"], "inode": identity["inode"],
                                            "size": identity["size"]}), \
                 patch.object(mobile_capture.os, "kill", side_effect=ProcessLookupError):
                stdout, stderr, process = mobile_capture.run_simulator(
                    args, inventory, selected / "Dyn4kPerformance", ["fixture"], "nonce")
            self.assertEqual(stdout, app_raw)
            self.assertEqual(stderr, b"app err\x00")
            self.assertEqual((archive / "stdout.bin").read_bytes(), app_raw)
            self.assertEqual((archive / "stderr.bin").read_bytes(), stderr)
            self.assertEqual((archive / "setup/apple-launch.stdout.bin").read_bytes(), launch_raw)
            self.assertEqual(process["launch"]["pid"], 123)
            self.assertEqual(process["image"]["sha256"], inventory["linked_sha256"])
            self.assertEqual(process["installed_image_size"], identity["size"])
            self.assertEqual(len(launches), 1)
            self.assertNotIn("--console", launches[0])
            self.assertTrue(any(arg.startswith("--stdout=") for arg in launches[0]))
            self.assertTrue(any(arg.startswith("--stderr=") for arg in launches[0]))

    def test_simulator_rejects_executable_replaced_during_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected, installed, data, archive = (root / name for name in
                                                  ("selected.app", "installed.app", "data", "archive"))
            for path in (selected, installed, data, archive):
                path.mkdir()
            for app in (selected, installed):
                (app / "Dyn4kPerformance").write_bytes(b"selected image")
                (app / "Info.plist").write_bytes(b"selected package")
            bundle = "io.github.rubixhacker.dyn4k.performance.iosx64"
            selected_sha = mobile_capture.capture.digest(selected / "Dyn4kPerformance")
            inventory = {"app_bundle": str(selected), "bundle_id": bundle,
                         "linked_sha256": selected_sha,
                         "bundle_sha256": mobile_capture.validate_installed_bundle(selected, installed)}
            args = SimpleNamespace(udid="selected-udid", target="iosX64",
                                   archive=archive, timeout=1)

            def setup(_archive, label, argv, **_kwargs):
                if label == "apple-xcode":
                    output = "Xcode 26.5\nBuild version 17F42\n"
                elif label == "apple-device-list":
                    output = '{"devices": {}}'
                elif label == "apple-architecture":
                    output = "x86_64\n"
                elif label == "apple-launch-help":
                    output = ("--stdout=<path> Redirect the application's standard output to a file.\n"
                              "--stderr=<path> Redirect the application's standard error to a file.\n")
                elif label == "apple-container":
                    output = str(installed) + "\n"
                elif label == "apple-data-container":
                    output = str(data) + "\n"
                elif label == "apple-launch":
                    (installed / "Dyn4kPerformance").write_bytes(b"replaced image")
                    (archive / "setup").mkdir()
                    (archive / "setup/apple-launch.stdout.bin").write_bytes((bundle + ": 123\n").encode())
                    (archive / "setup/apple-launch.stderr.bin").write_bytes(b"")
                    Path(next(arg.split("=", 1)[1] for arg in argv if arg.startswith("--stdout="))).write_bytes(
                        b"DYN4K\tCOMPLETE\tnonce\n")
                    Path(next(arg.split("=", 1)[1] for arg in argv if arg.startswith("--stderr="))).write_bytes(b"app err")
                    output = bundle + ": 123\n"
                else:
                    output = ""
                return subprocess.CompletedProcess(argv, 0, output, "")

            with patch.object(mobile_capture, "setup_command", side_effect=setup), \
                 patch.object(mobile_capture, "validate_simulator", return_value={"udid": args.udid}), \
                 patch.object(mobile_capture, "apple_process_path",
                              return_value=installed / "Dyn4kPerformance"), \
                 patch.object(mobile_capture, "apple_process_vnode",
                              return_value={"pid": 123, "path": str(installed / "Dyn4kPerformance"),
                                            "device": (installed / "Dyn4kPerformance").stat().st_dev,
                                            "inode": (installed / "Dyn4kPerformance").stat().st_ino,
                                            "size": len(b"selected image")}):
                with self.assertRaisesRegex(ValueError, "selected|package|image"):
                    mobile_capture.run_simulator(
                        args, inventory, selected / "Dyn4kPerformance", ["fixture"], "nonce")
            self.assertEqual((archive / "stdout.bin").read_bytes(), b"DYN4K\tCOMPLETE\tnonce\n")
            self.assertEqual((archive / "stderr.bin").read_bytes(), b"app err")
            self.assertNotEqual(mobile_capture.capture.digest(installed / "Dyn4kPerformance"), selected_sha)

    def test_installed_bundle_rejects_nonexecutable_package_substitution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected = root / "selected.app"
            installed = root / "installed.app"
            selected.mkdir()
            installed.mkdir()
            for app in (selected, installed):
                (app / "Dyn4kPerformance").write_bytes(b"same executable")
            (selected / "Info.plist").write_bytes(b"selected metadata")
            (installed / "Info.plist").write_bytes(b"substituted metadata")
            with self.assertRaisesRegex(ValueError, "package bytes"):
                mobile_capture.validate_installed_bundle(selected, installed)

    def test_apple_process_vnode_requires_one_exact_kernel_text_mapping(self):
        executable = Path("/private/tmp/installed.app/Dyn4kPerformance")
        good = (b"p123\0\nftxt\0D0x10\0i42\0s14\0n" +
                str(executable).encode() + b"\0\n")
        self.assertEqual(mobile_capture.parse_apple_process_vnode(good, 123, executable),
                         {"pid": 123, "path": str(executable), "device": 16,
                          "inode": 42, "size": 14})
        for raw in (good.replace(b"p123", b"p124"), good.replace(b"ftxt", b"f3r"),
                    good.replace(b"i42", b""), good.replace(b"D0x10", b""),
                    good.replace(b"s14", b""), good.replace(b"i42", b"i0"),
                    good + good, good.replace(b"Dyn4kPerformance", b"Other")):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                mobile_capture.parse_apple_process_vnode(raw, 123, executable)

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
            self.assertIn("launch receipt", result["error"])
            self.assertEqual((archive / "stdout.bin").read_bytes(), raw)

    def test_simulator_run_validates_full_fixture_with_separate_os_receipt(self):
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
            package = {"Dyn4kPerformance": mobile_capture.capture.digest(executable)}
            inventory = {"source_sha": fixture.source, "producer_tree": fixture.producer_tree,
                         "build": "development", "linked_sha256": mobile_capture.capture.digest(executable),
                         "bundle_sha256": package}
            bundle = "io.github.rubixhacker.dyn4k.performance.iosx64"
            launch_raw = (bundle + ": 123\n").encode()
            process = {"started_ns": 1, "ended_ns": 2, "bundle_id": bundle,
                       "image": {"pid": 123, "sha256": mobile_capture.capture.digest(executable),
                                 "size": executable.stat().st_size, "device": 1, "inode": 2,
                                 "method": "simctl-launch-pid/proc_pidpath/lsof-text-vnode"},
                       "launch": {"pid": 123, "method": "simctl-redirected-files",
                                  "stdout_sha256": mobile_capture.hashlib.sha256(launch_raw).hexdigest()},
                       "output": {"stdout_sha256": mobile_capture.hashlib.sha256(raw).hexdigest(),
                                  "stderr_sha256": mobile_capture.hashlib.sha256(b"").hexdigest()},
                       "linked_sha256": inventory["linked_sha256"],
                       "installed_image_sha256": inventory["linked_sha256"],
                       "installed_image_size": executable.stat().st_size,
                       "installed_bundle_sha256": package}

            def simulator(*_unused):
                (args.archive / "setup").mkdir()
                (args.archive / "setup/apple-launch.stdout.bin").write_bytes(launch_raw)
                return raw, b"", process

            with patch.object(mobile_capture.capture, "required_file", return_value=inventory_path), \
                 patch.object(mobile_capture, "validate_inventory",
                              return_value=(inventory, executable, artifacts)), \
                 patch.object(mobile_capture.secrets, "token_hex", return_value=fixture.nonce), \
                 patch.object(mobile_capture, "run_simulator", side_effect=simulator):
                self.assertEqual(mobile_capture.run(args), 0)
            result = json.loads((archive / "result.json").read_text())
            self.assertEqual(result["protocol"], "valid")
            self.assertEqual(result["qualification"], "unpassed")
            self.assertEqual(result["step_count"], 1)
            args.archive = root / "forged-image"
            process["image"]["sha256"] = "0" * 64
            with patch.object(mobile_capture.capture, "required_file", return_value=inventory_path), \
                 patch.object(mobile_capture, "validate_inventory",
                              return_value=(inventory, executable, artifacts)), \
                 patch.object(mobile_capture.secrets, "token_hex", return_value=fixture.nonce), \
                 patch.object(mobile_capture, "run_simulator", side_effect=simulator):
                self.assertEqual(mobile_capture.run(args), 1)
            forged = json.loads((args.archive / "result.json").read_text())
            self.assertNotIn("protocol", forged)
            self.assertIn("installed package or link", forged["error"])

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

    def test_android_cleanup_timeout_keeps_completed_producer_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive"
            archive.mkdir()
            harness = root / "native"
            harness.write_bytes(b"selected executable")
            adb = root / "adb"
            adb.write_bytes(b"adb")
            digest = mobile_capture.capture.digest(harness)
            args = SimpleNamespace(archive=archive, adb=str(adb), adb_port=5049,
                                   serial="task-native", target="androidNativeX64", timeout=1)
            producer = Mock()
            producer.stdout = io.BytesIO(b"DYN4K_PID:123\n")
            producer.poll.return_value = None
            producer.communicate.return_value = (b"DYN4K\tCOMPLETE\tnonce\n", b"binary\x00err")
            producer.returncode = 0
            real_setup = mobile_capture.setup_command

            def setup(archive_path, label, argv, **kwargs):
                if label == "android-remove":
                    return real_setup(archive_path, label, argv, **kwargs)
                if label == "android-devices":
                    output = "List of devices attached\ntask-native device\n"
                elif label.startswith("android-prop-"):
                    output = {"ro.product.cpu.abi": "x86_64", "ro.build.version.sdk": "37",
                              "ro.build.fingerprint": "fingerprint", "sys.boot_completed": "1"}[
                                  label.removeprefix("android-prop-")]
                elif label in ("android-deployed-sha", "android-process-sha"):
                    output = digest + "  native\n"
                elif label.startswith("android-process-path-"):
                    output = "/data/local/tmp/dyn4k-performance-nonce\n"
                else:
                    output = ""
                return subprocess.CompletedProcess(argv, 0, output, "")

            with patch.object(mobile_capture.capture, "required_file", return_value=adb), \
                 patch.object(mobile_capture, "setup_command", side_effect=setup), \
                 patch.object(mobile_capture.subprocess, "Popen", return_value=producer), \
                 patch.object(mobile_capture.subprocess, "run",
                              side_effect=subprocess.TimeoutExpired(["adb", "rm"], 1,
                                                                    output=b"remove out",
                                                                    stderr=b"remove err")), \
                 patch.object(mobile_capture.select, "select",
                              return_value=([producer.stdout], [], [])):
                stdout, stderr, receipt = mobile_capture.run_android(
                    args, {}, harness, ["fixture"], "nonce")
            self.assertEqual(stdout, b"DYN4K\tCOMPLETE\tnonce\n")
            self.assertEqual(stderr, b"binary\x00err")
            self.assertEqual((archive / "stdout.bin").read_bytes(), stdout)
            self.assertEqual((archive / "stderr.bin").read_bytes(), stderr)
            self.assertEqual((archive / "setup/android-remove.stdout.bin").read_bytes(), b"remove out")
            self.assertEqual((archive / "setup/android-remove.stderr.bin").read_bytes(), b"remove err")
            self.assertTrue(json.loads((archive / "setup/android-remove.json").read_text())["timed_out"])
            self.assertEqual(receipt["cleanup"]["status"], "failed")
            self.assertEqual(json.loads((archive / "cleanup.json").read_text())["status"], "failed")

    def test_process_image_is_required_and_exact(self):
        for observed in (None, "0" * 64):
            with self.subTest(observed=observed), self.assertRaises(ValueError):
                mobile_capture.validate_process_image(observed, "1" * 64)

    def test_apple_launch_pid_must_resolve_to_installed_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installed = root / "Dyn4kPerformance"
            other = root / "other"
            installed.write_bytes(b"installed")
            other.write_bytes(b"substituted")
            expected = mobile_capture.capture.digest(installed)
            size = installed.stat().st_size
            before = mobile_capture.apple_file_identity(installed)
            with patch.object(mobile_capture, "apple_process_path", return_value=other):
                with self.assertRaisesRegex(ValueError, "launch PID"):
                    mobile_capture.apple_process_image(installed, 123, expected, size, before, root)
            with patch.object(mobile_capture, "apple_process_path", return_value=installed), \
                 patch.object(mobile_capture, "apple_process_vnode",
                              return_value={"pid": 123, "path": str(installed),
                                            "device": before["device"], "inode": before["inode"],
                                            "size": size}):
                image = mobile_capture.apple_process_image(installed, 123, expected, size, before, root)
            self.assertEqual(image["sha256"], mobile_capture.capture.digest(installed))
            self.assertEqual(image["pid"], 123)

    def test_apple_process_image_rejects_same_path_replaced_bytes_and_vnode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installed = root / "Dyn4kPerformance"
            installed.write_bytes(b"selected image")
            expected = mobile_capture.capture.digest(installed)
            size = installed.stat().st_size
            before = mobile_capture.apple_file_identity(installed)
            installed.write_bytes(b"replaced image")
            with patch.object(mobile_capture, "apple_process_path", return_value=installed), \
                 patch.object(mobile_capture, "apple_process_vnode",
                              return_value={"pid": 123, "path": str(installed),
                                            "device": before["device"], "inode": before["inode"],
                                            "size": size}):
                with self.assertRaisesRegex(ValueError, "selected|changed"):
                    mobile_capture.apple_process_image(installed, 123, expected, size, before, root)
            installed.write_bytes(b"selected image")
            current = mobile_capture.apple_file_identity(installed)
            for field in ("device", "inode", "size"):
                vnode = {"pid": 123, "path": str(installed),
                         "device": current["device"], "inode": current["inode"], "size": size}
                vnode[field] += 1
                with self.subTest(field=field), \
                     patch.object(mobile_capture, "apple_process_path", return_value=installed), \
                     patch.object(mobile_capture, "apple_process_vnode", return_value=vnode):
                    with self.assertRaisesRegex(ValueError, "vnode"):
                        mobile_capture.apple_process_image(installed, 123, expected, size, current, root)

    def test_apple_process_image_rejects_exit_before_observation_ends(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installed = root / "Dyn4kPerformance"
            installed.write_bytes(b"selected image")
            before = mobile_capture.apple_file_identity(installed)
            with patch.object(mobile_capture, "apple_process_path", side_effect=[installed, None]), \
                 patch.object(mobile_capture, "apple_process_vnode",
                              return_value={"pid": 123, "path": str(installed),
                                            "device": before["device"], "inode": before["inode"],
                                            "size": before["size"]}):
                with self.assertRaisesRegex(ValueError, "exited"):
                    mobile_capture.apple_process_image(
                        installed, 123, mobile_capture.capture.digest(installed),
                        before["size"], before, root)

    def test_receipt_rejects_missing_completion(self):
        with self.assertRaisesRegex(ValueError, "completion"):
            mobile_capture.validate_completion(b"DYN4K\tRUN\tdirect_kotlin\n", "abc")


if __name__ == "__main__":
    unittest.main()
