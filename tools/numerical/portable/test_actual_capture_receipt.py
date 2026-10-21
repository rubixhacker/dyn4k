import copy
import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import actual_arithmetic as actual
from capture_actual import ENVIRONMENT_SENTINEL, reject_environment_trace
from actual_arithmetic import (CaptureRejected, _AUDITED_ENGINE_CLASSES,
                               _ROOT, _STAGED_JAR, _WHEEL_RECORDER_CLASSES,
                               _inspect_worker_classpath,
                               make_capture_receipt,
                               verify_capture_receipt)
from test_actual_arithmetic import fixture, focused_wheel_fixture, xml_for
from test_rotation_marker import bits


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
        self.assertEqual(receipt["summary"]["status"],
                         "VERIFIED_ARITHMETIC_BINDING")

    def test_resealed_duplicate_lambda_rejects_and_new_or_missing_is_unbound(self):
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
                    result = verify_capture_receipt(resealed, files, *args)
                    self.assertEqual(result["status"],
                                     "UNPASSED_DYNAMIC_CLASS_LOAD")
                    self.assertEqual(result["dynamic_class_load_status"], "UNBOUND")
                    self.assertEqual(result["operation_record_status"],
                                     "VERIFIED_ARITHMETIC_BINDING")
                    self.assertEqual(result["operations_verified"], 1800)

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
        self.assertEqual(result["status"], "VERIFIED_ARITHMETIC_BINDING")
        self.assertEqual(result["qualification"], "UNPASSED")
        self.assertEqual(result["operations_verified"], 1)

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
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as traces:
            traces.writestr("trace.123", worker_line + b"\nclone(0) = 124\n")
            traces.writestr("trace.124", write)
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
                traces.writestr("trace.124", write)
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
                "test": {"portable/PortableMatrixTest.class",
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
