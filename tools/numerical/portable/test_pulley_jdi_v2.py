import unittest
import shutil
import tempfile
import json
import zipfile
import hashlib
import os
import sys
from pathlib import Path
from unittest.mock import patch

from pulley_jdi_v1 import Rejected
from pulley_jdi_v2 import (class_inventory, compare_indexed_onecase,
                           inspect_capture, inspect_loaded_code)
from pulley_jdi_capture_v2 import _build_sidecar, _copy_bounded, _run_bounded, capture, replay_capture
from pulley_jdi_inputs_v2 import (inspect_classpath, verify_candidate_publication,
                                  MAX_LOG_BYTES)


class PulleyJdiV2Test(unittest.TestCase):
    ROOT = Path('/var/home/stewart/dyn4k-evidence/root-jdi-loaded-code')
    BASELINE = Path('/tmp/dyn4k-baseline-cache/dyn4j-6.0.0.jar')
    CANDIDATE = Path('/var/home/stewart/dyn4k-evidence/session-control/numerical-followup-7d/wheel/capture-7d/artifact.jar')
    TASK_HOME = Path('/var/home/stewart/dyn4k-evidence/session-control/numerical-followup-7d/pulley-jdi-controller-followup')
    REVIEW_HOME = Path('/var/home/stewart/dyn4k-evidence/session-control/numerical-followup-7d/pulley-jdi-reviewfix-f9')

    def test_capture_fixture_is_absent_from_normal_jvm_source_root(self):
        root = Path(__file__).resolve().parent
        self.assertFalse((root / 'src/jvmTest/kotlin/portable/PulleyPreparationJdiV1Test.kt').exists())
        self.assertTrue((root / 'pulley-jdi-sidecar-v2/src/test/kotlin/portable/PulleyPreparationJdiV1Test.kt').is_file())

    def test_shadow_provider_is_rejected_before_output_creation(self):
        with tempfile.TemporaryDirectory(dir=self.REVIEW_HOME) as directory:
            root = Path(directory)
            shadow = root / 'shadow.jar'
            shadow.write_bytes(b'other provider')
            classpath = root / 'classpath.txt'
            classpath.write_text(str(shadow) + ':' + str(self.BASELINE) + '\n')
            with patch('pathlib.Path.mkdir', side_effect=AssertionError('capture started')):
                with self.assertRaises(Rejected):
                    capture('baseline', self.BASELINE, classpath,
                            root / 'capture', '204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e')

    @staticmethod
    def jar(path, names):
        with zipfile.ZipFile(path, 'w') as archive:
            for name in names:
                archive.writestr(name, b'\xca\xfe\xba\xbe')

    def test_complete_classpath_rejects_shadow_and_changed_fixture(self):
        with tempfile.TemporaryDirectory(dir=self.REVIEW_HOME) as directory:
            root = Path(directory)
            cache = root / 'cache'
            cache.mkdir()
            fixture = root / 'fixture.jar'
            runtime = cache / 'runtime.jar'
            shadow = cache / 'shadow.jar'
            self.jar(fixture, ['portable/PulleyPreparationJdiV1Test.class',
                               'portable/NumericalRecorder.class'])
            self.jar(runtime, ['org/junit/runner/JUnitCore.class',
                               'kotlin/jvm/internal/Intrinsics.class'])
            self.jar(shadow, ['org/dyn4j/world/World.class'])
            classpath = root / 'classpath.txt'
            classpath.write_text(':'.join(map(str, [fixture, self.BASELINE, runtime])) + '\n')
            entries = inspect_classpath(classpath, self.BASELINE, fixture, cache)
            self.assertEqual([entry['role'] for entry in entries],
                             ['fixture', 'provider', 'dependency'])
            classpath.write_text(':'.join(map(str, [fixture, self.BASELINE, runtime, shadow])) + '\n')
            with self.assertRaisesRegex(Rejected, 'duplicate classpath class'):
                inspect_classpath(classpath, self.BASELINE, fixture, cache)
            classpath.write_text(':'.join(map(str, [fixture, self.BASELINE, runtime])) + '\n')
            self.jar(fixture, ['portable/PulleyPreparationJdiV1Test.class'])
            with self.assertRaisesRegex(Rejected, 'fixture or recorder origin'):
                inspect_classpath(classpath, self.BASELINE, fixture, cache)

    def test_runtime_log_bound_is_explicit_and_controller_does_not_buffer_all_output(self):
        controller = (Path(__file__).resolve().parent / 'PulleyJdiControllerV2.java').read_text()
        self.assertEqual(MAX_LOG_BYTES, 2 * 1024 * 1024)
        self.assertIn('MAX_LOG_BYTES = 2L * 1024 * 1024', controller)
        self.assertIn('child.destroyForcibly()', controller)
        self.assertNotIn('readAllBytes()', controller)

    def test_copied_input_and_child_log_stop_at_bounds(self):
        with tempfile.TemporaryDirectory(dir=self.REVIEW_HOME) as directory:
            root = Path(directory)
            source = root / 'source'
            source.write_bytes(b'12345')
            with self.assertRaisesRegex(Rejected, 'bound'):
                _copy_bounded(source, root / 'copy', 4)
            self.assertFalse((root / 'copy').exists())
            environment = {key: value for key, value in os.environ.items()
                           if key != 'OLLAMA_API_KEY'}
            _, code = _run_bounded([sys.executable, '-c',
                    'import sys; sys.stdout.buffer.write(b"x" * (2 * 1024 * 1024 + 1))'],
                    environment, root / 'child.stdout', root / 'child.stderr', 5)
            self.assertNotEqual(code, 0)
            self.assertLessEqual((root / 'child.stdout').stat().st_size, MAX_LOG_BYTES)

    def test_oversized_provider_is_rejected_before_hash_or_copy(self):
        with tempfile.TemporaryDirectory(dir=self.REVIEW_HOME) as directory:
            root = Path(directory)
            provider = root / 'oversized.jar'
            with provider.open('wb') as stream:
                stream.truncate(32 * 1024 * 1024 + 1)
            classpath = root / 'classpath.txt'
            classpath.write_text(str(provider) + '\n')
            with patch('pulley_jdi_capture_v2._digest', side_effect=AssertionError('hashed oversized input')):
                with self.assertRaises(Rejected):
                    capture('candidate', provider, classpath, root / 'capture', '0' * 64)

    def test_candidate_needs_publication_record_before_output(self):
        with self.assertRaises(Rejected):
            verify_candidate_publication(self.CANDIDATE, None)

    def test_candidate_publication_binds_current_tree_log_and_all_staged_bytes(self):
        with tempfile.TemporaryDirectory(dir=self.REVIEW_HOME) as directory:
            root = Path(directory)
            staged = root / 'staged'
            staged.mkdir()
            source = root / 'publication.json'
            log = root / 'publication.log'
            log.write_text('bounded Gradle stage record\n')
            jar = staged / 'jvm.jar'
            metadata = staged / 'metadata.jar'
            shutil.copyfile(self.CANDIDATE, jar)
            metadata.write_bytes(b'metadata')
            sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
            identity = ('a' * 40, 'b' * 64)
            manifest = {'candidate_commit': identity[0], 'source_sha256': identity[1],
                        'artifact_sha256': {'jvm.jar': sha(jar),
                                            'metadata.jar': sha(metadata)},
                        'publication_log_sha256': sha(log)}
            source.write_text(json.dumps(manifest))
            with patch('pulley_jdi_inputs_v2.portable_runner.clean_identity',
                       return_value=identity), \
                    patch('pulley_jdi_inputs_v2.portable_runner.STAGED', staged), \
                    patch('pulley_jdi_inputs_v2.portable_runner._publication_names',
                          return_value={'jvm.jar', 'metadata.jar'}), \
                    patch('pulley_jdi_inputs_v2.portable_runner.artifact_relative_paths',
                          return_value={'target': 'jvm.jar'}):
                self.assertEqual(verify_candidate_publication(jar, source)['commit'],
                                 identity[0])
                metadata.write_bytes(b'changed')
                with self.assertRaisesRegex(Rejected, 'staged publication artifact'):
                    verify_candidate_publication(jar, source)
                metadata.write_bytes(b'metadata')
                manifest['source_sha256'] = 'c' * 64
                source.write_text(json.dumps(manifest))
                with self.assertRaisesRegex(Rejected, 'publication source'):
                    verify_candidate_publication(jar, source)

    def test_fresh_sidecar_source_build_must_match_declared_fixture(self):
        expected = [{'role': 'fixture', 'sha256': 'a' * 64, 'path': '/fixture.jar'},
                    {'role': 'provider', 'sha256': 'b' * 64, 'path': '/provider.jar'}]
        with tempfile.TemporaryDirectory(dir=self.REVIEW_HOME) as directory:
            with patch('pulley_jdi_capture_v2._run_bounded', return_value=(123, 0)) as run, \
                    patch('pulley_jdi_capture_v2.portable_runner.clean_identity',
                          return_value=('c' * 40, 'd' * 64)), \
                    patch('pulley_jdi_capture_v2.inspect_classpath',
                          return_value=expected):
                self.assertEqual(_build_sidecar('baseline', self.BASELINE,
                                 Path(directory), {}, expected),
                                 ('c' * 40, 'd' * 64, expected))
                self.assertIn('--offline', run.call_args.args[0])
                self.assertIn('--rerun-tasks', run.call_args.args[0])
            changed = [{**expected[0], 'sha256': 'e' * 64}, expected[1]]
            with patch('pulley_jdi_capture_v2._run_bounded', return_value=(123, 0)), \
                    patch('pulley_jdi_capture_v2.portable_runner.clean_identity',
                          return_value=('c' * 40, 'd' * 64)), \
                    patch('pulley_jdi_capture_v2.inspect_classpath',
                          return_value=changed):
                with self.assertRaisesRegex(Rejected, 'fresh source build'):
                    _build_sidecar('baseline', self.BASELINE, Path(directory), {}, expected)

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

    def test_non_pulley_loaded_world_bytes_are_compared_with_provider(self):
        entry = 'org/dyn4j/world/World.class'
        pool, methods = class_inventory(self.BASELINE, entry)
        with tempfile.TemporaryDirectory(dir=self.REVIEW_HOME) as directory:
            target = Path(directory)
            (target / 'constant-pool.bin').write_bytes(pool)
            rows = []
            for index, ((name, signature), body) in enumerate(methods.items()):
                file = f'method-{index}.bin'
                (target / file).write_bytes(body)
                rows.append(f'{name}\t{signature}\t{file}\n')
            (target / 'methods.tsv').write_text(''.join(rows))
            self.assertEqual(inspect_loaded_code(target, self.BASELINE, entry)['methods'],
                             len(methods))
            (target / 'method-0.bin').write_bytes(b'changed')
            with self.assertRaisesRegex(Rejected, 'method bytes'):
                inspect_loaded_code(target, self.BASELINE, entry)
            (target / 'method-0.bin').write_bytes(next(iter(methods.values())))
            (target / 'forged.bin').write_bytes(b'x')
            with self.assertRaisesRegex(Rejected, 'extra loaded class evidence'):
                inspect_loaded_code(target, self.BASELINE, entry, strict=True)

    def test_missing_capture_fails_closed(self):
        with self.assertRaises(Exception):
            inspect_capture(Path('/no/such/capture'))

    def test_replay_rejects_forged_local_values_even_if_original_is_resealed(self):
        with tempfile.TemporaryDirectory(dir=self.REVIEW_HOME) as directory:
            root = Path(directory)
            original = root / 'original'
            original.mkdir()
            (original / 'capture-v2.json').write_text(json.dumps({
                'profile': 'baseline', 'artifact_sha256': 'a' * 64}))
            (original / 'classpath-entries.json').write_text(json.dumps({
                'schema': 'pulley-jdi-classpath/2', 'entries': [
                    {'role': 'fixture', 'path': str(root / 'fixture.jar')},
                    {'role': 'provider', 'path': str(self.BASELINE)},
                    {'role': 'dependency', 'path': str(root / 'dependency.jar')},
                ]}))
            (original / 'case.jsonl').write_bytes(b'case\n')
            (original / 'events.jsonl').write_text(json.dumps({'pid': 1, 'l1': 4.0}))
            def fake_capture(_profile, _provider, _classpath, target, _sha, _record):
                target.mkdir()
                (target / 'case.jsonl').write_bytes(b'case\n')
                (target / 'events.jsonl').write_text(json.dumps({
                    'pid': 2, 'l1': 1.0 if target.name == 'replay-red' else 4.0}))
                return {'artifact_sha256': 'a' * 64}
            with patch('pulley_jdi_capture_v2.inspect_capture', return_value={
                'artifact_sha256': 'a' * 64, 'case_sha256': 'b' * 64}), \
                    patch('pulley_jdi_capture_v2.capture', side_effect=fake_capture):
                with self.assertRaisesRegex(Rejected, 'live operands differ'):
                    replay_capture(original, root / 'replay-red')
                self.assertEqual(replay_capture(original, root / 'replay-green')['status'],
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
