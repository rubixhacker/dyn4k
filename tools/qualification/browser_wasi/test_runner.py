import os
import json
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from runner import (gradle_test_task, runtime_version, source_cases, staged_files,
                    verify_reports, verify_wasmtime_output, isolated_karma_port)


class BrowserReporterStageTest(unittest.TestCase):
    def test_finite_decimal_range_preserves_binary_edges(self):
        from runner import verify_collision_value

        accepted = (
            "0@0", "0@-9223372036854775808",
            "0.0@0", "-0@-9223372036854775808",
            "-0.0@-9223372036854775808",
            "4.9E-324@1", "-4.9E-324@-9223372036854775807",
            "Infinity@9218868437227405312", "-Infinity@-4503599627370496",
            "NaN@9221120237041090561", "NaN@-2251799813685247",
        )
        for value in accepted:
            with self.subTest(accepted=value):
                verify_collision_value("penetration.depth", value)
        rejected = (
            ("1e-999@0", "underflows"),
            ("-1e-999@-9223372036854775808", "underflows"),
            ("1e999@9218868437227405312", "overflows"),
            ("-1e999@-4503599627370496", "overflows"),
            ("0e999@0", "zero spelling"),
            ("-0e999@-9223372036854775808", "zero spelling"),
            ("0.000@0", "zero spelling"),
            ("-0.000@-9223372036854775808", "zero spelling"),
            ("1@0", "raw bits"), ("-0@0", "raw bits"),
            ("-0.0@0", "raw bits"),
            ("0.0@-9223372036854775808", "raw bits"),
            ("inf@9218868437227405312", "numeric syntax"),
            ("NaN@9218868437227405312", "NaN bits"),
        )
        for value, error in rejected:
            with self.subTest(rejected=value):
                with self.assertRaisesRegex(ValueError, error):
                    verify_collision_value("penetration.depth", value)

    def test_real_wasm_negative_zero_requires_negative_raw_bits(self):
        from runner import verify_collision_diagnostics
        import xml.etree.ElementTree as ET

        receipt = os.environ.get("DYN4K_BROWSER_WASI_SIGNED_ZERO_WASM_RECEIPT")
        if receipt is None:
            self.skipTest("set retained Wasm JS receipt for signed-zero control")
        lane = json.loads(Path(receipt).read_text())
        report = next(Path(item["path"]) for item in lane["modules"]["dyn4k-core"]["raw_xml"]
                      if "WindowsCollisionIntermediateDiagnosticTest" in item["path"])
        suite = ET.parse(report).getroot()
        self.assertEqual(72, verify_collision_diagnostics(suite)["diagnostic_rows"])
        output = suite.find("system-out")
        rows = output.text.splitlines()
        fields = rows[0].split("\t")
        transform = next(i for i, field in enumerate(fields)
                         if field.startswith("a.transform="))
        original = "-0.0@-9223372036854775808"
        self.assertIn(original, fields[transform])
        fields[transform] = fields[transform].replace(original, "-0.0@0", 1)
        rows[0] = "\t".join(fields)
        output.text = "\n".join(rows) + "\n"
        with self.assertRaisesRegex(ValueError, "raw bits"):
            verify_collision_diagnostics(suite)

    def test_only_exact_generated_consumer_lock_is_accepted(self):
        import runner

        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory)
            lock = candidate / "consumers/qualification/browser-wasi/kotlin-js-store/yarn.lock"
            lock.parent.mkdir(parents=True)
            lock.write_bytes(b"pinned generated lock")
            problem = ("untracked candidate input: "
                       "consumers/qualification/browser-wasi/kotlin-js-store/yarn.lock")
            digest = hashlib.sha256(lock.read_bytes()).hexdigest()
            with mock.patch.object(runner, "CONSUMER_YARN_LOCK_SHA256", digest):
                self.assertTrue(runner.is_pinned_consumer_lock(candidate, problem))
                self.assertFalse(runner.is_pinned_consumer_lock(candidate, problem + ".other"))
                lock.write_bytes(lock.read_bytes() + b"tampered")
                self.assertFalse(runner.is_pinned_consumer_lock(candidate, problem))
                lock.unlink()
                self.assertFalse(runner.is_pinned_consumer_lock(candidate, problem))

    def test_scoped_browser_xml_rejects_lost_duplicated_and_truncated_diagnostics(self):
        source = os.environ.get("DYN4K_BROWSER_WASI_SCOPED_XML")
        if source is None:
            self.skipTest("set DYN4K_BROWSER_WASI_SCOPED_XML to a passing diagnostic XML")
        source_path = Path(source)
        self.assertTrue(source_path.is_file(), source_path)
        import xml.etree.ElementTree as ET

        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / source_path.name
            shutil.copy2(source_path, report)
            suite = ET.parse(report).getroot()
            cases = {
                ("org.dyn4j.collision.narrowphase.WindowsCollisionIntermediateDiagnosticTest",
                 case.attrib["name"].split("[", 1)[0])
                for case in suite.findall("testcase")
            }
            task = suite.attrib["name"].split(".", 1)[0]
            marker = "ChromeHeadless119"
            verify_reports(report.parent, cases, task, marker,
                           require_collision_diagnostics=True)
            original = suite.find("system-out").text
            rows = original.splitlines()
            self.assertEqual(72, len(rows))
            partial = rows[0].split("\t")
            transform = next(i for i, field in enumerate(partial)
                             if field.startswith("a.transform="))
            partial[transform] = "a.transform=1@4"

            def wrong_bits(row: str, key: str) -> str:
                fields = row.split("\t")
                index = next(i for i, field in enumerate(fields)
                             if field.startswith(key + "="))
                fields[index] = re.sub(r"@-?\d+", "@4", fields[index], count=1)
                return "\t".join(fields)

            sat_row = next(i for i, row in enumerate(rows) if "\talgorithm=sat\t" in row)
            for mutation in (rows[:1] + rows[2:], rows + rows[:1],
                             [rows[0].rsplit("\t", 1)[0], *rows[1:]],
                             ["\t".join(partial), *rows[1:]],
                             [wrong_bits(rows[0], "a.transform"), *rows[1:]],
                             [wrong_bits(rows[0], "a.shape.local"), *rows[1:]],
                             [wrong_bits(rows[0], "epa.iteration.records"), *rows[1:]],
                             [*rows[:sat_row], wrong_bits(rows[sat_row], "sat.candidates"),
                              *rows[sat_row + 1:]]):
                suite.find("system-out").text = "\n".join(mutation) + "\n"
                ET.ElementTree(suite).write(report, encoding="unicode")
                with self.assertRaisesRegex(ValueError, "diagnostic"):
                    verify_reports(report.parent, cases, task, marker,
                                   require_collision_diagnostics=True)

    def test_wasmtime_retained_executable_replays_after_source_changes(self):
        from runner import capture_linked_executable, verify_linked_source_digest, sha256

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "shared.wasm"
            retained = Path(directory) / "lane" / "linked-executable.wasm"
            retained.parent.mkdir()
            source.write_bytes(b"producer A")
            digest = capture_linked_executable(source, retained)
            self.assertEqual(sha256(source), digest)
            self.assertEqual(sha256(retained), digest)

            source.write_bytes(b"later producer B")
            verify_linked_source_digest(source, retained, digest, digest, "wasmWasi")
            retained.write_bytes(b"wrong producer B")
            with self.assertRaisesRegex(ValueError, "linked .*digest"):
                verify_linked_source_digest(source, retained, digest, digest, "wasmWasi")

    def test_capture_rejects_source_change_during_retention(self):
        from runner import capture_linked_executable

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "shared.wasm"
            retained = Path(directory) / "linked-executable.wasm"
            source.write_bytes(b"producer A")
            original_copy = shutil.copy2

            def changed_copy(from_path, to_path):
                original_copy(from_path, to_path)
                source.write_bytes(b"producer B")

            with mock.patch("runner.shutil.copy2", side_effect=changed_copy):
                with self.assertRaisesRegex(ValueError, "linked .*digest"):
                    capture_linked_executable(source, retained)

    def test_firefox_launcher_graph_is_committed_for_root_js_builds(self):
        from runner import verify_firefox_launcher_graph

        root = Path(__file__).resolve().parents[3]
        verify_firefox_launcher_graph(root)
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory)
            for relative in ("dyn4k-core/build.gradle.kts", "dyn4k/build.gradle.kts",
                             "kotlin-js-store/yarn.lock"):
                path = copied / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((root / relative).read_bytes())
            lock = copied / "kotlin-js-store/yarn.lock"
            lock.write_text(lock.read_text().replace("karma-firefox-launcher@^2.1.3:",
                                                    "karma-firefox-launcher@^0.0.0:"))
            with self.assertRaisesRegex(ValueError, "Firefox launcher"):
                verify_firefox_launcher_graph(copied)

    def test_browser_port_stages_line_reporter_and_cleans_both_fragments(self):
        reporter = Path(__file__).with_name("browser-karma-reporter.js")
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            with isolated_karma_port(project, reporter) as port:
                config = project / "karma.config.d"
                self.assertEqual(reporter.read_bytes(),
                                 (config / "qualification-browser-reporter.js").read_bytes())
                self.assertEqual(f"config.set({{port: {port}}});\n",
                                 (config / "qualification-port.js").read_text())
            self.assertFalse(config.exists())

    def test_browser_port_rejects_missing_reporter_without_staging_port(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            with self.assertRaises(FileNotFoundError):
                with isolated_karma_port(project, project / "missing-reporter.js"):
                    pass
            self.assertFalse((project / "karma.config.d").exists())

    def test_browser_reporter_writes_all_messages_before_process_exit(self):
        reporter = Path(__file__).with_name("browser-karma-reporter.js")
        script = "\n".join((
            "const assert = require('node:assert/strict');",
            "const fs = require('node:fs');",
            "const vm = require('node:vm');",
            "const bytes = [];",
            "let calls = 0;",
            "const fakeFs = {writeSync(fd, data, offset, length) {",
            "  assert.equal(fd, 1);",
            "  if (calls++ === 0) { const error = new Error('busy'); error.code = 'EAGAIN'; throw error; }",
            "  const count = Math.min(length, 4096);",
            "  bytes.push(Buffer.from(data.subarray(offset, offset + count)));",
            "  return count;",
            "},",
            "realpathSync: path => path,",
            "readFileSync: () => Buffer.from('reporter fixture'),",
            "writeFileSync: (path, value) => { attestation = JSON.parse(value); },",
            "};",
            "let attestation;",
            "function OriginalReporter(decorate) {",
            "  decorate(this);",
            "  this.emit = message => this.write(message);",
            "}",
            "OriginalReporter.$inject = ['baseReporterDecorator'];",
            "const plugin = {'reporter:karma-kotlin-reporter': ['type', OriginalReporter]};",
            "const config = {plugins: [plugin]};",
            "const fakeRequire = name => name === 'node:fs' ? fakeFs :",
            "  name === 'node:crypto' ? {createHash: () => ({update() {return this;},",
            "  digest: () => '7c3232f60952aff254847ae62a866385735e3094197454d755100e962c2f2347'})} : require(name);",
            "fakeRequire.cache = {'/fixture/reporter.js':",
            "  {filename: '/fixture/reporter.js', exports: plugin}};",
            "vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'),",
            "  {config, Buffer, process: {stdout: {fd: 1},",
            "   env: {DYN4K_BROWSER_REPORTER_ATTESTATION: '/fixture/attestation'}},",
            "   require: fakeRequire});",
            "assert.deepEqual(attestation, {path: '/fixture/reporter.js',",
            "  sha256: '7c3232f60952aff254847ae62a866385735e3094197454d755100e962c2f2347'});",
            "const Reporter = plugin['reporter:karma-kotlin-reporter'][1];",
            "assert.deepEqual(Reporter.$inject, OriginalReporter.$inject);",
            "const instance = new Reporter(reporter => {",
            "  reporter.write = () => { throw new Error('asynchronous adapter used'); };",
            "});",
            "const messages = Array.from({length: 72}, (_, i) =>",
            "  `##teamcity[testStdOut out='v2-${i}-${'x'.repeat(15000)}']`);",
            "messages.forEach(message => instance.emit(message));",
            "const output = Buffer.concat(bytes).toString('utf8');",
            "assert.equal(output, messages.map(message => message + '\\n').join(''));",
            "assert.ok(Buffer.byteLength(output, 'utf8') > 1048576);",
            "assert.ok(output.split('\\n').slice(0, -1).every(line =>",
            "  Buffer.byteLength(line, 'utf8') < 262144));",
            "assert.throws(() => instance.emit('x'.repeat(262145)), /exceeds/);",
            "assert.equal(Buffer.concat(bytes).toString('utf8'), output);",
            "fakeFs.writeSync = () => 0;",
            "assert.throws(() => instance.emit(\"##teamcity[testFinished name='x']\"),",
            "  /write made no progress/);",
        ))
        result = subprocess.run(["node", "-e", script, str(reporter)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_browser_reporter_attests_loaded_file_and_rejects_changed_or_absent_bytes(self):
        root = Path(__file__).resolve().parents[3]
        js_producer = (root / "build/js/node_modules/kotlin-web-helpers/dist"
                       / "karma-kotlin-reporter.js")
        wasm_config = (root / "build/wasm/packages/dyn4k-dyn4k-core-test/karma.conf.js")
        if not js_producer.is_file() or not wasm_config.is_file():
            self.skipTest("cached JS and Wasm JS Kotlin browser reporters are unavailable")
        runner = re.search(r'"([^"]*/kotlin-web-helpers/dist/kotlin-test-karma-runner.js)"',
                           wasm_config.read_text())
        self.assertIsNotNone(runner)
        wasm_producer = Path(runner.group(1)).with_name("karma-kotlin-reporter.js")
        self.assertTrue(wasm_producer.is_file(), wasm_producer)
        script = "\n".join((
            "const assert = require('node:assert/strict');",
            "const fs = require('node:fs');",
            "const crypto = require('node:crypto');",
            "const path = require('node:path');",
            "const vm = require('node:vm');",
            "const [wrapper, producer, folder] = process.argv.slice(1);",
            "const plugin = require(producer);",
            "const originalKey = require.resolve(producer);",
            "delete require.cache[originalKey];",
            "const loaded = path.join(folder, 'karma-kotlin-reporter.js');",
            "fs.copyFileSync(producer, loaded);",
            "require.cache[loaded] = {filename: loaded, exports: plugin};",
            "const wrapperCode = fs.readFileSync(wrapper, 'utf8');",
            "function invoke(label) {",
            "  const attestation = path.join(folder, label + '.json');",
            "  vm.runInNewContext(wrapperCode, {config: {plugins: [plugin]}, Buffer, require,",
            "    process: {env: {DYN4K_BROWSER_REPORTER_ATTESTATION: attestation},",
            "      stdout: {fd: 1}}});",
            "  return attestation;",
            "}",
            "const valid = invoke('valid');",
            "const expected = crypto.createHash('sha256').update(fs.readFileSync(loaded)).digest('hex');",
            "assert.deepEqual(JSON.parse(fs.readFileSync(valid)),",
            "  {path: fs.realpathSync(loaded), sha256: expected});",
            "fs.appendFileSync(loaded, 'tampered');",
            "assert.throws(() => invoke('changed'), /producer bytes differ/);",
            "assert.equal(fs.existsSync(path.join(folder, 'changed.json')), false);",
            "fs.unlinkSync(loaded);",
            "assert.throws(() => invoke('absent'));",
            "assert.equal(fs.existsSync(path.join(folder, 'absent.json')), false);",
        ))
        for producer in (js_producer, wasm_producer):
            with tempfile.TemporaryDirectory() as directory:
                result = subprocess.run(
                    ["node", "-e", script, str(Path(__file__).with_name(
                        "browser-karma-reporter.js")), str(producer), directory],
                    capture_output=True, text=True, timeout=10,
                )
            with self.subTest(producer=producer):
                self.assertEqual(0, result.returncode, result.stderr)


class SourceCasesTest(unittest.TestCase):
    REVIEWED_SUCCESSOR = "8b0071563a31f7866f9fe8c3549ed284c9e7a092"
    REVIEWED_ASSEMBLY = "0533142a1358b2eebb3c3f36ae3dc1a8b01d9667"

    @staticmethod
    def current_revision() -> str:
        source_root = Path(__file__).resolve().parents[3]
        return subprocess.check_output(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"], text=True).strip()

    @staticmethod
    def clone_candidate(directory: str, name: str, revision: str) -> Path:
        source_root = Path(__file__).resolve().parents[3]
        checkout = Path(directory) / name
        subprocess.run(["git", "clone", "--quiet", "--shared", "--no-checkout",
                        str(source_root), str(checkout)], check=True)
        subprocess.run(["git", "-C", str(checkout), "checkout", "--quiet",
                        "--detach", revision], check=True)
        return checkout

    @staticmethod
    def commit_candidate(checkout: Path, relative: str) -> str:
        subprocess.run(["git", "-C", str(checkout), "add", "--", relative], check=True)
        subprocess.run(["git", "-C", str(checkout),
                        "-c", "user.name=Candidate Control",
                        "-c", "user.email=candidate-control@example.invalid",
                        "commit", "--quiet", "-m", "Adverse candidate control"], check=True)
        return subprocess.check_output(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()

    def test_public_candidate_rejects_pre_reseal_assembled_source(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = self.clone_candidate(directory, "assembled", self.REVIEWED_ASSEMBLY)
            historical = json.loads((checkout / "tools/qualification/full-common-corpus.json").read_text())
            self.assertEqual(2521, historical["counts"]["total_methods"])
            rejected = self.public_candidate(checkout, self.REVIEWED_ASSEMBLY)
            self.assertEqual(1, rejected.returncode)
            self.assertIn("corpus count differs", rejected.stderr)
            dishonest = self.public_candidate(checkout, self.REVIEWED_SUCCESSOR)
            self.assertEqual(1, dishonest.returncode)
            self.assertIn("source SHA differs", dishonest.stderr)

    def test_public_candidate_accepts_current_resealed_source(self):
        current = self.current_revision()
        with tempfile.TemporaryDirectory() as directory:
            checkout = self.clone_candidate(directory, "resealed", current)
            accepted = self.public_candidate(checkout, current)
            self.assertEqual(0, accepted.returncode, accepted.stderr)

    def test_fresh_checkout_stages_and_prepares_lane_with_reviewed_consumer_lock(self):
        import runner

        current = self.current_revision()
        with tempfile.TemporaryDirectory() as directory:
            checkout = self.clone_candidate(directory, "clean-consumer", current)
            lock = checkout / "consumers/qualification/browser-wasi/kotlin-js-store/yarn.lock"
            self.assertFalse(lock.exists())
            accepted = self.public_candidate(checkout, current)
            self.assertEqual(0, accepted.returncode, accepted.stderr)

            original_command = runner.command
            gradle_environment = []

            def observed_command(args, cwd, env=None):
                if args[0] == str(checkout / "gradlew"):
                    gradle_environment.append(env)
                    return subprocess.CompletedProcess(args, 0, "cached stage probe\n", "")
                return original_command(args, cwd, env)

            stage_output = Path(directory) / "stage"
            with mock.patch("runner.command", side_effect=observed_command), \
                    mock.patch("runner.staged_files", return_value={}):
                self.assertEqual(0, runner.stage(checkout, current, stage_output))
            self.assertTrue(lock.is_file())
            self.assertEqual(runner.CONSUMER_YARN_LOCK_SHA256, runner.sha256(lock))
            self.assertEqual("true", gradle_environment[0]["YARN_OFFLINE"])
            self.assertEqual(0, self.public_candidate(checkout, current).returncode)

            lock.unlink()
            with mock.patch("runner.verified_stage", side_effect=ValueError("stop before runtime")):
                self.assertEqual(1, runner.run_lane(
                    checkout, current, stage_output / "stage.json",
                    Path(directory) / "lane", "js", "chromium", "minimum",
                    "development", Path("/unneeded/browser"), "119.0.6045.105"))
            self.assertEqual(runner.CONSUMER_YARN_LOCK_SHA256, runner.sha256(lock))

            result = json.loads(accepted.stdout)
            self.assertEqual("VERIFIED", result["status"])
            self.assertEqual(2526, result["suite_methods"])
            self.assertEqual("edac14e1a000821b30cdd4bb3f07c82d78e33f305399a09849078dac210eb2ed",
                             result["manifest_sha256"])

    def test_public_candidate_rejects_generated_and_source_lock_mutations(self):
        current = self.current_revision()
        with tempfile.TemporaryDirectory() as directory:
            checkout = self.clone_candidate(directory, "lock-adverse", current)
            fixture = checkout / "tools/qualification/browser_wasi/fixtures/consumer-yarn.lock"
            lock = checkout / "consumers/qualification/browser-wasi/kotlin-js-store/yarn.lock"
            self.assertEqual(0, self.public_candidate(checkout, current).returncode)

            lock.parent.mkdir(parents=True)
            lock.write_bytes(fixture.read_bytes() + b"\n# wrong byte\n")
            rejected = self.public_candidate(checkout, current)
            self.assertEqual(1, rejected.returncode)
            self.assertIn("untracked candidate input", rejected.stderr)
            lock.unlink()

            lock.symlink_to(fixture)
            rejected = self.public_candidate(checkout, current)
            self.assertEqual(1, rejected.returncode)
            self.assertIn("untracked candidate input", rejected.stderr)
            lock.unlink()

            lock.write_bytes(fixture.read_bytes())
            duplicate = lock.with_name("yarn.lock.copy")
            duplicate.write_bytes(lock.read_bytes())
            rejected = self.public_candidate(checkout, current)
            self.assertEqual(1, rejected.returncode)
            self.assertIn("yarn.lock.copy", rejected.stderr)
            duplicate.unlink()
            self.assertEqual(0, self.public_candidate(checkout, current).returncode)

            fixture.write_bytes(fixture.read_bytes() + b"\n# source tamper\n")
            subprocess.run(["git", "-C", str(checkout), "update-index",
                            "--assume-unchanged", str(fixture)], check=True)
            rejected = self.public_candidate(checkout, current)
            self.assertEqual(1, rejected.returncode)
            self.assertIn("reviewed consumer lock fixture bytes differ", rejected.stderr)
            subprocess.run(["git", "-C", str(checkout), "update-index",
                            "--no-assume-unchanged", str(fixture)], check=True)
            changed_sha = self.commit_candidate(
                checkout, "tools/qualification/browser_wasi/fixtures/consumer-yarn.lock")
            rejected = self.public_candidate(checkout, changed_sha)
            self.assertEqual(1, rejected.returncode)
            self.assertIn("reviewed consumer lock fixture bytes differ", rejected.stderr)

    def test_public_candidate_rejects_committed_generator_mutation(self):
        current = self.current_revision()
        with tempfile.TemporaryDirectory() as directory:
            checkout = self.clone_candidate(directory, "generator", current)
            relative = "tools/qualification/full_corpus.py"
            generator = checkout / relative
            generator.write_bytes(generator.read_bytes() + b"\n# adverse generator mutation\n")
            changed_sha = self.commit_candidate(checkout, relative)
            rejected = self.public_candidate(checkout, changed_sha)
            self.assertEqual(1, rejected.returncode, rejected.stderr)
            self.assertIn("reviewed corpus generator differs", rejected.stderr)

    def test_public_candidate_rejects_committed_corpus_map_and_test_source_mutations(self):
        current = self.current_revision()
        with tempfile.TemporaryDirectory() as directory:
            for name, relative in (
                ("manifest", "tools/qualification/full-common-corpus.json"),
                ("map", "tools/qualification/full-common-original-map.tsv"),
                ("test-source", "dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/world/core/PhysicsWorldCoreCoverageTest.kt"),
            ):
                checkout = self.clone_candidate(directory, name, current)
                changed = checkout / relative
                self.assertTrue(changed.is_file(), changed)
                if name == "manifest":
                    manifest = json.loads(changed.read_text())
                    manifest["cases"].pop()
                    manifest["counts"]["total_methods"] -= 1
                    changed.write_text(json.dumps(manifest, sort_keys=True) + "\n")
                else:
                    changed.write_bytes(changed.read_bytes() + b"\n")
                changed_sha = self.commit_candidate(checkout, relative)
                rejected = self.public_candidate(checkout, changed_sha)
                self.assertEqual(1, rejected.returncode, f"{name}: {rejected.stderr}")
                self.assertTrue(
                    "corpus" in rejected.stderr or "map" in rejected.stderr,
                    f"{name}: {rejected.stderr}",
                )

    @staticmethod
    def public_candidate(root: Path, sha: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(Path(__file__).with_name("runner.py")), "candidate",
             "--root", str(root), "--candidate-sha", sha],
            capture_output=True, text=True, check=False,
        )

    def test_public_candidate_accepts_exact_reviewed_source_and_rejects_mutants(self):
        current = self.current_revision()
        with tempfile.TemporaryDirectory() as directory:
            checkout = self.clone_candidate(directory, "reviewed-candidate", current)
            exact = self.public_candidate(checkout, current)
            self.assertEqual(0, exact.returncode, exact.stderr)
            verified = json.loads(exact.stdout)
            self.assertEqual("VERIFIED", verified["status"])
            self.assertEqual(current, verified["candidate_sha"])
            self.assertEqual(2526, verified["suite_methods"])

            generated = checkout / "consumers/qualification/browser-wasi/build/generated.txt"
            generated.parent.mkdir(parents=True)
            generated.write_text("generated output")
            with_output = self.public_candidate(checkout, current)
            self.assertEqual(0, with_output.returncode, with_output.stderr)

            stale = self.public_candidate(checkout, "0" * 40)
            self.assertEqual(1, stale.returncode)
            self.assertIn("source SHA differs", stale.stderr)

            production = next((checkout / "dyn4k-core/src/commonMain/kotlin").rglob("*.kt"))
            production.write_bytes(production.read_bytes() + b"\n// source mutation\n")
            changed = self.public_candidate(checkout, current)
            self.assertEqual(1, changed.returncode)
            self.assertIn("dirty", changed.stderr)
            subprocess.run(["git", "-C", str(checkout), "update-index",
                            "--assume-unchanged", str(production)], check=True)
            hidden_change = self.public_candidate(checkout, current)
            self.assertEqual(1, hidden_change.returncode, hidden_change.stderr)
            self.assertIn("committed source bytes differ", hidden_change.stderr)
            subprocess.run(["git", "-C", str(checkout), "update-index",
                            "--no-assume-unchanged", str(production)], check=True)
            subprocess.run(["git", "-C", str(checkout), "restore", str(production)],
                           check=True)

            ignored = production.parent / "UntrackedCandidateInput.kt"
            ignored.write_text("package ignored\nclass UntrackedCandidateInput\n")
            (checkout / ".git/info/exclude").write_text(
                "/dyn4k-core/src/commonMain/kotlin/**/UntrackedCandidateInput.kt\n")
            untracked = self.public_candidate(checkout, current)
            self.assertEqual(1, untracked.returncode)
            self.assertIn("untracked candidate input", untracked.stderr)
            ignored.unlink()

            old = subprocess.check_output(
                ["git", "-C", str(checkout), "show",
                 "5f02826703f799fee0bd185b335e5cba36a08900:tools/qualification/full-common-corpus.json"])
            old_manifest = json.loads(old)
            current_manifest = json.loads(
                (checkout / "tools/qualification/full-common-corpus.json").read_text())
            old_manifest["source_tree_sha256"] = current_manifest["source_tree_sha256"]
            old_manifest["counts"]["total_methods"] = current_manifest["counts"]["total_methods"]
            (checkout / "tools/qualification/full-common-corpus.json").write_text(
                json.dumps(old_manifest, sort_keys=True))
            old_corpus = self.public_candidate(checkout, current)
            self.assertEqual(1, old_corpus.returncode)
            self.assertTrue(
                "dirty" in old_corpus.stderr or "corpus" in old_corpus.stderr,
                old_corpus.stderr,
            )

            from runner import candidate_identity

            with mock.patch("runner.full_corpus.candidate_checkout_problems", return_value=[]):
                with self.assertRaisesRegex(ValueError, "candidate commit bytes differ"):
                    candidate_identity(checkout, current)
                with mock.patch("runner.full_corpus.committed_bytes",
                                side_effect=lambda root, sha, path: (root / path).read_bytes()):
                    with self.assertRaisesRegex(ValueError, "corpus differs from source tree"):
                        candidate_identity(checkout, current)

            subprocess.run(["git", "-C", str(checkout), "restore",
                            "tools/qualification/full-common-corpus.json"], check=True)
            consumer_build = checkout / "consumers/qualification/browser-wasi/build.gradle.kts"
            consumer_build.write_bytes(consumer_build.read_bytes().replace(
                b"io.github.rubixhacker:dyn4k-core:0.1.0-alpha.1",
                b"io.github.rubixhacker:dyn4k-core:0.1.0-alpha.0"))
            with mock.patch("runner.full_corpus.candidate_checkout_problems", return_value=[]):
                with self.assertRaisesRegex(ValueError, "consumer dependency pins differ"):
                    candidate_identity(checkout, current)

    @staticmethod
    def copy_lane(source: Path, directory: str) -> tuple[dict, Path]:
        copied = Path(directory) / source.name
        shutil.copytree(source, copied)

        def replace_paths(value):
            if isinstance(value, str):
                return value.replace(str(source), str(copied))
            if isinstance(value, list):
                return [replace_paths(item) for item in value]
            if isinstance(value, dict):
                return {key: replace_paths(item) for key, item in value.items()}
            return value

        return replace_paths(json.loads((copied / "lane.json").read_text())), copied

    @staticmethod
    def save_copied_lane(lane: dict, copied: Path) -> None:
        from runner import sealed_lane, sha256, write_json

        for module in lane["modules"].values():
            result = Path(module["result_json"])
            write_json(result, {key: value for key, value in module.items()
                                if key not in ("result_json", "result_json_sha256")})
            module["result_json_sha256"] = sha256(result)
        write_json(copied / "lane.json", sealed_lane(lane))

    @classmethod
    def copy_resealed_diagnostic_depth(cls, source: Path, case: Path, value: str) -> Path:
        from runner import sha256
        import xml.etree.ElementTree as ET

        lane, copied = cls.copy_lane(source, str(case))
        module = lane["modules"]["dyn4k-core"]
        report_item = next(item for item in module["raw_xml"]
                           if "WindowsCollisionIntermediateDiagnosticTest" in item["path"])
        report = Path(report_item["path"])
        timestamp = report.stat()
        suite = ET.parse(report).getroot()
        output = suite.find("system-out")
        rows = output.text.splitlines()
        if len(rows) != 72:
            raise ValueError("retained browser diagnostic row count differs")
        fields = rows[0].split("\t")
        depth = next(i for i, field in enumerate(fields)
                     if field.startswith("penetration.depth="))
        fields[depth] = f"penetration.depth={value}"
        rows[0] = "\t".join(fields)
        output.text = "\n".join(rows) + "\n"
        ET.ElementTree(suite).write(report, encoding="unicode")
        os.utime(report, ns=(timestamp.st_atime_ns, timestamp.st_mtime_ns))
        report_item["sha256"] = sha256(report)
        module["diagnostic_sha256"] = hashlib.sha256(
            "\n".join(rows).encode()).hexdigest()
        cls.save_copied_lane(lane, copied)
        return copied / "lane.json"

    def test_public_browser_receipt_rejects_resealed_diagnostic_and_producer_mutations(self):
        from runner import sha256
        import xml.etree.ElementTree as ET

        original = os.environ.get("DYN4K_BROWSER_WASI_PUBLIC_RECEIPT")
        if original is None:
            self.skipTest("set DYN4K_BROWSER_WASI_PUBLIC_RECEIPT to a passing browser lane")
        source = Path(original).parent
        self.assertTrue((source / "lane.json").is_file(), source)
        root = Path(__file__).resolve().parents[3]

        def public_audit(receipt: Path) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [sys.executable, str(root / "tools/qualification/browser_wasi/runner.py"),
                 "audit", "--receipt", str(receipt)],
                capture_output=True, text=True, check=False,
            )

        with tempfile.TemporaryDirectory() as directory:
            baseline = public_audit(source / "lane.json")
            self.assertEqual(0, baseline.returncode, baseline.stderr)
            for mutation in ("deleted_row", "duplicate_row", "truncated_row",
                             "partial_numeric_value",
                             "changed_producer", "absent_producer"):
                case_dir = Path(directory) / mutation
                case_dir.mkdir()
                lane, copied = self.copy_lane(source, str(case_dir))
                module = lane["modules"]["dyn4k-core"]
                diagnostic_mutation = mutation.endswith("row") or mutation == "partial_numeric_value"
                if diagnostic_mutation:
                    report = next(Path(item["path"]) for item in module["raw_xml"]
                                  if "WindowsCollisionIntermediateDiagnosticTest" in item["path"])
                    suite = ET.parse(report).getroot()
                    output = suite.find("system-out")
                    rows = output.text.splitlines()
                    self.assertEqual(72, len(rows))
                    if mutation == "deleted_row":
                        rows.pop(0)
                    elif mutation == "duplicate_row":
                        rows.append(rows[0])
                    elif mutation == "truncated_row":
                        rows[0] = rows[0].rsplit("\t", 1)[0]
                    else:
                        fields = rows[0].split("\t")
                        transform = next(i for i, field in enumerate(fields)
                                         if field.startswith("a.transform="))
                        fields[transform] = "a.transform=1@4"
                        rows[0] = "\t".join(fields)
                    output.text = "\n".join(rows) + "\n"
                    ET.ElementTree(suite).write(report, encoding="unicode")
                    for item in module["raw_xml"]:
                        if item["path"] == str(report):
                            item["sha256"] = sha256(report)
                elif mutation == "changed_producer":
                    retained = Path(module["karma_reporter_retained"])
                    retained.write_bytes(retained.read_bytes() + b"tampered")
                    module["karma_reporter_sha256"] = sha256(retained)
                else:
                    module["karma_reporter_source"] += ".missing"
                self.save_copied_lane(lane, copied)
                rejected = public_audit(copied / "lane.json")
                with self.subTest(mutation=mutation):
                    self.assertEqual(1, rejected.returncode, rejected.stderr)
                    self.assertIn("diagnostic" if diagnostic_mutation else
                                  "reporter", rejected.stderr.lower())

    def test_public_signed_zero_replay_accepts_js_and_wasm_and_rejects_resealed_wasm(self):
        from runner import sha256
        import xml.etree.ElementTree as ET

        wasm_receipt = os.environ.get("DYN4K_BROWSER_WASI_SIGNED_ZERO_WASM_RECEIPT")
        wasm_replay = os.environ.get("DYN4K_BROWSER_WASI_SIGNED_ZERO_WASM_REPLAY_ROOT")
        js_receipt = os.environ.get("DYN4K_BROWSER_WASI_SIGNED_ZERO_JS_RECEIPT")
        js_replay = os.environ.get("DYN4K_BROWSER_WASI_SIGNED_ZERO_JS_REPLAY_ROOT")
        if any(value is None for value in (wasm_receipt, wasm_replay, js_receipt, js_replay)):
            self.skipTest("set real JS/Wasm receipts and exact source replay checkouts")
        with tempfile.TemporaryDirectory() as directory:
            for target, receipt, replay in (("js", js_receipt, js_replay),
                                            ("wasmJs", wasm_receipt, wasm_replay)):
                with mock.patch.dict(os.environ, {"DYN4K_BROWSER_WASI_REPLAY_ROOT": replay}):
                    accepted = self.public_historical_audit(
                        Path(receipt), Path(directory) / f"{target}-auditor")
                self.assertEqual(0, accepted.returncode, accepted.stderr)

            lane, copied = self.copy_lane(Path(wasm_receipt).parent, directory)
            module = lane["modules"]["dyn4k-core"]
            report_item = next(item for item in module["raw_xml"]
                               if "WindowsCollisionIntermediateDiagnosticTest" in item["path"])
            report = Path(report_item["path"])
            timestamp = report.stat()
            suite = ET.parse(report).getroot()
            output = suite.find("system-out")
            rows = output.text.splitlines()
            fields = rows[0].split("\t")
            transform = next(i for i, field in enumerate(fields)
                             if field.startswith("a.transform="))
            original = "-0.0@-9223372036854775808"
            self.assertIn(original, fields[transform])
            fields[transform] = fields[transform].replace(original, "-0.0@0", 1)
            rows[0] = "\t".join(fields)
            output.text = "\n".join(rows) + "\n"
            ET.ElementTree(suite).write(report, encoding="unicode")
            os.utime(report, ns=(timestamp.st_atime_ns, timestamp.st_mtime_ns))
            report_item["sha256"] = sha256(report)
            module["diagnostic_sha256"] = hashlib.sha256(
                "\n".join(rows).encode()).hexdigest()
            self.save_copied_lane(lane, copied)
            with mock.patch.dict(os.environ,
                                 {"DYN4K_BROWSER_WASI_REPLAY_ROOT": wasm_replay}):
                rejected = self.public_historical_audit(
                    copied / "lane.json", Path(directory) / "mutant-auditor")
            self.assertEqual(1, rejected.returncode, rejected.stderr)
            self.assertIn("raw bits", rejected.stderr)

    def test_public_finite_decimal_range_rejects_resealed_real_wasm(self):
        receipt = os.environ.get("DYN4K_BROWSER_WASI_RANGE_WASM_RECEIPT")
        replay = os.environ.get("DYN4K_BROWSER_WASI_RANGE_WASM_REPLAY_ROOT")
        artifacts = os.environ.get("DYN4K_BROWSER_WASI_RANGE_ARTIFACTS")
        if any(value is None for value in (receipt, replay, artifacts)):
            self.skipTest("set real Wasm receipt, exact replay root, and range artifacts")
        source = Path(receipt).parent
        evidence = Path(artifacts)
        evidence.mkdir(parents=True, exist_ok=False)
        with mock.patch.dict(os.environ, {"DYN4K_BROWSER_WASI_REPLAY_ROOT": replay}):
            baseline = self.public_historical_audit(
                Path(receipt), evidence / "baseline-auditor")
            self.assertEqual(0, baseline.returncode, baseline.stderr)
            for name, value in (
                ("positive-underflow", "1e-999@0"),
                ("negative-underflow", "-1e-999@-9223372036854775808"),
                ("positive-overflow", "1e999@9218868437227405312"),
                ("negative-overflow", "-1e999@-4503599627370496"),
            ):
                case = evidence / name
                case.mkdir()
                copied_receipt = self.copy_resealed_diagnostic_depth(source, case, value)
                audited = self.public_historical_audit(
                    copied_receipt, case / "auditor")
                (case / "audit-result.json").write_text(json.dumps({
                    "returncode": audited.returncode,
                    "stdout": audited.stdout,
                    "stderr": audited.stderr,
                }, indent=2) + "\n")
                with self.subTest(value=value):
                    self.assertEqual(1, audited.returncode, audited.stderr)
                    self.assertIn("finite decimal", audited.stderr)

    def test_public_zero_spelling_rejects_resealed_real_wasm(self):
        receipt = os.environ.get("DYN4K_BROWSER_WASI_ZERO_WASM_RECEIPT")
        replay = os.environ.get("DYN4K_BROWSER_WASI_ZERO_WASM_REPLAY_ROOT")
        artifacts = os.environ.get("DYN4K_BROWSER_WASI_ZERO_ARTIFACTS")
        if any(value is None for value in (receipt, replay, artifacts)):
            self.skipTest("set real Wasm receipt, exact replay root, and zero artifacts")
        source = Path(receipt).parent
        evidence = Path(artifacts)
        evidence.mkdir(parents=True, exist_ok=False)
        with mock.patch.dict(os.environ, {"DYN4K_BROWSER_WASI_REPLAY_ROOT": replay}):
            baseline = self.public_historical_audit(
                Path(receipt), evidence / "baseline-auditor")
            self.assertEqual(0, baseline.returncode, baseline.stderr)
            for name, value in (
                ("positive-exponent", "0e999@0"),
                ("negative-exponent", "-0e999@-9223372036854775808"),
                ("positive-precision", "0.000@0"),
                ("negative-precision", "-0.000@-9223372036854775808"),
            ):
                case = evidence / name
                case.mkdir()
                copied_receipt = self.copy_resealed_diagnostic_depth(source, case, value)
                audited = self.public_historical_audit(
                    copied_receipt, case / "auditor")
                (case / "audit-result.json").write_text(json.dumps({
                    "returncode": audited.returncode,
                    "stdout": audited.stdout,
                    "stderr": audited.stderr,
                }, indent=2) + "\n")
                with self.subTest(value=value):
                    self.assertEqual(1, audited.returncode, audited.stderr)
                    self.assertIn("zero spelling", audited.stderr)

    def test_public_wasmtime_receipt_rejects_events_moved_to_stderr(self):
        from runner import sha256

        original = os.environ.get("DYN4K_BROWSER_WASI_WASMTIME_RECEIPT")
        replay = os.environ.get("DYN4K_BROWSER_WASI_REPLAY_ROOT")
        if original is None or replay is None:
            self.skipTest("set retained Wasmtime receipt and its exact source replay checkout")
        source = Path(original).parent
        self.assertTrue((source / "lane.json").is_file(), source)
        with tempfile.TemporaryDirectory() as directory:
            lane, copied = self.copy_lane(source, directory)
            receipt = copied / "lane.json"
            self.save_copied_lane(lane, copied)
            baseline = self.public_historical_audit(
                receipt, Path(directory) / "baseline-auditor")
            self.assertEqual(0, baseline.returncode, baseline.stderr)

            module = lane["modules"]["dyn4k-core"]
            stdout = Path(module["raw_stdout"])
            stderr = Path(module["raw_stderr"])
            original_stdout = stdout.read_text()
            self.assertIn("##teamcity[", original_stdout)
            stdout.write_text("")
            stderr.write_text(original_stdout + stderr.read_text())
            module["raw_stdout_sha256"] = sha256(stdout)
            module["raw_stderr_sha256"] = sha256(stderr)
            self.save_copied_lane(lane, copied)
            rejected = self.public_historical_audit(
                receipt, Path(directory) / "mutant-auditor")
            self.assertEqual(1, rejected.returncode, rejected.stderr)
            self.assertIn("test identities", rejected.stderr)

    @staticmethod
    def public_historical_audit(
        receipt: Path, audit_view: Path, extra_mounts: tuple[str, ...] = ()
    ) -> subprocess.CompletedProcess[str]:
        root = Path(json.loads(receipt.read_text())["candidate_root"])
        auditor_root = Path(__file__).resolve().parents[3]
        replay = Path(os.environ["DYN4K_BROWSER_WASI_REPLAY_ROOT"])
        audit_view.mkdir()
        mounts = ["--ro-bind", "/", "/", "--bind", "/tmp", "/tmp",
                  "--dev-bind", "/dev", "/dev", "--proc", "/proc",
                  "--ro-bind", str(auditor_root), str(audit_view),
                  "--bind", str(replay), str(root)]
        for suffix in ("build", "dyn4k-core/build", "dyn4k/build",
                       "consumers/qualification/browser-wasi/build"):
            mounts.extend(("--bind", str(root / suffix), str(root / suffix)))
        mounts.extend(extra_mounts)
        return subprocess.run(
            ["bwrap", *mounts, "--", "env", "PYTHONDONTWRITEBYTECODE=1", "python3",
             str(audit_view / "tools/qualification/browser_wasi/runner.py"),
             "audit", "--receipt", str(receipt)],
            capture_output=True, text=True, check=False,
        )

    def assert_resealed_public_config_mutation_rejected(
        self, mutation: str, lane_name: str = "js-chromium-minimum-production"
    ) -> None:
        from runner import sha256

        evidence_root = os.environ.get("DYN4K_BROWSER_WASI_REVIEW_EVIDENCE")
        replay_root = os.environ.get("DYN4K_BROWSER_WASI_REPLAY_ROOT")
        if not evidence_root or not replay_root:
            self.skipTest("set review evidence and replay root for public historical audit")
        source = Path(evidence_root) / lane_name
        self.assertTrue((source / "lane.json").is_file(), source)
        with tempfile.TemporaryDirectory() as directory:
            lane, copied = self.copy_lane(source, directory)
            receipt = copied / "lane.json"
            self.save_copied_lane(lane, copied)
            baseline = self.public_historical_audit(receipt, Path(directory) / "baseline-auditor")
            self.assertEqual(0, baseline.returncode, baseline.stderr)

            module = lane["modules"]["dyn4k-core"]
            config = Path(module["karma_config"])
            content = config.read_text()
            if mutation in ("json_exclude_input", "json_custom_launcher", "json_disable_set"):
                before, separator, after = content.partition("});")
                self.assertEqual("});", separator)
                start = before.index("config.set({") + len("config.set(")
                settings = json.loads(before[start:] + "}")
                if mutation == "json_exclude_input":
                    settings["exclude"] = [settings["files"][1]]
                elif mutation == "json_custom_launcher":
                    settings["customLaunchers"] = {
                        "ChromeHeadless": {"base": "FirefoxHeadless"}}
                else:
                    settings["set"] = None
                config.write_text(before[:start] + json.dumps(settings, indent=2) + ");" + after)
            else:
                port_setter = f"config.set({{port: {module['karma_port']}}});"
                self.assertEqual(1, content.count(port_setter))
                if mutation == "unreachable_port_setter":
                    replacement = "return;\n" + port_setter
                elif mutation == "later_browser_override":
                    replacement = 'config.set({browsers: ["FirefoxHeadless"]});\n' + port_setter
                elif mutation == "later_js_input_override":
                    wrong = module["linked_source"].replace(
                        "testProductionExecutable", "testDevelopmentExecutable")
                    self.assertNotEqual(wrong, module["linked_source"])
                    replacement = ('config.set({files: ["/tmp/runner.js", ' + json.dumps(wrong) +
                                   '], preprocessors: {' + json.dumps(wrong) +
                                   ': ["webpack", "sourcemap"]}});\n' + port_setter)
                else:
                    self.fail(f"unknown Karma mutation: {mutation}")
                config.write_text(content.replace(port_setter, replacement))
            module["karma_config_sha256"] = sha256(config)
            self.save_copied_lane(lane, copied)
            rejected = self.public_historical_audit(receipt, Path(directory) / "mutant-auditor")
            self.assertEqual(1, rejected.returncode, rejected.stderr)
            self.assertIn("Karma", rejected.stderr)

    def test_public_audit_rejects_unreachable_port_setter(self):
        self.assert_resealed_public_config_mutation_rejected("unreachable_port_setter")

    def test_public_audit_rejects_later_browser_override(self):
        self.assert_resealed_public_config_mutation_rejected("later_browser_override")

    def test_public_audit_rejects_later_js_input_override(self):
        self.assert_resealed_public_config_mutation_rejected("later_js_input_override")

    def test_public_audit_rejects_json_excluded_js_input(self):
        self.assert_resealed_public_config_mutation_rejected("json_exclude_input")

    def test_public_audit_rejects_json_excluded_wasm_input(self):
        self.assert_resealed_public_config_mutation_rejected(
            "json_exclude_input", "wasmJs-firefox-minimum-production")

    def test_public_audit_rejects_json_custom_launcher(self):
        self.assert_resealed_public_config_mutation_rejected("json_custom_launcher")

    def test_public_audit_rejects_json_disabled_port_setter(self):
        self.assert_resealed_public_config_mutation_rejected("json_disable_set")

    def test_public_audit_rejects_changed_karma_helper_bytes(self):
        evidence_root = os.environ.get("DYN4K_BROWSER_WASI_REVIEW_EVIDENCE")
        replay_root = os.environ.get("DYN4K_BROWSER_WASI_REPLAY_ROOT")
        if not evidence_root or not replay_root:
            self.skipTest("set review evidence and replay root for public historical audit")
        source = Path(evidence_root) / "wasmJs-firefox-minimum-production"
        with tempfile.TemporaryDirectory() as directory:
            lane, copied = self.copy_lane(source, directory)
            receipt = copied / "lane.json"
            self.save_copied_lane(lane, copied)
            baseline = self.public_historical_audit(receipt, Path(directory) / "baseline-auditor")
            self.assertEqual(0, baseline.returncode, baseline.stderr)
            config = Path(lane["modules"]["dyn4k-core"]["karma_config"]).read_text()
            before = config.partition("});")[0]
            settings = json.loads(before[before.index("config.set({") + len("config.set("):] + "}")
            runner_input = Path(settings["files"][0])
            changed = Path(directory) / "changed-karma-runner.js"
            changed.write_bytes(runner_input.read_bytes() + b"\n")
            rejected = self.public_historical_audit(
                receipt, Path(directory) / "mutant-auditor",
                ("--bind", str(changed), str(runner_input)))
            self.assertEqual(1, rejected.returncode, rejected.stderr)
            self.assertIn("Karma", rejected.stderr)

    def test_committed_common_corpus_has_all_browser_and_wasi_cases(self):
        from runner import common_corpus_cases

        root = Path(__file__).resolve().parents[3]
        candidate = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        core = common_corpus_cases(root, candidate, "dyn4k-core")
        facade = common_corpus_cases(root, candidate, "dyn4k")
        self.assertEqual(2465, len(core))
        self.assertEqual(58, len(facade))
        self.assertIn(("org.dyn4j.coverage.world.core.PhysicsWorldCoreCoverageTest",
                       "addBody"), core)

    def test_collects_each_public_test_identity_across_classes(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "Suite.kt"
            source.write_text(
                "package sample\n"
                "class FirstTest {\n"
                "  @Test fun identity() {}\n"
                "  @Test\n"
                "  fun collision() {}\n"
                "}\n"
                "class SecondTest {\n"
                "  @Test fun callback() {}\n"
                "}\n"
            )
            self.assertEqual(
                {
                    ("sample.FirstTest", "identity"),
                    ("sample.FirstTest", "collision"),
                    ("sample.SecondTest", "callback"),
                },
                source_cases(Path(directory)),
            )

    def test_rejects_skipped_or_partial_browser_results(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "TEST-suite.xml"
            report.write_text(
                '<testsuite tests="1" failures="0" errors="0" skipped="1">'
                '<testcase classname="jsBrowserTest.sample.FirstTest" '
                'name="identity[js, browser, ChromeHeadless155.0.0.0, Linux0.0.0]">'
                '<skipped/></testcase></testsuite>'
            )
            with self.assertRaisesRegex(ValueError, "skipped"):
                verify_reports(
                    Path(directory),
                    {("sample.FirstTest", "identity")},
                    "jsBrowserTest",
                    "ChromeHeadless155",
                )

            report.write_text('<testsuite tests="0" failures="0" errors="0" skipped="0"/>')
            with self.assertRaisesRegex(ValueError, "zero"):
                verify_reports(
                    Path(directory),
                    {("sample.FirstTest", "identity")},
                    "jsBrowserTest",
                    "ChromeHeadless155",
                )

    def test_rejects_browser_major_that_only_starts_with_selected_major(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "TEST-suite.xml"
            report.write_text(
                '<testsuite tests="1" failures="0" errors="0" skipped="0">'
                '<testcase classname="jsBrowserTest.sample.FirstTest" '
                'name="identity[js, browser, ChromeHeadless1199.0.0.0, Linux0.0.0]"/>'
                '</testsuite>'
            )
            with self.assertRaisesRegex(ValueError, "wrong runtime"):
                verify_reports(
                    Path(directory),
                    {("sample.FirstTest", "identity")},
                    "jsBrowserTest",
                    "ChromeHeadless119",
                )

    def test_browser_launcher_binds_the_process_image(self):
        from runner import verify_browser_launches

        selected = Path(shutil.which("sleep"))
        launcher = Path(__file__).with_name("browser_launcher.py")
        with tempfile.TemporaryDirectory() as directory:
            attestation = Path(directory) / "launch.jsonl"
            token = "test-browser-launch"
            env = dict(os.environ, DYN4K_BROWSER_SELECTED_BINARY=str(selected),
                       DYN4K_BROWSER_ATTESTATION=str(attestation), DYN4K_BROWSER_TOKEN=token,
                       DYN4K_BROWSER_RUNTIME="chromium")
            launched = subprocess.run(
                [sys.executable, str(launcher), "0.2"], env=env,
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(0, launched.returncode, launched.stderr)
            records = verify_browser_launches(attestation, selected, token, "chromium")
            self.assertEqual(selected.resolve(), Path(records[0]["process_executable"]))

            forged = json.loads(attestation.read_text())
            forged["process_sha256"] = "0" * 64
            attestation.write_text(json.dumps(forged) + "\n")
            with self.assertRaisesRegex(ValueError, "process image"):
                verify_browser_launches(attestation, selected, token, "chromium")

    def test_browser_process_keeps_karmas_launcher_pid(self):
        selected = Path(shutil.which("sleep"))
        launcher = Path(__file__).with_name("browser_launcher.py")
        with tempfile.TemporaryDirectory() as directory:
            attestation = Path(directory) / "launch.jsonl"
            env = dict(os.environ, DYN4K_BROWSER_SELECTED_BINARY=str(selected),
                       DYN4K_BROWSER_ATTESTATION=str(attestation),
                       DYN4K_BROWSER_TOKEN="test-process-lifecycle",
                       DYN4K_BROWSER_RUNTIME="chromium")
            launched = subprocess.Popen([sys.executable, str(launcher), "10"], env=env,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            recorded_pid = None
            try:
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and not attestation.is_file():
                    time.sleep(0.01)
                self.assertTrue(attestation.is_file(), "browser launch was not attested")
                recorded_pid = json.loads(attestation.read_text())["pid"]
                self.assertEqual(launched.pid, recorded_pid)
            finally:
                launched.terminate()
                launched.wait(timeout=3)
                launched.stderr.close()
                if recorded_pid is not None and recorded_pid != launched.pid:
                    os.kill(recorded_pid, 15)

    def test_staged_physics_contract_rejects_noop_and_missing_assertions(self):
        from runner import verify_consumer_physics_contract

        source = (Path(__file__).resolve().parents[3] / "consumers/qualification/browser-wasi"
                  / "src/commonTest/kotlin/qualification/StagedWorldTest.kt")
        original = source.read_text()
        verify_consumer_physics_contract(source)
        mutations = (
            "package qualification\nclass StagedWorldTest {\n"
            "  @Test fun stagedModulesShareBodiesAndDeliverCollisionCallbacks() {}\n}\n",
            original.replace("assertSame(moving, same)", "Unit"),
            original.replace("world.step(1)", "Unit"),
            original.replace("collisions++", "Unit"),
            original.replace("assertTrue(contact != null)", "Unit"),
            original.replace("assertTrue(began > 0", "assertTrue(began >= 0"),
        )
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "StagedWorldTest.kt"
            for mutated in mutations:
                self.assertNotEqual(original, mutated)
                candidate.write_text(mutated)
                with self.assertRaisesRegex(ValueError, "physics contract"):
                    verify_consumer_physics_contract(candidate)

    def test_lane_receipt_rejects_changed_console_and_executable_bytes(self):
        from runner import audit_lane_receipt

        with tempfile.TemporaryDirectory() as directory:
            lane_dir = Path(directory)
            module_dir = lane_dir / "dyn4k-core"
            module_dir.mkdir()
            files = {
                "gradle_console": module_dir / "gradle-console.log",
                "raw_console": module_dir / "wasmtime-console.log",
                "linked_executable": module_dir / "linked-executable.wasm",
            }
            for label, path in files.items():
                path.write_bytes(label.encode())
            module = {"status": "PASSED"}
            for label, path in files.items():
                module[label] = str(path)
                module["linked_sha256" if label == "linked_executable" else label + "_sha256"] = (
                    hashlib.sha256(path.read_bytes()).hexdigest()
                )
            receipt = lane_dir / "lane.json"
            receipt.write_text(json.dumps({"status": "FAILED", "target": "wasmWasi",
                                           "modules": {"dyn4k-core": module}}))
            audit_lane_receipt(receipt)
            for path in files.values():
                original = path.read_bytes()
                path.write_bytes(original + b"tampered")
                with self.assertRaisesRegex(ValueError, "digest"):
                    audit_lane_receipt(receipt)
                path.write_bytes(original)

            del module["raw_console_sha256"]
            receipt.write_text(json.dumps({"status": "FAILED", "target": "wasmWasi",
                                           "modules": {"dyn4k-core": module}}))
            with self.assertRaisesRegex(ValueError, "digest"):
                audit_lane_receipt(receipt)

    def test_audit_rejects_forged_passing_wasmtime_receipt(self):
        from runner import audit_lane_receipt

        with tempfile.TemporaryDirectory() as directory:
            lane_dir = Path(directory)
            modules = {}
            for name in ("dyn4k-core", "dyn4k", "consumer"):
                folder = lane_dir / name
                folder.mkdir()
                evidence = {"status": "PASSED", "expected": 2465 if name == "dyn4k-core"
                            else 58 if name == "dyn4k" else 1,
                            "executed": 2465 if name == "dyn4k-core"
                            else 58 if name == "dyn4k" else 1,
                            "failures": 0, "skipped": 0}
                for field, filename in (("gradle_console", "gradle-console.log"),
                                        ("raw_console", "wasmtime-console.log"),
                                        ("linked_executable", "linked-executable.wasm")):
                    path = folder / filename
                    path.write_text("BUILD SUCCESSFUL\n" if field == "gradle_console"
                                    else "fake PASS\n")
                    evidence[field] = str(path)
                    digest_field = "linked_sha256" if field == "linked_executable" else field + "_sha256"
                    evidence[digest_field] = hashlib.sha256(path.read_bytes()).hexdigest()
                result = folder / "result.json"
                result.write_text(json.dumps(evidence))
                evidence["result_json"] = str(result)
                evidence["result_json_sha256"] = hashlib.sha256(result.read_bytes()).hexdigest()
                modules[name] = evidence
            receipt = lane_dir / "lane.json"
            receipt.write_text(json.dumps({"status": "PASSED", "target": "wasmWasi",
                                           "modules": modules}))
            with self.assertRaises(ValueError):
                audit_lane_receipt(receipt)

    def test_audit_rejects_tampered_receipt_seal(self):
        from runner import audit_lane_receipt, sealed_lane

        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / "lane.json"
            lane = sealed_lane({"status": "FAILED", "target": "wasmWasi", "modules": {},
                                "reason": "runtime failed"})
            receipt.write_text(json.dumps(lane))
            audit_lane_receipt(receipt)
            lane["reason"] = "claimed success"
            receipt.write_text(json.dumps(lane))
            with self.assertRaisesRegex(ValueError, "seal"):
                audit_lane_receipt(receipt)

    def test_resealed_browser_configuration_relabel_is_rejected(self):
        from runner import audit_lane_receipt

        evidence_root = os.environ.get("DYN4K_BROWSER_WASI_REVIEW_EVIDENCE")
        if evidence_root is None:
            self.skipTest("set DYN4K_BROWSER_WASI_REVIEW_EVIDENCE to a full 20-lane archive")
        for target, runtime in (("js", "chromium"), ("wasmJs", "firefox")):
            for original, claimed in (("development", "production"),
                                      ("production", "development")):
                source = Path(evidence_root) / f"{target}-{runtime}-minimum-{original}"
                self.assertTrue((source / "lane.json").is_file(), source)
                with tempfile.TemporaryDirectory() as directory:
                    lane, copied = self.copy_lane(source, directory)
                    lane["configuration"] = claimed
                    for module in lane["modules"].values():
                        module["configuration"] = claimed
                    self.save_copied_lane(lane, copied)
                    with self.subTest(target=target, original=original, claimed=claimed):
                        with self.assertRaisesRegex(ValueError, "configuration|production|development"):
                            with mock.patch("runner.candidate_identity"):
                                audit_lane_receipt(copied / "lane.json")

    def test_resealed_browser_output_binding_mutations_are_rejected(self):
        from runner import audit_lane_receipt, sha256

        evidence_root = os.environ.get("DYN4K_BROWSER_WASI_REVIEW_EVIDENCE")
        if evidence_root is None:
            self.skipTest("set DYN4K_BROWSER_WASI_REVIEW_EVIDENCE to a full 20-lane archive")
        for original, mutation, expected_error in (
            ("production", "missing_production_flag", "Gradle configuration"),
            ("production", "missing_production_marker", "browser configuration input"),
            ("production", "development_linked_source", "linked source configuration"),
            ("production", "wrong_linked_digest", "linked source digest"),
            ("production", "wrong_browser_task", "Gradle configuration"),
            ("development", "added_production_flag", "Gradle configuration"),
        ):
            source = Path(evidence_root) / f"js-chromium-minimum-{original}"
            self.assertTrue((source / "lane.json").is_file(), source)
            with tempfile.TemporaryDirectory() as directory:
                lane, copied = self.copy_lane(source, directory)
                module = lane["modules"]["dyn4k-core"]
                if mutation == "missing_production_flag":
                    module["gradle_command"].remove("-PqualificationProduction=true")
                elif mutation == "missing_production_marker":
                    stdout = Path(module["gradle_stdout"])
                    stdout.write_text("".join(line for line in stdout.read_text().splitlines(True)
                                              if not line.startswith("qualification test input:")))
                    console = Path(module["gradle_console"])
                    console.write_text(stdout.read_text() + Path(module["gradle_stderr"]).read_text())
                    module["gradle_stdout_sha256"] = sha256(stdout)
                    module["gradle_console_sha256"] = sha256(console)
                elif mutation == "development_linked_source":
                    module["linked_source"] = module["linked_source"].replace(
                        "testProductionExecutable", "testDevelopmentExecutable")
                elif mutation == "wrong_linked_digest":
                    module["linked_source_sha256"] = "0" * 64
                elif mutation == "wrong_browser_task":
                    module["gradle_command"][2] = ":dyn4k-core:wasmJsBrowserTest"
                else:
                    module["gradle_command"].append("-PqualificationProduction=true")
                self.save_copied_lane(lane, copied)
                with self.subTest(mutation=mutation):
                    with self.assertRaisesRegex(ValueError, expected_error):
                        with mock.patch("runner.candidate_identity"):
                            audit_lane_receipt(copied / "lane.json")

    def test_resealed_relabel_with_forged_command_and_output_is_rejected(self):
        from runner import (audit_lane_receipt, gradle_command, linked_file, sha256,
                            test_project)

        evidence_root = os.environ.get("DYN4K_BROWSER_WASI_REVIEW_EVIDENCE")
        if evidence_root is None:
            self.skipTest("set DYN4K_BROWSER_WASI_REVIEW_EVIDENCE to a full 20-lane archive")
        for original, claimed in (("development", "production"),
                                  ("production", "development")):
            source = Path(evidence_root) / f"js-chromium-minimum-{original}"
            self.assertTrue((source / "lane.json").is_file(), source)
            with tempfile.TemporaryDirectory() as directory:
                lane, copied = self.copy_lane(source, directory)
                lane["configuration"] = claimed
                root = Path(lane["candidate_root"])
                for name, module in lane["modules"].items():
                    module["configuration"] = claimed
                    module["gradle_command"] = gradle_command(root, name, "js", claimed)
                    linked = linked_file(test_project(root, name), "js", claimed, name)
                    module["linked_source"] = str(linked)
                    stdout = Path(module["gradle_stdout"])
                    output = "".join(line for line in stdout.read_text().splitlines(True)
                                     if not line.startswith("qualification test input:"))
                    if claimed == "production":
                        output += f"qualification test input: {linked}\n"
                    stdout.write_text(output)
                    console = Path(module["gradle_console"])
                    console.write_text(output + Path(module["gradle_stderr"]).read_text())
                    module["gradle_stdout_sha256"] = sha256(stdout)
                    module["gradle_console_sha256"] = sha256(console)
                self.save_copied_lane(lane, copied)
                with self.subTest(original=original, claimed=claimed):
                    with self.assertRaisesRegex(ValueError, "linked source digest"):
                        with mock.patch("runner.candidate_identity"):
                            audit_lane_receipt(copied / "lane.json")

    def test_resealed_browser_omitted_karma_evidence_is_rejected(self):
        from runner import audit_lane_receipt

        evidence_root = os.environ.get("DYN4K_BROWSER_WASI_REVIEW_EVIDENCE")
        if evidence_root is None:
            self.skipTest("set DYN4K_BROWSER_WASI_REVIEW_EVIDENCE to a full 20-lane archive")
        source = Path(evidence_root) / "js-chromium-minimum-development"
        self.assertTrue((source / "lane.json").is_file(), source)
        for omitted in (("karma_port",), ("karma_config",),
                        ("karma_config_sha256",),
                        ("karma_port", "karma_config", "karma_config_sha256")):
            with tempfile.TemporaryDirectory() as directory:
                lane, copied = self.copy_lane(source, directory)
                for module in lane["modules"].values():
                    for field in omitted:
                        module.pop(field)
                self.save_copied_lane(lane, copied)
                with self.subTest(omitted=omitted):
                    with self.assertRaises(ValueError):
                        with mock.patch("runner.candidate_identity"):
                            audit_lane_receipt(copied / "lane.json")

    def test_resealed_browser_mismatched_karma_config_is_rejected(self):
        from runner import audit_lane_receipt, sha256

        evidence_root = os.environ.get("DYN4K_BROWSER_WASI_REVIEW_EVIDENCE")
        if evidence_root is None:
            self.skipTest("set DYN4K_BROWSER_WASI_REVIEW_EVIDENCE to a full 20-lane archive")
        for lane_name, mutation in (
            ("js-chromium-minimum-production", "wrong_receipt_port"),
            ("js-chromium-minimum-production", "wrong_active_port"),
            ("js-chromium-minimum-development", "wrong_browser"),
            ("js-chromium-minimum-production", "wrong_js_input"),
            ("wasmJs-firefox-minimum-production", "wrong_wasm_loader"),
            ("js-chromium-minimum-production", "spoofed_config_comment"),
        ):
            source = Path(evidence_root) / lane_name
            self.assertTrue((source / "lane.json").is_file(), source)
            with tempfile.TemporaryDirectory() as directory:
                lane, copied = self.copy_lane(source, directory)
                module = lane["modules"]["dyn4k-core"]
                config = Path(module["karma_config"])
                content = config.read_text()
                if mutation == "wrong_receipt_port":
                    module["karma_port"] += 1
                elif mutation == "wrong_active_port":
                    port = module["karma_port"]
                    original = f"config.set({{port: {port}}});"
                    self.assertIn(original, content)
                    content = content.replace(
                        original,
                        f"config.set({{port: {port + 1}}});\n// {original}",
                    )
                elif mutation == "wrong_browser":
                    self.assertIn('"ChromeHeadless"', content)
                    content = content.replace('"ChromeHeadless"', '"FirefoxHeadless"')
                elif mutation == "wrong_js_input":
                    production = module["linked_source"]
                    self.assertIn(production, content)
                    content = content.replace(
                        production,
                        production.replace("testProductionExecutable", "testDevelopmentExecutable"),
                    )
                elif mutation == "spoofed_config_comment":
                    first_block = content.partition("config.set({")[2].partition("});")[0]
                    content = ("/* config.set({" + first_block + "}); */\n" +
                               content.replace('"ChromeHeadless"', '"FirefoxHeadless"'))
                else:
                    self.assertIn("static/load.mjs", content)
                    content = content.replace("static/load.mjs", "static/other.mjs")
                if mutation != "wrong_receipt_port":
                    config.write_text(content)
                    module["karma_config_sha256"] = sha256(config)
                self.save_copied_lane(lane, copied)
                with self.subTest(lane=lane_name, mutation=mutation):
                    with self.assertRaisesRegex(ValueError, "Karma"):
                        with mock.patch("runner.candidate_identity"):
                            audit_lane_receipt(copied / "lane.json")

    def test_browser_port_configuration_is_isolated_and_removed(self):
        from runner import isolated_karma_port

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reporter = Path(__file__).with_name("browser-karma-reporter.js")
            with isolated_karma_port(root, reporter) as port:
                source = root / "karma.config.d/qualification-port.js"
                self.assertIn(f"port: {port}", source.read_text())
                self.assertGreater(port, 0)
            self.assertFalse((root / "karma.config.d").exists())

    def test_existing_failed_lane_is_not_overwritten(self):
        from runner import run_lane

        with tempfile.TemporaryDirectory() as directory:
            lane_dir = Path(directory) / "failed-lane"
            lane_dir.mkdir()
            receipt = lane_dir / "lane.json"
            receipt.write_text('{"status":"FAILED","reason":"world unavailable"}\n')
            before = receipt.read_bytes()
            self.assertEqual(1, run_lane(Path(directory), "wrong-sha", receipt, lane_dir,
                                         "js", "chromium", "minimum", "development",
                                         Path(directory) / "missing-chrome", "119.0.6045.105"))
            self.assertEqual(before, receipt.read_bytes())

    def test_wasmtime_requires_finished_physics_case(self):
        expected = {("sample.WorldTest", "collides")}
        started = (
            "##teamcity[testSuiteStarted name='sample']\n"
            "##teamcity[testSuiteStarted name='WorldTest']\n"
            "##teamcity[testStarted name='collides']\n"
        )
        with self.assertRaisesRegex(ValueError, "unfinished"):
            verify_wasmtime_output(started, expected)
        finished = (
            started
            + "##teamcity[testFinished name='collides']\n"
            + "##teamcity[testSuiteFinished name='WorldTest']\n"
            + "##teamcity[testSuiteFinished name='sample']\n"
        )
        self.assertEqual(1, verify_wasmtime_output(finished, expected)["executed"])

    def test_wasmtime_production_selects_binaryen_output_task(self):
        self.assertEqual(
            ":dyn4k-core:compileTestProductionExecutableKotlinWasmWasiOptimize",
            gradle_test_task("dyn4k-core", "wasmWasi", "production"),
        )
        self.assertEqual(
            ":compileTestDevelopmentExecutableKotlinWasmWasi",
            gradle_test_task("consumer", "wasmWasi", "development"),
        )

    def test_runtime_selection_rejects_wrong_binary_and_role(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "browser"
            binary.write_text("#!/bin/sh\nprintf 'Mozilla Firefox 120.0.1\\n'\n")
            os.chmod(binary, 0o755)
            self.assertEqual(
                "Mozilla Firefox 120.0.1",
                runtime_version(binary, "js", "firefox", "120.0.1", "minimum"),
            )
            with self.assertRaisesRegex(ValueError, "pinned matrix"):
                runtime_version(binary, "js", "firefox", "120.0.1", "current")
            with self.assertRaisesRegex(ValueError, "wrong runtime binary"):
                runtime_version(binary, "js", "chromium", "119.0.6045.105", "minimum")

    def test_missing_staged_publication_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "LICENSE.md").write_text("test license\n")
            with self.assertRaisesRegex(ValueError, "missing staged artifact"):
                staged_files(Path(directory))

if __name__ == "__main__":
    unittest.main()
