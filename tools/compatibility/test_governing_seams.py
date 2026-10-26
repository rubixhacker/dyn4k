from __future__ import annotations

import copy
import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import governing_seams


ROOT = Path(__file__).resolve().parents[2]
RECEIPT = ROOT / "tools/compatibility/receipts/governing-seams-0681a8cd.json"


class GoverningSeamsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = json.loads((ROOT / "tools/compatibility/declaration-ledger.json").read_text())
        cls.report = json.loads(RECEIPT.read_text())

    def check_without_candidate_jar(self, report):
        source = self.ledger["candidate_source"]
        real_digest = governing_seams.candidate_coverage.digest

        def digest(path):
            if Path(path) == ROOT / source["artifact"]:
                return source["artifact_sha256"]
            return real_digest(path)

        methods = [
            {"owner": owner, "name": name, "descriptor": descriptor,
             "covered_instructions": 1}
            for owner, name, descriptor in
            (identity.split("|", maxsplit=2)
             for identity in self.report["observed_method_ids"])
        ]
        with patch.object(governing_seams.candidate_coverage, "digest", side_effect=digest), \
                patch.object(governing_seams.method_coverage, "analyze", return_value=methods):
            return governing_seams.check(report, self.ledger, ROOT)

    def test_uncovered_behavior_runs_against_both_exact_archives(self):
        self.assertIsNone(governing_seams.check(self.report, self.ledger, ROOT, replay=True))
        self.assertEqual(len(self.report["lanes"]), 8)
        self.assertTrue(all(row["status"] == "passed" for row in self.report["lanes"].values()))
        self.assertIn("org/dyn4j/AVLTree|isSelfBalancing|()Z",
                      self.report["observed_method_ids"])
        self.assertIn("org/dyn4j/geometry/AbstractShape|project|(Lorg/dyn4j/geometry/Vector2;)Lorg/dyn4j/geometry/Interval;",
                      self.report["observed_method_ids"])

    def test_changed_fixture_artifact_or_method_hit_is_rejected(self):
        changed = copy.deepcopy(self.report)
        changed["fixture_sha256"] = "0" * 64
        self.assertIn("fixture", governing_seams.check(changed, self.ledger, ROOT))
        changed = copy.deepcopy(self.report)
        changed["candidate_artifact_sha256"] = "0" * 64
        self.assertIn("candidate", governing_seams.check(changed, self.ledger, ROOT))
        changed = copy.deepcopy(self.report)
        changed["observed_method_ids"].pop()
        self.assertIn("method", self.check_without_candidate_jar(changed))

    def test_java_options_keep_the_inherited_route_for_both_providers(self):
        route = "-Duser.home=/owned/tmp -Djava.io.tmpdir=/owned/tmp"
        agent = "-Dcoverage.agent=enabled"
        with patch.dict(os.environ, {"JAVA_TOOL_OPTIONS": route}):
            baseline_env, baseline_options = governing_seams.lane_environment()
            candidate_env, candidate_options = governing_seams.lane_environment(agent)

        self.assertEqual(baseline_env["JAVA_TOOL_OPTIONS"], route)
        self.assertEqual(baseline_options, route)
        self.assertEqual(candidate_env["JAVA_TOOL_OPTIONS"], route + " " + agent)
        self.assertEqual(candidate_options, route + " " + agent)

    def test_only_one_exact_java_options_banner_is_removed(self):
        options = "-Duser.home=/owned/tmp -Djava.io.tmpdir=/owned/tmp"
        banner = "Picked up JAVA_TOOL_OPTIONS: " + options + "\n"
        self.assertEqual(governing_seams.strip_java_tool_options_banner(
            banner + "unexpected\n", options), "unexpected\n")
        self.assertEqual(governing_seams.strip_java_tool_options_banner(
            banner + banner, options), banner)
        self.assertEqual(governing_seams.strip_java_tool_options_banner(
            "Picked up JAVA_TOOL_OPTIONS: " + options + " extra\n", options),
            "Picked up JAVA_TOOL_OPTIONS: " + options + " extra\n")
        self.assertEqual(governing_seams.strip_java_tool_options_banner(
            "unexpected\n" + banner, options), "unexpected\n" + banner)
        self.assertEqual(governing_seams.strip_java_tool_options_banner(
            "", options), "")
        self.assertEqual(governing_seams.strip_java_tool_options_banner(
            banner, None), banner)
        self.assertEqual(governing_seams.strip_java_tool_options_banner(
            "unexpected\n", options), "unexpected\n")

    def test_pinned_jdks_run_baseline_and_candidate_options(self):
        tmpdir = os.environ["TMPDIR"]
        route = f"-Duser.home={tmpdir} -Djava.io.tmpdir={tmpdir}"
        agent = "-Dcoverage.agent=enabled"
        for major in (8, 21):
            with self.subTest(jdk=major), patch.dict(os.environ, {"JAVA_TOOL_OPTIONS": route}):
                java = Path(self.report["jdk_tools"][str(major)]["java"]["path"])
                baseline_env, baseline_options = governing_seams.lane_environment()
                candidate_env, candidate_options = governing_seams.lane_environment(agent)
                for env, options, candidate in (
                    (baseline_env, baseline_options, False),
                    (candidate_env, candidate_options, True),
                ):
                    run = subprocess.run(
                        [str(java), "-XshowSettings:properties", "-version"],
                        capture_output=True, text=True, timeout=120, env=env,
                    )
                    stderr = governing_seams.strip_java_tool_options_banner(
                        run.stderr, options)
                    self.assertEqual(run.returncode, 0, run.stderr)
                    self.assertNotIn("Picked up JAVA_TOOL_OPTIONS:", stderr)
                    self.assertIn(f"java.io.tmpdir = {tmpdir}", stderr)
                    self.assertIn(f"user.home = {tmpdir}", stderr)
                    self.assertEqual(
                        "coverage.agent = enabled" in stderr, candidate)

    def test_unexpected_lane_stderr_and_changed_java_identity_are_rejected(self):
        changed = copy.deepcopy(self.report)
        changed["lanes"][next(iter(changed["lanes"]))]["stderr"] = "unexpected\n"
        self.assertIn("lane outcome", self.check_without_candidate_jar(changed))

        changed = copy.deepcopy(self.report)
        changed["jdk_tools"]["8"]["java"]["sha256"] = "0" * 64
        self.assertIn("Java tools", self.check_without_candidate_jar(changed))
