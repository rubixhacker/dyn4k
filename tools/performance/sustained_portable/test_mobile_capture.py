import copy
import json
import io
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import mobile_capture
import test_capture


def apple_derivation(linked, harness, target="iosX64", build="development"):
    app = harness.parent
    simulator = target in mobile_capture.APPLE_SIMULATORS
    linked_sha = mobile_capture.capture.digest(linked)
    return {
        "format": "portable-apple-image-derivation-v1", "target": target, "build": build,
        "linked_path": str(linked), "linked_sha256": linked_sha,
        "linked_size": linked.stat().st_size,
        "copied_sha256": linked_sha, "copied_size": linked.stat().st_size,
        "package_path": str(app),
        "packaged_sha256": mobile_capture.capture.digest(harness),
        "packaged_size": harness.stat().st_size,
        "signing": "ad_hoc" if simulator else "none",
        "signing_command": (["codesign", "--force", "--sign", "-", "--timestamp=none", str(app)]
                            if simulator else None),
        "verification_command": ["codesign", "--verify", str(app)] if simulator else None,
        "codesign_verified": simulator,
    }


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

    def test_simulator_adapter_accepts_signed_image_distinct_from_raw_link(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected = root / "selected.app"
            installed = root / "installed.app"
            data = root / "data"
            archive = root / "archive"
            for path in (selected, installed, data, archive):
                path.mkdir()
            for app in (selected, installed):
                (app / "Dyn4kPerformance").write_bytes(b"signed executable")
                (app / "Info.plist").write_bytes(b"same package")
            linked = root / "raw-linked.kexe"
            linked.write_bytes(b"raw linked executable")
            bundle = "io.github.rubixhacker.dyn4k.performance.iosx64"
            launch_raw = (bundle + ": 123\n").encode()
            app_raw = b"DYN4K\tCOMPLETE\tnonce\n"
            args = SimpleNamespace(udid="selected-udid", target="iosX64",
                                   archive=archive, timeout=1)
            inventory = {"app_bundle": str(selected), "bundle_id": bundle,
                         "linked_sha256": mobile_capture.capture.digest(linked),
                         "bundle_sha256": mobile_capture.validate_installed_bundle(selected, installed),
                         "image_derivation": apple_derivation(linked, selected / "Dyn4kPerformance")}
            launches = []
            signature_checks = []

            def setup(_archive, label, argv, **_kwargs):
                if label in ("apple-selected-signature", "apple-installed-signature"):
                    signature_checks.append((label, argv))
                if label == "apple-xcode":
                    output = "Xcode 26.4.1\nBuild version 1\n"
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
                    (data / "dyn4k-performance-nonce.ready").write_bytes(b"nonce")
                    output = launch_raw.decode()
                else:
                    output = ""
                return subprocess.CompletedProcess(argv, 0, output, "")

            installed_image = installed / "Dyn4kPerformance"
            identity = mobile_capture.apple_file_identity(installed_image)
            def vnode(_pid, _executable, _archive):
                self.assertFalse((data / "dyn4k-performance-nonce.release").exists())
                return {"pid": 123, "path": str(installed_image),
                        "device": identity["device"], "inode": identity["inode"],
                        "size": identity["size"]}

            def finish(_pid, _signal):
                self.assertEqual((data / "dyn4k-performance-nonce.release").read_bytes(), b"nonce")
                Path(next(arg.split("=", 1)[1] for arg in launches[0]
                          if arg.startswith("--stdout="))).write_bytes(app_raw)
                Path(next(arg.split("=", 1)[1] for arg in launches[0]
                          if arg.startswith("--stderr="))).write_bytes(b"app err\x00")
                raise ProcessLookupError

            with patch.object(mobile_capture, "setup_command", side_effect=setup), \
                 patch.object(mobile_capture, "validate_simulator", return_value={"udid": args.udid}), \
                 patch.object(mobile_capture, "apple_process_path",
                              side_effect=[installed_image, installed_image, installed_image, None]), \
                 patch.object(mobile_capture, "apple_process_vnode", side_effect=vnode), \
                 patch.object(mobile_capture.os, "kill", side_effect=finish):
                stdout, stderr, process = mobile_capture.run_simulator(
                    args, inventory, selected / "Dyn4kPerformance", ["fixture"], "nonce")
            self.assertEqual(stdout, app_raw)
            self.assertEqual(stderr, b"app err\x00")
            self.assertEqual((archive / "stdout.bin").read_bytes(), app_raw)
            self.assertEqual((archive / "stderr.bin").read_bytes(), stderr)
            self.assertEqual((archive / "setup/apple-launch.stdout.bin").read_bytes(), launch_raw)
            self.assertEqual(process["launch"]["pid"], 123)
            self.assertEqual(process["image"]["sha256"], inventory["bundle_sha256"]["Dyn4kPerformance"])
            self.assertNotEqual(process["image"]["sha256"], inventory["linked_sha256"])
            self.assertEqual(process["installed_image_size"], identity["size"])
            self.assertEqual(len(launches), 1)
            self.assertEqual(signature_checks, [
                ("apple-selected-signature", ["codesign", "--verify", str(selected)]),
                ("apple-installed-signature", ["codesign", "--verify", str(installed)]),
            ])
            self.assertNotIn("--console", launches[0])
            self.assertTrue(any(arg.startswith("--stdout=") for arg in launches[0]))
            self.assertTrue(any(arg.startswith("--stderr=") for arg in launches[0]))
            self.assertEqual(launches[0][-2:], ["--simulator-attestation-barrier", str(data)])
            self.assertEqual(process["attestation"]["ready_sha256"],
                             mobile_capture.capture.digest(archive / "attestation.ready.bin"))
            self.assertLess(process["attestation"]["ready_ns"],
                            process["attestation"]["released_ns"])
            for path in data.iterdir():
                path.unlink()
            archive = root / "failed-archive"
            archive.mkdir()
            args.archive = archive
            with patch.object(mobile_capture, "setup_command", side_effect=setup), \
                 patch.object(mobile_capture, "validate_simulator", return_value={"udid": args.udid}), \
                 patch.object(mobile_capture, "apple_process_path", return_value=installed_image), \
                 patch.object(mobile_capture, "apple_process_vnode",
                              side_effect=ValueError("simulator process executable vnode is missing or ambiguous")):
                with self.assertRaisesRegex(ValueError, "vnode"):
                    mobile_capture.run_simulator(
                        args, inventory, selected / "Dyn4kPerformance", ["fixture"], "nonce")
            self.assertFalse((data / "dyn4k-performance-nonce.release").exists())
            self.assertEqual((archive / "stdout.bin").read_bytes(), b"")
            self.assertEqual((archive / "stderr.bin").read_bytes(), b"")

    def test_simulator_barrier_rejects_early_completion_and_wrong_nonce(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            for ready in (None, b"wrong"):
                path = data / "dyn4k-performance-nonce.ready"
                if ready is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(ready)
                with self.subTest(ready=ready), self.assertRaisesRegex(ValueError, "attestation ready"):
                    mobile_capture.wait_simulator_ready(data, "nonce", 0.01)
                self.assertFalse((data / "dyn4k-performance-nonce.release").exists())

    def test_simulator_barrier_rejects_release_before_live_vnode(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            ready = data / "dyn4k-performance-nonce.ready"
            ready.write_bytes(b"nonce")
            barrier = mobile_capture.wait_simulator_ready(data, "nonce", 0.01)
            with self.assertRaisesRegex(ValueError, "vnode"):
                mobile_capture.parse_apple_process_vnode(b"", 11424, data / "Dyn4kPerformance")
            self.assertFalse(barrier["release"].exists())
            barrier["release"].write_bytes(b"nonce")
            with self.assertRaisesRegex(ValueError, "before live image proof"):
                mobile_capture.wait_simulator_ready(data, "nonce", 0.01)

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
            linked = root / "raw-linked.kexe"
            linked.write_bytes(b"raw linked image")
            bundle = "io.github.rubixhacker.dyn4k.performance.iosx64"
            selected_sha = mobile_capture.capture.digest(selected / "Dyn4kPerformance")
            inventory = {"app_bundle": str(selected), "bundle_id": bundle,
                         "linked_sha256": mobile_capture.capture.digest(linked),
                         "bundle_sha256": mobile_capture.validate_installed_bundle(selected, installed),
                         "image_derivation": apple_derivation(linked, selected / "Dyn4kPerformance")}
            args = SimpleNamespace(udid="selected-udid", target="iosX64",
                                   archive=archive, timeout=1)

            def setup(_archive, label, argv, **_kwargs):
                if label == "apple-xcode":
                    output = "Xcode 26.4.1\nBuild version 1\n"
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
                    (data / "dyn4k-performance-nonce.ready").write_bytes(b"nonce")
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

    def test_apple_derivation_binds_raw_copy_and_signed_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            linked = root / "raw.kexe"
            linked.write_bytes(b"raw linked image")
            app = root / "selected.app"
            app.mkdir()
            signed = app / "Dyn4kPerformance"
            signed.write_bytes(b"signed linked image with signature")
            inventory = {
                "app_bundle": str(app),
                "linked_sha256": mobile_capture.capture.digest(linked),
                "bundle_sha256": {"Dyn4kPerformance": mobile_capture.capture.digest(signed)},
                "image_derivation": apple_derivation(linked, signed),
            }
            self.assertNotEqual(mobile_capture.capture.digest(linked),
                                mobile_capture.capture.digest(signed))
            self.assertEqual(mobile_capture.validate_apple_image_derivation(
                inventory, linked, signed, "iosX64", "development"),
                inventory["image_derivation"])
            for field, value in (("linked_sha256", "0" * 64), ("copied_sha256", "0" * 64),
                                 ("copied_size", 1), ("linked_size", float(linked.stat().st_size)),
                                 ("packaged_sha256", "0" * 64), ("packaged_size", 1),
                                 ("codesign_verified", False), ("codesign_verified", 1),
                                 ("signing", "none"), ("target", "iosSimulatorArm64"),
                                 ("signing_command", None), ("verification_command", None),
                                 ("linked_path", str(signed)), ("package_path", str(root))):
                changed = {**inventory, "image_derivation": {**inventory["image_derivation"],
                                                             field: value}}
                with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, "derivation"):
                    mobile_capture.validate_apple_image_derivation(
                        changed, linked, signed, "iosX64", "development")
            signed.write_bytes(b"substituted signed image")
            with self.assertRaisesRegex(ValueError, "derivation"):
                mobile_capture.validate_apple_image_derivation(
                    inventory, linked, signed, "iosX64", "development")

    def test_unsigned_physical_apple_package_must_equal_raw_link(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            linked = root / "raw.kexe"
            linked.write_bytes(b"raw linked image")
            app = root / "selected.app"
            app.mkdir()
            image = app / "Dyn4kPerformance"
            image.write_bytes(linked.read_bytes())
            inventory = {"app_bundle": str(app),
                         "bundle_sha256": {"Dyn4kPerformance": mobile_capture.capture.digest(image)},
                         "image_derivation": apple_derivation(linked, image, target="iosArm64")}
            mobile_capture.validate_apple_image_derivation(
                inventory, linked, image, "iosArm64", "development")
            image.write_bytes(b"changed physical image")
            inventory["bundle_sha256"]["Dyn4kPerformance"] = mobile_capture.capture.digest(image)
            inventory["image_derivation"] = apple_derivation(linked, image, target="iosArm64")
            with self.assertRaisesRegex(ValueError, "derivation"):
                mobile_capture.validate_apple_image_derivation(
                    inventory, linked, image, "iosArm64", "development")

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
                         "build": "development",
                         "linked_sha256": mobile_capture.capture.digest(executable)}
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
            selected_app = root / "selected.app"
            installed_app = root / "installed.app"
            selected_app.mkdir()
            installed_app.mkdir()
            executable = selected_app / "Dyn4kPerformance"
            executable.write_bytes(b"signed test image")
            installed = installed_app / "Dyn4kPerformance"
            installed.write_bytes(executable.read_bytes())
            linked = root / "raw-linked.kexe"
            linked.write_bytes(b"raw test image")
            archive = root / "capture"
            args = SimpleNamespace(archive=archive, inventory=inventory_path,
                                   target="iosX64", build="development",
                                   scenario=fixture.scenario["id"], steps=1, warmup=1)
            artifacts = {"dyn4k-core": {"sha256": fixture.hashes["core"]},
                         "dyn4k": {"sha256": fixture.hashes["kotlin"]}}
            package = {"Dyn4kPerformance": mobile_capture.capture.digest(executable)}
            inventory = {"source_sha": fixture.source, "producer_tree": fixture.producer_tree,
                         "build": "development", "linked_sha256": mobile_capture.capture.digest(linked),
                         "linked_executable": str(linked),
                         "app_bundle": str(selected_app),
                         "bundle_sha256": package,
                         "image_derivation": apple_derivation(linked, executable)}
            bundle = "io.github.rubixhacker.dyn4k.performance.iosx64"
            launch_raw = (bundle + ": 123\n").encode()
            data_container = root / "data"
            launch_command = ["xcrun", "simctl", "launch", "selected-udid", bundle,
                              "--simulator-attestation-barrier", str(data_container)]
            token_sha = mobile_capture.hashlib.sha256(fixture.nonce.encode()).hexdigest()
            process = {"started_ns": 1, "ended_ns": 4, "bundle_id": bundle,
                       "command": launch_command,
                       "image": {"pid": 123, "path": str(installed),
                                 "sha256": mobile_capture.capture.digest(executable),
                                 "size": executable.stat().st_size, "device": 1, "inode": 2,
                                 "method": "simctl-launch-pid/proc_pidpath/lsof-text-vnode"},
                       "launch": {"pid": 123, "method": "simctl-redirected-files",
                                  "stdout_sha256": mobile_capture.hashlib.sha256(launch_raw).hexdigest()},
                       "attestation": {"method": "simulator-data-container-nonce-file-v1",
                                       "ready_sha256": token_sha, "release_sha256": token_sha,
                                       "ready_ns": 2, "released_ns": 3},
                       "output": {"stdout_path": str(data_container / "producer.stdout"),
                                  "stderr_path": str(data_container / "producer.stderr"),
                                  "stdout_sha256": mobile_capture.hashlib.sha256(raw).hexdigest(),
                                  "stderr_sha256": mobile_capture.hashlib.sha256(b"").hexdigest()},
                       "linked_sha256": inventory["linked_sha256"],
                       "installed_image_sha256": package["Dyn4kPerformance"],
                       "installed_image_size": executable.stat().st_size,
                       "installed_bundle_sha256": package,
                       "image_derivation": inventory["image_derivation"]}

            def simulator(*_unused):
                (args.archive / "setup").mkdir()
                (args.archive / "setup/apple-launch.stdout.bin").write_bytes(launch_raw)
                (args.archive / "setup/apple-launch.json").write_text(
                    json.dumps({"argv": launch_command, "exit_code": 0}))
                (args.archive / "attestation.ready.bin").write_bytes(fixture.nonce.encode())
                (args.archive / "attestation.release.bin").write_bytes(fixture.nonce.encode())
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
            self.assertNotEqual(result["process"]["linked_sha256"],
                                result["process"]["image"]["sha256"])
            self.assertEqual(result["linked_executable_sha256"], inventory["linked_sha256"])
            self.assertEqual(result["executable_sha256"], package["Dyn4kPerformance"])
            valid_process = copy.deepcopy(process)
            args.archive = root / "barrier-missing-launch-arg"
            process = {**valid_process, "command": launch_command[:-2]}
            with patch.object(mobile_capture.capture, "required_file", return_value=inventory_path), \
                 patch.object(mobile_capture, "validate_inventory",
                              return_value=(inventory, executable, artifacts)), \
                 patch.object(mobile_capture.secrets, "token_hex", return_value=fixture.nonce), \
                 patch.object(mobile_capture, "run_simulator", side_effect=simulator):
                self.assertEqual(mobile_capture.run(args), 1)
            self.assertIn("did not request the attestation barrier",
                          json.loads((args.archive / "result.json").read_text())["error"])
            args.archive = root / "barrier-wrong-container"
            process = {**valid_process, "output": {**valid_process["output"],
                                                   "stdout_path": str(root / "other/producer.stdout")}}
            with patch.object(mobile_capture.capture, "required_file", return_value=inventory_path), \
                 patch.object(mobile_capture, "validate_inventory",
                              return_value=(inventory, executable, artifacts)), \
                 patch.object(mobile_capture.secrets, "token_hex", return_value=fixture.nonce), \
                 patch.object(mobile_capture, "run_simulator", side_effect=simulator):
                self.assertEqual(mobile_capture.run(args), 1)
            self.assertIn("attestation container differs",
                          json.loads((args.archive / "result.json").read_text())["error"])
            process = valid_process
            for label, change in (("missing", None), ("wrong-nonce", b"wrong")):
                args.archive = root / f"barrier-{label}"
                def invalid_barrier(*_unused):
                    result = simulator()
                    path = args.archive / "attestation.ready.bin"
                    if change is None:
                        path.unlink()
                    else:
                        path.write_bytes(change)
                    return result
                with self.subTest(label=label), \
                     patch.object(mobile_capture.capture, "required_file", return_value=inventory_path), \
                     patch.object(mobile_capture, "validate_inventory",
                                  return_value=(inventory, executable, artifacts)), \
                     patch.object(mobile_capture.secrets, "token_hex", return_value=fixture.nonce), \
                     patch.object(mobile_capture, "run_simulator", side_effect=invalid_barrier):
                    self.assertEqual(mobile_capture.run(args), 1)
                invalid = json.loads((args.archive / "result.json").read_text())
                self.assertIn("attestation barrier", invalid["error"])
            for label, attestation in (
                    ("early-release", {**process["attestation"], "released_ns": 2}),
                    ("forged-method", {**process["attestation"], "method": "app-stdout"}),
                    ("forged-hash", {**process["attestation"], "ready_sha256": "0" * 64})):
                args.archive = root / f"barrier-{label}"
                process = {**valid_process, "attestation": attestation}
                with self.subTest(label=label), \
                     patch.object(mobile_capture.capture, "required_file", return_value=inventory_path), \
                     patch.object(mobile_capture, "validate_inventory",
                                  return_value=(inventory, executable, artifacts)), \
                     patch.object(mobile_capture.secrets, "token_hex", return_value=fixture.nonce), \
                     patch.object(mobile_capture, "run_simulator", side_effect=simulator):
                    self.assertEqual(mobile_capture.run(args), 1)
                invalid = json.loads((args.archive / "result.json").read_text())
                self.assertIn("attestation barrier", invalid["error"])
            process = valid_process
            for label, field, value in (
                    ("image", "image", {**process["image"], "sha256": "0" * 64}),
                    ("raw-link", "linked_sha256", "0" * 64),
                    ("derivation", "image_derivation", {**process["image_derivation"],
                                                          "codesign_verified": False}),
                    ("installed-image", "installed_image_sha256", "0" * 64),
                    ("installed-size", "installed_image_size", 1)):
                args.archive = root / f"forged-{label}"
                process = {**valid_process, field: value}
                with self.subTest(label=label), \
                     patch.object(mobile_capture.capture, "required_file", return_value=inventory_path), \
                     patch.object(mobile_capture, "validate_inventory",
                                  return_value=(inventory, executable, artifacts)), \
                     patch.object(mobile_capture.secrets, "token_hex", return_value=fixture.nonce), \
                     patch.object(mobile_capture, "run_simulator", side_effect=simulator):
                    self.assertEqual(mobile_capture.run(args), 1)
                forged = json.loads((args.archive / "result.json").read_text())
                self.assertNotIn("protocol", forged)
                self.assertIn("installed package or link", forged["error"])
            process = valid_process
            for label, path in (("raw-link", linked), ("selected", executable),
                                ("installed", installed)):
                original = path.read_bytes()
                path.write_bytes(b"substituted image")
                args.archive = root / f"changed-{label}"
                with self.subTest(path=label), \
                     patch.object(mobile_capture.capture, "required_file", return_value=inventory_path), \
                     patch.object(mobile_capture, "validate_inventory",
                                  return_value=(inventory, executable, artifacts)), \
                     patch.object(mobile_capture.secrets, "token_hex", return_value=fixture.nonce), \
                     patch.object(mobile_capture, "run_simulator", side_effect=simulator):
                    self.assertEqual(mobile_capture.run(args), 1)
                changed = json.loads((args.archive / "result.json").read_text())
                self.assertNotIn("protocol", changed)
                self.assertIn("raw link or selected/installed signed", changed["error"])
                path.write_bytes(original)

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


class NativeSimulatorBarrierExecutionTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("DYN4K_NATIVE_BARRIER_EXECUTABLE") and
                         os.environ.get("DYN4K_NATIVE_BARRIER_SOURCE"),
                         "set the linked Native producer and its exact source SHA")
    def test_release_requires_exact_regular_file_before_either_api_runs(self):
        executable = Path(os.environ["DYN4K_NATIVE_BARRIER_EXECUTABLE"]).resolve(strict=True)
        source = os.environ["DYN4K_NATIVE_BARRIER_SOURCE"]
        root = Path(__file__).resolve().parents[3]
        tree = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", f"{source}:consumers/performance/portable"],
            text=True).strip()
        manifest = json.loads(mobile_capture.capture.MANIFEST.read_text())
        hashes = {"core": "a" * 64, "kotlin": "b" * 64}
        for api in ("direct_kotlin", "compatibility"):
            scenario = mobile_capture.capture.scenario_from_manifest(
                manifest, f"separated.default.small.30hz.{api}")
            for release_kind in ("wrong", "symlink"):
                with self.subTest(api=api, release_kind=release_kind), \
                     tempfile.TemporaryDirectory() as directory:
                    nonce = "c" * 32
                    data = Path(directory)
                    ready = data / f"dyn4k-performance-{nonce}.ready"
                    release = data / f"dyn4k-performance-{nonce}.release"
                    arguments = [str(executable), scenario["id"], "separated", "default", "small",
                                 "30", "30", "3", "timing", api, source, hashes["core"],
                                 hashes["kotlin"], "development", nonce,
                                 "--simulator-attestation-barrier", directory]
                    process = subprocess.Popen(arguments, stdout=subprocess.PIPE,
                                               stderr=subprocess.PIPE)
                    try:
                        deadline = time.monotonic() + 10
                        while not ready.is_file() and time.monotonic() < deadline:
                            time.sleep(0.005)
                        self.assertEqual(ready.read_bytes(), nonce.encode())
                        self.assertIsNone(process.poll())
                        self.assertEqual(select.select([process.stdout], [], [], 0.05)[0], [])
                        if release_kind == "wrong":
                            release.write_bytes(b"wrong")
                        else:
                            target = data / "target"
                            target.write_bytes(nonce.encode())
                            release.symlink_to(target)
                        self.assertEqual(select.select([process.stdout], [], [], 0.25)[0], [],
                                         "Native producer left barrier before valid release")
                        self.assertIsNone(process.poll())
                        release.unlink()
                        release.write_bytes(nonce.encode())
                        stdout, stderr = process.communicate(timeout=10)
                        self.assertEqual(process.returncode, 0, stderr.decode(errors="replace"))
                        self.assertEqual(stderr, b"")
                        clocks, rows, provider, run = mobile_capture.capture.validate_protocol(
                            stdout, scenario, source, tree, hashes, "development", nonce,
                            30, 3, "timing")
                        self.assertEqual((len(clocks["warmup"]), len(clocks["measure"]), len(rows)),
                                         (3, 30, 30))
                        self.assertLessEqual(clocks["warmup"][-1][2], clocks["measure"][0][1])
                        self.assertEqual(provider[2], source)
                        self.assertEqual(run[-1], "unpassed")
                        self.assertEqual(mobile_capture.capture.validate_protocol(
                            stdout, scenario, source, tree, hashes, "development", nonce,
                            30, 3, "timing")[1], rows)
                        with self.assertRaisesRegex(ValueError, "provider"):
                            mobile_capture.capture.validate_protocol(
                                stdout, scenario, "0" * 40, tree, hashes, "development", nonce,
                                30, 3, "timing")
                    finally:
                        if process.poll() is None:
                            process.kill()
                            process.communicate()


if __name__ == "__main__":
    unittest.main()
