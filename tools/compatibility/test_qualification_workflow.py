import re
import unittest
from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/qualification.yml"
UPSTREAM_REVISION = "058bf6d982a0fb89b54050f929f6ea9dae53b714"


def workflow_jobs(workflow):
    jobs = re.split(r"(?m)^  ([a-z][a-z0-9-]+):\n", workflow.split("jobs:\n", 1)[1])
    return dict(zip(jobs[1::2], jobs[2::2]))


class QualificationWorkflowContractTest(unittest.TestCase):
    def test_main_push_keeps_diagnostic_branch_routes(self):
        workflow = WORKFLOW.read_text()
        push = workflow.split("  push:\n    branches:\n", 1)[1].split("  pull_request:", 1)[0]
        for branch in ("main", "codex/port-qualification-harness", "codex/dyn4k-port",
                       "codex/port-publication-assembly"):
            with self.subTest(branch=branch):
                self.assertIn(f"      - {branch}\n", push)

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
        self.assertEqual(2, ubuntu.count("sha256sum -c"))
        self.assertEqual(2, ubuntu.count("tar -tzf"))
        self.assertIn("diff -qr \"$RUNNER_TEMP/full-common\"", ubuntu)
        self.assertIn("--output \"$RUNNER_TEMP/full-ci-transport-check/full-ci\"", ubuntu)
        self.assertLess(ubuntu.index("- name: Upload complete common raw evidence"),
                        ubuntu.index("- name: Stage all target publications"))
        self.assertLess(ubuntu.index("- name: Stage all target publications"),
                        ubuntu.index("- name: Run full staged Java compatibility closure"))


if __name__ == "__main__":
    unittest.main()
