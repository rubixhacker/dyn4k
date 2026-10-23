import ast
import os
import re
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/qualification.yml"
SOURCE_CHECKS = WORKFLOW.with_name("qualification-source-checks.yml")
UPSTREAM_REVISION = "058bf6d982a0fb89b54050f929f6ea9dae53b714"


def workflow_jobs(workflow):
    jobs = re.split(r"(?m)^  ([a-z][a-z0-9-]+):\n", workflow.split("jobs:\n", 1)[1])
    return dict(zip(jobs[1::2], jobs[2::2]))


def workflow_event_blocks(workflow):
    match = re.search(r"(?ms)^on:\n(.*?)(?=^jobs:\n)", workflow)
    if match is None:
        raise AssertionError("workflow trigger block is missing")
    source = match.group(1)
    events = list(re.finditer(r"(?m)^  ([a-z][a-z0-9_-]*):\s*$", source))
    return {
        event.group(1): source[event.end():events[index + 1].start() if index + 1 < len(events) else len(source)]
        for index, event in enumerate(events)
    }


def workflow_dispatch_inputs(workflow):
    dispatch = workflow_event_blocks(workflow).get("workflow_dispatch", "")
    inputs = re.search(r"(?m)^    inputs:\n((?:      .*\n|        .*\n|\s*\n)+)", dispatch)
    if inputs is None:
        return {}
    source = inputs.group(1)
    fields = list(re.finditer(r"(?m)^      ([a-z][a-z0-9_-]*):\n", source))
    result = {}
    for index, field in enumerate(fields):
        body = source[field.end():fields[index + 1].start() if index + 1 < len(fields) else len(source)]
        result[field.group(1)] = body
    return result


def _condition_value(node):
    if isinstance(node, ast.Expression):
        return _condition_value(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
        values = [_condition_value(value) for value in node.values]
        return all(values) if isinstance(node.op, ast.And) else any(values)
    raise AssertionError(f"unsupported workflow job condition: {ast.dump(node)}")


def workflow_job_enabled(condition, event, inputs):
    if condition is None:
        return True
    expression = condition.replace("always()", "True")
    expression = re.sub(
        r"github\.event_name\s*(==|!=)\s*'workflow_dispatch'",
        lambda match: str((event == "workflow_dispatch") == (match.group(1) == "==")),
        expression,
    )

    def replace_input(match):
        equal = inputs.get(match.group(1)) is True
        return str(equal if match.group(2) == "==" else not equal)

    expression = re.sub(r"inputs\.([a-z][a-z0-9_-]*)\s*(==|!=)\s*true", replace_input, expression)
    expression = expression.replace("&&", " and ").replace("||", " or ")
    return _condition_value(ast.parse(expression, mode="eval"))


def workflow_jobs_for_event(workflow, event, inputs=None):
    if event not in workflow_event_blocks(workflow):
        return set()
    inputs = inputs or {}
    jobs = workflow_jobs(workflow)
    selected = set()
    for name, job in jobs.items():
        condition = re.search(r"(?m)^    if: (.+)$", job)
        if workflow_job_enabled(condition.group(1) if condition else None, event, inputs):
            selected.add(name)
    return selected


def _yaml_structural_entry(content):
    match = re.fullmatch(
        r'(?P<key>"(?:[^"\\]|\\.)*"|\'(?:[^\']|\'\')*\'|'
        r'[A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(?P<value>.*)',
        content,
    )
    if match is None:
        raise AssertionError("invalid workflow mapping entry")
    key = match.group("key")
    if key.startswith(('"', "'")):
        raise AssertionError("quoted workflow structural keys are not allowed")
    return key, match.group("value")


def _yaml_structural_entries_at_indent(source, indentation):
    entries = []
    seen = set()
    for line in source.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        leading = len(line) - len(line.lstrip(" "))
        if leading != indentation:
            continue
        key, value = _yaml_structural_entry(line[indentation:])
        if key in seen:
            raise AssertionError(f"duplicate workflow structural key: {key}")
        seen.add(key)
        entries.append((key, value))
    return entries


class QualificationWorkflowContractTest(unittest.TestCase):
    def assert_staged_guide_check_contract(self, workflow):
        ubuntu = workflow_jobs(workflow)["staged-jvm-and-linux"]
        step_names = (
            "Stage all target publications",
            "Check staged migration guide example",
            "Upload staged migration guide evidence",
            "Execute staged Kotlin and Java consumer",
        )
        blocks = {}
        for name in step_names:
            match = re.search(rf"(?m)^      - name: {re.escape(name)}\n", ubuntu)
            self.assertIsNotNone(match, name)
            next_step = re.search(r"(?m)^      - (?:name|uses): ", ubuntu[match.end():])
            end = match.end() + next_step.start() if next_step else len(ubuntu)
            blocks[name] = ubuntu[match.start():end]

        stage_at = ubuntu.index("- name: Stage all target publications")
        check_at = ubuntu.index("- name: Check staged migration guide example")
        upload_at = ubuntu.index("- name: Upload staged migration guide evidence")
        consumer_at = ubuntu.index("- name: Execute staged Kotlin and Java consumer")
        self.assertLess(stage_at, check_at)
        self.assertLess(check_at, upload_at)
        self.assertLess(upload_at, consumer_at)

        check = blocks["Check staged migration guide example"]
        self.assertRegex(check, r"(?m)^        run: \|\n")
        script_match = re.search(
            r"(?ms)^        run: \|\n((?:          .*\n)+)", check
        )
        self.assertIsNotNone(script_match)
        script = textwrap.dedent(script_match.group(1))
        normalized = " ".join(script.split())
        self.assertIn("set -euo pipefail", script)
        self.assertIn("unset OLLAMA_API_KEY", script)
        self.assertIn("export PYTHONDONTWRITEBYTECODE=1", script)
        self.assertIn('evidence="$RUNNER_TEMP/staged-guide-example"', script)
        self.assertIn('export TMPDIR="$evidence/tmp"', script)
        self.assertIn('source_commit="$(git rev-parse HEAD)"', script)
        self.assertIn('test "$source_commit" = "$GITHUB_SHA"', script)
        self.assertIn('> "$evidence/source-identity.txt"', script)
        self.assertIn(
            "sha256sum docs/guide/migration.md docs/guide/check_examples.py "
            "docs/guide/check_links.py "
            '> "$evidence/guide-checker-sha256.txt"',
            normalized,
        )
        self.assertIn(
            'io/github/rubixhacker/dyn4k/0.1.0-alpha.1/dyn4k-0.1.0-alpha.1.module',
            script,
        )
        self.assertIn(
            'io/github/rubixhacker/dyn4k-jvm/0.1.0-alpha.1/dyn4k-jvm-0.1.0-alpha.1.module',
            script,
        )
        self.assertIn(
            'io/github/rubixhacker/dyn4k-jvm/0.1.0-alpha.1/dyn4k-jvm-0.1.0-alpha.1.jar',
            script,
        )
        self.assertIn(
            'io/github/rubixhacker/dyn4k-core-jvm/0.1.0-alpha.1/'
            'dyn4k-core-jvm-0.1.0-alpha.1.jar',
            script,
        )
        self.assertIn('> "$evidence/staged-jvm-artifacts-sha256.txt"', script)
        self.assertIn(
            'env -u OLLAMA_API_KEY PYTHONDONTWRITEBYTECODE=1 '
            'python3 -B docs/guide/check_examples.py '
            '"$GITHUB_WORKSPACE/build/staging-repository" --run',
            normalized,
        )
        self.assertIn('> "$evidence/stdout.log" 2> "$evidence/stderr.log"', script)
        self.assertIn('checker_status=$?', script)
        self.assertIn('printf \'%s\\n\' "$checker_status" > "$evidence/exit-code.txt"', script)
        self.assertIn('exit "$checker_status"', script)
        self.assertNotRegex(check, r"(?m)^        (?:if|continue-on-error):")

        upload = blocks["Upload staged migration guide evidence"]
        self.assertIn("        if: always()\n", upload)
        self.assertIn("        uses: actions/upload-artifact@v4\n", upload)
        self.assertIn("name: staged-guide-example-${{ github.sha }}", upload)
        self.assertIn("${{ runner.temp }}/staged-guide-example/", upload)
        self.assertIn("if-no-files-found: warn", upload)

    def test_ubuntu_staged_guide_check_is_auditable_and_fail_closed(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assert_staged_guide_check_contract(workflow)

        checker = re.search(
            r"(?ms)^      - name: Check staged migration guide example\n"
            r".*?(?=^      - (?:name|uses): |\Z)",
            workflow,
        )
        self.assertIsNotNone(checker)
        checker_block = checker.group(0)
        mutations = (
            ("secret inherited by shell", "unset OLLAMA_API_KEY", "true"),
            ("bytecode writes enabled", "export PYTHONDONTWRITEBYTECODE=1",
             "export PYTHONDONTWRITEBYTECODE=0"),
            ("exact checker path changed",
             'python3 -B docs/guide/check_examples.py '
             '"$GITHUB_WORKSPACE/build/staging-repository" --run',
             'python3 -B docs/guide/check_links.py '
             '"$GITHUB_WORKSPACE/build/staging-repository" --run'),
            ("run mode removed", " --run", ""),
            ("stdout not retained", '> "$evidence/stdout.log"', '> /dev/null'),
            ("stderr not retained", '2> "$evidence/stderr.log"', '2> /dev/null'),
            ("actual exit code discarded", "checker_status=$?", "checker_status=0"),
            ("failure propagation removed", 'exit "$checker_status"', "exit 0"),
            ("source commit shortened", "git rev-parse HEAD",
             "git rev-parse --short HEAD"),
            ("guide identity omitted", "docs/guide/migration.md",
             "docs/guide/migration-removed.md"),
            ("staged jar identity omitted", "dyn4k-core-jvm-0.1.0-alpha.1.jar",
             "dyn4k-core-jvm-0.1.0-alpha.1.module"),
        )
        for name, old, new in mutations:
            with self.subTest(mutation=name):
                self.assertEqual(1, checker_block.count(old), name)
                mutated = workflow.replace(
                    checker_block, checker_block.replace(old, new, 1), 1
                )
                with self.assertRaises(AssertionError):
                    self.assert_staged_guide_check_contract(mutated)

        self.assertEqual(1, workflow.count(checker_block), "checker step removed")
        with self.assertRaises(AssertionError):
            self.assert_staged_guide_check_contract(workflow.replace(checker_block, "", 1))

        upload = re.search(
            r"(?ms)^      - name: Upload staged migration guide evidence\n"
            r".*?(?=^      - (?:name|uses): |\Z)",
            workflow,
        )
        self.assertIsNotNone(upload)
        upload_block = upload.group(0)
        upload_mutations = (
            ("evidence upload removed", "      - name: Upload staged migration guide evidence\n",
             "      - name: Upload omitted staged migration guide evidence\n"),
            ("upload no longer runs after failure", "if: always()", "if: success()"),
            ("missing evidence treated as error", "if-no-files-found: warn",
             "if-no-files-found: error"),
        )
        for name, old, new in upload_mutations:
            with self.subTest(mutation=name):
                self.assertEqual(1, upload_block.count(old), name)
                mutated = workflow.replace(
                    upload_block, upload_block.replace(old, new, 1), 1
                )
                with self.assertRaises(AssertionError):
                    self.assert_staged_guide_check_contract(mutated)

        staged_before_check = workflow.replace(checker_block, "", 1)
        stage_at = staged_before_check.index("      - name: Stage all target publications\n")
        staged_before_check = (
            staged_before_check[:stage_at] + checker_block + staged_before_check[stage_at:]
        )
        with self.assertRaises(AssertionError):
            self.assert_staged_guide_check_contract(staged_before_check)

    def assert_source_checks_job_contract(self, source):
        self.assertEqual(
            [("name", "Qualification workflow source checks"),
             ("on", ""), ("permissions", ""), ("jobs", "")],
            _yaml_structural_entries_at_indent(source, 0),
        )
        jobs_block = re.search(r"(?ms)^jobs:\n(.*)\Z", source)
        self.assertIsNotNone(jobs_block)
        jobs_source = jobs_block.group(1)
        self.assertEqual(
            [("workflow-source-contracts", "")],
            _yaml_structural_entries_at_indent(jobs_source, 2),
        )
        job_id_lines = [
            line for line in jobs_source.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
            and len(line) - len(line.lstrip(" ")) == 2
        ]
        self.assertEqual(["  workflow-source-contracts:"], job_id_lines)
        events = workflow_event_blocks(source)
        self.assertEqual(["push", "pull_request"], list(events))
        trigger_block = re.search(r"(?ms)^on:\n(.*?)^permissions:\n", source)
        self.assertIsNotNone(trigger_block)
        self.assertEqual("  push:\n  pull_request:\n\n", trigger_block.group(1))
        self.assertIn("permissions:\n  contents: read\n\njobs:\n", source)
        jobs = workflow_jobs(source)
        self.assertEqual({"workflow-source-contracts"}, set(jobs))
        job = jobs["workflow-source-contracts"]
        self.assertEqual(
            [("runs-on", "ubuntu-26.04"), ("timeout-minutes", "5"), ("steps", "")],
            _yaml_structural_entries_at_indent(job, 4),
        )
        self.assertEqual(
            ["runs-on", "timeout-minutes", "steps"],
            re.findall(r"(?m)^    ([a-z][a-z0-9-]*):(?:\s+.*)?$", job),
        )
        self.assertIn("    runs-on: ubuntu-26.04\n", job)
        self.assertIn("    timeout-minutes: 5\n", job)
        checkout = re.search(
            r"(?m)^      - uses: actions/checkout@v4\n((?: {8,}.*\n)+)", job
        )
        self.assertIsNotNone(checkout)
        self.assertEqual("        with:\n          fetch-depth: 0\n", checkout.group(1))
        self.assertNotRegex(job, r"(?m)^        (?:if|continue-on-error):")

        step_matches = list(re.finditer(r"(?m)^      - (.+)$", job))
        step_contract = []
        for index, match in enumerate(step_matches):
            end = step_matches[index + 1].start() if index + 1 < len(step_matches) else len(job)
            block = job[match.start():end]
            first_key, first_value = _yaml_structural_entry(match.group(1))
            continuation = _yaml_structural_entries_at_indent(block, 8)
            keys = [first_key, *(key for key, _ in continuation)]
            if len(keys) != len(set(keys)):
                raise AssertionError("duplicate workflow step structural key")
            if first_key == "uses":
                self.assertEqual(["uses", "with"], keys)
                if first_value == "actions/checkout@v4":
                    self.assertEqual([("fetch-depth", "0")],
                                     _yaml_structural_entries_at_indent(block, 10))
                else:
                    self.assertEqual("actions/setup-java@v4", first_value)
                    self.assertEqual([("distribution", "temurin"), ("java-version", "|")],
                                     _yaml_structural_entries_at_indent(block, 10))
                    self.assertIn("          java-version: |\n            8\n            21\n", block)
            else:
                self.assertEqual(["name", "run"], keys)
            multiline = re.search(r"(?ms)^        run: \|\n((?: {10}.*\n)+)", block)
            if multiline is not None:
                script = textwrap.dedent(multiline.group(1))
                command = " ".join(re.sub(r"\\\s*\n", " ", script).split())
            else:
                inline = re.search(r"(?m)^        run: (.+)$", block)
                command = inline.group(1) if inline is not None else None
            step_contract.append((match.group(1), command))

        self.assertEqual(
            [
                ("uses: actions/checkout@v4", None),
                ("uses: actions/setup-java@v4", None),
                ("name: Reject hosted macOS routes",
                 "python3 -B tools/qualification/guard_hosted_runners.py"),
                ("name: Test qualification workflow contracts",
                 "python3 -B -m unittest tools.compatibility.test_qualification_workflow"),
                ("name: Test hosted runner guard",
                 "PYTHONPATH=tools/qualification python3 -B -m unittest test_guard_hosted_runners"),
                ("name: Verify pinned GNU MPFR runtime",
                 "env -u OLLAMA_API_KEY PYTHONPATH=tools/numerical/portable python3 -B -c "
                 "'from rotation_oracle import _MPFR; mpfr = _MPFR(); "
                 "print(\"GNU MPFR\", mpfr.version)'"),
                ("name: Test source-only numerical regressions",
                 "env -u OLLAMA_API_KEY -u DYN4K_JDI_JDK_HOME "
                 "-u DYN4K_JDI_RETAINED_JAR -u DYN4K_WHEEL_ARCHIVE "
                 "-u DYN4K_WHEEL_ORIGIN -u DYN4K_GEOMETRY_BASELINE "
                 "-u DYN4K_PROSPECTIVE_CURRENT_MANIFEST "
                 "-u DYN4K_PROSPECTIVE_HISTORICAL_MANIFEST "
                 "-u DYN4K_BOOLEAN_REFERENCE_ORIGIN "
                 "-u DYN4K_BOOLEAN_JDI_TOY "
                 "-u BOOLEAN_JDI_TOY_ROOT "
                 "-u DYN4K_PULLEY_BASELINE_JAR "
                 "-u DYN4K_PULLEY_LOADED_CODE_ROOT "
                 "-u DYN4K_PULLEY_CANDIDATE_JAR "
                 "-u DYN4K_PULLEY_REAL_CLASSPATH "
                 "-u DYN4K_PULLEY_CACHE_ROOT "
                 "-u ANDROID_SDK_ROOT "
                 "DYN4K_TEST_JDK8_HOME=\"$JAVA_HOME_8_X64\" "
                 "PYTHONPATH=tools/numerical/portable:"
                 "tools/numerical/portable/boolean_rotation_jdi "
                 "python3 -B -m unittest -v "
                 "test_actual_arithmetic test_actual_capture_receipt "
                 "test_capture_actual test_rotation_oracle test_rotation_marker "
                 "test_prospective_compare test_witness test_source_guard "
                 "test_jdi_bridge test_pulley_jdi_v1 test_pulley_jdi_v2 "
                 "test_pulley_jdi_classpath_v2 test_external_rotation_binding "
                 "test_numeric_producer test_run"),
                ("name: Test bounded JDI wait on JDK 21",
                 "test -n \"${JAVA_HOME_21_X64:-}\" "
                 "test -x \"$JAVA_HOME_21_X64/bin/java\" "
                 "test -x \"$JAVA_HOME_21_X64/bin/javac\" "
                 "test -n \"${JAVA_HOME_8_X64:-}\" "
                 "test -x \"$JAVA_HOME_8_X64/bin/java\" "
                 "test -x \"$JAVA_HOME_8_X64/bin/javac\" "
                 "\"$JAVA_HOME_8_X64/bin/java\" -version 2>&1 | "
                 "grep -Eq 'version \"1\\.8\\.' "
                 "\"$JAVA_HOME_8_X64/bin/javac\" -version 2>&1 | "
                 "grep -Eq '^javac 1\\.8\\.' "
                 "\"$JAVA_HOME_21_X64/bin/java\" -version 2>&1 | "
                 "grep -Eq 'version \"21\\.' "
                 "command -v strace "
                 "env -u OLLAMA_API_KEY "
                 "DYN4K_JDI_JDK_HOME=\"$JAVA_HOME_21_X64\" "
                 "PYTHONDONTWRITEBYTECODE=1 "
                 "PYTHONPATH=tools/numerical/portable/boolean_rotation_jdi "
                 "python3 -B -m unittest -v test_jdi_wait"),
                ("name: Test numeric class witness on JDK 21",
                 "set -euo pipefail unset OLLAMA_API_KEY "
                 "evidence=\"$RUNNER_TEMP/numeric-class-witness\" "
                 "mkdir -p \"$evidence/tmp\" "
                 "export TMPDIR=\"$evidence/tmp\" "
                 "export JAVA_TOOL_OPTIONS=\"-XX:-UsePerfData -Djava.io.tmpdir=$TMPDIR\" "
                 "test -n \"${JAVA_HOME_21_X64:-}\" "
                 "test -d \"$JAVA_HOME_21_X64\" "
                 "test -x \"$JAVA_HOME_21_X64/bin/java\" "
                 "test -x \"$JAVA_HOME_21_X64/bin/javac\" "
                 "\"$JAVA_HOME_21_X64/bin/java\" -version 2>&1 | "
                 "grep -Eq 'version \"21\\.' "
                 "\"$JAVA_HOME_21_X64/bin/javac\" -version 2>&1 | "
                 "grep -Eq '^javac 21\\.' "
                 "command -v strace env -u OLLAMA_API_KEY "
                 "DYN4K_CLASS_WITNESS_JDK_HOME=\"$JAVA_HOME_21_X64\" "
                 "DYN4K_TEST_JDK8_HOME=\"$JAVA_HOME_8_X64\" "
                 "PYTHONDONTWRITEBYTECODE=1 "
                 "PYTHONPATH=tools/numerical/portable "
                 "python3 -B -m unittest -v test_numeric_class_witness"),
                ("name: Test qualification manifest and publication contracts",
                 "env -u OLLAMA_API_KEY PYTHONDONTWRITEBYTECODE=1 "
                 "PYTHONPATH=tools/qualification python3 -B -m unittest -v "
                 "test_full_suite_manifest test_publication"),
                ("name: Test independent qualification gate seams",
                 "env -u OLLAMA_API_KEY PYTHONDONTWRITEBYTECODE=1 "
                 "PYTHONPATH=tools/qualification python3 -B -m unittest -v "
                 "test_independent_gates"),
                ("name: Test portable qualification source modules",
                 "env -u OLLAMA_API_KEY -u DYN4K_UPSTREAM_SOURCE "
                 "-u DYN4K_RETAINED_FULL_JVM_ARCHIVE "
                 "-u DYN4K_JVM_MODE_PUBLICATION "
                 "-u DYN4K_RETAINED_BROWSER_PRODUCER "
                 "-u DYN4K_RETAINED_BROWSER_ARCHIVES "
                 "PYTHONDONTWRITEBYTECODE=1 "
                 "PYTHONPATH=tools/qualification python3 -B -m unittest -v "
                 "test_collection test_compiler_modes test_full_corpus "
                 "test_independent_adapter"),
                ("name: Check migration guide links and claims",
                 "env -u OLLAMA_API_KEY PYTHONDONTWRITEBYTECODE=1 "
                 "python3 -B docs/guide/check_links.py"),
                ("name: Test migration guide checks",
                 "env -u OLLAMA_API_KEY PYTHONDONTWRITEBYTECODE=1 "
                 "PYTHONPATH=docs/guide python3 -B -m unittest -v test_checks"),
            ],
            step_contract,
        )

    def test_source_mpfr_preflight_is_required_and_pinned(self):
        source = SOURCE_CHECKS.read_text(encoding="utf-8")
        self.assert_source_checks_job_contract(source)
        preflight = (
            "      - name: Verify pinned GNU MPFR runtime\n"
            "        run: env -u OLLAMA_API_KEY "
            "PYTHONPATH=tools/numerical/portable python3 -B -c "
            "'from rotation_oracle import _MPFR; mpfr = _MPFR(); "
            "print(\"GNU MPFR\", mpfr.version)'\n"
        )
        mutations = (
            ("preflight removed", preflight, ""),
            ("version enforcement skipped", "mpfr = _MPFR()", "mpfr = None"),
            ("loaded version not printed", "print(\"GNU MPFR\", mpfr.version)",
             "print(\"GNU MPFR\", _MPFR.MPFR_VERSION)"),
        )
        for name, old, new in mutations:
            with self.subTest(mutation=name):
                self.assertEqual(1, source.count(old), name)
                with self.assertRaises(AssertionError):
                    self.assert_source_checks_job_contract(source.replace(old, new, 1))

    def test_bounded_jdi_step_fails_when_required_jdk21_is_missing(self):
        source = SOURCE_CHECKS.read_text(encoding="utf-8")
        self.assert_source_checks_job_contract(source)
        step = re.search(
            r"(?m)^      - name: Test bounded JDI wait on JDK 21\n"
            r"        run: \|\n((?:          [^\n]*\n)+)", source,
        )
        self.assertIsNotNone(step)
        environment = os.environ.copy()
        environment.pop("OLLAMA_API_KEY", None)
        environment.pop("JAVA_HOME_21_X64", None)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run(
            ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c",
             textwrap.dedent(step.group(1))],
            cwd=WORKFLOW.parents[2], env=environment, capture_output=True, text=True,
            timeout=5,
        )
        self.assertNotEqual(0, result.returncode)

    def test_source_contract_rejects_yaml_key_execution_overrides(self):
        source = SOURCE_CHECKS.read_text(encoding="utf-8")
        preflight_run = (
            "        run: env -u OLLAMA_API_KEY "
            "PYTHONPATH=tools/numerical/portable python3 -B -c "
            "'from rotation_oracle import _MPFR; mpfr = _MPFR(); "
            "print(\"GNU MPFR\", mpfr.version)'\n"
        )
        hosted_guard_run = "        run: python3 -B tools/qualification/guard_hosted_runners.py\n"
        timeout = "    timeout-minutes: 5\n"
        mutations = (
            ("quoted job failure suppression", timeout,
             timeout + '    "continue-on-error": true\n'),
            ("quoted job permission override", timeout,
             timeout + '    "permissions": write-all\n'),
            ("quoted job steps override", timeout,
             timeout + '    "steps": []\n'),
            ("duplicate job timeout", timeout,
             timeout + "    timeout-minutes: 1\n"),
            ("quoted preflight skip", preflight_run,
             preflight_run + '        "if": false\n'),
            ("quoted hosted guard skip", hosted_guard_run,
             hosted_guard_run + '        "if": false\n'),
            ("unknown shell override", preflight_run,
             preflight_run + "        shell: bash\n"),
            ("unknown step execution key", preflight_run,
             preflight_run + "        continue-on-error: true\n"),
            ("duplicate step command", preflight_run,
             preflight_run + "        run: echo skipped\n"),
        )
        for name, old, new in mutations:
            with self.subTest(mutation=name):
                self.assertEqual(1, source.count(old), name)
                with self.assertRaises(AssertionError):
                    self.assert_source_checks_job_contract(source.replace(old, new, 1))

    def test_source_contract_rejects_root_execution_overrides(self):
        source = SOURCE_CHECKS.read_text(encoding="utf-8")
        name_line = "name: Qualification workflow source checks\n"
        mutations = (
            ("root environment override", name_line,
             name_line + "env:\n  BASH_ENV: /dev/null\n"),
            ("root shell defaults override", name_line,
             name_line + "defaults:\n  run:\n    shell: pwsh\n"),
            ("quoted unknown root key", name_line,
             name_line + '"env":\n  BASH_ENV: /dev/null\n'),
            ("spaced unknown root key", name_line,
             name_line + "env :\n  BASH_ENV: /dev/null\n"),
            ("duplicate unknown root key", name_line,
             name_line + "env:\n  BASH_ENV: /dev/null\n"
             "env:\n  CI: false\n"),
        )
        for name, old, new in mutations:
            with self.subTest(mutation=name):
                self.assertEqual(1, source.count(old), name)
                with self.assertRaises(AssertionError):
                    self.assert_source_checks_job_contract(source.replace(old, new, 1))

    def test_source_contract_rejects_job_id_overrides(self):
        source = SOURCE_CHECKS.read_text(encoding="utf-8")
        jobs_marker = "jobs:\n"
        extra_job = (
            "  {job_id}:\n"
            "    runs-on: ubuntu-26.04\n"
            "    steps:\n"
            "      - run: echo extra\n"
        )
        original_job = workflow_jobs(source)["workflow-source-contracts"]
        duplicate_job = (
            source.rstrip("\n") + "\n  workflow-source-contracts:\n" + original_job
        )
        mutations = (
            ("quoted extra job id", source.replace(
                jobs_marker, jobs_marker + extra_job.format(job_id='"extra"'), 1)),
            ("unknown extra job id", source.replace(
                jobs_marker, jobs_marker + extra_job.format(job_id="extra"), 1)),
            ("spaced job id", source.replace(
                jobs_marker, jobs_marker + extra_job.format(job_id="extra "), 1)),
            ("duplicate job id", duplicate_job),
        )
        for name, mutated in mutations:
            with self.subTest(mutation=name):
                self.assertNotEqual(source, mutated, name)
                with self.assertRaises(AssertionError):
                    self.assert_source_checks_job_contract(mutated)

    def test_source_job_contract_rejects_failure_suppression_and_body_changes(self):
        source = SOURCE_CHECKS.read_text(encoding="utf-8")
        mutations = (
            ("job failure suppression", "    timeout-minutes: 5\n",
             "    timeout-minutes: 5\n    continue-on-error: true\n"),
            ("runner guard body", "run: python3 -B tools/qualification/guard_hosted_runners.py",
             "run: python3 -B tools/qualification/guard_hosted_runners.py && true"),
            ("workflow contract body",
             "run: python3 -B -m unittest tools.compatibility.test_qualification_workflow",
             "run: python3 -B -m unittest tools.compatibility.test_qualification_workflow -q"),
            ("hosted runner test body",
             "run: PYTHONPATH=tools/qualification python3 -B -m unittest test_guard_hosted_runners",
             "run: PYTHONPATH=tools/qualification python3 -B -m unittest test_guard_hosted_runners -q"),
            ("runner label", "runs-on: ubuntu-26.04", "runs-on: ubuntu-latest"),
            ("history depth", "fetch-depth: 0", "fetch-depth: 1"),
            ("archive unset", "-u DYN4K_WHEEL_ORIGIN ", ""),
            ("JDI JDK home unset omitted", "-u DYN4K_JDI_JDK_HOME ", ""),
            ("JDI retained JAR unset omitted", "-u DYN4K_JDI_RETAINED_JAR ", ""),
            ("numerical module", "test_rotation_oracle", "test_rotation_oracle_changed"),
            ("JDI bridge module omitted", "test_jdi_bridge", "test_jdi_bridge_changed"),
            ("capture regression omitted", "              test_capture_actual \\\n", ""),
            ("Pulley v1 regression omitted", "test_pulley_jdi_v1", "test_pulley_jdi_v1_changed"),
            ("Pulley v2 regression omitted", "test_pulley_jdi_v2", "test_pulley_jdi_v2_changed"),
            ("Pulley classpath regression omitted", "test_pulley_jdi_classpath_v2", "test_pulley_jdi_classpath_v2_changed"),
            ("external rotation binding omitted", "test_external_rotation_binding", "test_external_rotation_binding_changed"),
            ("bounded JDI module omitted", "test_jdi_wait", "test_jdi_bridge"),
            ("required JDK executable omitted", "test -x \"$JAVA_HOME_21_X64/bin/javac\"", "true"),
            ("required JDK version omitted", "grep -Eq 'version \"21\\.'", "cat"),
            ("required strace omitted", "command -v strace", "true"),
            ("bounded JDI failure suppressed", "python3 -B -m unittest -v test_jdi_wait", "python3 -B -m unittest -v test_jdi_wait || true"),
            ("JDI reference origin unset omitted", "-u DYN4K_BOOLEAN_REFERENCE_ORIGIN ", ""),
            ("Pulley baseline input unset omitted", "-u DYN4K_PULLEY_BASELINE_JAR ", ""),
            ("Pulley loaded-code input unset omitted", "-u DYN4K_PULLEY_LOADED_CODE_ROOT ", ""),
            ("Pulley candidate input unset omitted", "-u DYN4K_PULLEY_CANDIDATE_JAR ", ""),
            ("Pulley classpath input unset omitted", "-u DYN4K_PULLEY_REAL_CLASSPATH ", ""),
            ("Pulley cache input unset omitted", "-u DYN4K_PULLEY_CACHE_ROOT ", ""),
            ("added installation step",
             "      - name: Test source-only numerical regressions\n",
             "      - name: Install a dependency\n"
             "        run: pip install example\n"
             "      - name: Test source-only numerical regressions\n"),
            ("push trigger filter", "  push:\n", "  push:\n    branches: [main]\n"),
        )
        bounded_jdi = re.search(
            r"(?ms)^      - name: Test bounded JDI wait on JDK 21\n"
            r".*?(?=^      - (?:name|uses): |\Z)", source,
        )
        self.assertIsNotNone(bounded_jdi)
        bounded_controls = {
            "required JDK executable omitted",
            "required JDK version omitted",
            "required strace omitted",
            "bounded JDI failure suppressed",
        }
        for name, old, new in mutations:
            with self.subTest(mutation=name):
                target = bounded_jdi.group(0) if name in bounded_controls else source
                self.assertEqual(1, target.count(old), name)
                mutated = source.replace(target, target.replace(old, new, 1), 1)
                with self.assertRaises(AssertionError):
                    self.assert_source_checks_job_contract(mutated)

    def test_capture_actual_source_regression_is_required(self):
        source = SOURCE_CHECKS.read_text(encoding="utf-8")
        self.assertIn("test_capture_actual", source)
        self.assert_source_checks_job_contract(source)
        without_capture = source.replace("              test_capture_actual \\\n", "", 1)
        self.assertNotEqual(source, without_capture)
        with self.assertRaises(AssertionError):
            self.assert_source_checks_job_contract(without_capture)

    def test_added_source_ci_gates_are_required_with_deletion_controls(self):
        source = SOURCE_CHECKS.read_text(encoding="utf-8")
        self.assert_source_checks_job_contract(source)
        mutations = (
            ("39-test manifest and publication command",
             "test_full_suite_manifest test_publication", "test_full_suite_manifest"),
            ("independent-gates suite", "-m unittest -v test_independent_gates",
             "-m unittest -v"),
            ("guide link and claim check", "docs/guide/check_links.py",
             "docs/guide/check_examples.py"),
            ("five-test guide check suite", "-m unittest -v test_checks",
             "-m unittest -v"),
        )
        for name, old, new in mutations:
            with self.subTest(mutation=name):
                self.assertEqual(1, source.count(old), name)
                mutated = source.replace(old, new, 1)
                with self.assertRaises(AssertionError):
                    self.assert_source_checks_job_contract(mutated)

    def test_portable_qualification_source_suite_rejects_noop_and_missing_modules(self):
        source = SOURCE_CHECKS.read_text(encoding="utf-8")
        self.assert_source_checks_job_contract(source)
        suite = re.search(
            r"(?m)^      - name: Test portable qualification source modules\n"
            r"        run: (.+)\n", source,
        ).group(0)
        self.assertEqual(1, source.count(suite))
        mutations = (
            ("suite command replaced by no-op", "python3 -B -m unittest -v",
             "true # python3 -B -m unittest -v"),
            ("one module omitted", "test_collection test_compiler_modes test_full_corpus "
             "test_independent_adapter", "test_collection test_compiler_modes "
             "test_full_corpus"),
            ("secret not removed", "env -u OLLAMA_API_KEY PYTHONDONTWRITEBYTECODE=1 "
             "PYTHONPATH=tools/qualification", "PYTHONDONTWRITEBYTECODE=1 "
             "PYTHONPATH=tools/qualification"),
            ("bytecode writes enabled", "PYTHONDONTWRITEBYTECODE=1 "
             "PYTHONPATH=tools/qualification", "PYTHONDONTWRITEBYTECODE=0 "
             "PYTHONPATH=tools/qualification"),
            ("qualification import path omitted", "PYTHONPATH=tools/qualification "
             "python3 -B", "python3 -B"),
        )
        for name, old, new in mutations:
            with self.subTest(mutation=name):
                self.assertIn(old, source)
                with self.assertRaises(AssertionError):
                    self.assert_source_checks_job_contract(source.replace(old, new, 1))

    def test_push_and_pull_request_do_not_schedule_qualification_jobs(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(["workflow_dispatch"], list(workflow_event_blocks(workflow)))
        commit_message = "Fix qualification workflow dispatch guard"
        self.assertNotIn("[skip ci]", commit_message)
        for event in ("push", "pull_request"):
            with self.subTest(event=event):
                self.assertEqual(set(), workflow_jobs_for_event(workflow, event))

    def test_manual_dispatch_retains_full_and_bounded_routes(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        inputs = workflow_dispatch_inputs(workflow)
        self.assertEqual(
            {"windows_diagnostics", "cross_run_only", "cross_run_source_index"},
            set(inputs),
        )
        self.assertIn("type: boolean", inputs["windows_diagnostics"])
        self.assertIn("default: false", inputs["windows_diagnostics"])
        self.assertIn("type: boolean", inputs["cross_run_only"])
        self.assertIn("default: false", inputs["cross_run_only"])
        self.assertIn("type: string", inputs["cross_run_source_index"])

        full = workflow_jobs_for_event(
            workflow, "workflow_dispatch",
            {"windows_diagnostics": False, "cross_run_only": False},
        )
        self.assertEqual(set(workflow_jobs(workflow)), full)

        windows = workflow_jobs_for_event(
            workflow, "workflow_dispatch",
            {"windows_diagnostics": True, "cross_run_only": False},
        )
        self.assertEqual(
            {"hosted-runner-guard", "hosted-publications", "hosted-native"}, windows
        )

        cross_run = workflow_jobs_for_event(
            workflow, "workflow_dispatch",
            {"windows_diagnostics": False, "cross_run_only": True,
             "cross_run_source_index": "source-index-v1.json"},
        )
        self.assertEqual({"hosted-runner-guard", "central-qualification-collection"},
                         cross_run)
        self.assertIn("${{ inputs.cross_run_source_index }}",
                      workflow_jobs(workflow)["central-qualification-collection"])

    def test_automatic_source_checks_are_lightweight_and_mac_is_dispatch_only(self):
        source = SOURCE_CHECKS.read_text(encoding="utf-8")
        self.assert_source_checks_job_contract(source)
        jobs = workflow_jobs(source)
        self.assertEqual({"workflow-source-contracts"}, set(jobs))
        for event in ("push", "pull_request"):
            self.assertEqual({"workflow-source-contracts"},
                             workflow_jobs_for_event(source, event), event)
        self.assertIn("runs-on: ubuntu-26.04", jobs["workflow-source-contracts"])
        self.assertIn("timeout-minutes: 5", jobs["workflow-source-contracts"])
        self.assertIn("tools/qualification/guard_hosted_runners.py", jobs["workflow-source-contracts"])
        self.assertIn("tools.compatibility.test_qualification_workflow",
                      jobs["workflow-source-contracts"])
        self.assertIn("test_guard_hosted_runners", jobs["workflow-source-contracts"])
        self.assertNotIn("mac-mini", jobs["workflow-source-contracts"])

        workflows = sorted(WORKFLOW.parent.glob("*.yml")) + sorted(WORKFLOW.parent.glob("*.yaml"))
        mac_routes = []
        for path in workflows:
            source_text = path.read_text(encoding="utf-8")
            for job_name, job in workflow_jobs(source_text).items():
                if re.search(r"(?m)^    runs-on: mac-mini\s*$", job):
                    mac_routes.append((path.name, job_name))
                    self.assertEqual(["workflow_dispatch"],
                                     list(workflow_event_blocks(source_text)), path.name)
        self.assertEqual([("qualification.yml", "hosted-mac")], mac_routes)

    def test_source_checks_run_archive_isolated_numerical_regressions(self):
        source = SOURCE_CHECKS.read_text(encoding="utf-8")
        job = workflow_jobs(source)["workflow-source-contracts"]
        step_names = re.findall(r"(?m)^      - (?:name: .+|uses: .+)$", job)
        self.assertEqual(
            ["      - uses: actions/checkout@v4",
             "      - uses: actions/setup-java@v4",
             "      - name: Reject hosted macOS routes",
             "      - name: Test qualification workflow contracts",
             "      - name: Test hosted runner guard",
             "      - name: Verify pinned GNU MPFR runtime",
             "      - name: Test source-only numerical regressions",
             "      - name: Test bounded JDI wait on JDK 21",
             "      - name: Test numeric class witness on JDK 21",
             "      - name: Test qualification manifest and publication contracts",
             "      - name: Test independent qualification gate seams",
             "      - name: Test portable qualification source modules",
             "      - name: Check migration guide links and claims",
             "      - name: Test migration guide checks"],
            step_names,
        )
        step = re.search(
            r"(?ms)^      - name: Test source-only numerical regressions\n"
            r"        run: \|\n((?:          [^\n]*\n)+)",
            job,
        )
        self.assertIsNotNone(step)
        script = textwrap.dedent(step.group(1))
        command = " ".join(re.sub(r"\\\s*\n", " ", script).split())
        self.assertEqual(
            "env -u OLLAMA_API_KEY -u DYN4K_JDI_JDK_HOME "
            "-u DYN4K_JDI_RETAINED_JAR -u DYN4K_WHEEL_ARCHIVE "
            "-u DYN4K_WHEEL_ORIGIN -u DYN4K_GEOMETRY_BASELINE "
            "-u DYN4K_PROSPECTIVE_CURRENT_MANIFEST "
            "-u DYN4K_PROSPECTIVE_HISTORICAL_MANIFEST "
            "-u DYN4K_BOOLEAN_REFERENCE_ORIGIN "
            "-u DYN4K_BOOLEAN_JDI_TOY "
            "-u BOOLEAN_JDI_TOY_ROOT "
            "-u DYN4K_PULLEY_BASELINE_JAR "
            "-u DYN4K_PULLEY_LOADED_CODE_ROOT "
            "-u DYN4K_PULLEY_CANDIDATE_JAR "
            "-u DYN4K_PULLEY_REAL_CLASSPATH "
            "-u DYN4K_PULLEY_CACHE_ROOT "
            "-u ANDROID_SDK_ROOT "
            "DYN4K_TEST_JDK8_HOME=\"$JAVA_HOME_8_X64\" "
            "PYTHONPATH=tools/numerical/portable:"
            "tools/numerical/portable/boolean_rotation_jdi "
            "python3 -B -m unittest -v "
            "test_actual_arithmetic test_actual_capture_receipt "
            "test_capture_actual test_rotation_oracle test_rotation_marker "
            "test_prospective_compare test_witness test_source_guard "
            "test_jdi_bridge test_pulley_jdi_v1 test_pulley_jdi_v2 "
            "test_pulley_jdi_classpath_v2 test_external_rotation_binding "
            "test_numeric_producer test_run",
            command,
        )

        observer = re.search(
            r"(?ms)^      - name: Test numeric class witness on JDK 21\n"
            r"        run: \|\n((?:          [^\n]*\n)+)", job,
        )
        self.assertIsNotNone(observer)
        script = textwrap.dedent(observer.group(1))
        command = " ".join(re.sub(r"\\\s*\n", " ", script).split())
        self.assertEqual(
            "set -euo pipefail unset OLLAMA_API_KEY "
            "evidence=\"$RUNNER_TEMP/numeric-class-witness\" "
            "mkdir -p \"$evidence/tmp\" "
            "export TMPDIR=\"$evidence/tmp\" "
            "export JAVA_TOOL_OPTIONS=\"-XX:-UsePerfData -Djava.io.tmpdir=$TMPDIR\" "
            "test -n \"${JAVA_HOME_21_X64:-}\" test -d \"$JAVA_HOME_21_X64\" "
            "test -x \"$JAVA_HOME_21_X64/bin/java\" "
            "test -x \"$JAVA_HOME_21_X64/bin/javac\" "
            "\"$JAVA_HOME_21_X64/bin/java\" -version 2>&1 | "
            "grep -Eq 'version \"21\\.' "
            "\"$JAVA_HOME_21_X64/bin/javac\" -version 2>&1 | "
            "grep -Eq '^javac 21\\.' command -v strace "
            "env -u OLLAMA_API_KEY "
            "DYN4K_CLASS_WITNESS_JDK_HOME=\"$JAVA_HOME_21_X64\" "
            "DYN4K_TEST_JDK8_HOME=\"$JAVA_HOME_8_X64\" "
            "PYTHONDONTWRITEBYTECODE=1 "
            "PYTHONPATH=tools/numerical/portable "
            "python3 -B -m unittest -v test_numeric_class_witness",
            command,
        )

    def test_source_contract_rejects_observer_step_mutations(self):
        source = SOURCE_CHECKS.read_text(encoding="utf-8")
        self.assert_source_checks_job_contract(source)
        mutations = (
            ("observer step removed", "      - name: Test numeric class witness on JDK 21\n", ""),
            ("observer command replaced by no-op", "python3 -B -m unittest -v test_numeric_class_witness",
             "true # python3 -B -m unittest -v test_numeric_class_witness"),
            ("observer command commented", "python3 -B -m unittest -v test_numeric_class_witness",
             "# python3 -B -m unittest -v test_numeric_class_witness"),
            ("observer command disabled by condition", "          test -n \"${JAVA_HOME_21_X64:-}\"\n",
             "          if false; then test -n \"${JAVA_HOME_21_X64:-}\"; fi\n"),
            ("observer failure suppressed", "python3 -B -m unittest -v test_numeric_class_witness",
             "python3 -B -m unittest -v test_numeric_class_witness || true"),
            ("explicit JDK input omitted", "DYN4K_CLASS_WITNESS_JDK_HOME=\"$JAVA_HOME_21_X64\" ", ""),
            ("HOME reset to scratch", "          export TMPDIR=\"$evidence/tmp\"\n",
             "          export TMPDIR=\"$evidence/tmp\"\n"
             "          export HOME=\"$evidence/home\"\n"),
            ("scratch home directory created", "          mkdir -p \"$evidence/tmp\"\n",
             "          mkdir -p \"$evidence/home\" \"$evidence/tmp\"\n"),
            ("Java temp directory override omitted",
             "          export JAVA_TOOL_OPTIONS=\"-XX:-UsePerfData -Djava.io.tmpdir=$TMPDIR\"\n",
             "          export JAVA_TOOL_OPTIONS=\"-XX:-UsePerfData\"\n"),
            ("configured JDK directory check omitted", "          test -d \"$JAVA_HOME_21_X64\"\n", "          true\n"),
            ("Java major check omitted", "grep -Eq 'version \"21\\.'", "cat"),
            ("javac major check omitted", "grep -Eq '^javac 21\\.'", "cat"),
            ("producer module omitted",
             "              test_external_rotation_binding \\\n              test_numeric_producer \\\n              test_run\n",
             "              test_external_rotation_binding\n"),
        )
        observer = re.search(
            r"(?ms)^      - name: Test numeric class witness on JDK 21\n"
            r".*?(?=^      - (?:name|uses): |\Z)", source,
        )
        self.assertIsNotNone(observer)
        numerical = re.search(
            r"(?ms)^      - name: Test source-only numerical regressions\n"
            r".*?(?=^      - (?:name|uses): |\Z)", source,
        )
        self.assertIsNotNone(numerical)
        for name, old, new in mutations:
            with self.subTest(mutation=name):
                if name == "observer step removed":
                    target = source
                elif name == "producer module omitted":
                    target = numerical.group(0)
                else:
                    target = observer.group(0)
                self.assertEqual(1, target.count(old), name)
                replacement = target.replace(old, new, 1)
                with self.assertRaises(AssertionError):
                    self.assert_source_checks_job_contract(
                        source.replace(target, replacement, 1))

    def test_numeric_class_witness_configuration_rejects_explicit_bad_jdk(self):
        module_path = Path(__file__).resolve().parents[1] / "numerical/portable"
        with tempfile.TemporaryDirectory() as temporary:
            invalid_jdk = Path(temporary) / "owned-missing-jdk"
            for supplied in (str(invalid_jdk), ""):
                with self.subTest(supplied=supplied):
                    environment = os.environ.copy()
                    environment.pop("OLLAMA_API_KEY", None)
                    environment.pop("ANDROID_SDK_ROOT", None)
                    environment["PYTHONDONTWRITEBYTECODE"] = "1"
                    environment["PYTHONPATH"] = str(module_path)
                    environment["DYN4K_CLASS_WITNESS_JDK_HOME"] = supplied
                    result = subprocess.run(
                        ["python3", "-B", "-c", "import test_numeric_class_witness"],
                        cwd=WORKFLOW.parents[2], env=environment,
                        capture_output=True, text=True, check=False, timeout=5,
                    )
                    self.assertNotEqual(0, result.returncode)
                    self.assertIn("DYN4K_CLASS_WITNESS_JDK_HOME", result.stderr)

    def test_mac_mini_uses_verified_preinstalled_python(self):
        mac_mini = workflow_jobs(WORKFLOW.read_text())["hosted-mac"]
        self.assertIn("    runs-on: mac-mini\n", mac_mini)
        self.assertIn("          - target: macosArm64\n", mac_mini)
        self.assertIn("          - target: iosSimulatorArm64\n", mac_mini)
        self.assertIn("          - target: tvosSimulatorArm64\n", mac_mini)
        self.assertIn("          - target: watchosSimulatorArm64\n", mac_mini)
        self.assertIn("          - target: iosX64\n", mac_mini)
        self.assertIn("          - target: jsSafari\n", mac_mini)
        self.assertNotIn("actions/setup-python@v5", mac_mini)
        self.assertIn("Use pre-installed Python 3.12.15", mac_mini)
        step = re.search(
            r"(?m)^      - name: Use pre-installed Python 3\.12\.15\n"
            r"        run: \|\n((?:          .*\n)+)",
            mac_mini,
        )
        self.assertIsNotNone(step)
        script = textwrap.dedent(step.group(1))
        pinned_dir = "/Users/stew/.cache/dyn4k-codex/tools/python-3.12.15/python/bin"
        self.assertEqual(1, script.count(pinned_dir))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for case, version, optimize in (
                ("absent", None, False),
                ("wrong-optimized", "3.12.14", True),
                ("correct", "3.12.15", False),
            ):
                with self.subTest(case=case):
                    python_dir = root / case / "bin"
                    github_path = root / f"{case}-github-path"
                    github_path.write_text("", encoding="utf-8")
                    if version is not None:
                        python_dir.mkdir(parents=True)
                        python = python_dir / "python"
                        python.write_text(
                            "#!/bin/sh\n"
                            "case \"${1-}\" in\n"
                            "  -c)\n"
                            "    if [ -n \"${PYTHONOPTIMIZE:-}\" ] || "
                            "[ \"${FAKE_VERSION:-}\" = 3.12.15 ]; then exit 0; fi\n"
                            "    exit 1 ;;\n"
                            "  --version) printf 'Python %s\\n' \"$FAKE_VERSION\" ;;\n"
                            "  *) exit 2 ;;\n"
                            "esac\n",
                            encoding="utf-8",
                        )
                        python.chmod(0o755)

                    case_script = script.replace(pinned_dir, str(python_dir))
                    self.assertEqual(1, case_script.count(str(python_dir)))
                    environment = {
                        "PATH": "/usr/bin:/bin",
                        "GITHUB_PATH": str(github_path),
                        "FAKE_VERSION": version or "",
                    }
                    if optimize:
                        environment["PYTHONOPTIMIZE"] = "1"
                    else:
                        environment.pop("PYTHONOPTIMIZE", None)
                    result = subprocess.run(
                        ["/bin/bash", "-e", "-c", case_script],
                        env=environment,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if case == "absent":
                        self.assertNotEqual(0, result.returncode)
                        self.assertIn("Required pre-installed Python is missing", result.stderr)
                        self.assertEqual("", github_path.read_text(encoding="utf-8"))
                    elif case == "wrong-optimized":
                        self.assertNotEqual(0, result.returncode)
                        self.assertIn("Required Python 3.12.15", result.stderr)
                        self.assertIn("Python 3.12.14", result.stderr)
                        self.assertEqual("", github_path.read_text(encoding="utf-8"))
                    else:
                        self.assertEqual(0, result.returncode, result.stderr)
                        self.assertEqual(
                            f"{python_dir}\n", github_path.read_text(encoding="utf-8")
                        )
                        next_step = subprocess.run(
                            ["/bin/bash", "-e", "-c", "command -v python"],
                            env={"PATH": f"{python_dir}:/usr/bin:/bin"},
                            capture_output=True,
                            text=True,
                            check=False,
                        )
                        self.assertEqual(0, next_step.returncode, next_step.stderr)
                        self.assertEqual(str(python), next_step.stdout.strip())

    def test_native_monitor_probe_runs_on_windows_publication_runner(self):
        publications = workflow_jobs(WORKFLOW.read_text())["hosted-publications"]
        self.assertIn("    runs-on: windows-2025\n", publications)
        self.assertIn("          - host: windows\n            targets: --target mingwX64\n", publications)
        self.assertNotIn("macos-26", publications)
        step_name = "      - name: Probe native performance monitor\n"
        self.assertEqual(1, publications.count(step_name))
        setup = publications.index("      - uses: actions/setup-python@v5")
        probe = publications.index(step_name)
        harness = publications.index("      - name: Harness regression tests")
        self.assertLess(setup, probe)
        self.assertLess(probe, harness)
        step = publications[probe:publications.index("      - uses:", probe)]
        self.assertEqual(
            step_name + "        run: PYTHONPATH=tools/performance python -B -m unittest "
            "tools.performance.test_stress_monitor.StressMonitorTest."
            "test_native_hosted_probe_when_available -v\n", step)

    def test_windows_dispatch_keeps_only_windows_hosted_jobs(self):
        workflow = WORKFLOW.read_text()
        self.assertIn("      windows_diagnostics:\n", workflow)
        self.assertIn("        type: boolean\n", workflow)
        self.assertIn("        default: false\n", workflow)
        jobs = workflow_jobs(workflow)
        guard = "if: github.event_name != 'workflow_dispatch' || (inputs.windows_diagnostics != true && inputs.cross_run_only != true)"
        self.assertIn(guard, jobs["staged-jvm-and-linux"])
        mac = jobs["hosted-mac"]
        self.assertIn(guard, mac)
        self.assertEqual(
            ["macosArm64", "iosSimulatorArm64", "tvosSimulatorArm64",
             "watchosSimulatorArm64", "iosX64", "jsSafari"],
            re.findall(r"(?m)^          - target: ([A-Za-z0-9]+)$", mac),
        )
        self.assertNotIn("safari-browser", jobs)
        self.assertIn("hosted-runner-guard", jobs)
        for name, entry in (("hosted-publications", "host"), ("hosted-native", "target")):
            with self.subTest(job=name):
                job = jobs[name]
                self.assertIn("if: github.event_name != 'workflow_dispatch' || inputs.cross_run_only != true", job)
                self.assertIn("needs: hosted-runner-guard", job)
                self.assertIn("    runs-on: windows-2025\n", job)
                self.assertIn(f"          - {entry}: " +
                              ("windows" if entry == "host" else "mingwX64") + "\n", job)
                self.assertNotIn("macos-26", job)

    def test_windows_failure_collectors_retain_logs_and_failed_status(self):
        jobs = workflow_jobs(WORKFLOW.read_text())
        publications = jobs["hosted-publications"]
        native = jobs["hosted-native"]
        self.assertIn('printf \'%s\\n\' "$result" > "$diagnostics/harness.exit-code"', publications)
        self.assertIn('exit "$result"', publications)
        for job, kind, selector in (
                (publications, "publication logs", "matrix.host == 'windows'"),
                (native, "native failure evidence", "matrix.target == 'mingwX64'")):
            with self.subTest(kind=kind):
                collect = job.index("- name: Collect Windows " + kind)
                upload = job.index("- name: Upload Windows " + kind)
                self.assertLess(collect, upload)
                block = job[collect:upload]
                self.assertIn("if: always() && " + selector, block)
                self.assertIn("set -euo pipefail", block)
                self.assertIn('errors="$diagnostics/logs/collection-errors.txt"', block)
                self.assertIn('cp --parents -- "$relative"', block)
                self.assertIn('cat "$errors" >&2\n            exit 1', block)
                self.assertIn("if: always() && " + selector, job[upload:])
                self.assertIn("windows-failure-raw-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}-${{ github.job }}-", job[upload:])
                self.assertIn("if-no-files-found: warn", job[upload:])
        self.assertIn('cygpath -u "${GRADLE_USER_HOME:-$HOME/.gradle}"', publications)
        self.assertIn('cygpath -u "$RUNNER_TEMP/full-hosted-mingwX64"', native)
        self.assertIn("-path '*/build/test-results/*/TEST-*.xml'", native)

    def test_combined_workflow_keeps_unique_steps_and_pre_staging_corpus(self):
        jobs = workflow_jobs(WORKFLOW.read_text())
        for name, job in jobs.items():
            with self.subTest(job=name):
                names = re.findall(r"(?m)^      - name: (.+)$", job)
                ids = re.findall(r"(?m)^        id: (.+)$", job)
                self.assertEqual(len(names), len(set(names)))
                self.assertEqual(len(ids), len(set(ids)))
        ubuntu = jobs["staged-jvm-and-linux"]
        corpus = ubuntu[ubuntu.index("- name: Run complete source-derived common corpus"):
                        ubuntu.index("- name: Verify complete common corpus")]
        tasks = re.findall(r":dyn4k(?:-core)?:[A-Za-z0-9]+Test\b", corpus)
        self.assertEqual(12, len(tasks))
        self.assertEqual(12, len(set(tasks)))
        self.assertLess(ubuntu.index("- name: Verify complete common corpus"),
                        ubuntu.index("- name: Stage all target publications"))
        self.assertLess(ubuntu.index("- name: Stage all target publications"),
                        ubuntu.index("- name: Run full staged Java compatibility closure"))

    def test_full_qualification_workflow_is_dispatch_only(self):
        events = workflow_event_blocks(WORKFLOW.read_text())
        self.assertEqual(["workflow_dispatch"], list(events))

    def test_extracted_common_archive_is_verified_before_upload(self):
        ubuntu = workflow_jobs(WORKFLOW.read_text())["staged-jvm-and-linux"]
        packaged = ubuntu.index("tools/qualification/full_corpus.py package-archive")
        extracted = ubuntu.index("full-common-transport-check")
        verified = ubuntu.index("tools/qualification/full_corpus.py verify-archive")
        uploaded = ubuntu.index("- name: Upload complete common raw evidence")
        self.assertLess(packaged, extracted)
        self.assertLess(extracted, verified)
        self.assertLess(verified, uploaded)
        self.assertIn('--candidate-sha "$GITHUB_SHA"', ubuntu[verified:uploaded])

    def test_every_qualification_suite_job_provisions_declared_pinned_upstream(self):
        invoking = {}
        for workflow in sorted(WORKFLOW.parent.glob("*.yml")) + sorted(
                WORKFLOW.parent.glob("*.yaml")):
            for name, job in workflow_jobs(workflow.read_text()).items():
                if re.search(r"python(?:3)? -m unittest discover -s tools/qualification\b",
                             job):
                    invoking[f"{workflow.name}:{name}"] = job
        self.assertTrue(invoking)
        for name, job in invoking.items():
            with self.subTest(job=name):
                if name.startswith("windows-qualification-harness.yml:"):
                    self.assertIn("$env:DYN4K_UPSTREAM_SOURCE = $upstreamSource", job)
                    self.assertIn(
                        "'fetch', '--depth=1', 'origin', '058bf6d982a0fb89b54050f929f6ea9dae53b714'",
                        job)
                    self.assertIn(
                        "$upstreamSha -ne '058bf6d982a0fb89b54050f929f6ea9dae53b714'",
                        job)
                    continue
                suite = re.search(
                    r"python(?:3)? -m unittest discover -s tools/qualification\b", job)
                before_suite = job[:suite.start()]
                self.assertRegex(before_suite, r"DYN4K_UPSTREAM_SOURCE: \S+")
                self.assertIn('git init "$DYN4K_UPSTREAM_SOURCE"', before_suite)
                self.assertIn("remote add origin https://github.com/dyn4j/dyn4j.git",
                              before_suite)
                self.assertIn(f"fetch --depth=1 origin {UPSTREAM_REVISION}", before_suite)
                self.assertIn('checkout --detach FETCH_HEAD', before_suite)
                self.assertIn(
                    f'test "$(git -C "$DYN4K_UPSTREAM_SOURCE" rev-parse HEAD)" = {UPSTREAM_REVISION}',
                    before_suite)
                self.assertIn('test "$(git rev-parse HEAD)" = "$GITHUB_SHA"',
                              before_suite)
                if not re.search(r"(?m)^    env:\n      DYN4K_UPSTREAM_SOURCE:",
                                 before_suite):
                    self.assertIn(
                        "printf 'DYN4K_UPSTREAM_SOURCE=%s\\n' "
                        '"$DYN4K_UPSTREAM_SOURCE" >> "$GITHUB_ENV"',
                        before_suite)
                if "windows-" in job or "macos-" in job:
                    self.assertRegex(job, r"defaults:\n\s+run:\n\s+shell: bash")
                    self.assertIn(
                        "DYN4K_UPSTREAM_SOURCE: ${{ runner.temp }}/dyn4j-source",
                        before_suite)

    def test_ubuntu_job_runs_complete_corpus_and_compatibility_gates(self):
        workflow = WORKFLOW.read_text()
        ubuntu = workflow.split("  staged-jvm-and-linux:\n", 1)[1].split(
            "  hosted-publications:\n", 1)[0]
        self.assertRegex(ubuntu, r"java-version: \|\n\s+8\n\s+21")
        self.assertIn("DYN4K_UPSTREAM_SOURCE:", ubuntu)
        self.assertIn("PYTHONDONTWRITEBYTECODE: '1'", ubuntu)
        self.assertIn("058bf6d982a0fb89b54050f929f6ea9dae53b714", ubuntu)
        self.assertIn("git rev-parse HEAD", ubuntu)
        self.assertIn("tools/qualification/full_corpus.py run", ubuntu)
        self.assertIn("tools/qualification/full_corpus.py verify", ubuntu)
        self.assertIn("tools/compatibility/full_ci.py", ubuntu)
        self.assertIn("tools/compatibility/full_ci.py seal", ubuntu)
        self.assertIn("tools/compatibility/full_ci.py verify", ubuntu)
        self.assertIn("--candidate-sha \"$GITHUB_SHA\"", ubuntu)
        self.assertIn("--jdk8 \"$JAVA_HOME_8_X64\"", ubuntu)
        self.assertIn("--jdk21 \"$JAVA_HOME_21_X64\"", ubuntu)
        self.assertRegex(ubuntu, r"name: full-ci-\$\{\{ github.sha \}\}")
        self.assertRegex(ubuntu, r"name: full-common-\$\{\{ github.sha \}\}")
        for name in ("Run complete source-derived common corpus",
                     "Verify complete common corpus",
                     "Archive and check complete common raw evidence",
                     "Upload complete common raw evidence",
                     "Run full staged Java compatibility closure",
                     "Seal full Java compatibility archive",
                     "Verify full Java compatibility archive",
                     "Archive and check full Java compatibility raw evidence",
                     "Upload full Java compatibility raw archive"):
            with self.subTest(step=name):
                self.assertRegex(ubuntu, re.escape("- name: " + name) + r"\n\s+if: always\(\)")
        self.assertEqual(3, ubuntu.count("sha256sum -c"))
        self.assertLess(ubuntu.index("- name: Audit staged artifact contract"),
                        ubuntu.index("- name: Verify Java subclass dispatch"))
        dispatch = ubuntu[ubuntu.index("- name: Verify Java subclass dispatch"):
                          ubuntu.index("- name: Upload Java subclass dispatch evidence")]
        self.assertIn("tools/qualification/subclass_audit.py", dispatch)
        self.assertIn('for java_home in "$JAVA_HOME_8_X64" "$JAVA_HOME_21_X64"; do', dispatch)
        self.assertIn('--output "$RUNNER_TEMP/subclass-dispatch/$jdk"', dispatch)
        self.assertIn('--candidate-commit "$GITHUB_SHA" --audit "$RUNNER_TEMP/artifact-audit.json"', dispatch)
        self.assertIn('--repository "$GITHUB_WORKSPACE"', dispatch)
        self.assertIn('--jdk-major "$jdk"', dispatch)
        self.assertIn('tools/qualification/subclass_audit.py --verify', dispatch)
        self.assertIn("204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e", dispatch)
        self.assertIn("if: always()", ubuntu[ubuntu.index("- name: Upload Java subclass dispatch evidence"):])
        self.assertEqual(2, ubuntu.count("tar -tzf"))
        self.assertIn("diff -qr \"$RUNNER_TEMP/full-common\"", ubuntu)
        self.assertIn("--output \"$RUNNER_TEMP/full-ci-transport-check/full-ci\"", ubuntu)
        self.assertLess(ubuntu.index("- name: Upload complete common raw evidence"),
                        ubuntu.index("- name: Stage all target publications"))
        self.assertLess(ubuntu.index("- name: Stage all target publications"),
                        ubuntu.index("- name: Run full staged Java compatibility closure"))


if __name__ == "__main__":
    unittest.main()
