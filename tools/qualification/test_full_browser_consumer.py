import unittest
import xml.etree.ElementTree as ET
import json
import subprocess
import tempfile
from pathlib import Path
from unittest import mock

import full_browser_consumer as browser


class BrowserRowsTest(unittest.TestCase):
    def setUp(self):
        self.selected = {("org.dyn4j.SampleTest", "first"): "core:first",
                         ("org.dyn4j.SampleTest", "second"): "core:second"}

    def xml(self, names, tests=None, failures=0, skipped=0):
        suite = ET.Element("testsuite", {"name": "jsBrowserTest.org.dyn4j.SampleTest",
                                         "tests": str(len(names) if tests is None else tests),
                                         "failures": str(failures), "errors": "0",
                                         "skipped": str(skipped), "time": "0.25"})
        for name in names:
            ET.SubElement(suite, "testcase", {
                "classname": "jsBrowserTest.org.dyn4j.SampleTest",
                "name": f"{name}[js, browser, ChromeHeadless155.0.0.0, Linux0.0.0]",
                "time": "0.01"})
        return suite

    def test_original_order_is_preserved(self):
        suite = self.xml(["second", "first"])
        self.assertEqual(browser.rows(ET.tostring(suite), self.selected, 155),
                         ["core:second", "core:first"])

    def test_duplicate_method_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicates"):
            browser.rows(ET.tostring(self.xml(["first", "first"])), self.selected, 155)

    def test_foreign_method_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "foreign"):
            browser.rows(ET.tostring(self.xml(["first", "foreign"])), self.selected, 155)

    def test_wrong_chromium_version_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "runtime"):
            browser.rows(ET.tostring(self.xml(["first"])), self.selected, 119)

    def test_missing_count_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            browser.rows(ET.tostring(self.xml(["first"], tests=2)), self.selected, 155)

    def test_failing_and_skipped_rows_are_rejected(self):
        failed = self.xml(["first"], failures=1)
        failed[0].append(ET.Element("failure"))
        with self.assertRaisesRegex(ValueError, "failing"):
            browser.rows(ET.tostring(failed), self.selected, 155)
        skipped = self.xml(["first"], skipped=1)
        skipped[0].append(ET.Element("skipped"))
        with self.assertRaisesRegex(ValueError, "skipped"):
            browser.rows(ET.tostring(skipped), self.selected, 155)

    def test_missing_nonfinite_and_negative_xml_durations_are_rejected(self):
        for target in ("suite", "case"):
            for value in (None, "NaN", "Infinity", "-1", "-0.0"):
                with self.subTest(target=target, value=value):
                    suite = self.xml(["first"])
                    element = suite if target == "suite" else suite[0]
                    if value is None:
                        del element.attrib["time"]
                    else:
                        element.set("time", value)
                    with self.assertRaisesRegex(ValueError, "duration"):
                        browser.rows(ET.tostring(suite), self.selected, 155)

    def test_input_map_rejects_duplicate_and_malformed_rows(self):
        with self.assertRaisesRegex(ValueError, "differs"):
            browser.selected_map(b"a\tA\tm\na\tA\tm\n")
        with self.assertRaisesRegex(ValueError, "differs"):
            browser.selected_map(b"a\tA\n")

    def karma(self, methods):
        suite = "org.dyn4j SampleTest.Chrome Headless 155.0.0.0 (Linux 0.0.0)"
        flow = "karmaTC123"
        messages = [f"##teamcity[testSuiteStarted name='{suite}' flowId='{flow}']"]
        for method in methods:
            messages.extend((
                f"##teamcity[testStarted name='{method}' captureStandardOutput='true' flowId='{flow}']",
                f"##teamcity[testFinished name='{method}' duration='' flowId='{flow}']"))
        messages.append(f"##teamcity[testSuiteFinished name='{suite}' duration='%s' flowId='{flow}']")
        return b"".join((json.dumps({"sha256": browser.sha(message.encode()),
                                     "message": message}) + "\n").encode()
                        for message in messages)

    def test_raw_karma_methods_are_replayed(self):
        self.assertEqual(browser.karma_rows(self.karma(["second", "first"]),
                                            self.selected, 155),
                         ["core:second", "core:first"])

    def test_raw_karma_rejects_missing_duplicate_and_foreign_methods(self):
        for methods in (["first"], ["first", "first"], ["first", "foreign"]):
            with self.subTest(methods=methods), self.assertRaises(ValueError):
                browser.karma_rows(self.karma(methods), self.selected, 155)

    def test_raw_karma_rejects_wrong_runtime(self):
        with self.assertRaisesRegex(ValueError, "suite start"):
            browser.karma_rows(self.karma(["first", "second"]), self.selected, 119)


class SelectedBundleTest(unittest.TestCase):
    middle = b");\nconfig.set({webpack: createWebpackConfig()});\n\n"
    reporter = b"const reviewedReporter = true;\n"
    port = 34567

    def settings(self, work, mode):
        _, selected, runner = browser.bundle_paths(work, "core", mode)
        paths = [str(runner), str(selected)]
        return {"singleRun": True, "autoWatch": False,
                "basePath": str(work / "root/js/packages" /
                                "dyn4k-full-staged-browser-consumer-core-test"),
                "files": paths, "frameworks": ["webpack-output", "mocha", "webpack"],
                "client": {"args": []}, "browsers": ["ChromeHeadless"],
                "customLaunchers": {}, "failOnFailingTestSuite": False,
                "failOnEmptyTestSuite": False, "reporters": ["karma-kotlin-reporter"],
                "preprocessors": {path: ["webpack", "sourcemap"] for path in paths},
                "proxies": {}, "webpackCopy": []}

    def config(self, settings):
        return (browser.KARMA_HEADER + json.dumps(settings).encode() + self.middle
                + browser.KARMA_REPORTER_MARKER + self.reporter
                + f"\n\n// qualification-port.js\nconfig.set({{port: {self.port}}});\n\n\n\n\n}}\n".encode())

    def test_configured_paths_and_later_overrides(self):
        work = Path("/evidence/build")
        with mock.patch.object(browser, "KARMA_GENERATED_MIDDLE_SHA256", browser.sha(self.middle)):
            for mode in ("development", "production"):
                with self.subTest(mode=mode):
                    settings = self.settings(work, mode)
                    raw = self.config(settings)
                    self.assertEqual(browser.configured_bundle(raw, work, "core", mode,
                                                               self.reporter, self.port),
                                     browser.bundle_paths(work, "core", mode)[:2])
                    for override in (b"config.set({files: [runner, selected, '/tmp/extra.js']});\n",
                                     b"config.set({preprocessors: {'/tmp/extra.js': ['webpack']}});\n"):
                        for marker in (browser.KARMA_REPORTER_MARKER,
                                       b"// qualification-port.js"):
                            changed = raw.replace(marker, override + marker)
                            with self.subTest(override=override, marker=marker), self.assertRaisesRegex(
                                    ValueError, "later override"):
                                browser.configured_bundle(changed, work, "core", mode,
                                                          self.reporter, self.port)
                    settings["files"].append("/tmp/untracked-injection.js")
                    with self.assertRaisesRegex(ValueError, "selected bundle path"):
                        browser.configured_bundle(self.config(settings), work, "core", mode,
                                                  self.reporter, self.port)

    def test_effective_files_reject_extra_script_and_changed_preprocessor(self):
        work = Path("/evidence/build")
        tmpdir = "/evidence/tmp"
        webpack = Path(tmpdir) / "_karma_webpack_123"
        _, selected, runner = browser.bundle_paths(work, "core", "development")
        root = work / "root/js/node_modules"
        evidence = {"tmpdir": tmpdir,
                    "effective_files": [{"pattern": path, "served": True,
                                         "included": index != 6, "watched": False,
                                         "nocache": False,
                                         "type": None}
                                        for index, path in enumerate((
                                            str(webpack / "runtime.js"),
                                            str(webpack / "commons.js"),
                                            str(root / "mocha/mocha.js"),
                                            str(root / "karma-mocha/lib/adapter.js"),
                                            str(runner), str(selected),
                                            str(webpack / "**/*")))],
                    "effective_preprocessors": {str(path): ["webpack", "sourcemap"]
                                                for path in (runner, selected)},
                    "input_sha256": {str(root / name): digest for name, digest
                                     in browser.RUNTIME_INPUT_SHA256.items()}}
        browser.effective_files(evidence, work, "core", "development")
        evidence["effective_files"].insert(5, {**evidence["effective_files"][5],
                                                 "pattern": "/tmp/untracked-injection.js"})
        with self.assertRaisesRegex(ValueError, "effective file list"):
            browser.effective_files(evidence, work, "core", "development")
        evidence["effective_files"].pop(5)
        evidence["effective_preprocessors"][str(selected)] = ["sourcemap"]
        with self.assertRaisesRegex(ValueError, "preprocessors"):
            browser.effective_files(evidence, work, "core", "development")

    def test_effective_pattern_flags_reject_changed_selected_script(self):
        work = Path("/evidence/build")
        webpack = Path("/evidence/tmp/_karma_webpack_123")
        _, selected, runner = browser.bundle_paths(work, "core", "development")
        root = work / "root/js/node_modules"
        paths = [str(webpack / "runtime.js"), str(webpack / "commons.js"),
                 str(root / "mocha/mocha.js"), str(root / "karma-mocha/lib/adapter.js"),
                 str(runner), str(selected), str(webpack / "**/*")]
        evidence = {"tmpdir": str(webpack.parent),
                    "effective_files": [{"pattern": path, "served": True,
                                         "included": index != 6, "watched": False,
                                         "nocache": False,
                                         "type": None}
                                        for index, path in enumerate(paths)],
                    "effective_preprocessors": {str(path): ["webpack", "sourcemap"]
                                                for path in (runner, selected)},
                    "input_sha256": {str(root / name): digest for name, digest
                                     in browser.RUNTIME_INPUT_SHA256.items()}}
        browser.effective_files(evidence, work, "core", "development")
        for field, changed in (("included", False), ("served", False),
                               ("watched", True), ("nocache", None),
                               ("type", "module"), ("included", 1)):
            with self.subTest(field=field, changed=changed):
                original = evidence["effective_files"][5][field]
                evidence["effective_files"][5][field] = changed
                with self.assertRaisesRegex(ValueError, "effective files"):
                    browser.effective_files(evidence, work, "core", "development")
                evidence["effective_files"][5][field] = original

    def test_reporter_node_vm_rejects_unserved_or_excluded_selected_script(self):
        script = "\n".join((
            "const assert = require('node:assert/strict');",
            "const fs = require('node:fs');",
            "const path = require('node:path');",
            "const vm = require('node:vm');",
            "const source = fs.readFileSync(process.argv[1], 'utf8');",
            "const work = '/evidence/build';",
            "const root = path.join(work, 'root/js/node_modules');",
            "const tmpdir = '/evidence/tmp';",
            "const webpack = path.join(tmpdir, '_karma_webpack_123');",
            "const selected = path.join(work, 'root/js/packages/test/kotlin/test.js');",
            "const runner = path.join(root, 'kotlin-web-helpers/dist/kotlin-test-karma-runner.js');",
            "const paths = [path.join(webpack, 'runtime.js'), path.join(webpack, 'commons.js'),",
            "    path.join(root, 'mocha/mocha.js'), path.join(root, 'karma-mocha/lib/adapter.js'),",
            "    runner, selected, path.join(webpack, '**/*')];",
            "const digests = new Map([",
            "    ['karma-kotlin-reporter.js', '7c3232f60952aff254847ae62a866385735e3094197454d755100e962c2f2347'],",
            "    ['mocha.js', '8f46c07ab4422da71bdb27e8f54d0a9ba59b736face2c9f5534c414623c55ef6'],",
            "    ['adapter.js', 'd2ecb1de057231e7c5efe6b7a5b36e163c85f49834814ab8fc3a893a3a404933'],",
            "    ['kotlin-test-karma-runner.js', '15261c8d909c161dfc3004934d1f2542f96abcb78071b6f3663aa927773aba18'],",
            "    ['config.js', 'fadd8d4cef5e4d62dcd9a5ccd63295ceb028925a5d2f8b7edfb1d47a09fb7e42'],",
            "    ['helper.js', 'db2c4942bde7e0d696a40d1a1a7b58ba18b9acc3843c53a8a336c86645d5de6f'],",
            "    ['file-list.js', 'b91c1f294a2f1fbd886a8d3b991c8066c70037319a8e71d97a549b0928eefc22'],",
            "    ['index.js', '4e9a83d5ff0504ad8d2ea42ee535d5e05324b2e4e8f1796b809c8314b1cc524b'],",
            "    ['framework.js', '705fc7f4d211eee26beb549758d8ea39f502a7385c2a43756bc71e3003c99ca9'],",
            "    ['preprocessor.js', '6af7525c470abcc69165a9732bf492b4524201525183eeef55998940f3f802c6'],",
            "    ['karma-webpack-output.js', '7accb6fbba4ce0082f6e8ae2ca165eb9dd3c6dcfed0dfb2a8ba2e9aaa43061c7']",
            "]);",
            "const fakeFs = {readFileSync: name => Buffer.from(name), realpathSync: name => name,",
            "    writeFileSync: () => {}, openSync: () => 1};",
            "const fakeCrypto = {createHash: () => ({update(data) {this.name = data.toString(); return this;},",
            "    digest() {return digests.get(path.basename(this.name)) || '0'.repeat(64);}})};",
            "function fakeRequire(name) {",
            "    if (name === 'node:fs') return fakeFs;",
            "    if (name === 'node:crypto') return fakeCrypto;",
            "    if (name === 'node:path') return path;",
            "    if (name === 'karma/lib/config') return {createPatternObject: file =>",
            "        ({...file, nocache: file.nocache === undefined ? false : file.nocache})};",
            "    throw Error(name);",
            "}",
            "fakeRequire.resolve = () => path.join(root,",
            "    'kotlin-web-helpers/dist/karma-kotlin-reporter.js');",
            "function OriginalReporter() {",
            "    this.write = () => {};",
            "    this.onBrowserStart = () => {};",
            "    this.onRunComplete = () => {};",
            "}",
            "OriginalReporter.$inject = [];",
            "const key = 'reporter:karma-kotlin-reporter';",
            "const config = {plugins: [{[key]: ['type', OriginalReporter]}],",
            "    files: paths.map((pattern, index) => ({pattern, served: true,",
            "        included: index !== 6, watched: false,",
            "        ...(index === 4 || index === 5 ? {nocache: false} : {})})),",
            "    preprocessors: {[runner]: ['webpack', 'sourcemap'],",
            "        [selected]: ['webpack', 'sourcemap']}};",
            "const env = {DYN4K_BROWSER_REPORTER_SOURCE: '/evidence/reporter.js',",
            "    DYN4K_BROWSER_REPORTER_ATTESTATION: '/evidence/reporter.json',",
            "    DYN4K_BROWSER_RAW_KARMA: '/evidence/raw.jsonl',",
            "    DYN4K_BROWSER_SELECTED_BUNDLE: selected,",
            "    DYN4K_BROWSER_SELECTED_ARCHIVE: '/evidence/selected.js',",
            "    DYN4K_BROWSER_SELECTED_ATTESTATION: '/evidence/selected.json',",
            "    DYN4K_BROWSER_WORK_ROOT: work, DYN4K_BROWSER_TMPDIR: tmpdir};",
            "vm.runInNewContext(source, {config, require: fakeRequire, process: {env, pid: 12}, Buffer});",
            "const Reporter = config.plugins[0][key][1];",
            "assert.doesNotThrow(() => new Reporter(null, config, null));",
            "for (const field of ['included', 'served']) {",
            "    config.files[5][field] = false;",
            "    assert.throws(() => new Reporter(null, config, null), /effective files/);",
            "    config.files[5][field] = true;",
            "}",
        ))
        reporter = Path(__file__).resolve().parents[2] / browser.REPORTER
        completed = subprocess.run(["node", "-e", script, str(reporter)],
                                   check=False, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_resealed_selected_copy_must_match_linked_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            work = folder / "build"
            linked, selected, runner = browser.bundle_paths(work, "core", "development")
            config = self.settings(work, "development")
            (folder / "karma.conf.js").write_bytes(self.config(config))
            (folder / "browser-reporter.js").write_bytes(self.reporter)
            (folder / "linked-executable.js").write_bytes(b"linked bytes")
            (folder / "karma-selected.js").write_bytes(b"different selected bytes")
            evidence = {"source_path": str(selected), "archive_path": str(folder / "karma-selected.js"),
                        "sha256": browser.sha(b"different selected bytes"), "node_pid": 123,
                        "browser_id": "browser-id", "browser_name": "Chrome Headless 155.0.0.0 (Linux 0.0.0)",
                        "captured_ns": 2, "complete_ns": 3}
            (folder / "selected-bundle.json").write_text(json.dumps(evidence))
            record = {"started_ns": 1, "finished_ns": 4,
                      "linked_sha256": browser.sha(b"linked bytes"), "karma_port": self.port}
            with mock.patch.object(browser, "KARMA_GENERATED_MIDDLE_SHA256",
                                   browser.sha(self.middle)):
                with self.assertRaisesRegex(ValueError, "selected bundle bytes"):
                    browser.selected_bundle(folder, work, "core", "development", record, 155)


if __name__ == "__main__":
    unittest.main()
