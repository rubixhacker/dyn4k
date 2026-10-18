import unittest
import tempfile
import json
import hashlib
import io
import shutil
import subprocess
import zipfile
import xml.etree.ElementTree as ET
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import full_ci
from full_ci import normalized_cases, validate_audit, validate_corpus, validate_source_inputs, validate_xml
from test_world_ci import WorldCiTest


class FullCiEvidenceTest(unittest.TestCase):
    def test_production_source_replay_uses_pinned_commit_without_writing_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            java = source / 'src/main/java/org/dyn4j/Example.java'
            java.parent.mkdir(parents=True)
            java.write_bytes(b'package org.dyn4j; class Example {}\n')
            test = source / 'src/test/java/org/dyn4j/ExampleTest.java'
            test.parent.mkdir(parents=True)
            test.write_bytes(b'package org.dyn4j; @Test class ExampleTest {}\n')
            subprocess.run(['git', 'init', '-q', str(source)], check=True)
            subprocess.run(['git', '-C', str(source), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(source), '-c', 'user.name=Test',
                            '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'pin'], check=True)
            commit = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'],
                                             text=True).strip()
            jar = root / 'sources.jar'
            with zipfile.ZipFile(jar, 'w') as archive:
                archive.write(java, 'org/dyn4j/Example.java')
            index = (source / '.git/index').read_bytes()
            full_ci.validate_production_sources(source, jar, commit,
                                                hashlib.sha256(jar.read_bytes()).hexdigest(),
                                                expected_count=1)
            relative = 'src/test/java/org/dyn4j/ExampleTest.java'
            test_hashes = {relative: hashlib.sha256(test.read_bytes()).hexdigest()}
            full_ci.validate_test_source_commit(source, commit, test_hashes, expected_count=1)
            self.assertEqual((source / '.git/index').read_bytes(), index)
            test.write_bytes(test.read_bytes() + b'// stale\n')
            changed_hashes = {relative: hashlib.sha256(test.read_bytes()).hexdigest()}
            with self.assertRaisesRegex(ValueError, 'pinned test source'):
                full_ci.validate_test_source_commit(source, commit, changed_hashes,
                                                    expected_count=1)
            test.write_bytes(b'package org.dyn4j; @Test class ExampleTest {}\n')
            java.write_bytes(java.read_bytes() + b'// stale\n')
            with self.assertRaisesRegex(ValueError, 'production source'):
                full_ci.validate_production_sources(source, jar, commit,
                                                    hashlib.sha256(jar.read_bytes()).hexdigest(),
                                                    expected_count=1)
            self.assertEqual((source / '.git/index').read_bytes(), index)

    def test_corpus_argfile_and_process_command_reject_resealed_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'baseline-cache/dyn4j-source'
            relative = 'src/test/java/org/dyn4j/ExampleTest.java'
            java = source / relative
            java.parent.mkdir(parents=True)
            java.write_text('package org.dyn4j; @Test class ExampleTest {}\n')
            hashes = {relative: hashlib.sha256(java.read_bytes()).hexdigest()}
            original = Path('/original/archive')
            argfile = root / 'test-sources.args'
            argfile.write_text(f'"{original / "baseline-cache/dyn4j-source" / relative}"\n')
            classes = full_ci.validate_corpus_argfile(root, original, hashes,
                                                      expected_count=1, expected_classes=1)
            self.assertEqual(classes, ['org.dyn4j.ExampleTest'])
            argfile.write_text('"/tmp/stale/Unrelated.java"\n')
            with self.assertRaisesRegex(ValueError, 'test source argfile'):
                full_ci.validate_corpus_argfile(root, original, hashes,
                                                expected_count=1, expected_classes=1)

            command = ['/jdk8/bin/javac', '-cp', '/original/archive/baseline.jar',
                       '@' + str(original / 'test-sources.args')]
            raw = root / 'process.json'
            log = root / 'process.log'
            log.write_text('')
            raw.write_text(json.dumps({'command': command, 'cwd': '/source/root', 'exit': 0,
                                       'stdout': '', 'stderr': ''}) + '\n')
            row = {'process_sha256': hashlib.sha256(raw.read_bytes()).hexdigest()}
            full_ci.validate_corpus_process(raw, log, row, command, Path('/source/root'))
            changed = command.copy()
            changed[2] = '/tmp/stale.jar'
            raw.write_text(json.dumps({'command': changed, 'cwd': '/source/root', 'exit': 0,
                                       'stdout': '', 'stderr': ''}) + '\n')
            row['process_sha256'] = hashlib.sha256(raw.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, 'command'):
                full_ci.validate_corpus_process(raw, log, row, command, Path('/source/root'))

    def test_archive_file_inventory_survives_copy_and_rejects_changed_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / 'original'
            original.mkdir()
            (original / 'fixture').mkdir()
            (original / 'fixture/stream.ser').write_bytes(b'pinned stream')
            (original / 'result.json').write_text('{"status":"PASSED"}')
            recorded = full_ci.snapshot_archive(original)
            copied = Path(directory) / 'copied'
            shutil.copytree(original, copied)
            full_ci.verify_archive_files(copied, recorded)
            stream = copied / 'fixture/stream.ser'
            stream.write_bytes(b'changed stream')
            with self.assertRaisesRegex(ValueError, 'archive file hash'):
                full_ci.verify_archive_files(copied, recorded)
            stream.write_bytes(b'pinned stream')
            (copied / 'extra').write_bytes(b'extra')
            with self.assertRaisesRegex(ValueError, 'archive file set'):
                full_ci.verify_archive_files(copied, recorded)
            (copied / 'extra').unlink()
            stream.unlink()
            stream.symlink_to(original / 'fixture/stream.ser')
            with self.assertRaisesRegex(ValueError, 'symlink'):
                full_ci.verify_archive_files(copied, recorded)

    def test_archive_manifest_rejects_duplicate_and_traversal_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / 'result.json').write_text('{}')
            sha = hashlib.sha256(b'{}').hexdigest()
            for inventory in ({'../result.json': sha}, {'/tmp/result.json': sha},
                              {'folder\\..\\result.json': sha},
                              {'result.json': sha, './result.json': sha}):
                with self.subTest(inventory=inventory), self.assertRaisesRegex(
                        ValueError, 'archive path or hash is unsafe'):
                    full_ci.verify_archive_files(output, inventory)
            duplicate = '{"files":{"result.json":"a","result.json":"b"}}'
            with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
                full_ci.load_json_unique(duplicate)

    def test_exception_process_paths_map_only_declared_output_root(self):
        original = Path('/frozen/output')
        copied = Path('/downloaded/output')
        row = {'operation': 'write', 'runtime': 'jdk8', 'provider': 'jvm',
               'writer_runtime': 'jdk8', 'writer_provider': 'jvm',
               'case': 'ArgumentNullException',
               'command': ['/jdk8/bin/java', '-cp',
                           '/frozen/output/exception-serialization/fixture/classes/jvm:'
                           '/frozen/output/exception-serialization/fixture/jvm.jar:'
                           '/frozen/output/deps/kotlin-stdlib-2.4.20.jar',
                           'ExceptionSerializationProbe', 'write',
                           '/frozen/output/exception-serialization/fixture/'
                           'jdk8-jvm-ArgumentNullException.ser', 'ArgumentNullException']}
        mapped = full_ci.relocate_exception_runs([row], original, copied,
                                                 {'jdk8': Path('/jdk8')})
        self.assertEqual(mapped[0]['command'][-2],
                         '/downloaded/output/exception-serialization/fixture/'
                         'jdk8-jvm-ArgumentNullException.ser')
        self.assertEqual(row['command'][-2],
                         '/frozen/output/exception-serialization/fixture/'
                         'jdk8-jvm-ArgumentNullException.ser')
        changed = {**row, 'command': [*row['command'][:-2],
                                     '/elsewhere/jdk8-jvm-ArgumentNullException.ser',
                                     'ArgumentNullException']}
        with self.assertRaisesRegex(ValueError, 'exception process command'):
            full_ci.relocate_exception_runs([changed], original, copied,
                                            {'jdk8': Path('/jdk8')})
        swapped = {**row, 'command': [row['command'][0], '-cp',
                                      row['command'][2].replace('/classes/jvm:', '/classes/android:'),
                                      *row['command'][3:]]}
        with self.assertRaisesRegex(ValueError, 'exception process command'):
            full_ci.relocate_exception_runs([swapped], original, copied,
                                            {'jdk8': Path('/jdk8')})
        adverse = {**row, 'command': [part.replace(
            '/exception-serialization/fixture/', '/exception-serialization/uid-adverse/')
            for part in row['command']]}
        adverse_mapped = full_ci.relocate_exception_runs(
            [adverse], original, copied, {'jdk8': Path('/jdk8')}, 'uid-adverse')
        self.assertEqual(adverse_mapped[0]['command'][-2],
                         '/downloaded/output/exception-serialization/uid-adverse/'
                         'jdk8-jvm-ArgumentNullException.ser')

    def test_parameter_groups_keep_types_indices_and_complete_methods(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'corpus.xml'
            suite = ET.Element('testsuite', tests='2385', failures='0', errors='0', skipped='0')
            suites = {
                'org.dyn4j.collision.broadphase.CollisionBodyBroadphaseTest':
                    (25, ('Sap', 'Sap', 'DynamicAABBTree', 'DynamicAABBTree', 'BruteForceBroadphase')),
                'org.dyn4j.collision.broadphase.CollisionItemBroadphaseTest':
                    (29, ('CollisionItemBroadphaseDetectorAdapter',) * 5),
            }
            for owner, (count, types) in suites.items():
                for index, parameter_type in enumerate(types):
                    for method in range(count):
                        ET.SubElement(suite, 'testcase', classname=owner,
                                      name=f'method{method}[org.dyn4j.collision.broadphase.{parameter_type}@{index + 1:x}]')
            for index in range(2115):
                ET.SubElement(suite, 'testcase', classname='Other', name=f'case{index}')
            ET.ElementTree(suite).write(output)
            original = validate_xml(output)
            expected = normalized_cases(original)
            first = suite.findall('testcase')[0]
            first.set('name', first.get('name').replace('@1]', '@deadbeef]'))
            ET.ElementTree(suite).write(output)
            with self.assertRaisesRegex(ValueError, 'parameter group'):
                validate_xml(output)
            first.set('name', first.get('name').replace('@deadbeef]', '@1]'))
            for case in suite.findall('testcase')[:25]:
                case.set('name', case.get('name').replace('@1]', '@abcdef]'))
            ET.ElementTree(suite).write(output)
            self.assertEqual(expected, normalized_cases(validate_xml(output)))
            first.set('name', first.get('name').replace('.Sap@', '.Invented@'))
            ET.ElementTree(suite).write(output)
            with self.assertRaisesRegex(ValueError, 'parameter group'):
                validate_xml(output)

    def test_lane_seal_rejects_missing_changed_and_extra_files(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            corpus = {}
            for provider in ('baseline', 'candidate', 'android'):
                for compiler in (8, 21):
                    for runtime in (8, 21):
                        key = f'{provider}-javac{compiler}-java{runtime}'
                        xml = output / f'corpus-{key}.xml'
                        report = output / f'corpus-{key}.json'
                        xml.write_text(f'<testsuite name="{key}"/>')
                        report.write_text(json.dumps({'lane': key}))
                        corpus[key] = {'status': 'PASSED', 'cases': 2385,
                                       'xml': xml.name, 'report': report.name,
                                       'xml_sha256': hashlib.sha256(xml.read_bytes()).hexdigest(),
                                       'report_sha256': hashlib.sha256(report.read_bytes()).hexdigest()}
            evidence = {'status': 'PASSED', 'candidate_sha': 'a' * 40, 'corpus': corpus}
            self.assertEqual(len(full_ci.seal_lanes(output, evidence, 'a' * 40)), 24)
            victim = output / 'corpus-candidate-javac21-java21.xml'
            original = victim.read_bytes()
            victim.unlink()
            with self.assertRaises(ValueError):
                full_ci.seal_lanes(output, evidence, 'a' * 40)
            victim.write_bytes(original + b'changed')
            with self.assertRaises(ValueError):
                full_ci.seal_lanes(output, evidence, 'a' * 40)
            victim.write_bytes(original)
            extra = output / 'corpus-invented.json'
            extra.write_text('{}')
            with self.assertRaises(ValueError):
                full_ci.seal_lanes(output, evidence, 'a' * 40)
            extra.unlink()
            evidence['corpus']['candidate-javac21-java21'] = None
            (output / 'result.json').write_text(json.dumps(evidence))
            with patch('sys.argv', ['full_ci.py', 'seal', '--candidate-sha', 'a' * 40,
                                    '--output', str(output)]), redirect_stdout(io.StringIO()):
                self.assertEqual(full_ci.seal_main(), 1)
            manifest = json.loads((output / 'lane-manifest.json').read_text())
            self.assertEqual(manifest['status'], 'FAILED')
            self.assertEqual(len(manifest['files']), 24)

    def test_upload_seal_requires_world_fixture_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / 'result.json').write_text(json.dumps({
                'status': 'PASSED', 'candidate_sha': 'a' * 40,
                'archives': {'staged_jvm_jar': 'b' * 64,
                             'staged_android_classes_jar': 'c' * 64},
                'exception_serialization': {'report_sha256': 'd' * 64}}))
            with patch.object(full_ci, 'seal_lanes', return_value={}), \
                    patch.object(full_ci, 'seal_exception', return_value={}), \
                    patch('sys.argv', ['full_ci.py', 'seal', '--candidate-sha', 'a' * 40,
                                       '--output', str(output)]), redirect_stdout(io.StringIO()):
                self.assertEqual(full_ci.seal_main(), 1)
            manifest = json.loads((output / 'lane-manifest.json').read_text())
            self.assertEqual(manifest['status'], 'FAILED')
            self.assertEqual(manifest['world_files'], {})

    def test_exception_report_rejects_missing_identity_path_and_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            cases = ('ArgumentNullException', 'CopyException', 'EmptyCollectionException',
                     'SameObjectException', 'InvalidIndexException', 'ObjectAlreadyExistsException',
                     'ObjectAlreadyOwnedException', 'NullElementException-index',
                     'NullElementException-name', 'ValueOutOfRangeException-int',
                     'ValueOutOfRangeException-double', 'ValueOutOfRangeException-bound-int',
                     'ValueOutOfRangeException-bound-double', 'ValueOutOfRangeException-pair-int',
                     'ValueOutOfRangeException-pair-double')
            uids = {'ArgumentNullException': 7104871716542808869,
                    'CopyException': 2434249738746680073,
                    'EmptyCollectionException': 3188055341987092721,
                    'SameObjectException': -2844289260493601312,
                    'InvalidIndexException': 1297019115982655104,
                    'ValueOutOfRangeException': -7115378379246433066,
                    'ObjectAlreadyExistsException': 3414084132509765709,
                    'ObjectAlreadyOwnedException': -7471557485578931121,
                    'NullElementException': 4560521220204618552}
            providers = {name: {'sha256': value} for name, value in
                         (('baseline', 'a' * 64), ('jvm', 'b' * 64), ('android', 'c' * 64))}
            identities = [{'provider': provider, 'type': 'org.dyn4j.exception.' + name,
                           'expected': uid, 'matches': True, 'exit': 0,
                           'stdout': f'  private static final long serialVersionUID = {uid}l;\n'}
                          for provider in providers for name, uid in uids.items()]
            runs = []
            for runtime in ('jdk8', 'jdk21'):
                for provider in providers:
                    runs.append({'operation': 'ids', 'runtime': runtime, 'provider': provider,
                                 'case': None, 'matches': True, 'exit': 0,
                                 'stdout': ''.join(f'{name}={uid}\n' for name, uid in uids.items())})
            for writer_runtime in ('jdk8', 'jdk21'):
                for case in cases:
                    expected = (f'TYPE=org.dyn4j.exception.{case.split("-")[0]}\n'
                                'MESSAGE=sample\nCAUSE=java.lang.IllegalStateException:cause\n'
                                'SUPPRESSED=java.lang.IllegalArgumentException:suppressed\n'
                                'STACK=Example:run:Example.java:12\n')
                    for writer_provider in providers:
                        stream = output / f'{writer_runtime}-{writer_provider}-{case}.ser'
                        stream.write_bytes(b'stream')
                        runs.append({'operation': 'write', 'runtime': writer_runtime,
                                     'provider': writer_provider, 'writer_runtime': writer_runtime,
                                     'writer_provider': writer_provider, 'case': case,
                                     'command': ['java', 'write', str(stream), case],
                                     'stream_sha256': hashlib.sha256(stream.read_bytes()).hexdigest(),
                                     'matches': True, 'exit': 0, 'stdout': expected})
                        for reader_runtime in ('jdk8', 'jdk21'):
                            for reader_provider in providers:
                                runs.append({'operation': 'read', 'runtime': reader_runtime,
                                             'provider': reader_provider,
                                             'writer_runtime': writer_runtime,
                                             'writer_provider': writer_provider, 'case': case,
                                             'matches': True, 'exit': 0, 'stdout': expected})
            report = {'passed': True, 'failure_count': 0, 'providers': providers,
                      'baseline_sha256': 'a' * 64, 'probe_sha256': 'd' * 64,
                      'driver_sha256': 'e' * 64, 'stdlib_sha256': 'f' * 64,
                      'cases': list(cases), 'identities': identities, 'runs': runs,
                      'compiles': {name: {'exit': 0} for name in providers},
                      'versions': {name: {'exit': 0} for name in ('jdk8', 'jdk21')}}
            expected = {name: value['sha256'] for name, value in providers.items()}
            full_ci.validate_exception_report(report, output, expected, 'd' * 64, 'e' * 64, 'f' * 64)
            for change in ({'identities': identities[:-1]}, {'runs': runs[:-1]},
                           {'cases': cases[:-1]}, {'runs': [*runs[:-1], {**runs[-1], 'stdout': 'CAUSE=cauze'}]}):
                with self.subTest(change=tuple(change)), self.assertRaises(ValueError):
                    full_ci.validate_exception_report({**report, **change}, output, expected,
                                                      'd' * 64, 'e' * 64, 'f' * 64)
    def test_projection_rejects_duplicate_lane_and_changed_source(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            fixture = output / 'fixture'
            fixture.mkdir()
            for relative in ('extra/Names.java', 'org/dyn4j/geometry/simplify/NodeDispatchProbe.java'):
                path = fixture / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(relative)
            sources = output / 'sources'
            for index in range(1, 78):
                path = sources / f'org/dyn4j/ProjectionProbe{index:02d}.java'
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(str(index))
            suite = sources / 'projection/Suite.java'
            suite.parent.mkdir(parents=True, exist_ok=True)
            suite.write_text('suite')
            def hash_file(path):
                return hashlib.sha256(path.read_bytes()).hexdigest()
            source_hashes = {str(path.relative_to(sources)): hash_file(path)
                             for path in sources.rglob('*.java')}
            source_hashes.update({relative: hash_file(fixture / relative) for relative in
                                  ('extra/Names.java', 'org/dyn4j/geometry/simplify/NodeDispatchProbe.java')})
            observations = []
            for provider in ('baseline', 'jvm', 'android'):
                for compiler in ('jdk8', 'jdk21'):
                    for runtime in ('jdk8', 'jdk21'):
                        log = output / f'run-{provider}-{compiler}-{runtime}.log'
                        log.write_text('(1.0, 2.0)\nACTUAL_PROBES=77')
                        observations.append({'provider': provider, 'compiler': compiler,
                                             'runtime': runtime, 'probes': 77,
                                             'run_log_sha256': hash_file(log)})
            providers = {'baseline': 'a' * 64, 'jvm': 'b' * 64, 'android': 'c' * 64}
            report = {'audit_sha256': 'd' * 64, 'source_count': 80,
                      'source_sha256': source_hashes, 'providers': providers,
                      'observations': observations}
            full_ci.validate_projection(report, output, fixture, providers, 'd' * 64)
            changed = {**report, 'observations': [*observations[:-1], observations[0]]}
            with self.assertRaises(ValueError):
                full_ci.validate_projection(changed, output, fixture, providers, 'd' * 64)
            changed = {**report, 'observations': [{**observations[0], 'probes': 76},
                                                  *observations[1:]]}
            with self.assertRaises(ValueError):
                full_ci.validate_projection(changed, output, fixture, providers, 'd' * 64)
            changed = {**report, 'providers': {**providers, 'android': '0' * 64}}
            with self.assertRaises(ValueError):
                full_ci.validate_projection(changed, output, fixture, providers, 'd' * 64)
            changed = {**report, 'source_sha256': {**source_hashes, 'projection/Suite.java': '0' * 64}}
            with self.assertRaises(ValueError):
                full_ci.validate_projection(changed, output, fixture, providers, 'd' * 64)
            suite.write_text('changed')
            with self.assertRaises(ValueError):
                full_ci.validate_projection(report, output, fixture, providers, 'd' * 64)

    def test_unrelated_object_addresses_remain_distinct(self):
        observed = {("org.dyn4j.Test", "check[org.dyn4j.Tree@1a2b]"),
                    ("org.dyn4j.Test", "check[org.dyn4j.Tree@c3d4]")}
        expected = normalized_cases(observed)
        self.assertEqual(len(expected), 2)
        self.assertNotEqual(expected, normalized_cases({
            ("org.dyn4j.Test", "check[org.dyn4j.Tree@9a0b]"),
            ("org.dyn4j.Test", "check[org.dyn4j.Tree@8c7d]")}))
        self.assertNotEqual(expected, normalized_cases({("org.dyn4j.Test", "check[org.dyn4j.Tree@9a0b]")}))

    def test_changed_pinned_test_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            path = source / "src/test/java/Example.java"
            path.parent.mkdir(parents=True)
            path.write_text("class Example {}")
            import hashlib
            expected = {"src/test/java/Example.java": hashlib.sha256(path.read_bytes()).hexdigest()}
            validate_source_inputs(source, expected, expected_count=1)
            path.write_text("class Example { int changed; }")
            with self.assertRaises(ValueError):
                validate_source_inputs(source, expected, expected_count=1)

    def test_xml_requires_every_executed_case(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corpus.xml"
            path.write_text('<testsuite tests="2" failures="0" errors="0" skipped="0">'
                            '<testcase classname="A" name="first"/>'
                            '<testcase classname="A" name="second"/></testsuite>')
            validate_xml(path, 2)
            with self.assertRaises(ValueError):
                validate_xml(path, 3)
            path.write_text('<testsuite tests="2" failures="0" errors="0" skipped="1">'
                            '<testcase classname="A" name="first"/>'
                            '<testcase classname="A" name="second"><skipped/></testcase></testsuite>')
            with self.assertRaises(ValueError):
                validate_xml(path, 2)
            path.write_text('<testsuite tests="2" failures="0" errors="0" skipped="0">'
                            '<testcase classname="A" name="first"/>'
                            '<testcase classname="A" name="first"/></testsuite>')
            with self.assertRaises(ValueError):
                validate_xml(path, 2)

    def test_empty_or_skipped_corpus_is_rejected(self):
        report = {"actual_executed_cases": 2385, "failures": 0, "ignored": 0,
                  "process_exit_code": 0, "output": "ACTUAL_TESTS=2385\nFAILURES=0\nIGNORED=0\n"}
        validate_corpus(report)
        for change in ({"actual_executed_cases": 0, "output": "ACTUAL_TESTS=0\nFAILURES=0\nIGNORED=0\n"},
                       {"ignored": 1, "output": "ACTUAL_TESTS=2385\nFAILURES=0\nIGNORED=1\n"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_corpus({**report, **change})

    def test_incomplete_or_risky_archive_audit_is_rejected(self):
        report = {"compared_api_types": [f"org.dyn4j.Type{index}" for index in range(216)],
                  "compared_baseline_declarations": 3078,
                  "missing_types": [], "signature_mismatches": [],
                  "added_member_risks": [], "inventory_errors": [],
                  "fixture_failures": [], "fixture_errors": [],
                  "fixture_results": [{"source_sha256": value, "baseline_exit_code": 0,
                                       "candidate_exit_code": 0} for value in
                                      ("b668a59b6b50e6d5be1ca4828d2eaa179c6f9b3623a839be3e8c2c063d9ce6a4",
                                       "bb3f75b5f938b5e6da6e2444f5626606daa2223d29ba5c9ba2405660e50097ed",
                                       "b37d307b808a55961bad6d6cfd5606ec7d27b2ba33567e8d44621d0942530ff0")],
                  "baseline_sha256": "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e",
                  "candidate_sha256": "a" * 64}
        validate_audit(report, "a" * 64)
        for change in ({"compared_api_types": report["compared_api_types"][:-1]},
                       {"compared_baseline_declarations": 3077},
                       {"added_member_risks": [{"declaration": "public int getEntries();"}]},
                       {"fixture_results": []},
                       {"fixture_results": [{**report["fixture_results"][0], "candidate_exit_code": 1},
                                            *report["fixture_results"][1:]]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_audit({**report, **change}, "a" * 64)


if __name__ == "__main__":
    unittest.main()
