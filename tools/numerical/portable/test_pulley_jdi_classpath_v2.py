import hashlib
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from pulley_jdi_inputs_v2 import inspect_classpath
from pulley_jdi_v1 import Rejected


class PulleyMultiReleaseClasspathTest(unittest.TestCase):
    PROVIDER_CLASSES = ('org/dyn4j/dynamics/joint/PulleyJoint.class',
                        'org/dyn4j/dynamics/Body.class',
                        'org/dyn4j/world/World.class',
                        'org/dyn4j/geometry/Geometry.class')
    FIXTURE_CLASSES = ('portable/PulleyPreparationJdiV1Test.class',
                       'portable/NumericalRecorder.class')
    RUNTIME_CLASSES = ('org/junit/runner/JUnitCore.class',
                       'kotlin/jvm/internal/Intrinsics.class')
    MR_MANIFEST = b'Manifest-Version: 1.0\r\nMulti-Release: true\r\n\r\n'

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.cache = self.root / 'cache'
        self.cache.mkdir()
        self.BASELINE = self.root / 'baseline-test-only.jar'
        self.jar(self.BASELINE, self.PROVIDER_CLASSES)

    def configured_paths(self, names, directories, reason):
        values = tuple(os.environ.get(name) for name in names)
        if not any(value is not None for value in values):
            self.skipTest(reason)
        self.assertTrue(all(values), f'{reason}; partial or empty input was supplied')
        paths = tuple(Path(value) for value in values)
        self.assertEqual(len(paths), len(directories))
        for path, is_directory in zip(paths, directories):
            self.assertTrue(path.is_dir() if is_directory else path.is_file(),
                            f'configured evidence path has the wrong type: {path}')
        return paths

    @staticmethod
    def jar(path, classes, manifest=b'Manifest-Version: 1.0\r\n\r\n'):
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('META-INF/MANIFEST.MF', manifest)
            for name in classes:
                archive.writestr(name, b'test-only class placeholder')

    def setup_synthetic(self, root, extra=(), manifest=None):
        cache = root / 'cache'
        cache.mkdir(exist_ok=True)
        fixture = root / 'fixture-test-only.jar'
        runtime = cache / 'runtime-test-only.jar'
        self.jar(fixture, self.FIXTURE_CLASSES)
        self.jar(runtime, self.RUNTIME_CLASSES + tuple(extra),
                 self.MR_MANIFEST if manifest is None else manifest)
        classpath = root / 'classpath.txt'
        classpath.write_text(':'.join(map(str, (fixture, self.BASELINE, runtime))) + '\n')
        return classpath, fixture, runtime, cache

    def test_real_eight_entry_classpath_is_admitted_with_bound_hashes(self):
        classpath, cache = self.configured_paths(
            ('DYN4K_PULLEY_REAL_CLASSPATH', 'DYN4K_PULLEY_CACHE_ROOT'),
            (False, True),
            'set real classpath and dependency cache inputs for historical archive verification')
        self.assertEqual(hashlib.sha256(classpath.read_bytes()).hexdigest(),
                         '791e12b6ab0366a3fb86119f2534c01cab2b4e0ed40bfa040d451966dc4f66db')
        paths = [Path(part) for part in classpath.read_text().strip().split(':')]
        entries = inspect_classpath(classpath, paths[1], paths[0], cache)
        self.assertEqual(len(entries), 8)
        self.assertEqual([entry['role'] for entry in entries[:2]], ['fixture', 'provider'])
        self.assertEqual([entry['sha256'] for entry in entries[:2]], [
            '9531eb292d9143a1bafe14416739e560cd86b71bfa338d4c158380dd2158cf34',
            '204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e'])
        self.assertEqual([entry['sha256'] for entry in entries[2:5]], [
            '8a5c498fa3cc04f451498cd4ff9d5d81cc6e9f08d6b5ab1cb39f6db09ea69d1e',
            'fa281d657898a34f6b0c7383f374f0a0161e61b6cea0095f135d917721d63f22',
            '2226de463d309d4a5500a481320b3dea515a6981dcae1def531fbc158884e25f'])

    def test_versioned_engine_and_fixture_shadows_are_rejected(self):
        for name in ('META-INF/versions/9/org/dyn4j/world/World.class',
                     'META-INF/versions/21/portable/NumericalRecorder.class'):
            with self.subTest(name=name), tempfile.TemporaryDirectory(dir=self.root) as directory:
                classpath, fixture, _, cache = self.setup_synthetic(Path(directory), (name,))
                with self.assertRaisesRegex(Rejected, 'duplicate classpath class'):
                    inspect_classpath(classpath, self.BASELINE, fixture, cache)

    def test_versioned_duplicate_between_dependencies_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            classpath, fixture, _, cache = self.setup_synthetic(
                Path(directory), ('META-INF/versions/11/extra/Duplicate.class',))
            duplicate = cache / 'duplicate.jar'
            self.jar(duplicate, ('extra/Duplicate.class',))
            classpath.write_text(classpath.read_text().strip() + ':' + str(duplicate) + '\n')
            with self.assertRaisesRegex(Rejected, 'duplicate classpath class'):
                inspect_classpath(classpath, self.BASELINE, fixture, cache)

    def test_base_and_versioned_class_in_same_jar_are_one_owner(self):
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            classpath, fixture, _, cache = self.setup_synthetic(
                Path(directory), ('extra/Owned.class',
                                  'META-INF/versions/9/extra/Owned.class',
                                  'META-INF/versions/21/extra/Owned.class'))
            first = inspect_classpath(classpath, self.BASELINE, fixture, cache)
            self.assertEqual(len(first), 3)
            runtime = cache / 'runtime-test-only.jar'
            with zipfile.ZipFile(runtime, 'w') as archive:
                archive.writestr('META-INF/MANIFEST.MF', self.MR_MANIFEST)
                for name in self.RUNTIME_CLASSES:
                    archive.writestr(name, b'test-only class placeholder')
                archive.writestr('extra/Owned.class', b'test-only class placeholder')
                archive.writestr('META-INF/versions/9/extra/Owned.class', b'changed')
                archive.writestr('META-INF/versions/21/extra/Owned.class', b'test-only class placeholder')
            second = inspect_classpath(classpath, self.BASELINE, fixture, cache)
            self.assertNotEqual(first[2]['sha256'], second[2]['sha256'])
            self.assertEqual(second[2]['sha256'], hashlib.sha256(runtime.read_bytes()).hexdigest())

    def test_folded_class_path_and_malformed_manifest_are_rejected(self):
        manifests = (
            b'Manifest-Version: 1.0\r\nClass-Path: extra.jar\r\n\r\n',
            b'Manifest-Version: 1.0\r\nClass-Path: extra.\r\n jar\r\n\r\n',
            b'Manifest-Version: 1.0\r\ncLaSs-PaTh: extra.\r\n jar\r\n\r\n',
            b'Manifest-Version: 1.0\r\n orphan\r\nMulti-Release: true\r\n\r\n',
            b'Manifest-Version: 1.0\r\nMulti-Release: true\r\nMulti-Release: false\r\n\r\n',
            b'Manifest-Version: 1.0\r\n\r\nName: entry\r\nClass-Path: extra.jar\r\n\r\n',
        )
        for manifest in manifests:
            with self.subTest(manifest=manifest), tempfile.TemporaryDirectory(dir=self.root) as directory:
                classpath, fixture, _, cache = self.setup_synthetic(Path(directory), manifest=manifest)
                with self.assertRaises(Rejected):
                    inspect_classpath(classpath, self.BASELINE, fixture, cache)

    def test_folded_multi_release_value_is_recognized(self):
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            classpath, fixture, _, cache = self.setup_synthetic(
                Path(directory), ('META-INF/versions/9/extra/Owned.class',),
                b'Manifest-Version: 1.0\r\nMulti-Release: tr\r\n ue\r\n\r\n')
            self.assertEqual(len(inspect_classpath(classpath, self.BASELINE, fixture, cache)), 3)

    def test_manifest_alias_and_invalid_version_directory_are_rejected(self):
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            classpath, fixture, runtime, cache = self.setup_synthetic(Path(directory))
            with zipfile.ZipFile(runtime, 'w') as archive:
                archive.writestr('META-INF/manifest.mf',
                                 b'Manifest-Version: 1.0\r\nClass-Path: extra.jar\r\n\r\n')
                for name in self.RUNTIME_CLASSES:
                    archive.writestr(name, b'\xca\xfe\xba\xbe')
            with self.assertRaisesRegex(Rejected, 'manifest path differs'):
                inspect_classpath(classpath, self.BASELINE, fixture, cache)
            self.jar(runtime, self.RUNTIME_CLASSES +
                     ('META-INF/versions/09/extra/Owned.class',), self.MR_MANIFEST)
            with self.assertRaisesRegex(Rejected, 'versioned class path is malformed'):
                inspect_classpath(classpath, self.BASELINE, fixture, cache)

    def test_above_jdk21_class_is_ignored_but_archive_is_inspected(self):
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            root = Path(directory)
            classpath, fixture, runtime, cache = self.setup_synthetic(
                root, ('META-INF/versions/22/org/dyn4j/world/World.class',))
            self.assertEqual(len(inspect_classpath(classpath, self.BASELINE, fixture, cache)), 3)
            self.jar(runtime, self.RUNTIME_CLASSES +
                     ('META-INF/versions/22/../../escape.class',), self.MR_MANIFEST)
            with self.assertRaisesRegex(Rejected, 'unsafe'):
                inspect_classpath(classpath, self.BASELINE, fixture, cache)

    def test_versioned_classes_require_multi_release_declaration(self):
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            classpath, fixture, _, cache = self.setup_synthetic(
                Path(directory), ('META-INF/versions/9/extra/Hidden.class',),
                b'Manifest-Version: 1.0\r\n\r\n')
            with self.assertRaises(Rejected):
                inspect_classpath(classpath, self.BASELINE, fixture, cache)


if __name__ == '__main__':
    unittest.main()
