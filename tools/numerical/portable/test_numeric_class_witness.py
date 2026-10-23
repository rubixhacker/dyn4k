import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from receipt import Rejected
from numeric_class_witness import build_agent, read_witness
from numeric_producer_trace import verify_stable_input


SOURCE = Path(__file__).with_name("class_witness") / "NumericClassWitness.java"
JDK_HOME_ENV = "DYN4K_CLASS_WITNESS_JDK_HOME"


def configured_jdk_home():
    if JDK_HOME_ENV in os.environ:
        supplied = os.environ[JDK_HOME_ENV]
        if not supplied.strip():
            raise RuntimeError(f"{JDK_HOME_ENV} must name a JDK directory")
        jdk_home = Path(supplied)
    else:
        jdk_home = Path("/tmp/dyn4k-tools/jdk21")

    if not jdk_home.is_dir():
        raise RuntimeError(f"{JDK_HOME_ENV} is not a JDK directory: {jdk_home}")
    for tool in ("java", "javac"):
        executable = jdk_home / "bin" / tool
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise RuntimeError(f"{JDK_HOME_ENV} lacks executable bin/{tool}: {jdk_home}")
    return jdk_home


JDK = configured_jdk_home()


def record(name="portable/PortableMatrixTest", value=b"class", origin="file:/fixture/"):
    return ("CLASS\t1\t" + name + "\t" + hashlib.sha256(value).hexdigest()
            + "\tL1\t" + origin + "\tjava:1\n").encode()


def witness(rows=None, status="OK"):
    body = b"BEGIN\tclass-witness/1\n" + (record() if rows is None else rows)
    end = f"END\t{status}\t1\t"
    return body + (end + f"{len(body) + len(end) + 21:020d}\n").encode()


class ClassWitnessTest(unittest.TestCase):
    def test_rebuild_is_deterministic_and_capabilities_are_absent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            one = build_agent(SOURCE.read_bytes(), JDK, root / "one.jar", root / "one")
            two = build_agent(SOURCE.read_bytes(), JDK, root / "two.jar", root / "two")
            self.assertEqual(one, two)
            self.assertEqual((root / "one.jar").read_bytes(), one)
            self.assertNotIn(b"Can-Redefine-Classes", one)
            self.assertNotIn(b"Can-Retransform-Classes", one)

    def test_records_are_strict_and_complete(self):
        expected = {"portable/PortableMatrixTest": b"class"}
        good = witness()
        self.assertEqual(read_witness(good, expected)["definitions"][0]["thread"], "java:1")
        failures = (good.replace(b"END\tOK", b"END\tFAIL"), good[:-31],
                    good.replace(hashlib.sha256(b"class").hexdigest().encode(), b"0" * 64),
                    good.replace(b"file:/fixture/", b"file:/shadow/"),
                    good.replace(b"java:1", b"os:1"),
                    witness(record() + record().replace(b"CLASS\t1", b"CLASS\t2")))
        for invalid in failures:
            with self.subTest(invalid=invalid[:40]), self.assertRaises(Rejected):
                read_witness(invalid, expected, {"portable/PortableMatrixTest": "file:/fixture/"})

    def test_real_jvm_callback_precedes_successful_load(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agent = root / "agent.jar"
            build_agent(SOURCE.read_bytes(), JDK, agent, root / "build-agent")
            classes = root / "classes"
            package = root / "source" / "portable"
            classes.mkdir()
            package.mkdir(parents=True)
            sources = {
                "NumericProbeMatrixTest": "public class NumericProbeMatrixTest {}",
                "PortableMatrixTest": "public class PortableMatrixTest { public static int answer() { return 75; } }",
                "NumericalRecorder": "public class NumericalRecorder {}",
            }
            for name, body in sources.items():
                (package / (name + ".java")).write_text("package portable; " + body)
            main = root / "source" / "Main.java"
            main.write_text("public class Main { public static void main(String[] a) throws Exception { "
                            "Class.forName(\"portable.NumericProbeMatrixTest\"); "
                            "Class.forName(\"portable.NumericalRecorder\"); "
                            "System.out.println(portable.PortableMatrixTest.answer()); } }")
            javac = subprocess.run([str(JDK / "bin/javac"), "--release", "8", "-d", str(classes),
                                    str(main), *map(str, sorted(package.glob("*.java")))],
                                   capture_output=True, check=False)
            self.assertEqual(javac.returncode, 0, javac.stderr.decode())
            expected = {"portable/" + path.stem: path.read_bytes()
                        for path in package.glob("*.java")
                        for path in [classes / "portable" / (path.stem + ".class")]}
            witness_path = root / "witness.log"
            command = [str(JDK / "bin/java"), "-XX:+DisableAttachMechanism", "-Xshare:off",
                       "-javaagent:" + str(agent) + "=" + str(witness_path),
                       "-Xlog:class+load=info:file=" + str(root / "loads.log"),
                       "-cp", str(classes), "Main"]
            successful = subprocess.run(command, capture_output=True, check=False, timeout=30)
            self.assertEqual(successful.returncode, 0, successful.stderr.decode())
            self.assertEqual(successful.stdout, b"75\n")
            records = read_witness(witness_path.read_bytes(), expected)
            self.assertEqual(len(records["definitions"]), 3)
            self.assertIn("portable.PortableMatrixTest source:",
                          (root / "loads.log").read_text())
            tracer = shutil.which("strace")
            self.assertIsNotNone(tracer)
            witness_path.unlink()
            traced = subprocess.run([tracer, "-ff", "-ttt", "-yy", "-e",
                                     "abbrev=!fstat,newfstatat,statx", "-s", "131072",
                                     "-e", "trace=process,open,openat,openat2,close,read,pread64,lseek,"
                                     "fstat,newfstatat,statx,write,mmap,rename,unlink,truncate",
                                     "-o", str(root / "trace"), *command],
                                    capture_output=True, check=False, timeout=30)
            self.assertEqual(traced.returncode, 0, traced.stderr.decode())
            traces = {path.name.split(".")[-1]: path.read_bytes()
                      for path in root.glob("trace.*")}
            worker = next(tid for tid, data in traces.items()
                          if b"execve(" in data and b'"Main"' in data)
            status = agent.stat()
            identity = {"device_major": os.major(status.st_dev),
                        "device_minor": os.minor(status.st_dev),
                        "inode": status.st_ino, "size": status.st_size}
            try:
                input_proof = verify_stable_input(traces, str(agent), identity, worker,
                                                  agent.read_bytes())
            except Exception as error:
                count = sum(str(agent) in line for data in traces.values()
                            for line in data.decode().splitlines())
                kinds = [(line.split(" ", 1)[-1].split("(", 1)[0],
                          "PROT_WRITE" in line, "MAP_PRIVATE" in line)
                         for data in traces.values() for line in data.decode().splitlines()
                         if str(agent) in line and line.split(" ", 1)[-1].startswith(
                             ("write", "mmap", "rename", "unlink", "truncate"))]
                self.fail(str(error) + f"; relevant trace records: {count}; operations: {kinds[:10]}")
            self.assertGreater(input_proof["reads"], 0)
            broken = classes / "portable" / "PortableMatrixTest.class"
            bad = broken.read_bytes()
            broken.write_bytes(b"XXXX" + bad[4:])
            witness_path.unlink()
            failed = subprocess.run(command, capture_output=True, check=False, timeout=30)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn(b"CLASS\t", witness_path.read_bytes())
            with self.assertRaises(Rejected):
                read_witness(witness_path.read_bytes(), expected)
            broken.write_bytes(bad)
            shadow = root / "source" / "dyn4k" / "witness" / "NumericClassWitness.java"
            shadow.parent.mkdir(parents=True)
            shadow.write_text("package dyn4k.witness; public final class NumericClassWitness { "
                              "public static void premain(String a, java.lang.instrument.Instrumentation i) "
                              "{ throw new IllegalStateException(\"shadow\"); } }")
            shadow_compile = subprocess.run([str(JDK / "bin/javac"), "--release", "8",
                                             "-d", str(classes), str(shadow)],
                                            capture_output=True, check=False)
            self.assertEqual(shadow_compile.returncode, 0, shadow_compile.stderr.decode())
            witness_path.unlink()
            substituted = subprocess.run(command, capture_output=True, check=False, timeout=30)
            self.assertNotEqual(substituted.returncode, 0)
            self.assertFalse(witness_path.exists())


if __name__ == "__main__":
    unittest.main()
