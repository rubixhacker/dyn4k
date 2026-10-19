import copy
import json
import os
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
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
        lane = independent_gates.evaluate(
            independent_gates.load_approved_manifest(REPOSITORY), candidate,
            route.LANE, {"staged-consumer": root}, REPOSITORY, hashes, identity,
            {"staged-consumer": digest})
        self.assertEqual(lane["gates"]["staged-consumer"]["status"], "PASSED")
        self.assertEqual(lane["status"], "NOT_RUN")

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
            (copied / "receipt.json").write_bytes(route.encoded(altered) + b"\n")
            copied_digest = independent_gates.archive_digest(copied)
            self.assertEqual(route.verify(copied, REPOSITORY, candidate, hashes,
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
                    route.verify(copied, REPOSITORY, candidate, hashes, identity, digest)

        for mutation in ("source-inventory", "source-build", "binary-bytes"):
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
                else:
                    relative = altered["resolved_artifacts"]["dyn4k-core"]
                    marker = "RESOLVED_DYN4K_CORE"
                    path = copied / relative
                    data = bytearray(path.read_bytes())
                    data[100] ^= 1
                    path.write_bytes(data)
                digest = reseal(copied, altered, {relative: marker})
                with self.assertRaises(ValueError):
                    route.verify(copied, REPOSITORY, candidate, hashes, identity, digest)

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
                    route.verify(copied, REPOSITORY, candidate, hashes, identity,
                                 independent_gates.archive_digest(copied))

        with self.assertRaises(ValueError):
            route.verify(root, REPOSITORY, "0" * 40, hashes, identity, digest)


if __name__ == "__main__":
    unittest.main()
