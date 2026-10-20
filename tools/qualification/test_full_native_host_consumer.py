import json
import io
import contextlib
import os
import subprocess
import sys
import tarfile
import tempfile
import time
from types import SimpleNamespace
import unittest
from pathlib import Path, PurePosixPath
from unittest.mock import Mock, patch

import full_native_host_consumer as route
import independent_gates


LANE = "linuxArm64:Linux ARM64:current:debug-g"
MODULE_CASES = {
    "core": ("dyn4k-core:a.B#one", "a.B", "one"),
    "facade": ("dyn4k:c.D#two", "c.D", "two"),
}


def report(short, name=None, outcome=None, duplicate=False):
    _, classname, method = MODULE_CASES[short]
    method = name or method
    row = (f'<testcase classname="linuxArm64Test.{classname}" '
           f'name="{method}[linuxArm64]" time="0.1">'
           f'{f"<{outcome}/>" if outcome else ""}</testcase>')
    if duplicate:
        row += row
    return (f'<testsuite tests="{2 if duplicate else 1}" '
            f'failures="{1 if outcome == "failure" else 0}" errors="0" '
            f'skipped="{1 if outcome == "skipped" else 0}" time="0.1">'
            f'{row}</testsuite>').encode()


class NativeHostConsumerTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform.startswith("linux"), "requires the local /proc process view")
    def test_process_sampler_observes_live_executable_bytes(self):
        image = Path(sys.executable).resolve()
        child = subprocess.Popen([str(image), "-c", "import time; time.sleep(2)"])
        try:
            matches = []
            deadline = time.monotonic() + 1
            while not matches and time.monotonic() < deadline:
                matches = [sample for sample in route.process_snapshot([image.parent], None)
                           if sample["pid"] == child.pid]
            self.assertTrue(matches)
            self.assertEqual(matches[0]["image_sha256"], route.digest(image.read_bytes()))
            self.assertEqual(Path(matches[0]["image"]), image)
        finally:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=5)

    @unittest.skipUnless(os.environ.get("DYN4K_NATIVE_GRADLE"),
                         "requires an existing pinned Gradle and JDK 21")
    def test_release_mode_init_script_configures_external_project(self):
        repository = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary:
            scratch = Path(temporary)
            script = scratch / "mode.init.gradle"
            script.write_bytes(route.mode_script("linuxArm64", "optimized-opt"))
            command = [os.environ["DYN4K_NATIVE_GRADLE"], "-p", str(repository / route.PROJECT),
                       "--offline", "--no-daemon", "--console=plain", "--init-script", str(script),
                       f"-PqualificationCheckout={repository}",
                       f"-PqualificationRepository={scratch / 'staging'}",
                       f"-PqualificationArchiveRoot={scratch / 'archive'}",
                       f"-PqualificationWorkRoot={scratch / 'build'}",
                       f"-PqualificationLaneId={LANE.replace('debug-g', 'optimized-opt')}",
                       "-PqualificationMode=optimized-opt",
                       "-PqualificationCoreSha256=" + "a" * 64,
                       "-PqualificationFacadeSha256=" + "b" * 64,
                       f"-PqualificationSourceInventory={scratch / 'source.tsv'}", "help"]
            result = subprocess.run(command, cwd=repository, capture_output=True, text=True,
                                    check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("BUILD SUCCESSFUL", result.stdout)
            dry_run = subprocess.run(command[:-1] + [":core:compileTestKotlinLinuxArm64", "--dry-run"],
                                     cwd=repository, capture_output=True, text=True, check=False)
            self.assertEqual(dry_run.returncode, 0, dry_run.stdout + dry_run.stderr)
            self.assertIn(":core:compileTestKotlinLinuxArm64 SKIPPED", dry_run.stdout)
            cross = subprocess.run(command[:-1] + ["qualificationCrossBuild", "--dry-run"],
                                   cwd=repository, capture_output=True, text=True, check=False)
            self.assertEqual(cross.returncode, 0, cross.stdout + cross.stderr)
            for short in ("core", "facade"):
                self.assertIn(f":{short}:linkReleaseTestLinuxArm64 SKIPPED", cross.stdout)

    def test_manifest_contains_all_28_selected_routes(self):
        repository = Path(__file__).resolve().parents[2]
        manifest = independent_gates.load_approved_manifest(repository)
        lanes = [lane for lane in manifest["lanes"]
                 if manifest["lanes"][lane]["target"] in route.TARGETS]
        self.assertEqual(len(lanes), 28)
        for lane in lanes:
            _, contract = route.lane_contract(repository, lane)
            self.assertEqual(len(contract["cases"]), 2523)

    def test_runtime_target_version_mode_and_simulator_are_distinct(self):
        selected = {"lane": LANE, "role": "current", "system": "Linux",
                    "machine": "aarch64", "os_version": "6.1.0", "libc": "2.39"}
        observed = {key: selected[key] for key in ("system", "machine", "os_version", "libc")}
        route.validate_host(LANE, selected, observed)
        for changed in ({"machine": "x86_64"}, {"os_version": "6.2.0"},
                        {"libc": "2.38"}, {"lane": LANE.replace("debug-g", "optimized-opt")}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                route.validate_host(LANE, {**selected, **changed}, observed)
        simulator = "iosSimulatorArm64:iOS simulator ARM64:current:debug-g"
        chosen = {"lane": simulator, "role": "current", "system": "Darwin",
                  "machine": "arm64", "os_version": "26.5.1", "guest_version": "26.5",
                  "simulator_runtime": "com.apple.CoreSimulator.SimRuntime.iOS-26-5",
                  "simulator_udid": "12345678-1234-1234-1234-123456789abc"}
        guest = {"system": "Darwin", "machine": "arm64", "os_version": "26.5.1",
                 "xcode_version": "26.5", "guest_family": "iOS",
                 "guest_version": "26.5", "guest_runtime": chosen["simulator_runtime"],
                 "guest_udid": chosen["simulator_udid"], "guest_state": "Booted"}
        route.validate_host(simulator, chosen, guest)
        for altered in ({"guest_state": "Shutdown"}, {"guest_udid": "foreign"},
                        {"guest_version": "15.0"}, {"guest_family": "tvOS"}):
            with self.subTest(altered=altered), self.assertRaises(ValueError):
                route.validate_host(simulator, chosen, {**guest, **altered})
        windows_lane = "mingwX64:Windows x64:current:debug-g"
        windows = {"lane": windows_lane, "role": "current", "system": "Windows",
                   "machine": "AMD64", "os_version": "10.0.26100",
                   "windows_product_type": "client", "windows_product_name": "Windows 11 Pro"}
        observed_windows = {key: value for key, value in windows.items()
                            if key not in ("lane", "role")}
        route.validate_host(windows_lane, windows, observed_windows)
        for product in ("server", None):
            with self.subTest(product=product), self.assertRaises(ValueError):
                route.validate_host(windows_lane, windows,
                                    {**observed_windows, "windows_product_type": product})

    def test_transport_preserves_nanosecond_mtimes_and_rejects_links(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary:
            root = Path(temporary)
            raw = root / "raw"
            raw.mkdir()
            (raw / "receipt.json").write_bytes(b"{}")
            (raw / "evidence.bin").write_bytes(b"original")
            (raw / "evidence.bin").chmod(0o700)
            timestamp = 1_700_000_000_123_456_700
            for path in raw.iterdir():
                os.utime(path, ns=(timestamp, timestamp))
            transport = root / "raw.tar"
            sha = route.pack_archive(raw, transport)
            self.assertEqual(sha, route.digest(transport.read_bytes()))
            relocated = root / "relocated"
            route.unpack_archive(transport, relocated)
            self.assertEqual((relocated / "evidence.bin").stat().st_mtime_ns, timestamp)
            self.assertEqual((relocated / "evidence.bin").read_bytes(), b"original")
            self.assertEqual((relocated / "evidence.bin").stat().st_mode & 0o777, 0o700)
            outside = root / "outside"
            outside.write_bytes(b"original")
            (raw / "evidence.bin").unlink()
            os.link(outside, raw / "evidence.bin")
            with self.assertRaises(ValueError):
                route.snapshot_archive(raw, root / "rejected")
            with self.assertRaises(ValueError):
                route.pack_archive(raw, root / "linked.tar")
            malicious = root / "malicious.tar"
            with tarfile.open(malicious, "w") as transport:
                link = tarfile.TarInfo("raw/evidence.bin")
                link.type = tarfile.LNKTYPE
                link.linkname = "../outside"
                transport.addfile(link)
                timestamps = b"{}"
                info = tarfile.TarInfo("transport-mtimes.json")
                info.size = len(timestamps)
                transport.addfile(info, io.BytesIO(timestamps))
            with self.assertRaises(ValueError):
                route.unpack_archive(malicious, root / "malicious-output")

    def test_snapshot_rejects_path_swap_between_scan_and_open(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary:
            root = Path(temporary)
            raw = root / "raw"
            raw.mkdir()
            (raw / "receipt.json").write_bytes(b"{}")
            (raw / "evidence.bin").write_bytes(b"original")
            original = route.os.open
            def swap(path, flags, *args, **kwargs):
                if path == "evidence.bin":
                    (raw / "evidence.bin").unlink()
                    (raw / "evidence.bin").symlink_to(raw / "receipt.json")
                return original(path, flags, *args, **kwargs)
            with patch.object(route.os, "open", side_effect=swap), self.assertRaises((OSError, ValueError)):
                route.snapshot_archive(raw, root / "relocated")

    def test_unpack_requires_a_new_unlinked_root(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary:
            root = Path(temporary)
            raw = root / "raw"
            raw.mkdir()
            (raw / "receipt.json").write_bytes(b"{}")
            transport = root / "raw.tar"
            route.pack_archive(raw, transport)
            outside = root / "outside"
            outside.mkdir()
            linked = root / "linked"
            linked.symlink_to(outside, target_is_directory=True)
            for destination in (linked, outside):
                error = "already exists" if os.name == "nt" else "new, unlinked"
                with self.subTest(destination=destination), self.assertRaisesRegex(ValueError, error):
                    route.unpack_archive(transport, destination)
            self.assertEqual(list(outside.iterdir()), [])
            parent_link = root / "parent-link"
            parent_link.symlink_to(outside, target_is_directory=True)
            with self.assertRaises((OSError, ValueError)):
                route.unpack_archive(transport, parent_link / "new")
            self.assertEqual(list(outside.iterdir()), [])
            route.unpack_archive(transport, root / "new")
            self.assertEqual((root / "new/receipt.json").read_bytes(), b"{}")

    def test_windows_paths_reject_aliases_and_escapes(self):
        self.assertEqual(route.windows_components(r"C:\evidence\raw"),
                         ("C:\\", ("evidence", "raw")))
        for path in (r"C:evidence\raw", r"C:\evidence\..\outside",
                     r"C:\evidence\CON.txt", r"C:\evidence\name.",
                     r"C:\evidence\name ", r"C:\evidence\data:stream",
                     r"\\server\share\raw", r"\\?\C:\evidence\raw"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                route.windows_components(path)
        for name in ("raw/../outside", "raw/C:/outside", "raw/CON.txt",
                     "raw/folder./file", "raw/data:stream", "/raw/receipt.json"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                route.windows_transport_name(name)
        with self.assertRaises(ValueError):
            route.windows_unique_names(["raw/receipt.json", "raw/Receipt.json"])
        with self.assertRaises(ValueError):
            route.windows_unique_names(["raw/LongDirectory/a", "raw/longdirectory/b"])

    def test_windows_snapshot_requires_a_real_windows_host(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary:
            root = Path(temporary)
            raw = root / "raw"
            raw.mkdir()
            (raw / "receipt.json").write_bytes(b"{}")
            if os.name == "nt":
                self.skipTest("the Windows backend is covered by the live round trip")
            with self.assertRaisesRegex(ValueError, "Windows host"):
                route.snapshot_archive(raw, root / "copied", platform_name="nt")
            self.assertFalse((root / "copied").exists())

    def test_windows_drive_root_create_keeps_anchored_write_access(self):
        api = route.WindowsArchiveApi.__new__(route.WindowsArchiveApi)
        api.drive = Mock(return_value=1)
        api.child = Mock(return_value=2)
        api.close = Mock()
        with api.walk(r"C:\new", create_last=True, writable=True):
            api.drive.assert_called_with("C:\\", writable=True)
        with api.walk("C:\\", writable=True):
            api.drive.assert_called_with("C:\\", writable=True)

    def test_windows_walk_close_failure_preserves_original_error(self):
        api = route.WindowsArchiveApi.__new__(route.WindowsArchiveApi)
        api.drive = Mock(return_value=1)
        api.child = Mock(return_value=2)
        api.close = Mock(side_effect=OSError("injected root close failure"))
        with self.assertRaisesRegex(OSError, "injected write failure") as failure:
            with api.walk(r"C:\new"):
                raise OSError("injected write failure")
        self.assertIn("root close failure", " ".join(failure.exception.__notes__))
        self.assertEqual(api.close.call_count, 2)

    def test_windows_transport_parser_rejects_unsafe_members(self):
        timestamp = 1_700_000_000_123_456_700
        def make_transport(entries, mtimes):
            stream = io.BytesIO()
            with tarfile.open(fileobj=stream, mode="w") as archive:
                for name, data, kind in entries:
                    item = tarfile.TarInfo(name)
                    item.mode = 0o700
                    if kind == "hardlink":
                        item.type = tarfile.LNKTYPE
                        item.linkname = "../outside"
                        archive.addfile(item)
                    else:
                        item.size = len(data)
                        archive.addfile(item, io.BytesIO(data))
                stamps = route.encoded(mtimes)
                item = tarfile.TarInfo("transport-mtimes.json")
                item.size = len(stamps)
                archive.addfile(item, io.BytesIO(stamps))
            return stream.getvalue()

        receipt = ("raw/receipt.json", b"{}", "file")
        image = ("raw/nested/core.program", b"image", "file")
        api = Mock()
        api.read_absolute.return_value = make_transport(
            [receipt, image], {"receipt.json": timestamp, "nested/core.program": timestamp})
        with patch.object(route, "WindowsArchiveApi", return_value=api):
            route.windows_unpack_archive(r"C:\evidence\raw.tar", r"C:\evidence\new")
        rows = api.write_tree.call_args.args[1]
        self.assertEqual(rows[0], (("nested", "core.program"), b"image", timestamp, 0o700))
        self.assertTrue(api.write_tree.call_args.kwargs["create"])

        mutations = (
            ([receipt, ("raw/Receipt.json", b"{}", "file")],
             {"receipt.json": timestamp, "Receipt.json": timestamp}),
            ([receipt, ("raw/nested/core.program", b"", "hardlink")],
             {"receipt.json": timestamp, "nested/core.program": timestamp}),
            ([receipt, ("raw/../escape", b"x", "file")],
             {"receipt.json": timestamp, "../escape": timestamp}),
            ([receipt, ("raw/CON.txt", b"x", "file")],
             {"receipt.json": timestamp, "CON.txt": timestamp}),
            ([receipt], {"receipt.json": timestamp + 1}),
        )
        for entries, mtimes in mutations:
            with self.subTest(entries=entries):
                api = Mock()
                api.read_absolute.return_value = make_transport(entries, mtimes)
                with patch.object(route, "WindowsArchiveApi", return_value=api), self.assertRaises(ValueError):
                    route.windows_unpack_archive(r"C:\evidence\raw.tar", r"C:\evidence\new")
                api.write_tree.assert_not_called()

    def test_windows_public_unpack_rejects_filetime_overflow_before_output(self):
        offset = 116444736000000000
        maximum = ((1 << 64) - 1 - offset) * 100
        def transport_bytes(timestamp):
            stream = io.BytesIO()
            with tarfile.open(fileobj=stream, mode="w") as archive:
                receipt = tarfile.TarInfo("raw/receipt.json")
                receipt.size = 2
                archive.addfile(receipt, io.BytesIO(b"{}"))
                mtimes = route.encoded({"receipt.json": timestamp})
                stamps = tarfile.TarInfo("transport-mtimes.json")
                stamps.size = len(mtimes)
                archive.addfile(stamps, io.BytesIO(mtimes))
            return stream.getvalue()

        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary:
            output = Path(temporary) / "relocated"
            api = Mock()
            api.read_absolute.return_value = transport_bytes(maximum + 100)
            api.write_tree.side_effect = lambda *_args, **_kwargs: output.mkdir()
            with patch.object(route, "os", SimpleNamespace(name="nt")), patch.object(
                    route, "WindowsArchiveApi", return_value=api):
                with self.assertRaisesRegex(ValueError, "FILETIME"):
                    route.main(["unpack", "--transport", r"C:\evidence\raw.tar",
                                "--output", str(output)])
            api.write_tree.assert_not_called()
            self.assertFalse(output.exists())

            api.read_absolute.return_value = transport_bytes(maximum)
            with patch.object(route, "os", SimpleNamespace(name="nt")), patch.object(
                    route, "WindowsArchiveApi", return_value=api):
                route.main(["unpack", "--transport", r"C:\evidence\raw.tar",
                            "--output", str(output)])
            self.assertTrue(output.is_dir())
            self.assertEqual(api.write_tree.call_args.args[1][0][2], maximum)

    def test_windows_public_unpack_cleans_late_write_failure_for_same_path_retry(self):
        timestamp = 1_700_000_000_123_456_700
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as archive:
            for name, data in (("raw/receipt.json", b"{}"),
                               ("raw/nested/core.program", b"image")):
                member = tarfile.TarInfo(name)
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
            mtimes = route.encoded({"receipt.json": timestamp,
                                    "nested/core.program": timestamp})
            member = tarfile.TarInfo("transport-mtimes.json")
            member.size = len(mtimes)
            archive.addfile(member, io.BytesIO(mtimes))

        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary:
            parent = Path(temporary)
            output = parent / "relocated"
            existing = parent / "keep.txt"
            existing.write_bytes(b"user content")

            class FailingArchiveApi:
                write_tree = route.WindowsArchiveApi.write_tree

                def __init__(self):
                    self.fail_once = True
                    self.fail_cleanup_close = False
                    self.cleaning = False

                def read_absolute(self, _path):
                    return stream.getvalue()

                @contextlib.contextmanager
                def walk(self, _path, *, create_last=False, writable=False):
                    if create_last:
                        output.mkdir()
                    yield output

                def child(self, anchor, name, *, directory, create=False, writable=False,
                          deletable=False):
                    path = anchor / name
                    if create:
                        if directory:
                            path.mkdir()
                        else:
                            path.touch(exist_ok=False)
                    return path

                def info(self, path, _directory):
                    details = path.stat()
                    return ((details.st_dev, details.st_ino, 0), 0)

                def discard(self, path, directory):
                    self.cleaning = True
                    if directory:
                        path.rmdir()
                    else:
                        path.unlink()

                def write(self, path, data, _mtime_ns, _mode):
                    path.write_bytes(data)
                    if self.fail_once and path.name == "receipt.json":
                        self.fail_once = False
                        raise OSError("injected late metadata failure")

                def close(self, value):
                    if self.fail_cleanup_close and self.cleaning and value.name == "nested":
                        self.fail_cleanup_close = False
                        raise OSError("injected cleanup close failure")

            api = FailingArchiveApi()
            with patch.object(route, "os", SimpleNamespace(name="nt")), patch.object(
                    route, "WindowsArchiveApi", return_value=api):
                with self.assertRaisesRegex(OSError, "injected late metadata failure"):
                    route.main(["unpack", "--transport", r"C:\evidence\raw.tar",
                                "--output", r"C:\evidence\relocated"])
                self.assertFalse(output.exists())
                self.assertEqual(existing.read_bytes(), b"user content")
                route.main(["unpack", "--transport", r"C:\evidence\raw.tar",
                            "--output", r"C:\evidence\relocated"])
                with self.assertRaises(FileExistsError):
                    route.main(["unpack", "--transport", r"C:\evidence\raw.tar",
                                "--output", r"C:\evidence\relocated"])
            self.assertEqual((output / "receipt.json").read_bytes(), b"{}")
            self.assertEqual((output / "nested/core.program").read_bytes(), b"image")
            self.assertEqual(existing.read_bytes(), b"user content")

            output = parent / "close-failure"
            api.fail_once = True
            api.fail_cleanup_close = True
            api.cleaning = False
            with patch.object(route, "os", SimpleNamespace(name="nt")), patch.object(
                    route, "WindowsArchiveApi", return_value=api):
                with self.assertRaisesRegex(OSError, "injected late metadata failure") as failure:
                    route.main(["unpack", "--transport", r"C:\evidence\raw.tar",
                                "--output", r"C:\evidence\close-failure"])
                self.assertIn("cleanup close failure", " ".join(failure.exception.__notes__))
                self.assertFalse(output.exists())
                route.main(["unpack", "--transport", r"C:\evidence\raw.tar",
                            "--output", r"C:\evidence\close-failure"])
            self.assertEqual((output / "receipt.json").read_bytes(), b"{}")

    def test_windows_public_unpack_keeps_replacement_with_aliased_file_id(self):
        timestamp = 1_700_000_000_123_456_700
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as archive:
            receipt = tarfile.TarInfo("raw/receipt.json")
            receipt.size = 2
            archive.addfile(receipt, io.BytesIO(b"{}"))
            mtimes = route.encoded({"receipt.json": timestamp})
            manifest = tarfile.TarInfo("transport-mtimes.json")
            manifest.size = len(mtimes)
            archive.addfile(manifest, io.BytesIO(mtimes))

        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary:
            output = Path(temporary) / "relocated"

            class ReplacingArchiveApi:
                write_tree = route.WindowsArchiveApi.write_tree

                def __init__(self):
                    self.objects = {}

                def read_absolute(self, _path):
                    return stream.getvalue()

                @contextlib.contextmanager
                def walk(self, _path, *, create_last=False, writable=False):
                    if create_last:
                        output.mkdir()
                    yield output

                def child(self, parent, name, *, directory, create=False, writable=False,
                          deletable=False):
                    path = parent / name
                    if directory:
                        if create:
                            path.mkdir()
                        return path
                    if create:
                        path.touch(exist_ok=False)
                        self.objects[path] = object()
                    return SimpleNamespace(path=path, object=self.objects[path])

                def info(self, _value, _directory):
                    return ((1, 2, 3), 0)

                def write(self, value, data, _mtime_ns, _mode):
                    value.path.write_bytes(data)
                    value.path.unlink()
                    value.path.write_bytes(b"user replacement")
                    self.objects[value.path] = object()
                    raise OSError("injected write failure after replacement")

                def discard(self, value, directory):
                    if directory:
                        value.rmdir()
                    elif self.objects.get(value.path) is value.object:
                        value.path.unlink()
                        del self.objects[value.path]

                def close(self, _value):
                    pass

            api = ReplacingArchiveApi()
            with patch.object(route, "os", SimpleNamespace(name="nt")), patch.object(
                    route, "WindowsArchiveApi", return_value=api):
                with self.assertRaisesRegex(OSError, "injected write failure after replacement"):
                    route.main(["unpack", "--transport", r"C:\evidence\raw.tar",
                                "--output", r"C:\evidence\relocated"])
                self.assertEqual((output / "receipt.json").read_bytes(), b"user replacement")
                with self.assertRaises(FileExistsError):
                    route.main(["unpack", "--transport", r"C:\evidence\raw.tar",
                                "--output", r"C:\evidence\relocated"])

    @unittest.skipUnless(os.name == "nt", "requires real Windows handle APIs")
    def test_windows_handle_anchored_round_trip_and_links(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary:
            root = Path(temporary)
            raw = root / "raw"
            (raw / "nested").mkdir(parents=True)
            (raw / "receipt.json").write_bytes(b"{}")
            image = raw / "nested" / "core.program"
            image.write_bytes(b"native-test-image")
            timestamp = 1_700_000_000_123_456_700
            os.utime(image, ns=(timestamp, timestamp))
            snap = root / "snapshot"
            snap.mkdir()
            route.snapshot_archive(raw, snap)
            self.assertEqual((snap / "nested/core.program").read_bytes(), b"native-test-image")
            self.assertEqual((snap / "nested/core.program").stat().st_mtime_ns, timestamp)
            transport = root / "raw.tar"
            route.pack_archive(raw, transport)
            relocated = root / "relocated"
            route.unpack_archive(transport, relocated)
            self.assertEqual((relocated / "nested/core.program").read_bytes(), b"native-test-image")
            self.assertEqual((relocated / "nested/core.program").stat().st_mtime_ns, timestamp)
            with self.assertRaises((OSError, ValueError)):
                route.unpack_archive(transport, relocated)
            with route.WindowsArchiveApi().walk(raw):
                with self.assertRaises(OSError):
                    raw.rename(root / "moved")
            duplicate = root / "duplicate.tar"
            with tarfile.open(duplicate, "w") as output:
                for name in ("raw/receipt.json", "raw/Receipt.json"):
                    item = tarfile.TarInfo(name)
                    item.size = 2
                    output.addfile(item, io.BytesIO(b"{}"))
                stamps = b'{}'
                item = tarfile.TarInfo("transport-mtimes.json")
                item.size = len(stamps)
                output.addfile(item, io.BytesIO(stamps))
            with self.assertRaises(ValueError):
                route.unpack_archive(duplicate, root / "duplicate-output")
            outside = root / "outside"
            outside.write_bytes(b"outside")
            image.unlink()
            os.link(outside, image)
            with self.assertRaises(ValueError):
                route.snapshot_archive(raw, root / "rejected")
            parent = root / "parent-link"
            try:
                parent.symlink_to(raw, target_is_directory=True)
            except OSError:
                pass
            else:
                with self.assertRaises((OSError, ValueError)):
                    route.unpack_archive(transport, parent / "new")

    def test_cross_build_requires_aarch64_elf_and_x64_compiler_host(self):
        header = bytearray(64)
        header[:6] = b"\x7fELF\x02\x01"
        header[18:20] = (183).to_bytes(2, "little")
        route.validate_linux_arm64_elf(bytes(header))
        for changed in (bytes(header[:4] + b"\x01" + header[5:]),
                        bytes(header[:18] + (62).to_bytes(2, "little") + header[20:])):
            with self.assertRaises(ValueError):
                route.validate_linux_arm64_elf(changed)
        route.validate_cross_build_host({"system": "Linux", "machine": "x86_64"})
        with self.assertRaises(ValueError):
            route.validate_cross_build_host({"system": "Linux", "machine": "aarch64"})

    def test_original_teamcity_events_require_each_method_once_and_no_failure(self):
        selected = {("a.B", "one"): "dyn4k-core:a.B#one"}
        valid = (b"##teamcity[testSuiteStarted name='a.B']\n"
                 b"##teamcity[testStarted name='one' locationHint='ktest:test://a.B.one']\n"
                 b"##teamcity[testFinished name='one' duration='1']\n"
                 b"##teamcity[testSuiteFinished name='a.B']\n")
        self.assertEqual(route.original_teamcity_events(valid, selected),
                         ["dyn4k-core:a.B#one"])
        for raw in (valid + valid,
                    valid.replace(b"testFinished", b"testFailed"),
                    valid.replace(b"name='one'", b"name='other'"),
                    valid.replace(b"testFinished", b"testIgnored")):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                route.original_teamcity_events(raw, selected)

    def test_native_listing_probe_is_diagnostic_and_checks_registration(self):
        selected = {("a.B", "one"): "dyn4k-core:a.B#one"}
        self.assertEqual(route.original_test_listing(b"a.B.\n  one\n", selected),
                         ["dyn4k-core:a.B#one"])
        for listing in (b"a.B.\n", b"a.B.\n  one\n  one\n",
                        b"a.B.\n  foreign\n"):
            with self.subTest(listing=listing), self.assertRaises(ValueError):
                route.original_test_listing(listing, selected)

    def test_original_native_rows_reject_missing_duplicate_failing_and_wrong_target(self):
        selected = {("a.B", "one"): "dyn4k-core:a.B#one"}
        ids, normalized = route.original_report(report("core"), "linuxArm64", selected)
        self.assertEqual(ids, ["dyn4k-core:a.B#one"])
        self.assertIn(b'id="dyn4k-core:a.B#one"', normalized)
        for raw in (report("core", name="other"), report("core", outcome="failure"),
                    report("core", outcome="skipped"), report("core", duplicate=True),
                    report("core").replace(b"linuxArm64Test", b"macosArm64Test")):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                route.original_report(raw, "linuxArm64", selected)
        with self.assertRaises(ValueError):
            route.check_method_coverage([], list(selected.values()))

    def test_relocated_replay_rejects_binary_klib_host_and_method_mutations(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary:
            root = Path(temporary) / "relocated-archive"
            root.mkdir()
            selection = {"lane": LANE, "role": "current", "system": "Linux",
                         "machine": "aarch64", "os_version": "6.1.0", "libc": "2.39"}
            host = {key: selection[key] for key in ("system", "machine", "os_version", "libc")}
            hashes = {"dyn4k-core": route.digest(b"core-klib"),
                      "dyn4k": route.digest(b"facade-klib")}
            toolchain = {"java_home": "/tools/jdk21",
                         "java_version": 'openjdk version "21.0.1"',
                         "java_sha256": "a" * 64,
                         "gradle_version": "Gradle 9.5.0", "gradle_executable": "/tools/gradle",
                         "gradle_sha256": "b" * 64,
                         "gradle_user_home": "/home/runner/.gradle",
                         "kgp_version": "2.4.20", "native_home": "/tools/konan",
                         "native_version": "Kotlin/Native: 2.4.20",
                         "native_sha256": "c" * 64,
                         "native_compiler_sha256": "d" * 64,
                         "python_executable": "/tools/python", "python_version": "3.14.0",
                         "python_sha256": "e" * 64}
            contract = {"cases": [{"id": item[0], "module": module}
                                  for module, item in (("dyn4k-core", MODULE_CASES["core"]),
                                                       ("dyn4k", MODULE_CASES["facade"]))]}
            manifest = {"lanes": {LANE: {"target": "linuxArm64", "runtime": "Linux ARM64",
                                          "version": "current", "configuration": "debug-g"}}}
            inputs = {"source-inventory.tsv": b"source\tsha\n",
                      "core-cases.tsv": b"dyn4k-core:a.B#one\ta.B\tone\n",
                      "facade-cases.tsv": b"dyn4k:c.D#two\tc.D\ttwo\n"}

            def write(relative, data):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)

            write("host.json", route.encoded(host))
            write("host-after.json", route.encoded(host))
            write("attempt.json", route.encoded({"status": "PASSED"}))
            for name, data in inputs.items():
                write(f"inputs/{name}", data)
            write("inputs/runtime-selection.json", route.encoded(selection))
            write("inputs/mode.init.gradle", route.mode_script("linuxArm64", "debug-g"))
            components = [f"io.github.rubixhacker:{module}:0.1.0-alpha.1"
                          for module in route.MODULES]
            components += [f"io.github.rubixhacker:{module}-linuxarm64:0.1.0-alpha.1"
                           for module in route.MODULES]
            artifacts = [{"component": components[index + 2], "size": len(b"core-klib")
                          if module == "dyn4k-core" else len(b"facade-klib"),
                          "sha256": hashes[module],
                          "file": str(route.staged_path(PurePosixPath("/staging"), module, "linuxArm64"))}
                         for index, module in enumerate(route.MODULES)]
            graph = {"compile": [], "runtime_resolution":
                     "native-test-executable; no separate KLIB runtime resolution",
                     "gradle_user_home": toolchain["gradle_user_home"]}
            for phase in ("compile",):
                graph[phase] = [{"project": short,
                                 "configuration": "linuxArm64TestCompileKlibraries",
                                 "components": components, "artifacts": artifacts}
                                for short in ("core", "facade")]
            write("provider-graph.json", route.encoded(graph))
            for module, data in (("dyn4k-core", b"core-klib"), ("dyn4k", b"facade-klib")):
                write(f"resolved/{module}-linuxarm64-0.1.0-alpha.1.klib", data)
            products = {}
            samples = []
            output = ["BUILD SUCCESSFUL", f"QUALIFICATION_LANE={LANE}",
                      "QUALIFICATION_CASE_COUNT=2523",
                      f"QUALIFICATION_PROVIDER_GRAPH_SHA256={route.digest((root / 'provider-graph.json').read_bytes())}"]
            observed = []
            raw_paths, normal_paths = [], []
            for short in ("core", "facade"):
                friend_module = "dyn4k-core" if short == "core" else "dyn4k"
                output += [f"> Task :{short}:linuxArm64Test",
                           f"QUALIFICATION_COMPILER_FLAGS_{short.upper()}=" + json.dumps(
                               ["-g", "-friend-modules", str(route.staged_path(
                                   PurePosixPath('/staging'), friend_module, 'linuxArm64'))])]
                binary = f"binary-{short}".encode()
                write(f"runtime/{short}.program", binary)
                sample = {"pid": 200 if short == "core" else 201,
                          "parent_pid": 101, "image":
                          f"/producer-build/{short}/bin/linuxArm64/debugTest/test.kexe",
                          "command": f"/producer-build/{short}/bin/linuxArm64/debugTest/test.kexe",
                          "image_sha256": route.digest(binary), "observed_ns": time.time_ns(),
                          "module": short, "simulator_udid": None}
                samples.append(sample)
                products[short] = {"archive": f"runtime/{short}.program",
                                   "path": f"/producer-build/{short}/bin/linuxArm64/debugTest/test.kexe",
                                   "sha256": route.digest(binary), "mode": "debugTest",
                                   "target": "linuxArm64", "observed_process": sample}
                output.append(f"QUALIFICATION_RUNTIME_{short.upper()}_PROGRAM_SHA256={route.digest(binary)}")
                raw = report(short)
                ids, normal = route.original_report(raw, "linuxArm64", route.selected_rows(
                    inputs[f"{short}-cases.tsv"]))
                observed.extend(ids)
                raw_path = f"reports/raw/{short}/TEST-{short}.xml"
                normal_path = f"reports/normalized/{short}/TEST-{short}.xml"
                write(raw_path, raw)
                write(normal_path, normal)
                raw_paths.append(raw_path)
                normal_paths.append(normal_path)
                output += [f"QUALIFICATION_RAW_XML_SHA256={route.digest(raw)}",
                           f"QUALIFICATION_XML_SHA256={route.digest(normal)}"]
            write("runtime/products.json", route.encoded(products))
            write("runtime/process-observations.jsonl", b"".join(route.encoded(item) for item in samples))
            write("reports/report-traversal.json", route.encoded(observed))
            output.append(f"QUALIFICATION_REPORT_TRAVERSAL_SHA256={route.digest((root / 'reports/report-traversal.json').read_bytes())}")
            for module, value in hashes.items():
                output.append(f"QUALIFICATION_RESOLVED_{module.upper().replace('-', '_')}_SHA256={value}")
            write("stdout.txt", ("\n".join(output) + "\n").encode())
            write("stderr.txt", b"")
            start, finish = time.time_ns() - 1_000_000_000, time.time_ns() + 1_000_000_000
            build_paths = [f"{route.PROJECT}/{name}" for name in
                           ("build.gradle.kts", "settings.gradle.kts",
                            "gradle.properties",
                            "core/build.gradle.kts", "facade/build.gradle.kts")]
            paths = {"checkout": "/candidate-checkout", "staging": "/staging",
                     "archive_root": "/producer-archive", "work_root": "/producer-build",
                     "gradle": "/tools/gradle", "native_home": "/tools/konan",
                     "python": "/tools/python"}
            receipt = {"schema": 1, "candidate_sha": "candidate", "lane": LANE,
                       **manifest["lanes"][LANE],
                       "source_tree": "tree", "consumer_group": "full-suite",
                       "consumer_contract_sha256": independent_gates.digest(contract),
                       "artifact_hashes": hashes, "selection": selection, "host": host,
                       "host_after": host,
                       "runtime_identity": route.digest(route.encoded(host)),
                       "toolchain": toolchain, "source_inventory_sha256": route.digest(inputs["source-inventory.tsv"]),
                       "consumer_build_sha256": {path: route.digest(b"code") for path in build_paths},
                       "producer_sha256": route.digest(b"code"),
                       "producer_paths": paths,
                       "process": {"command": route.gradle_command(paths, LANE, "debug-g", hashes),
                                   "cwd": "/producer-archive", "exit_code": 0,
                                   "pid": 101, "parent_pid": 100, "started_ns": start,
                                   "finished_ns": finish, "stdout": "stdout.txt", "stderr": "stderr.txt"},
                       "provider_graph": "provider-graph.json",
                       "resolved_artifacts": {module: f"resolved/{module}-linuxarm64-0.1.0-alpha.1.klib"
                                              for module in route.MODULES},
                       "products": products, "raw_consumer_xml": raw_paths,
                       "consumer_xml": normal_paths}

            def seal():
                receipt["files"] = route.archive_files(root)
                write("receipt.json", route.encoded(receipt))
                return independent_gates.archive_digest(root)

            def verify():
                archive_hash = seal()
                return route.verify(root, Path(temporary), "candidate", LANE, hashes,
                                    selection, archive_hash, toolchain)

            with (patch.object(route, "lane_contract", return_value=(manifest, contract)),
                  patch.object(route, "git", return_value="tree"),
                  patch.object(route, "verify_source_binding"),
                  patch.object(route, "source_inputs", return_value=inputs),
                  patch.object(route.subprocess, "check_output", return_value=b"code")):
                self.assertEqual(verify()["status"], "PASSED")
                mutations = {
                    "wrong KLIB": ("resolved/dyn4k-core-linuxarm64-0.1.0-alpha.1.klib", b"wrong"),
                    "changed binary": ("runtime/core.program", b"changed"),
                    "altered host": ("host.json", route.encoded({**host, "machine": "x86_64"})),
                    "missing method": (raw_paths[0], report("core", name="missing")),
                    "duplicate method": (raw_paths[0], report("core", duplicate=True)),
                    "failing method": (raw_paths[0], report("core", outcome="failure")),
                    "changed process image": ("runtime/process-observations.jsonl",
                        route.encoded({**samples[0], "image_sha256": "0" * 64})
                        + route.encoded(samples[1])),
                }
                for label, (relative, data) in mutations.items():
                    original = (root / relative).read_bytes()
                    write(relative, data)
                    with self.subTest(label=label), self.assertRaises(ValueError):
                        verify()
                    write(relative, original)
                selection["lane"] = LANE.replace("debug-g", "optimized-opt")
                with self.assertRaises(ValueError):
                    verify()
                selection["lane"] = LANE
                for key, wrong in (("target", "macosArm64"), ("runtime", "macOS ARM64"),
                                   ("version", "minimum"), ("configuration", "optimized-opt")):
                    original = receipt[key]
                    receipt[key] = wrong
                    with self.subTest(key=key), self.assertRaises(ValueError):
                        verify()
                    receipt[key] = original


if __name__ == "__main__":
    unittest.main()
