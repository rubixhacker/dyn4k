import hashlib
import json
import os
import subprocess
import unittest
from pathlib import Path

from candidate_runner import ROOT
from test_sustained_jvm_memory import (BASELINE, JDK, RAW, SOURCE, rows,
                                       validate_binding, validate_plateau,
                                       validate_warmup_clock)


GRADLE = Path("/tmp/dyn4k-tools/gradle-9.5.0/bin/gradle")
STAGING = ROOT / "build/staging-repository/io/github/rubixhacker"


class CandidateJvmP2Control(unittest.TestCase):
    @staticmethod
    def prepare_empty_directory(path):
        if path.exists():
            if not path.is_dir() or any(path.iterdir()):
                raise AssertionError(f"refusing to reuse nonempty control path: {path}")
        else:
            path.mkdir(parents=True)
        return path

    @classmethod
    def build(cls, name, command, cwd=ROOT):
        result = subprocess.run(command, cwd=cwd, env=cls.env, capture_output=True,
                                text=True, timeout=180)
        (cls.root / f"{name}.stdout.raw").write_text(result.stdout)
        (cls.root / f"{name}.stderr.raw").write_text(result.stderr)
        (cls.root / f"{name}.result.json").write_text(json.dumps(
            {"command": command, "exit_code": result.returncode,
             "environment": {key: cls.env.get(key) for key in
                             ("JAVA_HOME", "TMPDIR", "GRADLE_OPTS", "JAVA_TOOL_OPTIONS",
                              "ANDROID_HOME", "ANDROID_SDK_ROOT")}}, indent=2) + "\n")
        if result.returncode:
            raise AssertionError(f"{name} failed: {result.stderr[-2000:]}")

    @classmethod
    def setUpClass(cls):
        cls.root = RAW / "candidate-p2"
        cls.prepare_empty_directory(cls.root)
        tmp = cls.prepare_empty_directory(cls.root / "java-gradle-tmp")
        cls.env = os.environ.copy()
        for name in ("OLLAMA_API_KEY", "JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS",
                     "_JAVA_OPTIONS", "CLASSPATH", "ANDROID_HOME",
                     "ANDROID_SDK_ROOT", "GRADLE_OPTS"):
            cls.env.pop(name, None)
        selected_sdk = os.environ.get("DYN4K_ANDROID_SDK_PATH")
        if selected_sdk is not None:
            sdk = Path(selected_sdk).resolve(strict=True)
            if not (sdk / "platforms").is_dir() or not (sdk / "build-tools").is_dir():
                raise AssertionError(f"selected Android SDK is incomplete: {sdk}")
            cls.env.update(ANDROID_HOME=str(sdk), ANDROID_SDK_ROOT=str(sdk))
        cls.env.update(JAVA_HOME=str(JDK), TMPDIR=str(tmp),
                       PATH=f"{JDK / 'bin'}:{os.environ['PATH']}",
                       GRADLE_OPTS=(f"-Djava.io.tmpdir={tmp} "
                                    "-Dorg.gradle.workers.max=1"),
                       JAVA_TOOL_OPTIONS=f"-XX:-UsePerfData -Djava.io.tmpdir={tmp}")
        classes = cls.root / "classes"
        cls.prepare_empty_directory(classes)
        cls.build("javac", [str(JDK / "bin/javac"), "--release", "21", "-cp",
                            str(BASELINE), "-d", str(classes),
                            str(SOURCE / "SustainedSidecars.java"),
                            str(SOURCE / "SustainedPilot.java")])
        cls.harness = cls.root / "sustained-harness.jar"
        cls.build("harness-jar", [str(JDK / "bin/jar"), "--create", "--file",
                                  str(cls.harness), "-C", str(classes), "."])
        cls.build("stage", [str(GRADLE), "--offline", "--no-daemon", "--max-workers=1",
                            ":dyn4k-core:publishJvmPublicationToStagingRepository",
                            ":dyn4k:publishJvmPublicationToStagingRepository",
                            ":dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository",
                            ":dyn4k:publishKotlinMultiplatformPublicationToStagingRepository"])
        cls.build("consumer", [str(GRADLE), "--offline", "--no-daemon", "--max-workers=1", "-p",
                               "consumers/performance", "-I",
                               str(SOURCE / "direct.init.gradle"),
                               f"-PsustainedHarnessJar={cls.harness}",
                               "writeCandidateClasspath"])
        adapter_class = ROOT / "consumers/performance/build/classes/kotlin/main"
        cls.adapter = cls.root / "sustained-direct-adapter.jar"
        cls.build("adapter-jar", [str(JDK / "bin/jar"), "--create", "--file",
                                  str(cls.adapter), "-C", str(adapter_class),
                                  "performance/SustainedDirectPilotKt.class"])
        lines = (ROOT / "consumers/performance/build/candidate-paths.tsv").read_text().splitlines()
        cls.classpaths = dict(line.split("\t", 1) for line in lines)
        version = "0.1.0-alpha.1"
        core = STAGING / f"dyn4k-core-jvm/{version}/dyn4k-core-jvm-{version}.jar"
        kotlin = STAGING / f"dyn4k-jvm/{version}/dyn4k-jvm-{version}.jar"
        cls.core_hash = hashlib.sha256(core.read_bytes()).hexdigest()
        cls.kotlin_hash = hashlib.sha256(kotlin.read_bytes()).hexdigest()

    def execute(self, route, mode, disabled_gc=False):
        folder = self.root / f"{route}-{mode}{'-disabled-gc' if disabled_gc else ''}"
        self.prepare_empty_directory(folder)
        files = {name: folder / name for name in
                 ("provider.json", "clock-origin.json", "warmup-clock.csv",
                  "memory-v2.jsonl", "allocation-v2.jsonl", "plateau-v2.jsonl",
                  "steps.csv", "stdout.raw", "stderr.raw", "command.json",
                  "process-result.json")}
        nonce = f"p2-{route}-{mode}{'-disabled' if disabled_gc else ''}"
        env = self.env.copy()
        env.update(DYN4K_PROVIDER_JSON=str(files["provider.json"]),
                   DYN4K_CLOCK_ORIGIN_JSON=str(files["clock-origin.json"]),
                   DYN4K_WARMUP_CLOCK_CSV=str(files["warmup-clock.csv"]),
                   DYN4K_MEMORY_V2_JSONL=str(files["memory-v2.jsonl"]),
                   DYN4K_ALLOCATION_V2_JSONL=str(files["allocation-v2.jsonl"]),
                   DYN4K_PLATEAU_V2_JSONL=str(files["plateau-v2.jsonl"]),
                   DYN4K_CLOCK_NONCE=nonce,
                   DYN4K_SOURCE_COMMIT=subprocess.check_output(
                       ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                   DYN4K_ARTIFACT_HASHES_JSON=json.dumps(
                       {"core": self.core_hash, "kotlin": self.kotlin_hash}),
                   DYN4K_BASELINE_SHA256=hashlib.sha256(BASELINE.read_bytes()).hexdigest())
        prefix = str(self.adapter) if route == "direct_kotlin" else str(self.harness)
        main = "performance.SustainedDirectPilotKt" if route == "direct_kotlin" else "SustainedPilot"
        command = [str(JDK / "bin/java"),
                   f"-Djava.io.tmpdir={self.root / 'java-gradle-tmp'}",
                   *(["-XX:+DisableExplicitGC"] if disabled_gc else []),
                   "-cp", os.pathsep.join((prefix, self.classpaths[route])),
                   main, "separated", "default", "small", "30", "1", mode, "1", route]
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                text=True, timeout=90)
        files["steps.csv"].write_text(result.stdout)
        files["stderr.raw"].write_text(result.stderr)
        files["stdout.raw"].write_text(result.stdout)
        files["command.json"].write_text(json.dumps(command, indent=2) + "\n")
        files["process-result.json"].write_text(json.dumps(
            {"command": command, "exit_code": result.returncode,
             "nonce": nonce, "source_commit": env["DYN4K_SOURCE_COMMIT"],
             "environment": {key: env.get(key) for key in
                             ("JAVA_HOME", "TMPDIR", "JAVA_TOOL_OPTIONS",
                              "ANDROID_HOME", "ANDROID_SDK_ROOT")}}, indent=2) + "\n")
        return result, files, nonce

    def test_control_root_rejects_unrelated_nonempty_directory(self):
        unrelated = self.root / "unrelated"
        unrelated.mkdir()
        marker = unrelated / "keep.txt"
        marker.write_text("preserve this file\n")
        with self.assertRaisesRegex(AssertionError, "refusing to reuse nonempty"):
            self.prepare_empty_directory(unrelated)
        self.assertEqual("preserve this file\n", marker.read_text())

    def test_candidate_memory_disabled_gc_fails_closed(self):
        for route in ("direct_kotlin", "compatibility"):
            with self.subTest(route=route):
                result, files, nonce = self.execute(route, "memory", True)
                self.assertNotEqual(0, result.returncode)
                self.assertIn("#retained_collection_count_delta=0", result.stderr)
                self.assertIn("retained post-collection probe unsupported", result.stderr)
                memory = rows(files["memory-v2.jsonl"])
                validate_binding(memory, files["provider.json"], nonce, "memory")
                provider = json.loads(files["provider.json"].read_text())
                self.assertEqual(self.core_hash, provider["loaded_core_sha256"])
                self.assertEqual(self.kotlin_hash if route == "direct_kotlin" else None,
                                 provider["loaded_kotlin_sha256"])
                self.assertEqual(["empty", "construction", "warmup"],
                                 [row["phase"] for row in memory])
                self.assertFalse(any(row["managed_post_collection"] for row in memory))
                validate_warmup_clock(files["warmup-clock.csv"], files["stderr.raw"],
                                      files["clock-origin.json"])

    def test_candidate_memory_observes_collection(self):
        for route in ("direct_kotlin", "compatibility"):
            with self.subTest(route=route):
                result, files, nonce = self.execute(route, "memory")
                self.assertEqual(0, result.returncode, result.stderr)
                memory = rows(files["memory-v2.jsonl"])
                validate_binding(memory, files["provider.json"], nonce, "memory")
                self.assertEqual(["empty", "construction", "warmup", "retained", "measure"],
                                 [row["phase"] for row in memory])
                self.assertTrue(memory[3]["managed_post_collection"])
                self.assertGreater(memory[3]["collection_count_delta"], 0)
                validate_warmup_clock(files["warmup-clock.csv"], files["stderr.raw"],
                                      files["clock-origin.json"])

    def test_candidate_plateau_has_bound_warmup_clock(self):
        for route in ("direct_kotlin", "compatibility"):
            with self.subTest(route=route):
                result, files, nonce = self.execute(route, "plateau")
                self.assertEqual(0, result.returncode, result.stderr)
                plateau = rows(files["plateau-v2.jsonl"])
                validate_binding(plateau, files["provider.json"], nonce, "plateau")
                provider = json.loads(files["provider.json"].read_text())
                self.assertEqual(self.core_hash, provider["loaded_core_sha256"])
                self.assertEqual(self.kotlin_hash if route == "direct_kotlin" else None,
                                 provider["loaded_kotlin_sha256"])
                validate_plateau(plateau, files["steps.csv"])
                validate_warmup_clock(files["warmup-clock.csv"], files["stderr.raw"],
                                      files["clock-origin.json"])
                self.assertEqual(100, len(rows(files["allocation-v2.jsonl"])))

    def test_candidate_plateau_disabled_gc_fails_closed(self):
        for route in ("direct_kotlin", "compatibility"):
            with self.subTest(route=route):
                result, files, nonce = self.execute(route, "plateau", True)
                self.assertNotEqual(0, result.returncode)
                self.assertIn("post-collection plateau probe unsupported: no collection observed",
                              result.stderr)
                self.assertEqual([], rows(files["plateau-v2.jsonl"]))
                validate_warmup_clock(files["warmup-clock.csv"], files["stderr.raw"],
                                      files["clock-origin.json"])
