import hashlib
import json
import math
import runpy
import shutil
import struct
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


V = runpy.run_path(str(Path(__file__).with_name("validate-precision-control.py")))
FOCUS = V["focus"]
SCALAR = V["SCALAR"]
REPO = V["REPO"]
FOCUSED_SCRIPT = "tools/diagnostic/windows_collision/run-focused-controls.ps1"


def workflow_run_expressions(workflow):
    lines = workflow.splitlines(keepends=True)
    expressions = []
    for index, line in enumerate(lines):
        if line.strip() != "run: |":
            continue
        indentation = len(line) - len(line.lstrip(" "))
        body = []
        for continuation in lines[index + 1:]:
            if continuation.strip() and len(continuation) - len(continuation.lstrip(" ")) <= indentation:
                break
            body.append(continuation)
        expressions.append("".join(body))
    return expressions


def bits(value):
    return struct.unpack(">q", struct.pack(">d", value))[0]


def number(raw):
    return struct.unpack(">d", struct.pack(">q", raw))[0]


def encoded(value):
    return f"{repr(value)}@{bits(value)}"


def scalar_rows(provider):
    result = []
    for case_id, x_bits, y_bits in SCALAR["EXPECTED"]:
        x, y = number(x_bits), number(y_bits)
        x_squared, y_squared = x * x, y * y
        sum_ = x_squared + y_squared
        root = math.sqrt(sum_)
        reciprocal = 1.0 / root
        values = ("DYN4K_COLLISION_SCALAR", "v1", f"provider={provider}", f"id={case_id}",
                  f"x={encoded(x)}", f"y={encoded(y)}", f"xSquared={encoded(x_squared)}",
                  f"ySquared={encoded(y_squared)}", f"sum={encoded(sum_)}", f"sqrt={encoded(root)}",
                  f"reciprocal={encoded(reciprocal)}",
                  f"normalized={encoded(x * reciprocal)},{encoded(y * reciprocal)}")
        result.append("\t".join(values))
    return "\n".join(result) + "\n"


def probe_rows():
    rows = [f"input\t{case_id}\t{sum_bits}\t{root}\t{root + 1}\t{root}\t{root}"
            for case_id, sum_bits, root in V["PROBE_INPUTS"]]
    for center, roots in enumerate(V["PROBE_NEIGHBORS"]):
        for index, root in enumerate(roots):
            rows.append(f"neighbor\t{center}\t{index - 4}\t{V['PROBE_INPUTS'][center][1] + index - 4}\t{root}\t{root}")
    rows += [f"edge\t{source}\t{root}\t{root}" for source, root in V["PROBE_EDGES"]]
    rows.append("PASS inputs=7 neighbors=18 edges=7 specials=6 fallback=6 forcedDirections=both")
    return "\n".join(rows) + "\n"


def xml_fixture(directory):
    for suite, filename in FOCUS.SUITES.items():
        expected = (FOCUS.DIAGNOSTIC_CASES if suite.endswith("WindowsCollisionIntermediateDiagnosticTest")
                    else FOCUS.ORIGINAL_CASES[suite])
        root = ET.Element("testsuite", {"name": f"mingwX64Test.{suite}", "tests": str(len(expected)),
                                        "failures": "0", "errors": "0", "skipped": "0"})
        for name in sorted(expected):
            ET.SubElement(root, "testcase", {"name": name})
        ET.ElementTree(root).write(directory / filename, encoding="utf-8")


def probe_fixture(directory):
    (directory / "probe-exit-code.txt").write_text("0\n", encoding="utf-8")
    for name, flags in (("debug-g", ["-g"]), ("default", []), ("optimized-opt", ["-opt"])):
        mode = directory / name
        mode.mkdir()
        executable = mode / "sqrt-operation-probe.exe"
        executable.write_bytes(f"MZ{name}".encode())
        (mode / "executable-sha256.txt").write_text(
            f"{hashlib.sha256(executable.read_bytes()).hexdigest()}  sqrt-operation-probe.exe\n", encoding="utf-8")
        sources = [str(REPO / path) for path in (V["ENGINE_SOURCES"][1], V["ENGINE_SOURCES"][2], V["PROBE_SOURCE"])]
        arguments = ["-Xmulti-platform", f"-Xcommon-sources={sources[0]}", *sources,
                     "-target", "mingw_x64", *flags, "-o", str(mode / "sqrt-operation-probe")]
        compiler = "/pinned/bin/kotlinc-native.bat"
        (mode / "compiler-command.json").write_text(
            json.dumps({"mode": name, "executable": compiler, "arguments": arguments}), encoding="utf-8")
        for phase, command in (("compiler", [compiler, *arguments]), ("run", [str(executable)])):
            (mode / f"{phase}-exit-code.txt").write_text("0\n", encoding="utf-8")
            (mode / f"{phase}-receipt.json").write_text(
                json.dumps({"state": "EXITED", "childExitCode": 0, "command": command}), encoding="utf-8")
            (mode / ("compiler-stdout.log" if phase == "compiler" else "probe-stdout.tsv")).write_text(
                "" if phase == "compiler" else probe_rows(), encoding="utf-8")
            (mode / ("compiler-stderr.log" if phase == "compiler" else "probe-stderr.log")).write_text(
                "", encoding="utf-8")


class CorrectedControlTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def reject(self, operation):
        with self.assertRaises((ValueError, OSError, KeyError, TypeError)):
            operation()

    def test_original_cases_all_pass_and_adverse(self):
        xml_fixture(self.root)
        self.assertEqual(len(V["corrected_xml_cases"](self.root)), 30)
        report = self.root / FOCUS.SUITES["org.dyn4j.coverage.collision.shapes.a.CapsuleSliceTest"]
        original = report.read_bytes()
        for tag, counter in (("failure", "failures"), ("error", "errors"), ("skipped", "skipped")):
            tree = ET.parse(report)
            ET.SubElement(tree.getroot().find("testcase"), tag)
            tree.write(report)
            self.reject(lambda: V["corrected_xml_cases"](self.root))
            report.write_bytes(original)
            tree = ET.parse(report)
            tree.getroot().set(counter, "1")
            tree.write(report)
            self.reject(lambda: V["corrected_xml_cases"](self.root))
            report.write_bytes(original)
        report.unlink()
        self.reject(lambda: V["corrected_xml_cases"](self.root))

    def test_seven_scalar_bits_and_adverse(self):
        native, java = scalar_rows("kotlin-native"), scalar_rows("java")
        self.assertEqual(len(V["corrected_scalar_rows"](native, java)), 7)
        self.reject(lambda: V["corrected_scalar_rows"]("\n".join(native.splitlines()[:-1]), java))

    def test_retained_debug_scalar_divergence_is_observation(self):
        source = Path(__file__).with_name("testdata")
        native = (source / "c0d-debug-g-native-scalar.tsv").read_text(encoding="utf-8")
        java = (source / "c0d-java-scalar.tsv").read_text(encoding="utf-8")
        self.assertEqual(hashlib.sha256(native.encode()).hexdigest(),
                         "4ff346c6ddddd0c3cd20e352f0064334fea686fb9b2f4c8ad5cfe8a7609d8b06")
        self.assertEqual(hashlib.sha256(java.encode()).hexdigest(),
                         "b448b87180b11a8174e82e6e453ed95f08ea4f507575194a8c33752a90b2303e")
        SCALAR["validate"](native, java)
        observations = V["corrected_scalar_rows"](native, java)
        self.assertEqual([row["id"] for row in observations], list(V["SCALAR_IDS"]))
        self.assertEqual(observations[0]["native"]["sqrt"], "0.5@4602678819172646912")
        self.assertEqual(observations[0]["java"]["sqrt"], "0.49999999999999994@4602678819172646911")
        self.assertEqual(sum(row["native"]["sqrt"] != row["java"]["sqrt"] for row in observations), 7)
        self.assertEqual(sum(not row["computedBitEqual"]["sqrt"] for row in observations), 7)
        self.reject(lambda: V["corrected_scalar_rows"](native.replace(
            "x=-0.4330127018922194@-4621899953565315924", "x=0.0@0", 1), java))
        self.reject(lambda: V["corrected_scalar_rows"]("\n".join(native.splitlines()[:-1]), java))
        lines = native.splitlines()
        lines[0], lines[1] = lines[1], lines[0]
        self.reject(lambda: V["corrected_scalar_rows"]("\n".join(lines), java))
        self.reject(lambda: V["corrected_scalar_rows"](native.replace(
            "xSquared=0.18750000000000008@4595923419731591171",
            "xSquared=0.0@4595923419731591171", 1), java))
        self.reject(lambda: V["corrected_scalar_rows"](native.replace(
            "\treciprocal=2.0@4611686018427387904", "", 1), java))

    def test_committed_source_hashes_and_adverse(self):
        source_sha = subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip()
        paths = (*V["ENGINE_SOURCES"], *V["PROBE_SOURCES"])
        lines = [f"{hashlib.sha256((REPO / path).read_bytes()).hexdigest()}  {path}" for path in paths]
        receipt = self.root / "source-sha256.txt"
        receipt.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.assertEqual(V["corrected_source_hashes"](self.root, source_sha), 10)
        receipt.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
        self.reject(lambda: V["corrected_source_hashes"](self.root, source_sha))
        receipt.write_text("\n".join(["0" * 64 + "  " + paths[0], *lines[1:]]) + "\n", encoding="utf-8")
        self.reject(lambda: V["corrected_source_hashes"](self.root, source_sha))

    def test_corrected_route_result_and_adverse(self):
        native = self.root / "native"
        native.mkdir()
        xml_fixture(native)
        (native / "gradle-exit-code.txt").write_text("0\n", encoding="utf-8")
        gradle_command = list(V["CORRECTED_GRADLE_COMMAND"])
        (native / "gradle-command.txt").write_text("\n".join(gradle_command) + "\n", encoding="utf-8")
        (native / "gradle-receipt.json").write_text(json.dumps({"state": "EXITED", "childExitCode": 0,
            "command": ["cmd.exe", "/d", "/s", "/c", " ".join(gradle_command)]}), encoding="utf-8")
        for name in ("gradle-stdout.log", "gradle-stderr.log", "gradle-console.log"):
            (native / name).write_text("synthetic Gradle output\n", encoding="utf-8")
        (native / "test-pe-collector-exit-code.txt").write_text("0\n", encoding="utf-8")
        test_pe = native / "test-pe"
        test_pe.mkdir()
        (test_pe / "test.exe").write_bytes(b"MZfocused")
        (test_pe / "test-executable-status.txt").write_text("OK\n", encoding="utf-8")
        test_pe_hash = hashlib.sha256((test_pe / "test.exe").read_bytes()).hexdigest()
        (test_pe / "test-executable-sha256.txt").write_text(f"{test_pe_hash}  test.exe\n", encoding="utf-8")
        scalar = self.root / "scalar"
        scalar.mkdir()
        (scalar / "native-scalar.tsv").write_text(scalar_rows("kotlin-native"), encoding="utf-8")
        (scalar / "java-scalar.tsv").write_text(scalar_rows("java"), encoding="utf-8")
        (scalar / "kotlin-native-version.txt").write_text("Kotlin/Native 2.4.20\n", encoding="utf-8")
        java_dir = self.root / "java"
        java_dir.mkdir()
        (self.root / "baseline-source-revision.txt").write_text(
            "058bf6d982a0fb89b54050f929f6ea9dae53b714\n", encoding="utf-8")
        java_trace = java_dir / "java-trace.tsv"
        java_trace.write_text("synthetic 72-row parser delegation\n", encoding="utf-8")
        (java_dir / "java-exit-code.txt").write_text("0\n", encoding="utf-8")
        (java_dir / "java-command.txt").write_text("\n".join((
            ".\\tools\\diagnostic\\windows_collision\\run-java-control.ps1",
            "-JdkHome /pinned/jdk21", "-BaselineJar /pinned/dyn4j-6.0.0.jar",
            "-BaselineSource /pinned/dyn4j-source", f"-OutputDirectory {java_dir}")) + "\n", encoding="utf-8")
        (java_dir / "java-stdout.log").write_text(
            "PINNED_DYN4J_CONTROL jarSha256=204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e "
            "sourceRevision=058bf6d982a0fb89b54050f929f6ea9dae53b714 records=72\n", encoding="utf-8")
        for name in ("java-stderr.log", "java-console.log"):
            (java_dir / name).write_text("synthetic Java output\n", encoding="utf-8")
        probe = self.root / "probe"
        probe.mkdir()
        probe_fixture(probe)
        paths = (*V["ENGINE_SOURCES"], *V["PROBE_SOURCES"])
        (probe / "source-sha256.txt").write_text(
            "\n".join(f"{hashlib.sha256((REPO / path).read_bytes()).hexdigest()}  {path}" for path in paths) + "\n",
            encoding="utf-8")
        args = SimpleNamespace(native_directory=str(native), java_trace=str(java_trace),
                               native_scalars=str(scalar / "native-scalar.tsv"),
                               java_scalars=str(scalar / "java-scalar.tsv"), probe_directory=str(probe),
                               source_sha=subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                                                                  text=True).strip(),
                               result=str(self.root / "result.json"))
        with patch.object(FOCUS, "validate", return_value=(7, 6, 72, 72)) as trace_validator:
            V["validate_corrected"](args)
            trace_validator.assert_called_once()
            result = json.loads(Path(args.result).read_text(encoding="utf-8"))
            self.assertEqual((result["originalAndDiagnosticPasses"], result["engineSourceHashes"],
                              result["probeSourceHashes"], len(result["probeModes"])), (30, 8, 2, 3))
            (native / "gradle-exit-code.txt").write_text("1\n", encoding="utf-8")
            self.reject(lambda: V["validate_corrected"](args))
            (native / "gradle-exit-code.txt").write_text("0\n", encoding="utf-8")
            (native / "gradle-receipt.json").write_text(json.dumps({"state": "TIMEOUT", "childExitCode": None}),
                                                        encoding="utf-8")
            self.reject(lambda: V["validate_corrected"](args))
            (native / "gradle-receipt.json").write_text(json.dumps({"state": "EXITED", "childExitCode": 0,
                "command": ["cmd.exe", "/d", "/s", "/c", " ".join(gradle_command)]}), encoding="utf-8")
            (test_pe / "test.exe").write_bytes(b"MZother")
            self.reject(lambda: V["validate_corrected"](args))

    def test_probe_modes_and_adverse(self):
        probe_fixture(self.root)
        self.assertEqual(len(V["corrected_probe_modes"](self.root)), 3)
        mode = self.root / "debug-g"
        output = mode / "probe-stdout.tsv"
        original = output.read_text(encoding="utf-8")
        output.write_text("\n".join(original.splitlines()[:-1]), encoding="utf-8")
        self.reject(lambda: V["corrected_probe_modes"](self.root))
        output.write_text(original.replace("4602678819172646911\t4602678819172646911\n",
                                           "4602678819172646911\t4602678819172646912\n", 1), encoding="utf-8")
        self.reject(lambda: V["corrected_probe_modes"](self.root))
        output.write_text(original, encoding="utf-8")
        command = mode / "compiler-command.json"
        original_command = command.read_text(encoding="utf-8")
        command.write_text(original_command.replace("NearestSqrtPlatform.kt", "Other.kt", 1), encoding="utf-8")
        self.reject(lambda: V["corrected_probe_modes"](self.root))
        command.write_text(original_command, encoding="utf-8")
        default_command = self.root / "default" / "compiler-command.json"
        default_original = default_command.read_text(encoding="utf-8")
        default_command.write_text(default_original.replace('"-target", "mingw_x64", "-o"',
                                                            '"-target", "mingw_x64", "-g", "-o"'), encoding="utf-8")
        self.reject(lambda: V["corrected_probe_modes"](self.root))
        default_command.write_text(default_original, encoding="utf-8")
        receipt = mode / "run-receipt.json"
        receipt.write_text(json.dumps({"state": "TIMEOUT", "childExitCode": None}), encoding="utf-8")
        self.reject(lambda: V["corrected_probe_modes"](self.root))
        probe_fixture_rebuilt = self.root / "rebuilt"
        probe_fixture_rebuilt.mkdir()
        probe_fixture(probe_fixture_rebuilt)
        (probe_fixture_rebuilt / "optimized-opt" / "sqrt-operation-probe.exe").write_bytes(b"changed")
        self.reject(lambda: V["corrected_probe_modes"](probe_fixture_rebuilt))
        missing_default = self.root / "missing-default"
        missing_default.mkdir()
        probe_fixture(missing_default)
        shutil.rmtree(missing_default / "default")
        self.reject(lambda: V["corrected_probe_modes"](missing_default))

    def test_workflow_route_contract_and_adverse(self):
        workflow = (REPO / ".github/workflows/windows-collision-focus.yml").read_text(encoding="utf-8")
        script = (REPO / FOCUSED_SCRIPT).read_text(encoding="utf-8")
        required = ("default: historical-pc53", "- corrected-production", "if ($route -eq 'historical-pc53')",
                    "validate-corrected", "--native-scalars", "--probe-directory",
                    "Name = 'default'; Flags = @()", "+ $probeMode.Flags +",
                    "SqrtOperationJvmProbe.java", "$engineSources + $probeSources", "'-g'", "'-opt'",
                    "$correctedProbeExit -eq '0' -and $correctedValidationExit -eq 0")
        def check(text):
            if any(token not in text for token in required):
                raise ValueError("corrected script route is incomplete")
        check(workflow + script)
        for token in required:
            self.reject(lambda token=token: check((workflow + script).replace(token, "BROKEN")))

    def test_workflow_run_expression_limit_and_script_binding(self):
        workflow = (REPO / ".github/workflows/windows-collision-focus.yml").read_text(encoding="utf-8")
        invocation = f"& (Join-Path $PWD '{FOCUSED_SCRIPT}') -Route $env:DYN4K_COLLISION_ROUTE"
        script = (REPO / FOCUSED_SCRIPT).read_text(encoding="utf-8")
        route_binding = "DYN4K_COLLISION_ROUTE: ${{ inputs.route }}"

        def check(workflow_text, script_text):
            expressions = workflow_run_expressions(workflow_text)
            if len(expressions) != 2 or max(len(expression.encode("utf-8")) for expression in expressions) >= 21000:
                raise ValueError("workflow run expression exceeds the GitHub limit")
            if invocation not in workflow_text or route_binding not in workflow_text or \
                    workflow_text.count("${{ inputs.route }}") != 1 or "${{" in script_text:
                raise ValueError("workflow route is not bound to the script")
            sources = script_text.split("$controlSources = @(", 1)[1].split("\n)", 1)[0]
            if sources.count(f"'{FOCUSED_SCRIPT}'") != 1:
                raise ValueError("the committed script is missing from the source hash receipt")

        check(workflow, script)
        self.reject(lambda: check(workflow.replace(invocation, invocation + "x" * 21000), script))
        self.reject(lambda: check(workflow.replace(invocation, "Write-Output 'BROKEN'"), script))
        self.reject(lambda: check(workflow.replace(route_binding, "DYN4K_COLLISION_ROUTE: wrong"), script))
        self.reject(lambda: check(workflow, script.replace(f"'{FOCUSED_SCRIPT}'", "'missing.ps1'")))
        subprocess.check_call(["git", "-C", str(REPO), "ls-files", "--error-unmatch", FOCUSED_SCRIPT],
                              stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    unittest.main()
