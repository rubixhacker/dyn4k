import os
import copy
import json
import re
import shutil
import subprocess
import tempfile
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import full_klib_consumer as route
import independent_gates


REPOSITORY = Path(__file__).resolve().parents[2]
ARCHIVE = os.environ.get("DYN4K_FULL_KLIB_ARCHIVE")
TRUSTED = os.environ.get("DYN4K_FULL_KLIB_TRUSTED_TOOLCHAIN")
REPLAY_REPOSITORY = Path(os.environ.get("DYN4K_FULL_KLIB_REPLAY_CHECKOUT", REPOSITORY))


class FullKlibConsumerTests(unittest.TestCase):
    def test_all_approved_local_lane_modes_have_distinct_products(self):
        self.assertEqual(len(route.LOCAL_LANES), 8)
        self.assertEqual({route.mode_path(lane) for lane in route.LOCAL_LANES}, {
            "debugTest", "releaseTest", "testDevelopmentExecutable",
            "testProductionExecutable"})
        for lane, (target, variant) in route.LOCAL_LANES.items():
            self.assertIn(lane.split(":")[2], ("minimum", "current"))
            self.assertEqual(variant, "linuxx64" if target == "linuxX64" else "js")

    def test_schema2_gradle_events_require_exact_channels_and_tasks(self):
        stamp = "2026-10-19T00:07:49.593-0500"
        marker = "QUALIFICATION_CASE_COUNT=2523"
        self.assertTrue(route._process_marker(
            [f"{stamp} [QUIET] [system.out] {marker}"], marker, 2))
        self.assertTrue(route._process_marker(
            [f"{stamp} [LIFECYCLE] [org.gradle.api.Task] {marker}"], marker, 2))
        self.assertTrue(route._process_marker([marker], marker, 2))
        for line in (f"{stamp} [ERROR] [system.out] {marker}",
                     f"{stamp} [QUIET] [foreign.logger] {marker}",
                     f"spoofed [QUIET] [system.out] {marker}"):
            with self.subTest(line=line):
                self.assertFalse(route._process_marker([line], marker, 2))

        task = ":core:compileTestKotlinJs"
        lifecycle = (f"{stamp} [LIFECYCLE] "
                     f"[class org.gradle.internal.buildevents.TaskExecutionLogger] > Task {task}")
        action = (f"{stamp} [DEBUG] [org.gradle.api.internal.tasks.execution.TaskExecution] "
                  f"Executing actions for task '{task}'.")
        self.assertTrue(route._process_task([lifecycle, action], task, 2))
        for lines in ([lifecycle], [action],
                      [lifecycle, action.replace("[DEBUG]", "[INFO]")],
                      [lifecycle.replace(task, ":core:wrongTask"), action]):
            with self.subTest(lines=lines):
                self.assertFalse(route._process_task(lines, task, 2))

    def test_minimum_runtime_requires_real_floor_binaries(self):
        current = {"system": "Linux", "kernel_release": "7.2.9-test",
                   "machine": "x86_64", "glibc": "2.42", "node_version": "v26.10.0"}
        native = "linuxX64:Linux x64:minimum:optimized-opt"
        node = "js:Node.js:minimum:production"
        with self.assertRaisesRegex(ValueError, "minimum Linux x64 runner unavailable"):
            route.validate_runtime(native, current)
        with self.assertRaisesRegex(ValueError, "minimum Node.js runner unavailable"):
            route.validate_runtime(node, current)
        minimum = {**current, "kernel_release": "4.9.156", "glibc": "2.19",
                   "node_version": "v22.0.0"}
        route.validate_runtime(native, minimum)
        route.validate_runtime(node, minimum)
        for lane in route.LOCAL_LANES:
            if ":current:" in lane:
                with self.assertRaisesRegex(ValueError, "cannot equal the minimum profile"):
                    route.validate_runtime(lane, minimum)
                route.validate_runtime(lane, current)
                continue
            route.validate_runtime(lane, minimum)
        self.assertIn("glibc 2.19", route.observed_runtime_identity(minimum, "JDK21"))
        alternate_node = {**minimum, "system": "Darwin", "kernel_release": "25.0.0",
                          "machine": "arm64", "glibc": ""}
        route.validate_runtime(node, alternate_node)
        with self.assertRaisesRegex(ValueError, "Linux x64 runtime identity"):
            route.validate_runtime(native, alternate_node)

    def test_compiler_evidence_rejects_wrong_link_and_friend_module(self):
        for variant, mode in (("linuxx64", "releaseTest"),
                              ("js", "testProductionExecutable")):
            graph = {"compile": []}
            evidence = []
            for short, module in (("core", "dyn4k-core"), ("facade", "dyn4k")):
                resolved = f"/external-cache/{module}-{variant}.klib"
                graph["compile"].append({"project": short, "artifacts": [{
                    "component": f"{route.GROUP}:{module}-{variant}:{route.VERSION}",
                    "file": resolved}]})
                if variant == "linuxx64":
                    compile_task = f":{short}:compileTestKotlinLinuxX64"
                    executable_task = f":{short}:linkReleaseTestLinuxX64"
                    args = ["-opt", "-friend-modules", resolved]
                    executable_args = []
                else:
                    compile_task = f":{short}:compileTestKotlinJs"
                    executable_task = f":{short}:compileTestProductionExecutableKotlinJs"
                    executable_args = [f"-Xfriend-modules={resolved}"]
                    args = [f"-Xir-per-module-output-name=dyn4k-full-staged-klib-consumer-{short}-test",
                            *executable_args]
                evidence.append({"module": short, "compile_task": compile_task,
                                 "compile_args": args, "executable_task": executable_task,
                                 "executable_args": executable_args})
            route.require_compiler_evidence(evidence, graph, variant, mode)
            wrong = copy.deepcopy(evidence)
            wrong[0]["executable_task"] = wrong[0]["executable_task"].replace(
                "Release", "Debug").replace("Production", "Development")
            with self.assertRaisesRegex(ValueError, "compiler mode"):
                route.require_compiler_evidence(wrong, graph, variant, mode)
            wrong = copy.deepcopy(evidence)
            wrong[0]["compile_args"][-1] = "/source/build/dyn4k-core.klib"
            with self.assertRaisesRegex(ValueError, "friend KLIB"):
                route.require_compiler_evidence(wrong, graph, variant, mode)

    def test_effective_js_invocations_reject_wrong_mode_friend_and_missing_link(self):
        graph = {"compile": []}
        for short, module in (("core", "dyn4k-core"), ("facade", "dyn4k")):
            graph["compile"].append({"project": short, "artifacts": [
                {"component": f"{route.GROUP}:{name}-js:{route.VERSION}",
                 "file": f"/stage/{name}.klib"} for name in route.MODULES]})
        paths = {"work_root": "/work"}
        lines = []
        for short, module in (("core", "dyn4k-core"), ("facade", "dyn4k")):
            common = (f"-target es5 -libraries /stage/dyn4k-core.klib:/stage/dyn4k.klib "
                      f"-Xfriend-modules=/stage/{module}.klib")
            lines.append(f"[KOTLIN] :{short}:compileTestKotlinJs Kotlin compiler args: "
                         f"{common} -ir-output-dir /work/{short}/classes/kotlin/js/test")
            lines.append(f"[KOTLIN] :{short}:compileTestProductionExecutableKotlinJs "
                         f"Kotlin compiler args: {common} -Xir-produce-js -Xir-dce "
                         f"-ir-output-dir /work/{short}/compileSync/js/test/"
                         "testProductionExecutable/kotlin")
        output = "\n".join(lines)
        route.require_actual_invocations(output, graph, "js", "testProductionExecutable", paths)
        for altered in (output.replace("-Xir-dce", "-Xir-no-dce", 1),
                        output.replace("/stage/dyn4k-core.klib", "/source/core.klib", 1),
                        "\n".join(lines[:-1])):
            with self.subTest(altered=altered[:60]), self.assertRaisesRegex(ValueError,
                                                                              "actual JS"):
                route.require_actual_invocations(altered, graph, "js",
                                                 "testProductionExecutable", paths)

    def test_effective_native_invocations_reject_wrong_mode_friend_and_missing_link(self):
        graph = {"compile": []}
        for short in ("core", "facade"):
            graph["compile"].append({"project": short, "artifacts": [
                {"component": f"{route.GROUP}:{name}-linuxx64:{route.VERSION}",
                 "file": f"/cache/{name}.klib"} for name in route.MODULES]})
        paths = {"work_root": "/work"}
        chunks = []
        for short, module in (("core", "dyn4k-core"), ("facade", "dyn4k")):
            for task, product, destination in (
                (f"compileTestKotlinLinuxX64", "library",
                 f"/work/{short}/classes/kotlin/linuxX64/test/klib/{short}_test"),
                (f"linkReleaseTestLinuxX64", "program",
                 f"/work/{short}/bin/linuxX64/releaseTest/test.kexe")):
                chunks.append(f"Executing actions for task ':{short}:{task}'.\n"
                              "[DEBUG] [konanc] Run in-process tool \"konanc\"\n"
                              "Entry point method = main\nArguments = [\n"
                              "\t-g\n\t-opt\n\t-target\n\tlinux_x64\n"
                              f"\t-produce\n\t{product}\n\t-output\n\t{destination}\n"
                              "\t-library\n\t/cache/dyn4k-core.klib\n"
                              "\t-library\n\t/cache/dyn4k.klib\n"
                              f"\t-friend-modules\n\t/cache/{module}.klib\n]")
        output = "\n".join(chunks)
        route.require_actual_invocations(output, graph, "linuxx64", "releaseTest", paths)
        for altered in (output.replace("\t-opt", "\t-g", 1),
                        output.replace("/cache/dyn4k-core.klib\n]", "/source/core.klib\n]", 1),
                        "\n".join(chunks[:-1])):
            with self.subTest(altered=altered[:60]), self.assertRaisesRegex(ValueError,
                                                                              "actual Native"):
                route.require_actual_invocations(altered, graph, "linuxx64",
                                                 "releaseTest", paths)

    def test_capture_cli_passes_named_original_inputs(self):
        command = ["full_klib_consumer.py", "capture", "--repository", "/source",
                   "--project", "/project", "--archive", "/archive",
                   "--work-root", "/work", "--lane", "linuxX64:Linux x64:current:debug-g",
                   "--node", "/node", "--source-inventory", "/source.tsv",
                   "--core-cases", "/core.tsv", "--facade-cases", "/facade.tsv",
                   "--lane-script", "/script"]
        with patch.object(sys, "argv", command), patch.object(route, "capture") as capture:
            route.main()
        self.assertEqual(capture.call_args.args[-1], {
            "source-inventory.tsv": Path("/source.tsv"),
            "core-cases.tsv": Path("/core.tsv"),
            "facade-cases.tsv": Path("/facade.tsv"),
            "lane-script": Path("/script")})

    def test_approved_portable_contract_and_exact_sources(self):
        candidate = __import__("subprocess").check_output(
            ["git", "-C", str(REPOSITORY), "rev-parse", "HEAD"], text=True).strip()
        for lane in route.LOCAL_LANES:
            _, selected = route.contract(REPOSITORY, lane)
            self.assertEqual(len(selected["cases"]), 2523)
            prepared = route.input_bytes(REPOSITORY, candidate, lane)
            self.assertEqual(len(prepared["source-inventory.tsv"].splitlines()), 170)
            self.assertEqual(len(prepared["core-cases.tsv"].splitlines()), 2465)
            self.assertEqual(len(prepared["facade-cases.tsv"].splitlines()), 58)

    def test_native_xml_requires_original_selected_assertions(self):
        selected = {("a.B", "method"): "dyn4k-core:a.B#method"}
        raw = (b'<testsuite tests="1" failures="0" errors="0" skipped="0" time="0.1">'
               b'<testcase classname="linuxX64Test.a.B" name="method[linuxX64]" time="0.1"/>'
               b'</testsuite>')
        ids, normalized = route._report(raw, "linuxX64", selected)
        self.assertEqual(ids, ["dyn4k-core:a.B#method"])
        self.assertEqual(ET.fromstring(normalized).find("testcase").get("id"), ids[0])
        for altered in (raw.replace(b"method[linuxX64]", b"other[linuxX64]"),
                        raw.replace(b'skipped="0"', b'skipped="1"'),
                        raw.replace(b'tests="1"', b'tests="2"')):
            with self.subTest(altered=altered), self.assertRaises(ValueError):
                route._report(altered, "linuxX64", selected)
        duplicate = raw.replace(b'tests="1"', b'tests="2"').replace(
            b'</testsuite>',
            b'<testcase classname="linuxX64Test.a.B" name="method[linuxX64]" time="0.1"/>'
            b'</testsuite>')
        with self.assertRaisesRegex(ValueError, "duplicate"):
            route._report(duplicate, "linuxX64", selected)
        for outcome in (b"skipped", b"failure"):
            altered = raw.replace(b' name="method[linuxX64]" time="0.1"/>',
                                  b' name="method[linuxX64]" time="0.1"><' + outcome +
                                  b'/></testcase>')
            altered = altered.replace(outcome + b'="0"', outcome + b'="1"')
            with self.subTest(outcome=outcome), self.assertRaises(ValueError):
                route._report(altered, "linuxX64", selected)

    @unittest.skipUnless(os.environ.get("DYN4K_KLIB_BOUNDED_TAP"),
                         "requires retained original bounded Node TAP")
    def test_node_tap_rejects_fabricated_and_failed_rows(self):
        tap = Path(os.environ["DYN4K_KLIB_BOUNDED_TAP"]).read_bytes()
        selected = route._selected_cases(Path(os.environ["DYN4K_KLIB_BOUNDED_CASES"]))
        ids, xml = route._tap(tap, selected)
        self.assertEqual(len(ids), 4)
        self.assertEqual(len(list(ET.fromstring(xml).iter("testcase"))), 4)
        with self.assertRaises(ValueError):
            route._tap(tap.replace(b"# pass 4", b"# pass 3"), selected)
        with self.assertRaises(ValueError):
            route._tap(tap.replace(b"# skipped 0", b"# skipped 1"), selected)
        with self.assertRaises(ValueError):
            route._tap(tap.replace(b"ok 1 - equalDistanceEdges", b"not ok 1 - equalDistanceEdges"),
                       selected)
        with self.assertRaises(ValueError):
            route._tap(tap.replace(b"# Subtest: equalDistanceEdges", b"# Subtest: fakeMethod"),
                       selected)
        with self.assertRaises(ValueError):
            route._tap(tap.replace(b"ok 1 - equalDistanceEdges", b"ok 1 - fakeMethod"),
                       selected)
        with self.assertRaises(ValueError):
            route._tap(tap.replace(b"# Subtest: equalDistanceEdges",
                                   b"# Subtest: equalDistanceEdges\n        # Subtest: equalDistanceEdges"),
                       selected)

    @unittest.skipUnless(ARCHIVE and TRUSTED, "requires retained real full KLIB archive")
    def test_schema2_retained_command_and_prefixed_output_controls(self):
        original = Path(ARCHIVE)
        receipt = json.loads((original / "receipt.json").read_bytes())
        if receipt.get("schema") != 2:
            self.skipTest("requires retained schema-2 archive")
        trusted = json.loads(Path(TRUSTED).read_bytes())
        candidate, lane = receipt["candidate_sha"], receipt["lane"]
        hashes, identity = receipt["artifact_hashes"], receipt["runtime_identity"]
        command = receipt["process"]["command"]
        self.assertEqual(command[command.index("--debug"):command.index("--debug") + 3],
                         ["--debug", "--max-workers=1", "--no-parallel"])

        class ReachedCentralGate(Exception):
            pass

        def verify(path):
            return route.verify(path, REPLAY_REPOSITORY, candidate, lane, hashes, identity,
                                independent_gates.archive_digest(path), trusted,
                                replay_node="/usr/local/bin/node" if lane.startswith("js:") else None)

        with patch.object(route.independent_gates, "evaluate_gate",
                          side_effect=ReachedCentralGate):
            with self.assertRaises(ReachedCentralGate):
                verify(original)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "archive"
            shutil.copytree(original, path, copy_function=shutil.copy2)

            def seal(changed, stdout=None):
                if stdout is not None:
                    (path / "stdout.txt").write_bytes(stdout)
                    item = next(item for item in changed["files"]
                                if item["path"] == "stdout.txt")
                    os.utime(path / "stdout.txt", ns=(item["mtime_ns"], item["mtime_ns"]))
                    item["sha256"] = route.sha(stdout)
                (path / "receipt.json").write_bytes(route.encoded(changed) + b"\n")

            for option in ("--debug", "--max-workers=1", "--no-parallel"):
                with self.subTest(option=option):
                    changed = copy.deepcopy(receipt)
                    changed["process"]["command"].remove(option)
                    seal(changed)
                    with self.assertRaisesRegex(ValueError, "process command differs"):
                        verify(path)

            stdout = (original / "stdout.txt").read_bytes()
            marker = f"[QUIET] [system.out] QUALIFICATION_LANE={lane}".encode()
            self.assertIn(marker, stdout)
            changed = copy.deepcopy(receipt)
            seal(changed, stdout.replace(marker, marker.replace(b"[QUIET]", b"[FAKE!]"), 1))
            with self.assertRaisesRegex(ValueError, "raw process output"):
                verify(path)

            task = (b":core:compileTestKotlinJs" if lane.startswith("js:")
                    else b":core:compileTestKotlinLinuxX64")
            lifecycle = b"> Task " + task
            self.assertIn(lifecycle, stdout)
            changed = copy.deepcopy(receipt)
            seal(changed, stdout.replace(lifecycle, b"> Task :core:wrongTask"))
            with self.assertRaisesRegex(ValueError, "required external runtime task"):
                verify(path)

    @unittest.skipUnless(ARCHIVE and TRUSTED, "requires retained real full KLIB archive")
    def test_replay_rejects_changed_clean_checkout_preload_before_subprocess(self):
        original = Path(ARCHIVE)
        receipt = json.loads((original / "receipt.json").read_bytes())
        if not receipt["lane"].startswith("js:"):
            self.skipTest("requires retained Node bundle")
        trusted = json.loads(Path(TRUSTED).read_bytes())
        candidate = receipt["candidate_sha"]
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory) / "changed-checkout"
            subprocess.run(["git", "clone", "--quiet", "--shared", "--no-checkout",
                            str(REPLAY_REPOSITORY), str(checkout)], check=True)
            subprocess.run(["git", "-C", str(checkout), "checkout", "--quiet", "--detach",
                            candidate], check=True)
            preload = checkout / route.CONSUMER / "node-test-preload.cjs"
            preload.write_bytes(preload.read_bytes() + b"\n// Changed replay preload.\n")
            subprocess.run(["git", "-C", str(checkout), "add", str(preload)], check=True)
            subprocess.run(["git", "-C", str(checkout), "-c", "user.name=KLIB Replay Test",
                            "-c", "user.email=klib-replay@example.invalid", "commit", "--quiet",
                            "-m", "Change replay preload"], check=True)
            self.assertFalse(route.git(checkout, "status", "--porcelain"))
            self.assertNotEqual(route.git(checkout, "rev-parse", "HEAD").strip(),
                                candidate.encode())

            actual_run = route.subprocess.run

            def reject_replay(command, *args, **kwargs):
                if "--test" in command:
                    raise AssertionError("replay subprocess reached")
                return actual_run(command, *args, **kwargs)

            with patch.object(route.subprocess, "run", side_effect=reject_replay) as observed:
                with self.assertRaisesRegex(ValueError, "live Node replay preload differs"):
                    route.verify(original, checkout, candidate, receipt["lane"],
                                 receipt["artifact_hashes"], receipt["runtime_identity"],
                                 independent_gates.archive_digest(original), trusted,
                                 replay_node="/usr/local/bin/node")
                self.assertFalse(any("--test" in call.args[0]
                                     for call in observed.call_args_list))

    @unittest.skipUnless(ARCHIVE and TRUSTED, "requires retained real full KLIB archive")
    def test_replay_rejects_unauthenticated_bundle_before_subprocess(self):
        original = Path(ARCHIVE)
        receipt = json.loads((original / "receipt.json").read_bytes())
        if not receipt["lane"].startswith("js:"):
            self.skipTest("requires retained Node bundle")
        trusted = json.loads(Path(TRUSTED).read_bytes())
        candidate = receipt["candidate_sha"]
        lane = receipt["lane"]
        hashes = receipt["artifact_hashes"]
        identity = receipt["runtime_identity"]
        original_digest = independent_gates.archive_digest(original)

        def check(path, digest, reason):
            actual_run = route.subprocess.run

            def reject_replay(command, *args, **kwargs):
                if "--test" in command:
                    raise AssertionError("replay subprocess reached")
                return actual_run(command, *args, **kwargs)

            with patch.object(route.subprocess, "run",
                              side_effect=reject_replay) as observed:
                with self.assertRaisesRegex(ValueError, reason):
                    route.verify(path, REPLAY_REPOSITORY, candidate, lane, hashes, identity,
                                 digest, trusted, replay_node="/usr/local/bin/node")
                self.assertFalse(any("--test" in call.args[0]
                                     for call in observed.call_args_list))

        check(original, "0" * 64, "independent archive provenance digest differs")

        def check_no_replay(repository, node, reason):
            actual_run = route.subprocess.run

            def reject_replay(command, *args, **kwargs):
                if "--test" in command:
                    raise AssertionError("replay subprocess reached")
                return actual_run(command, *args, **kwargs)

            with patch.object(route.subprocess, "run", side_effect=reject_replay) as observed:
                with self.assertRaisesRegex(ValueError, reason):
                    route.verify(original, repository, candidate, lane, hashes, identity,
                                 original_digest, trusted, replay_node=node)
                self.assertFalse(any("--test" in call.args[0]
                                     for call in observed.call_args_list))

        check_no_replay(REPLAY_REPOSITORY, None, "independent Node replay is required")
        check_no_replay(Path(receipt["producer_paths"]["checkout"]), "/usr/local/bin/node",
                        "unrelated clean source checkout")

        tap = (original / "reports/raw/core/node.tap").read_bytes()
        names = re.findall(rb"(?m)^        # Subtest: (.+)$", tap)
        self.assertGreaterEqual(len(names), 2)
        self.assertNotEqual(names[0], names[1])
        changed_tap = tap.replace(names[0], b"__FIRST_METHOD__", 2)
        changed_tap = changed_tap.replace(names[1], names[0], 2)
        changed_tap = changed_tap.replace(b"__FIRST_METHOD__", names[1], 2)
        selected = route._selected_cases(original / "inputs/core-cases.tsv")
        original_ids, _ = route._tap(tap, selected)
        changed_ids, _ = route._tap(changed_tap, selected)
        self.assertEqual(set(changed_ids), set(original_ids))
        self.assertNotEqual(changed_ids, original_ids)
        actual_run = route.subprocess.run

        def changed_replay(command, *args, **kwargs):
            if "--test" in command:
                preload = Path(command[command.index("--require") + 1])
                self.assertNotEqual(preload, REPLAY_REPOSITORY / route.CONSUMER /
                                    "node-test-preload.cjs")
                self.assertEqual(preload.read_bytes(), route.git(
                    REPLAY_REPOSITORY, "show",
                    f"{candidate}:{route.CONSUMER}/node-test-preload.cjs"))
                return subprocess.CompletedProcess(command, 0, changed_tap, b"")
            return actual_run(command, *args, **kwargs)

        with patch.object(route.subprocess, "run", side_effect=changed_replay):
            with self.assertRaisesRegex(ValueError, "method order or outcomes"):
                route.verify(original, REPLAY_REPOSITORY, candidate, lane, hashes, identity,
                             original_digest, trusted, replay_node="/usr/local/bin/node")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "archive"
            shutil.copytree(original, path, copy_function=shutil.copy2)
            program = path / "runtime/bundle/core" / Path(
                json.loads((path / "runtime/core.json").read_bytes())["command"][-1]).name
            program.write_bytes(program.read_bytes() + b"\nreplaced bundle\n")
            check(path, independent_gates.archive_digest(path), "raw file hash differs")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "archive"
            shutil.copytree(original, path, copy_function=shutil.copy2)
            program = path / "runtime/bundle/core" / Path(
                json.loads((path / "runtime/core.json").read_bytes())["command"][-1]).name
            program.unlink()
            program.symlink_to(original / program.relative_to(path))
            check(path, original_digest, "symbolic archive path")

    @unittest.skipUnless(ARCHIVE and TRUSTED, "requires retained real full KLIB archive")
    def test_public_replay_and_resealed_adverse_archive(self):
        original = Path(ARCHIVE)
        receipt = json.loads((original / "receipt.json").read_bytes())
        trusted = json.loads(Path(TRUSTED).read_bytes())
        candidate = receipt["candidate_sha"]
        lane = receipt["lane"]
        hashes = receipt["artifact_hashes"]
        identity = receipt["runtime_identity"]

        def check(path, current_receipt):
            return route.verify(path, REPLAY_REPOSITORY, candidate, lane, hashes, identity,
                                independent_gates.archive_digest(path), trusted,
                                replay_node="/usr/local/bin/node" if lane.startswith("js:") else None)

        self.assertEqual(check(original, receipt)["status"], "PASSED")

        def copied(directory):
            path = Path(directory) / "archive"
            shutil.copytree(original, path, copy_function=shutil.copy2)
            return path, copy.deepcopy(receipt)

        def reseal(path, changed):
            for item in changed["files"]:
                file = path / item["path"]
                os.utime(file, ns=(item["mtime_ns"], item["mtime_ns"]))
                item["sha256"] = route.sha(file.read_bytes())
            (path / "receipt.json").write_bytes(route.encoded(changed) + b"\n")

        with tempfile.TemporaryDirectory() as directory:
            path, changed = copied(directory)
            changed["producer_paths"]["work_root"] = changed["producer_paths"]["checkout"]
            reseal(path, changed)
            with self.assertRaisesRegex(ValueError, "aliases source checkout"):
                check(path, changed)

        with tempfile.TemporaryDirectory() as directory:
            path, changed = copied(directory)
            changed["process"]["command"][-1] = "wrong:lane:task"
            reseal(path, changed)
            with self.assertRaisesRegex(ValueError, "process command differs"):
                check(path, changed)

        with tempfile.TemporaryDirectory() as directory:
            path, changed = copied(directory)
            changed["toolchain"]["java_sha256"] = "0" * 64
            reseal(path, changed)
            with self.assertRaisesRegex(ValueError, "toolchain differs"):
                check(path, changed)

        with tempfile.TemporaryDirectory() as directory:
            path, changed = copied(directory)
            changed["target"] = "wrong-target"
            reseal(path, changed)
            with self.assertRaisesRegex(ValueError, "target differs"):
                check(path, changed)

        with tempfile.TemporaryDirectory() as directory:
            path, changed = copied(directory)
            changed["runtime"] = "wrong-runtime"
            reseal(path, changed)
            with self.assertRaisesRegex(ValueError, "runtime differs"):
                check(path, changed)

        with tempfile.TemporaryDirectory() as directory:
            path, changed = copied(directory)
            graph_path = path / "provider-graph.json"
            graph = json.loads(graph_path.read_bytes())
            provider = next(item for item in graph["compile"][0]["artifacts"]
                            if item["component"].startswith("io.github.rubixhacker:"))
            provider["file"] = str(REPOSITORY / "build/source-project-binary.klib")
            graph_path.write_bytes(route.encoded(graph))
            reseal(path, changed)
            with self.assertRaisesRegex(ValueError, "resolved external KLIB differs"):
                check(path, changed)

        with tempfile.TemporaryDirectory() as directory:
            path, changed = copied(directory)
            binary = path / changed["resolved_artifacts"]["dyn4k-core"]
            binary.write_bytes(binary.read_bytes() + b"changed")
            reseal(path, changed)
            with self.assertRaisesRegex(ValueError, "resolved external KLIB differs"):
                check(path, changed)

        if lane.startswith("linuxX64:"):
            raw = receipt["raw_consumer_xml"][0]
            with tempfile.TemporaryDirectory() as directory:
                path, changed = copied(directory)
                xml_path = path / raw
                suite = ET.fromstring(xml_path.read_bytes())
                suite.append(copy.deepcopy(next(suite.iter("testcase"))))
                suite.set("tests", str(int(suite.get("tests")) + 1))
                xml_path.write_bytes(ET.tostring(suite))
                reseal(path, changed)
                with self.assertRaisesRegex(ValueError, "duplicate"):
                    check(path, changed)
            with tempfile.TemporaryDirectory() as directory:
                path, changed = copied(directory)
                xml_path = path / raw
                suite = ET.fromstring(xml_path.read_bytes())
                suite.remove(next(suite.iter("testcase")))
                xml_path.write_bytes(ET.tostring(suite))
                reseal(path, changed)
                with self.assertRaisesRegex(ValueError, "native raw XML records missing"):
                    check(path, changed)
            with tempfile.TemporaryDirectory() as directory:
                path, changed = copied(directory)
                xml_path = path / raw
                suite = ET.fromstring(xml_path.read_bytes())
                next(suite.iter("testcase")).set("name", "fabricated[linuxX64]")
                xml_path.write_bytes(ET.tostring(suite))
                reseal(path, changed)
                with self.assertRaisesRegex(ValueError, "native raw case is foreign"):
                    check(path, changed)
        else:
            tap = receipt["raw_consumer_tap"][0]
            with tempfile.TemporaryDirectory() as directory:
                path, changed = copied(directory)
                tap_path = path / tap
                tap_path.write_bytes(tap_path.read_bytes().replace(b"# pass 2465", b"# pass 2464"))
                reseal(path, changed)
                with self.assertRaisesRegex(ValueError, "Node TAP summary differs"):
                    check(path, changed)
            with tempfile.TemporaryDirectory() as directory:
                path, changed = copied(directory)
                normal = path / "reports/normalized/core/TEST-Node.xml"
                suite = ET.fromstring(normal.read_bytes())
                next(suite.iter("testcase")).set("id", "fabricated:id")
                normal.write_bytes(ET.tostring(suite))
                reseal(path, changed)
                with self.assertRaisesRegex(ValueError, "normalized full KLIB method IDs differ"):
                    check(path, changed)


if __name__ == "__main__":
    unittest.main()
