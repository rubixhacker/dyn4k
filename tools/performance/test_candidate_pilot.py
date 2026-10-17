import csv
import tempfile
import unittest
from pathlib import Path

from candidate_pilot import clean_warmup


class CandidatePlateauTest(unittest.TestCase):
    def test_candidate_metadata_is_separate_from_warmup_csv(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "warmup.csv"
            path.write_text("#process_pid=42\n#route_marker=1\nwarmup_step,elapsed_ns\n0,5\n")
            clean_warmup(path, "direct_kotlin", 42)
            with path.open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([{"warmup_step": "0", "elapsed_ns": "5"}], rows)


if __name__ == "__main__":
    unittest.main()
