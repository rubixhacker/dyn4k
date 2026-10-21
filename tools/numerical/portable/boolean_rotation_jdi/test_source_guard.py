from pathlib import Path
import tempfile
import unittest

from source_guard import PINNED_FILES, verify_source_schedule


ROOT = Path(__file__).resolve().parents[4]


class SourceGuardTest(unittest.TestCase):
    def test_body_mapping_owner_is_source_pinned(self):
        self.assertIn(
            "dyn4k-core/src/commonMain/kotlin/org/dyn4j/dynamics/joint/"
            "AbstractPairedBodyJoint.kt", PINNED_FILES)

    def test_exact_checkout_matches(self):
        self.assertEqual(verify_source_schedule(ROOT)["status"], "MATCHED_SOURCE_SCHEDULE")

    def test_changed_and_missing_source_reject(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            for name in PINNED_FILES:
                path = target / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((ROOT / name).read_bytes())
            victim = target / next(iter(PINNED_FILES))
            victim.write_bytes(victim.read_bytes() + b"changed")
            self.assertEqual(verify_source_schedule(target)["status"], "FAILED_SOURCE_SCHEDULE")
            victim.unlink()
            self.assertEqual(verify_source_schedule(target)["status"], "FAILED_SOURCE_SCHEDULE")


if __name__ == "__main__":
    unittest.main()
