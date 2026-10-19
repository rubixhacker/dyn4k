import os
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import full_klib_consumer as route


REPOSITORY = Path(__file__).resolve().parents[2]


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


if __name__ == "__main__":
    unittest.main()
