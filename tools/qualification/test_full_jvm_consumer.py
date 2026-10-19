import copy
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import full_jvm_consumer as route
import independent_gates


REPOSITORY = Path(__file__).resolve().parents[2]
ARCHIVE = os.environ.get("DYN4K_FULL_JVM_ARCHIVE")


class FullJvmConsumerTests(unittest.TestCase):
    def test_original_xml_maps_only_approved_identity(self):
        raw = (b'<testsuite tests="1" failures="0" errors="0" skipped="0" time="1">'
               b'<testcase classname="a.B" name="method" time="1"/></testsuite>')
        normalized = raw.replace(b'time="1"/>', b'time="1" id="core:a.B#method"/>')
        selected = {("a.B", "method"): "core:a.B#method"}
        self.assertEqual(route._same_report(raw, normalized, selected),
                         ["core:a.B#method"])
        with self.assertRaisesRegex(ValueError, "selected source identity"):
            route._same_report(raw, normalized.replace(b"core:a.B", b"core:x.B"), selected)
        with self.assertRaisesRegex(ValueError, "normalized XML changes"):
            route._same_report(raw, normalized.replace(b'time="1"', b'time="2"'), selected)

    def test_prepared_inventory_is_full_approved_contract(self):
        candidate = os.environ.get("DYN4K_FULL_JVM_CANDIDATE") or __import__(
            "subprocess").check_output(["git", "-C", str(REPOSITORY), "rev-parse", "HEAD"],
                                         text=True).strip()
        with tempfile.TemporaryDirectory() as directory:
            result = route.prepare(REPOSITORY, candidate, Path(directory) / "inputs")
            self.assertEqual(result["selected_cases"], 2526)
            self.assertEqual(result["source_count"], 175)
            inputs = Path(directory) / "inputs"
            self.assertEqual(len((inputs / "core-cases.tsv").read_text().splitlines()), 2465)
            self.assertEqual(len((inputs / "facade-cases.tsv").read_text().splitlines()), 61)

    @unittest.skipUnless(ARCHIVE, "requires retained real full JVM archive")
    def test_public_replay_and_resealed_adverse_archive(self):
        root = Path(ARCHIVE)
        receipt = json.loads((root / "receipt.json").read_bytes())
        candidate = receipt["candidate_sha"]
        hashes = receipt["artifact_hashes"]
        identity = receipt["runtime_identity"]
        digest = independent_gates.archive_digest(root)
        positive = route.verify(root, REPOSITORY, candidate, hashes, identity, digest)
        self.assertEqual(positive["status"], "PASSED")
        self.assertEqual(positive["selected_cases"], 2526)

        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "copy"
            shutil.copytree(root, copied, copy_function=shutil.copy2)
            altered = copy.deepcopy(receipt)
            altered["process"]["command"] = [
                f"-PqualificationArchiveRoot={copied}" if arg.startswith(
                    "-PqualificationArchiveRoot=") else arg
                for arg in altered["process"]["command"]]
            (copied / "receipt.json").write_bytes(route.encoded(altered) + b"\n")
            copied_digest = independent_gates.archive_digest(copied)
            self.assertEqual(route.verify(copied, REPOSITORY, candidate, hashes,
                                          identity, copied_digest)["status"], "PASSED")

            raw = copied / altered["raw_consumer_xml"][0]
            original = raw.read_bytes()
            raw.write_bytes(original.replace(b'tests="', b'tests="9', 1))
            os.utime(raw, ns=(raw.stat().st_atime_ns,
                              next(item["mtime_ns"] for item in altered["files"]
                                   if item["path"] == altered["raw_consumer_xml"][0])))
            for item in altered["files"]:
                if item["path"] == altered["raw_consumer_xml"][0]:
                    item["sha256"] = route.sha(raw.read_bytes())
            (copied / "receipt.json").write_bytes(route.encoded(altered) + b"\n")
            with self.assertRaisesRegex(ValueError, "normalized XML"):
                route.verify(copied, REPOSITORY, candidate, hashes, identity,
                             independent_gates.archive_digest(copied))


if __name__ == "__main__":
    unittest.main()
