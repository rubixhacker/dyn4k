import unittest
import xml.etree.ElementTree as ET
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

import full_browser_consumer as browser


class SafariLauncherTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[2] / (
            "consumers/qualification/portable/full-browser/safari_launcher.py")
        spec = importlib.util.spec_from_file_location("full_browser_safari_launcher", path)
        cls.launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.launcher)

    def test_launchservices_waits_for_a_new_selected_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected = root / "Safari.app/Contents/MacOS/Safari"
            selected.parent.mkdir(parents=True)
            selected.write_bytes(b"selected Safari")
            record = root / "launches.jsonl"
            redirect = root / "redirect.html"
            redirect.write_text("redirect")
            env = {"DYN4K_BROWSER_SELECTED_BINARY": str(selected),
                   "DYN4K_BROWSER_ATTESTATION": str(record),
                   "DYN4K_BROWSER_TOKEN": "test-token"}
            with mock.patch.dict(os.environ, env), mock.patch.object(
                    sys, "argv", ["safari_launcher.py", str(redirect)]), mock.patch.object(
                    self.launcher, "safari_pids", return_value={17}), mock.patch.object(
                    self.launcher.os, "fork", return_value=1), mock.patch.object(
                    self.launcher.os, "execv") as execv:
                self.launcher.main()
            execv.assert_called_once_with("/usr/bin/open", [
                "/usr/bin/open", "-n", "-W", "-a", str(selected.parents[2]),
                str(redirect)])

    def test_observer_records_only_new_selected_safari_pid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected = root / "Safari"
            selected.write_bytes(b"selected Safari")
            record = root / "launches.jsonl"
            with mock.patch.object(self.launcher, "safari_pids", return_value={17, 19}), \
                    mock.patch.object(self.launcher, "image_path", return_value=selected):
                self.launcher.observe({17}, selected, record, "test-token")
            row = json.loads(record.read_text())
            self.assertEqual(row["pid"], 19)
            self.assertEqual(row["process_sha256"], browser.sha(b"selected Safari"))


class ToolchainPinTest(unittest.TestCase):
    def test_safari_uses_darwin_jdk_pin(self):
        self.assertEqual(browser.expected_java_sha256("Darwin", "Safari"),
                         "9be1d0a740ff6502df1a762145e62860f5de4b7e17658d9cb9498da3acf9d16c")
        self.assertEqual(browser.expected_java_sha256("Linux", "Chromium"),
                         browser.JAVA_SHA256)
        with self.assertRaisesRegex(ValueError, "browser host differs"):
            browser.expected_java_sha256("Linux", "Safari")
        with self.assertRaisesRegex(ValueError, "browser host differs"):
            browser.expected_java_sha256("Windows", "Safari")


class ArchiveLocationTest(unittest.TestCase):
    def test_relocated_copy_keeps_observed_capture_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "checkout"
            repository.mkdir()
            observed = root / "observed"
            observed.mkdir()
            (observed / "raw.txt").write_bytes(b"original observation")
            relocated = root / "relocated"
            shutil.copytree(observed, relocated, copy_function=shutil.copy2)
            paths = {"checkout": str(repository), "archive": str(observed),
                     "staging": str(root / "staging"), "inputs": str(root / "inputs"),
                     "work": str(root / "work")}
            self.assertEqual(browser.capture_archive_root(paths, relocated, repository),
                             observed)
            self.assertEqual(browser.capture_archive_root(paths, observed, repository),
                             observed)
            alias = root / "alias"
            alias.symlink_to(relocated, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "archive path"):
                browser.capture_archive_root(paths, alias, repository)
            with self.assertRaisesRegex(ValueError, "archive path"):
                browser.capture_archive_root(paths, relocated / ".." / "relocated",
                                             repository)
            linked = root / "hardlinked"
            linked.mkdir()
            os.link(observed / "raw.txt", linked / "raw.txt")
            with self.assertRaisesRegex(ValueError, "hardlink"):
                browser.capture_archive_root(paths, linked, repository)


class LiveYarnLockTest(unittest.TestCase):
    def test_mutation_after_graph_is_rejected_and_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive"
            archive.mkdir()
            lock = root / "yarn.lock"
            lock.write_bytes(b"committed lock\n")
            graph = {"pid": 11, "finished_ns": time.time_ns() - 1_000_000}
            graph_record = browser.capture_live_lock(
                lock, b"committed lock\n", archive, "graph", graph)
            self.assertEqual(graph_record["sha256"], browser.sha(b"committed lock\n"))
            lock.write_bytes(b"changed during resolution\n")
            core = {"pid": 12, "finished_ns": time.time_ns() - 1_000_000}
            with self.assertRaisesRegex(ValueError, "live Yarn lock differs"):
                browser.capture_live_lock(lock, b"committed lock\n", archive,
                                          "core", core)
            self.assertEqual((archive / "lock-observations/core.yarn.lock").read_bytes(),
                             b"changed during resolution\n")
            self.assertTrue((archive / "lock-observations/core.json").is_file())

    def test_public_replay_requires_each_process_bound_lock_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive"
            archive.mkdir()
            lock = root / "yarn.lock"
            fixture = b"committed lock\n"
            lock.write_bytes(fixture)
            started = time.time_ns() - 1_000_000
            processes = {}
            observations = []
            for stage, pid in (("graph", 11), ("core", 12), ("facade", 13)):
                process = {"pid": pid, "started_ns": started,
                           "finished_ns": time.time_ns()}
                processes[stage] = process
                observations.append(browser.capture_live_lock(
                    lock, fixture, archive, stage, process))
                started = time.time_ns()
            receipt = {"schema": 2, "lock_observations": observations,
                       "process": {"started_ns": processes["graph"]["started_ns"],
                                   "finished_ns": time.time_ns(),
                                   "graph": processes["graph"]},
                       "modules": {"core": processes["core"],
                                   "facade": processes["facade"]}}
            browser.verify_live_lock_observations(archive, receipt, fixture, lock)
            (archive / "lock-observations/core.yarn.lock").write_bytes(b"resealed")
            with self.assertRaisesRegex(ValueError, "live Yarn lock"):
                browser.verify_live_lock_observations(archive, receipt, fixture, lock)
            (archive / "lock-observations/core.yarn.lock").write_bytes(fixture)
            receipt["lock_observations"] = [observations[0],
                                            {**observations[1], "observed_ns": 0},
                                            observations[2]]
            with self.assertRaisesRegex(ValueError, "live Yarn lock"):
                browser.verify_live_lock_observations(archive, receipt, fixture, lock)
            receipt["lock_observations"] = observations[:2]
            with self.assertRaisesRegex(ValueError, "live Yarn lock"):
                browser.verify_live_lock_observations(archive, receipt, fixture, lock)


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

    def test_approved_browser_matrix_has_all_24_routes(self):
        self.assertEqual(len(browser.LANES), 24)
        for target in ("js", "wasmJs"):
            for family in ("Chromium", "Firefox", "Safari"):
                for role in ("minimum", "current"):
                    for mode in ("development", "production"):
                        self.assertIn(f"{target}:{family}:{role}:{mode}", browser.LANES)

    def test_target_lock_fixture_is_selected_from_candidate(self):
        selected = []
        def original(_, candidate, path):
            selected.append((candidate, path))
            return b"locked"
        with mock.patch.object(browser, "contract", return_value={"cases": []}), \
                mock.patch.object(browser, "source_inventory", return_value={}), \
                mock.patch.object(browser, "original", side_effect=original):
            browser.input_bytes(Path("/source"), "f" * 40,
                                "js:Firefox:current:development")
            browser.input_bytes(Path("/source"), "f" * 40,
                                "wasmJs:Chromium:current:development")
            browser.input_bytes(Path("/source"), browser.LEGACY_CANDIDATE_SHA,
                                "js:Chromium:current:development")
        self.assertEqual([path for _, path in selected],
                         [browser.MULTI_BROWSER_YARN_LOCK,
                          browser.WASM_YARN_LOCK, browser.YARN_LOCK])

    def test_firefox_and_wasm_rows_bind_target_family_and_version(self):
        for target, family, major in (("js", "Firefox", 158),
                                      ("wasmJs", "Chromium", 155),
                                      ("wasmJs", "Firefox", 120)):
            with self.subTest(target=target, family=family):
                suite = self.xml(["first", "second"])
                suite.set("name", f"{target}BrowserTest.org.dyn4j.SampleTest")
                label = "ChromeHeadless" if family == "Chromium" else family
                for case in suite:
                    case.set("classname", f"{target}BrowserTest.org.dyn4j.SampleTest")
                    case.set("name", f"{case.get('name').split('[')[0]}"
                             f"[{target}, browser, {label}{major}.0, Linux0.0.0]")
                self.assertEqual(browser.rows(ET.tostring(suite), self.selected, major,
                                              target, family),
                                 ["core:first", "core:second"])
                with self.assertRaisesRegex(ValueError, "runtime"):
                    browser.rows(ET.tostring(suite), self.selected, major + 1,
                                 target, family)

    def test_firefox_process_image_must_match_selected_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            selected = Path(directory) / "firefox"
            selected.write_bytes(b"selected")
            item = {"token": "token", "runtime": "firefox",
                    "selected_binary": str(selected),
                    "selected_sha256": browser.sha(b"selected"),
                    "process_executable": str(selected),
                    "process_sha256": browser.sha(b"selected"), "pid": 12}
            self.assertTrue(browser.observed_browser(
                item, "token", "Firefox", selected, browser.sha(b"selected")))
            for key, value in (("runtime", "chromium"),
                               ("selected_sha256", browser.sha(b"changed")),
                               ("process_executable", str(Path(directory) / "foreign")),
                               ("pid", 0)):
                changed = {**item, key: value}
                self.assertFalse(browser.observed_browser(
                    changed, "token", "Firefox", selected, browser.sha(b"selected")))


class SelectedBundleTest(unittest.TestCase):
    middle = b");\nconfig.set({webpack: createWebpackConfig()});\n\n"
    reporter = b"const reviewedReporter = true;\n"
    port = 34567

    def settings(self, work, mode, target="js", family="Chromium"):
        tooling = (Path.home() / ".kotlin/kotlin-npm-tooling/yarn/"
                   "9c7852378f220e63c4f92e7d93026c2f/node_modules/"
                   "kotlin-web-helpers/dist/kotlin-test-karma-runner.js")
        _, selected, runner = browser.bundle_paths(
            work, "core", mode, target, tooling if target == "wasmJs" else None)
        paths = [str(runner), str(selected)]
        result = {"singleRun": True, "autoWatch": False,
                "basePath": str(work / "root" / ("js" if target == "js" else "wasm") / "packages" /
                                "dyn4k-full-staged-browser-consumer-core-test"),
                "files": paths, "frameworks": ["webpack-output", "mocha", "webpack"],
                "client": {"args": []},
                "browsers": [{"Chromium": "ChromeHeadless", "Firefox": "FirefoxHeadless",
                              "Safari": "Safari"}[family]],
                "customLaunchers": {}, "failOnFailingTestSuite": False,
                "failOnEmptyTestSuite": False, "reporters": ["karma-kotlin-reporter"],
                "preprocessors": {path: ["webpack", "sourcemap"] for path in paths},
                "proxies": {}, "webpackCopy": []}
        if target == "wasmJs":
            result["customContextFile"] = str(runner.parent / "static/context.html")
            result["customDebugFile"] = str(runner.parent / "static/debug.html")
        return result

    def test_other_browser_karma_config_and_bundle_selection(self):
        work = Path("/evidence/build")
        with mock.patch.object(browser, "KARMA_GENERATED_MIDDLE_SHA256",
                               browser.sha(self.middle)), mock.patch.object(
                                   browser, "WASM_KARMA_GENERATED_MIDDLE_SHA256",
                                   browser.sha(self.middle)):
            for target, family in (("js", "Firefox"), ("js", "Safari"),
                                   ("wasmJs", "Chromium"), ("wasmJs", "Firefox"),
                                   ("wasmJs", "Safari")):
                for mode in ("development", "production"):
                    with self.subTest(target=target, family=family, mode=mode):
                        settings = self.settings(work, mode, target, family)
                        linked, selected = browser.configured_bundle(
                            self.config(settings), work, "core", mode, self.reporter,
                            self.port, target, family)
                        self.assertEqual(selected, browser.bundle_paths(
                            work, "core", mode, target,
                            Path(settings["files"][0]) if target == "wasmJs" else None)[1])
                        self.assertEqual(linked.suffix, ".js" if target == "js" else ".mjs")
                        settings["browsers"] = ["ChromeHeadless"] if family != "Chromium" else ["FirefoxHeadless"]
                        with self.assertRaisesRegex(ValueError, "selected bundle"):
                            browser.configured_bundle(self.config(settings), work, "core",
                                                      mode, self.reporter, self.port,
                                                      target, family)

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
                                         "type": None, "isBinary": None}
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
                 str(root.resolve() / "mocha/mocha.js"),
                 str(root.resolve() / "karma-mocha/lib/adapter.js"),
                 str(runner), str(selected), str(webpack / "**/*")]
        evidence = {"tmpdir": str(webpack.parent),
                    "effective_files": [{"pattern": path, "served": True,
                                         "included": index != 6, "watched": False,
                                         "nocache": False,
                                         "type": None, "isBinary": None}
                                        for index, path in enumerate(paths)],
                    "effective_preprocessors": {str(path): ["webpack", "sourcemap"]
                                                for path in (runner, selected)},
                    "input_sha256": {str(root / name): digest for name, digest
                                     in browser.RUNTIME_INPUT_SHA256.items()}}
        browser.effective_files(evidence, work, "core", "development")
        for field, changed in (("included", False), ("served", False),
                               ("watched", True), ("nocache", None),
                               ("type", "module"), ("isBinary", True),
                               ("isBinary", False), ("included", 1)):
            with self.subTest(field=field, changed=changed):
                original = evidence["effective_files"][5][field]
                evidence["effective_files"][5][field] = changed
                with self.assertRaisesRegex(ValueError, "effective files"):
                    browser.effective_files(evidence, work, "core", "development")
                evidence["effective_files"][5][field] = original
        del evidence["effective_files"][5]["isBinary"]
        with self.assertRaisesRegex(ValueError, "effective file list"):
            browser.effective_files(evidence, work, "core", "development")

    def test_wasm_effective_patterns_pin_loader_and_tooling(self):
        work = Path("/evidence/build")
        tmpdir = Path("/evidence/tmp")
        runner = (Path.home() / ".kotlin/kotlin-npm-tooling/yarn/"
                  "9c7852378f220e63c4f92e7d93026c2f/node_modules/"
                  "kotlin-web-helpers/dist/kotlin-test-karma-runner.js")
        _, selected, _ = browser.bundle_paths(work, "core", "development",
                                               "wasmJs", runner)
        root = runner.parents[2]
        webpack = tmpdir / "_karma_webpack_456"
        paths = [str(webpack / "runtime.js"), str(webpack / "commons.js"),
                 str(root.resolve() / "mocha/mocha.js"),
                 str(root.resolve() / "karma-mocha/lib/adapter.js"),
                 str(runner), str(selected), str(webpack / "**/*")]
        evidence = {"tmpdir": str(tmpdir),
                    "effective_files": [{"pattern": path, "served": True,
                                         "included": index != 6, "watched": False,
                                         "nocache": False, "type": None, "isBinary": None}
                                        for index, path in enumerate(paths)],
                    "effective_preprocessors": {str(path): ["webpack", "sourcemap"]
                                                for path in (runner, selected)},
                    "input_sha256": {str(root / name): digest for name, digest
                                     in browser.WASM_INPUT_SHA256.items()}}
        browser.effective_files(evidence, work, "core", "development", "wasmJs")
        for field, changed in (("served", False), ("included", False),
                               ("isBinary", True), ("pattern", "/evidence/foreign.mjs")):
            with self.subTest(field=field):
                original = evidence["effective_files"][5][field]
                evidence["effective_files"][5][field] = changed
                with self.assertRaisesRegex(ValueError, "effective files"):
                    browser.effective_files(evidence, work, "core", "development", "wasmJs")
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
            "const fakeFs = {readFileSync: name => Buffer.from(name), realpathSync: name => name, mkdirSync: () => {},",
            "    writeFileSync: () => {}, openSync: () => 1};",
            "const fakeCrypto = {createHash: () => ({update(data) {this.name = data.toString(); return this;},",
            "    digest() {return this.name.endsWith('/karma/lib/preprocessor.js')",
            "        ? '0ad9180342ad37e9a1782105a98df0b60225598fd5ccd66016fd90fbb49230f5'",
            "        : digests.get(path.basename(this.name)) || '0'.repeat(64);}})};",
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
            "const config = {plugins: [{[key]: ['type', OriginalReporter]}], set: () => {},",
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
            "assert.equal(config.plugins[1]['middleware:qualification-response'][1].$inject.length, 0);",
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

    def test_reporter_real_karma_pattern_rejects_binary_selected_script(self):
        cache = Path("/var/home/stewart/dyn4k-evidence/session-control/"
                     "full-browser-f565-review-findings-sol-current-development-attempt3-build")
        reporter = Path(__file__).resolve().parents[2] / browser.REPORTER
        script = "\n".join((
            "const assert = require('node:assert/strict');",
            "const crypto = require('node:crypto');",
            "const fs = require('node:fs');",
            "const path = require('node:path');",
            "const vm = require('node:vm');",
            "const {createRequire} = require('node:module');",
            "const source = fs.readFileSync(process.argv[1], 'utf8');",
            "const work = process.argv[2];",
            "const root = path.join(work, 'root/js/node_modules');",
            "const karma = createRequire(path.join(root, 'karma/package.json'))('karma/lib/config');",
            "const tmpdir = process.env.TMPDIR;",
            "const webpack = path.join(tmpdir, '_karma_webpack_123');",
            "const name = 'dyn4k-full-staged-browser-consumer-core-test';",
            "const selected = path.join(work, 'root/js/packages', name, 'kotlin', name + '.js');",
            "const runner = path.join(root, 'kotlin-web-helpers/dist/kotlin-test-karma-runner.js');",
            "const paths = [path.join(webpack, 'runtime.js'), path.join(webpack, 'commons.js'),",
            "    path.join(root, 'mocha/mocha.js'), path.join(root, 'karma-mocha/lib/adapter.js'),",
            "    runner, selected, path.join(webpack, '**/*')];",
            "const files = paths.map((pattern, index) => {",
            "    if (index === 4 || index === 5) {",
            "        const file = karma.createPatternObject(pattern);",
            "        file.watched = false;",
            "        return file;",
            "    }",
            "    return {pattern, served: true, included: index !== 6, watched: false};",
            "});",
            "function OriginalReporter() {",
            "    this.write = () => {};",
            "    this.onBrowserStart = () => {};",
            "    this.onRunComplete = () => {};",
            "}",
            "OriginalReporter.$inject = [];",
            "const key = 'reporter:karma-kotlin-reporter';",
            "const config = {plugins: [{[key]: ['type', OriginalReporter]}], files, set: () => {},",
            "    preprocessors: {[runner]: ['webpack', 'sourcemap'],",
            "        [selected]: ['webpack', 'sourcemap']}};",
            "const interceptedFs = {readFileSync: fs.readFileSync, realpathSync: fs.realpathSync, mkdirSync: () => {},",
            "    writeFileSync: () => {}, openSync: () => 1};",
            "function injectedRequire(name) {",
            "    if (name === 'node:fs') return interceptedFs;",
            "    if (name === 'node:crypto') return crypto;",
            "    if (name === 'node:path') return path;",
            "    if (name === 'karma/lib/config') return karma;",
            "    throw new Error(name);",
            "}",
            "injectedRequire.resolve = () => path.join(root,",
            "    'kotlin-web-helpers/dist/karma-kotlin-reporter.js');",
            "const env = {DYN4K_BROWSER_REPORTER_SOURCE: process.argv[1],",
            "    DYN4K_BROWSER_REPORTER_ATTESTATION: path.join(tmpdir, 'reporter.json'),",
            "    DYN4K_BROWSER_RAW_KARMA: path.join(tmpdir, 'raw.jsonl'),",
            "    DYN4K_BROWSER_SELECTED_BUNDLE: selected,",
            "    DYN4K_BROWSER_SELECTED_ARCHIVE: path.join(tmpdir, 'selected.js'),",
            "    DYN4K_BROWSER_SELECTED_ATTESTATION: path.join(tmpdir, 'selected.json'),",
            "    DYN4K_BROWSER_WORK_ROOT: work, DYN4K_BROWSER_TMPDIR: tmpdir};",
            "vm.runInNewContext(source, {config, require: injectedRequire,",
            "    process: {env, pid: 123}, Buffer});",
            "const Reporter = config.plugins[0][key][1];",
            "assert.equal(config.files.length, 7);",
            "assert.equal(Object.prototype.hasOwnProperty.call(files[0], 'isBinary'), false);",
            "assert.equal(Object.prototype.hasOwnProperty.call(files[5], 'isBinary'), true);",
            "assert.equal(files[5].isBinary, undefined);",
            "assert.doesNotThrow(() => new Reporter(null, config, null));",
            "for (let index = 0; index < files.length; index++) {",
            "    const file = files[index];",
            "    const owned = Object.prototype.hasOwnProperty.call(file, 'isBinary');",
            "    const original = file.isBinary;",
            "    file.isBinary = true;",
            "    assert.throws(() => new Reporter(null, config, null), /binary pattern/);",
            "    if (owned) file.isBinary = original;",
            "    else delete file.isBinary;",
            "}",
            "files[5].isBinary = false;",
            "assert.throws(() => new Reporter(null, config, null), /binary pattern/);",
            "files[5].isBinary = undefined;",
            "assert.doesNotThrow(() => new Reporter(null, config, null));",
        ))
        completed = subprocess.run(["node", "-e", script, str(reporter), str(cache)],
                                   check=False, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_reporter_wasm_pattern_rejects_unserved_loader(self):
        reporter = Path(__file__).resolve().parents[2] / browser.REPORTER
        root = (Path.home() / ".kotlin/kotlin-npm-tooling/yarn/"
                "9c7852378f220e63c4f92e7d93026c2f/node_modules")
        script = "\n".join((
            "const assert = require('node:assert/strict');",
            "const fs = require('node:fs');",
            "const path = require('node:path');",
            "const vm = require('node:vm');",
            "const {createRequire} = require('node:module');",
            "const source = fs.readFileSync(process.argv[1], 'utf8');",
            "const root = process.argv[2];",
            "const karma = createRequire(path.join(root, 'karma/package.json'))('karma/lib/config');",
            "const work = '/evidence/build';",
            "const tmpdir = '/evidence/tmp';",
            "const webpack = path.join(tmpdir, '_karma_webpack_123');",
            "const runner = path.join(root, 'kotlin-web-helpers/dist/kotlin-test-karma-runner.js');",
            "const selected = path.join(work, 'root/wasm/packages/test/static/load.mjs');",
            "const paths = [path.join(webpack, 'runtime.js'), path.join(webpack, 'commons.js'),",
            "  path.join(fs.realpathSync(root), 'mocha/mocha.js'),",
            "  path.join(fs.realpathSync(root), 'karma-mocha/lib/adapter.js'),",
            "  runner, selected, path.join(webpack, '**/*')];",
            "const files = paths.map((pattern, index) => ({pattern, served: true,",
            "  included: index !== 6, watched: false, nocache: false}));",
            "function OriginalReporter() {this.write = () => {};",
            "  this.onBrowserStart = () => {}; this.onRunComplete = () => {};}",
            "OriginalReporter.$inject = [];",
            "const key = 'reporter:karma-kotlin-reporter';",
            "const config = {plugins: [{[key]: ['type', OriginalReporter]}], files, set: () => {},",
            "  preprocessors: {[runner]: ['webpack', 'sourcemap'],",
            "    [selected]: ['webpack', 'sourcemap']}};",
            "const interceptedFs = {readFileSync: fs.readFileSync, realpathSync: fs.realpathSync, mkdirSync: () => {},",
            "  writeFileSync: () => {}, openSync: () => 1};",
            "function injectedRequire(name) {",
            "  if (name === 'node:fs') return interceptedFs;",
            "  if (name === 'node:crypto') return require('node:crypto');",
            "  if (name === 'node:path') return path;",
            "  if (name === 'karma/lib/config') return karma;",
            "  throw Error(name);}",
            "injectedRequire.resolve = () => path.join(root,",
            "  'kotlin-web-helpers/dist/karma-kotlin-reporter.js');",
            "const env = {DYN4K_BROWSER_TARGET: 'wasmJs',",
            "  DYN4K_BROWSER_REPORTER_SOURCE: process.argv[1],",
            "  DYN4K_BROWSER_REPORTER_ATTESTATION: '/evidence/reporter.json',",
            "  DYN4K_BROWSER_RAW_KARMA: '/evidence/raw.jsonl',",
            "  DYN4K_BROWSER_SELECTED_BUNDLE: selected,",
            "  DYN4K_BROWSER_SELECTED_ARCHIVE: '/evidence/selected.mjs',",
            "  DYN4K_BROWSER_SELECTED_ATTESTATION: '/evidence/selected.json',",
            "  DYN4K_BROWSER_WORK_ROOT: work, DYN4K_BROWSER_TMPDIR: tmpdir};",
            "vm.runInNewContext(source, {config, require: injectedRequire,",
            "  process: {env, pid: 123}, Buffer});",
            "const Reporter = config.plugins[0][key][1];",
            "assert.doesNotThrow(() => new Reporter(null, config, null));",
            "files[5].served = false;",
            "assert.throws(() => new Reporter(null, config, null), /effective files/);",
            "files[5].served = true; files[5].isBinary = true;",
            "assert.throws(() => new Reporter(null, config, null), /binary pattern/);",
        ))
        completed = subprocess.run(["node", "-e", script, str(reporter), str(root)],
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

    def test_archived_selected_record_requires_original_binary_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            work = folder / "build"
            linked, selected, runner = browser.bundle_paths(work, "core", "development")
            root = work / "root/js/node_modules"
            webpack = folder / "tmp/_karma_webpack_123"
            paths = [str(webpack / "runtime.js"), str(webpack / "commons.js"),
                     str(root / "mocha/mocha.js"), str(root / "karma-mocha/lib/adapter.js"),
                     str(runner), str(selected), str(webpack / "**/*")]
            (folder / "karma.conf.js").write_bytes(self.config(self.settings(work, "development")))
            (folder / "browser-reporter.js").write_bytes(self.reporter)
            (folder / "linked-executable.js").write_bytes(b"same selected bytes")
            (folder / "karma-selected.js").write_bytes(b"same selected bytes")
            evidence = {"source_path": str(selected),
                        "archive_path": str(folder / "karma-selected.js"),
                        "sha256": browser.sha(b"same selected bytes"), "node_pid": 123,
                        "browser_id": "browser-id",
                        "browser_name": "Chrome Headless 155.0.0.0 (Linux 0.0.0)",
                        "captured_ns": 2, "complete_ns": 3,
                        "tmpdir": str(webpack.parent),
                        "effective_files": [{"pattern": path, "served": True,
                                             "included": index != 6, "watched": False,
                                             "nocache": False, "type": None, "isBinary": None}
                                            for index, path in enumerate(paths)],
                        "effective_preprocessors": {str(path): ["webpack", "sourcemap"]
                                                    for path in (runner, selected)},
                        "input_sha256": {str(root / name): digest for name, digest
                                         in browser.RUNTIME_INPUT_SHA256.items()}}
            record = {"started_ns": 1, "finished_ns": 4,
                      "linked_sha256": browser.sha(b"same selected bytes"),
                      "karma_port": self.port}
            with mock.patch.object(browser, "KARMA_GENERATED_MIDDLE_SHA256",
                                   browser.sha(self.middle)):
                (folder / "selected-bundle.json").write_text(json.dumps(evidence))
                browser.selected_bundle(folder, work, "core", "development", record, 155,
                                        require_effective=True)
                with tempfile.TemporaryDirectory() as relocated_directory:
                    relocated = Path(relocated_directory) / "archive"
                    shutil.copytree(folder, relocated, copy_function=shutil.copy2)
                    browser.selected_bundle(relocated, work, "core", "development",
                                            record, 155, require_effective=True,
                                            observed_folder=folder)
                    with self.assertRaisesRegex(ValueError, "source-process binding"):
                        browser.selected_bundle(relocated, work, "core", "development",
                                                record, 155, require_effective=True)
                evidence["effective_files"][5]["isBinary"] = True
                (folder / "selected-bundle.json").write_text(json.dumps(evidence))
                with self.assertRaisesRegex(ValueError, "effective files"):
                    browser.selected_bundle(folder, work, "core", "development", record, 155,
                                            require_effective=True)

    def test_wasm_archive_rejects_changed_served_wasm(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            work = folder / "build"
            settings = self.settings(work, "development", "wasmJs", "Chromium")
            runner = Path(settings["files"][0])
            root = runner.parents[2]
            linked, selected, _ = browser.bundle_paths(work, "core", "development",
                                                        "wasmJs", runner)
            webpack = folder / "tmp/_karma_webpack_123"
            patterns = [str(webpack / "runtime.js"), str(webpack / "commons.js"),
                        str(root.resolve() / "mocha/mocha.js"),
                        str(root.resolve() / "karma-mocha/lib/adapter.js"),
                        str(runner), str(selected), str(webpack / "**/*")]
            package = "dyn4k-full-staged-browser-consumer-core-test"
            names = sorted((f"{package}.wasm", f"{package}.mjs",
                            f"{package}.wasm.map", "custom-formatters.js",
                            f"{package}.js-builtins.mjs",
                            f"{package}.import-object.mjs"))
            assets = folder / "assets"
            assets.mkdir()
            for name in names:
                (assets / name).write_bytes(name.encode())
            (folder / "karma.conf.js").write_bytes(self.config(settings))
            (folder / "browser-reporter.js").write_bytes(self.reporter)
            (folder / "linked-executable.js").write_bytes(f"{package}.mjs".encode())
            (folder / "linked-executable.wasm").write_bytes(f"{package}.wasm".encode())
            (folder / "karma-selected.js").write_bytes(b"loader")
            evidence = {"source_path": str(selected),
                        "archive_path": str(folder / "karma-selected.js"),
                        "sha256": browser.sha(b"loader"), "node_pid": 11,
                        "browser_id": "browser-id",
                        "browser_name": "Chrome Headless 155.0.0.0 (Linux 0.0.0)",
                        "captured_ns": 2, "complete_ns": 3,
                        "tmpdir": str(webpack.parent),
                        "effective_files": [{"pattern": path, "served": True,
                                             "included": index != 6, "watched": False,
                                             "nocache": False, "type": None,
                                             "isBinary": None}
                                            for index, path in enumerate(patterns)],
                        "effective_preprocessors": {str(path): ["webpack", "sourcemap"]
                                                    for path in (runner, selected)},
                        "input_sha256": {str(root / name): digest for name, digest
                                         in browser.WASM_INPUT_SHA256.items()},
                        "assets": [{"name": name, "sha256": browser.sha(name.encode())}
                                   for name in names]}
            (folder / "selected-bundle.json").write_text(json.dumps(evidence))
            record = {"started_ns": 1, "finished_ns": 4,
                      "linked_sha256": browser.sha(f"{package}.mjs".encode()),
                      "linked_wasm_sha256": browser.sha(f"{package}.wasm".encode()),
                      "karma_port": self.port}
            with mock.patch.object(browser, "WASM_KARMA_GENERATED_MIDDLE_SHA256",
                                   browser.sha(self.middle)):
                browser.selected_bundle(folder, work, "core", "development", record,
                                        155, True, "wasmJs", "Chromium")
                outside = {**record, "started_ns": 3}
                with self.assertRaisesRegex(ValueError, "source-process binding"):
                    browser.selected_bundle(folder, work, "core", "development", outside,
                                            155, True, "wasmJs", "Chromium")
                (assets / f"{package}.wasm").write_bytes(b"changed")
                with self.assertRaisesRegex(ValueError, "served executable assets"):
                    browser.selected_bundle(folder, work, "core", "development", record,
                                            155, True, "wasmJs", "Chromium")


class HttpResponseWitnessTest(unittest.TestCase):
    def fixture(self, root, target="wasmJs", commons_first=False):
        folder = root / "core"
        folder.mkdir()
        (folder / "http-responses").mkdir()
        (folder / "http-sources").mkdir()
        package = "dyn4k-full-staged-browser-consumer-core-test"
        generated_names = ["runtime.js", "commons.js",
                           "kotlin-test-karma-runner.123.js",
                           (package if target == "js" else "load") + ".456.js"]
        if target == "wasmJs":
            generated_names.append("a" * 20 + ".wasm")
        asset_names = ([] if target == "js" else
                       [package + ".mjs", package + ".wasm",
                        package + ".import-object.mjs", package + ".js-builtins.mjs",
                        "custom-formatters.js"])
        names = (list(reversed(generated_names[:2])) if commons_first
                 else generated_names[:2]) + generated_names[4:]
        webpack = root / "_karma_webpack_123"
        def body(name):
            return ("served " + (package + ".wasm" if name.endswith(".wasm")
                                  and name in generated_names else name)).encode()
        generated = [{"name": name, "source_path": str(webpack / name),
                      "size": len(body(name)), "sha256": browser.sha(body(name))}
                     for name in generated_names]
        evidence = {"browser_id": "selected-browser", "browser_name": "browser",
                    "node_pid": 123, "captured_ns": 2, "complete_ns": 30,
                    "effective_files": [{"pattern": str(webpack / "runtime.js")}],
                    "generated": generated}
        (folder / "selected-bundle.json").write_text(json.dumps(evidence))
        assets = folder / "assets"
        assets.mkdir()
        for name in asset_names:
            (folder / "assets" / name).write_bytes(body(name))
        for name in generated_names[2:]:
            (folder / "http-sources" / name).write_bytes(body(name))
        items = []
        for index, name in enumerate(names):
            raw = body(name)
            source = folder / "http-sources" / name
            source.write_bytes(raw)
            (folder / "http-responses" / f"{index:04d}.body").write_bytes(raw)
            items.append({"ordinal": index, "name": name,
                          "url": "/absolute/tmp/" + name + "?source=1",
                          "method": "GET", "started_ns": 3 + index * 2,
                          "finished_ns": 4 + index * 2, "status": 200,
                          "content_encoding": None, "range": None,
                          "size": len(raw), "sha256": browser.sha(raw),
                          "body_path": f"http-responses/{index:04d}.body"})
        witness = {key: evidence[key] for key in (
            "browser_id", "browser_name", "node_pid", "captured_ns", "complete_ns")}
        witness.update(generated=generated, responses=items)
        (folder / "http-responses.json").write_text(json.dumps(witness))
        return folder, witness, {"started_ns": 1, "finished_ns": 31}

    def test_original_http_bodies_are_replayed(self):
        for target in ("js", "wasmJs"):
            for commons_first in (False, True):
                with self.subTest(target=target, commons_first=commons_first), \
                        tempfile.TemporaryDirectory() as directory:
                    folder, witness, process = self.fixture(
                        Path(directory), target, commons_first)
                    witness["captured_ns"] = 22
                    (folder / "http-responses.json").write_text(json.dumps(witness))
                    evidence = json.loads((folder / "selected-bundle.json").read_text())
                    evidence["captured_ns"] = 22
                    (folder / "selected-bundle.json").write_text(json.dumps(evidence))
                    self.assertEqual(browser.verify_http_responses(folder, process, target),
                                     witness["responses"])

    def test_changed_missing_duplicate_reordered_and_uncorrelated_bodies_reject(self):
        changes = {
            "changed": lambda folder, witness: (folder / "http-responses/0001.body")
                .write_bytes(b"changed"),
            "missing": lambda folder, witness: (folder / "http-responses/0001.body").unlink(),
            "missing_runtime": lambda folder, witness: witness["responses"].pop(0),
            "missing_wasm": lambda folder, witness: witness["responses"].pop(),
            "duplicate": lambda folder, witness: witness["responses"].append(
                dict(witness["responses"][1])),
            "reordered": lambda folder, witness: witness["responses"].reverse(),
            "uncorrelated": lambda folder, witness: witness.update(browser_id="other-browser"),
            "wrong_window": lambda folder, witness: witness["responses"][1].update(
                started_ns=32),
            "wrong_url": lambda folder, witness: witness["responses"][1].update(
                url="/absolute/tmp/other.mjs"),
            "partial": lambda folder, witness: witness["responses"][1].update(status=206),
        }
        for name, mutate in changes.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                folder, witness, process = self.fixture(Path(directory))
                mutate(folder, witness)
                (folder / "http-responses.json").write_text(json.dumps(witness))
                with self.assertRaisesRegex(ValueError, "Karma HTTP response"):
                    browser.verify_http_responses(folder, process, "wasmJs")


class PublicHttpReplayTest(unittest.TestCase):
    def test_resealed_real_archive_rejects_adverse_http_evidence(self):
        selected = os.environ.get("DYN4K_HTTP_REPLAY_ARCHIVE")
        if selected is None:
            self.skipTest("set DYN4K_HTTP_REPLAY_ARCHIVE to a real schema-3 archive")
        source = Path(selected)
        receipt = json.loads((source / "receipt.json").read_text())
        self.assertEqual(receipt["schema"], 3)
        repository = Path(__file__).resolve().parents[2]
        changes = ("changed", "missing", "duplicate", "reordered", "uncorrelated")
        for change in changes:
            with self.subTest(change=change), tempfile.TemporaryDirectory(
                    dir=Path.home().resolve(), prefix="dyn4k-http-replay-") as directory:
                archive = Path(directory) / "archive"
                shutil.copytree(source, archive, copy_function=shutil.copy2)
                altered = json.loads((archive / "receipt.json").read_text())
                body = archive / "core/http-responses/0001.body"
                witness_path = archive / "core/http-responses.json"
                witness = json.loads(witness_path.read_text())
                if change == "changed":
                    old = body.stat()
                    body.write_bytes(b"changed HTTP response")
                    os.utime(body, ns=(old.st_atime_ns, old.st_mtime_ns))
                elif change == "missing":
                    body.unlink()
                    altered["files"] = [item for item in altered["files"]
                                        if item["path"] != "core/http-responses/0001.body"]
                else:
                    if change == "duplicate":
                        witness["responses"].append(dict(witness["responses"][1]))
                    elif change == "reordered":
                        witness["responses"].reverse()
                    else:
                        witness["browser_id"] = "other-browser"
                    old = witness_path.stat()
                    witness_path.write_bytes(browser.encoded(witness) + b"\n")
                    os.utime(witness_path, ns=(old.st_atime_ns, old.st_mtime_ns))
                for item in altered["files"]:
                    if item["path"] in {"core/http-responses/0001.body",
                                        "core/http-responses.json"}:
                        item["sha256"] = browser.file_hash(archive / item["path"])
                (archive / "receipt.json").write_bytes(browser.encoded(altered) + b"\n")
                digest = browser.independent_gates.archive_digest(archive)
                with self.assertRaisesRegex(ValueError, "Karma HTTP response"):
                    browser.verify(repository, altered["candidate_sha"], altered["lane"],
                                   archive, digest, Path(altered["toolchain"]["browser"]),
                                   altered["staged_hashes"])


class FirefoxProcessWitnessTest(unittest.TestCase):
    def test_bidi_body_transcript_rejects_process_source_url_body_and_time_changes(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            folder = Path(directory)
            (folder / "firefox-bodies").mkdir()
            (folder / "http-responses").mkdir()
            server = []
            rows = [{"kind": "session", "protocol": 1, "module": "core",
                     "target": "wasmJs", "candidate_sha": "a" * 40,
                     "browser_pid": 314, "bidi_browser_pid": 314,
                     "context_id": "context", "session_id": "session",
                     "collector_id": "collector", "started_ns": 110,
                     "bidi_port": 40000, "bidi_socket_inode": "4567",
                     "contexts": [
                         {"observed_ns": 105, "params": {"context": "context", "parent": None}},
                         {"observed_ns": 115, "params": {"context": "frame", "parent": "context"}}],
                     "source_path": "/checkout/firefox_bidi_witness.js",
                     "source_sha256": "c" * 64}]
            for index, name in enumerate(("runtime.js", "commons.js", "abc.wasm")):
                body = name.encode()
                relative = f"/absolute/build/{name}"
                url = f"http://localhost:9876{relative}"
                request_id = f"request-{index}"
                (folder / "firefox-bodies" / f"{index:04d}.body").write_bytes(body)
                (folder / "http-responses" / f"{index:04d}.body").write_bytes(body)
                server.append({"ordinal": index, "name": name, "url": relative,
                               "size": len(body), "sha256": browser.sha(body),
                               "body_path": f"http-responses/{index:04d}.body",
                               "started_ns": 122 + index * 10,
                               "finished_ns": 126 + index * 10})
                rows.append({"kind": "response", "ordinal": index,
                             "request_id": request_id, "context_id": "frame",
                             "browser_pid": 314, "url": url, "method": "GET",
                             "status": 200, "mime_type": "application/javascript",
                             "from_cache": False, "request_ns": 120 + index * 10,
                             "response_ns": 127 + index * 10,
                             "finished_ns": 129 + index * 10,
                             "body_path": f"firefox-bodies/{index:04d}.body",
                             "body_size": len(body), "body_sha256": browser.sha(body),
                             "events": {
                                 "request": {"context": "frame", "isBlocked": False,
                                             "timestamp": 120 + index * 10,
                                             "request": {"request": request_id,
                                                         "url": url, "method": "GET"}},
                                 "response": {"context": "frame", "isBlocked": False,
                                              "timestamp": 127 + index * 10,
                                              "request": {"request": request_id,
                                                          "url": url},
                                              "response": {"url": url, "status": 200,
                                                           "fromCache": False,
                                                           "mimeType": "application/javascript"}}}})
            process = {"started_ns": 100, "finished_ns": 200, "karma_port": 9876}

            def check(transcript):
                (folder / "firefox-bidi.jsonl").write_text(
                    "".join(json.dumps(item) + "\n" for item in transcript))
                return browser.verify_firefox_process_witness(
                    folder, process, [{"pid": 314}], server, "core", "wasmJs",
                    "a" * 40, "/checkout/firefox_bidi_witness.js", "c" * 64)

            self.assertEqual(len(check(rows)), 3)
            server.reverse()
            self.assertEqual(len(check(rows)), 3)
            server.reverse()
            for name, mutate in (
                    ("missing process", lambda items: items[0].update(browser_pid=315)),
                    ("wrong hash", lambda items: items[1].update(body_sha256="0" * 64)),
                    ("stale source", lambda items: items[0].update(source_sha256="0" * 64)),
                    ("missing frame", lambda items: items[0]["contexts"].pop()),
                    ("foreign frame", lambda items: items[0]["contexts"][1]["params"].update(
                        parent="other")),
                    ("late frame", lambda items: items[0]["contexts"][1].update(
                        observed_ns=130)),
                    ("wrong Wasm body", lambda items: items[3].update(body_sha256="0" * 64)),
                    ("duplicate request", lambda items: items[2].update(request_id="request-0")),
                    ("duplicate URL", lambda items: items[2].update(url=items[1]["url"])),
                    ("bad time", lambda items: items[1].update(response_ns=119)),
                    ("missing response", lambda items: items.pop()),
                    ("failed request", lambda items: items[1]["events"]["response"].update(
                        isBlocked=True))):
                with self.subTest(name=name):
                    changed = json.loads(json.dumps(rows))
                    mutate(changed)
                    with self.assertRaisesRegex(ValueError, "Firefox process witness"):
                        check(changed)


class ChromiumProcessWitnessTest(unittest.TestCase):
    def test_browser_observation_rejects_absent_changed_reordered_and_wrong_process(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            folder = Path(directory)
            server = []
            observations = [{"kind": "session", "protocol": 1, "module": "core",
                             "target": "js", "candidate_sha": "a" * 40,
                             "browser_pid": 314, "cdp_browser_pid": 314,
                             "target_id": "page-1", "started_ns": 110,
                             "devtools_port": 40000,
                             "devtools_socket_inode": "4567",
                             "source_path": "/checkout/chromium_http_witness.js",
                             "source_sha256": "c" * 64}]
            for ordinal, name in enumerate(("runtime.js", "commons.js")):
                body = name.encode()
                server.append({"ordinal": ordinal, "name": name,
                               "url": f"/absolute/build/{name}",
                               "size": len(body), "sha256": browser.sha(body),
                               "started_ns": 120 + ordinal * 10,
                               "finished_ns": 125 + ordinal * 10})
                url = f"http://localhost:9876/absolute/build/{name}"
                request_id = str(ordinal + 1)
                observations.append({"kind": "response", "ordinal": ordinal,
                                     "request_id": str(ordinal + 1),
                                     "target_id": "page-1", "browser_pid": 314,
                                     "url": url,
                                     "method": "GET", "status": 200,
                                     "mime_type": "application/javascript",
                                     "from_disk_cache": False,
                                     "from_service_worker": False,
                                     "request_ns": 120 + ordinal * 10,
                                     "response_ns": 122 + ordinal * 10,
                                     "finished_ns": 126 + ordinal * 10,
                                     "body_size": len(body),
                                     "body_sha256": browser.sha(body),
                                     "events": {
                                         "request": {"requestId": request_id,
                                                     "timestamp": ordinal + 1.0,
                                                     "request": {"url": url, "method": "GET"}},
                                         "response": {"requestId": request_id,
                                                      "timestamp": ordinal + 1.1,
                                                      "response": {"url": url, "status": 200,
                                                                   "mimeType": "application/javascript"}},
                                         "finish": {"requestId": request_id,
                                                    "timestamp": ordinal + 1.05}}})
            process = {"started_ns": 100, "finished_ns": 200,
                       "karma_port": 9876, "browser_token": "token"}
            launches = [{"pid": 314}]

            def check(records):
                (folder / "chromium-cdp.jsonl").write_text(
                    "".join(json.dumps(item) + "\n" for item in records))
                return browser.verify_chromium_process_witness(
                    folder, process, launches, server, "core", "js", "a" * 40,
                    "/checkout/chromium_http_witness.js", "c" * 64)

            self.assertEqual(len(check(observations)), 2)
            server.reverse()
            self.assertEqual(len(check(observations)), 2)
            server.reverse()
            for name, mutate in (
                    ("missing", lambda rows: rows.pop()),
                    ("changed body", lambda rows: rows[1].update(body_sha256="0" * 64)),
                    ("wrong process", lambda rows: rows[0].update(cdp_browser_pid=315)),
                    ("wrong response process", lambda rows: rows[1].update(browser_pid=315)),
                    ("reordered", lambda rows: rows.reverse()),
                    ("wrong source", lambda rows: rows[0].update(candidate_sha="b" * 40)),
                    ("wrong launcher source", lambda rows: rows[0].update(source_sha256="0" * 64)),
                    ("wrong URL", lambda rows: rows[1].update(url="http://localhost:9877/absolute/build/runtime.js")),
                    ("duplicate", lambda rows: rows.append(dict(rows[1])))):
                with self.subTest(name=name):
                    changed = json.loads(json.dumps(observations))
                    mutate(changed)
                    with self.assertRaisesRegex(ValueError, "Chromium process witness"):
                        check(changed)

    def test_resealed_real_archive_rejects_browser_process_evidence_changes(self):
        selected = os.environ.get("DYN4K_CDP_REPLAY_ARCHIVE")
        if selected is None:
            self.skipTest("set DYN4K_CDP_REPLAY_ARCHIVE to a real schema-4 archive")
        source = Path(selected)
        receipt = json.loads((source / "receipt.json").read_text())
        self.assertEqual(receipt["schema"], 4)
        repository = Path(__file__).resolve().parents[2]
        changes = ("missing", "body", "process", "reordered", "source",
                   "launcher source", "package")
        for change in changes:
            with self.subTest(change=change), tempfile.TemporaryDirectory(
                    dir=Path.home().resolve(), prefix="dyn4k-cdp-replay-") as directory:
                archive = Path(directory) / "archive"
                shutil.copytree(source, archive, copy_function=shutil.copy2)
                altered = json.loads((archive / "receipt.json").read_text())
                path = archive / "core/chromium-cdp.jsonl"
                rows = [json.loads(line) for line in path.read_text().splitlines()]
                if change == "missing":
                    rows.pop()
                elif change == "body":
                    rows[1]["body_sha256"] = "0" * 64
                elif change == "process":
                    rows[0]["cdp_browser_pid"] += 1
                elif change == "reordered":
                    rows[1], rows[2] = rows[2], rows[1]
                elif change == "source":
                    rows[0]["candidate_sha"] = "0" * 40
                elif change == "launcher source":
                    rows[0]["source_sha256"] = "0" * 64
                else:
                    self.assertEqual(altered["lane"].split(":")[0], "wasmJs")
                    wasm = next(row for row in rows[1:] if row["url"].split("?")[0].endswith(".wasm"))
                    wasm["body_sha256"] = "0" * 64
                old = path.stat()
                path.write_text("".join(json.dumps(row) + "\n" for row in rows))
                os.utime(path, ns=(old.st_atime_ns, old.st_mtime_ns))
                next(item for item in altered["files"] if item["path"] ==
                     "core/chromium-cdp.jsonl")["sha256"] = browser.file_hash(path)
                (archive / "receipt.json").write_bytes(browser.encoded(altered) + b"\n")
                digest = browser.independent_gates.archive_digest(archive)
                with self.assertRaisesRegex(ValueError, "Chromium process witness"):
                    browser.verify(repository, altered["candidate_sha"], altered["lane"],
                                   archive, digest, Path(altered["toolchain"]["browser"]),
                                   altered["staged_hashes"])


if __name__ == "__main__":
    unittest.main()
