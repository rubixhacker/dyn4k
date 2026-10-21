import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SOURCE = Path(__file__).with_name("reference_study_producer.py")
JDK = Path("/tmp/dyn4k-tools/jdk21")
GRADLE = Path("/tmp/dyn4k-tools/gradle-9.5.0/bin/gradle")
BASELINE = Path("/tmp/dyn4k-performance-dyn4j-6.0.0.jar")


class ReferenceStudyProducerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(dir=Path.home())
        cls.root = Path(cls.temporary.name)
        cls.output = cls.root / "production"
        cls.key = cls.root / "operator.key"
        cls.key.write_bytes(b"independent-reference-study-test-key-" * 2)
        cls.env = os.environ.copy()
        cls.env.update(JAVA_HOME=str(JDK), TMPDIR=str(cls.root),
                       JAVA_TOOL_OPTIONS=f"-Djava.io.tmpdir={cls.root}",
                       PYTHONDONTWRITEBYTECODE="1")
        cls.result = subprocess.run(
            [sys.executable, str(SOURCE), "capture", "--output-root", str(cls.output),
             "--trusted-key", str(cls.key), "--java", str(JDK / "bin/java"),
             "--javac", str(JDK / "bin/javac"), "--gradle", str(GRADLE),
             "--baseline", str(BASELINE), "--seconds", "1", "--warmup-seconds", "1"],
            env=cls.env, capture_output=True, text=True, timeout=240)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_real_frozen_pair_set_keeps_unpassed(self):
        self.assertEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)
        result = json.loads(self.result.stdout)
        self.assertEqual(result["study"], "structurally_verified")
        self.assertEqual(result["qualification"], "unpassed")
        self.assertEqual(result["validated_reference_rows"], 0)
        captures = json.loads((self.output / "captures.json").read_text())
        self.assertEqual([(row["pair"], row["side"], row["order"]) for row in captures],
                         [(1, "a", 1), (1, "b", 2), (2, "b", 1),
                          (2, "a", 2), (3, "a", 1), (3, "b", 2)])
        self.assertEqual(len({(row["boot_id"], row["os_pid"], row["process_start_id"])
                              for row in captures}), 6)
        self.assertEqual(len({row["run_id"] for row in captures}), 6)
        for ordinal, row in enumerate(captures):
            series = (self.output / row["series_path"]).read_text()
            self.assertEqual(len(series.splitlines()), 31)
            self.assertTrue(series.startswith("step,elapsed_ns,"))
            monitor = json.loads((self.output / row["monitor_path"]).read_text())
            self.assertEqual(monitor["os_pid"], row["os_pid"])
            self.assertEqual(monitor["process_start_id"], row["process_start_id"])
            self.assertTrue(monitor["samples"])
            self.assertEqual(monitor["launch_nonce"], row["run_id"])
        audit = subprocess.run([sys.executable, str(SOURCE), "audit", "--output-root",
                                str(self.output), "--trusted-key", str(self.key)],
                               env=self.env, capture_output=True, text=True)
        self.assertEqual(audit.returncode, 0, audit.stdout + audit.stderr)

    def test_distinct_real_java_processes_can_emit_identical_zero_series(self):
        from reference_study_producer import observe_process

        source = self.root / "ZeroSeries.java"
        source.write_text("public class ZeroSeries { public static void main(String[] a) "
                          "throws Exception { System.out.println(0); Thread.sleep(200); } }")
        subprocess.run([str(JDK / "bin/javac"), str(source)], check=True, env=self.env)
        command = [str(JDK / "bin/java"), "-cp", str(self.root), "ZeroSeries"]
        digest = hashlib.sha256((JDK / "bin/java").read_bytes()).hexdigest()
        observed = [observe_process(command, self.env, self.root / f"zero-{index}",
                                    f"zero-{index}", digest, timeout=5)
                    for index in (1, 2)]
        self.assertEqual([(self.root / f"zero-{index}" / "series.csv").read_bytes()
                          for index in (1, 2)], [b"0\n", b"0\n"])
        self.assertNotEqual(observed[0]["process_id"], observed[1]["process_id"])
        self.assertNotEqual(observed[0]["os_pid"], observed[1]["os_pid"])

    def test_audit_rejects_mismatched_external_provenance(self):
        self.assertEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)
        from reference_study_producer import audit_output

        cases = (
            ("monitor_pid", "monitor", "os_pid", 999999),
            ("monitor_start", "monitor", "process_start_id", "wrong-start"),
            ("monitor_nonce", "monitor", "launch_nonce", "wrong-run"),
            ("monitor_clock", "monitor", "ended_ns", 1),
            ("environment_artifact", "environment", "artifact_sha256", "0" * 64),
            ("environment_image", "environment", "image_sha256", "0" * 64),
            ("capture_pid", "capture", "os_pid", 999999),
            ("capture_process", "capture", "process_id", "REUSE_FIRST"),
        )
        for name, target, field, value in cases:
            with self.subTest(name=name):
                copy = self.root / name
                shutil.copytree(self.output, copy)
                captures = json.loads((copy / "captures.json").read_text())
                if target == "capture":
                    if value == "REUSE_FIRST":
                        captures[1][field] = captures[0][field]
                    else:
                        captures[0][field] = value
                    (copy / "captures.json").write_text(json.dumps(captures))
                else:
                    path = copy / captures[0][target + "_path"]
                    data = json.loads(path.read_text())
                    data[field] = value
                    path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    audit_output(copy, self.key)


if __name__ == "__main__":
    unittest.main()
