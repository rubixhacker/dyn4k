import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import world_ci


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class WorldCiTest(unittest.TestCase):
    def test_frozen_sources_and_mode_inventory(self):
        modes = world_ci.expected_modes()
        self.assertEqual(len(world_ci.SOURCE_SHA), 12)
        self.assertEqual(len(modes), 23)
        self.assertEqual(len(set(modes)), 23)
        world_ci.validate_sources(world_ci.SOURCE_ROOT, world_ci.SOURCE_SHA)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'WorldListSemanticsConsumer.java'
            path.write_text('class WorldListSemanticsConsumer {}')
            with self.assertRaisesRegex(ValueError, 'World source'):
                world_ci.validate_sources(Path(directory), {
                    'WorldListSemanticsConsumer.java':
                        world_ci.SOURCE_SHA['WorldListSemanticsConsumer.java']})

    def test_matrix_rejects_replaced_or_missing_world_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / 'runs').mkdir()
            rows = []
            for provider in world_ci.PROVIDERS:
                for runtime in world_ci.RUNTIMES:
                    for index, (main, mode) in enumerate(world_ci.expected_modes()):
                        path = output / world_ci.runlog_name(provider, runtime, index)
                        content = {'exit': 0, 'stdout': f'{runtime}:{main}:{mode}\n',
                                   'stderr': '', 'command': ['/jdk/bin/java', '-cp',
                                                           'classpath', main] +
                                   ([mode] if mode is not None else [])}
                        path.write_text(json.dumps(content) + '\n')
                        rows.append({'provider': provider, 'runtime': runtime,
                                     'main': main, 'mode': mode, 'exit': 0,
                                     'log': world_ci.runlog_name(provider, runtime, index),
                                     'log_sha256': digest(path)})
            world_ci.validate_runs(rows, output)
            with self.assertRaisesRegex(ValueError, 'World execution'):
                world_ci.validate_runs(rows[:-1], output)
            with self.assertRaisesRegex(ValueError, 'World execution'):
                world_ci.validate_runs([*rows[:-1], rows[0]], output)
            candidate = next(row for row in rows if row['provider'] == 'jvm'
                             and row['runtime'] == 'jdk8')
            path = output / candidate['log']
            content = json.loads(path.read_text())
            content['stdout'] = 'wrong World list result\n'
            path.write_text(json.dumps(content) + '\n')
            candidate['log_sha256'] = digest(path)
            with self.assertRaisesRegex(ValueError, 'World stdout'):
                world_ci.validate_runs(rows, output)

    def test_upload_file_set_and_hashes_are_sealed(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / 'sources').mkdir()
            source = output / 'sources' / 'WorldListSemanticsConsumer.java'
            source.write_text('source')
            log = output / 'run.json'
            log.write_text('log')
            recorded = {'sources/WorldListSemanticsConsumer.java': digest(source),
                        'run.json': digest(log)}
            self.assertEqual(world_ci.seal_files(output, recorded), recorded)
            source.unlink()
            with self.assertRaisesRegex(ValueError, 'World raw file set'):
                world_ci.seal_files(output, recorded)
            source.write_text('changed')
            with self.assertRaisesRegex(ValueError, 'World raw file hash'):
                world_ci.seal_files(output, recorded)
            source.write_text('source')
            (output / 'extra.txt').write_text('extra')
            with self.assertRaisesRegex(ValueError, 'World raw file set'):
                world_ci.seal_files(output, recorded)

    def test_bad_body_view_must_fail_on_specific_world_semantics(self):
        baseline = 'bodies,empty=VALUE:232:abc\n'
        mutant = ('bodies,empty=NotSerializableException:'
                  'org.dyn4j.world.AbstractCollisionWorldKt$worldReadOnlyView$1\n')
        world_ci.validate_adverse_output(baseline, mutant)
        with self.assertRaisesRegex(ValueError, 'World body-view adverse'):
            world_ci.validate_adverse_output(baseline, baseline)
        with self.assertRaisesRegex(ValueError, 'World body-view adverse'):
            world_ci.validate_adverse_output(baseline, 'other mismatch\n')


if __name__ == '__main__':
    unittest.main()
