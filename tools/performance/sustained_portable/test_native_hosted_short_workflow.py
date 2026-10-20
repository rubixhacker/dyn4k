import ast
import base64
import errno
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest

import yaml


WORKFLOW = Path(__file__).resolve().parents[3] / ".github/workflows/performance-native-host-short.yml"
RUNNER = Path(__file__).with_name("native_hosted_short_runner.py")
RAW_LIMIT = 64 * 1024 * 1024
RUN_EXPRESSION_LIMIT = 21000
VALID_HEAP_CSV = (b"stage,retained_heap_bytes,gc_epoch\n"
                  b"constructed,1024,1\nafter_reset,2048,2\nmeasured,3072,3\n")
VALID_HEAP_STDOUT = (b"DYN4K\tHEAP\tconstructed\t1024\t1\n"
                     b"DYN4K\tHEAP\tafter_reset\t2048\t2\n"
                     b"DYN4K\tHEAP\tmeasured\t3072\t3\n")
# This lock prevents unparsed YAML forms from bypassing the run-size scanner.
# After a workflow edit, independently parse every run value before updating its digest.
AUDITED_WORKFLOW_SHA256 = {
    "performance-host-capacity-control.yml": "03336de80b8deb55d6d8c1eee7247ab5cb54c404f188f240f0cfd2940873bcc1",
    "full-staged-native-host.yml": "dc312ad2acbd8c777e6c3ead5ffc1c5d9d171cab24ba776273411780818d3d7b",
    "performance-native-host-short.yml": "c49cc12671fdbe29b0c34e4b2d20920e8ab4a54c367d32f9ed2d041f32ccd9d2",
    "qualification.yml": "8bc7bce8bb15136c3de0dbbf9a3f18b37fedcbd69e48bb650ac5cb9cd70d62f5",
    "windows-collision-focus.yml": "861655f85b23426ed77022229a01f992f2fa276745148a17eda8bb04fb4b6b64",
}
def verify_sustained_workflow_contract(source):
    document = yaml.safe_load(source)
    if not isinstance(document, dict):
        raise AssertionError("workflow root must be a mapping")
    triggers = document.get("on", document.get(True))
    dispatch = triggers.get("workflow_dispatch") if isinstance(triggers, dict) else None
    inputs = dispatch.get("inputs") if isinstance(dispatch, dict) else None
    expected_inputs = {
        "target": ["mingwX64"],
        "build": ["development", "optimized"],
    }
    for name, options in expected_inputs.items():
        value = inputs.get(name) if isinstance(inputs, dict) else None
        if (not isinstance(value, dict) or value.get("type") != "choice"
                or value.get("required") is not True or value.get("options") != options):
            raise AssertionError(f"workflow_dispatch {name} input changed")

    jobs = document.get("jobs")
    validate = jobs.get("validate-target") if isinstance(jobs, dict) else None
    capture = jobs.get("capture") if isinstance(jobs, dict) else None
    if not isinstance(validate, dict) or not isinstance(capture, dict):
        raise AssertionError("required workflow jobs are missing")
    validate_steps = validate.get("steps")
    target_guard = next((step for step in validate_steps or ()
                         if isinstance(step, dict)
                         and step.get("name") == "Require the Windows target"), None)
    if ("if" in validate
            or validate.get("runs-on") != "ubuntu-latest"
            or validate.get("env", {}).get("TARGET") != "${{ inputs.target }}"
            or not isinstance(target_guard, dict)
            or "if" in target_guard
            or target_guard.get("run") != 'test "$TARGET" = mingwX64'):
        raise AssertionError("Windows target validation route changed")

    capture_env = capture.get("env")
    if (capture.get("needs") != "validate-target"
            or capture.get("runs-on") != "windows-2025"
            or capture.get("timeout-minutes") != 150
            or not isinstance(capture_env, dict)
            or capture_env.get("TARGET") != "${{ inputs.target }}"
            or capture_env.get("BUILD") != "${{ inputs.build }}"):
        raise AssertionError("sustained capture job route or dispatch bindings changed")

    steps = capture.get("steps")
    if not isinstance(steps, list):
        raise AssertionError("sustained capture steps are missing")
    setup = [
        {"uses": "actions/checkout@v4"},
        {"uses": "actions/setup-java@v4",
         "with": {"distribution": "temurin", "java-version": "21"}},
        {"uses": "actions/setup-python@v5", "with": {"python-version": "3.12"}},
        {"uses": "gradle/actions/setup-gradle@v4"},
    ]
    cursor = 0
    setup_indices = []
    for index, step in enumerate(steps):
        if (cursor < len(setup) and isinstance(step, dict)
                and all(step.get(key) == value
                        for key, value in setup[cursor].items())):
            setup_indices.append(index)
            cursor += 1
    if cursor != len(setup):
        raise AssertionError("sustained capture setup steps changed")

    capture_steps = [step for step in steps if isinstance(step, dict)
                     and step.get("name") == "Stage and capture on selected host"]
    if len(capture_steps) != 1:
        raise AssertionError("sustained capture step is missing or duplicated")
    capture_step = capture_steps[0]
    workflow_env = document.get("env", {})
    step_env = capture_step.get("env", {})
    if not isinstance(workflow_env, dict) or not isinstance(step_env, dict):
        raise AssertionError("sustained capture environment must be mappings")
    effective_capture_env = {**workflow_env, **capture_env, **step_env}
    if (effective_capture_env.get("TARGET") != "${{ inputs.target }}"
            or effective_capture_env.get("BUILD") != "${{ inputs.build }}"):
        raise AssertionError("effective sustained capture dispatch bindings changed")
    if ("if" in capture_step or "if" in capture
            or capture_step.get("shell") != "bash"
            or capture_step.get("run") !=
            'python -B "$GITHUB_WORKSPACE/tools/performance/sustained_portable/native_hosted_short_runner.py"'):
        raise AssertionError("sustained capture step is conditional or altered")
    capture_index = steps.index(capture_step)
    if any(index >= capture_index for index in setup_indices):
        raise AssertionError("sustained capture must follow its setup steps")

    uploads = [step for step in steps if isinstance(step, dict)
               and step.get("name") == "Upload raw Native host evidence"]
    upload = uploads[0] if len(uploads) == 1 else None
    upload_with = upload.get("with") if isinstance(upload, dict) else None
    if (not isinstance(upload, dict) or upload.get("if") != "always()"
            or upload.get("uses") != "actions/upload-artifact@v4"
            or not isinstance(upload_with, dict)
            or upload_with.get("name") != "performance-native-host-short-${{ github.sha }}-${{ inputs.target }}-${{ inputs.build }}-${{ github.run_id }}-${{ github.run_attempt }}"
            or upload_with.get("path") != "${{ runner.temp }}/performance-native-host-short/\n${{ github.workspace }}/build/staging-repository/\n"
            or upload_with.get("include-hidden-files") is not True
            or upload_with.get("if-no-files-found") != "warn"):
        raise AssertionError("raw sustained evidence upload changed")
    if steps.index(upload) <= capture_index:
        raise AssertionError("raw evidence upload must follow sustained capture")


WINDOWS_GRADLE_STDOUT_8FA = base64.b64decode(
    "DQotLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0NCkdyYWRsZSA5LjUu"
    "MA0KLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tDQoNCkJ1aWxkIHRp"
    "bWU6ICAgIDIwMjYtMDQtMjggMTI6MDU6MzAgVVRDDQpSZXZpc2lvbjogICAgICAzZmUxMTdkNjhmMzkwNzc5MGYzODA5ZjEyMWFh"
    "MzYzMDNhOTE1MWY4DQoNCktvdGxpbjogICAgICAgIDIuMy4yMA0KR3Jvb3Z5OiAgICAgICAgNC4wLjI5DQpBbnQ6ICAgICAgICAg"
    "ICBBcGFjaGUgQW50KFRNKSB2ZXJzaW9uIDEuMTAuMTUgY29tcGlsZWQgb24gQXVndXN0IDI1IDIwMjQNCkxhdW5jaGVyIEpWTTog"
    "IDIxLjAuMTIuMSAoRWNsaXBzZSBBZG9wdGl1bSAyMS4wLjEyLjErMS1MVFMpDQpEYWVtb24gSlZNOiAgICBDOlxob3N0ZWR0b29s"
    "Y2FjaGVcd2luZG93c1xKYXZhX1RlbXVyaW4tSG90c3BvdF9qZGtcMjEuMC4xMi0xMDEuMFx4NjQgKG5vIERhZW1vbiBKVk0gc3Bl"
    "Y2lmaWVkLCB1c2luZyBjdXJyZW50IEphdmEgaG9tZSkNCk9TOiAgICAgICAgICAgIFdpbmRvd3MgU2VydmVyIDIwMjUgMTAuMCBh"
    "bWQ2NA0KDQo=")


def verify_workflow_source_inventory(sources):
    expected = set(AUDITED_WORKFLOW_SHA256)
    actual = set(sources)
    if actual != expected:
        raise AssertionError(
            f"workflow source inventory changed: added={sorted(actual - expected)}, "
            f"removed={sorted(expected - actual)}")
    for name in sorted(expected):
        digest = hashlib.sha256(sources[name].encode("utf-8")).hexdigest()
        if digest != AUDITED_WORKFLOW_SHA256[name]:
            raise AssertionError(f"workflow source changed: {name}")


def run_expression_upper_bounds(source):
    lines = source.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if (re.match(r"^ *[\[{]", line)
                or re.match(r"^ *- +(?:\{|\[)", line)
                or re.match(r"^ *(?:- +)?[A-Za-z_][A-Za-z0-9_-]*[ \t]*:[ \t]*[\[{]", line)):
            raise ValueError(f"unsupported YAML flow syntax at line {index + 1}")
        if (re.match(r"^ *(?:- +)?['\"]", line)
                or re.match(r"^ *(?:- +)?\?[ \t]", line)):
            raise ValueError(f"unsupported YAML key syntax at line {index + 1}")
        if re.match(r"^ *(?:- +)?[A-Za-z_][A-Za-z0-9_-]*[ \t]*:[ \t]*[&*!]", line):
            raise ValueError(f"unsupported YAML alias or tag syntax at line {index + 1}")
        match = re.match(r"^( *)(- +)?run:[ \t]*(.*)$", line)
        if match is None:
            if (not line.lstrip().startswith("#")
                    and re.search(r"(?<![\w-])['\"]?run['\"]?[ \t]*:", line)):
                raise ValueError(f"unsupported run syntax at line {index + 1}")
            index += 1
            continue
        line_number = index + 1
        value = match.group(3)
        key_indent = len(match.group(1)) + len(match.group(2) or "")
        if not value:
            if match.group(2) or index == 0 or lines[index - 1].strip() != "defaults:":
                raise ValueError(f"unsupported run syntax at line {line_number}")
            index += 1
            continue
        if value.startswith(("|", ">")):
            if re.fullmatch(r"[|>](?:[+-][1-9]?|[1-9][+-]?)?", value) is None:
                raise ValueError(f"unsupported run syntax at line {line_number}")
            block = []
            index += 1
            while index < len(lines):
                line = lines[index]
                if line.strip() and len(line) - len(line.lstrip()) <= key_indent:
                    break
                block.append(line)
                index += 1
            conservative_content_indent = key_indent + 1
            yield line_number, sum(len(line[conservative_content_indent:]) + 1
                                   for line in block)
        else:
            if value.startswith(("'", '"', "&", "*", "!", "{", "[", "#", "?")):
                raise ValueError(f"unsupported run syntax at line {line_number}")
            next_index = index + 1
            while (next_index < len(lines)
                   and (not lines[next_index].strip()
                        or lines[next_index].lstrip().startswith("#"))):
                next_index += 1
            if (next_index < len(lines)
                    and len(lines[next_index]) - len(lines[next_index].lstrip()) > key_indent):
                raise ValueError(f"multiline plain run at line {line_number}")
            yield line_number, len(value)
            index += 1


class WorkflowExpressionLimit(unittest.TestCase):
    def test_flow_step_with_escaped_run_key_is_rejected(self):
        for key in ("steps:", "steps :", "steps  :"):
            with self.subTest(key=key):
                source = ("name: adverse\non: workflow_dispatch\njobs:\n  control:\n"
                          "    runs-on: ubuntu-latest\n    " + key
                          + ' [{"r\\u0075n": "' + "x" * (RUN_EXPRESSION_LIMIT + 1)
                          + '"}]\n')
                with self.assertRaisesRegex(ValueError, "unsupported YAML flow syntax"):
                    list(run_expression_upper_bounds(source))

    def test_unsupported_valid_run_syntax_is_rejected(self):
        job = ("name: adverse\non: workflow_dispatch\njobs:\n  control:\n"
               "    runs-on: ubuntu-latest\n    steps:\n")
        cases = (
            ("      - run : |\n          " + "x" * RUN_EXPRESSION_LIMIT + "\n",
             "unsupported run syntax"),
            ("      - run: " + "x" * 11000 + "\n          " + "x" * 10000 + "\n",
             "multiline plain run"),
            ('      - "r\\u0075n": |\n          echo hi\n',
             "unsupported YAML key syntax"),
            ('      - run: "echo hi"\n', "unsupported run syntax"),
            ("      - run: | # comment\n          echo hi\n",
             "unsupported run syntax"),
        )
        for step, error in cases:
            with self.subTest(step=step[:32]):
                with self.assertRaisesRegex(ValueError, error):
                    list(run_expression_upper_bounds(job + step))

    def test_inline_run_and_block_scalar_variants_are_bounded(self):
        cases = (
            ("- run: |", "          ", "x" * RUN_EXPRESSION_LIMIT),
            ("- run: |-", "          ", "x" * RUN_EXPRESSION_LIMIT),
            ("- run: |+", "          ", "x" * RUN_EXPRESSION_LIMIT),
            ("- run: >", "          ", "x" * RUN_EXPRESSION_LIMIT),
            ("- run: >-", "          ", "x" * RUN_EXPRESSION_LIMIT),
            ("- run: >+", "          ", "x" * RUN_EXPRESSION_LIMIT),
            ("- run: |2-", "            ", "x" * (RUN_EXPRESSION_LIMIT - 1)),
            ("- name: named\n        run: |+", "          ",
             "x" * RUN_EXPRESSION_LIMIT),
            ("- run: " + "x" * RUN_EXPRESSION_LIMIT, "", ""),
        )
        for step, indent, payload in cases:
            with self.subTest(step=step[:32]):
                source = ("name: adverse\njobs:\n  control:\n    runs-on: ubuntu-latest\n"
                          "    steps:\n      " + step + "\n" + indent + payload + "\n")
                bounds = list(run_expression_upper_bounds(source))
                self.assertEqual(len(bounds), 1)
                self.assertGreaterEqual(bounds[0][1], RUN_EXPRESSION_LIMIT)

    def workflow_sources(self):
        workflows = sorted(WORKFLOW.parent.glob("*.yml")) + sorted(WORKFLOW.parent.glob("*.yaml"))
        self.assertTrue(workflows)
        return {workflow.name: workflow.read_text(encoding="utf-8") for workflow in workflows}

    def audit_workflow_sources(self, sources):
        verify_workflow_source_inventory(sources)
        checked = 0
        violations = []
        for name, source in sorted(sources.items()):
            for line, upper_bound in run_expression_upper_bounds(source):
                checked += 1
                if name == WORKFLOW.name:
                    self.assertLess(upper_bound, RUN_EXPRESSION_LIMIT)
                if upper_bound >= RUN_EXPRESSION_LIMIT:
                    violations.append((name, line, upper_bound))
        self.assertEqual(checked, 66)
        self.assertEqual(violations, [])

    def test_changed_workflow_sources_are_rejected(self):
        sources = self.workflow_sources()
        windows = "windows-collision-focus.yml"
        payload = "x" * (RUN_EXPRESSION_LIMIT + 1)
        job = "  expression_limit_adverse:\n    runs-on: ubuntu-latest\n    steps:\n"
        cases = (
            ("tagged", job + '      - !!map {"r\\u0075n": "' + payload + '"}\n'),
            ("anchored", job + '      - &one {"r\\u0075n": "' + payload
             + '"}\n      - *one\n'),
            ("one character", " "),
        )
        for label, addition in cases:
            with self.subTest(change=label):
                changed = dict(sources)
                changed[windows] += addition
                with self.assertRaisesRegex(AssertionError, "workflow source"):
                    self.audit_workflow_sources(changed)
        added = dict(sources)
        added["new-workflow.yml"] = ("name: new\non: workflow_dispatch\njobs:\n  control:\n"
                                     "    runs-on: ubuntu-latest\n    steps:\n"
                                     "      - run: echo new\n")
        with self.assertRaisesRegex(AssertionError, "workflow source"):
            self.audit_workflow_sources(added)
        removed = dict(sources)
        del removed[windows]
        with self.assertRaisesRegex(AssertionError, "workflow source"):
            self.audit_workflow_sources(removed)

    def test_native_run_is_below_limit_and_all_workflows_are_audited(self):
        sources = self.workflow_sources()
        self.audit_workflow_sources(sources)
        for name, source in sources.items():
            with self.subTest(workflow=name):
                self.assertNotRegex(source, r"(?m)^\s*runs-on:\s*.*\bmacos-[\w-]+")

    def test_sustained_workflow_rejects_missing_or_altered_key_steps(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        verify_sustained_workflow_contract(source)
        baseline = yaml.safe_load(source)

        def capture_step(document):
            return next(step for step in document["jobs"]["capture"]["steps"]
                        if step.get("name") == "Stage and capture on selected host")

        def move_capture_to_validation(document):
            step = capture_step(document)
            document["jobs"]["capture"]["steps"].remove(step)
            document["jobs"]["validate-target"]["steps"].append(step)

        mutations = (
            ("validation conditional excludes optimized dispatch",
             lambda doc: doc["jobs"]["validate-target"].__setitem__(
                 "if", "${{ inputs.build == 'development' }}"),
             "Windows target validation route changed"),
            ("disabled capture", lambda doc: capture_step(doc).__setitem__("if", False),
             "sustained capture step is conditional or altered"),
            ("step overrides target binding",
             lambda doc: capture_step(doc).__setitem__("env", {"TARGET": "jvm"}),
             "effective sustained capture dispatch bindings changed"),
            ("step overrides build binding",
             lambda doc: capture_step(doc).__setitem__("env", {"BUILD": "development"}),
             "effective sustained capture dispatch bindings changed"),
            ("wrong target binding", lambda doc: doc["jobs"]["capture"]["env"].__setitem__("TARGET", "jvm"),
             "sustained capture job route or dispatch bindings changed"),
            ("wrong build binding", lambda doc: doc["jobs"]["capture"]["env"].__setitem__("BUILD", "development"),
             "sustained capture job route or dispatch bindings changed"),
            ("capture outside selected host job", move_capture_to_validation,
             "sustained capture step is missing or duplicated"),
            ("wrong dispatched target choices", lambda doc: doc[True]["workflow_dispatch"]["inputs"]["target"].__setitem__("options", ["jvm"]),
             "workflow_dispatch target input changed"),
        )
        for label, mutate, error in mutations:
            with self.subTest(change=label):
                adverse = copy.deepcopy(baseline)
                mutate(adverse)
                with self.assertRaisesRegex(AssertionError, error):
                    verify_sustained_workflow_contract(yaml.safe_dump(adverse, sort_keys=False))


def workflow_nodes():
    tree = ast.parse(RUNNER.read_text(), filename=str(RUNNER))
    raw = next(node for node in tree.body
               if isinstance(node, ast.FunctionDef) and node.name == "raw_file")
    sidecar = next((node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == "sidecar_bytes"), None)
    routes = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.For) and isinstance(node.target, ast.Name)
                  and node.target.id == "api")
    receipt = next(node for node in ast.walk(tree)
                   if isinstance(node, ast.Expr) and "route-result.json" in ast.unparse(node))
    gradle = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.If) and len(node.body) == 1
                  and isinstance(node.body[0], ast.Raise)
                  and "selected Gradle is not 9.5.0" in ast.unparse(node.body[0]))
    guard = next(node for node in ast.walk(tree)
                 if isinstance(node, ast.If) and len(node.body) == 1
                 and isinstance(node.body[0], ast.Raise)
                 and "one or more Native host controls failed" in ast.unparse(node.body[0]))
    return raw, sidecar, routes, receipt, gradle, guard


class GrowingFile:
    def __init__(self, size=0):
        self.size = size
        self.read_bytes = 0
        self.remaining = RAW_LIMIT + 1024 * 1024

    def is_file(self):
        return True

    def stat(self):
        return SimpleNamespace(st_size=self.size, st_dev=1, st_ino=1,
                               st_mtime_ns=1, st_ctime_ns=1)

    def open(self, mode):
        if mode != "rb":
            raise AssertionError(mode)
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self, size):
        count = min(size, self.remaining)
        self.remaining -= count
        self.read_bytes += count
        return b"x" * count


class UnreadableFile(GrowingFile):
    def open(self, mode):
        raise OSError("injected raw read failure")


class HostedRawFileContract(unittest.TestCase):
    def test_native_runner_xcode_pin_accepts_26_5_and_rejects_26_4_1(self):
        tree = ast.parse(RUNNER.read_text(), filename=str(RUNNER))
        validator = next(node for node in tree.body
                         if isinstance(node, ast.FunctionDef)
                         and node.name == "validate_xcode_version")
        scope = {"re": re}
        exec(compile(ast.Module(body=[validator], type_ignores=[]), str(RUNNER), "exec"), scope)
        scope["validate_xcode_version"]("Xcode 26.5\nBuild version 17F42\n")
        with self.assertRaisesRegex(RuntimeError, "not 26.5"):
            scope["validate_xcode_version"]("Xcode 26.4.1\nBuild version 17E303\n")
        scope["validate_xcode_version"]("Xcode 26.5\nBuild version 18A1\n")
        for build in ("Build version ", "Build version    ",
                      "Build version 17 F42", "Build version 17F42!", "17F42"):
            with self.subTest(build=build), self.assertRaisesRegex(RuntimeError, "not 26.5"):
                scope["validate_xcode_version"](f"Xcode 26.5\n{build}\n")

    def setUp(self):
        (self.raw_node, self.sidecar_node, self.route_node, self.receipt_node,
         self.gradle_node, self.guard_node) = workflow_nodes()
        self.scope = {"hashlib": hashlib, "json": json, "Path": Path, "sys": sys,
                      "errno": errno, "re": re}
        tree = ast.parse(RUNNER.read_text(), filename=str(RUNNER))
        resident_check = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                              and node.name == "resident_probe_errors_complete")
        heap_check = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                          and node.name == "validate_heap_csv")
        functions = [self.raw_node] + ([self.sidecar_node] if self.sidecar_node else [])
        functions.extend((heap_check, resident_check))
        exec(compile(ast.Module(body=functions, type_ignores=[]),
                     str(RUNNER), "exec"), self.scope)

    def terminal_receipt(self):
        terminal = {"monotonic_ns": 30, "error_observed_monotonic_ns": 31,
                    "exit_observed_monotonic_ns": 32, "exit_code": 0,
                    "returncode_at_error": 0,
                    "returncode_checked_monotonic_ns": 32,
                    "errno": errno.ESRCH, "classification": "terminal_esrch_exit_confirmed",
                    "error": "[Errno 3] macOS process resident bytes unavailable"}
        resident = {"method": "proc_pidinfo_task_resident", "samples": [[10, 4096]],
                    "errors": [terminal]}
        capture = {"rss_observation": {"samples": 1, "errors": 1}}
        execution = {"started_monotonic_ns": 1, "ended_monotonic_ns": 40,
                     "termination": "natural", "exit_code": 0}
        return resident, capture, execution

    def no_error_receipt(self):
        resident, capture, execution = self.terminal_receipt()
        resident["method"] = "GetProcessMemoryInfo_working_set"
        resident["errors"] = []
        capture["rss_observation"]["errors"] = 0
        return resident, capture, execution

    def test_no_error_method_matches_each_selected_target(self):
        check = self.scope["resident_probe_errors_complete"]
        methods = {"macosArm64": "proc_pidinfo_task_resident",
                   "mingwX64": "GetProcessMemoryInfo_working_set"}
        for target, expected in methods.items():
            for method in (None, "", next(value for value in methods.values()
                                            if value != expected)):
                with self.subTest(target=target, method=method):
                    resident, capture, execution = self.no_error_receipt()
                    resident["method"] = method
                    self.assertFalse(check(resident, capture, execution, target))
            with self.subTest(target=target, method=expected):
                resident, capture, execution = self.no_error_receipt()
                resident["method"] = expected
                self.assertTrue(check(resident, capture, execution, target))

    def test_terminal_method_matches_selected_target(self):
        check = self.scope["resident_probe_errors_complete"]
        for method in (None, "", "GetProcessMemoryInfo_working_set"):
            with self.subTest(method=method):
                resident, capture, execution = self.terminal_receipt()
                resident["method"] = method
                self.assertFalse(check(resident, capture, execution, "macosArm64"))
        resident, capture, execution = self.terminal_receipt()
        self.assertFalse(check(resident, capture, execution, "mingwX64"))

    def test_memory_identity_requires_exact_positive_pids_in_each_sidecar(self):
        tree = ast.parse(RUNNER.read_text(), filename=str(RUNNER))
        identity_guard = next(node.test for node in ast.walk(tree)
                              if isinstance(node, ast.If) and any(
                                  isinstance(child, ast.Raise) and
                                  isinstance(child.exc, ast.Call) and
                                  any(isinstance(arg, ast.Constant) and
                                      arg.value == "Native memory receipt or sidecar identity differs"
                                      for arg in child.exc.args)
                                  for child in node.body))
        expression = compile(ast.Expression(body=identity_guard), str(RUNNER), "eval")
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory)
            for name in ("stdout.raw", "stderr.raw", "rss.csv", "heap.csv"):
                (archive / name).touch()
            capture = {"mode": "memory", "source_sha": "source", "target": "mingwX64",
                       "build": "development", "scenario": {"api": "direct_kotlin"},
                       "pid": 1, "process_image_identity": "observed",
                       "managed_heap_observation": {
                           "status": "observed_kotlin_heap_after_collection", "stages": 3}}
            execution = {"pid": 1, "raw_collection": "selected_process_exited",
                         "termination": "natural", "exit_code": 0}
            resident = {"pid": 1}
            scope = {"capture": capture, "execution": execution, "resident": resident,
                     "run": {"mode": "memory", "qualification": "unpassed"},
                     "sha": "source", "target": "mingwX64", "build": "development",
                     "api": "direct_kotlin", "archive": archive}
            self.assertFalse(eval(expression, scope))
            for record in (capture, execution, resident):
                for malformed in (1.0, True, False, 0, -1, "1", None):
                    with self.subTest(record=record, malformed=malformed):
                        record["pid"] = malformed
                        self.assertTrue(eval(expression, scope))
                        record["pid"] = 1

    def test_memory_heap_receipt_in_true_outer_route(self):
        def stdout_for(heap_csv):
            return b"".join(b"DYN4K\tHEAP\t" + line.replace(b",", b"\t") + b"\n"
                            for line in heap_csv.splitlines()[1:] if line)

        def heap_case(label, heap_csv):
            return label, 3, heap_csv, stdout_for(heap_csv), False

        stage_cases = tuple((f"stages_{stages}", stages, VALID_HEAP_CSV,
                             VALID_HEAP_STDOUT, type(stages) is int and stages == 3)
                            for stages in (3, 3.0, 3.5, True, "3", None, 0, -1))
        heap_cases = (
            heap_case("header_only", b"stage,retained_heap_bytes,gc_epoch\n"),
            heap_case("two_rows", VALID_HEAP_CSV.rsplit(b"measured,", 1)[0]),
            heap_case("garbage", b"not,a,heap,csv\n"),
            heap_case("wrong_order", b"stage,retained_heap_bytes,gc_epoch\n"
                      b"after_reset,2048,2\nconstructed,1024,1\nmeasured,3072,3\n"),
            heap_case("duplicate_stage", b"stage,retained_heap_bytes,gc_epoch\n"
                      b"constructed,1024,1\nconstructed,2048,2\nmeasured,3072,3\n"),
            heap_case("extra_row", VALID_HEAP_CSV + b"measured,4096,4\n"),
            heap_case("blank_row", VALID_HEAP_CSV.replace(b"after_reset,", b"\nafter_reset,")),
            heap_case("zero_bytes", VALID_HEAP_CSV.replace(b"1024", b"0")),
            heap_case("negative_bytes", VALID_HEAP_CSV.replace(b"1024", b"-1")),
            heap_case("float_bytes", VALID_HEAP_CSV.replace(b"1024", b"1024.0")),
            heap_case("zero_epoch", VALID_HEAP_CSV.replace(b"1024,1", b"1024,0")),
            heap_case("repeat_epoch", VALID_HEAP_CSV.replace(b"2048,2", b"2048,1")),
            heap_case("decrease_epoch", VALID_HEAP_CSV.replace(b"3072,3", b"3072,1")),
            heap_case("float_epoch", VALID_HEAP_CSV.replace(b"2048,2", b"2048,2.0")),
            heap_case("missing_final_newline", VALID_HEAP_CSV[:-1]),
            ("missing_raw_heap", 3, VALID_HEAP_CSV, b"", False),
            ("mismatched_raw_heap", 3, VALID_HEAP_CSV,
             VALID_HEAP_STDOUT.replace(b"2048", b"2049"), False),
            ("valid_crlf", 3, VALID_HEAP_CSV.replace(b"\n", b"\r\n"),
             VALID_HEAP_STDOUT.replace(b"\n", b"\r\n"), True),
        )
        cases = (("macosArm64", False), ("mingwX64", False),
                 ("macosArm64", True))
        for target, terminal in cases:
            selected_cases = stage_cases + heap_cases
            if target == "macosArm64" and not terminal:
                selected_cases += (("oversized", 3, b"x" * (8 * 1024 * 1024 + 1),
                                    b"", False),)
            for label, stages, heap_csv, stdout, valid in selected_cases:
                with self.subTest(target=target, terminal=terminal, case=label), \
                        tempfile.TemporaryDirectory() as directory:
                    evidence = Path(directory)
                    route = {"qualification": "unpassed", "commands": {}, "scenarios": {},
                             "memory_scenarios": {}}

                    def execute(label, argv, timeout):
                        archive = argv[argv.index("--archive") + 1]
                        archive.mkdir(parents=True)
                        route["commands"][label] = {"exit_code": 0, "termination": "natural"}
                        if argv[argv.index("--mode") + 1] != "memory":
                            return True, None, None
                        api = "direct_kotlin" if "direct_kotlin" in label else "compatibility"
                        (archive / "stdout.raw").write_bytes(stdout)
                        (archive / "stderr.raw").write_bytes(b"")
                        (archive / "heap.csv").write_bytes(heap_csv)
                        (archive / "rss.csv").write_text(
                            "monotonic_ns,resident_bytes\n10,4096\n20,8192\n")
                        error = {"monotonic_ns": 30, "error_observed_monotonic_ns": 31,
                                 "exit_observed_monotonic_ns": 32, "exit_code": 0,
                                 "returncode_at_error": 0,
                                 "returncode_checked_monotonic_ns": 32,
                                 "errno": errno.ESRCH,
                                 "classification": "terminal_esrch_exit_confirmed",
                                 "error": "[Errno 3] macOS process resident bytes unavailable"}
                        resident = {"pid": 123,
                                    "method": ("proc_pidinfo_task_resident" if
                                               target == "macosArm64" else
                                               "GetProcessMemoryInfo_working_set"),
                                    "samples": [[10, 4096], [20, 8192]],
                                    "errors": [error] if terminal else [],
                                    "status": "observed_diagnostic"}
                        (archive / "rss.json").write_text(json.dumps(resident))
                        execution = {"pid": 123, "raw_collection": "selected_process_exited",
                                     "termination": "natural", "exit_code": 0,
                                     "started_monotonic_ns": 1,
                                     "ended_monotonic_ns": 40,
                                     "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
                                     "stderr_sha256": hashlib.sha256(b"").hexdigest()}
                        (archive / "execution.json").write_text(json.dumps(execution))
                        (archive / "run.json").write_text(json.dumps({
                            "mode": "memory", "qualification": "unpassed"}))
                        capture = {"mode": "memory", "source_sha": "local-control",
                                   "target": target, "build": "development",
                                   "scenario": {"api": api}, "pid": 123,
                                   "process_image_identity": "observed",
                                   "observed_image": {"identity_kind": "mapped_executable"},
                                   "execution_sha256": hashlib.sha256(
                                       (archive / "execution.json").read_bytes()).hexdigest(),
                                   "rss_observation": {
                                       "status": "observed_diagnostic", "samples": 2,
                                       "errors": int(terminal),
                                       "rss_json_sha256": hashlib.sha256(
                                           (archive / "rss.json").read_bytes()).hexdigest()},
                                   "managed_heap_observation": {
                                       "status": "observed_kotlin_heap_after_collection",
                                       "stages": stages,
                                       "heap_csv_sha256": hashlib.sha256(
                                           (archive / "heap.csv").read_bytes()).hexdigest()}}
                        (archive / "capture.json").write_text(json.dumps(capture))
                        return True, None, None

                    self.scope.update(evidence=evidence, route=route, execute=execute,
                                      root=WORKFLOW.parents[2],
                                      inventory=evidence / "inventory.json",
                                      staging=evidence / "stage", target=target,
                                      build="development", sha="local-control",
                                      image_control=True)
                    exec(compile(ast.Module(body=[self.route_node], type_ignores=[]),
                                 str(RUNNER), "exec"), self.scope)
                    expected = "observed_diagnostic" if valid else "failed"
                    for api in ("direct_kotlin", "compatibility"):
                        result = route["memory_scenarios"][api]
                        self.assertEqual(result["status"], expected)
                        failure = evidence / f"captures/memory/{api}-failure.json"
                        if expected == "failed":
                            self.assertIn("Native memory sidecar exceeds read limit" if
                                          label == "oversized" else "Native heap CSV",
                                          result["error"])
                            failed = json.loads(failure.read_text())
                            self.assertEqual(failed["qualification"], "unpassed")
                            self.assertEqual(failed["raw"]["stdout.raw"]["sha256"],
                                             hashlib.sha256(stdout).hexdigest())
                        else:
                            self.assertFalse(failure.exists())

    def test_ordered_live_sample_clocks_accept_in_both_routes(self):
        check = self.scope["resident_probe_errors_complete"]
        for no_error in (False, True):
            with self.subTest(no_error=no_error):
                resident, capture, execution = (
                    self.no_error_receipt() if no_error else self.terminal_receipt())
                resident["samples"] = [[10, 4096], [20, 8192]]
                capture["rss_observation"]["samples"] = 2
                target = "mingwX64" if no_error else "macosArm64"
                self.assertTrue(check(resident, capture, execution, target))

    def test_sample_clocks_must_fit_process_interval_in_both_routes(self):
        check = self.scope["resident_probe_errors_complete"]
        for no_error in (False, True):
            for stamp in (0, 50):
                with self.subTest(no_error=no_error, stamp=stamp):
                    resident, capture, execution = (
                        self.no_error_receipt() if no_error else self.terminal_receipt())
                    resident["samples"][0][0] = stamp
                    target = "mingwX64" if no_error else "macosArm64"
                    self.assertFalse(check(resident, capture, execution, target))

    def test_sample_clocks_must_be_nondecreasing_in_both_routes(self):
        check = self.scope["resident_probe_errors_complete"]
        for no_error in (False, True):
            with self.subTest(no_error=no_error):
                resident, capture, execution = (
                    self.no_error_receipt() if no_error else self.terminal_receipt())
                resident["samples"] = [[20, 4096], [10, 8192]]
                capture["rss_observation"]["samples"] = 2
                target = "mingwX64" if no_error else "macosArm64"
                self.assertFalse(check(resident, capture, execution, target))

    def test_no_error_route_requires_valid_execution_interval_and_zero_exit(self):
        check = self.scope["resident_probe_errors_complete"]
        cases = ({"started_monotonic_ns": True}, {"ended_monotonic_ns": 40.0},
                 {"started_monotonic_ns": 41}, {"ended_monotonic_ns": 1},
                 {"started_monotonic_ns": 10, "ended_monotonic_ns": 10},
                 {"exit_code": False}, {"termination": "host_deadline"})
        for change in cases:
            with self.subTest(change=change):
                resident, capture, execution = self.no_error_receipt()
                execution.update(change)
                self.assertFalse(check(resident, capture, execution, "mingwX64"))

    def test_terminal_esrch_accepts_exact_integer_receipt(self):
        resident, capture, execution = self.terminal_receipt()
        self.assertTrue(self.scope["resident_probe_errors_complete"](
            resident, capture, execution, "macosArm64"))

    def test_terminal_esrch_rejects_float_returncode_check_time(self):
        resident, capture, execution = self.terminal_receipt()
        resident["errors"][0]["returncode_checked_monotonic_ns"] = 32.0
        self.assertFalse(self.scope["resident_probe_errors_complete"](
            resident, capture, execution, "macosArm64"))

    def test_terminal_esrch_rejects_float_errno(self):
        resident, capture, execution = self.terminal_receipt()
        resident["errors"][0]["errno"] = float(errno.ESRCH)
        self.assertFalse(self.scope["resident_probe_errors_complete"](
            resident, capture, execution, "macosArm64"))

    def test_terminal_esrch_rejects_boolean_sample_time(self):
        resident, capture, execution = self.terminal_receipt()
        resident["samples"][0][0] = True
        self.assertFalse(self.scope["resident_probe_errors_complete"](
            resident, capture, execution, "macosArm64"))

    def test_terminal_esrch_rejects_malformed_sample_bytes(self):
        check = self.scope["resident_probe_errors_complete"]
        for value in (True, 4096.0, "4096", 0, -1):
            with self.subTest(resident_bytes=value):
                resident, capture, execution = self.terminal_receipt()
                resident["samples"][0][1] = value
                self.assertFalse(check(resident, capture, execution, "macosArm64"))

    def test_terminal_esrch_requires_exact_sample_pairs(self):
        check = self.scope["resident_probe_errors_complete"]
        for sample in ([10], [10, 4096, 99], (10, 4096)):
            with self.subTest(sample=sample):
                resident, capture, execution = self.terminal_receipt()
                resident["samples"] = [sample]
                self.assertFalse(check(resident, capture, execution, "macosArm64"))

    def test_terminal_esrch_requires_string_error(self):
        resident, capture, execution = self.terminal_receipt()
        resident["errors"][0]["error"] = ["macOS process resident bytes unavailable"]
        self.assertFalse(self.scope["resident_probe_errors_complete"](
            resident, capture, execution, "macosArm64"))

    def test_terminal_esrch_requires_integer_sample_count(self):
        resident, capture, execution = self.terminal_receipt()
        capture["rss_observation"]["samples"] = True
        self.assertFalse(self.scope["resident_probe_errors_complete"](
            resident, capture, execution, "macosArm64"))

    def test_later_zero_exit_does_not_prove_probe_time_exit(self):
        row = {"monotonic_ns": 10, "error_observed_monotonic_ns": 11,
               "exit_observed_monotonic_ns": 9_000_011, "exit_code": 0,
               "errno": errno.ESRCH, "classification": "terminal_esrch_exit_confirmed",
               "error": "[Errno 3] macOS process resident bytes unavailable"}
        resident = {"method": "proc_pidinfo_task_resident", "samples": [[5, 4096]],
                    "errors": [row]}
        capture_receipt = {"rss_observation": {"samples": 1, "errors": 1}}
        execution = {"started_monotonic_ns": 1, "ended_monotonic_ns": 10_000_000,
                     "termination": "natural", "exit_code": 0}
        self.assertFalse(self.scope["resident_probe_errors_complete"](
            resident, capture_receipt, execution, "macosArm64"))
        falsely_claimed = {**row, "returncode_at_error": 0,
                           "returncode_checked_monotonic_ns": 9_000_011}
        self.assertFalse(self.scope["resident_probe_errors_complete"](
            {**resident, "errors": [falsely_claimed]}, capture_receipt,
            execution, "macosArm64"))

    def test_terminal_esrch_requires_confirmed_exit_and_no_midrun_error(self):
        check = self.scope["resident_probe_errors_complete"]
        terminal = {"monotonic_ns": 30, "error_observed_monotonic_ns": 31,
                    "exit_observed_monotonic_ns": 32, "exit_code": 0,
                    "returncode_at_error": 0,
                    "returncode_checked_monotonic_ns": 32,
                    "errno": errno.ESRCH, "classification": "terminal_esrch_exit_confirmed",
                    "error": "[Errno 3] macOS process resident bytes unavailable"}
        resident = {"method": "proc_pidinfo_task_resident", "samples": [[10, 4096]],
                    "errors": [terminal]}
        capture_receipt = {"rss_observation": {"samples": 1, "errors": 1}}
        execution = {"started_monotonic_ns": 1, "ended_monotonic_ns": 40,
                     "termination": "natural", "exit_code": 0}
        self.assertTrue(check(resident, capture_receipt, execution, "macosArm64"))
        self.assertFalse(check(resident, capture_receipt, execution, "mingwX64"))
        self.assertFalse(check({**resident, "samples": [[35, 4096]]},
                               capture_receipt, execution, "macosArm64"))
        self.assertFalse(check({**resident, "errors": [terminal, terminal]},
                               capture_receipt, execution, "macosArm64"))
        self.assertFalse(check({**resident, "errors": ["bad row"]},
                               capture_receipt, execution, "macosArm64"))
        self.assertFalse(check(resident, capture_receipt,
                               {**execution, "ended_monotonic_ns": 31}, "macosArm64"))
        self.assertFalse(check({**resident, "errors": [{**terminal,
            "exit_observed_monotonic_ns": 50_000_032}]}, capture_receipt,
            {**execution, "ended_monotonic_ns": 50_000_040}, "macosArm64"))
        midrun = {**terminal, "errno": 5, "error": "[Errno 5] denied"}
        self.assertFalse(check({**resident, "errors": [midrun]},
                               capture_receipt, execution, "macosArm64"))
        archived_unconfirmed = {"monotonic_ns": 674382974750,
                                "error": "[Errno 3] macOS process resident bytes unavailable"}
        self.assertFalse(check({**resident, "errors": [archived_unconfirmed]},
                               capture_receipt, execution, "macosArm64"))

    def test_terminal_esrch_rejects_boolean_numeric_fields(self):
        check = self.scope["resident_probe_errors_complete"]
        terminal = {"monotonic_ns": 30, "error_observed_monotonic_ns": 31,
                    "exit_observed_monotonic_ns": 32, "exit_code": 0,
                    "returncode_at_error": 0,
                    "returncode_checked_monotonic_ns": 32,
                    "errno": errno.ESRCH, "classification": "terminal_esrch_exit_confirmed",
                    "error": "[Errno 3] macOS process resident bytes unavailable"}
        resident = {"method": "proc_pidinfo_task_resident", "samples": [[10, 4096]],
                    "errors": [terminal]}
        capture_receipt = {"rss_observation": {"samples": 1, "errors": 1}}
        execution = {"started_monotonic_ns": 1, "ended_monotonic_ns": 40,
                     "termination": "natural", "exit_code": 0}
        self.assertTrue(check(resident, capture_receipt, execution, "macosArm64"))
        for field in ("exit_code", "returncode_at_error"):
            with self.subTest(row_field=field):
                malformed = {**resident, "errors": [{**terminal, field: False}]}
                self.assertFalse(check(malformed, capture_receipt, execution,
                                       "macosArm64"))
        with self.subTest(execution_field="exit_code"):
            self.assertFalse(check(resident, capture_receipt,
                                   {**execution, "exit_code": False}, "macosArm64"))
        with self.subTest(capture_field="errors"):
            self.assertFalse(check(resident, {"rss_observation": {"samples": 1,
                                                                  "errors": True}},
                                   execution, "macosArm64"))
        with self.subTest(execution_field="started_monotonic_ns"):
            self.assertFalse(check(resident, capture_receipt,
                                   {**execution, "started_monotonic_ns": False},
                                   "macosArm64"))

    def test_windows_image_control_uses_exact_inventory_executable(self):
        tree = ast.parse(RUNNER.read_text(), filename=str(RUNNER))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "path_swap_command")
        scope = {"Path": Path, "sys": sys}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(RUNNER), "exec"), scope)
        root = WORKFLOW.parents[2]
        harness = Path("/selected/dyn4k-performance-portable.exe")
        selected = {"harness": str(harness),
                    "bundle_sha256": {harness.name: "a" * 64}}
        output = Path("/evidence/setup/path-swap.json")
        command = scope["path_swap_command"](root, output, "mingwX64", selected, "b" * 40)
        self.assertEqual(command[-6:], ["--control-image", harness, "--control-sha256",
                                        "a" * 64, "--control-source-sha", "b" * 40])
        self.assertNotIn("ping.exe", " ".join(map(str, command)))
        self.assertEqual(scope["path_swap_command"](root, output, "macosArm64", selected,
                                                     "b" * 40)[-2:], ["--output", output])
        with self.assertRaisesRegex(ValueError, "inventory executable hash"):
            scope["path_swap_command"](root, output, "mingwX64",
                                       {**selected, "bundle_sha256": {}}, "b" * 40)

    def test_growing_zero_size_file_has_bounded_incomplete_hash(self):
        growing = GrowingFile()
        result = self.scope["raw_file"](growing)
        self.assertEqual(growing.read_bytes, 1)
        self.assertEqual(result["status"], "changed_during_hash")
        self.assertNotIn("sha256", result)
        oversized = GrowingFile(RAW_LIMIT + 1)
        self.assertEqual(self.scope["raw_file"](oversized)["status"], "hash_size_limit")
        self.assertEqual(oversized.read_bytes, 0)

    def test_growing_memory_sidecar_has_bounded_incomplete_snapshot(self):
        growing = GrowingFile()
        with self.assertRaisesRegex(ValueError, "changed during read"):
            self.scope["sidecar_bytes"](growing)
        self.assertEqual(growing.read_bytes, 1)
        oversized = GrowingFile(8 * 1024 * 1024 + 1)
        with self.assertRaisesRegex(ValueError, "exceeds read limit"):
            self.scope["sidecar_bytes"](oversized)
        self.assertEqual(oversized.read_bytes, 0)

    def test_failed_cleanup_keeps_second_route_and_unpassed_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory)
            growing = GrowingFile()
            unreadable = UnreadableFile()
            actual_raw_file = self.scope["raw_file"]
            labels = []

            def routed_raw_file(path):
                if path.parent.name == "direct_kotlin" and path.name == "stdout.raw":
                    return actual_raw_file(growing)
                if path.parent.name == "compatibility" and path.name == "stderr.raw":
                    return actual_raw_file(unreadable)
                return actual_raw_file(path)

            route = {"qualification": "unpassed", "commands": {}, "scenarios": {},
                     "memory_scenarios": {}}

            def execute(label, argv, timeout):
                labels.append(label)
                archive = argv[argv.index("--archive") + 1]
                archive.mkdir(parents=True)
                (archive / "stdout.raw").write_bytes(b"raw-out")
                (archive / "stderr.raw").write_bytes(b"raw-err")
                route["commands"][label] = {"termination": "deadline_tree_unverified",
                                            "error": "timeout", "exit_code": -9}
                return False, None, None

            self.scope.update(raw_file=routed_raw_file, execute=execute,
                              evidence=evidence, route=route, root=WORKFLOW.parents[2],
                              inventory=evidence / "inventory.json", staging=evidence / "stage",
                              target="macosArm64", build="development", sha="local-control")
            exec(compile(ast.Module(body=[self.route_node], type_ignores=[]),
                         str(RUNNER), "exec"), self.scope)
            self.scope["image_control"] = False
            with self.assertRaisesRegex(RuntimeError, "Native host controls failed"):
                exec(compile(ast.Module(body=[self.guard_node], type_ignores=[]),
                             str(RUNNER), "exec"), self.scope)
            exec(compile(ast.Module(body=[self.receipt_node], type_ignores=[]),
                         str(RUNNER), "exec"), self.scope)
            self.assertEqual(labels, ["captures/direct_kotlin-command",
                                      "captures/memory/direct_kotlin-command",
                                      "captures/compatibility-command",
                                      "captures/memory/compatibility-command"])
            persisted = json.loads((evidence / "route-result.json").read_text())
            self.assertEqual(persisted["qualification"], "unpassed")
            self.assertEqual(len(persisted["scenarios"]), 2)
            self.assertEqual(len(persisted["memory_scenarios"]), 2)
            direct = json.loads((evidence / "captures/direct_kotlin-failure.json").read_text())
            compatibility = json.loads((evidence / "captures/compatibility-failure.json").read_text())
            memory_direct = json.loads((evidence / "captures/memory/direct_kotlin-failure.json").read_text())
            memory_compatibility = json.loads((evidence / "captures/memory/compatibility-failure.json").read_text())
            self.assertEqual(direct["raw"]["stdout.raw"]["status"], "changed_during_hash")
            self.assertEqual(compatibility["raw"]["stderr.raw"]["status"], "unreadable")
            self.assertEqual(direct["raw"]["stderr.raw"], {
                "bytes": 7, "sha256": hashlib.sha256(b"raw-err").hexdigest()})
            for receipt in (direct, compatibility, memory_direct, memory_compatibility):
                self.assertEqual(receipt["qualification"], "unpassed")
                self.assertEqual(receipt["raw_collection"], "incomplete")
            self.assertEqual(memory_direct["mode"], "memory")
            self.assertEqual(memory_compatibility["mode"], "memory")
            self.assertEqual(growing.read_bytes, 2)

    def test_memory_commands_and_unavailable_probe_preserve_both_api_routes(self):
        source = WORKFLOW.read_text()
        self.assertIn("workflow_dispatch:", source)
        self.assertNotIn("  push:", source)
        self.assertIn("if: always()", source)
        self.assertIn('run: python -B "$GITHUB_WORKSPACE/tools/performance/sustained_portable/native_hosted_short_runner.py"', source)
        self.assertNotIn("python -B - <<'PY'", source)
        self.assertIn('if Path(__file__).resolve() != selected_runner:', RUNNER.read_text())
        self.assertNotRegex(source, r"(?m)^\s*runs-on:\s*.*\bmacos-[\w-]+")
        local_mac_route = re.sub(
            r"\s+", " ", Path(__file__).with_name("native-hosted-short.md").read_text())
        self.assertIn("Run `macosArm64` on the installed local Mac over SSH with Xcode 26.5",
                      local_mac_route)
        self.assertIn("Do not dispatch the GitHub-hosted macOS workflow.", local_mac_route)
        self.assertIn("windows-2025", source)
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory)
            route = {"qualification": "unpassed", "commands": {}, "scenarios": {},
                     "memory_scenarios": {}}
            calls = []

            def execute(label, argv, timeout):
                calls.append((label, argv, timeout))
                archive = argv[argv.index("--archive") + 1]
                archive.mkdir(parents=True)
                (archive / "stdout.raw").write_bytes(VALID_HEAP_STDOUT)
                (archive / "stderr.raw").write_bytes(b"")
                (archive / "capture.json").write_text("{}")
                route["commands"][label] = {"exit_code": 0, "termination": "natural"}
                if "--mode" in argv and argv[argv.index("--mode") + 1] == "memory":
                    api = "direct_kotlin" if "direct_kotlin" in label else "compatibility"
                    status = "unavailable_or_partial" if api == "direct_kotlin" else "observed_diagnostic"
                    terminal = {"monotonic_ns": 2, "error_observed_monotonic_ns": 3,
                                "exit_observed_monotonic_ns": 4, "exit_code": 0,
                                "returncode_at_error": 0,
                                "returncode_checked_monotonic_ns": 4,
                                "errno": errno.ESRCH,
                                "classification": "terminal_esrch_exit_confirmed",
                                "error": "[Errno 3] macOS process resident bytes unavailable"}
                    (archive / "execution.json").write_text(json.dumps({
                        "pid": 123, "raw_collection": "selected_process_exited",
                        "termination": "natural", "exit_code": 0,
                        "started_monotonic_ns": 0, "ended_monotonic_ns": 5,
                        "stdout_sha256": hashlib.sha256(VALID_HEAP_STDOUT).hexdigest(),
                        "stderr_sha256": hashlib.sha256(b"").hexdigest()}))
                    (archive / "rss.json").write_text(json.dumps({
                        "pid": 123, "status": status,
                        "method": "proc_pidinfo_task_resident",
                        "samples": [] if api == "direct_kotlin" else [[1, 4096]],
                        "errors": [{"error": "probe denied"}] if api == "direct_kotlin"
                                  else [terminal]}))
                    (archive / "run.json").write_text(json.dumps({
                        "mode": "memory", "qualification": "unpassed"}))
                    (archive / "rss.csv").write_text(
                        "monotonic_ns,resident_bytes\n" +
                        ("1,4096\n" if api == "compatibility" else ""))
                    (archive / "heap.csv").write_bytes(VALID_HEAP_CSV)
                    (archive / "capture.json").write_text(json.dumps({
                        "mode": "memory", "source_sha": "local-control", "target": "macosArm64",
                        "build": "development", "scenario": {"api": api}, "pid": 123,
                        "process_image_identity": "observed", "observed_image": {"pid": 123},
                        "execution_sha256": hashlib.sha256((archive / "execution.json").read_bytes()).hexdigest(),
                        "rss_observation": {"status": status,
                                            "samples": 0 if api == "direct_kotlin" else 1,
                                            "errors": 1,
                                            "rss_json_sha256": hashlib.sha256(
                                                (archive / "rss.json").read_bytes()).hexdigest()},
                        "managed_heap_observation": {
                            "status": "observed_kotlin_heap_after_collection", "stages": 3,
                            "heap_csv_sha256": hashlib.sha256(
                                (archive / "heap.csv").read_bytes()).hexdigest()}}))
                return True, None, None

            self.scope.update(evidence=evidence, route=route, execute=execute,
                              root=WORKFLOW.parents[2], inventory=evidence / "inventory.json",
                              staging=evidence / "stage", target="macosArm64",
                              build="development", sha="local-control", image_control=True)
            exec(compile(ast.Module(body=[self.route_node], type_ignores=[]),
                         str(RUNNER), "exec"), self.scope)
            with self.assertRaisesRegex(RuntimeError, "Native host controls failed"):
                exec(compile(ast.Module(body=[self.guard_node], type_ignores=[]),
                             str(RUNNER), "exec"), self.scope)
            self.assertEqual([label for label, _, _ in calls], [
                "captures/direct_kotlin-command", "captures/memory/direct_kotlin-command",
                "captures/compatibility-command", "captures/memory/compatibility-command"])
            for label, argv, timeout in calls:
                self.assertEqual(timeout, 120)
                self.assertEqual(argv[argv.index("--mode") + 1],
                                 "memory" if "/memory/" in label else "timing")
                self.assertEqual(argv[argv.index("--steps") + 1], "30")
                self.assertEqual(argv[argv.index("--warmup") + 1], "3")
                self.assertEqual(argv[argv.index("--inventory") + 1], evidence / "inventory.json")
                self.assertEqual(argv[argv.index("--publication-root") + 1], evidence / "stage")
            self.assertTrue(all(row["exit_zero"] for row in route["scenarios"].values()))
            self.assertEqual(route["memory_scenarios"]["direct_kotlin"]["status"],
                             "unavailable_or_partial")
            self.assertEqual(route["memory_scenarios"]["compatibility"]["status"],
                             "observed_diagnostic")
            self.assertEqual(route["memory_scenarios"]["compatibility"]["terminal_rss_probe"]
                             ["classification"], "terminal_esrch_exit_confirmed")
            failure = json.loads((evidence / "captures/memory/direct_kotlin-failure.json").read_text())
            self.assertEqual(failure["qualification"], "unpassed")
            self.assertEqual(failure["raw_collection"], "selected_process_exited")
            self.assertEqual(failure["result"]["status"], "unavailable_or_partial")
            self.assertFalse((evidence / "captures/memory/compatibility-failure.json").exists())

    def test_each_host_and_build_selects_separate_bounded_memory_commands(self):
        for target in ("macosArm64", "mingwX64"):
            for build in ("development", "optimized"):
                with self.subTest(target=target, build=build), tempfile.TemporaryDirectory() as directory:
                    evidence = Path(directory)
                    route = {"qualification": "unpassed", "commands": {}, "scenarios": {},
                             "memory_scenarios": {}}
                    calls = []

                    def execute(label, argv, timeout):
                        calls.append((label, argv, timeout))
                        argv[argv.index("--archive") + 1].mkdir(parents=True)
                        route["commands"][label] = {"exit_code": 1, "error": "injected"}
                        return False, None, None

                    self.scope.update(evidence=evidence, route=route, execute=execute,
                                      root=WORKFLOW.parents[2], inventory=evidence / "inventory.json",
                                      staging=evidence / "stage", target=target, build=build,
                                      sha="local-control", image_control=False)
                    exec(compile(ast.Module(body=[self.route_node], type_ignores=[]),
                                 str(RUNNER), "exec"), self.scope)
                    self.assertEqual(len(calls), 4)
                    for label, argv, timeout in calls:
                        self.assertEqual(timeout, 120)
                        self.assertEqual(argv[argv.index("--target") + 1], target)
                        self.assertEqual(argv[argv.index("--build") + 1], build)
                        self.assertEqual(argv[argv.index("--mode") + 1],
                                         "memory" if "/memory/" in label else "timing")
                    self.assertEqual(len(route["memory_scenarios"]), 2)

    def test_gradle_pin_accepts_exact_retained_windows_stdout(self):
        raw = WINDOWS_GRADLE_STDOUT_8FA
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         "6fec462855c154c098721f24957d78e23fc154eaf1550b3b1b1eadbbc0312f16")
        self.assertEqual(len(raw), 608)
        self.assertIn(b"Gradle 9.5.0\r\n", raw)

        def accepts(output):
            scope = {"gradle": output.decode(errors="replace"), "re": re}
            try:
                exec(compile(ast.Module(body=[self.gradle_node], type_ignores=[]),
                             str(RUNNER), "exec"), scope)
            except RuntimeError as error:
                self.assertEqual(str(error), "selected Gradle is not 9.5.0")
                return False
            return True

        self.assertTrue(accepts(raw))
        self.assertTrue(accepts(raw.replace(b"\r\n", b"\n")))
        self.assertTrue(accepts(raw.replace(b"\r\n", b"\r")))
        for bad in (b"Gradle 9.5.0-rc-1\r\n", b"Gradle 9.5.0+vendor\r\n",
                    b"Gradle 9.5.1\r\n", b"Gradle 9.6.0\r\n"):
            self.assertFalse(accepts(raw.replace(b"Gradle 9.5.0\r\n", bad)))
        self.assertFalse(accepts(raw + b"Gradle 9.6.0\r\n"))
