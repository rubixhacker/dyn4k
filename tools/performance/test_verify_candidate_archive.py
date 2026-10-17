import json
import shutil
import tempfile
import unittest
from pathlib import Path

from verify_candidate_archive import verify


ARCHIVE = Path(__file__).resolve().parents[2] / "docs/research/performance-candidate-v1"


class ArchiveVerificationTest(unittest.TestCase):
    def test_altered_indexed_median_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            copied = Path(folder) / "archive"
            shutil.copytree(ARCHIVE, copied)
            index = copied / "pilot/evidence.json"
            evidence = json.loads(index.read_text())
            evidence["results"][0]["median_step_ns"] = 1
            index.write_text(json.dumps(evidence))
            with self.assertRaisesRegex(ValueError, "median_step_ns"):
                verify(copied)


if __name__ == "__main__":
    unittest.main()
