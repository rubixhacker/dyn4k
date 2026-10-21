import unittest
import shutil
import tempfile
import json
from pathlib import Path
from unittest.mock import patch

from pulley_jdi_v1 import Rejected
from pulley_jdi_v2 import (class_inventory, compare_indexed_onecase,
                           inspect_capture, inspect_loaded_code)
from pulley_jdi_capture_v2 import capture, replay_capture


class PulleyJdiV2Test(unittest.TestCase):
    ROOT = Path('/var/home/stewart/dyn4k-evidence/root-jdi-loaded-code')
    BASELINE = Path('/tmp/dyn4k-baseline-cache/dyn4j-6.0.0.jar')
    CANDIDATE = Path('/var/home/stewart/dyn4k-evidence/session-control/numerical-followup-7d/wheel/capture-7d/artifact.jar')
    TASK_HOME = Path('/var/home/stewart/dyn4k-evidence/session-control/numerical-followup-7d/pulley-jdi-controller-followup')

    def test_pinned_baseline_class_inventory(self):
        pool, methods = class_inventory(self.BASELINE)
        self.assertEqual(len(methods), 28)
        self.assertGreater(len(pool), 100)

    def test_root_loaded_code_matches_both_sealed_providers(self):
        baseline = inspect_loaded_code(self.ROOT / 'baseline', self.BASELINE)
        candidate = inspect_loaded_code(self.ROOT / 'candidate-historical', self.CANDIDATE)
        self.assertEqual(baseline['methods'], 28)
        self.assertEqual(candidate['methods'], 29)
        self.assertEqual(baseline['pool_sha256'],
                         'abd20fdf00e2a540cd3813616d18e07d6e24d879b89f043d8b4d70d8b5259563')

    def test_altered_loaded_pool_is_rejected(self):
        with self.assertRaisesRegex(Rejected, 'constant pool'):
            inspect_loaded_code(self.ROOT / 'altered-baseline-provider', self.BASELINE)

    def test_changed_and_extra_method_bytes_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            for path in (self.ROOT / 'baseline').iterdir():
                if path.is_file():
                    shutil.copyfile(path, target / path.name)
            method = target / 'method-0.bin'
            method.write_bytes(method.read_bytes() + b'X')
            with self.assertRaisesRegex(Rejected, 'method bytes'):
                inspect_loaded_code(target, self.BASELINE)
            shutil.copyfile(self.ROOT / 'baseline/method-0.bin', method)
            (target / 'method-28.bin').write_bytes(b'X')
            with self.assertRaisesRegex(Rejected, 'extra loaded'):
                inspect_loaded_code(target, self.BASELINE)

    def test_missing_capture_fails_closed(self):
        with self.assertRaises(Exception):
            inspect_capture(Path('/no/such/capture'))

    def test_replay_rejects_forged_local_values_even_if_original_is_resealed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / 'original'
            replay = root / 'replay'
            original.mkdir()
            replay.mkdir()
            (original / 'capture-v2.json').write_text(json.dumps({
                'profile': 'baseline', 'artifact_sha256': 'a' * 64}))
            (original / 'case.jsonl').write_bytes(b'case\n')
            (replay / 'case.jsonl').write_bytes(b'case\n')
            (original / 'events.jsonl').write_text(json.dumps({'pid': 1, 'l1': 4.0}))
            (replay / 'events.jsonl').write_text(json.dumps({'pid': 2, 'l1': 1.0}))
            with patch('pulley_jdi_capture_v2.inspect_capture', return_value={
                'artifact_sha256': 'a' * 64, 'case_sha256': 'b' * 64}), \
                    patch('pulley_jdi_capture_v2.capture', return_value={
                        'artifact_sha256': 'a' * 64}):
                with self.assertRaisesRegex(Rejected, 'live operands differ'):
                    replay_capture(original, replay)
                (replay / 'events.jsonl').write_text(json.dumps({'pid': 2, 'l1': 4.0}))
                self.assertEqual(replay_capture(original, replay)['status'],
                                 'PROVED_REPLAYED_ONECASE_OPERATION')

    def test_indexed_reference_hash_is_checked_before_any_policy_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / 'indexed.jsonl'
            reference.write_bytes(b'original\n')
            with self.assertRaisesRegex(Rejected, 'indexed baseline case hash differs'):
                compare_indexed_onecase(reference, directory, directory, '0' * 64)

    def test_wrong_provider_hash_stops_before_creating_capture(self):
        with tempfile.TemporaryDirectory(dir=self.TASK_HOME) as directory:
            output = Path(directory) / 'capture'
            with self.assertRaisesRegex(Rejected, 'provider artifact hash differs'):
                capture('baseline', self.BASELINE,
                        self.TASK_HOME / 'toy-classpath.txt', output, '0' * 64)
            self.assertFalse(output.exists())

    def test_sidecar_selects_only_the_onecase_producer(self):
        build = (Path(__file__).resolve().parent /
                 'pulley-jdi-sidecar-v2/build.gradle.kts').read_text()
        self.assertIn('portable/PulleyPreparationJdiV1Test.kt', build)
        self.assertNotIn('PortableMatrixTest.kt', build)
        self.assertIn('if (profile == "baseline")', build)
        self.assertIn('writePulleyClasspath', build)


if __name__ == '__main__':
    unittest.main()
