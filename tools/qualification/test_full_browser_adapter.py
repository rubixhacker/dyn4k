import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import full_browser_adapter as adapter


LANE = "js:Chromium:current:development"
CANDIDATE = "a" * 40
ARCHIVE_DIGEST = "b" * 64
CORE_HASH = "c" * 64
FACADE_HASH = "d" * 64


class BrowserAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.archive = Path(self.temporary.name)
        self.bundle_bytes = {"core": b"independent core", "facade": b"independent facade"}
        self.bundles = {short: hashlib.sha256(raw).hexdigest()
                        for short, raw in self.bundle_bytes.items()}
        for short, raw in self.bundle_bytes.items():
            folder = self.archive / short
            folder.mkdir()
            for name in ("karma-selected.js", "linked-executable.js"):
                (folder / name).write_bytes(raw)
        self.hashes = {"dyn4k-core": CORE_HASH, "dyn4k": FACADE_HASH}
        self.toolchain = {
            "java_home": str(self.archive / "jdk21"), "java_version": 'openjdk version "21.0.12"',
            "java_sha256": adapter.full_browser_consumer.JAVA_SHA256,
            "gradle": str(self.archive / "gradle"), "gradle_sha256": adapter.full_browser_consumer.GRADLE_SHA256,
            "gradle_version": "9.5.0", "kgp_version": "2.4.20",
            "browser": str(self.archive / "chrome"), "browser_sha256": adapter.full_browser_consumer.CHROMIUM["current"][1],
            "browser_version": "Google Chrome for Testing 155.0.1.0",
            "gradle_user_home": str(self.archive / "gradle-home"),
        }
        self.expected = {
            "expected_artifact_hashes": self.hashes,
            "expected_archive_digests": {"staged-consumer": ARCHIVE_DIGEST},
            "expected_runtime_identity": "Linux trusted x86_64",
            "expected_browser_toolchain": self.toolchain,
            "expected_browser_bundles": self.bundles,
        }
        self.gate = {"gate": "staged-consumer", "status": "PASSED",
                     "complete_selected_suite": True, "selected_cases": 2,
                     "archive_sha256": ARCHIVE_DIGEST}
        self.public = {"status": "PASSED", "lane": LANE, "selected_cases": 2,
                       "archive_sha256": ARCHIVE_DIGEST, "candidate_sha": CANDIDATE}

    def call(self, **changes):
        observed_digest = changes.pop("observed_digest", ARCHIVE_DIGEST)
        receipt = changes.pop("receipt", {"runtime_identity": "Linux trusted x86_64",
                                         "toolchain": self.toolchain})
        values = {"repository": self.archive, "candidate_sha": CANDIDATE,
                  "lane_id": LANE, "selected": {"case_ids": ["one", "two"]},
                  "archive": self.archive, "expected": self.expected,
                  "gate_result": self.gate, "audited_target_hashes": self.hashes}
        values.update(changes)
        with (mock.patch.object(adapter, "_executable"),
              mock.patch.object(adapter.full_browser_consumer, "contract",
                                return_value={"cases": [{"id": "one"}, {"id": "two"}]}),
              mock.patch.object(adapter.independent_gates, "archive_digest",
                                return_value=observed_digest),
              mock.patch.object(adapter.independent_gates, "_json",
                                return_value=receipt),
              mock.patch.object(adapter.full_browser_consumer, "verify",
                                return_value=self.public) as public):
            result = adapter.verify_full_browser_staged_consumer(**values)
        return result, public.call_count

    def test_positive_signed_binding_calls_public_replay(self):
        result, count = self.call()
        self.assertEqual(self.public, result)
        self.assertEqual(1, count)

    def test_wrong_lane_candidate_or_case_set_rejected(self):
        for change in ({"lane_id": "js:Chromium:foreign:development"},
                       {"candidate_sha": "short"},
                       {"selected": {"case_ids": ["two", "one"]}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.call(**change)

    def test_signed_artifact_runtime_archive_and_gate_mismatch_rejected(self):
        changes = []
        for field, value in (("expected_artifact_hashes", {"dyn4k-core": CORE_HASH}),
                             ("expected_runtime_identity", ""),
                             ("expected_archive_digests", {"staged-consumer": "e" * 64}),
                             ("expected_browser_bundles", {"core": "f" * 64, "facade": self.bundles["facade"]})):
            expected = copy.deepcopy(self.expected)
            expected[field] = value
            changes.append({"expected": expected})
        for field, value in (("status", "NOT_RUN"), ("gate", "other"),
                             ("complete_selected_suite", False), ("selected_cases", 1),
                             ("archive_sha256", "e" * 64)):
            gate = dict(self.gate)
            gate[field] = value
            changes.append({"gate_result": gate})
        changes.append({"audited_target_hashes": {"dyn4k-core": "e" * 64,
                                                     "dyn4k": FACADE_HASH}})
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.call(**change)

    def test_resealed_selected_and_linked_copies_rejected(self):
        for name in ("karma-selected.js", "linked-executable.js"):
            (self.archive / "core" / name).write_bytes(b"producer resealed copy")
        with self.assertRaisesRegex(ValueError, "independent signed hash"):
            self.call()

    def test_wrong_signed_toolchain_or_browser_role_rejected(self):
        for key, value in (("browser_sha256", "e" * 64),
                           ("gradle_sha256", "e" * 64),
                           ("browser", "relative/chrome"),
                           ("browser_version", "Google Chrome 119.0.1")):
            expected = copy.deepcopy(self.expected)
            expected["expected_browser_toolchain"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.call(expected=expected)

    def test_executable_bytes_must_match_signed_hash(self):
        executable = self.archive / "browser"
        executable.write_bytes(b"selected Chromium executable")
        digest = hashlib.sha256(executable.read_bytes()).hexdigest()
        adapter._executable(executable, digest, "Chromium")
        executable.write_bytes(b"different Chromium executable")
        with self.assertRaisesRegex(ValueError, "executable bytes differ"):
            adapter._executable(executable, digest, "Chromium")

    def test_archive_digest_and_runtime_receipt_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "archive digest differs"):
            self.call(observed_digest="e" * 64)
        with self.assertRaisesRegex(ValueError, "runtime or toolchain differs"):
            self.call(receipt={"runtime_identity": "other", "toolchain": self.toolchain})

    def test_public_result_mismatch_rejected(self):
        self.public = {**self.public, "selected_cases": 1}
        with self.assertRaisesRegex(ValueError, "public browser verifier differs"):
            self.call()


if __name__ == "__main__":
    unittest.main()
