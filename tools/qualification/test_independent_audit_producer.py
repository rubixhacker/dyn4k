import copy
import hashlib
import json
import os
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import independent_adapter
import independent_audit_producer as producer
import independent_gates
import qualify


ROOT = Path(__file__).resolve().parents[2]


def _patch_archive_member_open(callback, windows_directory_type=None):
    if windows_directory_type is None and os.name == "nt":
        from safari_windows_file import LockedDirectory
        windows_directory_type = LockedDirectory
    if windows_directory_type is not None:
        original = windows_directory_type.open_file

        def opened(directory, name):
            handle = original(directory, name)
            if name == "payload.bin":
                try:
                    callback()
                except BaseException:
                    os.close(handle)
                    raise
            return handle

        return mock.patch.object(windows_directory_type, "open_file", opened)

    original = independent_gates.os.open

    def opened(path, flags, *args, **kwargs):
        handle = original(path, flags, *args, **kwargs)
        if Path(path).name == "payload.bin":
            try:
                callback()
            except BaseException:
                os.close(handle)
                raise
        return handle

    return mock.patch.object(independent_gates.os, "open", opened)


class IndependentAuditProducerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.candidate = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
        self.suite = independent_gates.load_approved_manifest(ROOT)
        self.hashes = {target: {module: hashlib.sha256(
            f"fixture:{target}:{module}".encode()).hexdigest()
            for module in qualify.MODULES} for target in qualify.matrix_targets()}
        self.staged = {"candidate_sha": self.candidate, "status": "PASSED",
                       "artifacts": [{"path": qualify.target_binary_path(module, target),
                                      "sha256": value}
                                     for target, modules in self.hashes.items()
                                     for module, value in modules.items()]}
        self.candidate_manifest = {
            "candidate_sha": self.candidate,
            "suite_manifest_sha256": independent_gates.digest(self.suite),
            "audit_manifest_sha256": qualify.manifest_digest(self.staged),
            "lanes": {lane: {"artifact_hashes": copy.deepcopy(self.hashes[spec["target"]]),
                             "runtime_identity": f"fixture:{lane}"}
                      for lane, spec in self.suite["lanes"].items()}}
        self.observations = {"schema": 1, "candidate_sha": self.candidate,
                             "lanes": {lane: {"archives": {}, "signed_fields": {}}
                                       for lane in self.suite["lanes"]}}
        self.candidate_path = self.root / "candidate.json"
        self.stage_path = self.root / "staged.json"
        self.observations_path = self.root / "observations.json"
        self.private = self.root / "test-only-private.pem"
        self.public = self.root / "public.pem"
        subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out",
                        str(self.private)], check=True, capture_output=True)
        subprocess.run(["openssl", "pkey", "-in", str(self.private), "-pubout", "-out",
                        str(self.public)], check=True, capture_output=True)
        der = subprocess.check_output(["openssl", "pkey", "-pubin", "-in",
                                       str(self.public), "-outform", "DER"])
        self.fingerprint = hashlib.sha256(der).hexdigest()
        self.write_inputs()

    def write_inputs(self):
        self.candidate_path.write_text(json.dumps(self.candidate_manifest))
        self.stage_path.write_text(json.dumps(self.staged))
        self.observations_path.write_text(json.dumps(self.observations))

    def prepare(self, output=None):
        with mock.patch("qualify.verify_audit_against_staging"), mock.patch(
                "qualify.require_clean_checkout"):
            return producer.prepare(ROOT, self.candidate, self.candidate_path,
                                    self.stage_path, self.observations_path,
                                    output or self.root / "prepared", self.fingerprint)

    def sign(self, prepared):
        signature = self.root / "audit.sig"
        subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey", str(self.private),
                        "-rawin", "-in", str(prepared / "audit.json"), "-out",
                        str(signature)], check=True, capture_output=True)
        return signature, self.public, self.fingerprint

    def test_complete_empty_map_detached_signature_and_public_assembly(self):
        prepared = self.prepare()
        archive_map = json.loads((prepared / "archive-map.json").read_bytes())
        self.assertEqual(set(self.suite["lanes"]), set(archive_map["lanes"]))
        self.assertTrue(all(not paths for paths in archive_map["lanes"].values()))
        self.assertEqual((prepared / "audit.json").read_bytes(),
                         producer.canonical_json(json.loads((prepared / "audit.json").read_bytes())))
        signature, public, fingerprint = self.sign(prepared)
        with mock.patch("qualify.verify_audit_against_staging"), mock.patch(
                "qualify.require_clean_checkout"):
            result = producer.finalize(ROOT, self.candidate, prepared, self.candidate_path,
                                       self.stage_path, signature, public, fingerprint,
                                       self.observations_path)
        self.assertEqual(112, result["counts"]["NOT_RUN"])
        self.assertEqual(0, result["counts"]["PASSED"])
        self.assertEqual("NOT_RUN", result["status"])

    def test_wrong_candidate_stage_and_signature_controls(self):
        prepared = self.prepare()
        signature, public, fingerprint = self.sign(prepared)
        with self.assertRaisesRegex(ValueError, "candidate"):
            producer.prepare(ROOT, "0" * 40, self.candidate_path, self.stage_path,
                             self.observations_path, self.root / "wrong", self.fingerprint)
        changed = copy.deepcopy(self.staged)
        changed["artifacts"][0]["sha256"] = "0" * 64
        self.stage_path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, "staged audit bytes"):
            producer.finalize(ROOT, self.candidate, prepared, self.candidate_path,
                              self.stage_path, signature, public, fingerprint,
                              self.observations_path)
        self.stage_path.write_text(json.dumps(self.staged))
        for bad_signature, bad_key, bad_fingerprint, reason in (
                (None, public, fingerprint, "signature"),
                (signature, None, fingerprint, "public key"),
                (signature, public, "0" * 64, "fingerprint")):
            with self.assertRaisesRegex(ValueError, reason):
                producer.finalize(ROOT, self.candidate, prepared, self.candidate_path,
                                  self.stage_path, bad_signature, bad_key, bad_fingerprint,
                                  self.observations_path)
        (prepared / "audit.json").write_bytes((prepared / "audit.json").read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "audit bytes"):
            producer.finalize(ROOT, self.candidate, prepared, self.candidate_path,
                              self.stage_path, signature, public, fingerprint,
                              self.observations_path)

    def test_self_reported_green_and_changed_archive_fail_preflight(self):
        lane = next(iter(self.suite["lanes"]))
        archive = self.root / "attempt"
        archive.mkdir()
        (archive / "receipt.json").write_text(json.dumps({"status": "PASSED"}))
        self.observations["lanes"][lane]["archives"]["staged-consumer"] = str(archive)
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, "signed route fields are incomplete"):
            self.prepare()
        self.observations["lanes"][lane]["signed_fields"] = {
            field: "0" * 64 for field in producer.ROUTE_FIELDS["jvm"]}
        self.write_inputs()
        rejected_green = self.prepare(self.root / "prepared-rejected-green")
        green_audit = json.loads((rejected_green / "audit.json").read_bytes())
        self.assertEqual("FAILED", green_audit["preflight_results"][lane]["gates"]["staged-consumer"])
        self.observations["lanes"][lane]["signed_fields"].clear()
        self.write_inputs()
        (archive / "receipt.json").write_text(json.dumps({"status": "FAILED"}))
        malformed = self.prepare()
        failed = json.loads((malformed / "audit.json").read_bytes())
        self.assertEqual("FAILED", failed["preflight_results"][lane]["gates"]["staged-consumer"])
        signature, public, fingerprint = self.sign(malformed)
        (archive / "receipt.json").write_text(json.dumps({"status": "FAILED", "changed": True}))
        with self.assertRaisesRegex(ValueError, "archive bytes or timestamps changed"):
            producer.finalize(ROOT, self.candidate, malformed, self.candidate_path,
                              self.stage_path, signature, public, fingerprint,
                              self.observations_path)
        self.observations["lanes"][lane]["archives"].clear()
        self.write_inputs()
        prepared = self.prepare(self.root / "prepared-empty")
        signature, public, fingerprint = self.sign(prepared)
        self.observations["lanes"][lane]["archives"]["staged-consumer"] = str(archive)
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, "observation bytes"):
            producer.finalize(ROOT, self.candidate, prepared, self.candidate_path,
                              self.stage_path, signature, public, fingerprint,
                              self.observations_path)

    def test_snapshot_rejects_archive_alias_and_symbolic_member(self):
        archive = self.root / "archive"
        archive.mkdir()
        (archive / "receipt.json").write_text("{}")
        self.assertIn("receipt.json", producer._snapshot(archive)["files"])
        with self.assertRaisesRegex(ValueError, "archive path"):
            producer._snapshot(archive / ".." / "archive")
        alias = self.root / "alias"
        try:
            alias.symlink_to(archive, target_is_directory=True)
        except OSError:
            pass
        else:
            with self.assertRaisesRegex(ValueError, "archive path"):
                producer._snapshot(alias)
        member = archive / "linked-receipt"
        try:
            member.symlink_to(archive / "receipt.json")
        except OSError:
            pass
        else:
            with self.assertRaisesRegex(ValueError, "symbolic or reparse archive path"):
                producer._snapshot(archive)

    def test_archive_scan_rejects_hardlinks_duplicate_entries_and_mutation(self):
        archive = self.root / "strict-archive"
        archive.mkdir()
        receipt = archive / "receipt.json"
        receipt.write_text("{}")
        payload = archive / "payload.bin"
        payload.write_bytes(b"original")
        self.assertIn("payload.bin", producer._snapshot(archive)["files"])
        self.assertIsInstance(independent_gates.archive_digest(archive), str)

        alias = archive / "hardlink.bin"
        os.link(payload, alias)
        for scan in (producer._snapshot, independent_gates.archive_digest):
            with self.subTest(scan=scan, alteration="hardlink"):
                with self.assertRaisesRegex(ValueError, "hardlinked archive file"):
                    scan(archive)
        alias.unlink()

        original_scandir = os.scandir

        class ListedEntries:
            def __init__(self, entries):
                self.entries = entries

            def __enter__(self):
                return iter(self.entries)

            def __exit__(self, *_):
                return False

        def duplicate_scandir(path):
            with original_scandir(path) as entries:
                listed = list(entries)
            is_root = (os.fstat(path).st_ino == archive.stat().st_ino
                       if isinstance(path, int) else Path(path) == archive)
            if is_root:
                listed.append(next(entry for entry in listed if entry.name == "payload.bin"))
            return ListedEntries(listed)

        with mock.patch.object(independent_gates.os, "scandir", side_effect=duplicate_scandir):
            for scan in (producer._snapshot, independent_gates.archive_digest):
                with self.subTest(scan=scan, alteration="duplicate"):
                    with self.assertRaisesRegex(ValueError, "duplicate archive path"):
                        scan(archive)

        original_read = independent_gates.os.read
        def mutate_during_read(handle, size):
            chunk = original_read(handle, size)
            if chunk and os.fstat(handle).st_ino == payload.stat().st_ino:
                payload.write_bytes(b"changed")
            return chunk

        for scan in (producer._snapshot, independent_gates.archive_digest):
            payload.write_bytes(b"original")
            with self.subTest(scan=scan, alteration="mutation"), mock.patch.object(
                    independent_gates.os, "read", side_effect=mutate_during_read):
                with self.assertRaisesRegex(ValueError, "archive file changed during read"):
                    scan(archive)

    def test_archive_scan_rejects_failed_descendant_enumeration(self):
        archive = self.root / "unreadable-archive"
        hidden = archive / "hidden"
        hidden.mkdir(parents=True)
        (archive / "receipt.json").write_text("{}")
        (hidden / "unlisted.bin").write_bytes(b"must be included")
        original_scandir = os.scandir

        def fail_hidden(path):
            target = (os.fstat(path).st_ino == hidden.stat().st_ino
                      if isinstance(path, int) else Path(path) == hidden)
            if target:
                raise PermissionError("fixture denies descendant enumeration")
            return original_scandir(path)

        for scan in (producer._snapshot, independent_gates.archive_digest):
            with self.subTest(scan=scan), mock.patch.object(
                    independent_gates.os, "scandir", side_effect=fail_hidden):
                with self.assertRaisesRegex(PermissionError, "descendant enumeration"):
                    scan(archive)

    def test_archive_scan_accepts_path_and_handle_ctime_with_distinct_meanings(self):
        archive = self.root / "ctime-archive"
        archive.mkdir()
        (archive / "receipt.json").write_text("{}")
        payload = archive / "payload.bin"
        payload.write_bytes(b"unchanged")
        original_fstat = os.fstat

        class HandleState:
            def __init__(self, state):
                self.state = state

            def __getattr__(self, name):
                if name == "st_ctime_ns":
                    return self.state.st_ctime_ns + 1_000_000_000
                return getattr(self.state, name)

        def windows_handle_ctime(fd):
            state = original_fstat(fd)
            return HandleState(state) if state.st_ino == payload.stat().st_ino else state

        with mock.patch.object(independent_gates.os, "fstat", side_effect=windows_handle_ctime):
            self.assertIn("payload.bin", producer._snapshot(archive)["files"])
            self.assertIsInstance(independent_gates.archive_digest(archive), str)

    def test_archive_scan_accepts_unrelated_archive_ancestor_sibling(self):
        archive = self.root / "sibling-archive"
        archive.mkdir()
        (archive / "receipt.json").write_text("{}")
        (archive / "payload.bin").write_bytes(b"stable")
        expected = independent_gates.archive_digest(archive)

        for index, scan in enumerate((producer._snapshot, independent_gates.archive_digest)):
            created = False

            def add_sibling():
                nonlocal created
                if not created:
                    created = True
                    (self.root / f"unrelated-{index}.txt").write_text("sibling")

            with self.subTest(scan=scan), _patch_archive_member_open(add_sibling):
                result = scan(archive)
                self.assertTrue(created)
                if scan is independent_gates.archive_digest:
                    self.assertEqual(expected, result)
                else:
                    self.assertIn("payload.bin", result["files"])

    def test_archive_scan_rejects_new_archive_member_during_read(self):
        archive = self.root / "changed-archive"
        archive.mkdir()
        (archive / "receipt.json").write_text("{}")
        (archive / "payload.bin").write_bytes(b"stable")

        for scan in (producer._snapshot, independent_gates.archive_digest):
            new_member = archive / f"new-{scan.__name__}.bin"
            changed = False

            def add_member():
                nonlocal changed
                if not changed:
                    changed = True
                    new_member.write_bytes(b"concurrent")

            with self.subTest(scan=scan), _patch_archive_member_open(add_member):
                with self.assertRaisesRegex(ValueError, "archive entry changed during scan"):
                    scan(archive)
                self.assertTrue(changed)

    def test_windows_modelled_member_open_injection_reaches_callback(self):
        payload = self.root / "payload.bin"
        payload.write_bytes(b"stable")
        created = []

        class WindowsHandleModel:
            def open_file(self, name):
                return os.open(self.path / name, os.O_RDONLY)

        directory = WindowsHandleModel()
        directory.path = self.root
        with _patch_archive_member_open(lambda: created.append("opened"),
                                        windows_directory_type=WindowsHandleModel):
            other = self.root / "receipt.json"
            other.write_bytes(b"{}")
            handle = directory.open_file("receipt.json")
            os.close(handle)
            self.assertEqual([], created)
            handle = directory.open_file("payload.bin")
            try:
                self.assertEqual(b"stable", os.read(handle, 6))
            finally:
                os.close(handle)
        self.assertEqual(["opened"], created)

    @unittest.skipUnless(os.name == "posix", "requires POSIX parent replacement")
    def test_archive_scan_does_not_accept_transient_parent_swap(self):
        visible = self.root / "visible"
        archive = visible / "archive"
        archive.mkdir(parents=True)
        (archive / "receipt.json").write_text("{}")
        (archive / "payload.bin").write_bytes(b"approved")
        attacker = self.root / "attacker"
        alternate = attacker / "archive"
        alternate.mkdir(parents=True)
        (alternate / "receipt.json").write_text("{}")
        (alternate / "payload.bin").write_bytes(b"outside")
        original_identity = independent_gates._archive_identity
        parked = self.root / "parked-visible"

        for scan in (producer._snapshot, independent_gates.archive_digest):
            calls = 0
            swapped = False

            def transient_swap(path):
                nonlocal calls, swapped
                if Path(path) == archive / "payload.bin":
                    calls += 1
                    if calls == 1:
                        visible.rename(parked)
                        visible.symlink_to(attacker, target_is_directory=True)
                        swapped = True
                    result = original_identity(path)
                    if calls == 3 and swapped:
                        visible.unlink()
                        parked.rename(visible)
                        swapped = False
                    return result
                return original_identity(path)

            try:
                with self.subTest(scan=scan), mock.patch.object(
                        independent_gates, "_archive_identity", side_effect=transient_swap):
                    with self.assertRaisesRegex(ValueError, "archive file identity changed"):
                        scan(archive)
                self.assertGreater(calls, 0)
            finally:
                if swapped:
                    visible.unlink()
                    parked.rename(visible)

    @unittest.skipUnless(os.name == "posix", "requires POSIX ancestor symlink replacement")
    def test_archive_scan_rejects_ancestor_alias_during_root_open(self):
        visible = self.root / "visible"
        archive = visible / "archive"
        archive.mkdir(parents=True)
        (archive / "receipt.json").write_text("{}")
        parked = self.root / "parked-visible"
        original_open = os.open

        for scan in (producer._snapshot, independent_gates.archive_digest):
            swapped = False

            def alias_during_open(path, flags, *args, **kwargs):
                nonlocal swapped
                if path == "visible" and "dir_fd" in kwargs and not swapped:
                    visible.rename(parked)
                    visible.symlink_to(parked, target_is_directory=True)
                    swapped = True
                return original_open(path, flags, *args, **kwargs)

            try:
                with self.subTest(scan=scan), mock.patch.object(
                        independent_gates.os, "open", side_effect=alias_during_open):
                    with self.assertRaises(OSError):
                        scan(archive)
                    self.assertTrue(swapped)
            finally:
                if swapped:
                    visible.unlink()
                    parked.rename(visible)

    @unittest.skipUnless(os.name == "posix", "requires POSIX descriptor traversal")
    def test_archive_scan_rejects_missing_directory_nofollow_capability(self):
        archive = self.root / "no-nofollow-archive"
        archive.mkdir()
        (archive / "receipt.json").write_text("{}")
        with mock.patch.object(independent_gates.os, "O_NOFOLLOW", None):
            for scan in (producer._snapshot, independent_gates.archive_digest):
                with self.subTest(scan=scan):
                    with self.assertRaisesRegex(ValueError, "safe open is unavailable"):
                        scan(archive)

    def test_mocked_internal_junction_and_generic_reparse_are_rejected(self):
        archive = self.root / "mocked-reparse"
        member = archive / "inside"
        member.mkdir(parents=True)
        (archive / "receipt.json").write_text("{}")
        original_junction = Path.is_junction
        with mock.patch.object(Path, "is_junction", lambda path: (
                path == member or original_junction(path))):
            for scan in (producer._snapshot, independent_gates.archive_digest):
                with self.subTest(scan=scan, alteration="junction"):
                    with self.assertRaisesRegex(ValueError, "reparse archive path"):
                        scan(archive)

        original_lstat = Path.lstat
        class ReparseState:
            st_file_attributes = stat.FILE_ATTRIBUTE_REPARSE_POINT

            def __init__(self, state):
                self.state = state

            def __getattr__(self, name):
                return getattr(self.state, name)

        def reparse_lstat(path):
            state = original_lstat(path)
            return ReparseState(state) if path == member else state

        with mock.patch.object(Path, "lstat", reparse_lstat):
            for scan in (producer._snapshot, independent_gates.archive_digest):
                with self.subTest(scan=scan, alteration="generic-reparse"):
                    with self.assertRaisesRegex(ValueError, "reparse archive path"):
                        scan(archive)

    @unittest.skipUnless(os.name == "posix", "requires POSIX replacement of an open file")
    def test_archive_scan_rejects_same_bytes_replaced_during_read(self):
        archive = self.root / "replacement-archive"
        archive.mkdir()
        (archive / "receipt.json").write_text("{}")
        payload = archive / "payload.bin"
        original_read = independent_gates.os.read

        for scan in (producer._snapshot, independent_gates.archive_digest):
            payload.write_bytes(b"same bytes")
            mtime = payload.stat().st_mtime_ns
            replaced = False

            def replace_during_read(handle, size):
                nonlocal replaced
                chunk = original_read(handle, size)
                if (chunk and not replaced
                        and os.fstat(handle).st_ino == payload.stat().st_ino):
                    replacement = archive / "replacement.tmp"
                    replacement.write_bytes(b"same bytes")
                    os.utime(replacement, ns=(mtime, mtime))
                    os.replace(replacement, payload)
                    replaced = True
                return chunk

            with self.subTest(scan=scan), mock.patch.object(
                    independent_gates.os, "read", side_effect=replace_during_read):
                with self.assertRaisesRegex(ValueError, "archive file (identity changed|changed during read)"):
                    scan(archive)
            self.assertTrue(replaced)

    @unittest.skipUnless(os.name == "nt", "requires actual Windows reparse and hardlink support")
    def test_windows_junction_reparse_and_hardlink_fail_closed(self):
        archive = self.root / "windows-archive"
        archive.mkdir()
        (archive / "receipt.json").write_text("{}")
        target = archive / "target"
        target.mkdir()
        junction = archive / "junction"
        subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(target)],
                       check=True, capture_output=True)
        for scan in (producer._snapshot, independent_gates.archive_digest):
            with self.subTest(scan=scan, alteration="junction"):
                with self.assertRaisesRegex(ValueError, "reparse archive path"):
                    scan(archive)
        junction.rmdir()

        payload = archive / "payload.bin"
        payload.write_bytes(b"payload")
        link = archive / "symbolic.bin"
        link.symlink_to(payload)
        for scan in (producer._snapshot, independent_gates.archive_digest):
            with self.subTest(scan=scan, alteration="file-reparse"):
                with self.assertRaisesRegex(ValueError, "reparse archive path"):
                    scan(archive)
        link.unlink()

        hardlink = archive / "hardlink.bin"
        os.link(payload, hardlink)
        for scan in (producer._snapshot, independent_gates.archive_digest):
            with self.subTest(scan=scan, alteration="hardlink"):
                with self.assertRaisesRegex(ValueError, "hardlinked archive file"):
                    scan(archive)

    @unittest.skipUnless(os.name == "nt", "requires Windows directory share locks")
    def test_windows_archive_parent_cannot_swap_while_scanning(self):
        visible = self.root / "visible"
        archive = visible / "archive"
        archive.mkdir(parents=True)
        (archive / "receipt.json").write_text("{}")
        (archive / "payload.bin").write_bytes(b"stable")
        parked = self.root / "parked-visible"
        original_scandir = os.scandir

        for scan in (producer._snapshot, independent_gates.archive_digest):
            attempted = False
            blocked = False

            def attempt_parent_swap(path):
                nonlocal attempted, blocked
                if Path(path) == archive and not attempted:
                    attempted = True
                    try:
                        visible.rename(parked)
                    except OSError:
                        blocked = True
                    else:
                        parked.rename(visible)
                return original_scandir(path)

            with self.subTest(scan=scan), mock.patch.object(
                    independent_gates.os, "scandir", side_effect=attempt_parent_swap):
                scan(archive)
                self.assertTrue(attempted)
                self.assertTrue(blocked)

    @unittest.skipUnless(os.name == "nt", "requires Windows path and handle timestamps")
    def test_windows_modified_file_with_creation_ctime_is_accepted(self):
        archive = self.root / "windows-ctime-archive"
        archive.mkdir()
        (archive / "receipt.json").write_text("{}")
        payload = archive / "payload.bin"
        payload.write_bytes(b"original")
        time.sleep(0.1)
        payload.write_bytes(b"unchanged")
        descriptor = os.open(payload, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        try:
            self.assertNotEqual(payload.lstat().st_ctime_ns,
                                os.fstat(descriptor).st_ctime_ns)
        finally:
            os.close(descriptor)
        self.assertIn("payload.bin", producer._snapshot(archive)["files"])
        self.assertIsInstance(independent_gates.archive_digest(archive), str)

    def test_native_cross_preparation_binds_only_schema3_build_fields(self):
        lane = "linuxArm64:Linux ARM64:current:debug-g"
        archive = self.root / "cross-attempt"
        archive.mkdir()
        receipt = {"schema": 3, "status": "PASSED"}
        (archive / "receipt.json").write_text(json.dumps(receipt))
        fields = {key: key for key in
                  producer.ROUTE_FIELDS["native-host"] -
                  {"expected_native_host_executables"}}
        fields.update({"expected_native_build_archive_sha256": "a" * 64,
                       "expected_native_build_observer": {
                           "path": str(self.root / "observer"),
                           "events_sha256": "d" * 64,
                           "witness_sha256": "e" * 64},
                       "expected_native_build_host": {"system": "Linux",
                                                       "machine": "x86_64"},
                       "expected_native_build_executables": {
                           "core": "b" * 64, "facade": "c" * 64}})
        observation = self.observations["lanes"][lane]
        observation["archives"]["staged-consumer"] = str(archive)
        observation["signed_fields"] = fields
        self.write_inputs()
        prepared = self.prepare()
        signed = json.loads((prepared / "audit.json").read_bytes())["lanes"][lane]
        for key, value in fields.items():
            self.assertEqual(value, signed[key])
        for index, key in enumerate(sorted(producer.CROSS_FIELDS)):
            observation["signed_fields"] = {name: value for name, value in fields.items()
                                             if name != key}
            self.write_inputs()
            with self.assertRaisesRegex(ValueError, "signed route fields are incomplete"):
                self.prepare(self.root / f"missing-{index}")
        observation["signed_fields"] = dict(fields)
        observation["signed_fields"]["expected_native_host_executables"] = {
            "core": "b" * 64, "facade": "c" * 64}
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, "unrecognized signed route field"):
            self.prepare(self.root / "cross-extra")
        receipt["schema"] = 2
        (archive / "receipt.json").write_text(json.dumps(receipt))
        observation["signed_fields"] = dict(fields)
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, "unrecognized signed route field"):
            self.prepare(self.root / "ordinary-extra")
        observation["archives"].clear()
        observation["signed_fields"].clear()
        self.write_inputs()
        prepared = self.prepare(self.root / "arm-not-run")
        preflight = json.loads((prepared / "audit.json").read_bytes())[
            "preflight_results"][lane]["gates"]["staged-consumer"]
        self.assertEqual("NOT_RUN", preflight)

    def test_browser_schema3_requires_separate_signed_launcher_image(self):
        lane = "wasmJs:Chromium:current:development"
        archive = self.root / "browser-attempt"
        archive.mkdir()
        (archive / "receipt.json").write_text(json.dumps({"schema": 3,
                                                           "status": "PASSED"}))
        observation = self.observations["lanes"][lane]
        observation["archives"]["staged-consumer"] = str(archive)
        fields = {key: key for key in producer.ROUTE_FIELDS["browser"]}
        fields.update({"expected_browser_responses": {},
                       "expected_execution_witness": {"path": str(self.root / "witness"),
                                                      "sha256": "a" * 64}})
        observation["signed_fields"] = fields
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, "signed route fields are incomplete"):
            self.prepare()
        fields["expected_build_launcher_image"] = {
            "path": "/usr/bin/bash", "sha256": "b" * 64}
        self.write_inputs()
        prepared = self.prepare(self.root / "browser-prepared")
        signed = json.loads((prepared / "audit.json").read_bytes())["lanes"][lane]
        self.assertEqual(signed["expected_build_launcher_image"],
                         fields["expected_build_launcher_image"])
        unrelated = next(name for name in self.suite["lanes"] if name.startswith("jvm:"))
        self.observations["lanes"][unrelated]["signed_fields"] = {
            "expected_build_launcher_image": fields["expected_build_launcher_image"]}
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, "unrecognized signed route field"):
            self.prepare(self.root / "unrelated-prepared")

    def test_schema4_chromium_uses_browser_witness_without_launcher_claim(self):
        for target in ("js", "wasmJs"):
            with self.subTest(target=target):
                lane = f"{target}:Chromium:current:development"
                archive = self.root / f"chromium-schema4-{target}"
                archive.mkdir()
                (archive / "receipt.json").write_text(json.dumps({
                    "schema": 4, "status": "PASSED", "candidate_sha": self.candidate,
                    "lane": lane}))
                observation = self.observations["lanes"][lane]
                observation["archives"]["staged-consumer"] = str(archive)
                fields = observation["signed_fields"]
                fields.update({"expected_browser_toolchain": {},
                               "expected_browser_bundles": {}})
                self.write_inputs()
                with self.assertRaisesRegex(ValueError, "signed route fields are incomplete"):
                    self.prepare(self.root / f"missing-schema4-witness-{target}")
                fields["expected_browser_responses"] = {}
                fields["expected_execution_witness"] = {
                    "path": str(self.root / f"absent-browser-witness-{target}"),
                    "sha256": "a" * 64}
                self.write_inputs()
                prepared = self.prepare(self.root / f"schema4-browser-only-{target}")
                audit = json.loads((prepared / "audit.json").read_bytes())
                self.assertNotEqual("PASSED", audit["preflight_results"][lane]["gates"][
                    "staged-consumer"])
                self.assertNotIn("expected_build_launcher_image", audit["lanes"][lane])
                fields["expected_build_launcher_image"] = {
                    "path": "/usr/bin/false", "sha256": "b" * 64}
                self.write_inputs()
                with self.assertRaisesRegex(ValueError, "unrecognized signed route field"):
                    self.prepare(self.root / f"unused-schema4-launcher-{target}")
                del fields["expected_build_launcher_image"]

    def test_schema5_js_and_wasm_preparer_require_external_signed_evidence(self):
        for target, family in (("js", "Firefox"), ("wasmJs", "Safari")):
            lane = f"{target}:{family}:current:development"
            archive = self.root / f"{target}-{family}"
            archive.mkdir()
            (archive / "receipt.json").write_text(json.dumps({
                "schema": 5, "status": "PASSED", "candidate_sha": self.candidate,
                "lane": lane}))
            fields = self.observations["lanes"][lane]["signed_fields"]
            self.observations["lanes"][lane]["archives"]["staged-consumer"] = str(archive)
            fields.update({"expected_browser_toolchain": {},
                           "expected_browser_bundles": {}})
            self.write_inputs()
            with self.subTest(lane=lane), self.assertRaisesRegex(
                    ValueError, "signed route fields are incomplete"):
                self.prepare(self.root / f"missing-{target}")
            fields["expected_browser_responses"] = {}
            fields["expected_execution_witness"] = {"path": str(self.root / "absent"),
                                                    "sha256": "0" * 64}
            self.write_inputs()
            prepared = self.prepare(self.root / f"preflight-{target}")
            audit = json.loads((prepared / "audit.json").read_bytes())
            self.assertEqual("FAILED", audit["preflight_results"][lane]["gates"][
                "staged-consumer"])
            self.assertEqual(fields["expected_execution_witness"],
                             audit["lanes"][lane]["expected_execution_witness"])
            fields["expected_build_launcher_image"] = {
                "path": "/usr/bin/false", "sha256": "b" * 64}
            self.write_inputs()
            with self.assertRaisesRegex(ValueError, "unrecognized signed route field"):
                self.prepare(self.root / f"unused-schema5-launcher-{target}")
            del fields["expected_build_launcher_image"]

    def test_rejects_wrong_lane_identity_and_unsigned_replacement(self):
        lane = next(iter(self.suite["lanes"]))
        self.candidate_manifest["lanes"][lane]["runtime_identity"] = ""
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, "candidate lane artifact or runtime"):
            self.prepare()
        self.candidate_manifest["lanes"][lane]["runtime_identity"] = f"fixture:{lane}"
        self.candidate_manifest["lanes"][lane]["artifact_hashes"]["dyn4k-core"] = "0" * 64
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, "candidate lane artifact or runtime"):
            self.prepare()
        self.candidate_manifest["lanes"][lane]["artifact_hashes"] = self.hashes[
            self.suite["lanes"][lane]["target"]]
        self.write_inputs()
        missing = self.staged["artifacts"].pop()
        self.candidate_manifest["audit_manifest_sha256"] = qualify.manifest_digest(self.staged)
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, "21 target binary hashes"):
            self.prepare()
        self.staged["artifacts"].append(missing)
        self.candidate_manifest["audit_manifest_sha256"] = qualify.manifest_digest(self.staged)
        self.write_inputs()
        prepared = self.prepare()
        signature, public, fingerprint = self.sign(prepared)
        audit_path = prepared / "audit.json"
        request_path = prepared / "signing-request.json"
        replacement = json.loads(audit_path.read_bytes())
        replacement["lanes"][lane]["expected_runtime_identity"] = "forged runner"
        audit_path.write_bytes(producer.canonical_json(replacement))
        request = json.loads(request_path.read_bytes())
        request["audit_sha256"] = hashlib.sha256(audit_path.read_bytes()).hexdigest()
        request_path.write_bytes(producer.canonical_json(request))
        with self.assertRaisesRegex(ValueError, "signature is unverified"):
            producer.finalize(ROOT, self.candidate, prepared, self.candidate_path,
                              self.stage_path, signature, public, fingerprint,
                              self.observations_path)

    def test_signed_audit_binds_exact_candidate_and_staged_input_bytes(self):
        for index, (path, key) in enumerate((
                (self.candidate_path, "candidate_manifest_bytes_sha256"),
                (self.stage_path, "staged_audit_bytes_sha256"))):
            prepared = self.prepare(self.root / f"prepared-{index}")
            signature, public, fingerprint = self.sign(prepared)
            request_path = prepared / "signing-request.json"
            request = json.loads(request_path.read_bytes())
            original = path.read_bytes()
            path.write_bytes(original + b" ")
            request[key] = hashlib.sha256(path.read_bytes()).hexdigest()
            request_path.write_bytes(producer.canonical_json(request))
            with mock.patch("qualify.verify_audit_against_staging"), mock.patch(
                    "qualify.require_clean_checkout"):
                with self.assertRaisesRegex(ValueError, "signed .*input bytes"):
                    producer.finalize(ROOT, self.candidate, prepared, self.candidate_path,
                                      self.stage_path, signature, public, fingerprint,
                                      self.observations_path)
            path.write_bytes(original)

    def test_verified_jvm_mode_publication_survives_empty_archive_finalization(self):
        lane = "jvm:Java:minimum:no-optimize"
        hashes = {module: hashlib.sha256(f"mode:{module}".encode()).hexdigest()
                  for module in qualify.MODULES}
        binding = {"publication_archive": str(self.root / "mode-publication"),
                   "archive_digest": "a" * 64, "artifact_hashes": hashes}
        self.candidate_manifest["lanes"][lane]["artifact_hashes"] = hashes
        self.candidate_manifest["lanes"][lane]["jvm_mode_publication"] = binding
        self.write_inputs()
        with mock.patch("qualify.verify_audit_against_staging"), mock.patch(
                "qualify.require_clean_checkout"), mock.patch(
                "qualify.verify_jvm_mode_publication", return_value=True) as mode_check:
            prepared = producer.prepare(
                ROOT, self.candidate, self.candidate_path, self.stage_path,
                self.observations_path, self.root / "prepared", self.fingerprint)
            signed = json.loads((prepared / "audit.json").read_bytes())
            self.assertEqual(binding["publication_archive"], signed["lanes"][lane].get(
                "expected_mode_publication_path"))
            self.assertEqual(binding["archive_digest"], signed["lanes"][lane].get(
                "expected_mode_publication_digest"))
            signature, public, fingerprint = self.sign(prepared)
            result = producer.finalize(
                ROOT, self.candidate, prepared, self.candidate_path, self.stage_path,
                signature, public, fingerprint, self.observations_path)
            for field, wrong in (("expected_mode_publication_path", str(self.root / "wrong")),
                                 ("expected_mode_publication_digest", "0" * 64)):
                self.observations["lanes"][lane]["signed_fields"] = {field: wrong}
                self.write_inputs()
                with self.assertRaisesRegex(ValueError, "signed JVM mode publication differs"):
                    producer.prepare(ROOT, self.candidate, self.candidate_path,
                                     self.stage_path, self.observations_path,
                                     self.root / f"wrong-{field}", self.fingerprint)
        self.assertGreaterEqual(mode_check.call_count, 2)
        self.assertEqual(112, result["counts"]["NOT_RUN"])
        self.assertEqual(0, result["counts"]["PASSED"])

    def test_failed_archive_mutation_during_public_assembly_is_rejected(self):
        lane = next(iter(self.suite["lanes"]))
        archive = self.root / "failed-attempt"
        archive.mkdir()
        (archive / "receipt.json").write_text(json.dumps({"status": "FAILED"}))
        self.observations["lanes"][lane]["archives"]["staged-artifacts"] = str(archive)
        self.write_inputs()
        prepared = self.prepare()
        signed = json.loads((prepared / "audit.json").read_bytes())
        self.assertEqual("FAILED", signed["preflight_results"][lane]["gates"]["staged-artifacts"])
        signature, public, fingerprint = self.sign(prepared)
        original_assemble = independent_adapter.assemble_lanes

        def mutate_then_assemble(*args, **kwargs):
            (archive / "extra.txt").write_text("changed after snapshot")
            return original_assemble(*args, **kwargs)

        with mock.patch("qualify.verify_audit_against_staging"), mock.patch(
                "qualify.require_clean_checkout"), mock.patch.object(
                producer.independent_adapter, "assemble_lanes",
                side_effect=mutate_then_assemble):
            with self.assertRaisesRegex(ValueError, "archive bytes or timestamps changed after public assembly"):
                producer.finalize(ROOT, self.candidate, prepared, self.candidate_path,
                                  self.stage_path, signature, public, fingerprint,
                                  self.observations_path)


if __name__ == "__main__":
    unittest.main()
