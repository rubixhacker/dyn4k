import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from candidate_runner import IDENTITY, ROOT
from measure import sha256
from sustained_archive import signature


SCRIPT = ROOT / "tools/performance/sustained_host.py"
JDK = Path("/tmp/dyn4k-tools/jdk21")
BASELINE = Path("/tmp/dyn4k-performance-dyn4j-6.0.0.jar")


class SustainedHostPublicTest(unittest.TestCase):
    def test_real_versioned_host_capture_replay_and_adverse_signed_sidecars(self):
        if not JDK.is_dir() or not BASELINE.is_file():
            self.skipTest("pinned JVM inputs unavailable")
        with tempfile.TemporaryDirectory(dir=Path.home()) as folder:
            home = Path(folder)
            archive = home / "archive"
            key = home / "operator.key"
            key.write_bytes(b"sustained-host-test-operator-key-1234567")
            common = ["--archive", str(archive), "--trusted-key", str(key),
                      "--expected-source-commit", subprocess.check_output(
                          ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()]
            env = {**os.environ, "TMPDIR": str(home)}
            capture = subprocess.run([sys.executable, str(SCRIPT), "capture", *common,
                                      "--java", str(JDK / "bin/java"),
                                      "--javac", str(JDK / "bin/javac"),
                                      "--baseline", str(BASELINE),
                                      "--seconds", "1", "--warmup-seconds", "1"],
                                     cwd=ROOT, env=env, capture_output=True, text=True,
                                     timeout=180)
            self.assertEqual(0, capture.returncode, capture.stderr or capture.stdout)
            verification = subprocess.run([sys.executable, str(SCRIPT), "verify", *common],
                                          cwd=ROOT, env=env, capture_output=True, text=True,
                                          timeout=30)
            self.assertEqual(0, verification.returncode, verification.stderr or verification.stdout)
            verdict = json.loads(verification.stdout)
            self.assertEqual("verified", verdict["raw_audit"])
            self.assertEqual("unpassed", verdict["qualification"])
            self.assertEqual(3, verdict["executed_routes"])
            self.assertIn("600-second duration", verdict["missing_qualification"])
            index_file = archive / "archive.json"
            index = json.loads(index_file.read_text())
            self.assertEqual("sustained-jvm-host-v1", index["route"])
            self.assertEqual(3, len(index["captures"]))
            for run in index["captures"]:
                self.assertEqual(0, run["exit_code"])
                for stem in ("raw", "stderr", "clock", "warmup_clock", "resource",
                             "provider", "run", "process_image_receipt", "clock_origin",
                             "clock_origin_receipt"):
                    self.assertTrue((archive / run[stem + "_path"]).is_file())

            def reject(mutator, expected):
                original = json.loads(index_file.read_text())
                changed = json.loads(json.dumps(original))
                mutator(changed)
                changed["signature"] = signature(changed, key.read_bytes())
                index_file.write_text(json.dumps(changed))
                attempt = subprocess.run([sys.executable, str(SCRIPT), "verify", *common],
                                         cwd=ROOT, env=env, capture_output=True, text=True,
                                         timeout=30)
                self.assertNotEqual(0, attempt.returncode, attempt.stdout)
                self.assertIn(expected, attempt.stdout)
                index_file.write_text(json.dumps(original))

            reject(lambda item: item["captures"][0]["command"].insert(1, "-Dunbound=1"),
                   "command")
            reject(lambda item: item["captures"][0].update(exit_code=7), "exit")
            reject(lambda item: item["captures"][0].update(pid=42), "process image")
            reject(lambda item: item["captures"][0].update(seconds=600), "duration")
            reject(lambda item: item["build_receipt"]["consumer_command"].append("-Dunbound=1"),
                   "build command")

            changed = json.loads(index_file.read_text())
            record = changed["captures"][0]
            clock_path = archive / record["warmup_clock_path"]
            original_clock = clock_path.read_bytes()
            rows = clock_path.read_text().splitlines()
            for position in range(1, len(rows)):
                values = rows[position].split(",")
                values[1:] = [str(int(value) + 1_000_000_000_000) for value in values[1:]]
                rows[position] = ",".join(values)
            clock_path.write_text("\n".join(rows) + "\n")
            record["warmup_clock_sha256"] = sha256(clock_path)
            changed["signature"] = signature(changed, key.read_bytes())
            index_file.write_text(json.dumps(changed))
            attempt = subprocess.run([sys.executable, str(SCRIPT), "verify", *common],
                                     cwd=ROOT, env=env, capture_output=True, text=True,
                                     timeout=30)
            self.assertNotEqual(0, attempt.returncode, attempt.stdout)
            self.assertIn("process-bound clock", attempt.stdout)
            clock_path.write_bytes(original_clock)
            index_file.write_text(json.dumps(index))

            changed = json.loads(index_file.read_text())
            record = changed["captures"][0]
            clock_path = archive / record["clock_path"]
            original_clock = clock_path.read_bytes()
            rows = clock_path.read_text().splitlines()
            values = rows[16].split(",")
            values[1:] = [str(int(value) + 1_000_000_000_000) for value in values[1:]]
            rows[16] = ",".join(values)
            clock_path.write_text("\n".join(rows) + "\n")
            record["clock_sha256"] = sha256(clock_path)
            changed["signature"] = signature(changed, key.read_bytes())
            index_file.write_text(json.dumps(changed))
            attempt = subprocess.run([sys.executable, str(SCRIPT), "verify", *common],
                                     cwd=ROOT, env=env, capture_output=True, text=True,
                                     timeout=30)
            self.assertNotEqual(0, attempt.returncode, attempt.stdout)
            self.assertIn("process-bound clock", attempt.stdout)
            clock_path.write_bytes(original_clock)
            index_file.write_text(json.dumps(index))

            index = json.loads(index_file.read_text())
            receipt_input = next(item for item in index["inputs"]
                                 if item["source_path"].endswith("/build/receipt.json"))
            receipt_path = archive / receipt_input["archive_path"]
            original_receipt = receipt_path.read_bytes()
            index["build_receipt"]["consumer_command"].append("-Dunbound=1")
            receipt_path.write_text(json.dumps(index["build_receipt"]))
            receipt_input["sha256"] = sha256(receipt_path)
            index["signature"] = signature(index, key.read_bytes())
            index_file.write_text(json.dumps(index))
            attempt = subprocess.run([sys.executable, str(SCRIPT), "verify", *common],
                                     cwd=ROOT, env=env, capture_output=True, text=True,
                                     timeout=30)
            self.assertNotEqual(0, attempt.returncode, attempt.stdout)
            self.assertIn("build command", attempt.stdout)
            receipt_path.write_bytes(original_receipt)
            receipt_input["sha256"] = sha256(receipt_path)
            index["build_receipt"]["consumer_command"].remove("-Dunbound=1")
            index["signature"] = signature(index, key.read_bytes())
            index_file.write_text(json.dumps(index))

            for stem, field, value, expected in (
                ("provider", "loaded_core_sha256", "0" * 64, "provider"),
                ("provider", "loaded_adapter_sha256", "0" * 64, "provider"),
                ("run", "sample_count", 29, "sample"),
                ("run", "active_steps", 0, "activity"),
            ):
                index = json.loads(index_file.read_text())
                record = index["captures"][0]
                path = archive / record[stem + "_path"]
                original = path.read_bytes()
                payload = json.loads(original)
                payload[field] = value
                path.write_text(json.dumps(payload))
                record[stem + "_sha256"] = sha256(path)
                index["signature"] = signature(index, key.read_bytes())
                index_file.write_text(json.dumps(index))
                attempt = subprocess.run([sys.executable, str(SCRIPT), "verify", *common],
                                         cwd=ROOT, env=env, capture_output=True, text=True,
                                         timeout=30)
                self.assertNotEqual(0, attempt.returncode, attempt.stdout)
                self.assertIn(expected, attempt.stdout)
                path.write_bytes(original)
                index["captures"][0][stem + "_sha256"] = sha256(path)
                index["signature"] = signature(index, key.read_bytes())
                index_file.write_text(json.dumps(index))

            for stem, field, expected in (("clock", "end_ns", "clock"),
                                          ("resource", "heap_used_bytes", "resource")):
                index = json.loads(index_file.read_text())
                record = index["captures"][0]
                path = archive / record[stem + "_path"]
                original = path.read_bytes()
                lines = path.read_text().splitlines()
                header = lines[0].split(",")
                position = header.index(field)
                row = lines[-1].split(",")
                row[position] = str(int(row[position]) + 1)
                lines[-1] = ",".join(row)
                path.write_text("\n".join(lines) + "\n")
                record[stem + "_sha256"] = sha256(path)
                index["signature"] = signature(index, key.read_bytes())
                index_file.write_text(json.dumps(index))
                attempt = subprocess.run([sys.executable, str(SCRIPT), "verify", *common],
                                         cwd=ROOT, env=env, capture_output=True, text=True,
                                         timeout=30)
                self.assertNotEqual(0, attempt.returncode, attempt.stdout)
                self.assertIn(expected, attempt.stdout)
                path.write_bytes(original)
                index["captures"][0][stem + "_sha256"] = sha256(path)
                index["signature"] = signature(index, key.read_bytes())
                index_file.write_text(json.dumps(index))

            relocated = home / "relocated"
            archive.rename(relocated)
            replay = subprocess.run([sys.executable, str(SCRIPT), "verify", "--archive",
                                     str(relocated), "--trusted-key", str(key),
                                     "--expected-source-commit", common[-1]],
                                    cwd=ROOT, env=env, capture_output=True, text=True,
                                    timeout=30)
            self.assertEqual(0, replay.returncode, replay.stdout)
            internal = relocated / "copied-operator.key"
            internal.write_bytes(key.read_bytes())
            alias = home / "archive-key-alias"
            alias.symlink_to(internal)
            key_probe = subprocess.run([sys.executable, str(SCRIPT), "verify", "--archive",
                                        str(relocated), "--trusted-key", str(alias),
                                        "--expected-source-commit", common[-1]],
                                       cwd=ROOT, env=env, capture_output=True, text=True,
                                       timeout=30)
            self.assertNotEqual(0, key_probe.returncode)
            self.assertIn("trusted key", key_probe.stdout)


if __name__ == "__main__":
    unittest.main()
