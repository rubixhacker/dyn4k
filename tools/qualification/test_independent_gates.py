import builtins
import json
import hashlib
import gzip
import contextlib
import importlib
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import types
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

import independent_gates
import qualify

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "migration"))
import journeys
sys.path.pop(0)


ROOT = Path(__file__).resolve().parents[2]
BASE = "e35e3f1ec357b1c44b6d2b742e0d88bc2e91f767"
MANIFEST_REV = "2f5eb2d40df2d8549bb45f137e9f6b2c258e6ada"
MANIFEST_BLOB = "87276196a29af12296f9d14d156dbff1f9a774eb"
OLD_MANIFEST_REV = "e8b72ff86ca367dffa26b6bbab38f25e7aa0abc3"
MANIFEST_SHA256 = "9aa2f50dd3c38129a70f4ed042f2b7ae5a90d4234def40d70520aad13f36b3fc"
OLD_MANIFEST_SHA256 = "dfafb566e19962dacafd0f18e6ff5374b2c30b0c10e1a0c522169c28cd5b0e94"
LANE = "jvm:Java:minimum:no-optimize"
CAPTURE_REPLAY_NAMES = (
    "capture_actual", "actual_arithmetic", "actual_capture_receipt", "actual_trace",
    "actual_output_v6",
    "rotation_oracle", "boolean_rotation_jdi",
    "boolean_rotation_jdi.jdi_bridge", "boolean_rotation_jdi.source_guard",
    "boolean_rotation_jdi.witness", "boolean_rotation_jdi.loaded_code")


def checkout_matches_commit(paths):
    return all((ROOT / path).read_bytes() == subprocess.check_output(
        ["git", "--no-replace-objects", "show", f"HEAD:{path}"], cwd=ROOT)
        for path in paths)


def changed_capture_actual():
    portable = ROOT / "tools/numerical/portable"
    spec = importlib.util.spec_from_file_location("capture_actual", portable / "capture_actual.py")
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {}), mock.patch.object(
            sys, "path", [str(portable), *sys.path]):
        for name in ("actual_arithmetic", "actual_capture_receipt", "actual_trace",
                     "rotation_oracle", "boolean_rotation_jdi",
                     "boolean_rotation_jdi.jdi_bridge", "boolean_rotation_jdi.source_guard",
                     "boolean_rotation_jdi.witness", "boolean_rotation_jdi.loaded_code"):
            sys.modules.pop(name, None)
        spec.loader.exec_module(module)

    def changed(*unused, **options):
        raise AssertionError("cached capture helper was used")

    module.CaptureBudget = changed
    module.run_bounded_process = changed
    return module


def changed_ambient_comparator(directory):
    ambient = directory / "ambient"
    ambient.mkdir()
    marker = directory / "ambient-compare-executed"
    checked = (ROOT / "tools/numerical/compare.py").read_bytes()
    changed = checked + (f"\nfrom pathlib import Path\n"
                         f"Path({str(marker)!r}).write_text('executed')\n").encode()
    (ambient / "compare.py").write_bytes(changed)
    assert hashlib.sha256(changed).hexdigest() != independent_gates.APPROVED_POLICY[
        "tools/numerical/compare.py"]
    return ambient, marker


def reviewed_arithmetic_at(revision):
    approved = {
        "6040b40265975b9091db430d79269cb5ea3d9868":
            independent_gates.APPROVED_P2_HISTORICAL_PRODUCERS["actual_arithmetic.py"],
        "ffdc8ba9b600732e6927e38e7d3da43a519994a4":
            independent_gates.APPROVED_P2_CLASS_LOAD_PRODUCERS["actual_arithmetic.py"],
    }
    if revision not in approved:
        raise AssertionError("historical P2 revision is not approved for this replay")
    bound = {"actual_arithmetic.py": approved[revision],
             "rotation_oracle.py": independent_gates.APPROVED_P2_PRODUCERS[
                 "rotation_oracle.py"]}
    sources = {}
    for name in ("rotation_oracle.py", "actual_arithmetic.py"):
        path = f"tools/numerical/portable/{name}"
        raw = subprocess.check_output(["git", "--no-replace-objects", "show",
                                       f"{revision}:{path}"], cwd=ROOT)
        if hashlib.sha256(raw).hexdigest() != bound[name]:
            raise AssertionError(f"reviewed historical P2 producer differs: {path}")
        sources[name] = raw
    rotation = types.ModuleType("rotation_oracle")
    rotation.__file__ = str(ROOT / "tools/numerical/portable/rotation_oracle.py")
    exec(compile(sources["rotation_oracle.py"], "rotation_oracle.py", "exec"),
         rotation.__dict__)
    arithmetic = types.ModuleType("actual_arithmetic")
    arithmetic.__file__ = str(ROOT / "tools/numerical/portable/actual_arithmetic.py")
    with mock.patch.dict(sys.modules, {"rotation_oracle": rotation}):
        exec(compile(sources["actual_arithmetic.py"], "actual_arithmetic.py", "exec"),
             arithmetic.__dict__)
    return arithmetic


class IndependentGateSeamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(subprocess.check_output(
            ["git", "show", f"{MANIFEST_REV}:tools/qualification/full-suite-manifest.json"],
            cwd=ROOT))

    def test_approved_manifest_pin_is_reviewed_world_revision(self):
        blob = subprocess.check_output(
            ["git", "rev-parse", f"{MANIFEST_REV}:tools/qualification/full-suite-manifest.json"],
            cwd=ROOT, text=True).strip()
        self.assertEqual(MANIFEST_BLOB, blob)
        self.assertEqual(MANIFEST_REV, independent_gates.APPROVED_MANIFEST_REVISION)
        self.assertEqual(MANIFEST_SHA256, independent_gates.APPROVED_MANIFEST_SHA256)
        self.assertEqual(MANIFEST_SHA256, independent_gates.digest(self.manifest))
        self.assertEqual(self.manifest, independent_gates.load_approved_manifest(ROOT))

    def test_public_cli_rejects_old_altered_and_wrong_revision_manifests(self):
        old = json.loads(subprocess.check_output(
            ["git", "show", f"{OLD_MANIFEST_REV}:tools/qualification/full-suite-manifest.json"],
            cwd=ROOT))
        self.assertEqual(OLD_MANIFEST_SHA256, independent_gates.digest(old))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            current = json.loads((ROOT / "tools/qualification/full-suite-manifest.json").read_text())
            self.assertEqual(self.manifest, current)
            five_ids = {case["id"] for case in self.manifest["cases"]} - {
                case["id"] for case in old["cases"]}
            self.assertEqual(5, len(five_ids))
            missing_five = {**self.manifest, "cases": [
                case for case in self.manifest["cases"] if case["id"] not in five_ids]}
            extra_five = {**self.manifest, "cases": [
                *self.manifest["cases"], *[
                    {**self.manifest["cases"][-1], "id": f"extra-case-{index}"}
                    for index in range(5)]]}
            for label, manifest in (("old-2521", old),
                                    ("altered", {**self.manifest, "id": "altered"}),
                                    ("missing-five", missing_five), ("extra-five", extra_five),
                                    ("wrong-inventory", {**self.manifest,
                                                         "cases": self.manifest["cases"][:-1]})):
                path.write_text(json.dumps(manifest))
                with self.subTest(manifest=label), self.assertRaisesRegex(
                        ValueError, "manifest differs from independently approved complete suite"):
                    independent_gates.main(["--candidate-sha", BASE, "--lane", LANE,
                                            "--manifest", str(path)])
        with mock.patch.object(independent_gates, "APPROVED_MANIFEST_REVISION",
                               OLD_MANIFEST_REV):
            with self.assertRaisesRegex(ValueError, "approved complete-suite manifest changed"):
                independent_gates.main(["--candidate-sha", BASE, "--lane", LANE])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(1, independent_gates.main(
                ["--candidate-sha", BASE, "--lane", LANE]))
        result = json.loads(output.getvalue())
        self.assertEqual(MANIFEST_SHA256, result["manifest_sha256"])
        self.assertEqual("NOT_RUN", result["status"])

    def test_reviewed_manifest_selection_and_source_bindings(self):
        self.assertEqual(21, len(self.manifest["targets"]))
        self.assertEqual(28, len({(lane["target"], lane["runtime"])
                                  for lane in self.manifest["lanes"].values()}))
        self.assertEqual(112, len(self.manifest["lanes"]))
        self.assertEqual(2526, len(self.manifest["cases"]))
        corpus = json.loads((ROOT / "tools/qualification/full-common-corpus.json").read_text())
        self.assertEqual(2385, len(corpus["original_mappings"]))
        self.assertEqual(202, len(corpus["source_files"]))
        self.assertEqual(2523, sum(case["scope"] == "portable" for case in self.manifest["cases"]))
        self.assertEqual(3, sum(case["scope"] == "jvm-only" for case in self.manifest["cases"]))
        historical = json.loads(subprocess.check_output(
            ["git", "show", "6c6faed0499d0ddc2fee4ae910e4f58d044130e0:tools/qualification/full-common-corpus.json"],
            cwd=ROOT))
        self.assertEqual(199, len(historical["source_files"]))
        self.assertEqual(2385, len(historical["original_mappings"]))

    def test_missing_archives_keep_every_declared_route_unpassed(self):
        result = independent_gates.evaluate(
            self.manifest, BASE, LANE, {}, ROOT)
        expected = set(self.manifest["lanes"][LANE]["required_gates"])
        expected.update(self.manifest["global_gates"])
        self.assertEqual(expected, set(result["gates"]))
        self.assertEqual({"NOT_RUN"}, {gate["status"] for gate in result["gates"].values()})
        self.assertEqual("NOT_RUN", result["status"])
        self.assertEqual(64, len(result["result_sha256"]))

    def test_reported_pass_needs_independent_archive_pin(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "receipt.json").write_text(json.dumps({"status": "PASSED"}))
            result = independent_gates.evaluate(
                self.manifest, BASE, LANE, {"duplicate-provider": root}, ROOT)
            self.assertEqual("FAILED", result["gates"]["duplicate-provider"]["status"])
            self.assertIn("independent archive", result["gates"]["duplicate-provider"]["reason"])

    def test_every_approved_lane_has_a_consumer_contract(self):
        self.assertEqual(112, len(self.manifest["lanes"]))
        for lane_id, lane in self.manifest["lanes"].items():
            with self.subTest(lane=lane_id):
                contract = independent_gates.consumer_contract(self.manifest, lane_id)
                self.assertEqual(lane["target"], contract["target"])
                self.assertTrue(contract["cases"])

    def test_approved_comparator_accepts_reviewed_blob_and_rejects_stale_pin(self):
        current = "4a6b4646683389aca643551b5672ca94d2f1e6dd49adad1c4684472b2b97348d"
        historical_digest = "6e9abe839c74ac9be1e8507e4a693b0414e70063f878481c94ab136c7ec89f4f"
        path = "tools/numerical/compare.py"
        self.assertEqual(current, independent_gates.APPROVED_POLICY[path])
        self.assertEqual(historical_digest, independent_gates.HISTORICAL_COMPARATOR_SHA256)
        self.assertEqual(current, hashlib.sha256(subprocess.check_output(
            ["git", "show", f"HEAD:{path}"], cwd=ROOT)).hexdigest())
        self.assertEqual(current, hashlib.sha256((ROOT / path).read_bytes()).hexdigest())
        reviewed_revisions = (
            "f6fefba4f55267f40cc1e3a5844bd67f1e163139",
            "243dc33145f263b5a2918e25c588442b5df75430",
            "e7e22cde3094095e1ac2e4aee988a97ff2053ae8")
        approved_revisions = (
            "f0349a0d29f91879fc52286899f39e042c8523f6",
            "168fbfcdabd68cfb9317310958d6be7f52b38f05")
        self.assertEqual(approved_revisions, independent_gates.APPROVED_COMPARATOR_REVISIONS)
        required_revisions = (*reviewed_revisions, *approved_revisions,
                              "cd21a4bd7d6731a096597f97966db9e02b9de448",
                              "6f993d9f96ac3e5a722ed82eb85bc0b2394d98cd")
        if any(subprocess.run(["git", "cat-file", "-e", f"{revision}:{path}"],
                              cwd=ROOT, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode
               for revision in required_revisions):
            candidate = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                                cwd=ROOT, text=True).strip()
            try:
                binding = independent_gates._policy_binding(ROOT, candidate)
            except ValueError as error:
                self.assertIn("revision ancestry is unavailable", str(error))
            else:
                self.assertEqual(current, binding[path])
            with mock.patch.dict(independent_gates.APPROVED_POLICY,
                                 {path: historical_digest}):
                with self.assertRaisesRegex(ValueError, "approved policy/checker blob differs"):
                    independent_gates._policy_binding(ROOT, candidate)
            return
        for revision in (*reviewed_revisions,
                         "f0349a0d29f91879fc52286899f39e042c8523f6",
                         "168fbfcdabd68cfb9317310958d6be7f52b38f05"):
            self.assertEqual(current, hashlib.sha256(subprocess.check_output(
                ["git", "show", f"{revision}:{path}"], cwd=ROOT)).hexdigest())
        historical = "cd21a4bd7d6731a096597f97966db9e02b9de448"
        self.assertEqual(historical_digest, hashlib.sha256(subprocess.check_output(
            ["git", "show", f"{historical}:{path}"], cwd=ROOT)).hexdigest())
        current_source = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                                 cwd=ROOT, text=True).strip()
        if checkout_matches_commit(independent_gates.APPROVED_POLICY):
            self.assertEqual(historical_digest,
                             independent_gates._policy_binding(ROOT, historical)[path])
            self.assertEqual(current, independent_gates._policy_binding(
                ROOT, "f0349a0d29f91879fc52286899f39e042c8523f6")[path])
            self.assertEqual(current, independent_gates._policy_binding(
                ROOT, "168fbfcdabd68cfb9317310958d6be7f52b38f05")[path])
            self.assertEqual(current, independent_gates._policy_binding(ROOT, current_source)[path])
            unapproved = "6f993d9f96ac3e5a722ed82eb85bc0b2394d98cd"
            self.assertEqual(current, hashlib.sha256(subprocess.check_output(
                ["git", "show", f"{unapproved}:{path}"], cwd=ROOT)).hexdigest())
            with self.assertRaisesRegex(ValueError, "approved policy/checker blob differs"):
                independent_gates._policy_binding(ROOT, unapproved)
        else:
            with self.assertRaisesRegex(ValueError, "approved policy/checker blob differs"):
                independent_gates._policy_binding(ROOT, current_source)
        for path, approved in independent_gates.APPROVED_POLICY.items():
            committed = subprocess.check_output(["git", "show", f"{BASE}:{path}"],
                                                cwd=ROOT)
            if path == "tools/numerical/fixtures.json":
                self.assertEqual(independent_gates.HISTORICAL_FIXTURE_SHA256,
                                 hashlib.sha256(committed).hexdigest())
            elif path != "tools/numerical/compare.py":
                self.assertEqual(approved, hashlib.sha256(committed).hexdigest())
        with self.assertRaisesRegex(ValueError,
                                    "approved policy/checker blob differs: tools/numerical/compare.py"):
            independent_gates._policy_binding(ROOT, BASE)
        with mock.patch.dict(independent_gates.APPROVED_POLICY,
                             {"tools/numerical/compare.py":
                              historical_digest}):
            with self.assertRaisesRegex(ValueError, "approved policy/checker blob differs"):
                independent_gates._policy_binding(ROOT, current_source)
        with mock.patch.dict(independent_gates.APPROVED_POLICY,
                             {"tools/numerical/fixtures.json": "0" * 64}):
            with self.assertRaisesRegex(ValueError, "approved policy/checker blob differs"):
                independent_gates._policy_binding(ROOT, current_source)

    def test_producer_scope_requires_independently_pinned_raw_manifest(self):
        scope = {"candidate_sha": BASE, "target": "jvm", "runtime": "Java",
                 "runtime_identity": "reviewed JVM runner",
                 "artifact_hashes": {"dyn4k-core": "a" * 64}}
        with self.assertRaisesRegex(ValueError, "producer manifest"):
            independent_gates._producer_scope("migration-journeys", BASE,
                                              {"migration-journeys": scope})

    def test_historical_numerical_source_adapter_matches_producer_git_archive(self):
        candidate = "cd21a4bd7d6731a096597f97966db9e02b9de448"
        current = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                          cwd=ROOT, text=True).strip()

        def archive_sha(autocrlf, revision):
            return hashlib.sha256(subprocess.check_output(
                ["git", "-c", f"core.autocrlf={autocrlf}", "--no-replace-objects",
                 "-C", str(ROOT), "archive", "--format=tar", revision])).hexdigest()

        self.assertEqual("7958113412c14be8e106706a77871eba4dc8c4e1335c38fd01c7b9e18d26e12d",
                         archive_sha("false", candidate))
        self.assertEqual("371f767bb7e78c0203102f491ac1c7577177b7b7c91887030413af2e72466a05",
                         archive_sha("true", candidate))
        for revision in (candidate, current):
            canonical = archive_sha("false", revision)
            for autocrlf in ("false", "true"):
                with self.subTest(revision=revision, autocrlf=autocrlf), mock.patch.dict(
                        os.environ, {"GIT_CONFIG_COUNT": "1",
                                     "GIT_CONFIG_KEY_0": "core.autocrlf",
                                     "GIT_CONFIG_VALUE_0": autocrlf}):
                    self.assertEqual(canonical,
                                     independent_gates.verified_numerical_source_sha256(
                                         ROOT, revision))

    def test_canonical_archive_does_not_accept_converted_working_checker(self):
        candidate = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                            cwd=ROOT, text=True).strip()
        checker = ROOT / "tools/numerical/compare.py"
        original_read_bytes = Path.read_bytes

        def converted(path):
            raw = original_read_bytes(path)
            return raw.replace(b"\n", b"\r\n") if path == checker else raw

        with mock.patch.object(Path, "read_bytes", converted):
            with self.assertRaisesRegex(ValueError,
                                        "approved policy/checker blob differs: tools/numerical/compare.py"):
                independent_gates._policy_binding(ROOT, candidate)

    def test_shallow_history_cannot_select_historical_comparator_policy(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            source.mkdir()
            def git(repository, *args):
                return subprocess.run(["git", "-C", str(repository), *args],
                                      check=True, capture_output=True, text=True).stdout.strip()

            git(source, "init", "-q")
            tracked = source / "history.txt"
            tracked.write_text("approved\n")
            git(source, "add", "history.txt")
            git(source, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                "commit", "-qm", "approved")
            approved = git(source, "rev-parse", "HEAD")
            git(source, "tag", "approved")
            tracked.write_text("candidate\n")
            git(source, "add", "history.txt")
            git(source, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                "commit", "-qm", "candidate")
            candidate = git(source, "rev-parse", "HEAD")
            self.assertTrue(independent_gates._proven_ancestor(
                source, approved, candidate, "numerical comparator"))

            shallow = Path(temporary) / "shallow"
            subprocess.run(["git", "clone", "-q", "--depth=1", source.as_uri(),
                            str(shallow)], check=True, capture_output=True)
            git(shallow, "fetch", "-q", "--depth=1", "origin",
                "refs/tags/approved:refs/tags/approved")
            self.assertEqual("true", git(shallow, "rev-parse", "--is-shallow-repository"))
            ambiguous = subprocess.run(["git", "-C", str(shallow), "merge-base",
                                        "--is-ancestor", approved, candidate],
                                       capture_output=True)
            self.assertEqual(1, ambiguous.returncode)
            with self.assertRaisesRegex(ValueError, "revision ancestry is unavailable"):
                independent_gates._proven_ancestor(
                    shallow, approved, candidate, "numerical comparator")

    def test_prospective_and_joint_obligations_are_separate_when_unexecuted(self):
        gates = independent_gates.evaluate(self.manifest, BASE, LANE, {}, ROOT)["gates"]
        self.assertEqual(318, gates["numerical-parity"]["subgates"]["prospective-rule-arithmetic"]["required_cases"])
        self.assertEqual("NOT_RUN", gates["numerical-parity"]["subgates"]["prospective-rule-arithmetic"]["status"])
        cases = gates["numerical-parity"]["subgates"]["prospective-rule-arithmetic"]["cases"]
        self.assertEqual(318, len(cases))
        self.assertEqual({"NOT_RUN"}, {item["status"] for item in cases.values()})
        self.assertIn("P-J-Angle-ratio-limits-off--1.0", cases)
        joint = gates["physical-correctness"]["profiles"]["weld-pulley"]
        self.assertEqual(2, joint["required_cases"])
        self.assertEqual(36000, joint["steps_per_case"])
        self.assertEqual("NOT_RUN", joint["candidate_status"])
        legacy = gates["physical-correctness"]["profiles"]["legacy-weld-pulley"]
        self.assertEqual("NOT_RUN", legacy["candidate_status"])
        self.assertEqual(4, legacy["required_cases"])
        self.assertIn("old four", legacy["reason"])
        self.assertEqual("NOT_RUN", gates["physical-correctness"]["profiles"]["nominal"]["candidate_status"])

    def test_nominal_route_needs_36000_step_capture_and_all_profiles_to_pass(self):
        with self.assertRaisesRegex(ValueError, "nominal"):
            independent_gates.verify_nominal_physical_case(
                Path("/tmp"), {"nominal_physical_case": {"key": "wrong"}},
                "cd21a4bd7d6731a096597f97966db9e02b9de448",
                {"dyn4k-core": "a" * 64}, "b" * 64, ROOT)
        self.assertEqual("NOT_RUN", independent_gates.verify_nominal_physical_case(
            Path("/tmp"), {}, "cd21a4bd7d6731a096597f97966db9e02b9de448",
            {"dyn4k-core": "a" * 64}, "b" * 64, ROOT)["candidate_status"])
        passed = {name: {"candidate_status": "PASSED"} for name in
                  ("default-sleep-wake", "configured-sleep-wake", "weld-pulley", "nominal")}
        passed["legacy-weld-pulley"] = {"candidate_status": "NOT_RUN"}
        self.assertEqual("NOT_RUN", independent_gates.physical_status(passed))
        passed["invented-passing-profile"] = {"candidate_status": "PASSED"}
        self.assertEqual("NOT_RUN", independent_gates.physical_status(passed))
        passed["legacy-weld-pulley"]["candidate_status"] = "PASSED"
        with self.assertRaisesRegex(ValueError, "legacy"):
            independent_gates.physical_status(passed)
        passed["legacy-weld-pulley"]["candidate_status"] = "NOT_RUN"
        passed["nominal"]["candidate_status"] = "NOT_RUN"
        self.assertEqual("NOT_RUN", independent_gates.physical_status(passed))
        passed["nominal"]["candidate_status"] = "FAILED"
        self.assertEqual("FAILED", independent_gates.physical_status(passed))

    def test_verified_physical_result_keeps_legacy_disposition_out_of_receipt_control(self):
        receipt = {"fixtures": [], "legacy-weld-pulley": {"candidate_status": "PASSED"},
                   "profiles": {"legacy-weld-pulley": {"candidate_status": "PASSED"}}}
        with (mock.patch.object(independent_gates, "_json", return_value={"fixtures": []}),
              mock.patch.object(independent_gates, "_numerical_modules",
                                return_value=(mock.Mock(), mock.Mock())),
              mock.patch.object(independent_gates, "verified_numerical_source_sha256",
                                return_value="a" * 64),
              mock.patch.object(independent_gates, "verify_joint_physical_cases",
                                return_value={"candidate_status": "PASSED", "required_cases": 2}),
              mock.patch.object(independent_gates, "verify_nominal_physical_case",
                                return_value={"candidate_status": "PASSED"})):
            profiles = independent_gates._numerical_entries(
                ROOT, receipt, BASE, {"dyn4k-core": "b" * 64}, ROOT,
                physical_only=True)
        self.assertEqual({"PASSED"}, {profiles[name]["candidate_status"] for name in
                         ("default-sleep-wake", "configured-sleep-wake", "weld-pulley", "nominal")})
        self.assertEqual("NOT_RUN", profiles["legacy-weld-pulley"]["candidate_status"])
        self.assertEqual(4, profiles["legacy-weld-pulley"]["required_cases"])
        self.assertEqual("NOT_RUN", independent_gates.physical_status(profiles))
        del profiles["legacy-weld-pulley"]
        with self.assertRaisesRegex(ValueError, "legacy"):
            independent_gates.physical_status(profiles)

    @unittest.skipUnless(
        Path("/tmp/dyn4k-candidate-current-nominal/L-free-s1.0-o0.0_0.0-hz60-0.jsonl.gz").is_file(),
        "retained candidate nominal capture is absent")
    def test_retained_real_nominal_capture_replays_all_zero_and_timestep_checks(self):
        capture = Path("/tmp/dyn4k-candidate-current-nominal")
        receipt = json.loads((capture / "receipt.json").read_text())
        self.assertEqual("1a2b3b5174a5b7a438475628e95f376950fc4e4e",
                         receipt["candidate_commit"])
        self.assertEqual(independent_gates.verified_numerical_source_sha256(
            ROOT, receipt["candidate_commit"]), receipt["source_sha256"])
        trace = capture / "L-free-s1.0-o0.0_0.0-hz60-0.jsonl.gz"
        self.assertEqual(hashlib.sha256(trace.read_bytes()).hexdigest(),
                         receipt["trace_sha256"])
        nominal = independent_gates._nominal_module(ROOT / "tools/numerical")
        self.assertEqual({"states": 36000, "positive_zero_checks": 216000,
                          "timestep_callbacks": 108001, "exact_timestep_checks": 540005},
                         nominal.audit_trace(trace, 36000, 108001))
        self.assertEqual("FAILED", json.loads((capture / "comparison.json").read_text())["status"])

    @unittest.skipUnless(
        Path("/tmp/dyn4k-restored-nominal/trace/L-free-s1.0-o0.0_0.0-hz60-0.jsonl.gz").is_file(),
        "retained frozen nominal reference is absent")
    def test_nominal_route_replays_full_synthetic_positive_and_wrong_artifact(self):
        candidate = "cd21a4bd7d6731a096597f97966db9e02b9de448"
        source_sha = independent_gates.verified_numerical_source_sha256(ROOT, candidate)
        artifact_hash = "a" * 64
        fixture = independent_gates._nominal_module(ROOT / "tools/numerical").compare.load_fixture(
            "nominal-free-motion")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference = root / fixture["reference"]["file"]
            shutil.copy2(Path("/tmp/dyn4k-restored-nominal/trace") / reference.name,
                         reference)
            candidate_trace = root / "candidate.jsonl.gz"
            shutil.copy2(reference, candidate_trace)
            capture = root / "capture.json"
            capture.write_text(json.dumps({
                "candidate_commit": candidate, "source_sha256": source_sha,
                "artifact_sha256": artifact_hash,
                "reference_source_revision": fixture["baseline_source_revision"],
                "reference_artifact_sha256": fixture["baseline_jar_sha256"],
                "reference_trace_sha256": fixture["reference"]["gzip_sha256"],
                "trace_sha256": hashlib.sha256(candidate_trace.read_bytes()).hexdigest(),
                "expected_counts": fixture["counts"],
                "executed_counts": fixture["counts"], "skipped": 0}))
            receipt = {"nominal_physical_case": {"key": "nominal-free-motion",
                       "reference": reference.name, "candidate": candidate_trace.name,
                       "capture_receipt": capture.name}}
            outcome = independent_gates.verify_nominal_physical_case(
                root, receipt, candidate, {"dyn4k-core": artifact_hash}, source_sha, ROOT)
            self.assertEqual("PASSED", outcome["candidate_status"], outcome)
            outcome = independent_gates.verify_nominal_physical_case(
                root, receipt, candidate, {"dyn4k-core": "b" * 64}, source_sha, ROOT)
            self.assertEqual("FAILED", outcome["candidate_status"])

    def test_assembly_requires_every_selected_lane_and_digest_bound_results(self):
        candidate = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                            cwd=ROOT, text=True).strip()
        with self.assertRaisesRegex(ValueError, "112"):
            independent_gates.evaluate_assembly(self.manifest, candidate, {}, ROOT)
        selections = {lane: {"archives": {}} for lane in self.manifest["lanes"]}
        assembled = independent_gates.evaluate_assembly(self.manifest, candidate,
                                                         selections, ROOT)
        self.assertEqual(112, assembled["required_lanes"])
        self.assertEqual("NOT_RUN", assembled["status"])
        self.assertEqual(2526, assembled["selected_cases"][LANE])
        self.assertEqual(assembled["result_sha256"], independent_gates.digest(
            {key: value for key, value in assembled.items() if key != "result_sha256"}))
        with tempfile.TemporaryDirectory() as temporary:
            inputs = Path(temporary) / "assembly.json"
            inputs.write_text(json.dumps(selections))
            cli = subprocess.run([
                sys.executable, str(ROOT / "tools/qualification/independent_gates.py"),
                "--repository", str(ROOT), "--candidate-sha", candidate,
                "--assembly", str(inputs)], capture_output=True, text=True)
            self.assertEqual(1, cli.returncode)
            self.assertEqual("NOT_RUN", json.loads(cli.stdout)["status"])
        selections[LANE]["expected_artifact_hashes"] = {"dyn4k-core": "wrong"}
        with self.assertRaisesRegex(ValueError, "artifact"):
            independent_gates.evaluate_assembly(self.manifest, candidate,
                                                 selections, ROOT)

    def test_assembly_adapter_emits_selected_cases_only_from_verified_full_routes(self):
        candidate = "a17d7cfce8b8abb8cdc4c5f5f31285f74c9b7149"
        selections = {lane: {"archives": {}} for lane in self.manifest["lanes"]}
        def verified(_manifest, _candidate, lane_id, *_args):
            names = self.manifest["lanes"][lane_id]["required_gates"] + self.manifest["global_gates"]
            result = {"candidate_sha": candidate, "lane": lane_id,
                      "expected_archive_digests": {name: "a" * 64 for name in names},
                      "gates": {name: {"status": "PASSED", "archive_sha256": "b" * 64,
                                       "complete_selected_suite": name == "staged-consumer"}
                                for name in names}, "status": "PASSED"}
            result["result_sha256"] = independent_gates.digest(result)
            return result
        with mock.patch.object(independent_gates, "evaluate", side_effect=verified):
            assembled = independent_gates.evaluate_assembly(
                self.manifest, candidate, selections, ROOT)
        self.assertEqual("PASSED", assembled["status"])
        self.assertEqual(112, len(assembled["qualify_adapter"]))
        self.assertEqual(2526, len(assembled["qualify_adapter"][LANE]["case_results"]))
        self.assertEqual({"PASSED"}, {row["status"] for row in
                                        assembled["qualify_adapter"][LANE]["case_results"]})
        def incomplete(*args):
            result = verified(*args)
            result["gates"]["staged-consumer"]["complete_selected_suite"] = False
            result["result_sha256"] = independent_gates.digest(
                {key: value for key, value in result.items() if key != "result_sha256"})
            return result
        with mock.patch.object(independent_gates, "evaluate", side_effect=incomplete):
            with self.assertRaisesRegex(ValueError, "complete selected-suite"):
                independent_gates.evaluate_assembly(self.manifest, candidate,
                                                     selections, ROOT)

    def test_sustained_adapter_requires_external_key_and_reviewed_producer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "evidence").mkdir()
            (root / "evidence/archive.json").write_text(json.dumps({
                "schema": 1, "route": "sustained-raw-v1", "source_commit": BASE,
                "artifacts": {"jvm.java": {"core": {"sha256": "a" * 64},
                                            "kotlin": {"sha256": "b" * 64}}}}))
            scope = {"producer_manifest_hashes": {"evidence/archive.json":
                     hashlib.sha256((root / "evidence/archive.json").read_bytes()).hexdigest()},
                     "verifier_sha256": "c" * 64}
            with self.assertRaisesRegex(independent_gates.IncompleteEvidence,
                                        "trusted key"):
                independent_gates._performance_resource(
                    root, BASE, {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64},
                    scope, ROOT)
            with tempfile.TemporaryDirectory() as key_temporary:
                key = Path(key_temporary) / "trusted.key"
                key.write_bytes(b"independent-archive-key-1234567890")
                with self.assertRaisesRegex(independent_gates.IncompleteEvidence,
                                            "not present at candidate"):
                    independent_gates._performance_resource(
                        root, BASE, {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64},
                        scope, ROOT, key)
                with self.assertRaisesRegex(ValueError, "dyn4k-core JAR differs"):
                    independent_gates._performance_resource(
                        root, BASE, {"dyn4k-core": "e" * 64, "dyn4k": "b" * 64},
                        scope, ROOT, key)
            full_scope = {"candidate_sha": BASE, "target": "jvm", "runtime": "Java",
                          "runtime_identity": "reference host", "artifact_hashes": {
                              "dyn4k-core": "a" * 64, "dyn4k": "b" * 64}, **scope}
            with self.assertRaisesRegex(ValueError, "policy pin"):
                independent_gates._producer_scope("performance-resource", BASE,
                                                  {"performance-resource": full_scope})

    def test_sustained_current_source_requires_approved_policy_and_rejects_wrong_pin(self):
        candidate = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                            cwd=ROOT, text=True).strip()
        verifier = ROOT / "tools/performance/sustained_archive.py"
        policy = ROOT / "docs/research/performance-manifest-v1.json"
        guarded_paths = ["tools/performance/sustained_archive.py",
                         "tools/performance/manifest.py", "tools/performance/measure.py",
                         "tools/performance/analyze.py", "tools/performance/candidate_runner.py",
                         "tools/performance/stress_monitor.py",
                         "docs/research/performance-manifest-v1.json"]
        checkout_bound = checkout_matches_commit(guarded_paths)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "archive"
            root.mkdir()
            evidence = root / "evidence"
            evidence.mkdir()
            index = {"schema": 1, "route": "sustained-raw-v1",
                     "source_commit": candidate,
                     "artifacts": {"jvm.java": {"core": {"sha256": "a" * 64},
                                                 "kotlin": {"sha256": "b" * 64}}}}
            (evidence / "archive.json").write_text(json.dumps(index))
            key = Path(temporary) / "trusted.key"
            key.write_bytes(b"independent-archive-key-1234567890")
            scope = {"producer_manifest_hashes": {"evidence/archive.json":
                     hashlib.sha256((evidence / "archive.json").read_bytes()).hexdigest()},
                     "verifier_sha256": hashlib.sha256(verifier.read_bytes()).hexdigest(),
                     "policy_sha256": hashlib.sha256(policy.read_bytes()).hexdigest()}
            if checkout_bound:
                with self.assertRaisesRegex(independent_gates.IncompleteEvidence,
                                            "unpassed policy"):
                    independent_gates._performance_resource(
                        root, candidate, {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64},
                        scope, ROOT, key)
            else:
                with self.assertRaisesRegex(ValueError, "sustained performance verifier source differs"):
                    independent_gates._performance_resource(
                        root, candidate, {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64},
                        scope, ROOT, key)
            scope["verifier_sha256"] = "0" * 64
            if checkout_bound:
                with self.assertRaisesRegex(ValueError, "independently approved verifier"):
                    independent_gates._performance_resource(
                        root, candidate, {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64},
                        scope, ROOT, key)

    def test_producer_scope_is_part_of_digest_bound_public_result(self):
        scope = {"candidate_sha": BASE, "target": "jvm", "runtime": "Java",
                 "runtime_identity": "reviewed JVM runner",
                 "artifact_hashes": {"dyn4k-core": "a" * 64}}
        result = independent_gates.evaluate(
            self.manifest, BASE, LANE, {}, ROOT,
            expected_producer_scopes={"migration-journeys": scope})
        self.assertEqual(scope, result["expected_producer_scopes"]["migration-journeys"])
        self.assertEqual("NOT_RUN", result["gates"]["migration-journeys"]["status"])

    def test_prospective_adapter_rejects_a_reported_pass_without_318_raw_cases(self):
        source_sha = independent_gates.verified_numerical_source_sha256(ROOT, BASE)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt = {"status": "PASSED", "prospective_cases": [],
                       "prospective_catalog_sha256": independent_gates.PROSPECTIVE_POLICY_SHA256}
            with self.assertRaisesRegex(ValueError, "318 prospective"):
                independent_gates.verify_prospective_case_subgates(
                    root, receipt, ROOT, BASE, {"dyn4k-core": "a" * 64}, source_sha)

    def test_prospective_rule_and_arithmetic_status_requires_both_verified(self):
        self.assertEqual("PASSED", independent_gates._prospective_case_status(
            "PASSED_NUMERICAL_POLICY", "PASSED"))
        self.assertEqual("NOT_RUN", independent_gates._prospective_case_status(
            "PASSED_NUMERICAL_POLICY", "NOT_RUN"))
        self.assertEqual("NOT_RUN", independent_gates._prospective_case_status(
            "UNPASSED_TARGET_MATH", "PASSED"))
        self.assertEqual("FAILED", independent_gates._prospective_case_status(
            "FAILED_NUMERICAL_POLICY", "PASSED"))
        self.assertEqual("FAILED", independent_gates._prospective_case_status(
            "PASSED_NUMERICAL_POLICY", "FAILED_ARITHMETIC"))

    def test_pending_prospective_bridge_binds_15_receipts_without_claiming_pass(self):
        candidate = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                            cwd=ROOT, text=True).strip()
        source_sha = independent_gates.verified_numerical_source_sha256(ROOT, candidate)
        artifact_sha = "a" * 64
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            methods = []
            for method in independent_gates.PROSPECTIVE_BRIDGE_METHODS:
                path = f"{method}.json"
                (root / path).write_text(json.dumps({
                    "schema": "portable-arithmetic-capture-receipt/3",
                    "method": method, "candidate_commit": candidate,
                    "source_archive_sha256": source_sha,
                    "artifact_sha256": artifact_sha}))
                methods.append({"method": method, "receipt": path,
                                "sha256": hashlib.sha256((root / path).read_bytes()).hexdigest()})
            inventory = {"schema": "prospective-arithmetic-bridge/1",
                         "candidate_sha": candidate, "source_sha256": source_sha,
                         "artifact_sha256": artifact_sha,
                         "case_ids": list(independent_gates.approved_prospective_cases(str(ROOT))),
                         "methods": methods, "baseline_attestation_sha256": "b" * 64}

            def check():
                path = root / "bridge.json"
                path.write_text(json.dumps(inventory))
                bridge = {"inventory": path.name,
                          "inventory_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                return independent_gates.verify_pending_prospective_bridge(
                    root, {"status": "PASSED", "prospective_bridge": bridge}, ROOT,
                    candidate, artifact_sha, source_sha)

            self.assertEqual("NOT_RUN", check()["status"])
            self.assertEqual(15, check()["transport_receipts"])
            inventory["case_ids"].reverse()
            with self.assertRaisesRegex(ValueError, "case, method"):
                check()
            inventory["case_ids"].reverse()
            inventory["methods"][0], inventory["methods"][1] = (
                inventory["methods"][1], inventory["methods"][0])
            with self.assertRaisesRegex(ValueError, "case, method"):
                check()
            inventory["methods"][0], inventory["methods"][1] = (
                inventory["methods"][1], inventory["methods"][0])
            inventory["artifact_sha256"] = "c" * 64
            with self.assertRaisesRegex(ValueError, "case, method"):
                check()
            inventory["artifact_sha256"] = artifact_sha
            inventory["source_sha256"] = "d" * 64
            with self.assertRaisesRegex(ValueError, "case, method"):
                check()
            inventory["source_sha256"] = source_sha
            method_path = root / methods[0]["receipt"]
            method_path.write_text(method_path.read_text().replace(candidate, BASE))
            with self.assertRaisesRegex(ValueError, "method receipt differs"):
                check()

    def test_prospective_adapter_loads_pinned_checker_then_demands_raw_case_bytes(self):
        candidate = independent_gates.PROSPECTIVE_POLICY_REVISION
        identities = independent_gates.approved_prospective_cases(str(ROOT))
        receipt = {"status": "PASSED",
                   "prospective_catalog_sha256": independent_gates.PROSPECTIVE_POLICY_SHA256,
                   "prospective_cases": [
                       {"id": case, "reference": "missing.jsonl", "candidate": "missing.jsonl",
                        "capture_receipt": "missing.json", "arithmetic_audit": "missing-audit.json"}
                       for case in identities]}
        with tempfile.TemporaryDirectory() as temporary:
            checker_paths = [f"tools/numerical/portable/{name}" for name in
                             independent_gates.APPROVED_PROSPECTIVE_CHECKERS]
            checker_paths.append(independent_gates.PROSPECTIVE_POLICY_PATH)
            expected = ("raw archive file is missing" if checkout_matches_commit(checker_paths)
                        else "prospective policy/checker blob differs")
            with self.assertRaisesRegex(ValueError, expected):
                independent_gates.verify_prospective_case_subgates(
                    Path(temporary), receipt, ROOT, candidate,
                    {"dyn4k-core": "a" * 64},
                    independent_gates.verified_numerical_source_sha256(ROOT, candidate))

    def test_prospective_export_uses_approved_bytes_with_autocrlf_true(self):
        candidate = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                            cwd=ROOT, text=True).strip()
        receipt = {"prospective_catalog_sha256": independent_gates.PROSPECTIVE_POLICY_SHA256,
                   "prospective_cases": [
                       {"id": case, "reference": "missing.jsonl", "candidate": "missing.jsonl",
                        "capture_receipt": "missing.json", "arithmetic_audit": "missing-audit.json"}
                       for case in independent_gates.approved_prospective_cases(str(ROOT))]}
        exported = []
        closure = independent_gates.APPROVED_PROSPECTIVE_PATH_MODEL_CHECKERS
        original_extractall = tarfile.TarFile.extractall

        def observe(package, path, *args, **kwargs):
            original_extractall(package, path, *args, **kwargs)
            checked = {name: hashlib.sha256(
                (Path(path) / "tools/numerical/portable" / name).read_bytes()).hexdigest()
                for name in closure}
            checked.update({name: hashlib.sha256((Path(path) / name).read_bytes()).hexdigest()
                            for name in independent_gates.APPROVED_PROSPECTIVE_EXECUTABLE_SHARED})
            checked.update({name: hashlib.sha256((Path(path) / name).read_bytes()).hexdigest()
                            for name in independent_gates.PATH_MODEL_CAPTURE_DEPENDENCIES})
            exported.append(checked)

        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict(os.environ, {
                "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.autocrlf",
                "GIT_CONFIG_VALUE_0": "true"}), mock.patch.object(
                    tarfile.TarFile, "extractall", observe):
            with self.assertRaisesRegex(ValueError, "raw archive file is missing"):
                independent_gates.verify_prospective_case_subgates(
                    Path(temporary), receipt, ROOT, candidate, {"dyn4k-core": "a" * 64},
                    independent_gates.verified_numerical_source_sha256(ROOT, candidate))
        self.assertEqual([closure | independent_gates.APPROVED_PROSPECTIVE_EXECUTABLE_SHARED |
                          independent_gates.PATH_MODEL_CAPTURE_DEPENDENCIES],
                         exported)

    def test_prospective_export_rejects_altered_approved_bytes(self):
        candidate = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                            cwd=ROOT, text=True).strip()
        receipt = {"prospective_catalog_sha256": independent_gates.PROSPECTIVE_POLICY_SHA256,
                   "prospective_cases": [
                       {"id": case, "reference": "missing.jsonl", "candidate": "missing.jsonl",
                        "capture_receipt": "missing.json", "arithmetic_audit": "missing-audit.json"}
                       for case in independent_gates.approved_prospective_cases(str(ROOT))]}
        original_extractall = tarfile.TarFile.extractall

        for relative in (*(
                f"tools/numerical/portable/{name}" for name in
                independent_gates.APPROVED_PROSPECTIVE_EXECUTABLE_CHECKERS),
                *independent_gates.PROSPECTIVE_EXECUTABLE_CAPTURE_DEPENDENCIES,
                "tools/numerical/compare.py", "tools/numerical/physical.py",
                "tools/numerical/fixtures.json"):
            with self.subTest(exported=relative):
                def alter(package, path, *args, **kwargs):
                    original_extractall(package, path, *args, **kwargs)
                    checker = Path(path) / relative
                    checker.write_bytes(checker.read_bytes() + b"\n")

                with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
                        tarfile.TarFile, "extractall", alter):
                    with self.assertRaisesRegex(ValueError,
                                                f"prospective exported checker differs: {relative}"):
                        independent_gates.verify_prospective_case_subgates(
                            Path(temporary), receipt, ROOT, candidate,
                            {"dyn4k-core": "a" * 64},
                            independent_gates.verified_numerical_source_sha256(ROOT, candidate))

    def test_executable_checker_window_binds_complete_committed_closure(self):
        revision = "fbaee1b16de2ff0633e2981e69cf59044b61c745"
        self.assertEqual(revision, independent_gates.PROSPECTIVE_EXECUTABLE_CHECKER_REVISION)
        closure = independent_gates.APPROVED_PROSPECTIVE_EXECUTABLE_CHECKERS
        self.assertEqual({"numeric_producer.py", "numeric_producer_trace.py",
                          "numeric_class_witness.py", "pulley_jdi_v2.py",
                          "pulley_jdi_v1.py", "pulley_jdi_inputs_v2.py", "run.py",
                          "frozen_weld_pulley.py", "exact_consistency.py", "physical.py",
                          "class_witness/NumericClassWitness.java"},
                         set(closure) - set(independent_gates.APPROVED_PROSPECTIVE_INVENTORY_FIX_CHECKERS))
        self.assertIn("prospective_compare.py", closure)
        self.assertEqual({
            "tools/numerical/compare.py": independent_gates.APPROVED_POLICY[
                "tools/numerical/compare.py"],
            "tools/numerical/physical.py": independent_gates.APPROVED_POLICY[
                "tools/numerical/physical.py"]},
            independent_gates.APPROVED_PROSPECTIVE_EXECUTABLE_SHARED)
        for name, digest in closure.items():
            relative = f"tools/numerical/portable/{name}"
            committed = subprocess.check_output(
                ["git", "--no-replace-objects", "show", f"{revision}:{relative}"], cwd=ROOT)
            self.assertEqual(digest, hashlib.sha256(committed).hexdigest(), name)
            self.assertEqual(independent_gates.PINNED_PROSPECTIVE_LOCAL_CHECKERS[name],
                             hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), name)
        bound = independent_gates._prospective_checker_binding(ROOT, revision)
        for name, digest in closure.items():
            self.assertEqual(digest, bound[f"tools/numerical/portable/{name}"])
        for path, digest in independent_gates.APPROVED_PROSPECTIVE_EXECUTABLE_SHARED.items():
            self.assertEqual(digest, bound[path])
        build = "tools/numerical/portable/build.gradle.kts"
        self.assertEqual("fac77dd6282f67dd8593885a73f880d0bab6156eda93391a28cdbafb800fbdc3",
                         independent_gates.P2_EXECUTABLE_LOCAL_DEPENDENCIES[build])
        self.assertEqual(independent_gates.P2_JDK21_JDI_DEPENDENCIES[build],
                         hashlib.sha256(subprocess.check_output(
                             ["git", "--no-replace-objects", "show",
                              f"{independent_gates.P2_JDK21_JDI_SOURCE_REVISION}:{build}"],
                             cwd=ROOT)).hexdigest())
        self.assertEqual(independent_gates.APPROVED_P2_LOCAL_PRODUCERS,
                         independent_gates._p2_producer_binding(ROOT, revision))
        for candidate, expected in (
                ("df316d8900f850d22f9c933f6aac8250b1e10ed1",
                 independent_gates.APPROVED_PROSPECTIVE_INVENTORY_FIX_CHECKERS),
                ("375812a97de8cb3e439fc2a204e029de1a6de338",
                 independent_gates.APPROVED_PROSPECTIVE_NUMERIC_PROBE_CHECKERS)):
            with self.subTest(candidate=candidate):
                bound = independent_gates._prospective_checker_binding(ROOT, candidate)
                self.assertEqual(expected, {
                    name: bound[f"tools/numerical/portable/{name}"] for name in expected})
                self.assertNotIn("tools/numerical/portable/numeric_producer.py", bound)
                self.assertNotIn("tools/numerical/portable/pulley_jdi_v2.py", bound)

    def test_replay_scratch_window_selects_exact_producer_bytes(self):
        previous = independent_gates.PROSPECTIVE_EXECUTABLE_CHECKER_REVISION
        revision = independent_gates.PROSPECTIVE_REPLAY_SCRATCH_REVISION
        current = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                          cwd=ROOT, text=True).strip()
        relative = "tools/numerical/portable/numeric_producer.py"
        old = independent_gates.APPROVED_PROSPECTIVE_EXECUTABLE_CHECKERS["numeric_producer.py"]
        new = independent_gates.PROSPECTIVE_REPLAY_SCRATCH_CHECKERS[
            "numeric_producer.py"]
        self.assertNotEqual(old, new)
        self.assertEqual({**independent_gates.APPROVED_PROSPECTIVE_EXECUTABLE_CHECKERS,
                          "numeric_producer.py": new},
                         independent_gates.PROSPECTIVE_REPLAY_SCRATCH_CHECKERS)
        current_digest = independent_gates.APPROVED_PROSPECTIVE_BASELINE_COMPAT_CHECKERS[
            "numeric_producer.py"]
        self.assertEqual(current_digest, hashlib.sha256((ROOT / relative).read_bytes()).hexdigest())
        self.assertEqual(current_digest, independent_gates.PINNED_PROSPECTIVE_LOCAL_CHECKERS[
            "numeric_producer.py"])
        for candidate, expected in ((previous, old), (revision, new), (current, current_digest)):
            with self.subTest(candidate=candidate):
                committed = subprocess.check_output(
                    ["git", "--no-replace-objects", "show", f"{candidate}:{relative}"],
                    cwd=ROOT)
                self.assertEqual(expected, hashlib.sha256(committed).hexdigest())
                bound = independent_gates._prospective_checker_binding(ROOT, candidate)
                self.assertEqual(expected, bound[relative])
                dependencies = (independent_gates.PATH_MODEL_CAPTURE_DEPENDENCIES
                                if candidate == current else
                                independent_gates.PROSPECTIVE_EXECUTABLE_CAPTURE_DEPENDENCIES)
                closure = (independent_gates.APPROVED_PROSPECTIVE_PATH_MODEL_CHECKERS
                           if candidate == current else
                           independent_gates.PROSPECTIVE_REPLAY_SCRATCH_CHECKERS
                           if candidate == revision else
                           independent_gates.APPROVED_PROSPECTIVE_EXECUTABLE_CHECKERS)
                self.assertEqual(
                    {f"tools/numerical/portable/{name}" for name in closure} |
                    set(independent_gates.APPROVED_PROSPECTIVE_EXECUTABLE_SHARED) |
                    set(dependencies) | {independent_gates.PROSPECTIVE_POLICY_PATH},
                    set(bound))
                self.assertEqual((independent_gates.APPROVED_P2_PATH_MODEL_PRODUCERS
                                  if candidate == current
                                  else independent_gates.APPROVED_P2_LOCAL_PRODUCERS),
                                 independent_gates._p2_producer_binding(ROOT, candidate))

        original_read = Path.read_bytes
        local = ROOT / relative
        old_bytes = subprocess.check_output(
            ["git", "--no-replace-objects", "show", f"{previous}:{relative}"], cwd=ROOT)
        new_bytes = subprocess.check_output(
            ["git", "--no-replace-objects", "show", f"{revision}:{relative}"], cwd=ROOT)
        with mock.patch.object(Path, "read_bytes", lambda path: old_bytes
                               if path == local else original_read(path)):
            for candidate in (previous, revision):
                with self.subTest(local_drift=candidate), self.assertRaisesRegex(
                        ValueError, "prospective policy/checker blob differs"):
                    independent_gates._prospective_checker_binding(ROOT, candidate)

        original_show = subprocess.check_output
        for candidate, replacement in ((previous, new_bytes), (revision, old_bytes)):
            def altered(command, *args, **kwargs):
                if command[-1] == f"{candidate}:{relative}":
                    return replacement
                return original_show(command, *args, **kwargs)

            with self.subTest(candidate_drift=candidate), mock.patch.object(
                    subprocess, "check_output", altered), self.assertRaisesRegex(
                        ValueError, "prospective policy/checker blob differs"):
                independent_gates._prospective_checker_binding(ROOT, candidate)

        def missing(command, *args, **kwargs):
            if command[-1] == f"{revision}:{relative}":
                raise subprocess.CalledProcessError(128, command)
            return original_show(command, *args, **kwargs)

        with mock.patch.object(subprocess, "check_output", missing), self.assertRaisesRegex(
                ValueError, "prospective policy/checker blob differs"):
            independent_gates._prospective_checker_binding(ROOT, revision)

    def test_executable_checker_rejects_local_and_candidate_helper_drift(self):
        revision = "fbaee1b16de2ff0633e2981e69cf59044b61c745"
        original_read = Path.read_bytes
        original_show = subprocess.check_output
        for name in independent_gates.APPROVED_PROSPECTIVE_EXECUTABLE_CHECKERS:
            relative = f"tools/numerical/portable/{name}"
            local = ROOT / relative
            with self.subTest(name=name, surface="local"), mock.patch.object(
                    Path, "read_bytes", lambda path, local=local: b"substituted"
                    if path == local else original_read(path)):
                with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                    independent_gates._prospective_checker_binding(ROOT, revision)

            def missing_local(path):
                if path == local:
                    raise FileNotFoundError(path)
                return original_read(path)

            with self.subTest(name=name, surface="missing-local"), mock.patch.object(
                    Path, "read_bytes", missing_local):
                with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                    independent_gates._prospective_checker_binding(ROOT, revision)

            def altered(command, *args, **kwargs):
                if command[-1] == f"{revision}:{relative}":
                    return b"substituted"
                return original_show(command, *args, **kwargs)

            with self.subTest(name=name, surface="candidate"), mock.patch.object(
                    subprocess, "check_output", altered):
                with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                    independent_gates._prospective_checker_binding(ROOT, revision)

            def absent(command, *args, **kwargs):
                if command[-1] == f"{revision}:{relative}":
                    raise subprocess.CalledProcessError(128, command)
                return original_show(command, *args, **kwargs)

            with self.subTest(name=name, surface="missing-candidate"), mock.patch.object(
                    subprocess, "check_output", absent):
                with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                    independent_gates._prospective_checker_binding(ROOT, revision)

    def test_executable_shared_imports_reject_local_and_candidate_drift(self):
        revision = "fbaee1b16de2ff0633e2981e69cf59044b61c745"
        original_read = Path.read_bytes
        original_show = subprocess.check_output
        for relative in independent_gates.APPROVED_PROSPECTIVE_EXECUTABLE_SHARED:
            local = ROOT / relative
            with self.subTest(path=relative, surface="local"), mock.patch.object(
                    Path, "read_bytes", lambda path, local=local: b"substituted"
                    if path == local else original_read(path)):
                with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                    independent_gates._prospective_checker_binding(ROOT, revision)

            def altered(command, *args, **kwargs):
                if command[-1] == f"{revision}:{relative}":
                    return b"substituted"
                return original_show(command, *args, **kwargs)

            with self.subTest(path=relative, surface="candidate"), mock.patch.object(
                    subprocess, "check_output", altered):
                with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                    independent_gates._prospective_checker_binding(ROOT, revision)

    def test_executable_capture_dependencies_bind_current_and_candidate_bytes(self):
        dependencies = independent_gates.PROSPECTIVE_EXECUTABLE_CAPTURE_DEPENDENCIES
        self.assertEqual({
            "tools/numerical/portable/capture_actual.py",
            "tools/numerical/portable/actual_arithmetic.py",
            "tools/numerical/portable/rotation_oracle.py",
            "tools/numerical/portable/boolean_rotation_jdi/jdi_bridge.py",
            "tools/numerical/portable/boolean_rotation_jdi/source_guard.py",
            "tools/numerical/portable/boolean_rotation_jdi/witness.py",
            "tools/numerical/portable/boolean_rotation_jdi/loaded_code.py"}, set(dependencies))
        self.assertNotIn("capture_actual.py",
                         independent_gates.APPROVED_PROSPECTIVE_EXECUTABLE_CHECKERS)
        for candidate in (independent_gates.PROSPECTIVE_EXECUTABLE_CHECKER_REVISION,
                          independent_gates.PROSPECTIVE_REPLAY_SCRATCH_REVISION):
            bound = independent_gates._prospective_checker_binding(ROOT, candidate)
            for relative, expected in dependencies.items():
                with self.subTest(candidate=candidate, path=relative):
                    committed = subprocess.check_output(
                        ["git", "--no-replace-objects", "show", f"{candidate}:{relative}"],
                        cwd=ROOT)
                    self.assertEqual(expected, hashlib.sha256(committed).hexdigest())
                    self.assertEqual(independent_gates.OUTPUT_PROVENANCE_CAPTURE_DEPENDENCIES[relative],
                                     hashlib.sha256((ROOT / relative).read_bytes()).hexdigest())
                    self.assertEqual(expected, bound[relative])
        older = independent_gates._prospective_checker_binding(
            ROOT, independent_gates.PROSPECTIVE_INVENTORY_FIX_CHECKER_REVISION)
        self.assertNotIn("tools/numerical/portable/capture_actual.py", older)

        relative = "tools/numerical/portable/capture_actual.py"
        revision = independent_gates.PROSPECTIVE_REPLAY_SCRATCH_REVISION
        original_read = Path.read_bytes
        original_show = subprocess.check_output
        with mock.patch.object(Path, "read_bytes", lambda path: b"changed"
                               if path == ROOT / relative else original_read(path)):
            with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                independent_gates._prospective_checker_binding(ROOT, revision)

        def changed_candidate(command, *args, **kwargs):
            if command[-1] == f"{revision}:{relative}":
                return b"changed"
            return original_show(command, *args, **kwargs)

        with mock.patch.object(subprocess, "check_output", changed_candidate):
            with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                independent_gates._prospective_checker_binding(ROOT, revision)

        def missing_candidate(command, *args, **kwargs):
            if command[-1] == f"{revision}:{relative}":
                raise subprocess.CalledProcessError(128, command)
            return original_show(command, *args, **kwargs)

        with mock.patch.object(subprocess, "check_output", missing_candidate):
            with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                independent_gates._prospective_checker_binding(ROOT, revision)

    def test_v6_window_binds_reviewed_source_and_preserves_historical_windows(self):
        reviewed = "0d5799e1c84f76c504b53f3eaf7468bca20a60eb"
        self.assertEqual(reviewed, independent_gates.PROSPECTIVE_V6_SOURCE_REVISION)
        checker = independent_gates._prospective_checker_binding(ROOT, reviewed)
        producer = independent_gates._p2_producer_binding(ROOT, reviewed)
        expected = (independent_gates.APPROVED_PROSPECTIVE_V6_CHECKERS |
                    independent_gates.PROSPECTIVE_V6_CAPTURE_DEPENDENCIES |
                    independent_gates.APPROVED_PROSPECTIVE_EXECUTABLE_SHARED)
        for name, digest in expected.items():
            relative = (name if name.startswith("tools/") else
                        f"tools/numerical/portable/{name}")
            with self.subTest(path=relative):
                committed = subprocess.check_output(
                    ["git", "--no-replace-objects", "show", f"{reviewed}:{relative}"],
                    cwd=ROOT)
                self.assertEqual(digest, hashlib.sha256(committed).hexdigest())
                local_digest = independent_gates.OUTPUT_PROVENANCE_CAPTURE_DEPENDENCIES.get(
                    relative, independent_gates.PINNED_PROSPECTIVE_LOCAL_CHECKERS.get(
                        name, digest))
                self.assertEqual(local_digest,
                                 hashlib.sha256((ROOT / relative).read_bytes()).hexdigest())
                self.assertEqual(digest, checker[relative])
        for relative, digest in independent_gates.P2_V6_DEPENDENCIES.items():
            with self.subTest(dependency=relative):
                committed = subprocess.check_output(
                    ["git", "--no-replace-objects", "show", f"{reviewed}:{relative}"],
                    cwd=ROOT)
                self.assertEqual(digest, hashlib.sha256(committed).hexdigest())
                self.assertEqual(independent_gates.P2_OUTPUT_PROVENANCE_DEPENDENCIES[
                    relative], hashlib.sha256((ROOT / relative).read_bytes()).hexdigest())
        self.assertEqual(independent_gates.APPROVED_P2_V6_PRODUCERS, producer)
        self.assertIn("tools/numerical/portable/actual_capture_receipt.py", checker)
        self.assertIn("tools/numerical/portable/actual_trace.py", checker)
        self.assertIn("actual_capture_receipt", independent_gates.PORTABLE_REPLAY_MODULES)
        self.assertIn("actual_trace", independent_gates.PORTABLE_REPLAY_MODULES)

        historical = independent_gates.PROSPECTIVE_JVM8_AGENT_SOURCE_REVISION
        older = independent_gates._prospective_checker_binding(ROOT, historical)
        self.assertEqual(independent_gates.APPROVED_PROSPECTIVE_JVM8_AGENT_CHECKERS[
            "numeric_producer.py"], older["tools/numerical/portable/numeric_producer.py"])
        self.assertNotIn("tools/numerical/portable/actual_trace.py", older)
        self.assertEqual(independent_gates.APPROVED_P2_JVM8_PRODUCERS,
                         independent_gates._p2_producer_binding(ROOT, historical))
        for revision in ("606a8541cdf6209791e58af88c5d8f82543b91a9",
                         "02e9d287910aebd9301494a2ed745cdbb83ffc4c"):
            with self.subTest(intermediate=revision):
                with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                    independent_gates._prospective_checker_binding(ROOT, revision)
                with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, revision)

    def test_private_launch_window_pins_exact_source_and_rejects_intermediates(self):
        current = "42df45088321a592323ebb02ba9c1a1d6fb655e0"
        self.assertEqual(current, independent_gates.PRIVATE_LAUNCH_SOURCE_REVISION)
        checker = independent_gates._prospective_checker_binding(ROOT, current)
        producer = independent_gates._p2_producer_binding(ROOT, current)
        self.assertEqual(independent_gates.APPROVED_P2_PRIVATE_LAUNCH_PRODUCERS,
                         producer)
        for relative, digest in independent_gates.PRIVATE_LAUNCH_CAPTURE_DEPENDENCIES.items():
            with self.subTest(path=relative):
                committed = subprocess.check_output(
                    ["git", "--no-replace-objects", "show", f"{current}:{relative}"],
                    cwd=ROOT)
                self.assertEqual(digest, hashlib.sha256(committed).hexdigest())
                self.assertEqual(
                    independent_gates.OUTPUT_PROVENANCE_CAPTURE_DEPENDENCIES[relative],
                    hashlib.sha256((ROOT / relative).read_bytes()).hexdigest())
                self.assertEqual(digest, checker[relative])
        for relative, digest in independent_gates.P2_PRIVATE_LAUNCH_DEPENDENCIES.items():
            with self.subTest(dependency=relative):
                self.assertEqual(digest, hashlib.sha256(subprocess.check_output(
                    ["git", "--no-replace-objects", "show", f"{current}:{relative}"],
                    cwd=ROOT)).hexdigest())
                self.assertEqual(
                    independent_gates.P2_OUTPUT_PROVENANCE_DEPENDENCIES[relative],
                    hashlib.sha256((ROOT / relative).read_bytes()).hexdigest())
        historical = independent_gates.PROSPECTIVE_V6_SOURCE_REVISION
        old = independent_gates._prospective_checker_binding(ROOT, historical)
        self.assertEqual(independent_gates.PROSPECTIVE_V6_CAPTURE_DEPENDENCIES[
            "tools/numerical/portable/capture_actual.py"], old[
                "tools/numerical/portable/capture_actual.py"])
        self.assertEqual(independent_gates.APPROVED_P2_V6_PRODUCERS,
                         independent_gates._p2_producer_binding(ROOT, historical))
        for revision in ("650045f6845d73deb439aac07b6b8eaa826304be",
                         "566dccb4af37dc6ede65bc5f46d374d5acb97c14",
                         "e451ccf010c8f1c11a428d63806795f455086af0",
                         "59f97775bb7fc28ec2d63fb15a796a94231a5f80",
                         "41d04ac5af90b8cbc0033d5d8f3d69c022b6bb7e",
                         "84adade4d70550f13685c7852b3ea7ac867e8ff3",
                         "2bf8c3e10bcacc77354714541aa71bceb102bf41",
                         "74aa70123fcf64ef8444727d9cd1b491456b2931",
                         "9f62b631394453d03c5d95b8daf68c9f397849c6",
                         "542b1a7833db649c8d91568da4bdf93029ea6667",
                         "97edf52beb0a7ab15daa51382ed49205e1786893",
                         "9ab252e8e4e4f6e6a74abc66cfed3a92ad9dd85b",
                         "db548c15511d23c8d966d78abd976ecebb9fd326",
                         "e75f3b9325b45ea5675fe95eb852f592fd6aec9c",
                         "1f5d0647f915311ed096ce8945b4e86d3ea3fc9a",
                         "9b3442efa50b7a215b2c5c2ff2584671dc14a14a",
                         "fb08a5cbb0d0cd1ec8d27460b4e66a9bf65a6e8f"):
            with self.subTest(intermediate=revision):
                with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                    independent_gates._prospective_checker_binding(ROOT, revision)
                with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, revision)

        relative = "tools/numerical/portable/capture_actual.py"
        original_read = Path.read_bytes
        with mock.patch.object(Path, "read_bytes", lambda path: b"changed"
                               if path == ROOT / relative else original_read(path)):
            with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                independent_gates._prospective_checker_binding(ROOT, current)
            with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, current)

        relative = "tools/numerical/portable/boolean_rotation_jdi/jdi_bridge.py"
        original_show = subprocess.check_output
        def changed_candidate(command, *args, **kwargs):
            if command[-1] == f"{current}:{relative}":
                return b"changed"
            return original_show(command, *args, **kwargs)
        with mock.patch.object(subprocess, "check_output", changed_candidate):
            with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                independent_gates._prospective_checker_binding(ROOT, current)
            with self.assertRaisesRegex(ValueError, "JDK 21 JDI producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, current)
        for name in ("numeric_producer.py", "numeric_producer_trace.py"):
            relative = f"tools/numerical/portable/{name}"
            local = ROOT / relative
            with self.subTest(path=relative, surface="local"), mock.patch.object(
                    Path, "read_bytes", lambda path, local=local: b"changed"
                    if path == local else original_read(path)):
                with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                    independent_gates._prospective_checker_binding(ROOT, current)
                with self.assertRaisesRegex(ValueError, "JDK 21 JDI producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, current)

            def changed_module(command, *args, **kwargs):
                if command[-1] == f"{current}:{relative}":
                    return b"changed"
                return original_show(command, *args, **kwargs)

            with self.subTest(path=relative, surface="candidate"), mock.patch.object(
                    subprocess, "check_output", changed_module):
                with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                    independent_gates._prospective_checker_binding(ROOT, current)
                with self.assertRaisesRegex(ValueError, "JDK 21 JDI producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, current)

    def test_baseline_compat_window_pins_current_and_published_source(self):
        current = "b133e6e886dc17bff8ad8ccc3654d6538da18da8"
        published = "80808b119ee287d9a7504a0d972962e4d78586aa"
        self.assertEqual(independent_gates.BASELINE_COMPAT_SOURCE_REVISION, current)
        checker = independent_gates._prospective_checker_binding(ROOT, current)
        producer = independent_gates._p2_producer_binding(ROOT, current)
        self.assertEqual(producer,
                         independent_gates.APPROVED_P2_BASELINE_COMPAT_PRODUCERS)
        for relative, digest in independent_gates.BASELINE_COMPAT_CAPTURE_DEPENDENCIES.items():
            with self.subTest(relative=relative):
                committed = subprocess.check_output(
                    ("git", "--no-replace-objects", "show", f"{current}:{relative}"),
                    cwd=ROOT)
                self.assertEqual(digest, hashlib.sha256(committed).hexdigest())
                self.assertEqual(independent_gates.OUTPUT_PROVENANCE_CAPTURE_DEPENDENCIES[
                    relative], hashlib.sha256((ROOT / relative).read_bytes()).hexdigest())
                self.assertEqual(digest, checker[relative])
        old_checker = independent_gates._prospective_checker_binding(ROOT, published)
        old_producer = independent_gates._p2_producer_binding(ROOT, published)
        self.assertEqual(old_producer,
                         independent_gates.APPROVED_P2_PRIVATE_LAUNCH_PRODUCERS)
        self.assertEqual(old_checker["tools/numerical/portable/run.py"],
                         independent_gates.PRIVATE_LAUNCH_CAPTURE_DEPENDENCIES[
                             "tools/numerical/portable/run.py"])
        self.assertNotEqual(old_checker["tools/numerical/portable/run.py"],
                            checker["tools/numerical/portable/run.py"])

        original_read = Path.read_bytes
        original_show = subprocess.check_output
        for relative in ("tools/numerical/portable/run.py",
                         "tools/numerical/portable/actual_capture_receipt.py"):
            local = ROOT / relative
            with self.subTest(relative=relative, side="local"), mock.patch.object(
                    Path, "read_bytes", lambda path, local=local: b"changed"
                    if path == local else original_read(path)):
                with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                    independent_gates._prospective_checker_binding(ROOT, current)
                with self.assertRaisesRegex(
                        ValueError,
                        "reviewed P2 raw producer blob differs|JDK 21 JDI producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, current)

            def changed_candidate(command, *args, **kwargs):
                if command[-1] == f"{current}:{relative}":
                    return b"changed"
                return original_show(command, *args, **kwargs)

            with self.subTest(relative=relative, side="candidate"), mock.patch.object(
                    subprocess, "check_output", changed_candidate):
                with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                    independent_gates._prospective_checker_binding(ROOT, current)
                with self.assertRaisesRegex(
                        ValueError,
                        "reviewed P2 raw producer blob differs|JDK 21 JDI producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, current)

    def test_path_model_window_binds_complete_source_and_rejects_private_intermediates(self):
        revision = independent_gates.PATH_MODEL_SOURCE_REVISION
        checker = independent_gates._prospective_checker_binding(ROOT, revision)
        producer = independent_gates._p2_producer_binding(ROOT, revision)
        self.assertEqual(producer,
                         independent_gates.APPROVED_P2_PATH_MODEL_PRODUCERS)
        self.assertIn("actual_output_v6", independent_gates.PORTABLE_REPLAY_MODULES)
        for relative, digest in independent_gates.PATH_MODEL_CAPTURE_DEPENDENCIES.items():
            with self.subTest(path=relative):
                committed = subprocess.check_output(
                    ["git", "--no-replace-objects", "show", f"{revision}:{relative}"],
                    cwd=ROOT)
                self.assertEqual(digest, hashlib.sha256(committed).hexdigest())
                self.assertEqual(digest, hashlib.sha256((ROOT / relative).read_bytes()).hexdigest())
                self.assertEqual(digest, checker[relative])
        for relative, digest in independent_gates.P2_PATH_MODEL_DEPENDENCIES.items():
            with self.subTest(producer_dependency=relative):
                committed = subprocess.check_output(
                    ["git", "--no-replace-objects", "show", f"{revision}:{relative}"],
                    cwd=ROOT)
                self.assertEqual(digest, hashlib.sha256(committed).hexdigest())
        old_output = "tools/numerical/portable/actual_output_v6.py"
        old_committed = subprocess.check_output(
            ["git", "--no-replace-objects", "show",
             f"{independent_gates.SHARED_WRITER_SOURCE_REVISION}:{old_output}"],
            cwd=ROOT)
        self.assertEqual(independent_gates.OUTPUT_PROVENANCE_CAPTURE_DEPENDENCIES[
            old_output], hashlib.sha256(old_committed).hexdigest())
        for incomplete in (independent_gates.FAILED_OUTPUT_WRAPPER_SOURCE_REVISION,
                           independent_gates.OUTPUT_PROVENANCE_SOURCE_REVISION,
                           "ccd7188bd78a5e2667219d9338bc323d25fac839",
                           independent_gates.OUTPUT_REVIEW_REMEDY_SOURCE_REVISION,
                           independent_gates.SHARED_WRITER_SOURCE_REVISION,
                           "e10a67d2051e0437236ca7c85d9e8f7bd43177b3",
                           independent_gates.OBSERVER_OPERANDS_SOURCE_REVISION,
                           "35c8cbb6973c35922d9a7f9d3374cc13601ad557",
                           "96f21809f68d963c000b114420ab8044a9cf7e03"):
            with self.subTest(incomplete=incomplete):
                with self.assertRaisesRegex(ValueError, "incomplete output source"):
                    independent_gates._prospective_checker_binding(ROOT, incomplete)
                with self.assertRaisesRegex(ValueError, "incomplete output source"):
                    independent_gates._p2_producer_binding(ROOT, incomplete)
        old = independent_gates.BASELINE_COMPAT_SOURCE_REVISION
        self.assertEqual(independent_gates.APPROVED_P2_BASELINE_COMPAT_PRODUCERS,
                         independent_gates._p2_producer_binding(ROOT, old))
        self.assertNotIn("tools/numerical/portable/actual_output_v6.py",
                         independent_gates._prospective_checker_binding(ROOT, old))
        source = "tools/numerical/portable/actual_output_v6.py"
        original_read = Path.read_bytes
        original_show = subprocess.check_output
        with mock.patch.object(Path, "read_bytes", lambda path: b"changed"
                               if path == ROOT / source else original_read(path)):
            with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                independent_gates._prospective_checker_binding(ROOT, revision)
            with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, revision)
        def changed_candidate(command, *args, **kwargs):
            if command[-1] == f"{revision}:{source}":
                return b"changed"
            return original_show(command, *args, **kwargs)
        with mock.patch.object(subprocess, "check_output", changed_candidate):
            with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                independent_gates._prospective_checker_binding(ROOT, revision)
            with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, revision)

    def test_v6_new_capture_modules_reject_local_and_candidate_drift(self):
        reviewed = "0d5799e1c84f76c504b53f3eaf7468bca20a60eb"
        original_read = Path.read_bytes
        original_show = subprocess.check_output
        for name in ("actual_capture_receipt.py", "actual_trace.py"):
            relative = f"tools/numerical/portable/{name}"
            local = ROOT / relative
            with self.subTest(path=relative, surface="local"), mock.patch.object(
                    Path, "read_bytes", lambda path, local=local: b"changed"
                    if path == local else original_read(path)):
                with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                    independent_gates._prospective_checker_binding(ROOT, reviewed)
                with self.assertRaisesRegex(ValueError, "JDK 21 JDI producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, reviewed)

            def altered(command, *args, **kwargs):
                if command[-1] == f"{reviewed}:{relative}":
                    return b"changed"
                return original_show(command, *args, **kwargs)

            with self.subTest(path=relative, surface="candidate"), mock.patch.object(
                    subprocess, "check_output", altered):
                with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                    independent_gates._prospective_checker_binding(ROOT, reviewed)
                with self.assertRaisesRegex(ValueError, "JDK 21 JDI producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, reviewed)

    def test_v6_checker_and_capture_inputs_reject_changed_bytes(self):
        reviewed = independent_gates.PROSPECTIVE_V6_SOURCE_REVISION
        original_read = Path.read_bytes
        original_show = subprocess.check_output
        for name in ("numeric_producer.py", "numeric_producer_trace.py",
                     "numeric_class_witness.py", "class_witness/NumericClassWitness.java"):
            relative = f"tools/numerical/portable/{name}"
            with self.subTest(checker=name, surface="local"), mock.patch.object(
                    Path, "read_bytes", lambda path, target=ROOT / relative: b"changed"
                    if path == target else original_read(path)):
                with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                    independent_gates._prospective_checker_binding(ROOT, reviewed)

            def altered(command, *args, **kwargs):
                if command[-1] == f"{reviewed}:{relative}":
                    return b"changed"
                return original_show(command, *args, **kwargs)

            with self.subTest(checker=name, surface="candidate"), mock.patch.object(
                    subprocess, "check_output", altered):
                with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                    independent_gates._prospective_checker_binding(ROOT, reviewed)

        for relative in (
                "tools/numerical/portable/build.gradle.kts",
                "tools/numerical/portable/boolean_rotation_jdi/RotationJdiProbe.java",
                "tools/numerical/portable/boolean_rotation_jdi/jdi_bridge.py",
                "tools/numerical/portable/src/jvmTest/kotlin/portable/FocusedBooleanArithmeticSourceTest.kt"):
            with self.subTest(input=relative, surface="local"), mock.patch.object(
                    Path, "read_bytes", lambda path, target=ROOT / relative: b"changed"
                    if path == target else original_read(path)):
                with self.assertRaisesRegex(ValueError, "JDK 21 JDI producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, reviewed)

            def altered(command, *args, **kwargs):
                if command[-1] == f"{reviewed}:{relative}":
                    return b"changed"
                return original_show(command, *args, **kwargs)

            with self.subTest(input=relative, surface="candidate"), mock.patch.object(
                    subprocess, "check_output", altered):
                with self.assertRaisesRegex(ValueError, "JDK 21 JDI producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, reviewed)

        with mock.patch.dict(independent_gates.APPROVED_P2_V6_PRODUCERS,
                             {"actual_arithmetic.py": "0" * 64}):
            with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, reviewed)

    def _inspect_capture_boundary(self, producer, stale, scratch, dependencies=None):
        if dependencies is None:
            dependencies = independent_gates.PROSPECTIVE_EXECUTABLE_CAPTURE_DEPENDENCIES
        with mock.patch.object(subprocess, "Popen",
                               side_effect=RuntimeError("blocked process boundary")):
            with self.assertRaisesRegex(RuntimeError, "blocked process boundary"):
                producer.bounded_command(["blocked"], scratch, scratch,
                                         scratch / "bounded.log")
        imported = sys.modules["capture_actual"]
        self.assertIsNot(stale, imported)
        self.assertIsInstance(imported.CaptureBudget, type)
        self.assertEqual(Path(imported.__file__),
                         Path(imported.CaptureBudget.__init__.__code__.co_filename))
        self.assertEqual(Path(imported.__file__),
                         Path(imported.run_bounded_process.__code__.co_filename))
        loaded = {}
        for relative, expected in dependencies.items():
            name = relative.removeprefix("tools/numerical/portable/").removesuffix(
                ".py").replace("/", ".")
            module = importlib.import_module(name)
            path = Path(module.__file__)
            loaded[name] = (path, hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(expected, loaded[name][1], name)
        return loaded

    def test_exported_checker_ignores_stale_numeric_helpers_and_restores_cache_on_failure(self):
        revision = "fbaee1b16de2ff0633e2981e69cf59044b61c745"
        names = ("numeric_producer", "numeric_producer_trace", "numeric_class_witness",
                 "pulley_jdi_v2", "pulley_jdi_v1", "pulley_jdi_inputs_v2", "run",
                 "frozen_weld_pulley", "exact_consistency", "physical", "compare")
        stale = {name: types.ModuleType(name) for name in names + CAPTURE_REPLAY_NAMES}
        stale["capture_actual"] = changed_capture_actual()
        stale["pulley_jdi_v2"].Reader = lambda raw: self.fail("cached Reader was used")
        stale["compare"].compare_value = lambda *args: self.fail("cached compare was used")
        receipt = {"prospective_catalog_sha256": independent_gates.PROSPECTIVE_POLICY_SHA256,
                   "prospective_cases": [
                       {"id": case, "reference": "missing.jsonl", "candidate": "missing.jsonl",
                        "capture_receipt": "missing.json", "arithmetic_audit": "missing-audit.json"}
                       for case in independent_gates.approved_prospective_cases(str(ROOT))]}
        original_import = builtins.__import__
        loaded = {}
        capture_loaded = {}
        inspected = False

        def inspect_import(name, *args, **kwargs):
            nonlocal inspected
            module = original_import(name, *args, **kwargs)
            if name == "prospective_compare" and not inspected:
                inspected = True
                producer = original_import("numeric_producer")
                with self.assertRaisesRegex(ValueError, "class file is truncated"):
                    producer.verify_call_edge(b"")
                capture_loaded.update(self._inspect_capture_boundary(
                    producer, stale["capture_actual"], Path(temporary)))
                for helper in names:
                    imported = original_import(helper)
                    source = Path(imported.__file__)
                    loaded[helper] = (source, hashlib.sha256(source.read_bytes()).hexdigest())
                self.assertIs(sys.modules["compare"],
                              sys.modules["reference_diagnostic"].approved)
                self.assertIsNot(stale["compare"], sys.modules["compare"])
            return module

        prior_path = list(sys.path)
        with tempfile.TemporaryDirectory() as temporary:
            ambient, marker = changed_ambient_comparator(Path(temporary))
            with mock.patch.dict(sys.modules, stale), mock.patch.object(
                    builtins, "__import__", inspect_import), mock.patch.object(
                    sys, "path", [str(ambient), *sys.path]):
                with self.assertRaisesRegex(ValueError, "raw archive file is missing"):
                    independent_gates.verify_prospective_case_subgates(
                        Path(temporary), receipt, ROOT, revision,
                        {"dyn4k-core": "a" * 64},
                        independent_gates.verified_numerical_source_sha256(ROOT, revision))
                self.assertFalse(marker.exists(), "changed ambient comparator executed")
                self.assertEqual(set(names), set(loaded))
                for name in names:
                    self.assertIn("dyn4k-prospective-checker-", str(loaded[name][0]))
                    expected = (independent_gates.APPROVED_PROSPECTIVE_EXECUTABLE_SHARED[
                        "tools/numerical/compare.py"] if name == "compare" else
                        independent_gates.APPROVED_PROSPECTIVE_EXECUTABLE_CHECKERS[f"{name}.py"])
                    self.assertEqual(expected, loaded[name][1], name)
                    self.assertIs(stale[name], sys.modules[name])
                self.assertEqual({relative.removeprefix("tools/numerical/portable/")
                                  .removesuffix(".py").replace("/", ".") for relative in
                                  independent_gates.PROSPECTIVE_EXECUTABLE_CAPTURE_DEPENDENCIES},
                                 set(capture_loaded))
                for name, (path, digest) in capture_loaded.items():
                    self.assertIn("dyn4k-prospective-checker-", str(path), name)
                    self.assertEqual(independent_gates.PROSPECTIVE_EXECUTABLE_CAPTURE_DEPENDENCIES[
                        "tools/numerical/portable/" + name.replace(".", "/") + ".py"], digest)
                for name in CAPTURE_REPLAY_NAMES:
                    self.assertIs(stale[name], sys.modules[name])
                self.assertEqual([str(ambient), *prior_path], sys.path)
            self.assertFalse(marker.exists())
        self.assertEqual(prior_path, sys.path)

    def test_p2_host_ignores_stale_numeric_helpers_and_restores_cache_on_success(self):
        revision = independent_gates.PROSPECTIVE_REPLAY_SCRATCH_REVISION
        current_capture_python = {
            path: digest for path, digest in
            independent_gates.PATH_MODEL_CAPTURE_DEPENDENCIES.items()
            if path.endswith(".py")}
        names = ("numeric_producer", "numeric_producer_trace", "numeric_class_witness",
                 "pulley_jdi_v2", "pulley_jdi_v1", "pulley_jdi_inputs_v2", "run",
                 "frozen_weld_pulley", "exact_consistency", "physical", "compare")
        stale = {name: types.ModuleType(name) for name in names + CAPTURE_REPLAY_NAMES}
        stale["capture_actual"] = changed_capture_actual()
        stale["pulley_jdi_v2"].Reader = lambda raw: self.fail("cached Reader was used")
        stale["compare"].compare_value = lambda *args: self.fail("cached compare was used")
        source = "a" * 64
        artifact = "b" * 64
        original_import = builtins.__import__
        loaded = {}
        capture_loaded = {}
        inspected = False

        def inspect_import(name, *args, **kwargs):
            nonlocal inspected
            module = original_import(name, *args, **kwargs)
            if name == "prospective_compare" and not inspected:
                inspected = True
                producer = original_import("numeric_producer")
                with self.assertRaisesRegex(ValueError, "class file is truncated"):
                    producer.verify_call_edge(b"")
                capture_loaded.update(self._inspect_capture_boundary(
                    producer, stale["capture_actual"], root,
                    current_capture_python))
                for helper in names:
                    imported = original_import(helper)
                    loaded[helper] = Path(imported.__file__)
                self.assertIs(sys.modules["compare"],
                              sys.modules["reference_diagnostic"].approved)
                self.assertIsNot(stale["compare"], sys.modules["compare"])
                module.compare_host = lambda *unused, **options: {
                    "candidate_source_sha256": source,
                    "candidate_artifact_sha256": {"target": artifact},
                    "baseline_attestation_sha256": sidecar_sha}
            return module

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ambient, marker = changed_ambient_comparator(root)
            for relative in ("baseline", "candidate/jvm", "arithmetic"):
                (root / relative).mkdir(parents=True)
            sidecar = root / "sidecar.json"
            sidecar.write_bytes(b"synthetic cache control")
            sidecar_sha = hashlib.sha256(sidecar.read_bytes()).hexdigest()
            runtime = {"host": "jvm", "os": "test-host", "machine": "x86_64",
                       "device": False, "executable": str(root / "jdk21/bin/java"),
                       "executable_sha256": "c" * 64,
                       "version": 'openjdk version "21.0.1"',
                       "method_executions": 15, "dependency_sha256": artifact,
                       "method_process_sha256": "d" * 64}
            (root / "candidate/jvm/receipt.json").write_text(json.dumps({"runtime": runtime}))
            prior_path = list(sys.path)
            with mock.patch.dict(sys.modules, stale), mock.patch.object(
                    builtins, "__import__", inspect_import), mock.patch.object(
                    sys, "path", [str(ambient), *sys.path]):
                summary, case_order, case_methods, identity = independent_gates._verify_p2_host(
                    root, {"baseline": "baseline", "candidate": "candidate",
                           "arithmetic": "arithmetic"}, sidecar, ROOT, revision, source, artifact)
                self.assertFalse(marker.exists(), "changed ambient comparator executed")
                self.assertEqual(source, summary["candidate_source_sha256"])
                self.assertEqual(independent_gates.PROSPECTIVE_CASE_COUNT, len(case_order))
                self.assertEqual(set(case_order), set(case_methods))
                self.assertEqual(independent_gates._p2_runtime_identity(runtime), identity)
                self.assertEqual(set(names), set(loaded))
                self.assertEqual({relative.removeprefix("tools/numerical/portable/")
                                  .removesuffix(".py").replace("/", ".") for relative in
                                  current_capture_python},
                                 set(capture_loaded))
                for name, (path, digest) in capture_loaded.items():
                    self.assertEqual(ROOT / "tools/numerical/portable" /
                                     (name.replace(".", "/") + ".py"), path)
                    self.assertEqual(current_capture_python[
                        "tools/numerical/portable/" + name.replace(".", "/") + ".py"], digest)
                for name in names:
                    relative = (f"tools/numerical/{name}.py" if name == "compare" else
                                f"tools/numerical/portable/{name}.py")
                    self.assertEqual(ROOT / relative, loaded[name])
                    self.assertIs(stale[name], sys.modules[name])
                for name in CAPTURE_REPLAY_NAMES:
                    self.assertIs(stale[name], sys.modules[name])
                self.assertEqual([str(ambient), *prior_path], sys.path)
                with mock.patch.object(independent_gates.shutil, "copytree",
                                       side_effect=ValueError("forced replay rejection")):
                    with self.assertRaisesRegex(ValueError, "forced replay rejection"):
                        independent_gates._verify_p2_host(
                            root, {"baseline": "baseline", "candidate": "candidate",
                                   "arithmetic": "arithmetic"}, sidecar, ROOT, revision,
                            source, artifact)
                for name in names:
                    self.assertIs(stale[name], sys.modules[name])
                for name in CAPTURE_REPLAY_NAMES:
                    self.assertIs(stale[name], sys.modules[name])
                self.assertEqual([str(ambient), *prior_path], sys.path)
                self.assertFalse(marker.exists())
            self.assertFalse(marker.exists())
            self.assertEqual(prior_path, sys.path)

    def test_prospective_checker_pins_historical_and_assembled_source(self):
        current = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                          cwd=ROOT, text=True).strip()
        windows = (
            (independent_gates.PROSPECTIVE_HISTORICAL_POLICY_REVISION,
             independent_gates.APPROVED_PROSPECTIVE_POLICY_CHECKERS),
            (independent_gates.PROSPECTIVE_INVENTORY_FIX_CHECKER_REVISION,
             independent_gates.APPROVED_PROSPECTIVE_INVENTORY_FIX_CHECKERS),
            (independent_gates.PROSPECTIVE_ASSEMBLED_CHECKER_REVISION,
             independent_gates.APPROVED_PROSPECTIVE_ASSEMBLED_CHECKERS),
            ("0533142a1358b2eebb3c3f36ae3dc1a8b01d9667",
             independent_gates.APPROVED_PROSPECTIVE_ASSEMBLED_CHECKERS),
            (independent_gates.PROSPECTIVE_BRIDGE_CHECKER_REVISION,
             independent_gates.APPROVED_PROSPECTIVE_CHECKERS),
            (independent_gates.PROSPECTIVE_CHECKER_REVISION,
             independent_gates.APPROVED_PROSPECTIVE_CHECKERS),
            (independent_gates.PROSPECTIVE_POLICY_REVISION,
             independent_gates.APPROVED_PROSPECTIVE_CHECKERS),
            ("7d319d5027f2b10c11eae7f4574e6edf407449c0",
             independent_gates.APPROVED_PROSPECTIVE_CHECKERS),
            ("68339377a5d8dff1fd3dd6bf1ab17a32a0a402cd",
             independent_gates.APPROVED_PROSPECTIVE_SIGNED_ZERO_CHECKERS),
            ("dcc8211b51aad7bcb946417ad9019bd57cc6ecf1",
             independent_gates.APPROVED_PROSPECTIVE_REPRESENTED_CHECKERS),
            (current, independent_gates.APPROVED_PROSPECTIVE_BASELINE_COMPAT_CHECKERS),
        )
        checker_paths = [f"tools/numerical/portable/{name}" for name in
                         independent_gates.APPROVED_PROSPECTIVE_CHECKERS]
        checker_paths.append(independent_gates.PROSPECTIVE_POLICY_PATH)
        checkout_bound = checkout_matches_commit(checker_paths)
        for revision, blobs in windows:
            with self.subTest(revision=revision):
                if checkout_bound:
                    independent_gates._prospective_checker_binding(ROOT, revision)
                else:
                    with self.assertRaisesRegex(ValueError,
                                                "prospective policy/checker blob differs"):
                        independent_gates._prospective_checker_binding(ROOT, revision)
                for filename, approved in blobs.items():
                    path = f"tools/numerical/portable/{filename}"
                    self.assertEqual(approved, hashlib.sha256(subprocess.check_output(
                        ["git", "show", f"{revision}:{path}"], cwd=ROOT)).hexdigest())
        with self.assertRaisesRegex(ValueError, "predates approved revisions"):
            independent_gates._prospective_checker_binding(ROOT, BASE)
        with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
            independent_gates._source_binding(
                ROOT, independent_gates.PROSPECTIVE_BRIDGE_CHECKER_REVISION,
                {f"tools/numerical/portable/{name}": value
                 for name, value in independent_gates.APPROVED_P2_PRODUCERS.items()},
                "reviewed P2 raw producer")
        with mock.patch.dict(independent_gates.APPROVED_PROSPECTIVE_ASSEMBLED_CHECKERS,
                             {"cases.py": "0" * 64}):
            with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                independent_gates._prospective_checker_binding(
                    ROOT, independent_gates.PROSPECTIVE_ASSEMBLED_CHECKER_REVISION)
            if checkout_bound:
                independent_gates._prospective_checker_binding(ROOT, current)
        with mock.patch.dict(independent_gates.APPROVED_PROSPECTIVE_POLICY_CHECKERS,
                             {"cases.py": "0" * 64}):
            with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                independent_gates._prospective_checker_binding(
                    ROOT, independent_gates.PROSPECTIVE_HISTORICAL_POLICY_REVISION)
            if checkout_bound:
                independent_gates._prospective_checker_binding(
                    ROOT, independent_gates.PROSPECTIVE_ASSEMBLED_CHECKER_REVISION)
        with mock.patch.dict(independent_gates.APPROVED_PROSPECTIVE_CHECKERS,
                             {"prospective_compare.py": "0" * 64}):
            with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                independent_gates._prospective_checker_binding(
                    ROOT, "7d319d5027f2b10c11eae7f4574e6edf407449c0")
        with mock.patch.dict(independent_gates.APPROVED_PROSPECTIVE_SIGNED_ZERO_CHECKERS,
                             {"prospective_compare.py": "0" * 64}):
            with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                independent_gates._prospective_checker_binding(
                    ROOT, "68339377a5d8dff1fd3dd6bf1ab17a32a0a402cd")
        with mock.patch.dict(independent_gates.APPROVED_PROSPECTIVE_REPRESENTED_CHECKERS,
                             {"prospective_compare.py": "0" * 64}):
            with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                independent_gates._prospective_checker_binding(
                    ROOT, "dcc8211b51aad7bcb946417ad9019bd57cc6ecf1")
            if checkout_bound:
                independent_gates._prospective_checker_binding(ROOT, current)

    def test_represented_checker_revision_binds_exact_current_and_historical_bytes(self):
        current = "2bd0d70f36b521949641a5404bdb3fa5890f61d3"
        relative = "tools/numerical/portable/prospective_compare.py"
        expected = "469c23f619b5b37ab79fc75d7b73328aae122d712104bbe094cf2357eda1cd07"
        self.assertEqual(current, independent_gates.PROSPECTIVE_REPRESENTED_CHECKER_REVISION)
        self.assertEqual(expected, independent_gates.APPROVED_PROSPECTIVE_REPRESENTED_CHECKERS[
            "prospective_compare.py"])
        committed = subprocess.check_output(
            ["git", "--no-replace-objects", "show", f"{current}:{relative}"], cwd=ROOT)
        self.assertEqual(expected, hashlib.sha256(committed).hexdigest())
        self.assertEqual(independent_gates.APPROVED_PROSPECTIVE_JVM8_CHECKERS[
            "prospective_compare.py"], hashlib.sha256((ROOT / relative).read_bytes()).hexdigest())
        self.assertEqual(expected, independent_gates._prospective_checker_binding(
            ROOT, current)[relative])
        self.assertEqual(independent_gates.APPROVED_PROSPECTIVE_SIGNED_ZERO_CHECKERS[
            "prospective_compare.py"], independent_gates._prospective_checker_binding(
                ROOT, "4a15c77771d7cb65f0bfd303770b58c1afba29ef")[relative])
        original_read = Path.read_bytes
        local = ROOT / relative
        with mock.patch.object(Path, "read_bytes", lambda path_value: b"altered"
                               if path_value == local else original_read(path_value)):
            with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                independent_gates._prospective_checker_binding(ROOT, current)
        original_show = subprocess.check_output

        def altered_committed(command, *args, **kwargs):
            raw = original_show(command, *args, **kwargs)
            if "show" in command and f"{current}:{relative}" in command:
                return raw + b"altered"
            return raw

        with mock.patch.object(subprocess, "check_output", altered_committed):
            with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                independent_gates._prospective_checker_binding(ROOT, current)

    def test_jvm8_source_window_binds_exact_current_files_and_preserves_history(self):
        boundary = "b5159c3e769eb360fa69223d27d3b76b1a70e5f1"
        expected = {
            "prospective_compare.py": "7797931a7a0564933b00e9c6fc8e5e31e4254d2f15dbaf7fe32b865f85ed8095",
            "numeric_producer.py": "544fdd91a42cb2dc2b083fc9b14068d0f137a8bb36f92c033cf2f3c6d24a6352",
            "numeric_producer_trace.py": "357d7707f720f6a2f0e17304a687a45c7951a7b1cafddf4b27c971c3583e6d5f",
            "numeric_class_witness.py": "e528d55644ff793a79e89cdcb6365e119da074ecb9c2a79ac9d979f4e3411858",
            "run.py": "2f53b8baed1907370b16b0ce48dbe039c396445f27c74c5f843e7ca06650c01b",
            "class_witness/NumericClassWitness.java": "1bed2d631df60b6db97dc3cbdd8903917ccff234455ebafcc03808978321d564",
        }
        self.assertEqual(boundary, independent_gates.PROSPECTIVE_JVM8_SOURCE_REVISION)
        self.assertEqual(expected, {name: independent_gates.APPROVED_PROSPECTIVE_JVM8_CHECKERS[name]
                                    for name in expected})
        self.assertEqual(25, len(independent_gates._prospective_checker_binding(ROOT, boundary)) - 1)
        for name, digest in expected.items():
            relative = f"tools/numerical/portable/{name}"
            self.assertEqual(digest, hashlib.sha256(subprocess.check_output(
                ["git", "--no-replace-objects", "show", f"{boundary}:{relative}"], cwd=ROOT)).hexdigest())
        self.assertEqual(expected["run.py"], independent_gates._p2_producer_binding(
            ROOT, boundary)["run.py"])
        self.assertEqual(independent_gates.PROSPECTIVE_REPLAY_SCRATCH_CHECKERS[
            "numeric_producer.py"], independent_gates._prospective_checker_binding(
                ROOT, independent_gates.PROSPECTIVE_REPLAY_SCRATCH_REVISION)[
                    "tools/numerical/portable/numeric_producer.py"])
        for revision in ("b17bb126", "344498f4", "4ae45cb2", "d2b5062d"):
            with self.subTest(intermediate=revision), self.assertRaises(ValueError):
                independent_gates._prospective_checker_binding(ROOT, revision)

    def test_jvm8_source_window_rejects_unknown_shadowed_and_changed_links(self):
        candidate = independent_gates.PROSPECTIVE_JVM8_SOURCE_REVISION
        with self.assertRaisesRegex(ValueError, "ancestry is unavailable"):
            independent_gates._prospective_checker_binding(ROOT, "0" * 40)
        with self.assertRaisesRegex(ValueError, "ancestry is unavailable"):
            independent_gates._p2_producer_binding(ROOT, "0" * 40)

        original_read = Path.read_bytes
        original_show = subprocess.check_output
        for relative in ("tools/numerical/portable/prospective_compare.py",
                         "tools/numerical/portable/numeric_producer.py",
                         "tools/numerical/portable/boolean_rotation_jdi/jdi_bridge.py"):
            local = ROOT / relative
            with self.subTest(relative=relative, surface="local"), mock.patch.object(
                    Path, "read_bytes", lambda path, local=local: b"shadowed"
                    if path == local else original_read(path)):
                with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                    independent_gates._prospective_checker_binding(ROOT, candidate)

            def changed(command, *args, **kwargs):
                if command[-1] == f"{candidate}:{relative}":
                    return b"changed"
                return original_show(command, *args, **kwargs)

            with self.subTest(relative=relative, surface="committed"), mock.patch.object(
                    subprocess, "check_output", changed):
                with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                    independent_gates._prospective_checker_binding(ROOT, candidate)

        run = "tools/numerical/portable/run.py"
        with mock.patch.object(Path, "read_bytes", lambda path: b"shadowed"
                               if path == ROOT / run else original_read(path)):
            with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, candidate)

    def test_jvm8_agent_classpath_repair_has_its_own_exact_source_window(self):
        boundary = "4ec6a2dbb847bbc6fd18374225b12f7cc802d969"
        previous = independent_gates.PROSPECTIVE_JVM8_SOURCE_REVISION
        name = "numeric_producer.py"
        relative = f"tools/numerical/portable/{name}"
        digest = "2e5f80022e4457955e1f806d5ba7270eec9041726914fd245033e106b06ab3e5"
        self.assertEqual(boundary, independent_gates.PROSPECTIVE_JVM8_AGENT_SOURCE_REVISION)
        self.assertEqual(digest, independent_gates.APPROVED_PROSPECTIVE_JVM8_AGENT_CHECKERS[name])
        self.assertEqual(digest, hashlib.sha256(subprocess.check_output(
            ["git", "--no-replace-objects", "show", f"{boundary}:{relative}"], cwd=ROOT)).hexdigest())
        self.assertEqual(digest, independent_gates._prospective_checker_binding(ROOT, boundary)[relative])
        self.assertEqual(independent_gates.APPROVED_PROSPECTIVE_JVM8_CHECKERS[name],
                         independent_gates._prospective_checker_binding(ROOT, previous)[relative])
        self.assertEqual(independent_gates.APPROVED_PROSPECTIVE_JVM8_CHECKERS[name],
                         independent_gates._prospective_checker_binding(ROOT, "ecea01e9")[relative])
        self.assertEqual(25, len(independent_gates._prospective_checker_binding(ROOT, boundary)) - 1)

        original_show = subprocess.check_output
        def altered(command, *args, **kwargs):
            if command[-1] == f"{boundary}:{relative}":
                return b"changed"
            return original_show(command, *args, **kwargs)
        with mock.patch.object(subprocess, "check_output", altered):
            with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                independent_gates._prospective_checker_binding(ROOT, boundary)

    def test_jvm8_public_source_admission_reaches_raw_gate(self):
        candidate = independent_gates.PROSPECTIVE_JVM8_SOURCE_REVISION
        receipt = {"prospective_catalog_sha256": independent_gates.PROSPECTIVE_POLICY_SHA256,
                   "prospective_cases": [
                       {"id": case, "reference": "missing.jsonl", "candidate": "missing.jsonl",
                        "capture_receipt": "missing.json", "arithmetic_audit": "missing-audit.json"}
                       for case in independent_gates.approved_prospective_cases(str(ROOT))]}
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "raw archive file is missing"):
                independent_gates.verify_prospective_case_subgates(
                    Path(temporary), receipt, ROOT, candidate, {"dyn4k-core": "a" * 64},
                    independent_gates.verified_numerical_source_sha256(ROOT, candidate))

    def test_numeric_probe_checker_window_preserves_historical_hashes(self):
        relative = "tools/numerical/portable/prospective_compare.py"
        current = "375812a97de8cb3e439fc2a204e029de1a6de338"
        previous = "dcc8211b51aad7bcb946417ad9019bd57cc6ecf1"
        old_digest = "469c23f619b5b37ab79fc75d7b73328aae122d712104bbe094cf2357eda1cd07"
        new_digest = "2d254d2f2d5117ed81449000beb0c3373822af80d49424605c390ee83c90aeeb"
        self.assertEqual(current, independent_gates.PROSPECTIVE_NUMERIC_PROBE_CHECKER_REVISION)
        self.assertEqual(old_digest, independent_gates.APPROVED_PROSPECTIVE_REPRESENTED_CHECKERS[
            "prospective_compare.py"])
        self.assertEqual({**independent_gates.APPROVED_PROSPECTIVE_REPRESENTED_CHECKERS,
                          "prospective_compare.py": new_digest},
                         independent_gates.APPROVED_PROSPECTIVE_NUMERIC_PROBE_CHECKERS)
        self.assertEqual(independent_gates.APPROVED_PROSPECTIVE_BASELINE_COMPAT_CHECKERS,
                         independent_gates.PINNED_PROSPECTIVE_LOCAL_CHECKERS)
        for revision, digest in ((current, new_digest),
                                 (previous, old_digest),
                                 (independent_gates.PROSPECTIVE_REPRESENTED_CHECKER_REVISION,
                                  old_digest),
                                 ("4a15c77771d7cb65f0bfd303770b58c1afba29ef",
                                  independent_gates.APPROVED_PROSPECTIVE_SIGNED_ZERO_CHECKERS[
                                      "prospective_compare.py"])):
            with self.subTest(revision=revision):
                bound = independent_gates._prospective_checker_binding(ROOT, revision)
                self.assertEqual(digest, bound[relative])
                self.assertEqual(independent_gates.PROSPECTIVE_POLICY_SHA256,
                                 bound[independent_gates.PROSPECTIVE_POLICY_PATH])

        original_show = subprocess.check_output
        old_bytes = original_show(["git", "--no-replace-objects", "show",
                                   f"{previous}:{relative}"], cwd=ROOT)
        new_bytes = original_show(["git", "--no-replace-objects", "show",
                                   f"{current}:{relative}"], cwd=ROOT)
        self.assertEqual(old_digest, hashlib.sha256(old_bytes).hexdigest())
        self.assertEqual(new_digest, hashlib.sha256(new_bytes).hexdigest())
        for revision, replacement in ((current, old_bytes), (previous, new_bytes),
                                      (current, new_bytes + b"\n# altered\n")):
            def wrong_committed(command, *args, **kwargs):
                if "show" in command and f"{revision}:{relative}" in command:
                    return replacement
                return original_show(command, *args, **kwargs)

            with self.subTest(wrong_lineage=revision), mock.patch.object(
                    subprocess, "check_output", wrong_committed):
                with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                    independent_gates._prospective_checker_binding(ROOT, revision)

        original_read = Path.read_bytes
        for filename in independent_gates.APPROVED_PROSPECTIVE_CHECKERS:
            path = ROOT / "tools/numerical/portable" / filename

            def stale_local(target):
                return b"stale" if target == path else original_read(target)

            with self.subTest(stale_local=filename), mock.patch.object(
                    Path, "read_bytes", stale_local):
                with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                    independent_gates._prospective_checker_binding(ROOT, current)

            def missing_local(target):
                if target == path:
                    raise FileNotFoundError(target)
                return original_read(target)

            with self.subTest(missing_local=filename), mock.patch.object(
                    Path, "read_bytes", missing_local):
                with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                    independent_gates._prospective_checker_binding(ROOT, current)

            def missing_committed(command, *args, **kwargs):
                if "show" in command and f"{current}:tools/numerical/portable/{filename}" in command:
                    raise subprocess.CalledProcessError(1, command)
                return original_show(command, *args, **kwargs)

            with self.subTest(missing_committed=filename), mock.patch.object(
                    subprocess, "check_output", missing_committed):
                with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                    independent_gates._prospective_checker_binding(ROOT, current)

        for filename, copied in (("prospective_compare.py", old_digest),
                                 ("cases.py", "0" * 64)):
            with self.subTest(copied_hash=filename), mock.patch.dict(
                    independent_gates.APPROVED_PROSPECTIVE_NUMERIC_PROBE_CHECKERS,
                    {filename: copied}):
                with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                    independent_gates._prospective_checker_binding(ROOT, current)

    def test_inventory_fix_checker_window_preserves_numeric_probe_bytes(self):
        relative = "tools/numerical/portable/prospective_compare.py"
        inventory_revision = "df316d8900f850d22f9c933f6aac8250b1e10ed1"
        numeric_revision = "375812a97de8cb3e439fc2a204e029de1a6de338"
        numeric_digest = "2d254d2f2d5117ed81449000beb0c3373822af80d49424605c390ee83c90aeeb"
        inventory_digest = "ff7a428ff4fc39ad7ef1e77b605c1ffd39ef138bdc62599e416a4a0b9e80ae83"
        self.assertEqual(inventory_revision,
                         independent_gates.PROSPECTIVE_INVENTORY_FIX_CHECKER_REVISION)
        self.assertEqual(numeric_digest,
                         independent_gates.APPROVED_PROSPECTIVE_NUMERIC_PROBE_CHECKERS[
                             "prospective_compare.py"])
        self.assertEqual({**independent_gates.APPROVED_PROSPECTIVE_NUMERIC_PROBE_CHECKERS,
                          "prospective_compare.py": inventory_digest},
                         independent_gates.APPROVED_PROSPECTIVE_INVENTORY_FIX_CHECKERS)
        for revision, digest in ((inventory_revision, inventory_digest),
                                 ("HEAD", independent_gates.APPROVED_PROSPECTIVE_JVM8_CHECKERS[
                                     "prospective_compare.py"]),
                                 (numeric_revision, numeric_digest)):
            with self.subTest(revision=revision):
                self.assertEqual(digest, independent_gates._prospective_checker_binding(
                    ROOT, revision)[relative])

        original_show = subprocess.check_output
        old_bytes = original_show(["git", "--no-replace-objects", "show",
                                   f"{numeric_revision}:{relative}"], cwd=ROOT)
        new_bytes = original_show(["git", "--no-replace-objects", "show",
                                   f"{inventory_revision}:{relative}"], cwd=ROOT)
        self.assertEqual(numeric_digest, hashlib.sha256(old_bytes).hexdigest())
        self.assertEqual(inventory_digest, hashlib.sha256(new_bytes).hexdigest())

        def wrong_historical_bytes(command, *args, **kwargs):
            if "show" in command and f"{numeric_revision}:{relative}" in command:
                return new_bytes
            return original_show(command, *args, **kwargs)

        with mock.patch.object(subprocess, "check_output", wrong_historical_bytes):
            with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                independent_gates._prospective_checker_binding(ROOT, numeric_revision)

    def test_prospective_catalog_binding_keeps_historical_and_current_windows(self):
        path = independent_gates.PROSPECTIVE_POLICY_PATH
        historical_revision = "7213238591db1611da86cdec075978190ca6d52f"
        previous_revision = "e038c334caa07a1547b86839f5d467c5f73ec708"
        current_revision = "83914cfc86f3add09ea65c89dc5b3e6035f709a0"
        historical_sha = "5c8e2ca48a2128b99b2f52188f0f556c3dad3030bde00975bc80d2a25b0c74bb"
        previous_sha = "1b80b7c198d510ab16784348661053a4bde6507548f5ec12d4a460287ec7b484"
        current_sha = "fab269814476a5a0c1d65f268f6c4177bb942ea8e7cdf1ea5ab8d4d9dcd2e160"
        self.assertEqual(current_revision, independent_gates.PROSPECTIVE_POLICY_REVISION)
        self.assertEqual(current_sha, independent_gates.PROSPECTIVE_POLICY_SHA256)
        self.assertEqual(current_sha, hashlib.sha256((ROOT / path).read_bytes()).hexdigest())
        current_catalog = independent_gates.approved_prospective_catalog(str(ROOT))
        self.assertEqual(318, len(current_catalog["cases"]))
        self.assertEqual(566, len(current_catalog["paths"]))
        self.assertEqual(92, len(current_catalog["path_sets"]))
        self.assertEqual("UNPASSED", current_catalog["qualification"])
        historical_bytes = subprocess.check_output(
            ["git", "--no-replace-objects", "show", f"{historical_revision}:{path}"], cwd=ROOT)
        historical_catalog = json.loads(historical_bytes)
        previous_catalog = json.loads(subprocess.check_output(
            ["git", "--no-replace-objects", "show", f"{previous_revision}:{path}"], cwd=ROOT))
        changed_fields = {key for key in current_catalog
                          if current_catalog[key] != historical_catalog[key]}
        self.assertEqual({"baseline_trace_sha256", "baseline_fixture_source_sha256"},
                         changed_fields)
        self.assertEqual({"baseline_fixture_source_sha256"},
                         {key for key in current_catalog
                          if current_catalog[key] != previous_catalog[key]})
        for revision, expected in ((historical_revision, historical_sha),
                                   (f"{previous_revision}^", historical_sha),
                                   (previous_revision, previous_sha),
                                   (f"{current_revision}^", previous_sha),
                                   (current_revision, current_sha)):
            with self.subTest(revision=revision):
                committed = subprocess.check_output(
                    ["git", "--no-replace-objects", "show", f"{revision}:{path}"], cwd=ROOT)
                self.assertEqual(expected, hashlib.sha256(committed).hexdigest())
                self.assertEqual(expected,
                                 independent_gates._prospective_checker_binding(ROOT, revision)[path])
                self.assertEqual(json.loads(committed),
                                 independent_gates.approved_prospective_catalog(
                                     str(ROOT), revision))
        with mock.patch.object(independent_gates, "PROSPECTIVE_POLICY_SHA256", historical_sha):
            with self.assertRaisesRegex(ValueError, "adopted prospective policy catalog differs"):
                independent_gates.approved_prospective_catalog.cache_clear()
                independent_gates.approved_prospective_catalog(str(ROOT))
        independent_gates.approved_prospective_catalog.cache_clear()
        with mock.patch.object(independent_gates, "PROSPECTIVE_HISTORICAL_POLICY_SHA256", current_sha):
            with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                independent_gates._prospective_checker_binding(ROOT, historical_revision)
        with mock.patch.object(independent_gates, "PROSPECTIVE_POLICY_SHA256", historical_sha):
            with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                independent_gates._prospective_checker_binding(ROOT, current_revision)
        with mock.patch.object(independent_gates, "PROSPECTIVE_PREVIOUS_POLICY_SHA256", historical_sha):
            with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                independent_gates._prospective_checker_binding(ROOT, previous_revision)
        original_check_output = subprocess.check_output

        def stale_reference(command, *args, **kwargs):
            if "show" in command and f"{current_revision}:{path}" in command:
                return historical_bytes
            return original_check_output(command, *args, **kwargs)

        with mock.patch.object(subprocess, "check_output", stale_reference):
            with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                independent_gates._prospective_checker_binding(ROOT, current_revision)
        original_read_bytes = Path.read_bytes

        def altered_catalog(file):
            raw = original_read_bytes(file)
            return raw + b" " if file == ROOT / path else raw

        with mock.patch.object(Path, "read_bytes", altered_catalog):
            with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                independent_gates._prospective_checker_binding(ROOT, current_revision)

    def test_prospective_receipt_catalog_follows_candidate_source_window(self):
        revisions = (
            ("7213238591db1611da86cdec075978190ca6d52f",
             "5c8e2ca48a2128b99b2f52188f0f556c3dad3030bde00975bc80d2a25b0c74bb"),
            ("e038c334caa07a1547b86839f5d467c5f73ec708",
             "1b80b7c198d510ab16784348661053a4bde6507548f5ec12d4a460287ec7b484"),
            ("83914cfc86f3add09ea65c89dc5b3e6035f709a0",
             "fab269814476a5a0c1d65f268f6c4177bb942ea8e7cdf1ea5ab8d4d9dcd2e160"),
        )
        identities = independent_gates.approved_prospective_cases(str(ROOT))
        rows = [{"id": case, "reference": "missing.jsonl", "candidate": "missing.jsonl",
                 "capture_receipt": "missing.json", "arithmetic_audit": "missing-audit.json"}
                for case in identities]
        with tempfile.TemporaryDirectory() as temporary:
            for revision, expected in revisions:
                with self.subTest(revision=revision):
                    receipt = {"prospective_cases": rows,
                               "prospective_catalog_sha256": expected}
                    with self.assertRaisesRegex(ValueError, "raw archive file is missing"):
                        independent_gates.verify_prospective_case_subgates(
                            Path(temporary), receipt, ROOT, revision,
                            {"dyn4k-core": "a" * 64}, "b" * 64)
                    receipt["prospective_catalog_sha256"] = "0" * 64
                    with self.assertRaisesRegex(ValueError, "adopted prospective catalog identity differs"):
                        independent_gates.verify_prospective_case_subgates(
                            Path(temporary), receipt, ROOT, revision,
                            {"dyn4k-core": "a" * 64}, "b" * 64)

    def test_reviewed_p2_source_blobs_are_pinned_to_approved_revision(self):
        historical = independent_gates.PROSPECTIVE_CHECKER_REVISION
        revision = independent_gates.P2_CLASS_LOAD_REVISION
        self.assertEqual("5b750850277a6e9d494483dc5fa2791b6d292233", revision)
        current = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                          cwd=ROOT, text=True).strip()
        checker_paths = [f"tools/numerical/portable/{name}" for name in
                         independent_gates.APPROVED_PROSPECTIVE_CHECKERS]
        checker_paths.append(independent_gates.PROSPECTIVE_POLICY_PATH)
        if checkout_matches_commit(checker_paths):
            independent_gates._prospective_checker_binding(ROOT, current)
        else:
            with self.assertRaisesRegex(ValueError, "prospective policy/checker blob differs"):
                independent_gates._prospective_checker_binding(ROOT, current)
        producer_paths = [f"tools/numerical/portable/{name}" for name in
                          independent_gates.APPROVED_P2_PRODUCERS]
        producer_bound = checkout_matches_commit(producer_paths)
        for candidate in (historical, f"{revision}^", revision, current):
            with self.subTest(candidate=candidate):
                if producer_bound:
                    independent_gates._p2_producer_binding(ROOT, candidate)
                else:
                    with self.assertRaisesRegex(ValueError,
                                                "reviewed P2 raw producer blob differs"):
                        independent_gates._p2_producer_binding(ROOT, candidate)
        with self.assertRaisesRegex(ValueError, "predates reviewed P2 raw producer"):
            independent_gates._p2_producer_binding(
                ROOT, independent_gates.PROSPECTIVE_BRIDGE_CHECKER_REVISION)
        self.assertEqual(
            "e51e768c7d2c9075b9e1900b2bf3ad0fdacbda42bb3eb0d6f52f49492b546675",
            independent_gates.APPROVED_P2_HISTORICAL_PRODUCERS["actual_arithmetic.py"])
        self.assertEqual(
            "b96043c57a918dabe8425961b02aff930a704e592c32baffc5645b94b84ce835",
            independent_gates.APPROVED_P2_CLASS_LOAD_PRODUCERS["actual_arithmetic.py"])
        self.assertEqual(
            "5f02723e84401f612f4b7a1c72d7686b651e486e5153180ff80e2ec512faa1bf",
            independent_gates.APPROVED_P2_PRODUCERS["actual_arithmetic.py"])
        arithmetic_path = "tools/numerical/portable/actual_arithmetic.py"
        for reviewed in ("6408495750659a46eb0e2fb6f2167186f6eca2ef",
                         "ffdc8ba9b600732e6927e38e7d3da43a519994a4"):
            self.assertEqual(
                independent_gates.APPROVED_P2_CLASS_LOAD_PRODUCERS["actual_arithmetic.py"],
                hashlib.sha256(subprocess.check_output(
                    ["git", "show", f"{reviewed}:{arithmetic_path}"], cwd=ROOT)).hexdigest())
        for name, approved in independent_gates.APPROVED_P2_HISTORICAL_PRODUCERS.items():
            path = f"tools/numerical/portable/{name}"
            self.assertEqual(approved, hashlib.sha256(subprocess.check_output(
                ["git", "show", f"{historical}:{path}"], cwd=ROOT)).hexdigest())
        for name, approved in independent_gates.APPROVED_P2_CLASS_LOAD_PRODUCERS.items():
            path = f"tools/numerical/portable/{name}"
            self.assertEqual(approved, hashlib.sha256(subprocess.check_output(
                ["git", "show", f"{revision}:{path}"], cwd=ROOT)).hexdigest())
        for reviewed, blobs in (
                (independent_gates.P2_NUMERICAL_ARCHIVE_OWNER_REVISION,
                 independent_gates.APPROVED_P2_PRE_ARITHMETIC_PRODUCERS),
                (independent_gates.P2_NUMERICAL_ARCHIVE_REVISION,
                 independent_gates.APPROVED_P2_PRE_ARITHMETIC_PRODUCERS),
                (independent_gates.P2_CANONICAL_ARCHIVE_OWNER_REVISION,
                 independent_gates.APPROVED_P2_OWNER_CANONICAL_PRODUCERS),
                (independent_gates.P2_CANONICAL_ARCHIVE_ASSEMBLY_REVISION,
                 independent_gates.APPROVED_P2_PRE_ORIGINAL_OBJECT_PRODUCERS),
                (independent_gates.P2_ORIGINAL_OBJECT_OWNER_REVISION,
                 independent_gates.APPROVED_P2_ORIGINAL_OBJECT_OWNER_PRODUCERS),
                (independent_gates.P2_ORIGINAL_OBJECT_ASSEMBLY_REVISION,
                 independent_gates.APPROVED_P2_PRODUCERS)):
            for name, approved in blobs.items():
                path = f"tools/numerical/portable/{name}"
                self.assertEqual(approved, hashlib.sha256(subprocess.check_output(
                    ["git", "show", f"{reviewed}:{path}"], cwd=ROOT)).hexdigest())
        for name, approved in independent_gates.APPROVED_P2_CURRENT_PRODUCERS.items():
            path = f"tools/numerical/portable/{name}"
            self.assertEqual(approved, hashlib.sha256(subprocess.check_output(
                ["git", "show", f"{independent_gates.P2_CURRENT_ASSEMBLY_REVISION}:{path}"],
                cwd=ROOT)).hexdigest())
        with mock.patch.dict(independent_gates.PINNED_P2_CURRENT_LOCAL_PRODUCERS,
                             {"actual_arithmetic.py": "0" * 64}):
            with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, current)
        with mock.patch.dict(independent_gates.PINNED_P2_CURRENT_LOCAL_PRODUCERS, {
                "actual_arithmetic.py":
                independent_gates.APPROVED_P2_HISTORICAL_PRODUCERS["actual_arithmetic.py"]}):
            with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, current)
        with mock.patch.dict(independent_gates.APPROVED_P2_HISTORICAL_PRODUCERS,
                             {"actual_arithmetic.py": "0" * 64}):
            with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, historical)
        for blobs, candidate, name, stale in (
                (independent_gates.APPROVED_P2_CLASS_LOAD_PRODUCERS, revision,
                 "actual_arithmetic.py", independent_gates.APPROVED_P2_PRODUCERS["actual_arithmetic.py"]),
                (independent_gates.APPROVED_P2_PRE_ARITHMETIC_PRODUCERS,
                 independent_gates.P2_NUMERICAL_ARCHIVE_REVISION, "run.py",
                 independent_gates.APPROVED_P2_CLASS_LOAD_PRODUCERS["run.py"]),
                (independent_gates.APPROVED_P2_OWNER_CANONICAL_PRODUCERS,
                 independent_gates.P2_CANONICAL_ARCHIVE_OWNER_REVISION,
                 "actual_arithmetic.py",
                 independent_gates.APPROVED_P2_CLASS_LOAD_PRODUCERS["actual_arithmetic.py"]),
                (independent_gates.APPROVED_P2_DIRECT_WASM_22EFD_PRODUCERS,
                 independent_gates.P2_DIRECT_WASM_22EFD_ASSEMBLY_REVISION, "run.py",
                 independent_gates.APPROVED_P2_CLASS_LOAD_PRODUCERS["run.py"])):
            with self.subTest(candidate=candidate, stale=name), mock.patch.dict(
                    blobs, {name: stale}):
                with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, candidate)

    def test_p2_current_assembly_accepts_reviewed_baseline_capture_only(self):
        current = "24726f1f9e5c6c5cdad8dff3ea4e932265edd1c4"
        historical = independent_gates.P2_ORIGINAL_OBJECT_ASSEMBLY_REVISION
        current_sha256 = "0d61d0f942b6f0f977b028f47df183bcbd2f2d25add9300a787a30535f917847"
        current_git_blob = "a3b2c9a728bf49785c96fe2880a7c53e4f8be1a3"
        path = "tools/numerical/portable/baseline_capture.py"
        self.assertEqual(current, independent_gates.P2_CURRENT_ASSEMBLY_REVISION)
        self.assertEqual(current_sha256,
                         independent_gates.APPROVED_P2_CURRENT_PRODUCERS["baseline_capture.py"])
        self.assertEqual(current_git_blob, subprocess.check_output(
            ["git", "rev-parse", f"{current}:{path}"], cwd=ROOT, text=True).strip())
        self.assertNotEqual(current_sha256,
                            independent_gates.APPROVED_P2_PRODUCERS["baseline_capture.py"])
        self.assertEqual(independent_gates.APPROVED_P2_CURRENT_PRODUCERS,
                         independent_gates._p2_producer_binding(ROOT, current))
        self.assertEqual(independent_gates.APPROVED_P2_PRODUCERS,
                         independent_gates._p2_producer_binding(ROOT, historical))

        original_read_bytes = Path.read_bytes

        def tampered_local(path_value):
            content = original_read_bytes(path_value)
            return content + b"\n# changed local producer\n" if path_value == ROOT / path else content

        with mock.patch.object(Path, "read_bytes", tampered_local):
            with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, current)

        original_check_output = subprocess.check_output

        def tampered_committed(command, *args, **kwargs):
            content = original_check_output(command, *args, **kwargs)
            if "show" in command and f"{current}:{path}" in command:
                return content + b"\n# changed committed producer\n"
            return content

        with mock.patch.object(subprocess, "check_output", tampered_committed):
            with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, current)

    def test_p2_edbc_assembly_pins_only_reviewed_run_parser(self):
        edbc = "edbcfa5e219dd08b49a1fcef879dd5d458c23b1e"
        run_path = "tools/numerical/portable/run.py"
        run_sha256 = "4dd1f9eed602ae9cf3485fa64962edc3c541d087d9269dd5acd10ed1e22c1a97"
        run_git_blob = "1dc430fa554c31d8a275a3d48a812bad7e6b4ff1"
        reviewed = edbc
        previous = independent_gates.P2_CURRENT_ASSEMBLY_REVISION
        older = independent_gates.P2_ORIGINAL_OBJECT_ASSEMBLY_REVISION
        self.assertEqual(edbc, independent_gates.P2_EDBC_ASSEMBLY_REVISION)
        expected = dict(independent_gates.APPROVED_P2_CURRENT_PRODUCERS)
        expected["run.py"] = run_sha256
        self.assertEqual(expected, independent_gates.APPROVED_P2_EDBC_PRODUCERS)
        local_expected = dict(expected)
        local_expected["run.py"] = independent_gates.APPROVED_P2_BASELINE_COMPAT_PRODUCERS["run.py"]
        self.assertEqual(local_expected["run.py"],
                         independent_gates.PINNED_P2_CURRENT_LOCAL_PRODUCERS["run.py"])
        self.assertEqual(local_expected["run.py"],
                         hashlib.sha256((ROOT / run_path).read_bytes()).hexdigest())
        self.assertEqual(run_git_blob, subprocess.check_output(
            ["git", "rev-parse", f"{edbc}:{run_path}"], cwd=ROOT, text=True).strip())
        self.assertEqual(run_sha256, hashlib.sha256(subprocess.check_output(
            ["git", "show", f"{reviewed}:{run_path}"], cwd=ROOT)).hexdigest())

        for revision in (previous, "2b20aa96c5bc28f13258b86d517003ff74f8b5fd"):
            with self.subTest(revision=revision):
                self.assertEqual(independent_gates.APPROVED_P2_CURRENT_PRODUCERS,
                                 independent_gates._p2_producer_binding(ROOT, revision))
        self.assertEqual(independent_gates.APPROVED_P2_PRODUCERS,
                         independent_gates._p2_producer_binding(ROOT, older))
        self.assertEqual(expected, independent_gates._p2_producer_binding(ROOT, edbc))

        original_read_bytes = Path.read_bytes

        def tampered_local(path_value):
            content = original_read_bytes(path_value)
            if path_value == ROOT / run_path:
                return content + b"\n# changed local run producer\n"
            return content

        with mock.patch.object(Path, "read_bytes", tampered_local):
            with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, edbc)

        original_check_output = subprocess.check_output

        def tampered_committed(command, *args, **kwargs):
            content = original_check_output(command, *args, **kwargs)
            if "show" in command and f"{edbc}:{run_path}" in command:
                return content + b"\n# changed committed run producer\n"
            return content

        with mock.patch.object(subprocess, "check_output", tampered_committed):
            with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, edbc)

        with mock.patch.dict(independent_gates.APPROVED_P2_CURRENT_PRODUCERS,
                             {"run.py": "0" * 64}):
            with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, previous)

    def test_p2_native_02c_assembly_pins_only_reviewed_run_producer(self):
        current = "02cbc0a989e4d4b02a5305e8bf6d737251336ec8"
        pre_fence = "e7d11b4f"
        edbc = independent_gates.P2_EDBC_ASSEMBLY_REVISION
        older = independent_gates.P2_ORIGINAL_OBJECT_ASSEMBLY_REVISION
        run_path = "tools/numerical/portable/run.py"
        run_sha256 = "750273c0417ff633db79243e2b4df929104f6012b54f667168c176b450dea8cd"
        run_git_blob = "cb0455222f79d323f96eaac983772f813ea5601c"

        self.assertEqual(current, independent_gates.P2_NATIVE_02C_ASSEMBLY_REVISION)
        expected = dict(independent_gates.APPROVED_P2_EDBC_PRODUCERS)
        expected["run.py"] = run_sha256
        self.assertEqual(expected, independent_gates.APPROVED_P2_NATIVE_02C_PRODUCERS)
        local_expected = dict(expected)
        local_expected["run.py"] = independent_gates.APPROVED_P2_BASELINE_COMPAT_PRODUCERS["run.py"]
        self.assertEqual(local_expected["run.py"],
                         independent_gates.PINNED_P2_CURRENT_LOCAL_PRODUCERS["run.py"])
        self.assertEqual(local_expected["run.py"],
                         hashlib.sha256((ROOT / run_path).read_bytes()).hexdigest())
        self.assertEqual(run_git_blob, subprocess.check_output(
            ["git", "rev-parse", f"{current}:{run_path}"], cwd=ROOT, text=True).strip())
        self.assertEqual(run_sha256, hashlib.sha256(subprocess.check_output(
            ["git", "show", f"{current}:{run_path}"], cwd=ROOT)).hexdigest())

        self.assertEqual(expected, independent_gates._p2_producer_binding(ROOT, current))
        self.assertEqual(independent_gates.APPROVED_P2_EDBC_PRODUCERS,
                         independent_gates._p2_producer_binding(ROOT, edbc))
        self.assertEqual(independent_gates.APPROVED_P2_CURRENT_PRODUCERS,
                         independent_gates._p2_producer_binding(
                             ROOT, "2b20aa96c5bc28f13258b86d517003ff74f8b5fd"))
        self.assertEqual(independent_gates.APPROVED_P2_PRODUCERS,
                         independent_gates._p2_producer_binding(ROOT, older))

        with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
            independent_gates._p2_producer_binding(ROOT, pre_fence)

        original_read_bytes = Path.read_bytes

        def tampered_local(path_value):
            content = original_read_bytes(path_value)
            return (content + b"\n# changed local run producer\n"
                    if path_value == ROOT / run_path else content)

        with mock.patch.object(Path, "read_bytes", tampered_local):
            with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, current)

        original_check_output = subprocess.check_output

        def tampered_committed(command, *args, **kwargs):
            content = original_check_output(command, *args, **kwargs)
            if "show" in command and f"{current}:{run_path}" in command:
                return content + b"\n# changed committed run producer\n"
            return content

        with mock.patch.object(subprocess, "check_output", tampered_committed):
            with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, current)

    def test_p2_direct_wasm_22efd_assembly_pins_reviewed_current_run(self):
        assembly = "22efd65082287ccbda2700c69899ba404b61602a"
        run_path = "tools/numerical/portable/run.py"
        run_sha256 = "7a52d41dcb96238402beee7cfc381ccb87b8ffd96ef247d602d92037bd073051"
        run_git_blob = "3a290ab7b7b2dfea1851390bbe9d88d894cf5a81"
        candidate_head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        expected = dict(independent_gates.APPROVED_P2_NATIVE_02C_PRODUCERS)
        expected["run.py"] = run_sha256

        try:
            bound = independent_gates._p2_producer_binding(ROOT, assembly)
        except ValueError as error:
            self.fail(f"reviewed direct-Wasm producer was rejected: {error}")
        self.assertEqual(assembly, independent_gates.P2_DIRECT_WASM_22EFD_ASSEMBLY_REVISION)
        self.assertEqual(expected, independent_gates.APPROVED_P2_DIRECT_WASM_22EFD_PRODUCERS)
        self.assertEqual(expected, bound)
        self.assertEqual(independent_gates.APPROVED_P2_PATH_MODEL_PRODUCERS,
                         independent_gates._p2_producer_binding(ROOT, candidate_head))
        self.assertEqual(independent_gates.P2_ROTATION_PREMISE_PRODUCERS,
                         independent_gates.APPROVED_P2_LOCAL_PRODUCERS)
        self.assertEqual(independent_gates.APPROVED_P2_BASELINE_COMPAT_PRODUCERS["run.py"],
                         hashlib.sha256((ROOT / run_path).read_bytes()).hexdigest())
        self.assertEqual(run_git_blob, subprocess.check_output(
            ["git", "rev-parse", f"{assembly}:{run_path}"], cwd=ROOT, text=True).strip())
        self.assertEqual(run_sha256, hashlib.sha256(subprocess.check_output(
            ["git", "show", f"{assembly}:{run_path}"], cwd=ROOT)).hexdigest())

        original_read_bytes = Path.read_bytes

        def tampered_local(path_value):
            content = original_read_bytes(path_value)
            return (content + b"\n# changed local run producer\n"
                    if path_value == ROOT / run_path else content)

        with mock.patch.object(Path, "read_bytes", tampered_local):
            with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, assembly)

        original_check_output = subprocess.check_output

        def tampered_committed(command, *args, **kwargs):
            content = original_check_output(command, *args, **kwargs)
            if "show" in command and f"{assembly}:{run_path}" in command:
                return content + b"\n# changed committed run producer\n"
            return content

        with mock.patch.object(subprocess, "check_output", tampered_committed):
            with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, assembly)
    def test_p2_operation_assembly_pins_three_changed_producers(self):
        approved_revision = "0a8c7d74a2194c3e3b7428dddc273376dc854a0d"
        previous = "5a333f6cca2b774b42f53c1241a5e135fa29ecea"
        expected_changes = {
            "actual_arithmetic.py": "d4ea004cd0056b85845b1a281e9caf386536c3707aa6a702258c720080656d5a",
            "capture_actual.py": "d27b6d615ab8425aa050933ea57b46cd6ff7b8e489f9ccbf2fa064cd7e6717f8",
            "rotation_oracle.py": "a765c8ab4ffda48df651ec0df923f3cfeff9de7a734c78155963ea851d489a3e",
        }
        self.assertEqual(approved_revision, independent_gates.P2_OPERATION_ASSEMBLY_REVISION)
        self.assertEqual(expected_changes, {
            name: independent_gates.APPROVED_P2_OPERATION_PRODUCERS[name]
            for name in expected_changes})
        self.assertEqual(independent_gates.APPROVED_P2_NATIVE_02C_PRODUCERS,
                         independent_gates._p2_producer_binding(ROOT, previous))
        self.assertEqual(independent_gates.APPROVED_P2_OPERATION_PRODUCERS,
                         independent_gates._p2_producer_binding(ROOT, approved_revision))
        for name, digest in independent_gates.APPROVED_P2_OPERATION_PRODUCERS.items():
            path = f"tools/numerical/portable/{name}"
            self.assertEqual(digest, hashlib.sha256(subprocess.check_output(
                ["git", "show", f"{approved_revision}:{path}"], cwd=ROOT)).hexdigest())
        for revision in ("00af7a10", "2acec83c", "03125a11", "15184cbf"):
            with self.subTest(unreviewed=revision), self.assertRaisesRegex(
                    ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, revision)
        for name in expected_changes:
            with self.subTest(stale=name), mock.patch.dict(
                    independent_gates.APPROVED_P2_OPERATION_PRODUCERS,
                    {name: independent_gates.APPROVED_P2_NATIVE_02C_PRODUCERS[name]}):
                with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, approved_revision)
            path = ROOT / "tools/numerical/portable" / name
            original = Path.read_bytes

            def altered(file_path):
                raw = original(file_path)
                return raw + b"\n# altered\n" if file_path == path else raw

            with mock.patch.object(Path, "read_bytes", altered):
                with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, approved_revision)
        original_show = subprocess.check_output
        changed_path = "tools/numerical/portable/capture_actual.py"

        def altered_committed(command, *args, **kwargs):
            raw = original_show(command, *args, **kwargs)
            if "show" in command and f"{approved_revision}:{changed_path}" in command:
                return raw + b"\n# altered committed producer\n"
            return raw

        with mock.patch.object(subprocess, "check_output", altered_committed):
            with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, approved_revision)

    def test_p2_combined_assembly_requires_both_reviewed_producer_lineages(self):
        combined = "3212df564682e95b33b4bd59b248733b5b34b219"
        operation = independent_gates.P2_OPERATION_ASSEMBLY_REVISION
        direct_wasm = independent_gates.P2_DIRECT_WASM_22EFD_ASSEMBLY_REVISION
        expected = dict(independent_gates.APPROVED_P2_OPERATION_PRODUCERS)
        expected["run.py"] = independent_gates.APPROVED_P2_DIRECT_WASM_22EFD_PRODUCERS["run.py"]
        self.assertEqual(combined, independent_gates.P2_COMBINED_ASSEMBLY_REVISION)
        self.assertEqual(expected, independent_gates.APPROVED_P2_COMBINED_PRODUCERS)
        self.assertEqual(independent_gates.P2_ROTATION_PREMISE_PRODUCERS,
                         independent_gates.APPROVED_P2_LOCAL_PRODUCERS)
        self.assertEqual(independent_gates.APPROVED_P2_OPERATION_PRODUCERS,
                         independent_gates._p2_producer_binding(ROOT, operation))
        self.assertEqual(independent_gates.APPROVED_P2_DIRECT_WASM_22EFD_PRODUCERS,
                         independent_gates._p2_producer_binding(ROOT, direct_wasm))
        self.assertEqual(expected, independent_gates._p2_producer_binding(ROOT, combined))
        for name, digest in expected.items():
            path = f"tools/numerical/portable/{name}"
            committed = subprocess.check_output(
                ["git", "--no-replace-objects", "show", f"{combined}:{path}"], cwd=ROOT)
            self.assertEqual(digest, hashlib.sha256(committed).hexdigest())
            self.assertEqual(independent_gates.PINNED_P2_CURRENT_LOCAL_PRODUCERS[name],
                             hashlib.sha256((ROOT / path).read_bytes()).hexdigest())
        for revision in ("00af7a10", "2acec83c", "03125a11", "15184cbf"):
            with self.subTest(intermediate=revision), self.assertRaisesRegex(
                    ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, revision)
        for name, standalone in (("actual_arithmetic.py",
                                  independent_gates.APPROVED_P2_DIRECT_WASM_22EFD_PRODUCERS),
                                 ("run.py", independent_gates.APPROVED_P2_OPERATION_PRODUCERS)):
            with self.subTest(stale=name), mock.patch.dict(
                    independent_gates.APPROVED_P2_COMBINED_PRODUCERS,
                    {name: standalone[name]}):
                with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, combined)
            path = ROOT / "tools/numerical/portable" / name
            original_read = Path.read_bytes

            def changed_local(file_path):
                raw = original_read(file_path)
                return raw + b"\n# changed\n" if file_path == path else raw

            with mock.patch.object(Path, "read_bytes", changed_local):
                with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, combined)
            original_show = subprocess.check_output
            relative = f"tools/numerical/portable/{name}"

            def changed_committed(command, *args, **kwargs):
                raw = original_show(command, *args, **kwargs)
                if "show" in command and f"{combined}:{relative}" in command:
                    return raw + b"\n# changed\n"
                return raw

            with mock.patch.object(subprocess, "check_output", changed_committed):
                with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, combined)

    def test_p2_reviewed_arithmetic_assembly_binds_current_and_historical_bytes(self):
        current = "a8273834c52b20d9e4b4ca732af7c7160b910d8f"
        expected = dict(independent_gates.APPROVED_P2_COMBINED_PRODUCERS)
        expected.update({
            "actual_arithmetic.py": "dd3685fc1cf463682be36edf206ed78829333f53434a345bc3260927d7e27fdc",
            "rotation_oracle.py": "acb766b819eb314c65932e7357ac07314c93dcdd9acfd3ce48eb6c38a4ad1edd",
        })
        self.assertEqual(current, independent_gates.P2_ARITHMETIC_ASSEMBLY_REVISION)
        self.assertEqual(expected, independent_gates.APPROVED_P2_ARITHMETIC_PRODUCERS)
        for name, revision in (
                ("actual_arithmetic.py", "d981bdd2e6d915554f8fae1ea9b2c2a41cfcc7b0"),
                ("rotation_oracle.py", "a7d544677f0cd727bc356bacc7eac3dd555cfe80")):
            path = f"tools/numerical/portable/{name}"
            reviewed = subprocess.check_output(
                ["git", "--no-replace-objects", "show", f"{revision}:{path}"], cwd=ROOT)
            committed = subprocess.check_output(
                ["git", "--no-replace-objects", "show", f"{current}:{path}"], cwd=ROOT)
            self.assertEqual(reviewed, committed)
            self.assertEqual(expected[name], hashlib.sha256(reviewed).hexdigest())
            self.assertEqual(independent_gates.APPROVED_P2_OUTPUT_PROVENANCE_PRODUCERS[name],
                             hashlib.sha256((ROOT / path).read_bytes()).hexdigest())
        self.assertEqual(expected, independent_gates._p2_producer_binding(ROOT, current))
        self.assertEqual(independent_gates.APPROVED_P2_COMBINED_PRODUCERS,
                         independent_gates._p2_producer_binding(
                             ROOT, "68339377a5d8dff1fd3dd6bf1ab17a32a0a402cd"))
        self.assertEqual(independent_gates.APPROVED_P2_COMBINED_PRODUCERS,
                         independent_gates._p2_producer_binding(
                             ROOT, "7d319d5027f2b10c11eae7f4574e6edf407449c0"))
        with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
            independent_gates._p2_producer_binding(ROOT, "a7d54467")

    def test_p2_arithmetic_coverage_revision_binds_reviewed_call_shape_repair(self):
        current = "d981bdd2e6d915554f8fae1ea9b2c2a41cfcc7b0"
        relative = "tools/numerical/portable/rotation_oracle.py"
        expected = dict(independent_gates.APPROVED_P2_ARITHMETIC_PRODUCERS)
        expected["rotation_oracle.py"] = (
            "cf3b0906edb69b08cb24fb2be9a741ffacd3229a8ab466598887005d71109a47")
        self.assertEqual(current, independent_gates.P2_ARITHMETIC_COVERAGE_ASSEMBLY_REVISION)
        self.assertEqual(expected, independent_gates.APPROVED_P2_ARITHMETIC_COVERAGE_PRODUCERS)
        self.assertEqual(independent_gates.P2_ROTATION_PREMISE_PRODUCERS,
                         independent_gates.APPROVED_P2_LOCAL_PRODUCERS)
        committed = subprocess.check_output(
            ["git", "--no-replace-objects", "show", f"{current}:{relative}"], cwd=ROOT)
        self.assertEqual(expected["rotation_oracle.py"], hashlib.sha256(committed).hexdigest())
        self.assertNotEqual(committed, (ROOT / relative).read_bytes())
        self.assertEqual(expected, independent_gates._p2_producer_binding(ROOT, current))
        self.assertEqual(independent_gates.APPROVED_P2_ARITHMETIC_PRODUCERS,
                         independent_gates._p2_producer_binding(
                             ROOT, independent_gates.P2_ARITHMETIC_ASSEMBLY_REVISION))
        original_read = Path.read_bytes
        local = ROOT / relative
        with mock.patch.object(Path, "read_bytes", lambda path_value: committed + b"changed"
                               if path_value == local else original_read(path_value)):
            with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, current)

    def test_p2_portable_provider_revision_binds_reviewed_receipt_checker(self):
        current = "fac06d5240f8b030bfd9c5960d7784fa1a50c4f2"
        relative = "tools/numerical/portable/actual_arithmetic.py"
        expected = dict(independent_gates.APPROVED_P2_ARITHMETIC_COVERAGE_PRODUCERS)
        expected["actual_arithmetic.py"] = (
            "e2e01e3c10de4e06c86365661821cb9c1ee6985b8944098683bd1f6039c8652b")
        self.assertEqual(current, independent_gates.P2_PORTABLE_PROVIDER_ASSEMBLY_REVISION)
        self.assertEqual(expected, independent_gates.APPROVED_P2_PORTABLE_PROVIDER_PRODUCERS)
        self.assertEqual(independent_gates.P2_ROTATION_PREMISE_PRODUCERS,
                         independent_gates.APPROVED_P2_LOCAL_PRODUCERS)
        committed = subprocess.check_output(
            ["git", "--no-replace-objects", "show", f"{current}:{relative}"], cwd=ROOT)
        self.assertEqual(expected["actual_arithmetic.py"], hashlib.sha256(committed).hexdigest())
        self.assertNotEqual(committed, (ROOT / relative).read_bytes())
        self.assertEqual(expected, independent_gates._p2_producer_binding(ROOT, current))
        self.assertEqual(independent_gates.APPROVED_P2_ARITHMETIC_COVERAGE_PRODUCERS,
                         independent_gates._p2_producer_binding(
                             ROOT, independent_gates.P2_ARITHMETIC_COVERAGE_ASSEMBLY_REVISION))
        original_read = Path.read_bytes
        local = ROOT / relative
        with mock.patch.object(Path, "read_bytes", lambda path_value: committed + b"changed"
                               if path_value == local else original_read(path_value)):
            with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, current)
        original_show = subprocess.check_output

        def altered_show(command, *args, **kwargs):
            content = original_show(command, *args, **kwargs)
            return content + b"changed" if "show" in command and \
                f"{current}:{relative}" in command else content

        with mock.patch.object(subprocess, "check_output", altered_show):
            with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, current)

    def test_p2_dynamic_class_revision_keeps_unbound_status_source_pinned(self):
        current = "41926bd3d14a472f809c2e5693e6e774fb502ddc"
        relative = "tools/numerical/portable/actual_arithmetic.py"
        expected = dict(independent_gates.APPROVED_P2_PORTABLE_PROVIDER_PRODUCERS)
        expected["actual_arithmetic.py"] = (
            "e1732c31c7c3c290c81e379848b865b3b6968c63ebbc9d1dd03a6b6049fc7aa7")
        self.assertEqual(current, independent_gates.P2_DYNAMIC_CLASS_ASSEMBLY_REVISION)
        self.assertEqual(expected, independent_gates.APPROVED_P2_DYNAMIC_CLASS_PRODUCERS)
        self.assertNotEqual(expected, independent_gates.APPROVED_P2_LOCAL_PRODUCERS)
        committed = subprocess.check_output(
            ["git", "--no-replace-objects", "show", f"{current}:{relative}"], cwd=ROOT)
        self.assertEqual(expected["actual_arithmetic.py"], hashlib.sha256(committed).hexdigest())
        self.assertNotEqual(committed, (ROOT / relative).read_bytes())
        self.assertEqual(expected, independent_gates._p2_producer_binding(ROOT, current))
        self.assertEqual(independent_gates.APPROVED_P2_PORTABLE_PROVIDER_PRODUCERS,
                         independent_gates._p2_producer_binding(
                             ROOT, independent_gates.P2_PORTABLE_PROVIDER_ASSEMBLY_REVISION))
        original_read = Path.read_bytes
        local = ROOT / relative
        with mock.patch.object(Path, "read_bytes", lambda path_value: committed + b"changed"
                               if path_value == local else original_read(path_value)):
            with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, current)
        original_show = subprocess.check_output

        def altered_show(command, *args, **kwargs):
            content = original_show(command, *args, **kwargs)
            return content + b"changed" if "show" in command and \
                f"{current}:{relative}" in command else content

        with mock.patch.object(subprocess, "check_output", altered_show):
            with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, current)

    def test_p2_generic_class_revision_keeps_all_methods_unbound(self):
        current = "fc576e69703b6757d7306be720a9834a59e81af6"
        relative = "tools/numerical/portable/actual_arithmetic.py"
        expected = dict(independent_gates.APPROVED_P2_DYNAMIC_CLASS_PRODUCERS)
        expected["actual_arithmetic.py"] = (
            "83454c14e4e72412f11acdeb15bc4c405c3bc651df542319e9ac3e94bf76fa4b")
        self.assertEqual(current, independent_gates.P2_GENERIC_CLASS_ASSEMBLY_REVISION)
        self.assertEqual(expected, independent_gates.APPROVED_P2_GENERIC_CLASS_PRODUCERS)
        self.assertNotEqual(expected, independent_gates.APPROVED_P2_LOCAL_PRODUCERS)
        committed = subprocess.check_output(
            ["git", "--no-replace-objects", "show", f"{current}:{relative}"], cwd=ROOT)
        self.assertEqual(expected["actual_arithmetic.py"], hashlib.sha256(committed).hexdigest())
        self.assertNotEqual(committed, (ROOT / relative).read_bytes())
        self.assertEqual(expected, independent_gates._p2_producer_binding(ROOT, current))
        self.assertEqual(independent_gates.APPROVED_P2_DYNAMIC_CLASS_PRODUCERS,
                         independent_gates._p2_producer_binding(
                             ROOT, independent_gates.P2_DYNAMIC_CLASS_ASSEMBLY_REVISION))
        original_read = Path.read_bytes
        local = ROOT / relative
        with mock.patch.object(Path, "read_bytes", lambda path_value: committed + b"changed"
                               if path_value == local else original_read(path_value)):
            with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, current)
        original_show = subprocess.check_output

        def altered_show(command, *args, **kwargs):
            content = original_show(command, *args, **kwargs)
            return content + b"changed" if "show" in command and \
                f"{current}:{relative}" in command else content

        with mock.patch.object(subprocess, "check_output", altered_show):
            with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, current)

    def test_p2_d3d6_producer_window_binds_current_and_historical_source(self):
        current = "d3d6d554450060c8785209a6380535a33d87bfb4"
        historical = independent_gates.P2_GENERIC_CLASS_ASSEMBLY_REVISION
        changed = {
            "actual_arithmetic.py": "3d9f88a972e64f6d8ef5ae856091f6d35d49bb02d6a36774c4d84ecd8db6663c",
            "capture_actual.py": "9615eda6953125fa8fef0b991e4b4763c1db054625a587cdd2dac563874de265",
            "rotation_oracle.py": "0e7d89680e5fdac765b83a3c625c1e041b2c2e38a974492461fae150c8f46e9a",
        }
        expected = {**independent_gates.APPROVED_P2_GENERIC_CLASS_PRODUCERS,
                    **changed}
        self.assertEqual(current, independent_gates.P2_D3D6_SOURCE_REVISION)
        self.assertEqual(expected, independent_gates.P2_D3D6_PRODUCERS)
        self.assertNotEqual(expected, independent_gates.APPROVED_P2_LOCAL_PRODUCERS)
        for name, digest in expected.items():
            relative = f"tools/numerical/portable/{name}"
            committed = subprocess.check_output(
                ["git", "--no-replace-objects", "show", f"{current}:{relative}"], cwd=ROOT)
            self.assertEqual(digest, hashlib.sha256(committed).hexdigest())
            if name in ("actual_arithmetic.py", "capture_actual.py", "rotation_oracle.py",
                        "run.py"):
                self.assertNotEqual(committed, (ROOT / relative).read_bytes())
            else:
                self.assertEqual(committed, (ROOT / relative).read_bytes())
        self.assertEqual(expected, independent_gates._p2_producer_binding(ROOT, current))
        self.assertEqual(independent_gates.APPROVED_P2_GENERIC_CLASS_PRODUCERS,
                         independent_gates._p2_producer_binding(ROOT, historical))
        for revision in ("810ef6691a358e107d7225e0178332ac69d8655a",
                         "6cad7fa08f983347ae41ac3df2ab953611645ca9"):
            with self.subTest(intermediate=revision), self.assertRaisesRegex(
                    ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, revision)
        for name in changed:
            relative = f"tools/numerical/portable/{name}"
            local = ROOT / relative
            old = subprocess.check_output(
                ["git", "--no-replace-objects", "show", f"{historical}:{relative}"],
                cwd=ROOT)
            self.assertEqual(independent_gates.APPROVED_P2_GENERIC_CLASS_PRODUCERS[name],
                             hashlib.sha256(old).hexdigest())
            original_read = Path.read_bytes

            def altered_local(path_value):
                raw = original_read(path_value)
                return raw + b"\n# changed\n" if path_value == local else raw

            for label, replacement in (("altered", altered_local),
                                       ("stale", lambda path_value: old
                                        if path_value == local else original_read(path_value))):
                with self.subTest(file=name, local=label), mock.patch.object(
                        Path, "read_bytes", replacement):
                    with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                        independent_gates._p2_producer_binding(ROOT, current)
            original_show = subprocess.check_output

            for label, replacement in (("stale", old), ("altered", old + b"\n# changed\n")):
                def replaced_committed(command, *args, **kwargs):
                    if "show" in command and f"{current}:{relative}" in command:
                        return replacement
                    return original_show(command, *args, **kwargs)

                with self.subTest(file=name, committed=label), mock.patch.object(
                        subprocess, "check_output", replaced_committed):
                    with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                        independent_gates._p2_producer_binding(ROOT, current)
            with self.subTest(file=name, pin="stale"), mock.patch.dict(
                    independent_gates.P2_D3D6_PRODUCERS,
                    {name: hashlib.sha256(old).hexdigest()}):
                with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, current)
            with self.subTest(file=name, pin="unknown"), mock.patch.dict(
                    independent_gates.PINNED_P2_CURRENT_LOCAL_PRODUCERS, {name: "0" * 64}):
                with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, current)

    def test_p2_boolean_jdi_2a2_binds_worker_source_and_rejects_mutations(self):
        current = "2a2c4b797b8adcdf3c03ee8475366ba2cfd9b16e"
        earlier = independent_gates.P2_D3D6_SOURCE_REVISION
        expected = {**independent_gates.P2_D3D6_PRODUCERS,
                    "actual_arithmetic.py":
                    "6d1d478637b9645e6c007a2e5ce3def044742030698aefb3d792080a2be984c0",
                    "capture_actual.py":
                    "8f07d4d00877e1f57c74e75d99b052adb60c9f98c8b70f08691b8e533962106e"}
        dependencies = {
            "tools/numerical/portable/build.gradle.kts":
                "3d49cad9fd9205073f880cc20185856b2994c67e2e360cec64772d1e152a71f0",
            "tools/numerical/portable/boolean_rotation_jdi/RotationJdiProbe.java":
                "bd83b069d0eea15872b916024b2c5fd9af553a1f0bb9b91b534932491155921f",
            "tools/numerical/portable/boolean_rotation_jdi/jdi_bridge.py":
                "e041836cd3caf0ee0cfa847d66b718d9f10786ee9a914d85ebd4faac77e5dec7",
            "tools/numerical/portable/boolean_rotation_jdi/loaded_code.py":
                "1cc52a98ec4d93ad199f82831758bb61ae962f13da47f594a290f010a62087be",
            "tools/numerical/portable/boolean_rotation_jdi/source_guard.py":
                "5c44941dbe31ba0e2c196a53ed8fdfcd990aa51096661345e39731d54b132180",
            "tools/numerical/portable/boolean_rotation_jdi/witness.py":
                "dd7edfa3e0120520e4fd2fb2125e4f438cc73f0dbb08d70cb20ef0beddcb82a6",
            "dyn4k-core/src/commonMain/kotlin/org/dyn4j/geometry/Transform.kt":
                "ec22ca59049bbe090f381f133a43d7e1e72b3b220960ec751c3f278b7b280747",
            "dyn4k-core/src/commonMain/kotlin/org/dyn4j/collision/CollisionBody.kt":
                "71690455e111fbc3076885ef5a968a66e32616b334afdf428d8f9e56e74b0174",
            "dyn4k-core/src/commonMain/kotlin/org/dyn4j/dynamics/AbstractPhysicsBody.kt":
                "569979aee3583bf61d11dcffed236901257e606b207011c52f417e2ce1513719",
            "dyn4k-core/src/commonMain/kotlin/org/dyn4j/dynamics/joint/RevoluteJoint.kt":
                "8be0bf63a1b2940a2570bd814040aaa1d6058862a1419528d02ed5c0f2748e58",
            "dyn4k-core/src/commonMain/kotlin/org/dyn4j/dynamics/joint/AbstractPairedBodyJoint.kt":
                "90a4dc4bdf28e6ea785af699f5f40acd80afba86bf0e2a40a88ca03f8962d17f",
            "tools/numerical/portable/src/jvmTest/kotlin/portable/RevoluteLimitsFalseCaptureTest.kt":
                "d7a8467eb390a4c0db1544472fdb092420933470c879880f23ac64c2e43ff881",
        }
        self.assertEqual(current, independent_gates.P2_BOOLEAN_JDI_SOURCE_REVISION)
        self.assertEqual(expected, independent_gates.P2_BOOLEAN_JDI_PRODUCERS)
        self.assertEqual(independent_gates.P2_ROTATION_PREMISE_PRODUCERS,
                         independent_gates.APPROVED_P2_LOCAL_PRODUCERS)
        self.assertEqual(dependencies, independent_gates.P2_BOOLEAN_JDI_DEPENDENCIES)
        for name, digest in expected.items():
            relative = f"tools/numerical/portable/{name}"
            committed = subprocess.check_output(
                ["git", "--no-replace-objects", "show", f"{current}:{relative}"], cwd=ROOT)
            self.assertEqual(digest, hashlib.sha256(committed).hexdigest())
            if name in ("actual_arithmetic.py", "capture_actual.py", "rotation_oracle.py",
                        "run.py"):
                self.assertNotEqual(committed, (ROOT / relative).read_bytes())
            else:
                self.assertEqual(committed, (ROOT / relative).read_bytes())
        for relative, digest in dependencies.items():
            committed = subprocess.check_output(
                ["git", "--no-replace-objects", "show", f"{current}:{relative}"], cwd=ROOT)
            self.assertEqual(digest, hashlib.sha256(committed).hexdigest())
            if relative in ("tools/numerical/portable/build.gradle.kts",
                            "tools/numerical/portable/boolean_rotation_jdi/RotationJdiProbe.java",
                            "tools/numerical/portable/boolean_rotation_jdi/jdi_bridge.py",
                            "tools/numerical/portable/boolean_rotation_jdi/loaded_code.py",
                            "tools/numerical/portable/boolean_rotation_jdi/witness.py"):
                self.assertNotEqual(committed, (ROOT / relative).read_bytes())
            else:
                self.assertEqual(committed, (ROOT / relative).read_bytes())
        self.assertEqual(expected, independent_gates._p2_producer_binding(ROOT, current))
        self.assertEqual(independent_gates.P2_D3D6_PRODUCERS,
                         independent_gates._p2_producer_binding(ROOT, earlier))
        self.assertEqual(independent_gates.APPROVED_P2_GENERIC_CLASS_PRODUCERS,
                         independent_gates._p2_producer_binding(
                             ROOT, independent_gates.P2_GENERIC_CLASS_ASSEMBLY_REVISION))
        for revision in ("341276fd55ea23c35fabab4a859f520dd5831429",
                         "d0ddb5da98acb997af9db0b88bcab06590370747"):
            with self.subTest(incomplete=revision), self.assertRaisesRegex(
                    ValueError, "incomplete Boolean JDI producer lineage"):
                independent_gates._p2_producer_binding(ROOT, revision)
        for relative in dependencies:
            local = ROOT / relative
            original_read = Path.read_bytes

            def changed_local(path_value):
                raw = original_read(path_value)
                return raw + b"changed" if path_value == local else raw

            with self.subTest(path=relative, surface="local"), mock.patch.object(
                    Path, "read_bytes", changed_local):
                with self.assertRaisesRegex(ValueError, "Boolean JDI producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, current)
            original_show = subprocess.check_output

            def changed_committed(command, *args, **kwargs):
                raw = original_show(command, *args, **kwargs)
                return raw + b"changed" if "show" in command and \
                    f"{current}:{relative}" in command else raw

            with self.subTest(path=relative, surface="committed"), mock.patch.object(
                    subprocess, "check_output", changed_committed):
                with self.assertRaisesRegex(ValueError, "Boolean JDI producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, current)
        for name in ("actual_arithmetic.py", "capture_actual.py"):
            relative = f"tools/numerical/portable/{name}"
            stale = subprocess.check_output(
                ["git", "--no-replace-objects", "show", f"{earlier}:{relative}"], cwd=ROOT)
            self.assertEqual(independent_gates.P2_D3D6_PRODUCERS[name],
                             hashlib.sha256(stale).hexdigest())
            local = ROOT / relative
            original_read = Path.read_bytes
            with self.subTest(file=name, local="altered"), mock.patch.object(
                    Path, "read_bytes", lambda path_value: original_read(path_value) + b"changed"
                    if path_value == local else original_read(path_value)):
                with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, current)
            original_show = subprocess.check_output

            def stale_committed(command, *args, **kwargs):
                if "show" in command and f"{current}:{relative}" in command:
                    return stale
                return original_show(command, *args, **kwargs)

            with self.subTest(file=name, committed="stale"), mock.patch.object(
                    subprocess, "check_output", stale_committed):
                with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, current)
            with self.subTest(file=name, pin="stale"), mock.patch.dict(
                    independent_gates.P2_BOOLEAN_JDI_PRODUCERS,
                    {name: hashlib.sha256(stale).hexdigest()}):
                with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, current)

    def test_p2_boolean_jdi_final_binds_reviewed_source_and_rejects_mutations(self):
        current = "1ef6554b4edb4e6066f5ae16ee64dbeda131d568"
        assembly = "990910f697dbb8c183793796d0aca7a16c520815"
        parent = "d5683a7474e2379f5aa4d5c29dc49b1b109aa98f"
        self.assertEqual(current, independent_gates.P2_BOOLEAN_JDI_FINAL_SOURCE_REVISION)
        self.assertEqual(assembly, independent_gates.P2_BOOLEAN_JDI_FINAL_ASSEMBLY_REVISION)
        self.assertEqual(independent_gates.P2_ROTATION_PREMISE_PRODUCERS,
                         independent_gates.APPROVED_P2_LOCAL_PRODUCERS)
        self.assertNotEqual(independent_gates.P2_BOOLEAN_JDI_PRODUCERS,
                            independent_gates.P2_BOOLEAN_JDI_FINAL_PRODUCERS)
        self.assertEqual(
            {**independent_gates.P2_BOOLEAN_JDI_PRODUCERS,
             "actual_arithmetic.py":
             "2c3b33719c03ff2e57ac1eb6739bb248a554ed4efbf4b1e5fa59244e411b54d2",
             "capture_actual.py":
             "b3a867bfaf835bd41f998c93823375ec1e08b9ee4b2de8d2c52010447c28e5cc"},
            independent_gates.P2_BOOLEAN_JDI_FINAL_PRODUCERS)
        self.assertEqual(
            {**independent_gates.P2_BOOLEAN_JDI_DEPENDENCIES,
             "tools/numerical/portable/boolean_rotation_jdi/RotationJdiProbe.java":
             "70990e22075d2c34bc6c03a194291ece66de13c11926494042b93d511f75c712",
             "tools/numerical/portable/boolean_rotation_jdi/jdi_bridge.py":
             "bc6662c300718d82af7eb7b13e089780a8caf41bb43694a90767044c0cda13cb",
             "tools/numerical/portable/boolean_rotation_jdi/loaded_code.py":
             "d76aeb947911108c29fc27b53ec2dced6648c160a78017eaf595a6d41fdb3235",
             "tools/numerical/portable/boolean_rotation_jdi/EndpointControl.java":
             "d32c7dbeb06c3c73f739faf8869ef485b13f853151369cea1d40cdefe6b948dd"},
            independent_gates.P2_BOOLEAN_JDI_FINAL_DEPENDENCIES)
        for revision in (current, assembly):
            for name, digest in independent_gates.P2_BOOLEAN_JDI_FINAL_PRODUCERS.items():
                relative = f"tools/numerical/portable/{name}"
                committed = subprocess.check_output(
                    ["git", "--no-replace-objects", "show", f"{revision}:{relative}"], cwd=ROOT)
                self.assertEqual(digest, hashlib.sha256(committed).hexdigest())
            for relative, digest in independent_gates.P2_BOOLEAN_JDI_FINAL_DEPENDENCIES.items():
                committed = subprocess.check_output(
                    ["git", "--no-replace-objects", "show", f"{revision}:{relative}"], cwd=ROOT)
                self.assertEqual(digest, hashlib.sha256(committed).hexdigest())
        for revision in (current, assembly):
            self.assertEqual(independent_gates.P2_BOOLEAN_JDI_FINAL_PRODUCERS,
                             independent_gates._p2_producer_binding(ROOT, revision))
        with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
            independent_gates._p2_producer_binding(ROOT, parent)
        for revision in ("b1939e1290721a34c8d0901dc6e6981ac9f8d26d",
                         "54505a49c8cbecb416b44e43a6f491b2f4033224",
                         "edd9d5f2e82154b5bfc3df7ba51b66c8dab542c9",
                         "d5683a7474e2379f5aa4d5c29dc49b1b109aa98f"):
            with self.subTest(partial=revision), self.assertRaisesRegex(
                    ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, revision)
        for name, digest in independent_gates.P2_BOOLEAN_JDI_FINAL_PRODUCERS.items():
            relative = f"tools/numerical/portable/{name}"
            local = ROOT / relative
            original_read = Path.read_bytes

            def altered_local(path_value):
                raw = original_read(path_value)
                return raw + b"\n# changed\n" if path_value == local else raw

            with self.subTest(file=name, surface="local"), mock.patch.object(
                    Path, "read_bytes", altered_local):
                with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, current)
            original_show = subprocess.check_output

            def altered_committed(command, *args, **kwargs):
                raw = original_show(command, *args, **kwargs)
                return raw + b"\n# changed\n" if "show" in command and \
                    f"{current}:{relative}" in command else raw

            with self.subTest(file=name, surface="committed"), mock.patch.object(
                    subprocess, "check_output", altered_committed):
                with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, current)
        for relative in independent_gates.P2_BOOLEAN_JDI_FINAL_DEPENDENCIES:
            local = ROOT / relative
            original_read = Path.read_bytes

            def altered_dependency_local(path_value):
                raw = original_read(path_value)
                return raw + b"\n# changed\n" if path_value == local else raw

            with self.subTest(path=relative, surface="local"), mock.patch.object(
                    Path, "read_bytes", altered_dependency_local):
                with self.assertRaisesRegex(ValueError, "Boolean JDI final producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, current)
            original_show = subprocess.check_output

            def altered_dependency_committed(command, *args, **kwargs):
                raw = original_show(command, *args, **kwargs)
                return raw + b"\n# changed\n" if "show" in command and \
                    f"{current}:{relative}" in command else raw

            with self.subTest(path=relative, surface="committed"), mock.patch.object(
                    subprocess, "check_output", altered_dependency_committed):
                with self.assertRaisesRegex(ValueError, "Boolean JDI final producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, current)
        for relative in independent_gates.P2_BOOLEAN_JDI_FINAL_DEPENDENCIES:
            original_show = subprocess.check_output

            def missing_committed(command, *args, **kwargs):
                if "show" in command and f"{current}:{relative}" in command:
                    raise subprocess.CalledProcessError(1, command)
                return original_show(command, *args, **kwargs)

            with self.subTest(path=relative, surface="missing"), mock.patch.object(
                    subprocess, "check_output", missing_committed):
                with self.assertRaises(subprocess.CalledProcessError):
                    independent_gates._p2_producer_binding(ROOT, current)
        for name in independent_gates.P2_BOOLEAN_JDI_FINAL_PRODUCERS:
            relative = f"tools/numerical/portable/{name}"
            local = ROOT / relative
            original_read = Path.read_bytes

            def missing_local(path_value):
                if path_value == local:
                    raise FileNotFoundError(path_value)
                return original_read(path_value)

            with self.subTest(file=name, surface="missing-local"), mock.patch.object(
                    Path, "read_bytes", missing_local):
                with self.assertRaises(FileNotFoundError):
                    independent_gates._p2_producer_binding(ROOT, current)
        for relative in independent_gates.P2_BOOLEAN_JDI_FINAL_DEPENDENCIES:
            local = ROOT / relative
            original_read = Path.read_bytes

            def missing_dependency_local(path_value):
                if path_value == local:
                    raise FileNotFoundError(path_value)
                return original_read(path_value)

            with self.subTest(path=relative, surface="missing-local"), mock.patch.object(
                    Path, "read_bytes", missing_dependency_local):
                with self.assertRaises(FileNotFoundError):
                    independent_gates._p2_producer_binding(ROOT, current)

    def test_p2_boolean_jdi_source_binding_rejects_owned_git_history_mutations(self):
        current = independent_gates.P2_BOOLEAN_JDI_FINAL_SOURCE_REVISION
        relative = "tools/numerical/portable/actual_arithmetic.py"
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)

            def git(*arguments):
                return subprocess.check_output(
                    ["git", "-C", str(repository), *arguments], stderr=subprocess.PIPE,
                    text=True).strip()

            git("init", "--quiet")
            git("fetch", "--quiet", "--no-tags", f"file://{ROOT}", "HEAD")
            git("checkout", "--quiet", "--detach", current)
            self.assertEqual(
                "2c3b33719c03ff2e57ac1eb6739bb248a554ed4efbf4b1e5fa59244e411b54d2",
                hashlib.sha256((repository / relative).read_bytes()).hexdigest())
            self.assertEqual(independent_gates.P2_BOOLEAN_JDI_FINAL_PRODUCERS,
                             independent_gates._p2_producer_binding(repository, current))

            with (repository / relative).open("ab") as source:
                source.write(b"\n# fixture mutation\n")
            git("add", relative)
            git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "alter producer")
            altered = git("rev-parse", "HEAD")
            with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                independent_gates._p2_producer_binding(repository, altered)

            git("checkout", "--quiet", "--orphan", "copied", current)
            git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "copy source tree")
            copied = git("rev-parse", "HEAD")
            self.assertEqual(
                "2c3b33719c03ff2e57ac1eb6739bb248a554ed4efbf4b1e5fa59244e411b54d2",
                hashlib.sha256((repository / relative).read_bytes()).hexdigest())
            with self.assertRaisesRegex(ValueError, "candidate predates reviewed P2 raw producer revision"):
                independent_gates._p2_producer_binding(repository, copied)
            with self.assertRaisesRegex(ValueError, "revision ancestry is unavailable"):
                independent_gates._p2_producer_binding(repository, "0" * 40)

    def test_p2_bounded_jdi_window_binds_helper_and_replays_historical_source(self):
        helper = "tools/numerical/portable/boolean_rotation_jdi/RotationJdiProbe.java"
        revised = "7173d5058ed5524998cc26e3bfc8e8cfb9fa1b86"
        assembly = "48b198fb3fcb23847f345dedbb7e65a8f2ccf3a5"
        historical = "878727b172806fb6cf021a5495f206d145c46e17"
        new_digest = "ebf9cc36aba29df0a0fc39d5aa8813bb5b5b951c36d7a98355d2512bd2f0df8d"
        old_digest = "70990e22075d2c34bc6c03a194291ece66de13c11926494042b93d511f75c712"
        self.assertEqual(revised, independent_gates.P2_BOUNDED_JDI_SOURCE_REVISION)
        self.assertEqual(old_digest, independent_gates.P2_ROTATION_PREMISE_DEPENDENCIES[helper])
        self.assertEqual(new_digest, independent_gates.P2_BOUNDED_JDI_DEPENDENCIES[helper])
        for revision in (revised, assembly):
            with self.subTest(revision=revision):
                self.assertEqual(independent_gates.P2_ROTATION_PREMISE_PRODUCERS,
                                 independent_gates._p2_producer_binding(ROOT, revision))
        self.assertEqual(independent_gates.P2_ROTATION_PREMISE_PRODUCERS,
                         independent_gates._p2_producer_binding(ROOT, historical))

        original_show = subprocess.check_output
        stale = original_show(["git", "--no-replace-objects", "show",
                              f"{historical}:{helper}"], cwd=ROOT)

        def stale_committed(command, *args, **kwargs):
            if "show" in command and f"{assembly}:{helper}" in command:
                return stale
            return original_show(command, *args, **kwargs)

        with mock.patch.object(subprocess, "check_output", stale_committed):
            with self.assertRaisesRegex(ValueError, "bounded JDI producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, assembly)

        revised_bytes = original_show(["git", "--no-replace-objects", "show",
                                       f"{revised}:{helper}"], cwd=ROOT)

        def revised_at_ancestor(command, *args, **kwargs):
            if "show" in command and f"{historical}:{helper}" in command:
                return revised_bytes
            return original_show(command, *args, **kwargs)

        with mock.patch.object(subprocess, "check_output", revised_at_ancestor):
            with self.assertRaisesRegex(ValueError, "rotation premise producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, historical)

        original_read = Path.read_bytes
        local = ROOT / helper
        with mock.patch.object(Path, "read_bytes",
                               lambda path: stale if path == local else original_read(path)):
            with self.assertRaisesRegex(ValueError, "bounded JDI producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, assembly)

    def test_p2_corrected_jdi_bridge_window_binds_only_its_descendants(self):
        bridge = "tools/numerical/portable/boolean_rotation_jdi/jdi_bridge.py"
        current = "e9776f80e1bd5c7f6a3e622d052adaae97c45dfb"
        old = "481ffa64c82045be93da14f89dc4dcc3c3b30f49"
        bounded = independent_gates.P2_BOUNDED_JDI_SOURCE_REVISION
        old_digest = "ffe6d47cca98df6f41bb66a08995ef2b05d1235d1c65aad22540be574e78458e"
        new_digest = "ebd32c6add81e9ea25fdaeac52056db56f428a669f15b9400854ffc5da3d1f61"
        self.assertEqual(current, independent_gates.P2_CORRECTED_JDI_SOURCE_REVISION)
        self.assertEqual(old_digest, independent_gates.P2_BOUNDED_JDI_DEPENDENCIES[bridge])
        self.assertEqual({**independent_gates.P2_BOUNDED_JDI_DEPENDENCIES,
                          bridge: new_digest},
                         independent_gates.P2_CORRECTED_JDI_DEPENDENCIES)
        self.assertEqual(independent_gates.P2_ROTATION_PREMISE_PRODUCERS,
                         independent_gates.APPROVED_P2_LOCAL_PRODUCERS)
        for revision in (current, "HEAD", old, bounded):
            with self.subTest(revision=revision):
                self.assertEqual((independent_gates.APPROVED_P2_PATH_MODEL_PRODUCERS
                                  if revision == "HEAD"
                                  else independent_gates.P2_ROTATION_PREMISE_PRODUCERS),
                                 independent_gates._p2_producer_binding(ROOT, revision))
        for revision in ("aa3cd31465ebcad278001754b9a0f9ab40c4d30a",
                         "0d1acbb7c38fed7e616c85c8efb8e4b29f699908"):
            with self.subTest(incomplete=revision), self.assertRaisesRegex(
                    ValueError, "bounded JDI producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, revision)

        original_show = subprocess.check_output
        stale = original_show(["git", "--no-replace-objects", "show",
                               f"{old}:{bridge}"], cwd=ROOT)
        revised = original_show(["git", "--no-replace-objects", "show",
                                 f"{current}:{bridge}"], cwd=ROOT)
        self.assertEqual(old_digest, hashlib.sha256(stale).hexdigest())
        self.assertEqual(new_digest, hashlib.sha256(revised).hexdigest())

        for revision, substitute in ((current, stale), (old, revised), (bounded, revised),
                                     (current, revised + b"\n# altered\n")):
            def wrong_committed(command, *args, **kwargs):
                if "show" in command and f"{revision}:{bridge}" in command:
                    return substitute
                return original_show(command, *args, **kwargs)

            with self.subTest(wrong_revision=revision, substitute=substitute[:12]), \
                    mock.patch.object(subprocess, "check_output", wrong_committed):
                with self.assertRaisesRegex(ValueError, "JDI producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, revision)

        local = ROOT / bridge
        original_read = Path.read_bytes
        for substitute in (stale, revised + b"\n# altered\n"):
            with self.subTest(local=substitute[:12]), mock.patch.object(
                    Path, "read_bytes",
                    lambda path: substitute if path == local else original_read(path)):
                with self.assertRaisesRegex(ValueError, "corrected JDI producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, current)

        def missing_local(path):
            if path == local:
                raise FileNotFoundError(path)
            return original_read(path)

        with mock.patch.object(Path, "read_bytes", missing_local):
            with self.assertRaises(FileNotFoundError):
                independent_gates._p2_producer_binding(ROOT, current)

        def missing_committed(command, *args, **kwargs):
            if "show" in command and f"{current}:{bridge}" in command:
                raise subprocess.CalledProcessError(1, command)
            return original_show(command, *args, **kwargs)

        with mock.patch.object(subprocess, "check_output", missing_committed):
            with self.assertRaises(subprocess.CalledProcessError):
                independent_gates._p2_producer_binding(ROOT, current)

    def test_p2_jdk21_bridge_window_keeps_prior_lineages_and_rejects_wrong_bytes(self):
        bridge = "tools/numerical/portable/boolean_rotation_jdi/jdi_bridge.py"
        helper = "tools/numerical/portable/boolean_rotation_jdi/RotationJdiProbe.java"
        current = "a50e798e2490e7e74937808405b04f413b9e9dbc"
        previous = "09bee230a1ea6fbd8c748732d1872b3e907a8e0e"
        old = "481ffa64c82045be93da14f89dc4dcc3c3b30f49"
        bounded = independent_gates.P2_BOUNDED_JDI_SOURCE_REVISION
        prior_digest = "ebd32c6add81e9ea25fdaeac52056db56f428a669f15b9400854ffc5da3d1f61"
        new_digest = "bffde8be5655e2a47dea2bd97734d15fc4d46112d032ac432b646c17ab3d611b"
        self.assertEqual(current, independent_gates.P2_JDK21_JDI_SOURCE_REVISION)
        self.assertEqual(prior_digest, independent_gates.P2_CORRECTED_JDI_DEPENDENCIES[bridge])
        self.assertEqual({**independent_gates.P2_CORRECTED_JDI_DEPENDENCIES,
                          bridge: new_digest},
                         independent_gates.P2_JDK21_JDI_DEPENDENCIES)
        self.assertEqual(independent_gates.P2_CORRECTED_JDI_DEPENDENCIES[helper],
                         independent_gates.P2_JDK21_JDI_DEPENDENCIES[helper])
        for revision in (current, "HEAD", previous, old, bounded):
            with self.subTest(revision=revision):
                self.assertEqual((independent_gates.APPROVED_P2_PATH_MODEL_PRODUCERS
                                  if revision == "HEAD"
                                  else independent_gates.P2_ROTATION_PREMISE_PRODUCERS),
                                 independent_gates._p2_producer_binding(ROOT, revision))
        for revision in ("aa3cd31465ebcad278001754b9a0f9ab40c4d30a",
                         "0d1acbb7c38fed7e616c85c8efb8e4b29f699908"):
            with self.subTest(incomplete=revision), self.assertRaisesRegex(
                    ValueError, "bounded JDI producer blob differs"):
                independent_gates._p2_producer_binding(ROOT, revision)

        original_show = subprocess.check_output
        prior_bytes = original_show(["git", "--no-replace-objects", "show",
                                     f"{previous}:{bridge}"], cwd=ROOT)
        current_bytes = original_show(["git", "--no-replace-objects", "show",
                                       f"{current}:{bridge}"], cwd=ROOT)
        self.assertEqual(prior_digest, hashlib.sha256(prior_bytes).hexdigest())
        self.assertEqual(new_digest, hashlib.sha256(current_bytes).hexdigest())

        for revision, substitute in ((current, prior_bytes), (previous, current_bytes),
                                     (old, current_bytes), (bounded, current_bytes),
                                     (current, current_bytes + b"\n# altered\n")):
            def wrong_committed(command, *args, **kwargs):
                if "show" in command and f"{revision}:{bridge}" in command:
                    return substitute
                return original_show(command, *args, **kwargs)

            with self.subTest(wrong_lineage=revision), mock.patch.object(
                    subprocess, "check_output", wrong_committed):
                with self.assertRaisesRegex(ValueError, "JDI producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, revision)

        stale_helper = original_show(["git", "--no-replace-objects", "show",
                                      f"1ef6554b4edb4e6066f5ae16ee64dbeda131d568:{helper}"],
                                     cwd=ROOT)
        for relative, substitute in ((bridge, prior_bytes), (helper, stale_helper),
                                     (bridge, current_bytes + b"\n# altered\n")):
            local = ROOT / relative
            original_read = Path.read_bytes

            def wrong_local(path):
                return substitute if path == local else original_read(path)

            with self.subTest(stale_local=relative), mock.patch.object(
                    Path, "read_bytes", wrong_local):
                with self.assertRaisesRegex(ValueError, "JDI producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, current)

        for relative in (bridge, helper):
            local = ROOT / relative
            original_read = Path.read_bytes

            def missing_local(path):
                if path == local:
                    raise FileNotFoundError(path)
                return original_read(path)

            with self.subTest(missing_local=relative), mock.patch.object(
                    Path, "read_bytes", missing_local):
                with self.assertRaises(FileNotFoundError):
                    independent_gates._p2_producer_binding(ROOT, current)

            def missing_committed(command, *args, **kwargs):
                if "show" in command and f"{current}:{relative}" in command:
                    raise subprocess.CalledProcessError(1, command)
                return original_show(command, *args, **kwargs)

            with self.subTest(missing_committed=relative), mock.patch.object(
                    subprocess, "check_output", missing_committed):
                with self.assertRaises(subprocess.CalledProcessError):
                    independent_gates._p2_producer_binding(ROOT, current)

    def test_p2_reviewed_arithmetic_assembly_rejects_stale_and_altered_bytes(self):
        current = independent_gates.P2_ARITHMETIC_ASSEMBLY_REVISION
        old = independent_gates.APPROVED_P2_COMBINED_PRODUCERS
        for name in ("actual_arithmetic.py", "rotation_oracle.py"):
            relative = f"tools/numerical/portable/{name}"
            local = ROOT / relative
            historical = subprocess.check_output(
                ["git", "--no-replace-objects", "show",
                 f"68339377a5d8dff1fd3dd6bf1ab17a32a0a402cd:{relative}"], cwd=ROOT)
            self.assertEqual(old[name], hashlib.sha256(historical).hexdigest())
            original_read = Path.read_bytes

            def altered_local(path_value):
                raw = original_read(path_value)
                return raw + b"\n# altered\n" if path_value == local else raw

            with self.subTest(name=name, surface="local"), mock.patch.object(
                    Path, "read_bytes", altered_local):
                with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, current)
            with self.subTest(name=name, surface="stale-local"), mock.patch.object(
                    Path, "read_bytes",
                    lambda path_value: historical if path_value == local
                    else original_read(path_value)):
                with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, current)

            original_show = subprocess.check_output

            def altered_committed(command, *args, **kwargs):
                raw = original_show(command, *args, **kwargs)
                if "show" in command and f"{current}:{relative}" in command:
                    return raw + b"\n# altered\n"
                return raw

            with self.subTest(name=name, surface="committed"), mock.patch.object(
                    subprocess, "check_output", altered_committed):
                with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, current)

            def stale_committed(command, *args, **kwargs):
                if "show" in command and f"{current}:{relative}" in command:
                    return historical
                return original_show(command, *args, **kwargs)

            with self.subTest(name=name, surface="stale-committed"), mock.patch.object(
                    subprocess, "check_output", stale_committed):
                with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, current)

            with self.subTest(name=name, surface="stale-current-pin"), mock.patch.dict(
                    independent_gates.APPROVED_P2_ARITHMETIC_PRODUCERS, {name: old[name]}):
                with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, current)
            with self.subTest(name=name, surface="unknown-local-pin"), mock.patch.dict(
                    independent_gates.PINNED_P2_CURRENT_LOCAL_PRODUCERS, {name: "0" * 64}):
                with self.assertRaisesRegex(ValueError, "reviewed P2 raw producer blob differs"):
                    independent_gates._p2_producer_binding(ROOT, current)

    def test_p2_canonical_archive_source_keeps_exact_revision_windows(self):
        source = "tools/numerical/portable/actual_arithmetic.py"
        historical = "e51e768c7d2c9075b9e1900b2bf3ad0fdacbda42bb3eb0d6f52f49492b546675"
        class_load = "b96043c57a918dabe8425961b02aff930a704e592c32baffc5645b94b84ce835"
        canonical = "5f02723e84401f612f4b7a1c72d7686b651e486e5153180ff80e2ec512faa1bf"
        owner = "606e6734613fc90677d3c30cabbf01c6a2e17ae4"
        assembled = "48638f5acca9bf97532ce575809cf5e8472c93f7"
        self.assertEqual("4f2c7abb2cebd528515b7a5a0fd1497fd5511c86",
                         independent_gates.P2_NUMERICAL_ARCHIVE_REVISION)
        self.assertEqual(owner, independent_gates.P2_CANONICAL_ARCHIVE_OWNER_REVISION)
        self.assertEqual(assembled, independent_gates.P2_CANONICAL_ARCHIVE_ASSEMBLY_REVISION)
        current = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                          cwd=ROOT, text=True).strip()
        windows = ((independent_gates.PROSPECTIVE_CHECKER_REVISION, historical),
                   (f"{independent_gates.P2_CLASS_LOAD_REVISION}^", historical),
                   (independent_gates.P2_CLASS_LOAD_REVISION, class_load),
                   (f"{owner}^", class_load), (f"{assembled}^", class_load),
                   (owner, canonical), (assembled, canonical),
                   (independent_gates.P2_NATIVE_02C_ASSEMBLY_REVISION, canonical),
                   (current, independent_gates.APPROVED_P2_OUTPUT_PROVENANCE_PRODUCERS[
                       "actual_arithmetic.py"]))
        for revision, expected in windows:
            with self.subTest(revision=revision):
                committed = subprocess.check_output(["git", "--no-replace-objects", "show",
                                                     f"{revision}:{source}"], cwd=ROOT)
                self.assertEqual(expected, hashlib.sha256(committed).hexdigest())
                for autocrlf in ("false", "true"):
                    with mock.patch.dict(os.environ, {
                            "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.autocrlf",
                            "GIT_CONFIG_VALUE_0": autocrlf}):
                        self.assertEqual(expected, independent_gates._p2_producer_binding(
                            ROOT, revision)["actual_arithmetic.py"])
        with self.assertRaisesRegex(ValueError, "predates reviewed P2 raw producer"):
            independent_gates._p2_producer_binding(
                ROOT, independent_gates.PROSPECTIVE_BRIDGE_CHECKER_REVISION)

    def test_p2_original_object_producer_accepts_only_reviewed_revision_bytes(self):
        owner = "081b7c0be3bf92ffee28668538e61e2fade24081"
        assembled = "8163c24141e49fea7570ffd139fc9a3ad6aca077"
        self.assertEqual("7641de9f0e544a8a29d5d583b91d0fb40029115b",
                         independent_gates.P2_NUMERICAL_ARCHIVE_OWNER_REVISION)
        self.assertEqual(owner, independent_gates.P2_ORIGINAL_OBJECT_OWNER_REVISION)
        self.assertEqual(assembled, independent_gates.P2_ORIGINAL_OBJECT_ASSEMBLY_REVISION)
        previous = {
            "run.py": "d789ab13f68c81c8351a6b91450adf91a7961327f93fbb6969a5ead7de7cf2d0",
            "capture_actual.py": "aa95aa348dc0d78cab30afaf5f4ea4b64d36ab5e3d1e3e0aa35a12a6c6f44e0e",
            "baseline_capture.py": "b7bb228bde030d7fd6949ae3e7ca743a92060b436797835c6e4f7e12d779ad6c",
        }
        reviewed = {
            "run.py": "fd584dee2d88f60d5e3c8abd4b8d040c70365a9024d690d0ba307e039addd233",
            "capture_actual.py": "68080114fe5e9f68d97514a8605e167a5e47328d36948cd239c1d4ca74ab6158",
            "baseline_capture.py": "e4b4977da095744c3478ad6607a3281e4224f1ef83417c13dc88a51c9108bf34",
        }
        windows = ((f"{owner}^", previous), (owner, reviewed),
                   (f"{assembled}^", previous), (assembled, reviewed))
        for revision, expected in windows:
            with self.subTest(revision=revision):
                for name, approved in expected.items():
                    relative = f"tools/numerical/portable/{name}"
                    committed = subprocess.check_output(
                        ["git", "--no-replace-objects", "show", f"{revision}:{relative}"],
                        cwd=ROOT)
                    self.assertEqual(approved, hashlib.sha256(committed).hexdigest())
                for autocrlf in ("false", "true"):
                    with mock.patch.dict(os.environ, {
                            "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.autocrlf",
                            "GIT_CONFIG_VALUE_0": autocrlf}):
                        bound = independent_gates._p2_producer_binding(ROOT, revision)
                        self.assertEqual({name: bound[name] for name in expected}, expected)
        for blobs, revision, stale in (
                (independent_gates.APPROVED_P2_PRE_ORIGINAL_OBJECT_PRODUCERS,
                 f"{assembled}^", reviewed),
                (independent_gates.APPROVED_P2_ORIGINAL_OBJECT_OWNER_PRODUCERS,
                 owner, previous),
                (independent_gates.APPROVED_P2_PRODUCERS,
                 assembled, previous)):
            for name, wrong_digest in stale.items():
                with self.subTest(stale_revision=revision, file=name), mock.patch.dict(
                        blobs, {name: wrong_digest}):
                    with self.assertRaisesRegex(ValueError,
                                                "reviewed P2 raw producer blob differs"):
                        independent_gates._p2_producer_binding(ROOT, revision)

    def test_p2_318_case_policy_requires_attested_method_and_policy_results(self):
        methods = independent_gates.PROSPECTIVE_BRIDGE_METHODS
        ids = independent_gates.approved_prospective_cases(str(ROOT))
        evidence = {method: {"receipt_sha256": hashlib.sha256(method.encode()).hexdigest()}
                    for method in methods}
        rows = [{"id": case_id, "status": "PASSED_NUMERICAL_POLICY",
                 "qualification": "PASSED_CASE_POLICY",
                 "target_arithmetic": "PASSED_BOUND_OPERATION_EVIDENCE",
                 "operation_method": methods[index % len(methods)],
                 "operation_receipt_sha256": evidence[methods[index % len(methods)]]["receipt_sha256"]}
                for index, case_id in enumerate(ids)]
        summary = {"operation_binding": "VERIFIED_ARITHMETIC_BINDING",
                   "operation_evidence": evidence, "results": rows}
        case_methods = {row["id"]: row["operation_method"] for row in rows}
        def checked(value):
            return independent_gates._p2_summary(value, ids, methods, case_methods)
        qualified = checked(summary)
        self.assertEqual("PASSED", qualified["status"])
        self.assertEqual(318, len(qualified["cases"]))
        with self.assertRaisesRegex(ValueError, "receipt differs"):
            checked(
                {**summary, "results": [{**rows[0], "operation_receipt_sha256": "0" * 64},
                                          *rows[1:]]})
        with self.assertRaisesRegex(ValueError, "case identities or order differ"):
            checked({**summary, "results": [rows[0], *rows[:-1]]})
        with self.assertRaisesRegex(ValueError, "order differ"):
            checked({**summary, "results": [rows[1], rows[0], *rows[2:]]})
        with self.assertRaisesRegex(ValueError, "method or receipt differs"):
            checked({**summary, "results": [{**rows[0],
                       "operation_method": methods[1],
                       "operation_receipt_sha256": evidence[methods[1]]["receipt_sha256"]},
                       *rows[1:]]})
        failed = checked(
            {**summary, "results": [{**rows[0], "status": "FAILED_NUMERICAL_POLICY"},
                                      *rows[1:]]})
        self.assertEqual("FAILED", failed["status"])
        incomplete = checked(
            {**summary, "results": [{**rows[0], "target_arithmetic": "UNPASSED"},
                                      *rows[1:]]})
        self.assertEqual("NOT_RUN", incomplete["status"])

    def test_p2_bridge_conditional_adapter_requires_external_scope_and_raw_routes(self):
        candidate = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                            cwd=ROOT, text=True).strip()
        source_sha = independent_gates.verified_numerical_source_sha256(ROOT, candidate)
        artifact_sha = "a" * 64
        methods = independent_gates.PROSPECTIVE_BRIDGE_METHODS
        ids = independent_gates.approved_prospective_cases(str(ROOT))
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            root = parent / "archive"
            root.mkdir()
            sidecar = parent / "attestation.json"
            sidecar.write_text('{"schema":"synthetic-test-only"}')
            attest_sha = hashlib.sha256(sidecar.read_bytes()).hexdigest()
            entries = []
            for method in methods:
                path = root / f"{method}.json"
                path.write_text(json.dumps({
                    "schema": "portable-arithmetic-capture-receipt/3",
                    "method": method, "candidate_commit": candidate,
                    "source_archive_sha256": source_sha,
                    "artifact_sha256": artifact_sha}))
                entries.append({"method": method, "receipt": path.name,
                                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            inventory = {"schema": "prospective-arithmetic-bridge/1",
                         "candidate_sha": candidate, "source_sha256": source_sha,
                         "artifact_sha256": artifact_sha, "case_ids": list(ids),
                         "methods": entries, "baseline_attestation_sha256": attest_sha}
            inventory_path = root / "bridge.json"
            inventory_path.write_text(json.dumps(inventory))
            bridge = {"inventory": inventory_path.name,
                      "inventory_sha256": hashlib.sha256(inventory_path.read_bytes()).hexdigest(),
                      "baseline": "baseline", "candidate": "candidate",
                      "arithmetic": "arithmetic"}
            receipt = {"prospective_bridge": bridge}
            verified_runtime = {"host": "jvm", "os": "test-host", "machine": "x86_64",
                                "device": False, "executable": str(parent / "jdk21/bin/java"),
                                "executable_sha256": "e" * 64,
                                "version": 'openjdk version "21.0.1"',
                                "method_executions": 15,
                                "dependency_sha256": artifact_sha,
                                "method_process_sha256": "f" * 64}
            verified_identity = independent_gates._p2_runtime_identity(verified_runtime)
            self.assertEqual(independent_gates.digest(
                {"schema": "reviewed-p2-runtime/1", "runtime": verified_runtime}),
                verified_identity)
            scope = {"candidate_sha": candidate, "target": "jvm", "runtime": "Java",
                     "runtime_identity": verified_identity, "artifact_hashes": {
                         "dyn4k-core": artifact_sha, "dyn4k": "c" * 64},
                     "source_sha256": source_sha,
                     "baseline_attestation_path": str(sidecar),
                     "baseline_attestation_sha256": attest_sha}
            self.assertEqual("NOT_RUN", independent_gates.verify_pending_prospective_bridge(
                root, receipt, ROOT, candidate, artifact_sha, source_sha)["status"])
            with self.assertRaisesRegex(independent_gates.IncompleteEvidence,
                                        "prospective raw directory is missing"):
                independent_gates.verify_pending_prospective_bridge(
                    root, receipt, ROOT, candidate, artifact_sha, source_sha, scope)
            for directory in ("baseline", "candidate", "arithmetic"):
                (root / directory).mkdir()
            with mock.patch.object(independent_gates, "_verify_p2_host",
                                   return_value=({"operation_binding":
                                                  "VERIFIED_ARITHMETIC_BINDING",
                                                  "candidate_artifact_sha256": {
                                                      "target": artifact_sha,
                                                      "metadata": "c" * 64},
                                                  "operation_evidence": {
                                                      method: {"receipt_sha256": "d" * 64}
                                                      for method in methods},
                                                  "results": [
                                                      {"id": case_id,
                                                       "status": "PASSED_NUMERICAL_POLICY",
                                                       "qualification": "PASSED_CASE_POLICY",
                                                       "target_arithmetic":
                                                       "PASSED_BOUND_OPERATION_EVIDENCE",
                                                       "operation_method": methods[0],
                                                       "operation_receipt_sha256": "d" * 64}
                                                      for case_id in ids]}, list(ids),
                                                 {case_id: methods[0] for case_id in ids},
                                                 verified_identity)):
                self.assertEqual("PASSED", independent_gates.verify_pending_prospective_bridge(
                    root, receipt, ROOT, candidate, artifact_sha, source_sha, scope)["status"])
                self.assertEqual(verified_identity, independent_gates.verify_pending_prospective_bridge(
                    root, receipt, ROOT, candidate, artifact_sha, source_sha, scope)["runtime_identity"])
                for forged in ({**verified_runtime, "executable_sha256": "0" * 64},
                               {**verified_runtime, "method_process_sha256": "0" * 64}):
                    forged_identity = independent_gates._p2_runtime_identity(forged)
                    self.assertNotEqual(verified_identity, forged_identity)
                    with self.assertRaisesRegex(ValueError, "runtime identity differs"):
                        independent_gates.verify_pending_prospective_bridge(
                            root, receipt, ROOT, candidate, artifact_sha, source_sha,
                            {**scope, "runtime_identity": forged_identity})
                with self.assertRaisesRegex(ValueError, "metadata JAR differs"):
                    independent_gates.verify_pending_prospective_bridge(
                        root, receipt, ROOT, candidate, artifact_sha, source_sha,
                        {**scope, "artifact_hashes": {**scope["artifact_hashes"],
                                                     "dyn4k": "0" * 64}})
            for malformed in ({**verified_runtime, "method_executions": 14},
                              {**verified_runtime, "method_process_sha256": "missing"},
                              {**verified_runtime, "host": "node-js"}):
                with self.assertRaisesRegex(ValueError, "runtime/process proof is incomplete"):
                    independent_gates._p2_runtime_identity(malformed)
            for bad in ({**scope, "source_sha256": "0" * 64},
                        {**scope, "artifact_hashes": {**scope["artifact_hashes"],
                                                     "dyn4k-core": "0" * 64}},
                        {**scope, "baseline_attestation_sha256": "0" * 64}):
                with self.assertRaises(ValueError):
                    independent_gates.verify_pending_prospective_bridge(
                        root, receipt, ROOT, candidate, artifact_sha, source_sha, bad)
            with self.assertRaisesRegex(independent_gates.IncompleteEvidence,
                                        "baseline_attestation_path"):
                independent_gates.verify_pending_prospective_bridge(
                    root, receipt, ROOT, candidate, artifact_sha, source_sha,
                    {key: value for key, value in scope.items()
                     if key != "baseline_attestation_path"})

    @unittest.skipUnless(Path("/var/home/stewart/dyn4k-evidence/portable-p2-bridge-6040b402-free-motion-check/capture.xml").is_file(),
                         "retained real arithmetic capture is absent")
    def test_retained_real_p2_method_replays_raw_operations_but_not_full_gate(self):
        source = Path("/var/home/stewart/dyn4k-evidence/portable-p2-bridge-6040b402-free-motion-check")
        sys.path.insert(0, str(ROOT / "tools/numerical/portable"))
        try:
            arithmetic = reviewed_arithmetic_at("6040b40265975b9091db430d79269cb5ea3d9868")
            CaptureRejected = arithmetic.CaptureRejected
            expected_case_ids = arithmetic.expected_case_ids
            verify_capture = arithmetic.verify_capture
            raw = (source / "capture.xml").read_bytes()
            summary = verify_capture(raw, "captureFreeMotion",
                                     expected_case_ids()["captureFreeMotion"])
            self.assertEqual("VERIFIED_ARITHMETIC_BINDING", summary["status"])
            self.assertEqual(10, summary["cases"])
            self.assertEqual(6900, summary["steps"])
            self.assertEqual(0, summary["pair_inputs_unbound"])
            with self.assertRaises(CaptureRejected):
                verify_capture(raw.replace(b"NUMERICAL_JSON ", b"NUMERICAL_JSONX ", 1),
                               "captureFreeMotion", expected_case_ids()["captureFreeMotion"])
            failed = Path("/var/home/stewart/dyn4k-evidence/portable-p2-bridge-6040b402-angle-check-with-sdk/capture.xml")
            if failed.is_file():
                with self.assertRaisesRegex(CaptureRejected, "nonfinite binary64 field"):
                    verify_capture(failed.read_bytes(), "captureAngleFailure",
                                   expected_case_ids()["captureAngleFailure"])
        finally:
            sys.path.pop(0)

    @unittest.skipUnless(
        all(Path(f"/var/home/stewart/dyn4k-evidence/prospective-actual/"
                 f"ffdc8ba-hooks-order-{route}/receipt.json").is_file()
            for route in ("geometry", "ccd")),
        "reviewed exact-commit arithmetic receipts are absent")
    def test_reviewed_p2_class_load_receipts_replay_without_qualification(self):
        producer_root = Path("/var/home/stewart/Workspace/dyn4k-port-rotation-hooks-isolation")
        staged_jar = (producer_root / "build/staging-repository/io/github/rubixhacker/"
                      "dyn4k-core-jvm/0.1.0-alpha.1/dyn4k-core-jvm-0.1.0-alpha.1.jar")
        if not staged_jar.is_file():
            self.skipTest("reviewed producer's same-source staged JAR is absent")
        source = Path("/var/home/stewart/dyn4k-evidence/prospective-actual")
        filenames = {"xml": "capture.xml", "stage_log": "stage.log",
                     "gradle_log": "gradle.log", "execve_log": "execve.log",
                     "artifact": "artifact.jar", "runtime": "runtime-java",
                     "source": "source.tar", "worker_classpath": "worker-classpath.txt",
                     "portable_classes": "portable-classes.zip"}
        sys.path.insert(0, str(ROOT / "tools/numerical/portable"))
        try:
            arithmetic = reviewed_arithmetic_at("ffdc8ba9b600732e6927e38e7d3da43a519994a4")
            with (mock.patch.object(arithmetic, "_ROOT", producer_root),
                  mock.patch.object(arithmetic, "_STAGED_JAR", staged_jar)):
                for name, count, resets in (("ffdc8ba-hooks-order-geometry", 75, 0),
                                            ("ffdc8ba-hooks-order-ccd", 12, 6)):
                    with self.subTest(archive=name):
                        archive = source / name
                        receipt = json.loads((archive / "receipt.json").read_text())
                        files = {key: (archive / filename).read_bytes()
                                 for key, filename in filenames.items()}
                        files["worker_class_load"] = next(
                            archive.glob("worker-class-load-*.log")).read_bytes()
                        summary = arithmetic.verify_capture_receipt(
                            receipt, files, receipt["method"], receipt["candidate_commit"],
                            arithmetic.expected_case_ids()[receipt["method"]],
                            receipt["runtime_executable"])
                        self.assertEqual("VERIFIED_ARITHMETIC_BINDING", summary["status"])
                        self.assertEqual("UNPASSED", summary["qualification"])
                        self.assertEqual((count, resets),
                                         (summary["cases"], summary["selected_resets"]))
                        if resets:
                            changed = dict(files)
                            changed["worker_class_load"] = b"".join(
                                row for row in files["worker_class_load"].splitlines(keepends=True)
                                if b"org.dyn4j.world.ToiAcceptedResetTap " not in row)
                            with self.assertRaises(arithmetic.CaptureRejected):
                                arithmetic.verify_capture_receipt(
                                    receipt, changed, receipt["method"],
                                    receipt["candidate_commit"],
                                    arithmetic.expected_case_ids()[receipt["method"]],
                                    receipt["runtime_executable"])
        finally:
            sys.path.pop(0)

    def test_prospective_arithmetic_requires_raw_target_process_and_oracle_pin(self):
        case = "geometry-boundary-s0-o0-d0"
        candidate = independent_gates.PROSPECTIVE_POLICY_REVISION
        source_sha = independent_gates.verified_numerical_source_sha256(ROOT, candidate)
        identity = {"case_id": case, "candidate_commit": candidate,
                    "source_sha256": source_sha, "artifact_sha256": "a" * 64,
                    "trace_sha256": "b" * 64}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, "arithmetic producer manifest"):
                independent_gates._target_arithmetic_evidence(root, identity, identity, ROOT)
            payload = root / "target-payload.json"
            payload.write_text(json.dumps({"case_id": case, "runtime": "Java 21",
                                           "operations": [{"kind": "binary64", "value": "0"}]}))
            output = root / "target-stdout.txt"
            output.write_text(f"ARITHMETIC_CASE={case}\n")
            process = root / "target-process.json"
            process.write_text(json.dumps({"command": ["java", "CandidateArithmetic"],
                                           "exit_code": 0, "started_ns": 1,
                                           "finished_ns": 2, "stdout": output.name,
                                           "stdout_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}))
            audit = {**identity, "schema": "target-arithmetic-evidence/1",
                     "oracle_revision": independent_gates.ROTATION_ORACLE_REVISION,
                     "oracle_sha256": independent_gates.ROTATION_ORACLE_SHA256,
                     "target_payload": payload.name,
                     "target_payload_sha256": hashlib.sha256(payload.read_bytes()).hexdigest(),
                     "process_receipt": process.name,
                     "process_receipt_sha256": hashlib.sha256(process.read_bytes()).hexdigest()}
            self.assertEqual("NOT_RUN", independent_gates._target_arithmetic_evidence(
                root, audit, identity, ROOT))
            audit["oracle_sha256"] = "f" * 64
            with self.assertRaisesRegex(ValueError, "approved arithmetic oracle"):
                independent_gates._target_arithmetic_evidence(root, audit, identity, ROOT)
            audit["oracle_sha256"] = independent_gates.ROTATION_ORACLE_SHA256
            audit["oracle"] = {"binding": "missing.json"}
            with self.assertRaisesRegex(ValueError, "oracle raw contract"):
                independent_gates._target_arithmetic_evidence(root, audit, identity, ROOT)
            files = {"binding": "binding.json", "receipt": "producer.json",
                     "target_source": "source.kt", "artifact": "core.jar"}
            for name in files.values():
                (root / name).write_bytes(b"raw arithmetic producer bytes")
            audit["oracle"] = {"target_source_git_path": "README.md"}
            for key, name in files.items():
                audit["oracle"][key] = name
                audit["oracle"][key + "_sha256"] = hashlib.sha256(
                    (root / name).read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "artifact differs"):
                independent_gates._target_arithmetic_evidence(root, audit, identity, ROOT)
            audit["oracle"]["binding_sha256"] = "e" * 64
            with self.assertRaisesRegex(ValueError, "oracle binding differs"):
                independent_gates._target_arithmetic_evidence(root, audit, identity, ROOT)
            oracle = independent_gates._rotation_oracle_module(str(ROOT))
            self.assertEqual("UNPASSED", oracle.verify_rotation_arithmetic(
                {}, {"id": case}, {}, {}, 0)["status"])

    def test_joint_adapter_rejects_reported_pass_without_both_raw_cases(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "36,000-step candidate Weld and Pulley"):
                independent_gates.verify_joint_physical_cases(
                    Path(temporary), {"status": "PASSED"}, BASE,
                    {"dyn4k-core": "a" * 64},
                    independent_gates.verified_numerical_source_sha256(ROOT, BASE))

    def test_performance_global_scope_binds_own_jvm_binaries_before_raw_audit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            started = time.time_ns() - 1_000_000
            (root / "stdout.txt").write_text("performance runner started\n")
            os.utime(root / "stdout.txt", ns=(started + 1_000_000, started + 1_000_000))
            observed_mtime = (root / "stdout.txt").stat().st_mtime_ns
            scope = {"candidate_sha": BASE, "target": "jvm", "runtime": "Java",
                     "runtime_identity": "JDK 21 benchmark host",
                     "artifact_hashes": {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64},
                     "producer_manifest_hashes": {
                         "evidence/candidate-identity-at-pilot.json": "f" * 64}}
            receipt = {"schema": 1, "status": "PASSED", "candidate_sha": BASE,
                       "source_tree": subprocess.check_output(
                           ["git", "rev-parse", f"{BASE}^{{tree}}"], cwd=ROOT, text=True).strip(),
                       "lane": None, "runtime_identity": scope["runtime_identity"],
                       "artifact_hashes": scope["artifact_hashes"], "producer_scope": scope,
                       "process": {"command": ["python3", "tools/performance/verify_candidate_archive.py"],
                                   "exit_code": 0, "started_ns": started,
                                   "finished_ns": started + 2_000_000, "stdout": "stdout.txt"},
                       "files": [{"path": "stdout.txt",
                                  "sha256": hashlib.sha256((root / "stdout.txt").read_bytes()).hexdigest(),
                                  "mtime_ns": observed_mtime}]}
            (root / "receipt.json").write_text(json.dumps(receipt))
            pin = independent_gates.archive_digest(root)

            def checked(selected):
                return independent_gates.evaluate(
                    self.manifest, BASE, "linuxX64:Linux x64:minimum:debug-g",
                    {"performance-resource": root}, ROOT,
                    {"dyn4k-core": "c" * 64, "dyn4k": "d" * 64},
                    "native runner", {"performance-resource": pin},
                    expected_producer_scopes={"performance-resource": selected})[
                        "gates"]["performance-resource"]

            self.assertEqual("FAILED", checked(scope)["status"])
            self.assertIn("evidence", checked(scope)["reason"])
            wrong = {**scope, "artifact_hashes": {"dyn4k-core": "e" * 64,
                                                      "dyn4k": "b" * 64}}
            self.assertIn("producing artifact/runtime scope",
                          checked(wrong)["reason"])
            wrong_sha = {**scope, "candidate_sha": "f" * 40}
            self.assertIn("producing source commit", checked(wrong_sha)["reason"])

    @unittest.skipUnless(
        Path("/tmp/dyn4k-candidate-exact-weld-physical.jsonl").is_file()
        and Path("/tmp/dyn4k-candidate-exact-pulley-physical.jsonl").is_file(),
        "retained real candidate Weld/Pulley traces are absent")
    def test_joint_physical_adapter_replays_real_36000_step_captures(self):
        candidate = "c390dd9208988b523d5fd886c6eb9c28dd7a5362"
        source_sha = independent_gates.verified_numerical_source_sha256(ROOT, candidate)
        artifact = "b6986afbab28c9410ad471abdde038103a9acd6d161750d601f4a61de8efbd4d"
        rows = [{"case": case, "candidate": f"dyn4k-candidate-exact-{name}-physical.jsonl",
                 "capture_receipt": f"dyn4k-candidate-exact-{name}-physical-receipt.json"}
                for case, name in (("weld-spring-equal", "weld"), ("pulley-taut", "pulley"))]
        verified = independent_gates.verify_joint_physical_cases(
            Path("/tmp"), {"joint_physical_cases": rows}, candidate,
            {"dyn4k-core": artifact}, source_sha)
        self.assertEqual("PASSED", verified["candidate_status"])
        self.assertEqual({"anchor_gap_m": 0, "angular_error_rad": 0},
                         verified["failures"]["weld-spring-equal"])
        self.assertEqual({"absolute_rope_error_m": 0},
                         verified["failures"]["pulley-taut"])
        with self.assertRaisesRegex(ValueError, "candidate physical capture identity"):
            independent_gates.verify_joint_physical_cases(
                Path("/tmp"), {"joint_physical_cases": rows}, candidate,
                {"dyn4k-core": "e" * 64}, source_sha)
        with tempfile.TemporaryDirectory() as temporary:
            altered_root = Path(temporary)
            for row in rows:
                for field in ("candidate", "capture_receipt"):
                    shutil.copy2(Path("/tmp") / row[field], altered_root / row[field])
            weld = altered_root / rows[0]["candidate"]
            raw = weld.read_bytes()
            header, remainder = raw.split(b"\n", 1)
            changed = json.loads(header)
            changed["source_revision"] = BASE
            weld.write_bytes(json.dumps(changed).encode() + b"\n" + remainder)
            capture = altered_root / rows[0]["capture_receipt"]
            resealed = json.loads(capture.read_text())
            resealed["trace_sha256"] = hashlib.sha256(weld.read_bytes()).hexdigest()
            capture.write_text(json.dumps(resealed))
            with self.assertRaisesRegex(ValueError, "candidate physical input or source identity"):
                independent_gates.verify_joint_physical_cases(
                    altered_root, {"joint_physical_cases": rows}, candidate,
                    {"dyn4k-core": artifact}, source_sha)

    def test_physical_gate_keeps_default_reference_failure_and_port_gap_separate(self):
        physical = independent_gates.evaluate(
            self.manifest, BASE, LANE, {}, ROOT)["gates"]["physical-correctness"]
        self.assertEqual("NOT_RUN", physical["status"])
        self.assertEqual("FAILED_125847_OF_126000",
                         physical["profiles"]["default-sleep-wake"]["approved_reference_status"])
        for profile in ("default-sleep-wake", "configured-sleep-wake",
                        "weld-pulley", "nominal"):
            self.assertEqual("NOT_RUN", physical["profiles"][profile]["candidate_status"])

    def test_publication_audit_requires_all_21_target_binary_hashes(self):
        targets = {row["target"] for row in qualify.matrix()}
        self.assertEqual(21, len(targets))
        hashes = {target: {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64}
                  for target in targets}
        self.assertEqual(hashes, independent_gates._validated_all_target_hashes(hashes))
        del hashes[next(target for target in targets if target != "jvm")]
        with self.assertRaisesRegex(ValueError, "21-target"):
            independent_gates._validated_all_target_hashes(hashes)

    def test_publication_compares_unselected_target_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = root / "staged"
            staging.mkdir()
            hashes = {}
            targets = {row["target"] for row in qualify.matrix()}
            for target in targets:
                hashes[target] = {}
                for module in qualify.MODULES:
                    path = staging / qualify.target_binary_path(module, target)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(f"{target}/{module}".encode())
                    hashes[target][module] = hashlib.sha256(path.read_bytes()).hexdigest()
            lane = self.manifest["lanes"][LANE]
            with mock.patch.object(qualify, "audit_staging", return_value={"status": "PASSED", "artifacts": []}):
                self.assertIn("full staged audit verified",
                              independent_gates._staged_publication(
                                  root, BASE, lane, hashes["jvm"], ROOT, hashes))
                target = next(target for target in targets if target != "jvm")
                (staging / qualify.target_binary_path("dyn4k-core", target)).write_bytes(b"mutated")
                with self.assertRaisesRegex(ValueError, "independent audit"):
                    independent_gates._staged_publication(
                        root, BASE, lane, hashes["jvm"], ROOT, hashes)

    def test_jvm_mode_pairs_keep_canonical_publication_gates_separate(self):
        archive_root = Path(
            "/var/home/stewart/dyn4k-evidence/session-control/"
            "full-jvm-d50-p1-p2-sol-work/archive")
        source = Path(
            "/var/home/stewart/dyn4k-evidence/session-control/"
            "full-jvm-d50-p1-p2-sol-work/final-candidate")
        modes = ("default", "no-optimize")
        if not source.is_dir() or any(not (archive_root / f"jvm-{mode}-final").is_dir()
                                      for mode in modes):
            self.skipTest("retained exact10e JVM mode publications are unavailable")
        candidate = "10e78648d4b63083e89f6543896dd07794be7b87"
        lanes = {mode: f"jvm:Java:minimum:{mode}" for mode in modes}
        measured = {}
        for mode in modes:
            publication = archive_root / f"jvm-{mode}-final"
            pair = {module: hashlib.sha256((
                publication / "staged" / qualify.target_binary_path(module, "jvm"))
                .read_bytes()).hexdigest() for module in qualify.MODULES}
            binding = {"candidate_sha": candidate, "lane": lanes[mode], "mode": mode,
                       "source": "compiler_modes.replay", "source_checkout": str(source),
                       "publication_archive": str(publication),
                       "archive_digest": independent_gates.archive_digest(publication),
                       "artifact_hashes": pair}
            case = {"id": lanes[mode], "target": "jvm", "configuration": mode}
            self.assertTrue(qualify.verify_jvm_mode_publication(
                binding, case, candidate, pair))
            measured[mode] = pair
        self.assertNotEqual(measured["default"], measured["no-optimize"])
        targets = {row["target"] for row in qualify.matrix()}
        canonical_bytes = {target: {module: f"canonical:{target}:{module}".encode()
                                    for module in qualify.MODULES} for target in targets}
        canonical = {target: {module: hashlib.sha256(data).hexdigest()
                              for module, data in modules.items()}
                     for target, modules in canonical_bytes.items()}
        tree = subprocess.check_output(
            ["git", "rev-parse", f"{candidate}^{{tree}}"], cwd=ROOT, text=True).strip()

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def archive(name, pair, lane_id=None, staged=False):
                path = root / name
                path.mkdir()
                if staged:
                    for target, modules in canonical_bytes.items():
                        for module, data in modules.items():
                            binary = path / "staged" / qualify.target_binary_path(module, target)
                            binary.parent.mkdir(parents=True, exist_ok=True)
                            binary.write_bytes(data)
                markers = lanes.values() if lane_id is None else (lane_id,)
                (path / "stdout.txt").write_text(
                    "".join(f"QUALIFICATION_LANE={item}\n" for item in markers)
                    + "> Task :publish\nBUILD SUCCESSFUL\n")
                started = time.time_ns() - 10_000_000
                mtime = started + 1_000_000
                files = sorted(item for item in path.rglob("*") if item.is_file())
                for item in files:
                    os.utime(item, ns=(mtime, mtime))
                receipt = {"schema": 1, "status": "PASSED" if staged else "NOT_RUN",
                           "candidate_sha": candidate, "source_tree": tree,
                           "artifact_hashes": pair,
                           "process": {"command": ["./gradlew", ":publish"],
                                       "exit_code": 0, "stdout": "stdout.txt",
                                       "started_ns": started, "finished_ns": started + 2_000_000},
                           "files": [{"path": item.relative_to(path).as_posix(),
                                      "sha256": hashlib.sha256(item.read_bytes()).hexdigest(),
                                      "mtime_ns": item.stat().st_mtime_ns} for item in files]}
                if lane_id is not None:
                    lane = self.manifest["lanes"][lane_id]
                    receipt.update(lane=lane_id, runtime_identity="fixture runtime",
                                   **{key: lane[key] for key in
                                      ("target", "runtime", "version", "configuration")})
                (path / "receipt.json").write_text(json.dumps(receipt))
                return path

            publication = archive("publication", canonical["jvm"], staged=True)
            stages = {mode: archive(f"stage-{mode}", canonical["jvm"],
                                    lanes[mode], staged=True) for mode in modes}
            consumers = {mode: archive(f"consumer-{mode}", measured[mode], lanes[mode])
                         for mode in modes}
            audited_stage = {"status": "PASSED", "errors": [], "artifacts": []}

            def gates(mode, lane_pair, all_targets=canonical):
                paths = {"staged-artifacts": stages[mode],
                         "publication-contract": publication,
                         "staged-consumer": consumers[mode]}
                digests = {gate: independent_gates.archive_digest(path)
                           for gate, path in paths.items()}
                with mock.patch.object(qualify, "audit_staging", return_value=audited_stage):
                    return independent_gates.evaluate(
                        self.manifest, candidate, lanes[mode], paths, ROOT,
                        lane_pair, "fixture runtime", digests, all_targets)["gates"]

            publication_archives = set()
            for mode in modes:
                with self.subTest(mode=mode):
                    result = gates(mode, measured[mode])
                    self.assertEqual("PASSED", result["staged-artifacts"]["status"])
                    self.assertEqual("PASSED", result["publication-contract"]["status"])
                    publication_archives.add(result["publication-contract"]["archive_sha256"])
                    self.assertEqual("NOT_RUN", result["staged-consumer"]["status"])
                    other = "no-optimize" if mode == "default" else "default"
                    swapped = gates(mode, measured[other])
                    self.assertEqual("FAILED", swapped["staged-consumer"]["status"])
                    canonical_swap = gates(mode, canonical["jvm"])
                    self.assertEqual("FAILED", canonical_swap["staged-consumer"]["status"])
            self.assertEqual(1, len(publication_archives))
            wrong_map = {**canonical, "jvm": measured["default"]}
            wrong = gates("default", measured["default"], wrong_map)
            self.assertEqual("FAILED", wrong["staged-artifacts"]["status"])
            self.assertEqual("FAILED", wrong["publication-contract"]["status"])
            missing = gates("default", measured["default"], None)
            self.assertEqual("FAILED", missing["staged-artifacts"]["status"])
            self.assertEqual("FAILED", missing["publication-contract"]["status"])

    def test_duplicate_provider_requires_raw_graph_and_diagnostic(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            graph = "org.dyn4j:dyn4j:6.0.0\nio.github.rubixhacker:dyn4k-core-jvm:0.1.0-alpha.1\n"
            (root / "graph.txt").write_text(graph)
            (root / "stderr.txt").write_text(
                "duplicate org.dyn4j provider: exclude org.dyn4j:dyn4j\n")
            (root / "stdout.txt").write_text(
                f"QUALIFICATION_LANE={LANE}\n> Task :diagnoseDuplicateProviders\nBUILD FAILED\n"
                f"QUALIFICATION_PROVIDER_GRAPH_SHA256={hashlib.sha256((root / 'graph.txt').read_bytes()).hexdigest()}\n")
            started = time.time_ns() - 1_000_000
            finished = time.time_ns() + 1_000_000
            artifact_hashes = {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64}
            receipt = {
                "schema": 1, "status": "PASSED", "candidate_sha": BASE,
                "source_tree": subprocess.check_output(
                    ["git", "rev-parse", f"{BASE}^{{tree}}"], cwd=ROOT, text=True).strip(),
                "lane": LANE, "target": "jvm", "runtime": "Java",
                "version": "minimum", "configuration": "no-optimize",
                "runtime_identity": "OpenJDK 8 test fixture", "artifact_hashes": dict(artifact_hashes),
                "process": {"command": ["./gradlew", "diagnoseDuplicateProviders"],
                            "exit_code": 1, "started_ns": started,
                            "finished_ns": finished, "stderr": "stderr.txt",
                            "stdout": "stdout.txt"},
                "provider_graph": "graph.txt",
                "files": [{"path": name,
                           "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest(),
                           "mtime_ns": started + 1}
                          for name in ("graph.txt", "stderr.txt", "stdout.txt")],
            }
            for name in ("graph.txt", "stderr.txt", "stdout.txt"):
                os.utime(root / name, ns=(started + 1_000_000, started + 1_000_000))
            for file in receipt["files"]:
                file["mtime_ns"] = (root / file["path"]).stat().st_mtime_ns
            (root / "receipt.json").write_text(json.dumps(receipt))

            def status():
                try:
                    pin = independent_gates.archive_digest(root)
                except ValueError:
                    pin = "0" * 64
                return independent_gates.evaluate(
                    self.manifest, BASE, LANE, {"duplicate-provider": root}, ROOT,
                    artifact_hashes, "OpenJDK 8 test fixture",
                    {"duplicate-provider": pin})["gates"]["duplicate-provider"]

            self.assertEqual("PASSED", status()["status"])
            receipt["process"]["command"] = ["echo", "diagnoseDuplicateProviders"]
            (root / "receipt.json").write_text(json.dumps(receipt))
            self.assertEqual("FAILED", status()["status"])
            with tempfile.TemporaryDirectory() as audit_temporary:
                audit = Path(audit_temporary)
                (audit / "hashes.json").write_text(json.dumps(artifact_hashes))
                (audit / "digests.json").write_text(json.dumps({
                    "duplicate-provider": independent_gates.archive_digest(root)}))
                cli = subprocess.run([
                    sys.executable, str(ROOT / "tools/qualification/independent_gates.py"),
                    "--repository", str(ROOT), "--candidate-sha", BASE,
                    "--lane", LANE, "--expected-artifacts", str(audit / "hashes.json"),
                    "--expected-archive-digests", str(audit / "digests.json"),
                    "--expected-runtime-identity", "OpenJDK 8 test fixture",
                    "--archive", f"duplicate-provider={root}"], capture_output=True, text=True)
                self.assertEqual(1, cli.returncode)
                self.assertIn("execution launcher",
                              json.loads(cli.stdout)["gates"]["duplicate-provider"]["reason"])
            receipt["process"]["command"] = ["./gradlew", "diagnoseDuplicateProviders"]
            (root / "receipt.json").write_text(json.dumps(receipt))
            receipt["artifact_hashes"]["dyn4k-core"] = "0" * 64
            (root / "receipt.json").write_text(json.dumps(receipt))
            self.assertEqual("FAILED", status()["status"])
            receipt["artifact_hashes"]["dyn4k-core"] = "a" * 64
            receipt["source_tree"] = "0" * 40
            (root / "receipt.json").write_text(json.dumps(receipt))
            self.assertEqual("FAILED", status()["status"])
            receipt["source_tree"] = subprocess.check_output(
                ["git", "rev-parse", f"{BASE}^{{tree}}"], cwd=ROOT, text=True).strip()
            (root / "graph.txt").write_text("org.dyn4j:dyn4j:6.0.0\n")
            self.assertEqual("FAILED", status()["status"])
            (root / "graph.txt").write_text(graph)
            receipt["files"][0]["mtime_ns"] = finished + 1
            (root / "receipt.json").write_text(json.dumps(receipt))
            self.assertEqual("FAILED", status()["status"])
            receipt["files"][0]["mtime_ns"] = (root / "graph.txt").stat().st_mtime_ns
            receipt["files"].append(dict(receipt["files"][0]))
            (root / "receipt.json").write_text(json.dumps(receipt))
            self.assertEqual("FAILED", status()["status"])
            receipt["files"].pop()
            (root / "link.txt").symlink_to(root / "graph.txt")
            (root / "receipt.json").write_text(json.dumps(receipt))
            self.assertEqual("FAILED", status()["status"])
            (root / "link.txt").unlink()
            receipt["lane"] = "jvm:Java:minimum:default"
            (root / "receipt.json").write_text(json.dumps(receipt))
            self.assertEqual("FAILED", status()["status"])
            receipt["lane"] = LANE
            receipt["candidate_sha"] = "f" * 40
            (root / "receipt.json").write_text(json.dumps(receipt))
            self.assertEqual("FAILED", status()["status"])
            receipt["candidate_sha"] = BASE
            receipt["files"][0]["path"] = "../graph.txt"
            (root / "receipt.json").write_text(json.dumps(receipt))
            self.assertEqual("FAILED", status()["status"])

    def test_every_route_rejects_reported_green_without_raw_contract(self):
        names = (set(self.manifest["lanes"][LANE]["required_gates"])
                 | set(self.manifest["global_gates"]))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "receipt.json").write_text(json.dumps({"status": "PASSED"}))
            for gate in names:
                with self.subTest(gate=gate):
                    observed = independent_gates.evaluate(
                        self.manifest, BASE, LANE, {gate: root}, ROOT,
                        expected_archive_digests={gate: independent_gates.archive_digest(root)})
                    self.assertEqual("FAILED", observed["gates"][gate]["status"])

    def test_every_route_rejects_wrong_lane_and_candidate(self):
        names = (set(self.manifest["lanes"][LANE]["required_gates"])
                 | set(self.manifest["global_gates"]))
        all_hashes = {row["target"]: {"dyn4k-core": "a" * 64,
                                      "dyn4k": "b" * 64}
                      for row in qualify.matrix()}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "stdout.txt").write_text("execution\n")
            started = time.time_ns() - 1_000_000
            os.utime(root / "stdout.txt", ns=(started + 1_000_000, started + 1_000_000))
            observed_mtime = (root / "stdout.txt").stat().st_mtime_ns
            receipt = {
                "schema": 1, "status": "PASSED", "candidate_sha": BASE,
                "source_tree": subprocess.check_output(
                    ["git", "rev-parse", f"{BASE}^{{tree}}"], cwd=ROOT, text=True).strip(),
                "lane": LANE, "target": "jvm", "runtime": "Java",
                "version": "minimum", "configuration": "no-optimize",
                "runtime_identity": "OpenJDK 8", "artifact_hashes":
                    {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64},
                "process": {"command": ["./gradlew", "check"], "exit_code": 0,
                            "started_ns": started, "finished_ns": started + 2_000_000,
                            "stdout": "stdout.txt"},
                "files": [{"path": "stdout.txt",
                           "sha256": hashlib.sha256((root / "stdout.txt").read_bytes()).hexdigest(),
                           "mtime_ns": observed_mtime}],
            }
            for field, wrong in (("candidate_sha", "f" * 40), ("lane", "other")):
                receipt[field] = wrong
                (root / "receipt.json").write_text(json.dumps(receipt))
                for gate in names:
                    with self.subTest(gate=gate, field=field):
                        result = independent_gates.evaluate(
                            self.manifest, BASE, LANE, {gate: root}, ROOT,
                            receipt["artifact_hashes"], "OpenJDK 8",
                            {gate: independent_gates.archive_digest(root)},
                            expected_all_target_hashes=all_hashes)["gates"][gate]
                        self.assertEqual("FAILED", result["status"])
                        self.assertIn("candidate" if field == "candidate_sha" else "lane",
                                      result["reason"])
                receipt[field] = BASE if field == "candidate_sha" else LANE
            (root / "receipt.json").write_text(json.dumps(receipt))
            for gate in names:
                with self.subTest(gate=gate, missing="producer raw"):
                    result = independent_gates.evaluate(
                        self.manifest, BASE, LANE, {gate: root}, ROOT,
                        receipt["artifact_hashes"], "OpenJDK 8",
                        {gate: independent_gates.archive_digest(root)},
                        expected_all_target_hashes=all_hashes)["gates"][gate]
                    self.assertEqual("FAILED", result["status"])

    def test_external_unavailability_needs_bound_observation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt = {"schema": 1, "status": "UNAVAILABLE", "candidate_sha": BASE,
                       "lane": LANE, "reason": "no physical device attached",
                       "observed_by": "device-lab", "observed_at_ns": time.time_ns()}
            (root / "receipt.json").write_text(json.dumps(receipt))
            def result():
                return independent_gates.evaluate(
                    self.manifest, BASE, LANE,
                    {"physical-correctness": root}, ROOT)["gates"]["physical-correctness"]
            self.assertEqual("UNAVAILABLE", result()["status"])
            receipt["lane"] = "other"
            (root / "receipt.json").write_text(json.dumps(receipt))
            self.assertEqual("FAILED", result()["status"])
            self.assertEqual("FAILED", independent_gates.evaluate(
                self.manifest, BASE, LANE, {"migration-journeys": root}, ROOT
            )["gates"]["migration-journeys"]["status"])

    def test_review_requires_two_distinct_raw_sol_sessions_and_resolved_findings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            started = time.time_ns() - 1_000_000
            finished = time.time_ns() + 1_000_000
            hashes = {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64}
            scope = {"candidate_sha": BASE, "target": "source", "runtime": "codex",
                     "runtime_identity": "review CLI", "artifact_hashes": {},
                     "producer_manifest_hashes": {}}
            receipt = {
                "schema": 1, "status": "PASSED", "candidate_sha": BASE,
                "source_tree": subprocess.check_output(
                    ["git", "rev-parse", f"{BASE}^{{tree}}"], cwd=ROOT, text=True).strip(),
                "lane": LANE, "target": "jvm", "runtime": "Java",
                "version": "minimum", "configuration": "no-optimize",
                "runtime_identity": "review CLI", "artifact_hashes": {},
                "producer_scope": scope,
                "process": {"command": ["codex", "exec", "review"], "exit_code": 0,
                            "started_ns": started, "finished_ns": finished},
            }

            def write():
                files = [file for file in root.iterdir() if file.name != "receipt.json"]
                scope["producer_manifest_hashes"] = {
                    f"{kind}.json": hashlib.sha256((root / f"{kind}.json").read_bytes()).hexdigest()
                    for kind in ("standards", "spec") if (root / f"{kind}.json").is_file()}
                for file in files:
                    os.utime(file, ns=(started + 1_000_000, started + 1_000_000))
                receipt["files"] = [{"path": file.name,
                                     "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                                     "mtime_ns": file.stat().st_mtime_ns} for file in files]
                (root / "receipt.json").write_text(json.dumps(receipt))

            def status():
                return independent_gates.evaluate(
                    self.manifest, BASE, LANE, {"independent-review": root}, ROOT,
                    hashes, "review CLI",
                    {"independent-review": independent_gates.archive_digest(root)},
                    expected_producer_scopes={"independent-review": scope})["gates"]["independent-review"]["status"]

            def write_session(kind, session_id, findings):
                reviewed = (["AGENTS.md", "docs/agents/writing.md"] if kind == "standards"
                            else ["docs/specs/complete-port.md",
                                  "docs/planning/acceptance-implementation.md"])
                assessment = "Reviewed the exact final head against the required source and acceptance obligations."
                report = {"review_kind": kind, "candidate_sha": BASE,
                          "model": "gpt-6-sol", "session_id": session_id,
                          "verdict": "PASSED", "findings": findings,
                          "assessment": assessment, "reviewed_paths": reviewed}
                (root / f"{kind}.json").write_text(json.dumps(report))
                raw = {"kind": "independent-review-result", "review_kind": kind,
                       "candidate_sha": BASE, "verdict": "PASSED", "findings": findings,
                       "assessment": assessment, "reviewed_paths": reviewed}
                messages = (
                    {"type": "session_meta", "payload": {"id": session_id}},
                    {"type": "turn_context", "payload": {"model": "gpt-6-sol"}},
                    {"type": "response_item", "payload": {"type": "message", "role": "assistant",
                                                      "content": [{"type": "output_text", "text": json.dumps(raw)}]}},
                )
                (root / f"{kind}.jsonl").write_text(
                    "\n".join(json.dumps(item) for item in messages) + "\n")

            for kind, session_id in (("standards", "session-a"), ("spec", "session-b")):
                write_session(kind, session_id, [])
                write()
                self.assertEqual("FAILED" if kind == "standards" else "PASSED", status())
            with (root / "spec.jsonl").open("a") as stream:
                stream.write(json.dumps({"type": "response_item", "payload": {
                    "findings": [{"id": "hidden-p1", "severity": "P1"}]}}) + "\n")
            write()
            self.assertEqual("FAILED", status())
            write_session("spec", "session-b", [])
            finding = {"id": "finding-1", "severity": "P1", "description": "resolve a defect"}
            write_session("spec", "session-b", [finding])
            write()
            self.assertEqual("FAILED", status())
            finding["resolution"] = {
                "status": "RESOLVED", "candidate_sha": BASE, "evidence": "README.md",
                "evidence_sha256": hashlib.sha256(subprocess.check_output(
                    ["git", "show", f"{BASE}:README.md"], cwd=ROOT)).hexdigest()}
            write_session("spec", "session-b", [finding])
            write()
            self.assertEqual("PASSED", status())
            receipt["lane"] = None
            write()
            native = "linuxX64:Linux x64:minimum:debug-g"
            native_hashes = {"dyn4k-core": "c" * 64, "dyn4k": "d" * 64}
            native_result = independent_gates.evaluate(
                self.manifest, BASE, native, {"independent-review": root}, ROOT,
                native_hashes, "native runner",
                {"independent-review": independent_gates.archive_digest(root)},
                expected_producer_scopes={"independent-review": scope})
            self.assertEqual("PASSED", native_result["gates"]["independent-review"]["status"])
            wrong_manifest_scope = {**scope, "producer_manifest_hashes": {
                **scope["producer_manifest_hashes"], "spec.json": "e" * 64}}
            rejected_manifest = independent_gates.evaluate(
                self.manifest, BASE, native, {"independent-review": root}, ROOT,
                native_hashes, "native runner",
                {"independent-review": independent_gates.archive_digest(root)},
                expected_producer_scopes={"independent-review": wrong_manifest_scope})
            self.assertEqual("FAILED", rejected_manifest["gates"]["independent-review"]["status"])
            receipt["lane"] = LANE
            write()
            wrong_scope = {**scope, "target": "jvm"}
            rejected = independent_gates.evaluate(
                self.manifest, BASE, LANE, {"independent-review": root}, ROOT,
                hashes, "review CLI",
                {"independent-review": independent_gates.archive_digest(root)},
                expected_producer_scopes={"independent-review": wrong_scope})[
                    "gates"]["independent-review"]
            self.assertEqual("FAILED", rejected["status"])
            (root / "spec.json").write_text(json.dumps({"review_kind": "spec", "candidate_sha": BASE,
                "model": "gpt-6-sol", "session_id": "session-b", "verdict": "PASSED", "findings": []}))
            write()
            self.assertEqual("FAILED", status())

    def test_staged_consumer_checks_frozen_raw_xml_and_resolved_binary_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = json.loads(subprocess.check_output(
                ["git", "show", f"{BASE}:tools/qualification/foundation-probes.json"],
                cwd=ROOT))
            group = next(item for item in manifest["groups"] if item["id"] == "consumer-jvm")
            expected = qualify.expected_probe_cases(manifest, group)
            suite = ET.Element("testsuite", tests=str(len(expected)), failures="0",
                               errors="0", skipped="0", time="0.1")
            for classname, name in expected:
                ET.SubElement(suite, "testcase", classname=classname, name=name, time="0.1")
            (root / "consumer.xml").write_bytes(ET.tostring(suite))
            (root / "graph.txt").write_text(
                "io.github.rubixhacker:dyn4k-core-jvm:0.1.0-alpha.1\n"
                "io.github.rubixhacker:dyn4k-jvm:0.1.0-alpha.1\n")
            (root / "core.bin").write_bytes(b"core")
            (root / "api.bin").write_bytes(b"api")
            (root / "stdout.txt").write_text(
                f"QUALIFICATION_LANE={LANE}\n> Task :consumers:qualification:jvmTest\nBUILD SUCCESSFUL\n"
                + "".join(f"QUALIFICATION_{label}_SHA256={hashlib.sha256((root / name).read_bytes()).hexdigest()}\n"
                          for label, name in (("PROVIDER_GRAPH", "graph.txt"),
                                              ("CONSUMER_XML", "consumer.xml"),
                                              ("RESOLVED_DYN4K_CORE", "core.bin"),
                                              ("RESOLVED_DYN4K", "api.bin"))))
            hashes = {"dyn4k-core": hashlib.sha256(b"core").hexdigest(),
                      "dyn4k": hashlib.sha256(b"api").hexdigest()}
            started = time.time_ns() - 1_000_000
            receipt = {
                "schema": 1, "status": "PASSED", "candidate_sha": BASE,
                "source_tree": subprocess.check_output(
                    ["git", "rev-parse", f"{BASE}^{{tree}}"], cwd=ROOT, text=True).strip(),
                "lane": LANE, "target": "jvm", "runtime": "Java",
                "version": "minimum", "configuration": "no-optimize",
                "runtime_identity": "OpenJDK 8", "artifact_hashes": hashes,
                "process": {"command": ["./gradlew", ":consumers:qualification:jvmTest"],
                            "exit_code": 0, "stdout": "stdout.txt",
                            "started_ns": started, "finished_ns": started + 2_000_000},
                "consumer_group": "consumer-jvm", "consumer_xml": ["consumer.xml"],
                "provider_graph": "graph.txt",
                "resolved_artifacts": {"dyn4k-core": "core.bin", "dyn4k": "api.bin"},
            }

            def write():
                for file in root.iterdir():
                    if file.name != "receipt.json":
                        os.utime(file, ns=(started + 1_000_000, started + 1_000_000))
                receipt["files"] = [{"path": file.name,
                                     "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                                     "mtime_ns": file.stat().st_mtime_ns}
                                    for file in root.iterdir() if file.name != "receipt.json"]
                (root / "receipt.json").write_text(json.dumps(receipt))

            def status():
                return independent_gates.evaluate(
                    self.manifest, BASE, LANE, {"staged-consumer": root},
                    ROOT, hashes, "OpenJDK 8",
                    {"staged-consumer": independent_gates.archive_digest(root)})["gates"]["staged-consumer"]

            write()
            self.assertEqual("NOT_RUN", status()["status"])
            receipt["process"]["command"] = ["echo", "jvmTest"]
            write()
            self.assertEqual("FAILED", status()["status"])
            with tempfile.TemporaryDirectory() as audit_temporary:
                audit = Path(audit_temporary)
                (audit / "hashes.json").write_text(json.dumps(hashes))
                (audit / "digests.json").write_text(json.dumps({
                    "staged-consumer": independent_gates.archive_digest(root)}))
                cli = subprocess.run([
                    sys.executable, str(ROOT / "tools/qualification/independent_gates.py"),
                    "--repository", str(ROOT), "--candidate-sha", BASE,
                    "--lane", LANE, "--expected-artifacts", str(audit / "hashes.json"),
                    "--expected-archive-digests", str(audit / "digests.json"),
                    "--expected-runtime-identity", "OpenJDK 8",
                    "--archive", f"staged-consumer={root}"], capture_output=True, text=True)
                self.assertEqual(1, cli.returncode)
                self.assertIn("execution launcher",
                              json.loads(cli.stdout)["gates"]["staged-consumer"]["reason"])
            receipt["process"]["command"] = ["./gradlew", ":consumers:qualification:jvmTest"]
            write()
            os.utime(root / "consumer.xml", ns=(1, 1))
            self.assertEqual("FAILED", status()["status"])
            (root / "graph.txt").write_text(
                "io.github.rubixhacker:dyn4k-core-jvm:0.1.0-alpha.1\n")
            write()
            self.assertEqual("FAILED", status()["status"])
            (root / "graph.txt").write_text(
                "io.github.rubixhacker:dyn4k-core-jvm:0.1.0-alpha.1\n"
                "io.github.rubixhacker:dyn4k-jvm:0.1.0-alpha.1\n")
            suite.find("testcase").set("name", "other")
            (root / "consumer.xml").write_bytes(ET.tostring(suite))
            write()
            self.assertEqual("FAILED", status()["status"])

    def test_full_suite_consumer_route_accepts_approved_foundation_lane_case_set(self):
        lane_id = LANE
        lane = self.manifest["lanes"][lane_id]
        contract = independent_gates.consumer_contract(self.manifest, lane_id)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            suite = ET.Element("testsuite", tests=str(len(contract["cases"])),
                               failures="0", errors="0", skipped="0", time="1")
            for case in contract["cases"]:
                ET.SubElement(suite, "testcase", id=case["id"], time="0.001")
            (root / "consumer.xml").write_bytes(ET.tostring(suite))
            (root / "graph.txt").write_text("".join(
                f"io.github.rubixhacker:{qualify.target_publication_name(module, lane['target'])}:0.1.0-alpha.1\n"
                for module in qualify.MODULES))
            (root / "core.bin").write_bytes(b"native core fixture")
            (root / "api.bin").write_bytes(b"native facade fixture")
            (root / "stdout.txt").write_text(
                f"QUALIFICATION_LANE={lane_id}\n> Task :consumerJvm\nBUILD SUCCESSFUL\n"
                + "".join(f"QUALIFICATION_{label}_SHA256={hashlib.sha256((root / name).read_bytes()).hexdigest()}\n"
                          for label, name in (("PROVIDER_GRAPH", "graph.txt"),
                                              ("CONSUMER_XML", "consumer.xml"),
                                              ("RESOLVED_DYN4K_CORE", "core.bin"),
                                              ("RESOLVED_DYN4K", "api.bin"))))
            hashes = {"dyn4k-core": hashlib.sha256((root / "core.bin").read_bytes()).hexdigest(),
                      "dyn4k": hashlib.sha256((root / "api.bin").read_bytes()).hexdigest()}
            started = time.time_ns() - 1_000_000
            files = [file for file in root.iterdir()]
            for file in files:
                os.utime(file, ns=(started + 1_000_000, started + 1_000_000))
            receipt = {"schema": 1, "status": "PASSED", "candidate_sha": BASE,
                       "source_tree": subprocess.check_output(
                           ["git", "rev-parse", f"{BASE}^{{tree}}"], cwd=ROOT, text=True).strip(),
                       "lane": lane_id, **{key: lane[key] for key in
                                           ("target", "runtime", "version", "configuration")},
                       "runtime_identity": "selected device fixture", "artifact_hashes": hashes,
                       "process": {"command": ["./gradlew", ":consumerJvm", lane_id],
                                   "exit_code": 0, "started_ns": started,
                                   "finished_ns": started + 2_000_000, "stdout": "stdout.txt"},
                       "consumer_group": "full-suite",
                       "consumer_contract_sha256": independent_gates.digest(contract),
                       "consumer_xml": ["consumer.xml"], "provider_graph": "graph.txt",
                       "resolved_artifacts": {"dyn4k-core": "core.bin", "dyn4k": "api.bin"},
                       "files": [{"path": file.name,
                                  "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                                  "mtime_ns": file.stat().st_mtime_ns} for file in files]}
            (root / "receipt.json").write_text(json.dumps(receipt))
            def result():
                return independent_gates.evaluate(
                    self.manifest, BASE, lane_id, {"staged-consumer": root}, ROOT,
                    hashes, "selected device fixture",
                    {"staged-consumer": independent_gates.archive_digest(root)})["gates"]["staged-consumer"]
            self.assertEqual("PASSED", result()["status"], result()["reason"])
            suite.find("testcase").set("id", "invented:case")
            (root / "consumer.xml").write_bytes(ET.tostring(suite))
            os.utime(root / "consumer.xml", ns=(started + 1_000_000, started + 1_000_000))
            receipt["files"][0]["sha256"] = hashlib.sha256((root / "consumer.xml").read_bytes()).hexdigest()
            receipt["files"][0]["mtime_ns"] = (root / "consumer.xml").stat().st_mtime_ns
            (root / "receipt.json").write_text(json.dumps(receipt))
            self.assertEqual("FAILED", result()["status"])

    def test_java_source_rejects_legacy_case_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "reviewed full_ci raw archive contract"):
                independent_gates._java_full_ci(
                    Path(temporary), {"producer": "legacy-case-manifest"},
                    "java-source-compatibility", BASE, ROOT,
                    {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64})

    def test_required_full_ci_replay_rejects_missing_positive_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.dict(os.environ, {
                    "DYN4K_FULL_CI_REPLAY_REQUIRED": "1",
                    "DYN4K_FULL_CI_REPLAY_ARCHIVE": str(Path(temporary) / "absent-archive")}):
                with self.assertRaisesRegex(AssertionError,
                                            "required full_ci positive archive is missing"):
                    self.test_reviewed_full_ci_archive_replays_unchanged_and_strict_java_gates()

    def test_reviewed_full_ci_archive_replays_unchanged_and_strict_java_gates(self):
        required = "DYN4K_FULL_CI_REPLAY_REQUIRED" in os.environ
        if required:
            self.assertEqual("1", os.environ["DYN4K_FULL_CI_REPLAY_REQUIRED"])
            source = Path(os.environ.get("DYN4K_FULL_CI_REPLAY_ARCHIVE", ""))
            self.assertTrue(source.is_dir() and (source / "lane-manifest.json").is_file(),
                            "required full_ci positive archive is missing")
            candidate = os.environ.get("DYN4K_FULL_CI_REPLAY_CANDIDATE", "")
            current = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                              cwd=ROOT, text=True).strip()
            self.assertEqual(current, candidate, "required full_ci candidate differs from checkout")
            manifest_sha256 = os.environ.get("DYN4K_FULL_CI_REPLAY_MANIFEST_SHA256", "")
            audit_path = Path(os.environ.get("DYN4K_FULL_CI_STAGE_AUDIT", ""))
            self.assertTrue(audit_path.is_file(), "required independent staging audit is missing")
            audit = qualify.load_json_strict(audit_path)
            self.assertEqual("PASSED", audit.get("status"), "staging audit did not pass")
            self.assertEqual(candidate, audit.get("candidate_sha"),
                             "staging audit candidate differs")
            qualify.verify_audit_against_staging(audit, ROOT)
            hashes = qualify.target_binary_hashes(audit["artifacts"])["jvm"]
            facade_source = (ROOT / "build/staging-repository" /
                             qualify.publication_binary_path("dyn4k", "jvm"))
            self.assertEqual(hashes["dyn4k"], hashlib.sha256(facade_source.read_bytes()).hexdigest())
            altered_source = None
        else:
            source = Path("/tmp/dyn4k-archive-relocation-copy-7032-partial-provenance")
            if not (source / "lane-manifest.json").is_file():
                self.skipTest("reviewed historical full_ci archive is absent; CI requires a produced replay")
            altered_source = Path("/tmp/dyn4k-archive-relocation-copy-7032")
            candidate = "7032b41c780a08c850226eb2c984fb15af444a23"
            manifest_sha256 = "e2b2cffdb961213b73a706842af1446586c03f23ed5566c186d0bc8c77ca6269"
        manifest = source / "lane-manifest.json"
        self.assertEqual(manifest_sha256, hashlib.sha256(manifest.read_bytes()).hexdigest())
        archive_files = json.loads(manifest.read_text())["archive_files"]
        if not required:
            self.assertEqual(3593, len(archive_files))
        index = "baseline-cache/dyn4j-source/.git/index"
        self.assertEqual(archive_files[index], hashlib.sha256((source / index).read_bytes()).hexdigest())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(source, root / "full-ci")
            if required:
                shutil.copy2(facade_source, root / "facade.bin")
            else:
                (root / "facade.bin").write_bytes(b"separate facade fixture")
            evidence = json.loads((root / "full-ci/result.json").read_text())
            if required:
                self.assertEqual(hashes["dyn4k-core"], evidence["archives"]["staged_jvm_jar"])
            else:
                hashes = {"dyn4k-core": "005b6a8a5926dfffa7b3dfd932db7662b6cacc4bfdbad1a0742d9dfcfaef651f",
                          "dyn4k": hashlib.sha256((root / "facade.bin").read_bytes()).hexdigest()}
                self.assertEqual(hashes["dyn4k-core"], evidence["archives"]["staged_jvm_jar"])
            scope = {"candidate_sha": candidate, "target": "jvm", "runtime": "Java",
                     "runtime_identity": "reviewed local archive", "artifact_hashes": hashes,
                     "producer_manifest_hashes": {"full-ci/lane-manifest.json": manifest_sha256}}
            started = time.time_ns() - 1_000_000_000
            finished = time.time_ns() + 1_000_000_000
            receipt = {"schema": 1, "status": "PASSED", "candidate_sha": candidate,
                       "source_tree": subprocess.check_output(
                           ["git", "rev-parse", f"{candidate}^{{tree}}"], cwd=ROOT, text=True).strip(),
                       "lane": LANE, "target": "jvm", "runtime": "Java",
                       "version": "minimum", "configuration": "no-optimize",
                       "runtime_identity": "reviewed local archive", "artifact_hashes": hashes,
                       "producer_scope": scope,
                       "process": {"command": ["python3", "tools/compatibility/full_ci.py", "verify"],
                                   "exit_code": 0, "started_ns": started, "finished_ns": finished},
                       "producer": "reviewed-full-ci", "full_ci_archive": "full-ci",
                       "full_ci_manifest_sha256": manifest_sha256,
                       "resolved_artifacts": {
                           "dyn4k-core": "full-ci/archives/dyn4k-core-jvm-0.1.0-alpha.1.jar",
                           "dyn4k": "facade.bin"}}
            files = [path for path in root.rglob("*") if path.is_file()]
            for path in files:
                os.utime(path, ns=(started + 1_000_000, started + 1_000_000))
            receipt["files"] = [{"path": path.relative_to(root).as_posix(),
                                 "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                 "mtime_ns": path.stat().st_mtime_ns} for path in files]
            (root / "receipt.json").write_text(json.dumps(receipt))
            pin = independent_gates.archive_digest(root)
            corpus = evidence["corpus"]
            routes = [name for name in corpus if name.startswith(("baseline-javac", "candidate-javac",
                                                                  "android-javac")) and name.count("-java") == 2]
            self.assertEqual(12, len(routes))
            self.assertEqual({2385}, {corpus[name]["cases"] for name in routes})
            for gate in ("unchanged-java-corpus", "java-source-compatibility"):
                with self.subTest(gate=gate):
                    result = independent_gates.evaluate(
                        self.manifest, candidate, LANE, {gate: root}, ROOT, hashes,
                        "reviewed local archive", {gate: pin},
                        expected_producer_scopes={gate: scope})["gates"][gate]
                    self.assertEqual("PASSED", result["status"], result["reason"])
            wrong_manifest_scope = {**scope, "producer_manifest_hashes": {
                "full-ci/lane-manifest.json": "e" * 64}}
            rejected_manifest = independent_gates.evaluate(
                self.manifest, candidate, LANE, {"unchanged-java-corpus": root}, ROOT,
                hashes, "reviewed local archive", {"unchanged-java-corpus": pin},
                expected_producer_scopes={"unchanged-java-corpus": wrong_manifest_scope})
            self.assertEqual("FAILED", rejected_manifest["gates"]["unchanged-java-corpus"]["status"])
            with tempfile.TemporaryDirectory() as audit_temporary:
                audit = Path(audit_temporary)
                (audit / "hashes.json").write_text(json.dumps(hashes))
                (audit / "scopes.json").write_text(json.dumps({"unchanged-java-corpus": scope}))
                (audit / "digests.json").write_text(json.dumps({"unchanged-java-corpus": pin}))
                cli = subprocess.run([
                    sys.executable, str(ROOT / "tools/qualification/independent_gates.py"),
                    "--repository", str(ROOT), "--candidate-sha", candidate,
                    "--lane", LANE, "--expected-artifacts", str(audit / "hashes.json"),
                    "--expected-producer-scopes", str(audit / "scopes.json"),
                    "--expected-archive-digests", str(audit / "digests.json"),
                    "--expected-runtime-identity", "reviewed local archive",
                    "--archive", f"unchanged-java-corpus={root}"],
                    capture_output=True, text=True)
                self.assertEqual("PASSED", json.loads(cli.stdout)["gates"]["unchanged-java-corpus"]["status"])
            (root / "full-ci/logs/run-candidate-javac8-java8.log").write_text("mutated\n")
            result = independent_gates.evaluate(
                self.manifest, candidate, LANE, {"unchanged-java-corpus": root}, ROOT,
                hashes, "reviewed local archive", {"unchanged-java-corpus": pin},
                expected_producer_scopes={"unchanged-java-corpus": scope})
            self.assertEqual("FAILED", result["gates"]["unchanged-java-corpus"]["status"])
            if altered_source is not None and altered_source.is_dir():
                with tempfile.TemporaryDirectory() as adverse_temporary:
                    adverse = Path(adverse_temporary)
                    shutil.copytree(altered_source, adverse / "full-ci")
                    self.assertEqual(manifest_sha256, hashlib.sha256(
                        (adverse / "full-ci/lane-manifest.json").read_bytes()).hexdigest())
                    self.assertNotEqual(archive_files[index], hashlib.sha256(
                        (adverse / "full-ci" / index).read_bytes()).hexdigest())
                    (adverse / "facade.bin").write_bytes(b"separate facade fixture")
                    adverse_receipt = {**receipt}
                    adverse_files = [path for path in adverse.rglob("*") if path.is_file()]
                    for path in adverse_files:
                        os.utime(path, ns=(started + 1_000_000, started + 1_000_000))
                    adverse_receipt["files"] = [
                        {"path": path.relative_to(adverse).as_posix(),
                         "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                         "mtime_ns": path.stat().st_mtime_ns} for path in adverse_files]
                    (adverse / "receipt.json").write_text(json.dumps(adverse_receipt))
                    altered_pin = independent_gates.archive_digest(adverse)
                    rejected = independent_gates.evaluate(
                        self.manifest, candidate, LANE,
                        {"unchanged-java-corpus": adverse}, ROOT, hashes,
                        "reviewed local archive", {"unchanged-java-corpus": altered_pin},
                        expected_producer_scopes={"unchanged-java-corpus": scope})
                    gate = rejected["gates"]["unchanged-java-corpus"]
                    self.assertEqual("FAILED", gate["status"])
                    self.assertIn("reviewed full_ci/strict raw verifier rejected archive", gate["reason"])

    def test_reviewed_full_ci_replay_uses_canonical_export_with_autocrlf_true(self):
        with mock.patch.dict(os.environ, {"GIT_CONFIG_COUNT": "1",
                                       "GIT_CONFIG_KEY_0": "core.autocrlf",
                                       "GIT_CONFIG_VALUE_0": "true"}):
            self.test_reviewed_full_ci_archive_replays_unchanged_and_strict_java_gates()

    @unittest.skipUnless(
        Path("/tmp/dyn4k-merge-complete-corpus-rotation-migration-journeys-0681a8cd/summary.json").is_file()
        and Path("/tmp/dyn4k-merge-complete-corpus-rotation-gate-wave/build/staging-repository/"
                 "io/github/rubixhacker/dyn4k-core-jvm/0.1.0-alpha.1/"
                 "dyn4k-core-jvm-0.1.0-alpha.1.jar").is_file(),
        "reviewed local migration archive or same-commit staged JVM JAR is absent")
    def test_historical_migration_raw_scenes_replay_and_input_mutation_fails(self):
        source = Path("/tmp/dyn4k-merge-complete-corpus-rotation-migration-journeys-0681a8cd")
        samples = Path("/tmp/dyn4k-migration-preflight/samples")
        if not samples.is_dir():
            self.skipTest("pinned unchanged sample checkout is absent")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "evidence"
            shutil.copytree(source, evidence)
            report = json.loads((evidence / "summary.json").read_text())
            paths = subprocess.check_output(
                ["git", "-C", str(samples), "ls-files", "--", "*.java"], text=True).splitlines()
            rows = []
            for relative in paths:
                original = samples / relative
                copied = evidence / "sources" / relative
                copied.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, copied)
                rows.append(f"{hashlib.sha256(original.read_bytes()).hexdigest()}  {relative}\n")
            (evidence / "sources.sha256").write_text("".join(rows))
            producer_worktree = Path("/tmp/dyn4k-merge-complete-corpus-rotation-gate-wave")
            self.assertEqual(report["candidate_commit"], subprocess.check_output(
                ["git", "-C", str(producer_worktree), "rev-parse", "HEAD"], text=True).strip())
            candidate_jar = (producer_worktree / "build/staging-repository/io/github/rubixhacker/"
                             "dyn4k-core-jvm/0.1.0-alpha.1/dyn4k-core-jvm-0.1.0-alpha.1.jar")
            pinned_lib = Path("/tmp/dyn4k-migration-preflight/lib")
            full_ci = Path("/tmp/dyn4k-archive-relocation-copy-7032")
            for provider in journeys.PROVIDERS:
                destination = evidence / "resolved" / provider
                destination.mkdir(parents=True)
                for name in ("gluegen-rt-2.3.2.jar", "jogl-all-2.3.2.jar"):
                    shutil.copy2(pinned_lib / name, destination / name)
                if provider == "baseline":
                    shutil.copy2(pinned_lib / "dyn4j-6.0.0.jar", destination / "dyn4j-6.0.0.jar")
                else:
                    shutil.copy2(candidate_jar, destination / journeys.CANDIDATE_JAR)
                    for name in independent_gates.MIGRATION_DEPENDENCIES:
                        shutil.copy2(full_ci / "deps" / name, destination / name)
            (evidence / "instrumentation").mkdir()
            shutil.copy2(pinned_lib / "javassist-3.30.2-GA.jar",
                         evidence / "instrumentation/javassist-3.30.2-GA.jar")
            journeys.write_summary(evidence, report)
            hashes = {"dyn4k-core": hashlib.sha256(candidate_jar.read_bytes()).hexdigest()}
            self.assertIn("ten pinned migration journeys",
                          independent_gates._migration_journeys(root, report["candidate_commit"], hashes))
            (root / "facade.bin").write_bytes(b"separate facade fixture")
            hashes["dyn4k"] = hashlib.sha256((root / "facade.bin").read_bytes()).hexdigest()
            scope = {"candidate_sha": report["candidate_commit"], "target": "jvm",
                     "runtime": "Java", "runtime_identity": "historical migration archive",
                     "artifact_hashes": {"dyn4k-core": hashes["dyn4k-core"]},
                     "producer_manifest_hashes": {"evidence/summary.json":
                         hashlib.sha256((evidence / "summary.json").read_bytes()).hexdigest()}}
            started = time.time_ns() - 1_000_000_000
            finished = time.time_ns() + 1_000_000_000
            files = [path for path in root.rglob("*") if path.is_file()]
            for path in files:
                os.utime(path, ns=(started + 1_000_000, started + 1_000_000))
            receipt = {"schema": 1, "status": "PASSED",
                       "candidate_sha": report["candidate_commit"],
                       "source_tree": subprocess.check_output(
                           ["git", "rev-parse", f"{report['candidate_commit']}^{{tree}}"],
                           cwd=ROOT, text=True).strip(),
                       "lane": LANE, "target": "jvm", "runtime": "Java",
                       "version": "minimum", "configuration": "no-optimize",
                       "runtime_identity": "historical migration archive",
                       "artifact_hashes": scope["artifact_hashes"], "producer_scope": scope,
                       "process": {"command": ["python3", "tools/migration/journeys.py", "run"],
                                   "exit_code": 0, "started_ns": started, "finished_ns": finished},
                       "files": [{"path": path.relative_to(root).as_posix(),
                                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                  "mtime_ns": path.stat().st_mtime_ns} for path in files]}
            (root / "receipt.json").write_text(json.dumps(receipt))
            pin = independent_gates.archive_digest(root)
            selected = independent_gates.evaluate(
                self.manifest, report["candidate_commit"], LANE,
                {"migration-journeys": root}, ROOT, hashes,
                "historical migration archive", {"migration-journeys": pin},
                expected_producer_scopes={"migration-journeys": scope})
            self.assertEqual("PASSED", selected["gates"]["migration-journeys"]["status"])
            native_lane = "linuxX64:Linux x64:minimum:debug-g"
            receipt["lane"] = None
            (root / "receipt.json").write_text(json.dumps(receipt))
            native_pin = independent_gates.archive_digest(root)
            native_hashes = {"dyn4k-core": "c" * 64, "dyn4k": "d" * 64}
            native = independent_gates.evaluate(
                self.manifest, report["candidate_commit"], native_lane,
                {"migration-journeys": root}, ROOT, native_hashes,
                "native runner", {"migration-journeys": native_pin},
                expected_producer_scopes={"migration-journeys": scope})
            self.assertEqual("PASSED", native["gates"]["migration-journeys"]["status"])
            wrong_manifest_scope = {**scope, "producer_manifest_hashes": {
                "evidence/summary.json": "e" * 64}}
            wrong_manifest = independent_gates.evaluate(
                self.manifest, report["candidate_commit"], native_lane,
                {"migration-journeys": root}, ROOT, native_hashes,
                "native runner", {"migration-journeys": native_pin},
                expected_producer_scopes={"migration-journeys": wrong_manifest_scope})
            self.assertEqual("FAILED", wrong_manifest["gates"]["migration-journeys"]["status"])
            with tempfile.TemporaryDirectory() as audit_temporary:
                audit = Path(audit_temporary)
                (audit / "hashes.json").write_text(json.dumps(native_hashes))
                (audit / "scopes.json").write_text(json.dumps({"migration-journeys": scope}))
                (audit / "digests.json").write_text(json.dumps({"migration-journeys": native_pin}))
                cli = subprocess.run([
                    sys.executable, str(ROOT / "tools/qualification/independent_gates.py"),
                    "--repository", str(ROOT), "--candidate-sha", report["candidate_commit"],
                    "--lane", native_lane, "--expected-artifacts", str(audit / "hashes.json"),
                    "--expected-producer-scopes", str(audit / "scopes.json"),
                    "--expected-archive-digests", str(audit / "digests.json"),
                    "--expected-runtime-identity", "native runner",
                    "--archive", f"migration-journeys={root}"],
                    capture_output=True, text=True)
                self.assertEqual("PASSED", json.loads(cli.stdout)["gates"]["migration-journeys"]["status"])
            wrong_scope = {**scope, "artifact_hashes": {"dyn4k-core": "e" * 64}}
            wrong = independent_gates.evaluate(
                self.manifest, report["candidate_commit"], native_lane,
                {"migration-journeys": root}, ROOT, native_hashes,
                "native runner", {"migration-journeys": native_pin},
                expected_producer_scopes={"migration-journeys": wrong_scope})
            self.assertEqual("FAILED", wrong["gates"]["migration-journeys"]["status"])
            class_file = next((evidence / "candidate/compile/classes").rglob("*.class"))
            class_relative = class_file.relative_to(evidence)
            class_file.write_bytes(b"fake class")
            journeys.write_summary(evidence, report)
            with self.assertRaisesRegex(ValueError, "compiled class outputs differ"):
                independent_gates._migration_journeys(root, report["candidate_commit"], hashes)
            shutil.copy2(source / class_relative, class_file)
            source_file = evidence / "sources" / paths[0]
            source_file.write_bytes(b"class Invented {}\n")
            journeys.write_summary(evidence, report)
            with self.assertRaisesRegex(ValueError, "unchanged Java source bytes differ"):
                independent_gates._migration_journeys(root, report["candidate_commit"], hashes)
            shutil.copy2(samples / paths[0], source_file)
            input_log = evidence / "candidate/Billiards/observed/evidence/Billiards/inputs.log"
            input_log.write_text("scene=Billiards\n")
            journeys.write_summary(evidence, report)
            with self.assertRaisesRegex(ValueError, "raw scene, input, physics, or CCD evidence differs"):
                independent_gates._migration_journeys(root, report["candidate_commit"], hashes)


class NativeCrossSignedGateTests(unittest.TestCase):
    def test_public_cross_result_requires_audited_complete_suite(self):
        lane = "linuxArm64:Linux ARM64:current:debug-g"
        candidate = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        manifest = independent_gates.load_approved_manifest(ROOT)
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary)
            (archive / "receipt.json").write_text(json.dumps({
                "schema": 3, "status": "PASSED", "lane": lane,
                "candidate_sha": candidate}))
            digest = independent_gates.archive_digest(archive)
            public = {"status": "PASSED", "lane": lane, "candidate_sha": candidate,
                      "selected_cases": 2523, "archive_sha256": digest,
                      "artifact_hash_provenance": "audited",
                      "complete_selected_suite": True}
            args = {"gate": "staged-consumer", "archive": archive,
                    "candidate_sha": candidate, "lane_id": lane,
                    "lane": manifest["lanes"][lane], "repository": ROOT,
                    "expected_artifact_hashes": {"dyn4k-core": "a" * 64,
                                                 "dyn4k": "b" * 64},
                    "expected_runtime_identity": "fixture-arm64",
                    "expected_archive_digest": digest, "manifest": manifest,
                    "expected_signed_lane": {"expected_archive_digests": {
                        "staged-consumer": digest}}}
            with mock.patch("full_signed_routes.verify", return_value=public) as replay:
                result = independent_gates.evaluate_gate(**args)
                self.assertEqual("PASSED", result["status"], result)
                replay.assert_called_once()
                for changed in ({"artifact_hash_provenance": "staging-self"},
                                {"complete_selected_suite": False},
                                {"complete_selected_suite": None}):
                    replay.return_value = {**public, **changed}
                    self.assertEqual("FAILED", independent_gates.evaluate_gate(
                        **args)["status"])
                replay.return_value = {key: value for key, value in public.items()
                                       if key != "complete_selected_suite"}
                self.assertEqual("FAILED", independent_gates.evaluate_gate(
                    **args)["status"])


class FullBrowserGenericGateTests(unittest.TestCase):
    LANE = "js:Chromium:current:development"
    HASHES = {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64}
    RUNTIME = "Linux fixture x86_64"

    @classmethod
    def setUpClass(cls):
        cls.CANDIDATE = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        cls.manifest = independent_gates.load_approved_manifest(ROOT)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.archive = Path(self.temporary.name)
        self.receipt = {"schema": 1, "status": "PASSED", "lane": self.LANE,
                        "candidate_sha": self.CANDIDATE,
                        "runtime_identity": self.RUNTIME,
                        "consumer_contract_sha256": "browser archive marker",
                        "toolchain": {"browser": str(Path(self.temporary.name) / "chrome")}}
        self.write_receipt()

    def write_receipt(self):
        (self.archive / "receipt.json").write_text(json.dumps(self.receipt))

    def evaluate(self, **changes):
        selected = {"gate": "staged-consumer", "archive": self.archive,
                    "candidate_sha": self.CANDIDATE, "lane_id": self.LANE,
                    "lane": self.manifest["lanes"][self.LANE], "repository": ROOT,
                    "expected_artifact_hashes": self.HASHES,
                    "expected_runtime_identity": self.RUNTIME,
                    "expected_archive_digest": independent_gates.archive_digest(self.archive),
                    "manifest": self.manifest}
        selected.update(changes)
        return independent_gates.evaluate_gate(**selected)

    def test_current_source_rejects_historical_unsigned_browser_receipt(self):
        with mock.patch("full_browser_consumer.verify") as replay:
            result = self.evaluate()
        self.assertEqual("FAILED", result["status"])
        replay.assert_not_called()

    def test_current_source_rejects_posix_only_browser_path(self):
        self.receipt["toolchain"]["browser"] = "/trusted/chrome"
        self.write_receipt()
        with mock.patch("full_browser_consumer.verify") as replay:
            self.assertEqual("FAILED", self.evaluate()["status"])
        replay.assert_not_called()

    def test_pinned_historical_chromium_receipt_keeps_legacy_route(self):
        import full_browser_consumer

        candidate = full_browser_consumer.LEGACY_CANDIDATE_SHA
        self.receipt["candidate_sha"] = candidate
        self.receipt["toolchain"]["browser"] = "/trusted/chrome"
        self.write_receipt()
        digest = independent_gates.archive_digest(self.archive)
        public = {"status": "PASSED", "lane": self.LANE,
                  "selected_cases": 2523, "archive_sha256": digest,
                  "candidate_sha": candidate}
        with (mock.patch("full_browser_consumer.original",
                         return_value=Path(full_browser_consumer.__file__).read_bytes()),
              mock.patch("full_browser_consumer.verify", return_value=public) as replay):
            result = self.evaluate(candidate_sha=candidate)
        self.assertEqual("PASSED", result["status"], result)
        replay.assert_called_once()

    def test_full_browser_route_rejects_selected_identity_and_suite_mismatch(self):
        cases = [
            {"candidate_sha": "f" * 40},
            {"lane_id": "js:Chromium:foreign:development"},
            {"expected_runtime_identity": "other runtime"},
            {"expected_artifact_hashes": {"dyn4k-core": "a" * 64}},
            {"expected_archive_digest": "f" * 64},
            {"lane": {**self.manifest["lanes"][self.LANE], "runtime": "other"}},
            {"manifest": {**self.manifest, "cases": self.manifest["cases"][:-1]}},
            {"manifest": {**self.manifest, "cases": [*self.manifest["cases"],
                                                     self.manifest["cases"][-1]]}},
        ]
        for change in cases:
            with self.subTest(change=change), mock.patch("full_browser_consumer.verify") as replay:
                self.assertEqual("FAILED", self.evaluate(**change)["status"])
                replay.assert_not_called()

    def test_full_browser_route_rejects_receipt_binary_and_public_mismatch(self):
        for field, value in (("lane", "js:Chromium:minimum:development"),
                             ("candidate_sha", "f" * 40),
                             ("schema", True),
                             ("runtime_identity", "other runtime"),
                             ("toolchain", {"browser": "relative/chrome"})):
            original = self.receipt[field]
            self.receipt[field] = value
            self.write_receipt()
            with self.subTest(field=field), mock.patch("full_browser_consumer.verify") as replay:
                self.assertEqual("FAILED", self.evaluate()["status"])
                replay.assert_not_called()
            self.receipt[field] = original
        self.write_receipt()
        with mock.patch("full_browser_consumer.verify", return_value={
                "status": "PASSED", "lane": self.LANE, "selected_cases": 2522,
                "archive_sha256": independent_gates.archive_digest(self.archive),
                "candidate_sha": self.CANDIDATE}):
            self.assertEqual("FAILED", self.evaluate()["status"])
        with mock.patch("full_browser_consumer.verify", side_effect=ValueError("raw XML differs")):
            self.assertEqual("FAILED", self.evaluate()["status"])
        with (mock.patch("full_browser_consumer.original", return_value=b"different source"),
              mock.patch("full_browser_consumer.verify") as replay):
            self.assertEqual("FAILED", self.evaluate()["status"])
            replay.assert_not_called()

    def test_bounded_browser_archive_keeps_existing_not_run_route(self):
        (self.archive / "verification.json").write_text("{}")
        with (mock.patch.object(independent_gates, "_bounded_bundle",
                                return_value={"executed": 12}) as bounded,
              mock.patch("full_browser_consumer.verify") as replay):
            result = self.evaluate()
        self.assertEqual("NOT_RUN", result["status"])
        self.assertEqual(12, result["bounded_executed"])
        bounded.assert_called_once()
        replay.assert_not_called()


class FullBrowserSignedGateTests(unittest.TestCase):
    HASHES = {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64}
    RUNTIME = "Linux fixture x86_64"

    @classmethod
    def setUpClass(cls):
        cls.candidate = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        cls.manifest = independent_gates.load_approved_manifest(ROOT)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.archive = Path(self.temporary.name) / "archive"
        self.archive.mkdir()

    def browser_inputs(self, receipt, signed):
        browser_sha = "d" * 64
        receipt["toolchain"]["browser_sha256"] = browser_sha
        receipt["modules"] = {}
        consumption = {}
        for index, short in enumerate(("core", "facade")):
            folder = self.archive / short
            folder.mkdir(exist_ok=True)
            pid = 100 + index
            receipt["modules"][short] = {"started_ns": 10, "finished_ns": 100}
            (folder / "browser-launches.jsonl").write_text(json.dumps({
                "pid": pid, "process_sha256": browser_sha}) + "\n")
            response = {"url": f"/absolute/{short}/runtime.js", "sha256": "e" * 64,
                        "size": 12, "started_ns": 35, "finished_ns": 45}
            (folder / "http-responses.json").write_text(json.dumps({
                "responses": [response]}))
            if receipt["schema"] == 4:
                (folder / "chromium-cdp.jsonl").write_text("\n".join(json.dumps(row) for row in (
                    {"kind": "session", "browser_pid": pid, "cdp_browser_pid": pid,
                     "target_id": short, "started_ns": 20},
                    {"url": f"http://127.0.0.1:9876{response['url']}",
                     "browser_pid": pid, "target_id": short, "request_ns": 30,
                     "response_ns": 40, "finished_ns": 50,
                     "body_sha256": response["sha256"], "body_size": response["size"]}
                )) + "\n")
            consumption[short] = {"protocol": "cdp", "clock": "unix-epoch-ns",
                                  "browser_pid": pid,
                                  "browser_sha256": browser_sha,
                                  "started_ns": 20, "finished_ns": 90,
                                  "responses": [{"url": response["url"],
                                                 "body_sha256": response["sha256"],
                                                 "size": response["size"],
                                                 "request_ns": 30,
                                                 "response_ns": 40,
                                                 "finished_ns": 50}]}
        witness_path = Path(self.temporary.name) / "independent-witness.json"
        witness_path.write_text(json.dumps({"browser_consumption": consumption}))
        signed["expected_execution_witness"] = {
            "path": str(witness_path),
            "sha256": hashlib.sha256(witness_path.read_bytes()).hexdigest()}
        return witness_path

    def evaluate(self, lane, signed=True, **changes):
        import full_browser_consumer

        receipt = {"schema": 3, "status": "PASSED", "lane": lane,
                   "candidate_sha": self.candidate,
                   "source_tree": subprocess.check_output(
                       ["git", "rev-parse", f"{self.candidate}^{{tree}}"],
                       cwd=ROOT, text=True).strip(),
                   "consumer_contract_sha256": independent_gates.digest(
                       full_browser_consumer.contract(ROOT, lane)),
                   "browser_support_sha256": {}, "staged_hashes": self.HASHES,
                   "runtime_identity": self.RUNTIME,
                   "toolchain": {"browser": "/trusted/browser"},
                   "files": []}
        receipt.update(changes.pop("receipt", {}))
        historical_source = changes.pop("historical_source", receipt["schema"] == 3)
        missing_minimum_worker = changes.pop("missing_minimum_worker", False)
        expected = {"expected_artifact_hashes": self.HASHES,
                    "expected_runtime_identity": self.RUNTIME,
                    "expected_archive_digests": {},
                    "expected_browser_responses": {"core": {}, "facade": {}}}
        witness_path = self.browser_inputs(receipt, expected)
        if changes.pop("parallel_order", False):
            folder = self.archive / "core"
            captured = json.loads((folder / "http-responses.json").read_text())
            commons = {"url": "/absolute/core/commons.js", "sha256": "f" * 64,
                       "size": 16, "started_ns": 55, "finished_ns": 65}
            captured["responses"].append(commons)
            (folder / "http-responses.json").write_text(json.dumps(captured))
            witness = json.loads(witness_path.read_text())
            witness["browser_consumption"]["core"]["responses"].insert(0, {
                "url": commons["url"], "body_sha256": commons["sha256"],
                "size": commons["size"], "request_ns": 25,
                "response_ns": 60, "finished_ns": 70})
            witness_path.write_text(json.dumps(witness))
            expected["expected_execution_witness"]["sha256"] = hashlib.sha256(
                witness_path.read_bytes()).hexdigest()
            if receipt["schema"] == 4:
                cdp_path = folder / "chromium-cdp.jsonl"
                rows = [json.loads(line) for line in cdp_path.read_text().splitlines()]
                rows.append({"url": f"http://127.0.0.1:9876{commons['url']}",
                             "browser_pid": rows[0]["browser_pid"],
                             "target_id": rows[0]["target_id"],
                             "request_ns": 25, "response_ns": 60, "finished_ns": 70,
                             "body_sha256": commons["sha256"], "body_size": commons["size"]})
                cdp_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
        cdp_change = changes.pop("cdp_change", None)
        if cdp_change is not None:
            cdp_path = self.archive / "core/chromium-cdp.jsonl"
            rows = [json.loads(line) for line in cdp_path.read_text().splitlines()]
            field, value = cdp_change
            rows[1][field] = value
            cdp_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
        if receipt["status"] == "NOT_RUN":
            expected["expected_not_run"] = receipt.copy()
        if changes.pop("missing_witness", False):
            expected.pop("expected_execution_witness")
        forged_witness = changes.pop("forged_witness", False)
        if changes.pop("stale_witness", False):
            witness = json.loads(witness_path.read_text())
            witness["browser_consumption"]["core"]["browser_pid"] = 999
            witness_path.write_text(json.dumps(witness))
            expected["expected_execution_witness"]["sha256"] = hashlib.sha256(
                witness_path.read_bytes()).hexdigest()
        if changes.pop("wrong_body", False):
            witness = json.loads(witness_path.read_text())
            witness["browser_consumption"]["core"]["responses"][0][
                "body_sha256"] = "f" * 64
            witness_path.write_text(json.dumps(witness))
            expected["expected_execution_witness"]["sha256"] = hashlib.sha256(
                witness_path.read_bytes()).hexdigest()
        if changes.pop("missing_response", False):
            witness = json.loads(witness_path.read_text())
            witness["browser_consumption"]["core"]["responses"] = []
            witness_path.write_text(json.dumps(witness))
        if changes.pop("missing_process", False):
            witness = json.loads(witness_path.read_text())
            witness["browser_consumption"].pop("facade")
            witness_path.write_text(json.dumps(witness))
        if changes.pop("wrong_interval", False):
            witness = json.loads(witness_path.read_text())
            witness["browser_consumption"]["facade"]["responses"][0][
                "finished_ns"] = 101
            witness_path.write_text(json.dumps(witness))
            expected["expected_execution_witness"]["sha256"] = hashlib.sha256(
                witness_path.read_bytes()).hexdigest()
        if changes.pop("before_server", False):
            witness = json.loads(witness_path.read_text())
            observed = witness["browser_consumption"]["core"]["responses"][0]
            observed.update({"request_ns": 21, "response_ns": 31, "finished_ns": 33})
            witness_path.write_text(json.dumps(witness))
            expected["expected_execution_witness"]["sha256"] = hashlib.sha256(
                witness_path.read_bytes()).hexdigest()
        if changes.pop("wrong_clock", False):
            witness = json.loads(witness_path.read_text())
            witness["browser_consumption"]["core"]["clock"] = "unmapped-monotonic-ns"
            witness_path.write_text(json.dumps(witness))
            expected["expected_execution_witness"]["sha256"] = hashlib.sha256(
                witness_path.read_bytes()).hexdigest()
        protocol_change = changes.pop("protocol_change", None)
        if protocol_change is not None:
            witness = json.loads(witness_path.read_text())
            witness["browser_consumption"]["core"]["protocol"] = protocol_change
            witness_path.write_text(json.dumps(witness))
            expected["expected_execution_witness"]["sha256"] = hashlib.sha256(
                witness_path.read_bytes()).hexdigest()
        (self.archive / "receipt.json").write_text(json.dumps(receipt))
        digest = independent_gates.archive_digest(self.archive)
        expected["expected_archive_digests"]["staged-consumer"] = digest
        if receipt["schema"] == 4 and "expected_execution_witness" in expected:
            witness = json.loads(witness_path.read_text())
            witness.update({
                "schema": "independent-browser-execution-witness/1",
                "candidate_sha": receipt["candidate_sha"], "lane": lane,
                "archive_sha256": digest, "runtime_identity": receipt["runtime_identity"],
                "mode": lane.rsplit(":", 1)[1], "staged_artifacts": self.HASHES,
                "browser_sha256": receipt["toolchain"]["browser_sha256"],
                "observer_source_sha256": hashlib.sha256((ROOT /
                    "tools/qualification/independent_browser_observer.js").read_bytes()).hexdigest(),
                "auditor": "independent test key", "responses": expected["expected_browser_responses"]})
            witness_path.write_text(json.dumps(witness))
            expected["expected_execution_witness"]["sha256"] = hashlib.sha256(
                witness_path.read_bytes()).hexdigest()
        if forged_witness:
            expected["expected_execution_witness"]["sha256"] = "f" * 64
        selected = {"gate": "staged-consumer", "archive": self.archive,
                    "candidate_sha": self.candidate, "lane_id": lane,
                    "lane": self.manifest["lanes"][lane], "repository": ROOT,
                    "expected_artifact_hashes": self.HASHES,
                    "expected_runtime_identity": self.RUNTIME,
                    "expected_archive_digest": digest, "manifest": self.manifest,
                    "expected_signed_lane": expected if signed else None}
        selected.update(changes)
        original = full_browser_consumer.original
        def source(repository, candidate, path):
            raw = original(repository, candidate, path)
            if historical_source and path == "tools/qualification/full_browser_consumer.py":
                return (raw.replace(b"DYN4K_BROWSER_BIDI_ARCHIVE", b"historical-bidi-marker")
                           .replace(b"DYN4K_BROWSER_FIREFOX_MINIMUM_SW",
                                    b"historical-minimum-marker")
                           .replace(b"SAFARI_WORKER = ", b"historical-worker-marker"))
            if missing_minimum_worker and path == "tools/qualification/full_browser_consumer.py":
                return raw.replace(b"DYN4K_BROWSER_FIREFOX_MINIMUM_SW",
                                   b"missing-minimum-marker")
            return raw
        with mock.patch("full_browser_consumer.original", side_effect=source):
            return independent_gates.evaluate_gate(**selected), digest

    def test_schema3_firefox_and_safari_reach_signed_public_route(self):
        import full_browser_consumer

        self.assertEqual(24, len(full_browser_consumer.LANES))
        lanes = sorted(lane for lane in full_browser_consumer.LANES
                       if ":Chromium:" not in lane)
        self.assertEqual(16, len(lanes))
        for lane in lanes:
            with self.subTest(lane=lane):
                with mock.patch("full_signed_routes.verify_browser") as replay:
                    replay.side_effect = lambda *args: {
                        "status": "PASSED", "lane": args[2], "selected_cases": 2523,
                        "archive_sha256": args[7], "candidate_sha": args[1]}
                    result, digest = self.evaluate(lane)
                self.assertEqual("PASSED", result["status"], result)
                self.assertEqual(2523, result["selected_cases"])
                replay.assert_called_once()
                self.assertEqual(digest, replay.call_args.args[7])

    def test_schema4_chromium_eight_lanes_reach_signed_public_route(self):
        lanes = [f"{target}:Chromium:{role}:{mode}" for target in ("js", "wasmJs")
                 for role in ("minimum", "current")
                 for mode in ("development", "production")]
        for lane in lanes:
            with self.subTest(lane=lane), mock.patch(
                    "full_signed_routes.verify_browser") as replay:
                replay.side_effect = lambda *args: {
                    "status": "PASSED", "lane": args[2], "selected_cases": 2523,
                    "archive_sha256": args[7], "candidate_sha": args[1]}
                result, _ = self.evaluate(lane, receipt={"schema": 4})
                self.assertEqual("PASSED", result["status"], result)
                replay.assert_called_once()
                result, _ = self.evaluate(lane, receipt={"schema": 3})
                self.assertEqual("FAILED", result["status"], result)

    def test_schema5_family_source_and_signature_dispatch(self):
        for family, role in (("Firefox", "current"), ("Firefox", "minimum"),
                             ("Safari", "current")):
            for target in ("js", "wasmJs"):
                lane = f"{target}:{family}:{role}:development"
                with self.subTest(lane=lane), mock.patch(
                        "full_signed_routes.verify_browser") as replay:
                    replay.side_effect = lambda *args: {
                        "status": "PASSED", "lane": args[2], "selected_cases": 2523,
                        "archive_sha256": args[7], "candidate_sha": args[1]}
                    result, _ = self.evaluate(lane, receipt={"schema": 5})
                    self.assertEqual("PASSED", result["status"], result)
                    replay.assert_called_once()
                    replay.reset_mock()
                    result, _ = self.evaluate(lane, receipt={"schema": 5}, signed=False)
                    self.assertEqual("FAILED", result["status"])
                    replay.assert_not_called()
                    result, _ = self.evaluate(lane, receipt={"schema": 3},
                                              historical_source=False)
                    self.assertEqual("FAILED", result["status"])
                    replay.assert_not_called()
                    if family == "Firefox" and role == "minimum":
                        result, _ = self.evaluate(lane, receipt={"schema": 5},
                                                  missing_minimum_worker=True)
                        self.assertEqual("FAILED", result["status"])
                        replay.assert_not_called()
        for lane in ("wasmJs:Chromium:current:production",):
            with self.subTest(lane=lane), mock.patch("full_signed_routes.verify_browser") as replay:
                result, _ = self.evaluate(lane, receipt={"schema": 5})
                self.assertEqual("FAILED", result["status"])
                replay.assert_not_called()

    def test_schema5_firefox_minimum_production_dispatch_requires_signed_route(self):
        for target in ("js", "wasmJs"):
            lane = f"{target}:Firefox:minimum:production"
            with self.subTest(lane=lane), mock.patch(
                    "full_signed_routes.verify_browser") as replay:
                replay.side_effect = lambda *args: {
                    "status": "PASSED", "lane": args[2], "selected_cases": 2523,
                    "archive_sha256": args[7], "candidate_sha": args[1]}
                result, _ = self.evaluate(lane, receipt={"schema": 5})
                self.assertEqual("PASSED", result["status"], result)
                replay.assert_called_once()
                replay.reset_mock()
                result, _ = self.evaluate(lane, receipt={"schema": 5}, signed=False)
                self.assertEqual("FAILED", result["status"])
                replay.assert_not_called()

    def test_schema4_re_signed_wrong_observer_protocol_fails(self):
        lane = "js:Chromium:current:development"
        public = lambda *args: {"status": "PASSED", "lane": args[2],
                                "selected_cases": 2523, "archive_sha256": args[7],
                                "candidate_sha": args[1]}
        for protocol in ("bidi", "web-inspector"):
            with self.subTest(protocol=protocol), mock.patch(
                    "full_signed_routes.verify_browser", side_effect=public):
                result, _ = self.evaluate(lane, receipt={"schema": 4},
                                          protocol_change=protocol)
                self.assertEqual("FAILED", result["status"], result)
                self.assertIn("independent browser process observation differs",
                              result["reason"])

    def test_schema3_firefox_and_safari_keep_signed_protocols(self):
        public = lambda *args: {"status": "PASSED", "lane": args[2],
                                "selected_cases": 2523, "archive_sha256": args[7],
                                "candidate_sha": args[1]}
        for browser, protocol in (("Firefox", "bidi"),
                                  ("Safari", "web-inspector")):
            lane = f"js:{browser}:current:development"
            with self.subTest(lane=lane), mock.patch(
                    "full_signed_routes.verify_browser", side_effect=public):
                result, _ = self.evaluate(lane, protocol_change=protocol)
                self.assertEqual("PASSED", result["status"], result)

    def test_schema4_re_signed_external_witness_must_match_cdp_body_and_pid(self):
        lane = "js:Chromium:current:development"
        for change in ("missing_witness", "forged_witness", "stale_witness",
                       "missing_response", "missing_process", "wrong_body",
                       "wrong_interval", "before_server",
                       "wrong_clock"):
            with self.subTest(change=change), mock.patch(
                    "full_signed_routes.verify_browser") as replay:
                replay.side_effect = lambda *args: {
                    "status": "PASSED", "lane": args[2], "selected_cases": 2523,
                    "archive_sha256": args[7], "candidate_sha": args[1]}
                result, _ = self.evaluate(lane, receipt={"schema": 4}, **{change: True})
                self.assertEqual("FAILED", result["status"], result)

    def test_schema4_cdp_independent_binding_and_parallel_urls(self):
        lane = "wasmJs:Chromium:current:development"
        public = lambda *args: {"status": "PASSED", "lane": args[2],
                                "selected_cases": 2523, "archive_sha256": args[7],
                                "candidate_sha": args[1]}
        with mock.patch("full_signed_routes.verify_browser", side_effect=public):
            result, _ = self.evaluate(lane, receipt={"schema": 4}, parallel_order=True)
            self.assertEqual("PASSED", result["status"], result)
            for field, value in (("browser_pid", 999), ("body_sha256", "0" * 64),
                                 ("body_size", 999), ("response_ns", 25),
                                 ("finished_ns", 101)):
                with self.subTest(field=field):
                    result, _ = self.evaluate(lane, receipt={"schema": 4},
                                              cdp_change=(field, value))
                    self.assertEqual("FAILED", result["status"], result)

    def test_retained_a14_schema4_without_independent_audit_rejected(self):
        archive = Path("/var/home/stewart/dyn4k-evidence/root-browser-cdp-a14/js-relocated")
        if not (archive / "receipt.json").is_file():
            self.skipTest("retained a14 Chromium archive is absent")
        receipt = json.loads((archive / "receipt.json").read_text())
        result = independent_gates.evaluate_gate(
            "staged-consumer", archive, receipt["candidate_sha"], receipt["lane"],
            self.manifest["lanes"][receipt["lane"]], ROOT, receipt["staged_hashes"],
            receipt["runtime_identity"], independent_gates.archive_digest(archive),
            manifest=self.manifest, expected_signed_lane=None)
        self.assertEqual("FAILED", result["status"], result)
        self.assertIn("independently signed lane", result["reason"])

    def test_schema4_archive_mutation_and_unexecuted_statuses(self):
        lane = "js:Chromium:current:production"
        with mock.patch("full_signed_routes.verify_browser") as replay:
            result, _ = self.evaluate(lane, receipt={"schema": 4},
                                      expected_archive_digest="0" * 64)
            self.assertEqual("FAILED", result["status"])
            replay.assert_not_called()
            result, _ = self.evaluate(lane, receipt={"schema": 4, "status": "NOT_RUN"})
            self.assertEqual("NOT_RUN", result["status"])
            replay.assert_not_called()

    def test_schema2_browser_receipt_uses_signed_historical_route(self):
        lane = "js:Firefox:minimum:development"
        historical = subprocess.check_output(
            ["git", "rev-parse", "561d7329"], cwd=ROOT, text=True).strip()
        with mock.patch("full_signed_routes.verify_browser") as replay:
            replay.side_effect = lambda *args: {
                "status": "PASSED", "lane": args[2], "selected_cases": 2523,
                "archive_sha256": args[7], "candidate_sha": args[1]}
            result, _ = self.evaluate(lane, receipt={"schema": 2,
                                                    "candidate_sha": historical},
                                      candidate_sha=historical)
        self.assertEqual("PASSED", result["status"], result)
        replay.assert_called_once()
        with mock.patch("full_signed_routes.verify_browser") as replay:
            result, _ = self.evaluate(lane, receipt={"schema": 2})
        self.assertEqual("FAILED", result["status"])
        replay.assert_not_called()

    def test_schema3_unsigned_browser_receipt_fails(self):
        lane = "js:Firefox:current:development"
        with mock.patch("full_signed_routes.verify_browser") as replay:
            result, _ = self.evaluate(lane, signed=False)
            self.assertEqual("FAILED", result["status"])
            replay.assert_not_called()

    def test_schema3_missing_forged_or_stale_browser_process_witness_fails(self):
        lane = "js:Firefox:current:development"
        for change in ("missing_witness", "forged_witness", "stale_witness",
                       "wrong_body", "wrong_interval"):
            with self.subTest(change=change), mock.patch(
                    "full_signed_routes.verify_browser") as replay:
                replay.side_effect = lambda *args: {
                    "status": "PASSED", "lane": args[2], "selected_cases": 2523,
                    "archive_sha256": args[7], "candidate_sha": args[1]}
                result, _ = self.evaluate(lane, **{change: True})
                self.assertEqual("FAILED", result["status"], result)

    def test_schema3_resigned_browser_response_before_server_start_fails(self):
        lane = "js:Firefox:current:development"
        with mock.patch("full_signed_routes.verify_browser") as replay:
            replay.side_effect = lambda *args: {
                "status": "PASSED", "lane": args[2], "selected_cases": 2523,
                "archive_sha256": args[7], "candidate_sha": args[1]}
            result, _ = self.evaluate(lane, before_server=True)
        self.assertEqual("FAILED", result["status"], result)
        self.assertIn("response", result["reason"])

    def test_schema3_parallel_requests_can_invert_browser_and_server_order(self):
        lane = "js:Firefox:current:development"
        with mock.patch("full_signed_routes.verify_browser") as replay:
            replay.side_effect = lambda *args: {
                "status": "PASSED", "lane": args[2], "selected_cases": 2523,
                "archive_sha256": args[7], "candidate_sha": args[1]}
            result, _ = self.evaluate(lane, parallel_order=True)
        self.assertEqual("PASSED", result["status"], result)

    def test_schema3_unmapped_clock_fails_with_resigned_witness(self):
        lane = "wasmJs:Firefox:current:development"
        with mock.patch("full_signed_routes.verify_browser") as replay:
            replay.side_effect = lambda *args: {
                "status": "PASSED", "lane": args[2], "selected_cases": 2523,
                "archive_sha256": args[7], "candidate_sha": args[1]}
            result, _ = self.evaluate(lane, wrong_clock=True)
        self.assertEqual("FAILED", result["status"])

    def test_schema3_archive_identity_public_replay_and_attempt_status(self):
        lane = "wasmJs:Firefox:minimum:production"
        public = lambda *args: {"status": "PASSED", "lane": args[2],
                                "selected_cases": 2523, "archive_sha256": args[7],
                                "candidate_sha": args[1]}
        with mock.patch("full_signed_routes.verify_browser", side_effect=public) as replay:
            result, _ = self.evaluate(lane, expected_archive_digest="f" * 64)
            self.assertEqual("FAILED", result["status"])
            replay.assert_not_called()
            result, _ = self.evaluate(lane, receipt={"status": "FAILED"})
            self.assertEqual("FAILED", result["status"])
            replay.assert_not_called()
            result, _ = self.evaluate(lane, receipt={"status": "NOT_RUN"})
            self.assertEqual("NOT_RUN", result["status"])
            replay.assert_not_called()
        with mock.patch("full_signed_routes.verify_browser", return_value={
                "status": "PASSED", "lane": lane, "selected_cases": 2522,
                "archive_sha256": "f" * 64, "candidate_sha": self.candidate}):
            result, _ = self.evaluate(lane)
            self.assertEqual("FAILED", result["status"])

    def test_schema3_approved_lane_and_complete_methods_are_required(self):
        lane = "wasmJs:Safari:current:development"
        changed = {**self.manifest, "cases": self.manifest["cases"][:-1]}
        with mock.patch("full_signed_routes.verify_browser") as replay:
            result, _ = self.evaluate(lane, manifest=changed)
            self.assertEqual("FAILED", result["status"])
            result, _ = self.evaluate(lane, lane_id="wasmJs:Safari:minimum:development")
            self.assertEqual("FAILED", result["status"])
            replay.assert_not_called()

    def test_schema3_source_host_and_response_verifier_failures_propagate(self):
        lane = "js:Safari:current:production"
        for reason in ("public producer or central verifier differs from candidate",
                       "browser runtime or toolchain differs from signed lane",
                       "browser HTTP response bytes differ from selected source"):
            with self.subTest(reason=reason), mock.patch(
                    "full_signed_routes.verify_browser", side_effect=ValueError(reason)):
                result, _ = self.evaluate(lane)
                self.assertEqual("FAILED", result["status"])
                self.assertIn(reason, result["reason"])
