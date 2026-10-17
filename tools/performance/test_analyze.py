import unittest

from analyze import bootstrap_ratio, plateau_status, warmup_status


class AnalysisContractTest(unittest.TestCase):
    def test_unchanged_paired_series_has_unit_interval(self):
        rows = [{"elapsed_ns": str(1000 + step % 17)} for step in range(30 * 60)]
        interval = bootstrap_ratio(rows, rows, 60, draws=200)
        self.assertEqual(1.0, interval["lower_95"])
        self.assertEqual(1.0, interval["upper_95"])

    def test_short_warmup_cannot_converge_by_definition(self):
        rows = [{"elapsed_ns": "1000"} for _ in range(60)]
        self.assertEqual("unvalidated", warmup_status(rows, 60))

    def test_growth_in_create_dispose_series_is_not_stable(self):
        rows = [{"heap_after_collection_bytes": str(1000 + cycle * 100), "collection_count": str(cycle)}
                for cycle in range(100)]
        self.assertEqual("not_stable", plateau_status(rows))


if __name__ == "__main__":
    unittest.main()
