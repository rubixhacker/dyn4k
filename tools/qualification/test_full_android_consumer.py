import contextlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parent))
import full_android_consumer as subject


class OriginalRowTests(unittest.TestCase):
    CASE = {"id": "dyn4k-core:org.dyn4j.ExampleTest#checks",
            "classname": "org.dyn4j.ExampleTest", "method": "checks"}

    def raw(self, rows):
        lines = [
            f"INSTRUMENTATION_STATUS: class={subject.PACKAGE}.FullJourneyTest",
            "INSTRUMENTATION_STATUS: test=allInstalledCases",
            "INSTRUMENTATION_STATUS: numtests=1",
            "INSTRUMENTATION_STATUS_CODE: 1",
        ]
        for identity, status in rows:
            lines.extend((f"INSTRUMENTATION_STATUS: dyn4k_case={identity}",
                          f"INSTRUMENTATION_STATUS: dyn4k_status={status}",
                          "INSTRUMENTATION_STATUS_CODE: 0"))
        lines.extend((f"INSTRUMENTATION_STATUS: class={subject.PACKAGE}.FullJourneyTest",
                      "INSTRUMENTATION_STATUS: test=allInstalledCases",
                      "INSTRUMENTATION_STATUS: numtests=1",
                      "INSTRUMENTATION_STATUS_CODE: 0", "OK (1 test)",
                      "INSTRUMENTATION_CODE: -1"))
        return "\n".join(lines)

    def test_exact_method_row_passes(self):
        raw = self.raw([(self.CASE["id"], "PASSED")])
        xml, observed = subject.xml_from_original_rows(raw, [self.CASE], 0)
        self.assertIn(self.CASE["id"].encode(), xml)
        self.assertEqual(observed["portable"]["passed"], 1)

    def test_missing_duplicate_foreign_and_skipped_rows_fail(self):
        original = self.CASE["id"]
        for rows in ([], [(original, "PASSED"), (original, "PASSED")],
                     [(original + "Foreign", "PASSED")], [(original, "SKIPPED")],
                     [(original, "FAILED")]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                subject.xml_from_original_rows(self.raw(rows), [self.CASE], 0)

    def test_failed_process_cannot_be_normalized(self):
        with self.assertRaises(ValueError):
            subject.xml_from_original_rows(self.raw([(self.CASE["id"], "PASSED")]),
                                           [self.CASE], 1)


class ReplayIntegrityTests(unittest.TestCase):
    @staticmethod
    def dexdump(path, body=b"Class descriptor  : 'Lorg/dyn4j/Real;'\n"):
        encoded = str(path).encode()
        return (b"Processing '" + encoded + b"'...\nOpened '" + encoded +
                b"', DEX version '035'\n" + body)

    def test_missing_helper_and_foreign_source_paths_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary)
            roots = ("dyn4k-core/src/commonTest/kotlin",
                     "dyn4k/src/commonTest/kotlin",
                     "dyn4k-core/src/androidHostTest/kotlin")
            for root in roots:
                source = checkout / root / "Example.kt"
                source.parent.mkdir(parents=True)
                source.write_text("class Example\n")
            helper = checkout / roots[0] / "Helper.kt"
            helper.write_text("class Helper\n")
            original = subject.original_source_hashes(checkout)
            self.assertEqual(subject.verified_original_sources(checkout, original), original)
            missing = original.copy()
            del missing[helper.relative_to(checkout).as_posix()]
            with self.assertRaisesRegex(ValueError, "source file set"):
                subject.verified_original_sources(checkout, missing)
            for foreign in ("/etc/hosts", "../escape.kt", "README.md"):
                with self.subTest(foreign=foreign), self.assertRaises(ValueError):
                    subject.verified_original_sources(checkout, original | {foreign: "0" * 64})

    def test_invented_dexdump_descriptor_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary)
            directory = archive / "debug-dex"
            directory.mkdir()
            dex = b"test dex bytes"
            (directory / "classes.dex").write_bytes(dex)
            with zipfile.ZipFile(archive / "app.apk", "w") as apk:
                apk.writestr("classes.dex", dex)
            original = "/original/debug-dex/classes.dex"
            (directory / "classes.dex.dexdump.txt").write_bytes(
                self.dexdump(original,
                             b"Class descriptor  : 'Lorg/dyn4j/Real;'\n"
                             b"Class descriptor  : 'Lorg/dyn4j/Invented;'\n"))
            completed = mock.Mock(returncode=0,
                                  stdout=self.dexdump(directory / "classes.dex"))
            with mock.patch.object(subject.subprocess, "run", return_value=completed):
                with self.assertRaisesRegex(ValueError, "dexdump output differs"):
                    subject.archived_dex_descriptors(archive, "debug-dex", "app.apk")

    def test_relocated_dexdump_checks_only_path_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary)
            directory = archive / "debug-dex"
            directory.mkdir()
            dex = b"test dex bytes"
            (directory / "classes.dex").write_bytes(dex)
            with zipfile.ZipFile(archive / "app.apk", "w") as apk:
                apk.writestr("classes.dex", dex)
            original = "/original/debug-dex/classes.dex"
            (directory / "classes.dex.dexdump.txt").write_bytes(self.dexdump(original))
            completed = mock.Mock(returncode=0,
                                  stdout=self.dexdump(directory / "classes.dex"))
            with mock.patch.object(subject.subprocess, "run", return_value=completed):
                self.assertEqual(subject.archived_dex_descriptors(
                    archive, "debug-dex", "app.apk"), {"Lorg/dyn4j/Real;"})

    def test_dexdump_path_headers_must_match_each_input(self):
        original = "/original/debug-dex/classes.dex"
        current = "/moved/debug-dex/classes.dex"
        bad_original = self.dexdump(original).replace(
            b"Opened '/original/", b"Opened '/foreign/", 1)
        with self.assertRaisesRegex(ValueError, "dexdump path headers"):
            subject.canonical_dexdump(bad_original, "debug-dex/classes.dex")
        with self.assertRaisesRegex(ValueError, "dexdump path headers"):
            subject.canonical_dexdump(self.dexdump("/original/foreign/classes.dex"),
                                      "debug-dex/classes.dex")
        with self.assertRaisesRegex(ValueError, "dexdump path headers"):
            subject.canonical_dexdump(self.dexdump(original), "debug-dex/classes.dex",
                                      current)


class Api21DeviceTests(unittest.TestCase):
    PACKAGE = "io.github.rubixhacker.dyn4k.qualification.fullandroid"

    def test_task_serial_is_explicit_and_bounded(self):
        self.assertEqual(subject.adb_for_serial("emulator-5560")[-4:],
                         ["-P", "5038", "-s", "emulator-5560"])
        for serial in ("emulator-5559", "device-5560", "emulator-5560 extra"):
            with self.subTest(serial=serial), self.assertRaises(ValueError):
                subject.adb_for_serial(serial)

    def test_api21_ps_requires_exact_selected_process(self):
        header = "USER     PID   PPID  VSIZE  RSS   WCHAN    PC         NAME\n"
        selected = f"u0_a51   2867  123   1000   100  0        0          {self.PACKAGE}\n"
        foreign = "u0_a52   3333  123   1000   100  0        0          other.app\n"
        self.assertEqual(subject.api21_pid_from_ps(header + selected + foreign), "2867")
        self.assertIsNone(subject.api21_pid_from_ps(header + foreign, required=False))
        for raw in (header + foreign, header + selected + selected):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                subject.api21_pid_from_ps(raw)

    def test_runtime_identity_accepts_selected_api21_x86_and_rejects_wrong_abi(self):
        properties = {
            "ro.build.version.sdk": "21",
            "ro.build.fingerprint": subject.API21_FINGERPRINTS["x86"],
            "ro.product.cpu.abi": "x86",
            "ro.product.cpu.abilist": "x86",
            "ro.product.model": "Android SDK built for x86",
            "sys.boot_completed": "1",
        }
        with tempfile.TemporaryDirectory() as temporary:
            def capture(arguments, destination, **_kwargs):
                Path(destination).write_text(properties[arguments[-1]] + "\n")

            with mock.patch.object(subject, "adb_capture", side_effect=capture):
                archive = Path(temporary)
                self.assertEqual(subject.runtime_identity(archive, 21, "x86"), properties)
                with self.assertRaisesRegex(ValueError, "installed ABI differs"):
                    subject.runtime_identity(archive, 21, "x86_64")
                with self.assertRaisesRegex(ValueError, "approved guest"):
                    subject.runtime_identity(archive, 37, "x86")


class VerifyArchivePathTests(unittest.TestCase):
    def verify_cli(self, archive):
        def scan_before_result(_checkout, supplied, *_expected):
            return {"archive_digest": subject.independent_gates.archive_digest(supplied)}

        arguments = ["verify", "--archive", str(archive),
                     "--expected-archive-digest", "a" * 64,
                     "--expected-core-aar-sha256", "b" * 64,
                     "--expected-facade-aar-sha256", "c" * 64,
                     "--expected-runtime-identity", "d" * 64]
        with mock.patch.object(subject, "verify_archive", side_effect=scan_before_result), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            subject.main(arguments)
        return json.loads(output.getvalue())

    def test_public_verify_rejects_symbolic_archive_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            regular = Path(temporary) / "regular"
            regular.mkdir()
            (regular / "receipt.json").write_text("{}\n")
            symbolic = Path(temporary) / "symbolic"
            symbolic.symlink_to(regular, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symbolic or reparse archive path"):
                self.verify_cli(symbolic)

    def test_public_verify_rejects_symbolic_archive_ancestor(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary) / "parent"
            regular = parent / "regular"
            regular.mkdir(parents=True)
            (regular / "receipt.json").write_text("{}\n")
            symbolic = Path(temporary) / "symbolic-parent"
            symbolic.symlink_to(parent, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symbolic or reparse archive path"):
                self.verify_cli(symbolic / "regular")

    def test_public_verify_accepts_regular_archive_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            regular = Path(temporary) / "regular"
            regular.mkdir()
            (regular / "receipt.json").write_text("{}\n")
            self.assertEqual(self.verify_cli(regular),
                             {"archive_digest": subject.independent_gates.archive_digest(regular)})


if __name__ == "__main__":
    unittest.main()
