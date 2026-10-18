import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from candidate_runner import IDENTITY, ROOT
from measure import sha256
from sustained_archive import signature


SCRIPT = ROOT / "tools/performance/bounded_adapter.py"
BASELINE = Path("/tmp/dyn4k-performance-dyn4j-6.0.0.jar")
JDK = Path("/tmp/dyn4k-tools/jdk21")


class BoundedAdapterPublicTest(unittest.TestCase):
    def test_real_three_route_capture_audit_and_signed_raw_rejection(self):
        if not IDENTITY.is_file() or not BASELINE.is_file() or not JDK.is_dir():
            self.skipTest("staged exact-source JVM inputs unavailable")
        identity = json.loads(IDENTITY.read_text())
        with tempfile.TemporaryDirectory(dir=Path.home()) as folder:
            archive = Path(folder) / "archive"
            key = Path(folder) / "operator.key"
            key.write_bytes(b"bounded-integration-test-operator-key-123456")
            common = ["--archive", str(archive), "--trusted-key", str(key),
                      "--expected-source-commit", identity["source_commit"]]
            capture = subprocess.run([sys.executable, str(SCRIPT), "capture", *common,
                                      "--java", str(JDK / "bin/java"),
                                      "--javac", str(JDK / "bin/javac"),
                                      "--baseline", str(BASELINE),
                                      "--seconds", "1", "--warmup-seconds", "1"],
                                     cwd=ROOT, text=True, capture_output=True, timeout=90)
            self.assertEqual(0, capture.returncode, capture.stderr or capture.stdout)
            verify = subprocess.run([sys.executable, str(SCRIPT), "verify", *common],
                                    cwd=ROOT, text=True, capture_output=True, timeout=30)
            self.assertEqual(0, verify.returncode, verify.stderr or verify.stdout)
            verdict = json.loads(verify.stdout)
            self.assertEqual("verified", verdict["raw_audit"])
            self.assertEqual("unpassed", verdict["qualification"])
            self.assertEqual(3, verdict["executed_routes"])
            self.assertEqual(3, len(verdict["missing_sustained_sidecars"]))
            index_path = archive / "archive.json"
            index = json.loads(index_path.read_text())
            raw = archive / index["captures"][0]["raw_path"]
            original_raw = raw.read_bytes()
            raw.write_text("\n".join(raw.read_text().splitlines()[:-1]) + "\n")
            index["captures"][0]["raw_sha256"] = sha256(raw)
            index["signature"] = signature(index, key.read_bytes())
            index_path.write_text(json.dumps(index))
            rejected = subprocess.run([sys.executable, str(SCRIPT), "verify", *common],
                                      cwd=ROOT, text=True, capture_output=True, timeout=30)
            self.assertNotEqual(0, rejected.returncode)
            self.assertIn("unpassed", rejected.stdout)
            raw.write_bytes(original_raw)
            index["captures"][0]["raw_sha256"] = sha256(raw)
            index["captures"][0]["command"].insert(1, "-Dunbound=true")
            index["signature"] = signature(index, key.read_bytes())
            index_path.write_text(json.dumps(index))
            rejected = subprocess.run([sys.executable, str(SCRIPT), "verify", *common],
                                      cwd=ROOT, text=True, capture_output=True, timeout=30)
            self.assertNotEqual(0, rejected.returncode)
            self.assertIn("command", rejected.stdout)
            index["captures"][0]["command"].remove("-Dunbound=true")
            harness_source = str(ROOT / "tools/performance/BaselinePilot.java")
            index["candidate_identity"]["sha256"][harness_source] = "0" * 64
            identity_input = next(item for item in index["inputs"]
                                  if item["source_path"] == str(IDENTITY))
            identity_copy = archive / identity_input["archive_path"]
            identity_copy.write_text(json.dumps(index["candidate_identity"]))
            identity_input["sha256"] = sha256(identity_copy)
            index["signature"] = signature(index, key.read_bytes())
            index_path.write_text(json.dumps(index))
            rejected = subprocess.run([sys.executable, str(SCRIPT), "verify", *common],
                                      cwd=ROOT, text=True, capture_output=True, timeout=30)
            self.assertNotEqual(0, rejected.returncode)
            self.assertIn("source revision", rejected.stdout)
            index["candidate_identity"]["sha256"][harness_source] = sha256(Path(harness_source))
            identity_copy.write_text(json.dumps(index["candidate_identity"]))
            identity_input["sha256"] = sha256(identity_copy)
            index["scenario_id"] = "pile.default.small.30hz.baseline"
            index["signature"] = signature(index, key.read_bytes())
            index_path.write_text(json.dumps(index))
            rejected = subprocess.run([sys.executable, str(SCRIPT), "verify", *common],
                                      cwd=ROOT, text=True, capture_output=True, timeout=30)
            self.assertNotEqual(0, rejected.returncode)
            self.assertIn("scenario", rejected.stdout)
            index["scenario_id"] = "separated.default.small.30hz.baseline"
            source_input = next(item for item in index["inputs"]
                                if item["source_path"] == harness_source)
            source_copy = archive / source_input["archive_path"]
            source_copy.write_bytes(source_copy.read_bytes() + b"\n")
            source_input["sha256"] = sha256(source_copy)
            index["candidate_identity"]["sha256"][harness_source] = sha256(source_copy)
            identity_copy.write_text(json.dumps(index["candidate_identity"]))
            identity_input["sha256"] = sha256(identity_copy)
            index["signature"] = signature(index, key.read_bytes())
            index_path.write_text(json.dumps(index))
            rejected = subprocess.run([sys.executable, str(SCRIPT), "verify", *common],
                                      cwd=ROOT, text=True, capture_output=True, timeout=30)
            self.assertNotEqual(0, rejected.returncode)
            self.assertIn("source revision", rejected.stdout)


if __name__ == "__main__":
    unittest.main()
