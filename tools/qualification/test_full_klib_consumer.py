import os
import copy
import json
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import full_klib_consumer as route
import independent_gates


REPOSITORY = Path(__file__).resolve().parents[2]
ARCHIVE = os.environ.get("DYN4K_FULL_KLIB_ARCHIVE")
TRUSTED = os.environ.get("DYN4K_FULL_KLIB_TRUSTED_TOOLCHAIN")


class FullKlibConsumerTests(unittest.TestCase):
    def test_approved_portable_contract_and_exact_sources(self):
        candidate = __import__("subprocess").check_output(
            ["git", "-C", str(REPOSITORY), "rev-parse", "HEAD"], text=True).strip()
        for lane in route.LOCAL_LANES:
            _, selected = route.contract(REPOSITORY, lane)
            self.assertEqual(len(selected["cases"]), 2523)
            prepared = route.input_bytes(REPOSITORY, candidate, lane)
            self.assertEqual(len(prepared["source-inventory.tsv"].splitlines()), 169)
            self.assertEqual(len(prepared["core-cases.tsv"].splitlines()), 2465)
            self.assertEqual(len(prepared["facade-cases.tsv"].splitlines()), 58)

    def test_native_xml_requires_original_selected_assertions(self):
        selected = {("a.B", "method"): "dyn4k-core:a.B#method"}
        raw = (b'<testsuite tests="1" failures="0" errors="0" skipped="0" time="0.1">'
               b'<testcase classname="linuxX64Test.a.B" name="method[linuxX64]" time="0.1"/>'
               b'</testsuite>')
        ids, normalized = route._report(raw, "linuxX64", selected)
        self.assertEqual(ids, ["dyn4k-core:a.B#method"])
        self.assertEqual(ET.fromstring(normalized).find("testcase").get("id"), ids[0])
        for altered in (raw.replace(b"method[linuxX64]", b"other[linuxX64]"),
                        raw.replace(b'skipped="0"', b'skipped="1"'),
                        raw.replace(b'tests="1"', b'tests="2"')):
            with self.subTest(altered=altered), self.assertRaises(ValueError):
                route._report(altered, "linuxX64", selected)

    @unittest.skipUnless(os.environ.get("DYN4K_KLIB_BOUNDED_TAP"),
                         "requires retained original bounded Node TAP")
    def test_node_tap_rejects_fabricated_and_failed_rows(self):
        tap = Path(os.environ["DYN4K_KLIB_BOUNDED_TAP"]).read_bytes()
        selected = route._selected_cases(Path(os.environ["DYN4K_KLIB_BOUNDED_CASES"]))
        ids, xml = route._tap(tap, selected)
        self.assertEqual(len(ids), 4)
        self.assertEqual(len(list(ET.fromstring(xml).iter("testcase"))), 4)
        with self.assertRaises(ValueError):
            route._tap(tap.replace(b"# pass 4", b"# pass 3"), selected)
        with self.assertRaises(ValueError):
            route._tap(tap.replace(b"# skipped 0", b"# skipped 1"), selected)
        with self.assertRaises(ValueError):
            route._tap(tap.replace(b"ok 1 - equalDistanceEdges", b"not ok 1 - equalDistanceEdges"),
                       selected)
        with self.assertRaises(ValueError):
            route._tap(tap.replace(b"# Subtest: equalDistanceEdges", b"# Subtest: fakeMethod"),
                       selected)
        with self.assertRaises(ValueError):
            route._tap(tap.replace(b"ok 1 - equalDistanceEdges", b"ok 1 - fakeMethod"),
                       selected)

    @unittest.skipUnless(ARCHIVE and TRUSTED, "requires retained real full KLIB archive")
    def test_public_replay_and_resealed_adverse_archive(self):
        original = Path(ARCHIVE)
        receipt = json.loads((original / "receipt.json").read_bytes())
        trusted = json.loads(Path(TRUSTED).read_bytes())
        candidate = receipt["candidate_sha"]
        lane = receipt["lane"]
        hashes = receipt["artifact_hashes"]
        identity = receipt["runtime_identity"]

        def check(path, current_receipt):
            return route.verify(path, REPOSITORY, candidate, lane, hashes, identity,
                                independent_gates.archive_digest(path), trusted)

        self.assertEqual(check(original, receipt)["status"], "PASSED")

        def copied(directory):
            path = Path(directory) / "archive"
            shutil.copytree(original, path, copy_function=shutil.copy2)
            return path, copy.deepcopy(receipt)

        def reseal(path, changed):
            for item in changed["files"]:
                file = path / item["path"]
                os.utime(file, ns=(item["mtime_ns"], item["mtime_ns"]))
                item["sha256"] = route.sha(file.read_bytes())
            (path / "receipt.json").write_bytes(route.encoded(changed) + b"\n")

        with tempfile.TemporaryDirectory() as directory:
            path, changed = copied(directory)
            changed["producer_paths"]["work_root"] = changed["producer_paths"]["checkout"]
            reseal(path, changed)
            with self.assertRaisesRegex(ValueError, "aliases source checkout"):
                check(path, changed)

        with tempfile.TemporaryDirectory() as directory:
            path, changed = copied(directory)
            changed["process"]["command"][-1] = "wrong:lane:task"
            reseal(path, changed)
            with self.assertRaisesRegex(ValueError, "process command differs"):
                check(path, changed)

        with tempfile.TemporaryDirectory() as directory:
            path, changed = copied(directory)
            changed["toolchain"]["java_sha256"] = "0" * 64
            reseal(path, changed)
            with self.assertRaisesRegex(ValueError, "toolchain differs"):
                check(path, changed)

        with tempfile.TemporaryDirectory() as directory:
            path, changed = copied(directory)
            changed["target"] = "wrong-target"
            reseal(path, changed)
            with self.assertRaisesRegex(ValueError, "target differs"):
                check(path, changed)

        with tempfile.TemporaryDirectory() as directory:
            path, changed = copied(directory)
            graph_path = path / "provider-graph.json"
            graph = json.loads(graph_path.read_bytes())
            provider = next(item for item in graph["compile"][0]["artifacts"]
                            if item["component"].startswith("io.github.rubixhacker:"))
            provider["file"] = str(REPOSITORY / "build/source-project-binary.klib")
            graph_path.write_bytes(route.encoded(graph))
            reseal(path, changed)
            with self.assertRaisesRegex(ValueError, "resolved external KLIB differs"):
                check(path, changed)

        with tempfile.TemporaryDirectory() as directory:
            path, changed = copied(directory)
            binary = path / changed["resolved_artifacts"]["dyn4k-core"]
            binary.write_bytes(binary.read_bytes() + b"changed")
            reseal(path, changed)
            with self.assertRaisesRegex(ValueError, "resolved external KLIB differs"):
                check(path, changed)

        if lane.startswith("linuxX64:"):
            raw = receipt["raw_consumer_xml"][0]
            with tempfile.TemporaryDirectory() as directory:
                path, changed = copied(directory)
                xml_path = path / raw
                suite = ET.fromstring(xml_path.read_bytes())
                suite.remove(next(suite.iter("testcase")))
                xml_path.write_bytes(ET.tostring(suite))
                reseal(path, changed)
                with self.assertRaisesRegex(ValueError, "native raw XML records missing"):
                    check(path, changed)
            with tempfile.TemporaryDirectory() as directory:
                path, changed = copied(directory)
                xml_path = path / raw
                suite = ET.fromstring(xml_path.read_bytes())
                next(suite.iter("testcase")).set("name", "fabricated[linuxX64]")
                xml_path.write_bytes(ET.tostring(suite))
                reseal(path, changed)
                with self.assertRaisesRegex(ValueError, "native raw case is foreign"):
                    check(path, changed)
        else:
            tap = receipt["raw_consumer_tap"][0]
            with tempfile.TemporaryDirectory() as directory:
                path, changed = copied(directory)
                tap_path = path / tap
                tap_path.write_bytes(tap_path.read_bytes().replace(b"# pass 2465", b"# pass 2464"))
                reseal(path, changed)
                with self.assertRaisesRegex(ValueError, "Node TAP summary differs"):
                    check(path, changed)
            with tempfile.TemporaryDirectory() as directory:
                path, changed = copied(directory)
                normal = path / "reports/normalized/core/TEST-Node.xml"
                suite = ET.fromstring(normal.read_bytes())
                next(suite.iter("testcase")).set("id", "fabricated:id")
                normal.write_bytes(ET.tostring(suite))
                reseal(path, changed)
                with self.assertRaisesRegex(ValueError, "normalized full KLIB method IDs differ"):
                    check(path, changed)


if __name__ == "__main__":
    unittest.main()
