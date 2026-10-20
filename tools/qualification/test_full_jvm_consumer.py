import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import full_jvm_consumer as route
import independent_gates


REPOSITORY = Path(__file__).resolve().parents[2]
ARCHIVE = os.environ.get("DYN4K_FULL_JVM_ARCHIVE")
PUBLICATION = os.environ.get("DYN4K_JVM_MODE_PUBLICATION")
DEFAULT_PUBLICATION = os.environ.get("DYN4K_JVM_DEFAULT_PUBLICATION")
PUBLICATION_DIGEST = (independent_gates.archive_digest(PUBLICATION)
                      if ARCHIVE and PUBLICATION else None)
TEST_LANE = os.environ.get("DYN4K_FULL_JVM_LANE", route.LANE)
JAVA_EXECUTABLE_SHA256 = "2a207f5e7d075afa01d97f8048389a64432a44c4a5af0f5e77d6e286ec5f401d"
GRADLE_EXECUTABLE_SHA256 = "b88b6fc9f41fba7bf456a3f8255ee5b7c6c379202ca13f68c3feecebcbc7bd8b"
RUNTIME_EXECUTABLE_SHA256 = (route.sha((Path("/tmp/dyn4k-tools/jdk8" if
    ":minimum:" in TEST_LANE else "/tmp/dyn4k-tools/jdk21") / "bin/java").read_bytes())
    if ARCHIVE else None)


def verify_archive(root, repository, candidate, hashes, identity, digest):
    return route.verify(root, repository, candidate, hashes, identity, digest,
                        JAVA_EXECUTABLE_SHA256, GRADLE_EXECUTABLE_SHA256,
                        RUNTIME_EXECUTABLE_SHA256, TEST_LANE,
                        PUBLICATION, PUBLICATION_DIGEST)


class FullJvmConsumerTests(unittest.TestCase):
    def test_independent_executable_hash_arguments_are_required(self):
        for java_hash, gradle_hash in (
                (None, GRADLE_EXECUTABLE_SHA256),
                (JAVA_EXECUTABLE_SHA256, None),
                ("x" * 64, GRADLE_EXECUTABLE_SHA256),
                (JAVA_EXECUTABLE_SHA256, "x" * 64)):
            with self.subTest(java_hash=java_hash, gradle_hash=gradle_hash):
                with self.assertRaisesRegex(ValueError, "independent.*executable"):
                    route.verify("missing-archive", REPOSITORY, "0" * 40, {}, "Java",
                                 "0" * 64, java_hash, gradle_hash)

    @unittest.skipUnless(ARCHIVE and PUBLICATION, "requires retained JVM and mode archives")
    def test_resealed_forged_toolchain_hashes_fail_public_verify(self):
        root = Path(ARCHIVE)
        receipt = json.loads((root / "receipt.json").read_bytes())
        changes = (
            {"java_executable_sha256": "0" * 64},
            {"gradle_executable_sha256": "1" * 64},
            {"runtime_java_executable_sha256": "3" * 64},
            {"java_executable_sha256": "0" * 64,
             "gradle_executable_sha256": "1" * 64},
        )
        for changed in changes:
            with self.subTest(fields=tuple(changed)), tempfile.TemporaryDirectory() as directory:
                copied = Path(directory) / "forged"
                shutil.copytree(root, copied, copy_function=shutil.copy2)
                forged = copy.deepcopy(receipt)
                forged["toolchain"].update(changed)
                (copied / "receipt.json").write_bytes(route.encoded(forged) + b"\n")
                digest = independent_gates.archive_digest(copied)
                with self.assertRaisesRegex(ValueError, "independent executable"):
                    verify_archive(copied, REPOSITORY, forged["candidate_sha"],
                                   forged["artifact_hashes"], forged["runtime_identity"], digest)
                command = [
                    sys.executable, str(REPOSITORY / "tools/qualification/full_jvm_consumer.py"),
                    "verify", "--lane", TEST_LANE, "--repository", str(REPOSITORY), "--candidate-sha",
                    forged["candidate_sha"], "--archive", str(copied),
                    "--expected-core-sha256", forged["artifact_hashes"]["dyn4k-core"],
                    "--expected-facade-sha256", forged["artifact_hashes"]["dyn4k"],
                    "--runtime-identity", forged["runtime_identity"],
                    "--expected-archive-digest", digest,
                    "--expected-java-executable-sha256", JAVA_EXECUTABLE_SHA256,
                    "--expected-gradle-executable-sha256", GRADLE_EXECUTABLE_SHA256,
                    "--expected-runtime-java-executable-sha256", RUNTIME_EXECUTABLE_SHA256,
                    "--mode-publication", PUBLICATION,
                    "--expected-mode-publication-digest", PUBLICATION_DIGEST,
                ]
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("independent executable SHA-256 differs",
                              result.stderr)

    @unittest.skipUnless(ARCHIVE and PUBLICATION, "requires retained JVM and mode archives")
    def test_public_cli_requires_independent_executable_hashes(self):
        root = Path(ARCHIVE)
        receipt = json.loads((root / "receipt.json").read_bytes())
        base = [sys.executable, str(REPOSITORY / "tools/qualification/full_jvm_consumer.py"),
                "verify", "--lane", TEST_LANE, "--repository", str(REPOSITORY), "--candidate-sha",
                receipt["candidate_sha"], "--archive", str(root),
                "--expected-core-sha256", receipt["artifact_hashes"]["dyn4k-core"],
                "--expected-facade-sha256", receipt["artifact_hashes"]["dyn4k"],
                "--runtime-identity", receipt["runtime_identity"],
                "--expected-archive-digest", independent_gates.archive_digest(root)]
        java = ["--expected-java-executable-sha256", JAVA_EXECUTABLE_SHA256]
        gradle = ["--expected-gradle-executable-sha256", GRADLE_EXECUTABLE_SHA256]
        runtime_java = ["--expected-runtime-java-executable-sha256", RUNTIME_EXECUTABLE_SHA256]
        publication = ["--mode-publication", PUBLICATION,
                       "--expected-mode-publication-digest", PUBLICATION_DIGEST]
        positive = subprocess.run(base + java + gradle + runtime_java + publication,
                                  capture_output=True, text=True)
        self.assertEqual(positive.returncode, 0, positive.stderr)
        self.assertEqual(json.loads(positive.stdout)["selected_cases"], 2526)
        adverse = (
            (base + java + runtime_java, "required"),
            (base + gradle + runtime_java, "required"),
            (base + java + gradle, "required"),
            (base + ["--expected-java-executable-sha256", "x" * 64] + gradle + runtime_java,
             "independent Java and Gradle executable SHA-256 values are required"),
            (base + java + ["--expected-gradle-executable-sha256", "x" * 64] + runtime_java,
             "independent Java and Gradle executable SHA-256 values are required"),
            (base + ["--expected-java-executable-sha256", "0" * 64] + gradle + runtime_java,
             "independent executable SHA-256 differs from receipt"),
            (base + java + ["--expected-gradle-executable-sha256", "1" * 64] + runtime_java,
             "independent executable SHA-256 differs from receipt"),
            (base + java + gradle + ["--expected-runtime-java-executable-sha256", "3" * 64],
             "independent executable SHA-256 differs from receipt"),
        )
        for arguments, error in adverse:
            with self.subTest(arguments=arguments[-2:]):
                result = subprocess.run(arguments + publication, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(error, result.stderr)

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
        candidate = os.environ.get("DYN4K_FULL_JVM_CANDIDATE") or subprocess.check_output(
            ["git", "-C", str(REPOSITORY), "rev-parse", "HEAD"], text=True).strip()
        tracked = subprocess.check_output(
            ["git", "--no-replace-objects", "-C", str(REPOSITORY), "ls-tree", "-r",
             "--name-only", candidate, "--", *route.SOURCE_ROOTS], text=True).splitlines()
        sources = {path: route.sha(route.git_blob(REPOSITORY, candidate, path))
                   for path in tracked if path.endswith((".kt", ".java"))}
        self.assertEqual(len(sources), 175)
        source_bytes = "".join(f"{path}\t{digest}\n" for path, digest in
                               sorted(sources.items())).encode()
        script_bytes = (b"gradle.settingsEvaluated { settings ->\n"
                        b"  if (settings.rootProject.name != 'dyn4k-full-staged-jvm-consumer') {\n"
                        b"    throw new GradleException('qualification project differs')\n"
                        b"  }\n"
                        b"}\n")
        for lane in route.LANES:
            with self.subTest(lane=lane), tempfile.TemporaryDirectory(dir=Path.home()) as directory:
                manifest, contract = route.selected_contract(REPOSITORY, lane)
                cases = contract["cases"]
                self.assertEqual(len(cases), 2526)
                inputs = Path(directory) / "inputs"
                result = route.prepare(REPOSITORY, candidate, inputs, lane)
                self.assertEqual(result, {
                    "manifest_sha256": independent_gates.digest(manifest),
                    "contract_sha256": independent_gates.digest(contract),
                    "source_count": 175, "selected_cases": 2526,
                })
                expected = {"source-inventory.tsv": source_bytes,
                            "lane-script": script_bytes}
                for module, name, count in (("dyn4k-core", "core-cases.tsv", 2465),
                                            ("dyn4k", "facade-cases.tsv", 61)):
                    selected = sorted((item for item in cases if item["module"] == module),
                                      key=lambda item: item["id"])
                    self.assertEqual(len(selected), count)
                    expected[name] = "".join(
                        f"{item['id']}\t{item['classname']}\t{item['method']}\n"
                        for item in selected).encode()
                    self.assertTrue(all(sources[item["source"]["path"]] ==
                                        item["source"]["sha256"] for item in selected))
                names = {path.name for path in inputs.iterdir()}
                self.assertEqual(names, set(expected))
                self.assertNotIn(lane, names)
                for name, data in expected.items():
                    self.assertIsNotNone(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name))
                    self.assertNotIn(":", name)
                    self.assertEqual((inputs / name).read_bytes(), data)

    def test_all_four_lanes_select_original_jvm_contract(self):
        selected = [route.selected_contract(REPOSITORY, lane)[1]
                    for lane in route.LANES]
        ids = [[item["id"] for item in contract["cases"]] for contract in selected]
        self.assertTrue(all(item == ids[0] for item in ids))
        self.assertEqual(2526, len(ids[0]))
        with self.assertRaisesRegex(ValueError, "unsupported full JVM lane"):
            route.selected_contract(REPOSITORY, "jvm:Java:minimum:equivalent")

    @unittest.skipUnless(ARCHIVE and PUBLICATION, "requires retained JVM and mode archives")
    def test_public_replay_and_resealed_adverse_archive(self):
        root = Path(ARCHIVE)
        receipt = json.loads((root / "receipt.json").read_bytes())
        candidate = receipt["candidate_sha"]
        hashes = receipt["artifact_hashes"]
        identity = receipt["runtime_identity"]
        digest = independent_gates.archive_digest(root)
        positive = verify_archive(root, REPOSITORY, candidate, hashes, identity, digest)
        self.assertEqual(positive["status"], "PASSED")
        self.assertEqual(positive["selected_cases"], 2526)
        lane = independent_gates.evaluate(
            independent_gates.load_approved_manifest(REPOSITORY), candidate,
            TEST_LANE, {"staged-consumer": root}, REPOSITORY, hashes, identity,
            {"staged-consumer": digest})
        self.assertEqual(lane["gates"]["staged-consumer"]["status"], "PASSED")
        self.assertEqual(lane["status"], "NOT_RUN")

        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "wrong-publication"
            shutil.copytree(PUBLICATION, copied, copy_function=shutil.copy2)
            staged = route.target_binary(copied / "staged", "dyn4k-core")
            staged.write_bytes(b"wrong library JAR")
            with self.assertRaises(ValueError):
                route.verify(root, REPOSITORY, candidate, hashes, identity, digest,
                             JAVA_EXECUTABLE_SHA256, GRADLE_EXECUTABLE_SHA256,
                             RUNTIME_EXECUTABLE_SHA256, TEST_LANE, copied,
                             independent_gates.archive_digest(copied))

        if TEST_LANE.endswith(":no-optimize") and DEFAULT_PUBLICATION:
            with tempfile.TemporaryDirectory() as directory:
                copied = Path(directory) / "copy"
                shutil.copytree(root, copied, copy_function=shutil.copy2)
                altered = copy.deepcopy(receipt)
                default = Path(DEFAULT_PUBLICATION).resolve()
                default_hashes = {module: route.sha(route.target_binary(
                    default / "staged", module).read_bytes()) for module in route.MODULES}
                altered["artifact_hashes"] = default_hashes
                altered["mode_publication"] = {
                    "path": str(default),
                    "archive_digest": independent_gates.archive_digest(default)}
                (copied / "receipt.json").write_bytes(route.encoded(altered) + b"\n")
                forged_digest = independent_gates.archive_digest(copied)
                with self.assertRaisesRegex(ValueError, "mode publication"):
                    route.verify(copied, REPOSITORY, candidate, default_hashes, identity,
                                 forged_digest, JAVA_EXECUTABLE_SHA256,
                                 GRADLE_EXECUTABLE_SHA256, RUNTIME_EXECUTABLE_SHA256,
                                 TEST_LANE, default, altered["mode_publication"]["archive_digest"])

        def copied_archive(directory):
            copied = Path(directory) / "copy"
            shutil.copytree(root, copied, copy_function=shutil.copy2)
            altered = copy.deepcopy(receipt)
            return copied, altered

        def reseal(copied, altered, changed):
            entries = {item["path"]: item for item in altered["files"]}
            stdout = copied / "stdout.txt"
            output = stdout.read_bytes()
            for relative, marker in changed.items():
                path = copied / relative
                old = entries[relative]["sha256"].encode()
                new = route.sha(path.read_bytes())
                if marker:
                    prefix = f"QUALIFICATION_{marker}_SHA256=".encode()
                    self.assertIn(prefix + old, output)
                    output = output.replace(prefix + old, prefix + new.encode())
                entries[relative]["sha256"] = new
                stamp = entries[relative]["mtime_ns"]
                os.utime(path, ns=(stamp, stamp))
            stdout.write_bytes(output)
            entries["stdout.txt"]["sha256"] = route.sha(output)
            stamp = entries["stdout.txt"]["mtime_ns"]
            os.utime(stdout, ns=(stamp, stamp))
            (copied / "receipt.json").write_bytes(route.encoded(altered) + b"\n")
            return independent_gates.archive_digest(copied)

        with tempfile.TemporaryDirectory() as directory:
            copied, altered = copied_archive(directory)
            stdout = copied / "stdout.txt"
            lines = stdout.read_text().splitlines(keepends=True)
            executor = next(index for index, line in enumerate(lines)
                            if line.startswith("Starting process 'Gradle Test Executor "))
            lines[executor] = "Starting process 'Gradle Test Executor removed'.\n"
            stdout.write_text("".join(lines))
            forged_digest = reseal(copied, altered, {"stdout.txt": None})
            with self.assertRaisesRegex(ValueError, "Gradle Test Executor"):
                verify_archive(copied, REPOSITORY, candidate, hashes, identity, forged_digest)

        with tempfile.TemporaryDirectory() as directory:
            copied, altered = copied_archive(directory)
            (copied / "receipt.json").write_bytes(route.encoded(altered) + b"\n")
            copied_digest = independent_gates.archive_digest(copied)
            self.assertEqual(verify_archive(copied, REPOSITORY, candidate, hashes,
                                            identity, copied_digest)["status"], "PASSED")

        for mutation in ("missing", "duplicate", "foreign", "skipped"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                copied, altered = copied_archive(directory)
                raw_rel = altered["raw_consumer_xml"][0]
                normal_rel = raw_rel.replace("reports/raw/", "reports/normalized/")
                for relative in (raw_rel, normal_rel):
                    path = copied / relative
                    suite = ET.fromstring(path.read_bytes())
                    cases = list(suite.iter("testcase"))
                    if mutation == "missing":
                        suite.remove(cases[0])
                        suite.set("tests", str(len(cases) - 1))
                    elif mutation == "duplicate":
                        suite.append(copy.deepcopy(cases[0]))
                        suite.set("tests", str(len(cases) + 1))
                    elif mutation == "foreign":
                        cases[0].set("classname", "foreign.UnapprovedTest")
                        if relative == normal_rel:
                            cases[0].set("id", "dyn4k-core:foreign.UnapprovedTest#method")
                    else:
                        ET.SubElement(cases[0], "skipped")
                        suite.set("skipped", "1")
                    path.write_bytes(ET.tostring(suite))
                digest = reseal(copied, altered, {raw_rel: "RAW_XML",
                                                  normal_rel: "CONSUMER_XML"})
                with self.assertRaises(ValueError):
                    verify_archive(copied, REPOSITORY, candidate, hashes, identity, digest)

        for mutation in ("source-inventory", "source-build", "binary-bytes",
                         "build-configuration"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                copied, altered = copied_archive(directory)
                if mutation == "source-inventory":
                    relative, marker = "inputs/source-inventory.tsv", "SOURCE_INVENTORY"
                    path = copied / relative
                    path.write_bytes(path.read_bytes().replace(b"dyn4k-core", b"other-core", 1))
                elif mutation == "source-build":
                    relative, marker = "provider-graph.json", "PROVIDER_GRAPH"
                    path = copied / relative
                    graph = json.loads(path.read_bytes())
                    graph["compile"][0]["artifacts"][0]["file"] = (
                        str(REPOSITORY / "dyn4k-core/build/libs/forged.jar"))
                    path.write_bytes(route.encoded(graph))
                elif mutation == "binary-bytes":
                    relative = altered["resolved_artifacts"]["dyn4k-core"]
                    marker = "RESOLVED_DYN4K_CORE"
                    path = copied / relative
                    data = bytearray(path.read_bytes())
                    data[100] ^= 1
                    path.write_bytes(data)
                else:
                    relative, marker = "build-configuration.json", "BUILD_CONFIGURATION"
                    path = copied / relative
                    proof = json.loads(path.read_bytes())
                    proof["configuration"] = ("no-optimize" if
                        proof["configuration"] == "default" else "default")
                    path.write_bytes(route.encoded(proof))
                digest = reseal(copied, altered, {relative: marker})
                with self.assertRaises(ValueError):
                    verify_archive(copied, REPOSITORY, candidate, hashes, identity, digest)

        for mutation in ("different-input", "wrong-home", "missing-toolchain"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                copied, altered = copied_archive(directory)
                if mutation == "different-input":
                    altered["process"]["command"] = [
                        arg.replace("/core-cases.tsv", "/other-cases.tsv")
                        for arg in altered["process"]["command"]]
                elif mutation == "wrong-home":
                    altered["toolchain"]["gradle_user_home"] = "/tmp/other-gradle-home"
                else:
                    del altered["toolchain"]["java_executable_sha256"]
                (copied / "receipt.json").write_bytes(route.encoded(altered) + b"\n")
                with self.assertRaises(ValueError):
                    verify_archive(copied, REPOSITORY, candidate, hashes, identity,
                                   independent_gates.archive_digest(copied))

        with self.assertRaises(ValueError):
            verify_archive(root, REPOSITORY, "0" * 40, hashes, identity, digest)
        with self.assertRaisesRegex(ValueError, "candidate contract"):
            route.verify(root, REPOSITORY, candidate, hashes, identity, digest,
                         JAVA_EXECUTABLE_SHA256, GRADLE_EXECUTABLE_SHA256,
                         RUNTIME_EXECUTABLE_SHA256,
                         next(lane for lane in route.LANES if lane != TEST_LANE),
                         PUBLICATION, PUBLICATION_DIGEST)
        with self.assertRaises(ValueError):
            verify_archive(root, REPOSITORY, candidate, hashes, "wrong runtime", digest)


if __name__ == "__main__":
    unittest.main()
