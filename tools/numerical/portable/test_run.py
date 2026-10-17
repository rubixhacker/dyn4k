import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run


class ExtractionTest(unittest.TestCase):
    def test_xml_extraction_retains_whole_trace_and_case_slice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "build/test-results/jvmTest"
            results.mkdir(parents=True)
            case_id = "geometry-boundary-s0-o0-d0"
            rows = [{"kind": "inputs", "id": case_id},
                    {"kind": "state", "id": case_id, "step": 1},
                    {"kind": "case-end", "id": case_id}]
            xml = ("<?xml version=\"1.0\"?>\n"
                   "<testsuite tests=\"1\" skipped=\"0\" failures=\"0\" errors=\"0\">\n"
                   "<system-out><![CDATA[" +
                   "".join("NUMERICAL_JSON " + json.dumps(row) + "\n" for row in rows) +
                   "]]></system-out>\n</testsuite>\n")
            (results / "TEST-portable.PortableMatrixTest.xml").write_text(xml)
            output = root / "evidence"
            output.mkdir()
            with patch.object(run, "PORTABLE", root):
                trace, attributes = run.extract_xml("jvm", output)
            self.assertEqual(attributes["tests"], "1")
            self.assertEqual(trace.read_text(), (output / "cases" / f"{case_id}.jsonl").read_text())
            self.assertEqual(len(trace.read_text().splitlines()), 3)
            self.assertTrue((output / "matrix.xml").is_file())


if __name__ == "__main__":
    unittest.main()
