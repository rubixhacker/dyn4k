import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from measure import sha256
from sustained_archive import signature


SCRIPT = Path(__file__).with_name("sustained_host.py")


class SignedV2ArchivePublicTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = os.environ.get("DYN4K_V2_ARCHIVE_BASE")
        key = os.environ.get("DYN4K_V2_ARCHIVE_KEY")
        if not base or not key:
            raise unittest.SkipTest("retained signed version 2 archives and external key unavailable")
        cls.archives = {mode: Path(base) / folder for mode, folder in
                        (("allocation", "v2-archive-owner-allocation-711"),
                         ("memory", "v2-archive-owner-memory-711-attempt4"),
                         ("plateau", "v2-archive-owner-plateau-4e"))}
        cls.old_plateau = Path(base) / "v2-archive-owner-plateau-711"
        cls.key = Path(key)
        if not cls.key.is_file() or not all((path / "archive.json").is_file()
                                            for path in (*cls.archives.values(), cls.old_plateau)):
            raise unittest.SkipTest("retained signed version 2 archive input unavailable")

    def verify(self, archive, key=None):
        index = json.loads((archive / "archive.json").read_text())
        result = subprocess.run([sys.executable, str(SCRIPT), "verify",
                                 "--archive", str(archive),
                                 "--trusted-key", str(key or self.key),
                                 "--expected-source-commit", index["source_commit"]],
                                capture_output=True, text=True, timeout=30,
                                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        return result.returncode, json.loads(result.stdout)

    def copy(self, mode, folder):
        archive = Path(folder) / "archive"
        shutil.copytree(self.archives[mode], archive)
        return archive, json.loads((archive / "archive.json").read_text())

    def reseal(self, archive, index, stem):
        record = index["captures"][0]
        record[stem + "_sha256"] = sha256(archive / record[stem + "_path"])
        index["signature"] = signature(index, self.key.read_bytes())
        (archive / "archive.json").write_text(json.dumps(index))

    def test_real_signed_streams_report_executed_but_unqualified(self):
        for mode, archive in self.archives.items():
            with self.subTest(mode=mode):
                original = sha256(archive / "archive.json")
                status, result = self.verify(archive)
                self.assertEqual(0, status, result)
                self.assertEqual("verified", result["raw_audit"])
                self.assertEqual("unpassed", result["qualification"])
                self.assertEqual({mode: {"status": "executed_unqualified", "routes": 3}},
                                 result["executed_modes"])
                self.assertEqual(original, sha256(archive / "archive.json"))

    def test_independent_key_and_missing_or_altered_sidecars_fail(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as folder:
            archive, index = self.copy("memory", folder)
            wrong = Path(folder) / "wrong.key"
            wrong.write_bytes(b"wrong-v2-operator-key-012345678901234567890")
            status, result = self.verify(archive, wrong)
            self.assertNotEqual(0, status)
            self.assertIn("signature", result["reason"])
            inside = archive / "key-link"
            inside.symlink_to(self.key)
            status, result = self.verify(archive, inside)
            self.assertNotEqual(0, status)
            self.assertIn("outside", result["reason"])
            inside.unlink()
            record = index["captures"][0]
            path = archive / record["memory_v2_path"]
            original = path.read_bytes()
            path.unlink()
            status, result = self.verify(archive)
            self.assertNotEqual(0, status)
            self.assertIn("missing", result["reason"])
            path.write_bytes(original + b"\n")
            status, result = self.verify(archive)
            self.assertNotEqual(0, status)
            self.assertIn("bytes differ", result["reason"])

    def test_resigned_wrong_binding_order_collection_and_attribution_fail(self):
        changes = (("memory", "memory_v2", "pid", "pid", 42),
                   ("memory", "memory_v2", "nonce", "nonce", "wrong-nonce"),
                   ("memory", "memory_v2", "source", "source_commit", "0" * 40),
                   ("memory", "memory_v2", "fixture", "fixture_sha256", "0" * 64),
                   ("memory", "memory_v2", "binding", "provider_sha256", "0" * 64),
                   ("memory", "memory_v2", "clock", "clock_ns", 10 ** 18),
                   ("memory", "memory_v2", "collection", "collection_count_delta", 0),
                   ("memory", "memory_v2", "attribution", "qualification", "passed"),
                   ("memory", "memory_v2", "provenance", "managed_provenance", "validated workload attribution"),
                   ("allocation", "allocation_v2", "order", None, None),
                   ("plateau", "plateau_v2", "cycle", None, None),
                   ("plateau", "plateau_v2", "buffer", "buffer_pool_used_bytes", -7))
        for mode, stem, label, field, value in changes:
            with self.subTest(mode=mode, label=label):
                with tempfile.TemporaryDirectory(dir=Path.home()) as folder:
                    archive, index = self.copy(mode, folder)
                    record = index["captures"][0]
                    path = archive / record[stem + "_path"]
                    rows = [json.loads(line) for line in path.read_text().splitlines()]
                    if label == "order":
                        rows[0], rows[1] = rows[1], rows[0]
                    elif label == "cycle":
                        rows[1]["collection_count"] = rows[0]["collection_count"]
                    elif label == "collection":
                        next(row for row in rows if row["phase"] == "retained")[field] = value
                    else:
                        rows[0][field] = value
                    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
                    self.reseal(archive, index, stem)
                    status, result = self.verify(archive)
                    self.assertNotEqual(0, status, result)
                    self.assertEqual("unpassed", result["qualification"])
                    self.assertIn("version 2", result["reason"])

    def test_resigned_duplicate_json_key_fails(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as folder:
            archive, index = self.copy("memory", folder)
            record = index["captures"][0]
            path = archive / record["allocation_v2_path"]
            rows = path.read_text().splitlines()
            rows[0] = rows[0][:-1] + ',"pid":' + str(record["pid"]) + "}"
            path.write_text("\n".join(rows) + "\n")
            self.reseal(archive, index, "allocation_v2")
            status, result = self.verify(archive)
            self.assertNotEqual(0, status)
            self.assertIn("duplicate", result["reason"])

    def test_resigned_warmup_memory_observation_after_next_step_begins_fails(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as folder:
            archive, index = self.copy("memory", folder)
            record = index["captures"][0]
            with (archive / record["warmup_clock_path"]).open() as stream:
                clocks = list(csv.DictReader(stream))
            path = archive / record["memory_v2_path"]
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            rows[2 + 3]["clock_ns"] = int(clocks[4]["begin_ns"])
            self.assertLess(rows[2 + 3]["clock_ns"], rows[2 + 4]["clock_ns"])
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
            self.reseal(archive, index, "memory_v2")
            status, result = self.verify(archive)
            self.assertNotEqual(0, status, result)
            self.assertIn("version 2 warm-up memory clock", result["reason"])

    def test_signed_4e_plateau_requires_each_collection_and_sample_stamp(self):
        changes = ("zero_delta", "early_disposal", "early_heap", "early_rss", "missing_before",
                   "wrong_pid", "wrong_provider", "wrong_probe")
        for label in changes:
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory(dir=Path.home()) as folder:
                    archive, index = self.copy("plateau", folder)
                    record = index["captures"][0]
                    path = archive / record["plateau_v2_path"]
                    rows = [json.loads(line) for line in path.read_text().splitlines()]
                    row = rows[37]
                    if label == "zero_delta":
                        row["collection_count_before"] = row["collection_count_after"]
                        row["collection_count_delta"] = 0
                        self.assertGreater(rows[38]["collection_count"], row["collection_count"])
                    elif label == "early_disposal":
                        row["cycle_disposed_ns"] = rows[36]["clock_ns"] - 1
                    elif label == "early_heap":
                        row["heap_sample_begin_ns"] = row["collection_after_sample_ns"] - 1
                    elif label == "early_rss":
                        row["rss_sample_begin_ns"] = row["heap_sample_end_ns"] - 1
                    elif label == "missing_before":
                        del row["collection_count_before"]
                    elif label == "wrong_pid":
                        row["pid"] = record["pid"] + 1
                    elif label == "wrong_provider":
                        row["provider_sha256"] = "0" * 64
                    else:
                        row["collection_probe"] = "unobserved"
                    path.write_text("\n".join(json.dumps(value) for value in rows) + "\n")
                    self.reseal(archive, index, "plateau_v2")
                    status, result = self.verify(archive)
                    self.assertNotEqual(0, status, result)
                    self.assertEqual("unpassed", result["qualification"])
                    self.assertIn("version 2", result["reason"])

    def test_signed_4e_plateau_rejects_legacy_csv_disagreement(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as folder:
            archive, index = self.copy("plateau", folder)
            record = index["captures"][0]
            path = archive / record["raw_path"]
            with path.open(newline="") as stream:
                reader = csv.DictReader(stream)
                fields = reader.fieldnames
                rows = list(reader)
            rows[37]["collection_count"] = str(int(rows[37]["collection_count"]) + 1)
            with path.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            record["raw_sha256"] = sha256(path)
            index["signature"] = signature(index, self.key.read_bytes())
            (archive / "archive.json").write_text(json.dumps(index))
            status, result = self.verify(archive)
            self.assertNotEqual(0, status, result)
            self.assertIn("version 2 plateau", result["reason"])

    def test_old_plateau_schema_is_historical_not_current_v2_proof(self):
        status, result = self.verify(self.old_plateau)
        self.assertNotEqual(0, status, result)
        self.assertEqual("unpassed", result["qualification"])
        self.assertIn("version 2", result["reason"])


if __name__ == "__main__":
    unittest.main()
