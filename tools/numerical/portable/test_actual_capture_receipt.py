import ast
import copy
import hashlib
import io
import json
import os
import re
import tarfile
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import actual_arithmetic as actual
from capture_actual import ENVIRONMENT_SENTINEL, reject_environment_trace
from actual_arithmetic import (CaptureRejected, _AUDITED_ENGINE_CLASSES,
                               _FIXTURE_CLASSES, _ROOT, _STAGED_JAR,
                               _WHEEL_RECORDER_CLASSES,
                               _inspect_worker_classpath,
                               make_capture_receipt,
                               verify_capture_receipt)
from test_actual_arithmetic import fixture, focused_wheel_fixture, xml_for
from test_rotation_marker import bits, marker


class RetainedFixtureProviderTest(unittest.TestCase):
    def _retained(self):
        archive = os.environ.get("DYN4K_ROTATION_ARCHIVE")
        origin_name = os.environ.get("DYN4K_ROTATION_ORIGIN")
        if archive is None or origin_name is None:
            self.skipTest("retained local fixture archive is unavailable")
        from external_rotation_binding import _load
        origin = Path(origin_name).resolve()
        receipt, files, method = _load(archive, origin)
        return receipt, files, method, origin

    def test_resealed_alternate_fixture_provider_fails(self):
        receipt, original, method, origin = self._retained()
        files = dict(original)
        fixture_name = "portable/RotationPremiseFixtureTest.class"
        with zipfile.ZipFile(io.BytesIO(files["portable_classes"])) as classes:
            compiled = classes.read("test/" + fixture_name)
            source_name = b"RotationPremiseFixtureTest.kt"
            self.assertEqual(compiled.count(source_name), 1)
            altered = compiled.replace(source_name, b"RotationPremiseText.kt")
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as folder:
            shadow = Path(folder) / "alternate.jar"
            with zipfile.ZipFile(shadow, "w") as classes:
                classes.writestr(fixture_name, altered)
            classpath = files["worker_classpath"].decode().splitlines()
            files["worker_classpath"] = (
                f"-cp\n{shadow}:{classpath[1]}\n").encode()
            resealed = copy.deepcopy(receipt)
            resealed["worker_classpath_sha256"] = hashlib.sha256(
                files["worker_classpath"]).hexdigest()
            resealed["worker_classpath_entries"].insert(0, {
                "path": str(shadow),
                "sha256": hashlib.sha256(shadow.read_bytes()).hexdigest(),
            })
            for redirect_load in (False, True):
                if redirect_load:
                    test_root = (origin / "tools/numerical/portable/build/classes/"
                                 "kotlin/jvm/test")
                    files["worker_class_load"] = files["worker_class_load"].replace(
                        test_root.as_uri().encode() + b"/", shadow.as_uri().encode())
                    resealed["worker_class_load_sha256"] = hashlib.sha256(
                        files["worker_class_load"]).hexdigest()
                with self.subTest(redirect_load=redirect_load), self.assertRaises(
                        CaptureRejected):
                    verify_capture_receipt(
                        resealed, files, method, receipt["candidate_commit"],
                        ["rotation-premise-mode", "rotation-premise-zero",
                         "rotation-premise-negative-zero", "rotation-premise-tiny-angle",
                         "rotation-premise-subnormal-product"],
                        receipt["runtime_executable"])

    def test_resealed_missing_or_redirected_fixture_load_fails(self):
        receipt, original, method, origin = self._retained()
        lines = original["worker_class_load"].splitlines(keepends=True)
        for changed in (
                [line for line in lines if b"RotationPremiseFixtureTest$SeededTransform "
                 not in line],
                [line.replace(b"RotationPremiseFixtureTest source: file:",
                              b"RotationPremiseFixtureTest source: file:/other/")
                 for line in lines],
                [line.replace(b"source: portable.RotationPremiseFixtureTest",
                              b"source: file:/other/fixture.jar")
                 if b"RotationPremiseFixtureTest$$Lambda/" in line else line
                 for line in lines]):
            files = dict(original)
            files["worker_class_load"] = b"".join(changed)
            resealed = copy.deepcopy(receipt)
            resealed["worker_class_load_sha256"] = hashlib.sha256(
                files["worker_class_load"]).hexdigest()
            with self.subTest(changed_load=hashlib.sha256(
                    files["worker_class_load"]).hexdigest()), self.assertRaises(
                    CaptureRejected):
                verify_capture_receipt(
                    resealed, files, method, receipt["candidate_commit"],
                    ["rotation-premise-mode", "rotation-premise-zero",
                     "rotation-premise-negative-zero", "rotation-premise-tiny-angle",
                     "rotation-premise-subnormal-product"], receipt["runtime_executable"])


class RetainedWheelProviderTest(unittest.TestCase):
    def _retained(self):
        archive_name = os.environ.get("DYN4K_WHEEL_ARCHIVE")
        origin_name = os.environ.get("DYN4K_WHEEL_ORIGIN")
        if archive_name is None or origin_name is None:
            self.skipTest("retained Wheel archive is unavailable")
        archive = Path(archive_name)
        origin = Path(origin_name)
        names = {
            "xml": "capture.xml", "stage_log": "stage.log",
            "gradle_log": "gradle.log", "execve_log": "execve.log",
            "artifact": "artifact.jar", "runtime": "runtime-java",
            "source": "source.tar", "worker_classpath": "worker-classpath.txt",
            "portable_classes": "portable-classes.zip",
            "worker_write_traces": "worker-write-traces.zip",
        }
        files = {key: (archive / name).read_bytes() for key, name in names.items()}
        logs = list(archive.glob("worker-class-load-*.log"))
        self.assertEqual(len(logs), 1)
        files["worker_class_load"] = logs[0].read_bytes()
        receipt = json.loads((archive / "receipt.json").read_bytes())
        staged = (origin / "build/staging-repository/io/github/rubixhacker/"
                  "dyn4k-core-jvm/0.1.0-alpha.1/"
                  "dyn4k-core-jvm-0.1.0-alpha.1.jar")
        args = ("captureWheelActive", receipt["candidate_commit"],
                ["joint-Wheel-active"], receipt["runtime_executable"])
        return receipt, files, origin, staged, args

    def test_unchanged_wheel_receipt_verifies(self):
        receipt, files, origin, staged, args = self._retained()
        with patch.object(actual, "_ROOT", origin), patch.object(
                actual, "_STAGED_JAR", staged):
            result = verify_capture_receipt(receipt, files, *args)
        self.assertEqual(result["status"], "UNPASSED_DYNAMIC_CLASS_LOAD")
        self.assertEqual(result["operation_record_status"],
                         "VERIFIED_ARITHMETIC_BINDING")
        self.assertEqual(result["dynamic_class_load_status"], "UNBOUND")
        self.assertEqual(result["qualification"], "UNPASSED")
        self.assertEqual(result["operations_verified"], 1800)
        self.assertEqual(result["kernel_class_load_write_witness"], {
            "status": "MATCHED_COMPLETE_WRITES_UNBOUND_DESTINATION",
            "records": 2796, "writer_threads": 7})
        self.assertEqual(receipt["summary"]["status"],
                         "VERIFIED_ARITHMETIC_BINDING")

    def _verify_resealed(self, receipt, original, origin, staged, args, key, changed):
        files = dict(original)
        files[key] = changed
        resealed = copy.deepcopy(receipt)
        resealed[f"{key}_sha256"] = hashlib.sha256(changed).hexdigest()
        with patch.object(actual, "_ROOT", origin), patch.object(
                actual, "_STAGED_JAR", staged):
            return verify_capture_receipt(resealed, files, *args)

    def _alter_class_write(self, archive, variant):
        output = io.BytesIO()
        changed = False
        with zipfile.ZipFile(io.BytesIO(archive)) as old, zipfile.ZipFile(output, "w") as new:
            for name in old.namelist():
                lines = old.read(name).splitlines(keepends=True)
                for index, line in enumerate(lines):
                    if changed or not line.startswith(b"write(") or \
                            b"[class,load]" not in line:
                        continue
                    changed = True
                    if variant == "missing":
                        del lines[index]
                    elif variant == "duplicate":
                        lines.insert(index, line)
                    elif variant == "partial":
                        before, count = line.rstrip(b"\n").rsplit(b" = ", 1)
                        lines[index] = before + b" = " + str(int(count) - 1).encode() + b"\n"
                    elif variant == "second_fd":
                        lines[index] = re.sub(rb"^write\([0-9]+,", b"write(97,", line)
                    elif variant == "altered":
                        lines[index] = re.sub(
                            rb"(\[class,load\] )([A-Za-z])",
                            lambda match: match.group(1) +
                            (b"X" if match.group(2) != b"X" else b"Y"), line,
                            count=1)
                        self.assertNotEqual(lines[index], line)
                    elif variant == "untrusted":
                        lines.insert(index, b"untrusted [class,load] text\n")
                    elif variant == "split_untrusted":
                        match = actual._WITNESS_WRITE.fullmatch(line.decode().rstrip("\n"))
                        self.assertIsNotNone(match)
                        existing = ast.literal_eval("b" + match.group(2))
                        pid = existing.split(b"]", 1)[0][1:].decode()
                        record = (f'[{pid}][info][class,load] '
                                  'java.lang.Fabricated source: jrt:/java.base\n').encode()
                        split = record.index(b"[class,load]") + 4
                        fragments = (record[:split], record[split:])
                        writes = [
                            (f'write(4, {json.dumps(part.decode())}, {len(part)}) = '
                             f'{len(part)}\n').encode() for part in fragments]
                        lines[index:index] = writes
                    else:
                        self.fail("unknown write mutation")
                new.writestr(name, b"".join(lines))
        self.assertTrue(changed)
        return output.getvalue()

    def test_resealed_class_load_log_requires_kernel_write_membership(self):
        receipt, original, origin, staged, args = self._retained()
        lines = original["worker_class_load"].splitlines(keepends=True)
        ordinary = next(line for line in lines if b" portable." not in line and
                        b" org.dyn4j." not in line)
        fabricated = (f'[{receipt["worker_pid"]}][info][class,load] '
                      'java.lang.Fabricated source: jrt:/java.base\n').encode()
        variants = {
            "duplicate": original["worker_class_load"] + ordinary,
            "fabricated": original["worker_class_load"] + fabricated,
            "missing": original["worker_class_load"].replace(ordinary, b"", 1),
        }
        for name, changed in variants.items():
            reason = ("duplicate kernel class-load record" if name == "duplicate"
                      else "kernel class-load write")
            with self.subTest(name=name), self.assertRaisesRegex(
                    CaptureRejected, reason):
                self._verify_resealed(receipt, original, origin, staged, args,
                                      "worker_class_load", changed)

    def test_resealed_kernel_class_load_writes_require_complete_single_fd_match(self):
        receipt, original, origin, staged, args = self._retained()
        for variant in ("missing", "duplicate", "altered", "partial",
                        "second_fd", "untrusted", "split_untrusted"):
            changed = self._alter_class_write(original["worker_write_traces"], variant)
            with self.subTest(variant=variant), self.assertRaisesRegex(
                    CaptureRejected, "kernel class-load write"):
                self._verify_resealed(receipt, original, origin, staged, args,
                                      "worker_write_traces", changed)

    def test_resealed_matching_duplicate_log_and_kernel_write_rejects(self):
        receipt, original, origin, staged, args = self._retained()
        with zipfile.ZipFile(io.BytesIO(original["worker_write_traces"])) as traces:
            record = next(
                ast.literal_eval("b" + match.group(2))
                for name in traces.namelist()
                for line in traces.read(name).decode().splitlines()
                if (match := actual._WITNESS_WRITE.fullmatch(line)) is not None and
                "[class,load]" in line)
        self.assertNotIn(b" portable.", record)
        self.assertNotIn(b" org.dyn4j.", record)
        files = dict(original)
        files["worker_class_load"] += record
        files["worker_write_traces"] = self._alter_class_write(
            original["worker_write_traces"], "duplicate")
        resealed = copy.deepcopy(receipt)
        for key in ("worker_class_load", "worker_write_traces"):
            resealed[f"{key}_sha256"] = hashlib.sha256(files[key]).hexdigest()
        with patch.object(actual, "_ROOT", origin), patch.object(
                actual, "_STAGED_JAR", staged), self.assertRaisesRegex(
                CaptureRejected, "duplicate kernel class-load record"):
            verify_capture_receipt(resealed, files, *args)

    def test_resealed_kernel_trace_requires_exact_worker_descendants(self):
        receipt, original, origin, staged, args = self._retained()
        with zipfile.ZipFile(io.BytesIO(original["worker_write_traces"])) as archive:
            members = {name: archive.read(name) for name in archive.namelist()}
        child = next(name for name in members if name != f'trace.{receipt["worker_pid"]}')
        for variant in ("missing_child", "extra_thread"):
            changed_members = dict(members)
            if variant == "missing_child":
                del changed_members[child]
            else:
                changed_members["trace.999999"] = b"unrelated trace\n"
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as archive:
                for name, content in changed_members.items():
                    archive.writestr(name, content)
            with self.subTest(variant=variant), self.assertRaisesRegex(
                    CaptureRejected, "worker write"):
                self._verify_resealed(receipt, original, origin, staged, args,
                                      "worker_write_traces", output.getvalue())

    def test_resealed_duplicate_fabricated_or_missing_lambda_rejects(self):
        receipt, original, origin, staged, args = self._retained()
        lines = original["worker_class_load"].splitlines(keepends=True)
        lambdas = [line for line in lines if b"portable." in line and
                   b"$$Lambda/" in line]
        self.assertGreater(len(lambdas), 1)
        fabricated = (
            f'[{receipt["worker_pid"]}][info][class,load] '
            'portable.NumericalRecorder$$Lambda/0xdeadbeef '
            'source: portable.NumericalRecorder\n').encode()
        variants = {
            "duplicate": original["worker_class_load"] + lambdas[0],
            "fabricated": original["worker_class_load"] + fabricated,
            "missing": b"".join(line for line in lines if line != lambdas[0]),
            "missing_all": b"".join(line for line in lines
                                    if b"$$Lambda/" not in line),
        }
        for name, changed in variants.items():
            files = dict(original)
            files["worker_class_load"] = changed
            resealed = copy.deepcopy(receipt)
            resealed["worker_class_load_sha256"] = hashlib.sha256(changed).hexdigest()
            with self.subTest(name=name), patch.object(
                    actual, "_ROOT", origin), patch.object(
                    actual, "_STAGED_JAR", staged):
                if name == "duplicate":
                    with self.assertRaisesRegex(CaptureRejected,
                                                "duplicate portable lambda"):
                        verify_capture_receipt(resealed, files, *args)
                else:
                    with self.assertRaisesRegex(CaptureRejected,
                                                "kernel class-load write"):
                        verify_capture_receipt(resealed, files, *args)

    def test_lambda_owner_must_have_an_ordinary_load(self):
        receipt, original, origin, staged, args = self._retained()
        with zipfile.ZipFile(io.BytesIO(original["portable_classes"])) as classes:
            owners = (name.split("/", 1)[1].removesuffix(".class").replace("/", ".")
                      for name in classes.namelist() if name.endswith(".class") and
                      "/portable/" in name)
            owner = next(name for name in owners if
                         f" {name} source:".encode() not in
                         original["worker_class_load"])
        added = (f'[{receipt["worker_pid"]}][info][class,load] '
                 f'{owner}$$Lambda/0xdeadbeef source: {owner}\n').encode()
        files = dict(original)
        files["worker_class_load"] += added
        resealed = copy.deepcopy(receipt)
        resealed["worker_class_load_sha256"] = hashlib.sha256(
            files["worker_class_load"]).hexdigest()
        with patch.object(actual, "_ROOT", origin), patch.object(
                actual, "_STAGED_JAR", staged), self.assertRaisesRegex(
                CaptureRejected, "portable lambda owner was not loaded"):
            verify_capture_receipt(resealed, files, *args)

    def test_resealed_earlier_and_later_portable_provider_fail(self):
        receipt, original, origin, staged, args = self._retained()
        with zipfile.ZipFile(io.BytesIO(original["portable_classes"])) as classes:
            compiled = classes.read("test/portable/ProspectiveArithmeticTest.class")
        altered = compiled.replace(b"ProspectiveArithmeticTest.kt",
                                   b"ProspectiveArithmeticTesx.kt")
        self.assertNotEqual(altered, compiled)
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as folder:
            shadow = Path(folder) / "alternate.jar"
            with zipfile.ZipFile(shadow, "w") as classes:
                classes.writestr("portable/ProspectiveArithmeticTest.class", altered)
            classpath = original["worker_classpath"].decode().splitlines()
            self.assertEqual(classpath[0], "-cp")
            for earlier in (True, False):
                files = dict(original)
                entries = (f"{shadow}:{classpath[1]}" if earlier else
                           f"{classpath[1]}:{shadow}")
                files["worker_classpath"] = f"-cp\n{entries}\n".encode()
                resealed = copy.deepcopy(receipt)
                resealed["worker_classpath_sha256"] = hashlib.sha256(
                    files["worker_classpath"]).hexdigest()
                evidence = {"path": str(shadow),
                            "sha256": hashlib.sha256(shadow.read_bytes()).hexdigest()}
                if earlier:
                    resealed["worker_classpath_entries"].insert(0, evidence)
                else:
                    resealed["worker_classpath_entries"].append(evidence)
                with self.subTest(earlier=earlier), patch.object(
                        actual, "_ROOT", origin), patch.object(
                        actual, "_STAGED_JAR", staged), self.assertRaises(CaptureRejected):
                    verify_capture_receipt(resealed, files, *args)

    def test_missing_unknown_and_duplicate_portable_load_fail(self):
        receipt, original, origin, staged, args = self._retained()
        lines = original["worker_class_load"].splitlines(keepends=True)
        required = (
            b"portable.ProspectiveArithmeticTest ",
            b"portable.PortableMatrixTest ",
            b"portable.NumericalRecorder ",
            b"portable.NumericalRecorder$capture$collisions$1 ",
            b"portable.NumericalRecorder$capture$contacts$1 ",
            b"portable.NumericalRecorder$capture$steps$1 ",
            b"portable.NumericalRecorder$capture$timeOfImpact$1 ",
            b"portable.NumericalRecorder$json$$inlined$sortedBy$1 ",
        )
        for target in required:
            changed = [line for line in lines if target not in line]
            self.assertEqual(len(lines) - len(changed), 1)
            files = dict(original)
            files["worker_class_load"] = b"".join(changed)
            with self.subTest(missing=target), patch.object(
                    actual, "_ROOT", origin), patch.object(
                    actual, "_STAGED_JAR", staged), self.assertRaises(CaptureRejected):
                make_capture_receipt(files, *args)
        test_root = (origin / "tools/numerical/portable/build/classes/kotlin/jvm/test")
        additions = (
            (f'[{receipt["worker_pid"]}][info][class,load] portable.Unknown '
             f'source: {test_root.as_uri()}/\n').encode(),
            next(line for line in lines if b"portable.ProspectiveArithmeticTest " in line),
        )
        for added in additions:
            files = dict(original)
            files["worker_class_load"] += added
            with self.subTest(added=hashlib.sha256(added).hexdigest()), patch.object(
                    actual, "_ROOT", origin), patch.object(
                    actual, "_STAGED_JAR", staged), self.assertRaises(CaptureRejected):
                make_capture_receipt(files, *args)


class CaptureReceiptTest(unittest.TestCase):
    def setUp(self):
        source = patch("actual_arithmetic._source_archive", return_value=b"source")
        source.start()
        self.addCleanup(source.stop)
        binaries = patch("actual_arithmetic._check_local_binaries")
        binaries.start()
        self.addCleanup(binaries.stop)
        classpath = patch("actual_arithmetic._inspect_worker_classpath",
                          return_value=[{"path": str(_STAGED_JAR), "sha256": "0" * 64}])
        classpath.start()
        self.addCleanup(classpath.stop)
    def fixture(self):
        xml = xml_for(fixture())
        runtime = "/tmp/dyn4k-tools/jdk21/bin/java"
        log_pattern = Path.home() / "dyn4k-evidence/worker-class-load-%p.log"
        log_option = (f"-Xlog:class+load=info:file={log_pattern}:"
                      "pid,level,tags:filecount=0")
        log = (f"Starting process 'Gradle Test Executor 1'. Command: {runtime} "
               f"@/tmp/gradle-worker-classpath1txt {log_option} "
               "worker.org.gradle.process.internal.worker.GradleWorkerMain\n"
               "BUILD SUCCESSFUL\n").encode()
        execve = (f'122 execve("{_ROOT / "gradlew"}", ["gradlew", '
                  '"jvmTest", "--tests", '
                  '"portable.ProspectiveArithmeticTest.captureGeometry", '
                  f'"-PportableWorkerClassLoadLog={log_pattern}"], 0x0) = 0\n'
                  f'123 execve("{runtime}", ["{runtime}", '
                  '"@/tmp/gradle-worker-classpath1txt", '
                  f'"{log_option}", '
                  '"worker.org.gradle.process.internal.worker.GradleWorkerMain"], 0x0) = 0\n').encode()
        load = "".join(f"[123][info][class,load] "
                       f"{name.removesuffix('.class').replace('/', '.')} "
                       f"source: {_STAGED_JAR.as_uri()}\n"
                       for name in sorted(_AUDITED_ENGINE_CLASSES)).encode()
        class_root = _ROOT / "tools/numerical/portable/build/classes/kotlin/jvm"
        load += "".join(f"[123][info][class,load] {name} "
                        f"source: {(class_root / source_set).as_uri()}/\n"
                        for source_set, name in (
                            ("main", "portable.NumericalRecorder"),
                            ("test", "portable.PortableMatrixTest"),
                            ("test", "portable.ProspectiveArithmeticTest"))).encode()
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as classes:
            for name in ("main/portable/NumericalRecorder.class",
                         "test/portable/ProspectiveArithmeticTest.class",
                         "test/portable/PortableMatrixTest.class"):
                classes.writestr(name, b"class")
        files = {"xml": xml, "stage_log": b"BUILD SUCCESSFUL\n",
                 "gradle_log": log, "execve_log": execve,
                 "artifact": b"artifact", "runtime": b"runtime", "source": b"source",
                 "worker_classpath": (f"-cp\n{_STAGED_JAR}:{class_root / 'main'}:"
                                      f"{class_root / 'test'}\n").encode(),
                 "worker_class_load": load,
                 "portable_classes": payload.getvalue()}
        receipt = make_capture_receipt(files, "captureGeometry", "a" * 40,
                                       ["geometry-boundary-s0-o0-d0"], runtime)
        return receipt, files, runtime

    def test_sealed_capture_keeps_case_policy_unpassed(self):
        receipt, files, runtime = self.fixture()
        result = verify_capture_receipt(receipt, files, "captureGeometry", "a" * 40,
                                        ["geometry-boundary-s0-o0-d0"], runtime)
        self.assertEqual(result["status"], "UNPASSED_DYNAMIC_CLASS_LOAD")
        self.assertEqual(result["operation_record_status"],
                         "VERIFIED_ARITHMETIC_BINDING")
        self.assertEqual(result["dynamic_class_load_status"], "UNBOUND")
        self.assertEqual(result["qualification"], "UNPASSED")
        self.assertEqual(result["operations_verified"], 1)

    def test_boolean_source_call_sites_reject_one_changed_branch(self):
        sites = [("b1", "integrate"), ("b0", None), ("b1", None)]
        markers = [{"step": 1, "sequence": index, "body_id": body,
                    "branch": branch, "kind": "rotate"}
                   for index, (body, branch) in enumerate(sites)]
        actual._require_focused_boolean_step_calls(markers, 1)
        markers[1]["branch"] = "joint"
        with self.assertRaisesRegex(CaptureRejected, "source call schedule"):
            actual._require_focused_boolean_step_calls(markers, 1)

    def test_optional_indexed_boolean_reference_hash_catalog_and_origin(self):
        origin_name = os.environ.get("DYN4K_BOOLEAN_REFERENCE_ORIGIN")
        if not origin_name:
            self.skipTest("indexed Boolean reference origin is not configured")
        case_id = "joint-Revolute-LimitsEnabled-false"
        origin = Path(origin_name)
        reference = origin / "baseline-jvm" / "cases" / f"{case_id}.jsonl"
        if not reference.is_file():
            self.skipTest("indexed Boolean reference archive is unavailable")
        reference_bytes = reference.read_bytes()
        self.assertEqual(hashlib.sha256(reference_bytes).hexdigest(),
                         actual._FOCUSED_BOOLEAN_REFERENCE_SHA256)
        catalog_entry = actual.load_policy_catalog()["cases"][case_id]
        self.assertEqual(catalog_entry["sha256"],
                         actual._FOCUSED_BOOLEAN_REFERENCE_SHA256)
        header, separator, _ = reference_bytes.partition(b"\n")
        self.assertEqual(separator, b"\n")
        header_bytes = header + separator
        fixture = (Path(__file__).resolve().parent / "boolean_rotation_jdi" /
                   "fixtures" / "revolute-limits-false-header.jsonl")
        self.assertEqual(hashlib.sha256(header_bytes).hexdigest(),
                         actual._FOCUSED_BOOLEAN_INPUT_SHA256)
        self.assertEqual(header_bytes, fixture.read_bytes())

    def test_synthetic_boolean_xml_covers_all_steps_but_stays_unpassed(self):
        fixture = (Path(__file__).resolve().parent / "boolean_rotation_jdi" /
                   "fixtures" / "revolute-limits-false-header.jsonl")
        header_bytes = fixture.read_bytes()
        self.assertEqual(len(header_bytes), 4470)
        self.assertTrue(header_bytes.endswith(b"\n"))
        self.assertEqual(hashlib.sha256(header_bytes).hexdigest(),
                         actual._FOCUSED_BOOLEAN_INPUT_SHA256)
        header = header_bytes.decode("utf-8").rstrip("\n")
        case_id = "joint-Revolute-LimitsEnabled-false"
        body_rows = json.loads(header)["initial"]["bodies"]
        identity = [bits(1.0), bits(0.0)]
        rows = ["NUMERICAL_JSON " + header]
        for step in range(1, 601):
            for index, (body_id, branch) in enumerate((
                    ("b1", "integrate"), ("b0", None), ("b1", None))):
                call = marker()
                call.update(method="independentJointBooleanModes", case_id=case_id,
                            step=step, sequence=(step - 1) * 3 + index,
                            body_id=body_id, target_token=int(body_id[1:]),
                            branch=branch, source="pivot" if branch is None else "origin")
                rows.append("PROSPECTIVE_ROTATION_JSON " + json.dumps(call))
            state = {"kind": "state", "id": case_id, "step": step, "order": 0,
                     "state": {"bodies": body_rows}}
            rows.append("NUMERICAL_JSON " + json.dumps(state))
            receipt = {"kind": "body-step", "case_id": case_id, "step": step,
                       "bodies": [{"body_id": "b0", "calls": 1, "pre": identity,
                                   "post": identity},
                                  {"body_id": "b1", "calls": 2, "pre": identity,
                                   "post": identity}], "temporary_calls": 0}
            rows.append("PROSPECTIVE_BINDING_JSON " + json.dumps(receipt))
        rows.append("NUMERICAL_JSON " + json.dumps(
            {"kind": "case-end", "id": case_id, "steps": 600}))
        xml = xml_for(rows, "captureRevoluteLimitsFalse").replace(
            b"portable.ProspectiveArithmeticTest",
            b"portable.RevoluteLimitsFalseCaptureTest")
        summary = actual.verify_capture(xml, "captureRevoluteLimitsFalse", [case_id])
        self.assertEqual((summary["cases"], summary["steps"],
                          summary["operations_verified"]), (1, 600, 1800))
        self.assertEqual(summary["status"], "UNPASSED_SOURCE_CALL_SITE")
        self.assertEqual(summary["qualification"], "UNPASSED")
        marker_line = next(line for line in rows
                           if line.startswith("PROSPECTIVE_ROTATION_JSON "))
        variants = {
            "branch": xml.replace(b'"branch": null', b'"branch": "joint"', 1),
            "class": xml.replace(b"portable.RevoluteLimitsFalseCaptureTest",
                                 b"portable.ProspectiveArithmeticTest", 1),
            "method": xml.replace(b"captureRevoluteLimitsFalse[jvm]",
                                  b"captureJointBooleanModes[jvm]", 1),
            "missing_call": xml.replace((marker_line + "\n").encode(), b"", 1),
            "changed_input": xml.replace(b'"steps": 600', b'"steps": 599', 1),
        }
        for name, changed in variants.items():
            self.assertNotEqual(changed, xml)
            with self.subTest(name=name), self.assertRaises(CaptureRejected):
                actual.verify_capture(changed, "captureRevoluteLimitsFalse", [case_id])

    def test_boolean_process_requires_distinct_compiled_fixture_selector(self):
        _, files, runtime = self.fixture()
        old = b"portable.ProspectiveArithmeticTest.captureGeometry"
        new = b"portable.RevoluteLimitsFalseCaptureTest.captureRevoluteLimitsFalse"
        files["execve_log"] = files["execve_log"].replace(old, new)
        buffer = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(files["portable_classes"])) as old_zip, \
                zipfile.ZipFile(buffer, "w") as new_zip:
            for name in old_zip.namelist():
                new_zip.writestr(name, old_zip.read(name))
            new_zip.writestr("test/portable/RevoluteLimitsFalseCaptureTest.class",
                             b"compiled fixture")
        files["portable_classes"] = buffer.getvalue()
        _, pid, _, classes = actual._check_process(
            files, runtime, "captureRevoluteLimitsFalse")
        self.assertEqual(pid, "123")
        self.assertIn("portable/RevoluteLimitsFalseCaptureTest.class", classes["test"])
        with self.assertRaisesRegex(CaptureRejected, "JDI"):
            actual._check_process(files, runtime, "captureRevoluteLimitsFalse",
                                  jdi_port=40001)
        option = ("-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,"
                  "address=127.0.0.1:40001")
        files["gradle_log"] = files["gradle_log"].replace(
            b"worker.org.gradle.process.internal.worker.GradleWorkerMain",
            option.encode() + b" worker.org.gradle.process.internal.worker.GradleWorkerMain")
        files["execve_log"] = files["execve_log"].replace(
            b'"worker.org.gradle.process.internal.worker.GradleWorkerMain"',
            f'"{option}", "worker.org.gradle.process.internal.worker.GradleWorkerMain"'.encode())
        files["execve_log"] = files["execve_log"].replace(
            b'"-PportableWorkerClassLoadLog=',
            b'"-PportableBooleanJdiPort=40001", '
            b'"-PportableBooleanJdiMethod=captureRevoluteLimitsFalse", '
            b'"-PportableWorkerClassLoadLog=')
        actual._check_process(files, runtime, "captureRevoluteLimitsFalse", jdi_port=40001)
        files["execve_log"] = files["execve_log"].replace(new, old)
        with self.assertRaisesRegex(CaptureRejected, "capture method"):
            actual._check_process(files, runtime, "captureRevoluteLimitsFalse")
        files["execve_log"] = files["execve_log"].replace(old, new)
        with zipfile.ZipFile(io.BytesIO(files["portable_classes"])) as classes_zip:
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as missing:
                for name in classes_zip.namelist():
                    if name != "test/portable/RevoluteLimitsFalseCaptureTest.class":
                        missing.writestr(name, classes_zip.read(name))
        files["portable_classes"] = buffer.getvalue()
        with self.assertRaisesRegex(CaptureRejected, "portable test payload"):
            actual._check_process(files, runtime, "captureRevoluteLimitsFalse")

    def test_jdi_receipt_requires_versioned_complete_transport(self):
        _, files, runtime = self.fixture()
        files["jdi_evidence"] = b"forged"
        with self.assertRaisesRegex(CaptureRejected, "JDI receipt inventory"):
            actual.make_capture_receipt(files, "captureGeometry", "a" * 40,
                                        ["geometry-Square"], runtime)
        for value in (b"{}", b'{"schema":"boolean-jdi-transport/1"}',
                      b'{"port":40001,"port":40002}'):
            with self.assertRaises(CaptureRejected):
                actual._verify_boolean_jdi({"jdi_transport": value}, {}, "123")

    def test_boolean_source_pin_rejects_changed_jvm_fixture(self):
        name = ("tools/numerical/portable/src/jvmTest/kotlin/portable/"
                "RevoluteLimitsFalseCaptureTest.kt")
        source = (actual._ROOT / name).read_bytes()
        def archive(payload):
            output = io.BytesIO()
            with tarfile.open(fileobj=output, mode="w") as tar:
                member = tarfile.TarInfo(name)
                member.size = len(payload)
                tar.addfile(member, io.BytesIO(payload))
            return output.getvalue()
        actual._verify_boolean_source(archive(source))
        with self.assertRaisesRegex(CaptureRejected, "source schedule"):
            actual._verify_boolean_source(archive(source + b"\n"))
        empty = io.BytesIO()
        with tarfile.open(fileobj=empty, mode="w"):
            pass
        with self.assertRaisesRegex(CaptureRejected, "source inventory"):
            actual._verify_boolean_source(empty.getvalue())

    def test_startup_log_requires_exact_effective_classpath_and_writes(self):
        pid = "123"
        response = b"-cp\n/engine.jar:/compiled/main:/compiled/test\n"
        home = Path.home()
        option = (f"-Xlog:arguments=info:file={home}/evidence/"
                  "worker-arguments-%p.log:pid,level,tags:filecount=0")
        records = ["VM Arguments:", "jvm_args: " + option,
                   "java_command: worker.org.gradle.process.internal.worker.GradleWorkerMain",
                   "java_class_path (initial): /engine.jar:/compiled/main:/compiled/test",
                   "Launcher Type: SUN_STANDARD"]
        raw = "".join(f"[{pid}][info][arguments] {row}\n" for row in records).encode()
        def trace(payload):
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as archive:
                archive.writestr("trace.123", b"execve(dummy) = 0\n"
                                 b"clone3(dummy) = 124\n")
                archive.writestr("trace.124", b"".join(
                    f'write(4, {json.dumps(line.decode())}, {len(line)}) = '
                    f'{len(line)}\n'.encode() for line in payload.splitlines(keepends=True)))
            return output.getvalue()
        witness = actual._verify_worker_argument_log(raw, response, trace(raw), pid)
        self.assertEqual(witness["status"],
                         "MATCHED_INITIAL_CLASSPATH_WRITES_UNBOUND_DESTINATION")
        with tempfile.TemporaryDirectory(dir=home) as alternate_home, \
                patch.dict(os.environ, {"HOME": alternate_home}):
            alternate_raw = raw.replace(str(home).encode(), alternate_home.encode())
            alternate_witness = actual._verify_worker_argument_log(
                alternate_raw, response, trace(alternate_raw), pid)
            self.assertEqual(
                alternate_witness["status"],
                "MATCHED_INITIAL_CLASSPATH_WRITES_UNBOUND_DESTINATION")
        for name, candidate, saved_response, writes in (
                ("override", raw.replace(b"/engine.jar:", b"/other.jar:", 1),
                 response, trace(raw)),
                ("response", raw, response.replace(b"/engine.jar:", b"/other.jar:", 1),
                 trace(raw)),
                ("wrong_pid", raw.replace(b"[123]", b"[999]", 1),
                 response, trace(raw)),
                ("missing_record", b"".join(raw.splitlines(keepends=True)[:-1]),
                 response, trace(raw)),
                ("duplicate_record", raw + raw.splitlines(keepends=True)[-1],
                 response, trace(raw)),
                ("missing_option", raw.replace(b"-Xlog:arguments=info:file=", b"-Xlog:off=", 1),
                 response, trace(raw)),
                ("other_worker", raw.replace(b"GradleWorkerMain", b"OtherMain", 1),
                 response, trace(raw)),
                ("partial_write", raw, response, trace(raw[:-1])),
                ("changed_write", raw, response,
                 trace(raw.replace(b"/engine.jar:", b"/other.jar:", 1))),
                ("missing_write", raw, response,
                 trace(b"".join(raw.splitlines(keepends=True)[:-1]))),
                ("extra_write", raw, response,
                 trace(raw + raw.splitlines(keepends=True)[-1]))):
            with self.subTest(name=name), self.assertRaises(CaptureRejected):
                actual._verify_worker_argument_log(candidate, saved_response,
                                                   writes, pid)

    def test_resealed_generic_lambda_cannot_claim_full_binding(self):
        _, files, runtime = self.fixture()
        files["worker_class_load"] += (
            b"[123][info][class,load] portable.NumericalRecorder$$Lambda/0xdeadbeef "
            b"source: portable.NumericalRecorder\n")
        receipt = make_capture_receipt(files, "captureGeometry", "a" * 40,
                                       ["geometry-boundary-s0-o0-d0"], runtime)
        result = verify_capture_receipt(receipt, files, "captureGeometry", "a" * 40,
                                        ["geometry-boundary-s0-o0-d0"], runtime)
        self.assertEqual(result["status"], "UNPASSED_DYNAMIC_CLASS_LOAD")
        self.assertEqual(result["dynamic_class_load_status"], "UNBOUND")

    def test_unbound_pair_input_status_is_not_promoted(self):
        receipt = {"exit_code": 0, "summary": {
            "status": "UNPASSED_INPUT_ORIGIN", "qualification": "UNPASSED"}}
        with patch("actual_arithmetic.make_capture_receipt", return_value=receipt):
            result = verify_capture_receipt(receipt, {}, "captureGeometry", "a" * 40,
                                            ["geometry-boundary-s0-o0-d0"], "java")
        self.assertEqual(result["status"], "UNPASSED_INPUT_ORIGIN")
        self.assertEqual(result["operation_record_status"],
                         "UNPASSED_INPUT_ORIGIN")
        self.assertEqual(result["dynamic_class_load_status"], "UNBOUND")

    def test_resealed_wheel_receipt_rejects_nonworker_trace(self):
        _, files, runtime = self.fixture()
        files["xml"] = xml_for(focused_wheel_fixture(), "captureWheelActive")
        with zipfile.ZipFile(io.BytesIO(files["portable_classes"])) as classes:
            retained = {name: classes.read(name) for name in classes.namelist()}
        retained.update({"main/" + name: b"class" for name in _WHEEL_RECORDER_CLASSES})
        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, "w") as classes:
            for name, content in retained.items():
                classes.writestr(name, content)
        files["portable_classes"] = archive_bytes.getvalue()
        files["worker_class_load"] += "".join(
            f"[123][info][class,load] {name.removesuffix('.class').replace('/', '.')} "
            f"source: {(_ROOT / 'tools/numerical/portable/build/classes/kotlin/jvm/main').as_uri()}/\n"
            for name in sorted(_WHEEL_RECORDER_CLASSES)).encode()
        for name in ("gradle_log", "execve_log"):
            files[name] = files[name].replace(b"captureGeometry", b"captureWheelActive")
        worker_line = next(line.split(b" ", 1)[1]
                           for line in files["execve_log"].splitlines()
                           if line.startswith(b"123 execve("))
        output = ET.fromstring(files["xml"]).find("system-out").text.encode()
        write = (f'write(51, {json.dumps(output.decode())}, {len(output)}) = '
                 f'{len(output)}\n').encode()
        class_writes = b"".join(
            (f'write(4, {json.dumps(line.decode())}, {len(line)}) = '
             f'{len(line)}\n').encode()
            for line in files["worker_class_load"].splitlines(keepends=True))
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as traces:
            traces.writestr("trace.123", worker_line + b"\nclone(0) = 124\n")
            traces.writestr("trace.124", write + class_writes)
        files["worker_write_traces"] = stream.getvalue()
        summary = {"selected_resets": 0, "status": "VERIFIED_ARITHMETIC_BINDING",
                   "qualification": "UNPASSED"}
        with patch("actual_arithmetic.verify_capture", return_value=summary):
            receipt = make_capture_receipt(files, "captureWheelActive", "a" * 40,
                                           ["joint-Wheel-active"], runtime)
            genuine = verify_capture_receipt(receipt, files, "captureWheelActive",
                                             "a" * 40, ["joint-Wheel-active"], runtime)
            self.assertEqual(genuine["status"], "UNPASSED_DYNAMIC_CLASS_LOAD")
            self.assertEqual(genuine["external_xml_witness"],
                             "PASSED_KERNEL_WORKER_WRITES")
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as traces:
                traces.writestr("trace.123", worker_line + b"\nclone(0) = 124\n")
                traces.writestr("trace.124", write + class_writes)
                traces.writestr("trace.999999", b"benign unrelated trace\n")
            files["worker_write_traces"] = stream.getvalue()
            resealed = copy.deepcopy(receipt)
            resealed["worker_write_traces_sha256"] = hashlib.sha256(
                files["worker_write_traces"]).hexdigest()
            with self.assertRaisesRegex(CaptureRejected,
                                        "worker write trace inventory differs"):
                verify_capture_receipt(resealed, files, "captureWheelActive", "a" * 40,
                                       ["joint-Wheel-active"], runtime)

    def test_geometry_without_accepted_toi_does_not_require_reset_hook_execution(self):
        _, files, runtime = self.fixture()
        files["worker_class_load"] = b"".join(
            line for line in files["worker_class_load"].splitlines(keepends=True)
            if b"org.dyn4j.world.ToiAcceptedResetTap " not in line
        )
        receipt = make_capture_receipt(files, "captureGeometry", "a" * 40,
                                       ["geometry-boundary-s0-o0-d0"], runtime)
        result = verify_capture_receipt(receipt, files, "captureGeometry", "a" * 40,
                                        ["geometry-boundary-s0-o0-d0"], runtime)
        self.assertEqual(result["selected_resets"], 0)
        self.assertEqual(len(receipt["worker_class_load_sources"]), 4)

    def test_capture_slot_must_be_loaded_from_staged_engine(self):
        _, files, runtime = self.fixture()
        files["worker_class_load"] = b"".join(
            line for line in files["worker_class_load"].splitlines(keepends=True)
            if b"org.dyn4j.geometry.RotationCaptureSlot " not in line
        )
        with self.assertRaises(CaptureRejected):
            make_capture_receipt(files, "captureGeometry", "a" * 40,
                                 ["geometry-boundary-s0-o0-d0"], runtime)

    def test_accepted_reset_requires_executed_reset_hook_class(self):
        _, files, runtime = self.fixture()
        rows = fixture()
        identity = [bits(1.0), bits(0.0)]
        inputs = json.loads(rows[0].split(" ", 1)[1])
        inputs["setup"]["bodies"].append({"id": "b1"})
        inputs["initial"]["bodies"].append({
            "id": "b1", "transform": {"getCost": 1.0, "getSint": 0.0}})
        rows[0] = "NUMERICAL_JSON " + json.dumps(inputs)
        state = json.loads(rows[2].split(" ", 1)[1])
        state["state"]["bodies"].append({
            "id": "b1", "transform": {"getCost": 1.0, "getSint": 0.0}})
        state["order"] = 1
        rows[2] = "NUMERICAL_JSON " + json.dumps(state)
        body_step = json.loads(rows[3].split(" ", 1)[1])
        body_step["bodies"].append({"body_id": "b1", "calls": 0,
                                    "pre": identity, "post": identity})
        rows[3] = "PROSPECTIVE_BINDING_JSON " + json.dumps(body_step)
        operation = json.loads(rows[1].split(" ", 1)[1])
        operation.update(kind="lerp-reset", source="direct", raw=[None, None],
                         trig=identity, post=identity, angle_bits=bits(0.0),
                         alpha_bits=bits(0.5), start_angle_bits=bits(0.0),
                         end_angle_bits=bits(0.0), diff_bits=bits(0.0),
                         start=identity, end=identity)
        rows[1] = "PROSPECTIVE_ROTATION_JSON " + json.dumps(operation)
        rows.insert(1, "NUMERICAL_JSON " + json.dumps({
            "kind": "event", "id": "geometry-boundary-s0-o0-d0", "step": 1,
            "order": 0, "name": "toi.payload.bodies",
            "payload": {"bodies": [0, 1], "time": 0.5}}))
        rows.insert(3, "PROSPECTIVE_BINDING_JSON " + json.dumps({
            "kind": "toi-accepted", "case_id": "geometry-boundary-s0-o0-d0",
            "step": 1, "body_ids": ["b0", "b1"], "reset_body_ids": ["b0"],
            "time_bits": bits(0.5)}))
        files["xml"] = xml_for(rows)
        receipt = make_capture_receipt(files, "captureGeometry", "a" * 40,
                                       ["geometry-boundary-s0-o0-d0"], runtime)
        self.assertEqual(receipt["summary"]["selected_resets"], 1)
        files["worker_class_load"] = b"".join(
            line for line in files["worker_class_load"].splitlines(keepends=True)
            if b"org.dyn4j.world.ToiAcceptedResetTap " not in line
        )
        with self.assertRaises(CaptureRejected):
            make_capture_receipt(files, "captureGeometry", "a" * 40,
                                 ["geometry-boundary-s0-o0-d0"], runtime)

    def test_loaded_optional_reset_hook_still_requires_staged_source(self):
        _, files, runtime = self.fixture()
        files["worker_class_load"] = files["worker_class_load"].replace(
            b"org.dyn4j.world.ToiAcceptedResetTap source: " +
            _STAGED_JAR.as_uri().encode(),
            b"org.dyn4j.world.ToiAcceptedResetTap source: file:/tmp/other.jar")
        with self.assertRaises(CaptureRejected):
            make_capture_receipt(files, "captureGeometry", "a" * 40,
                                 ["geometry-boundary-s0-o0-d0"], runtime)

    def test_stale_bytes_source_artifact_trace_and_runtime_fail(self):
        for key in ("xml", "stage_log", "gradle_log", "execve_log",
                    "artifact", "runtime", "source", "worker_classpath",
                    "worker_class_load",
                    "portable_classes"):
            receipt, files, runtime = self.fixture()
            files[key] += b"tamper"
            with self.subTest(key=key), self.assertRaises(CaptureRejected):
                verify_capture_receipt(receipt, files, "captureGeometry", "a" * 40,
                                       ["geometry-boundary-s0-o0-d0"], runtime)
        receipt, files, runtime = self.fixture()
        receipt["summary"]["trace_sha256"] = "0" * 64
        with self.assertRaises(CaptureRejected):
            verify_capture_receipt(receipt, files, "captureGeometry", "a" * 40,
                                   ["geometry-boundary-s0-o0-d0"], runtime)

    def test_worker_load_log_rejects_substitution_and_recomputed_receipt(self):
        receipt, files, runtime = self.fixture()
        self.assertEqual(receipt["worker_pid"], "123")
        self.assertEqual(len(receipt["worker_class_load_sources"]), 5)
        original = files["worker_class_load"]
        first = sorted(_AUDITED_ENGINE_CLASSES)[0].removesuffix(".class").replace("/", ".")
        changes = {
            "wrong-pid": original.replace(b"[123]", b"[124]"),
            "missing-class": b"\n".join(original.splitlines()[1:]) + b"\n",
            "wrong-engine": original.replace(_STAGED_JAR.as_uri().encode(),
                                             b"file:/tmp/other-engine.jar", 1),
            "duplicate-class": original + original.splitlines()[0] + b"\n",
            "substituted-log": (f"[124][info][class,load] {first} "
                                f"source: {_STAGED_JAR.as_uri()}\n").encode(),
        }
        for name, changed in changes.items():
            files["worker_class_load"] = changed
            with self.subTest(name=name), self.assertRaises(CaptureRejected):
                make_capture_receipt(files, "captureGeometry", "a" * 40,
                                     ["geometry-boundary-s0-o0-d0"], runtime)
        files["worker_class_load"] = original
        files["execve_log"] = files["execve_log"].replace(b"123 execve", b"124 execve")
        with self.assertRaises(CaptureRejected):
            make_capture_receipt(files, "captureGeometry", "a" * 40,
                                 ["geometry-boundary-s0-o0-d0"], runtime)
        files["execve_log"] = files["execve_log"].replace(b"124 execve", b"123 execve")
        files["gradle_log"] = files["gradle_log"].replace(
            b"-Xlog:class+load", b"-Xlog:class+unload")
        with self.assertRaises(CaptureRejected):
            make_capture_receipt(files, "captureGeometry", "a" * 40,
                                 ["geometry-boundary-s0-o0-d0"], runtime)
        receipt, files, runtime = self.fixture()
        with patch("actual_arithmetic._source_archive", return_value=b"other"):
            with self.assertRaises(CaptureRejected):
                verify_capture_receipt(receipt, files, "captureGeometry", "a" * 40,
                                       ["geometry-boundary-s0-o0-d0"], runtime)

    def test_wrong_method_process_and_receipt_fields_fail(self):
        receipt, files, runtime = self.fixture()
        for field, value in (("method", "captureJoints"), ("candidate_commit", "b" * 40),
                             ("exit_code", 1), ("runtime_executable", "/other/java")):
            changed = copy.deepcopy(receipt)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(CaptureRejected):
                verify_capture_receipt(changed, files, "captureGeometry", "a" * 40,
                                       ["geometry-boundary-s0-o0-d0"], runtime)
        files["execve_log"] = files["execve_log"].replace(b" = 0", b" = -1")
        with self.assertRaises(CaptureRejected):
            verify_capture_receipt(receipt, files, "captureGeometry", "a" * 40,
                                   ["geometry-boundary-s0-o0-d0"], runtime)


class ClasspathProviderTest(unittest.TestCase):
    def test_portable_provider_bytes_and_precedence(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as folder:
            root = Path(folder)
            staged = root / "staged.jar"
            class_root = root / "classes"
            for source_set in ("main", "test"):
                (class_root / source_set).mkdir(parents=True)
            with zipfile.ZipFile(staged, "w") as archive:
                for name in _AUDITED_ENGINE_CLASSES:
                    archive.writestr(name, b"engine")
            names = {
                "main": {"portable/NumericalRecorder.class",
                         "portable/NumericalRecorder$capture$steps$1.class"},
                "test": set(_FIXTURE_CLASSES) | {
                    "portable/PortableMatrixTest.class",
                    "portable/ProspectiveArithmeticTest.class"},
            }
            inventory = {
                source_set: {name: hashlib.sha256(b"compiled").hexdigest()
                             for name in members}
                for source_set, members in names.items()}
            for source_set, members in names.items():
                for name in members:
                    path = class_root / source_set / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"compiled")
            main, test = class_root / "main", class_root / "test"
            valid = f"{main}:{test}:{staged}"
            self.assertEqual(len(_inspect_worker_classpath(
                valid, staged, class_root, inventory)), 3)
            shadow = root / "alternate.jar"
            for class_name in names["main"] | names["test"]:
                with zipfile.ZipFile(shadow, "w") as archive:
                    archive.writestr(class_name, b"altered")
                for value in (f"{shadow}:{valid}", f"{valid}:{shadow}"):
                    with self.subTest(class_name=class_name, value=value), \
                            self.assertRaises(CaptureRejected):
                        _inspect_worker_classpath(value, staged, class_root, inventory)
            missing = test / "portable/PortableMatrixTest.class"
            missing.unlink()
            with self.assertRaisesRegex(CaptureRejected,
                                        "compiled portable class provider differs"):
                _inspect_worker_classpath(valid, staged, class_root, inventory)
            missing.write_bytes(b"altered")
            with self.assertRaisesRegex(CaptureRejected,
                                        "compiled portable class provider differs"):
                _inspect_worker_classpath(valid, staged, class_root, inventory)

    def test_prior_and_later_engine_providers_fail(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as folder:
            root = Path(folder)
            staged = root / "staged.jar"
            shadow = root / "earlier.jar"
            class_root = root / "classes"
            (class_root / "main").mkdir(parents=True)
            (class_root / "test").mkdir()
            with zipfile.ZipFile(staged, "w") as archive:
                for name in _AUDITED_ENGINE_CLASSES:
                    archive.writestr(name, b"staged")
            with zipfile.ZipFile(shadow, "w") as archive:
                archive.writestr("org/dyn4j/geometry/Transform.class", b"earlier")
            main = class_root / "main"
            test = class_root / "test"
            self.assertEqual(len(_inspect_worker_classpath(
                f"{main}:{test}:{staged}", staged, class_root)), 3)
            for classpath in (f"{shadow}:{main}:{test}:{staged}",
                              f"{main}:{test}:{staged}:{shadow}"):
                with self.subTest(classpath=classpath), self.assertRaises(CaptureRejected):
                    _inspect_worker_classpath(classpath, staged, class_root)


class EnvironmentSentinelTest(unittest.TestCase):
    def test_normal_execve_trace_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "execve.log"
            trace.write_text('123 execve("/jdk/bin/java", ["java"], 0x0) = 0\n')
            reject_environment_trace(trace)
            self.assertTrue(trace.is_file())

    def test_environment_dump_is_removed_and_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "execve.log"
            trace.write_text(f"environment includes {ENVIRONMENT_SENTINEL}\n")
            with self.assertRaises(CaptureRejected):
                reject_environment_trace(trace)
            self.assertFalse(trace.exists())

    def test_unreadable_trace_is_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "execve.log"
            trace.write_text("synthetic trace bytes")
            with patch.object(Path, "read_bytes", side_effect=PermissionError):
                with self.assertRaisesRegex(CaptureRejected, "process trace is unavailable"):
                    reject_environment_trace(trace)
            self.assertFalse(trace.exists())

    def test_removal_failure_has_safe_error(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "execve.log"
            trace.write_text("synthetic trace bytes")
            with patch.object(Path, "read_bytes", side_effect=PermissionError):
                with patch.object(Path, "unlink", side_effect=PermissionError):
                    with self.assertRaises(CaptureRejected) as raised:
                        reject_environment_trace(trace)
            self.assertEqual(str(raised.exception), "process trace could not be removed")
            self.assertTrue(trace.exists())

    def test_missing_trace_reports_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "execve.log"
            with self.assertRaisesRegex(CaptureRejected, "process trace is missing"):
                reject_environment_trace(trace)
            self.assertFalse(trace.exists())


if __name__ == "__main__":
    unittest.main()
