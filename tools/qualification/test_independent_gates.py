import json
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
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
MANIFEST_REV = "6f983ad3a36bdc549c32f5d0883b0a47b28e1963"
LANE = "jvm:Java:minimum:no-optimize"


class IndependentGateSeamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(subprocess.check_output(
            ["git", "show", f"{MANIFEST_REV}:tools/qualification/full-suite-manifest.json"],
            cwd=ROOT))

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

    def test_numerical_checker_and_limits_match_approved_candidate_blobs(self):
        approved = independent_gates._policy_binding(ROOT, BASE)
        self.assertEqual(set(independent_gates.APPROVED_POLICY), set(approved))
        name = "tools/numerical/fixtures.json"
        original = independent_gates.APPROVED_POLICY[name]
        try:
            independent_gates.APPROVED_POLICY[name] = "0" * 64
            with self.assertRaisesRegex(ValueError, "approved policy/checker blob differs"):
                independent_gates._policy_binding(ROOT, BASE)
        finally:
            independent_gates.APPROVED_POLICY[name] = original

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
                os.utime(root / name, ns=(started + 1, started + 1))
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
            receipt["files"][0]["mtime_ns"] = started + 1
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
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "stdout.txt").write_text("execution\n")
            started = time.time_ns() - 1_000_000
            os.utime(root / "stdout.txt", ns=(started + 1, started + 1))
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
                           "mtime_ns": started + 1}],
            }
            for field, wrong in (("candidate_sha", "f" * 40), ("lane", "other")):
                receipt[field] = wrong
                (root / "receipt.json").write_text(json.dumps(receipt))
                for gate in names:
                    with self.subTest(gate=gate, field=field):
                        result = independent_gates.evaluate(
                            self.manifest, BASE, LANE, {gate: root}, ROOT,
                            receipt["artifact_hashes"], "OpenJDK 8",
                            {gate: independent_gates.archive_digest(root)})["gates"][gate]
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
                        {gate: independent_gates.archive_digest(root)})["gates"][gate]
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
            receipt = {
                "schema": 1, "status": "PASSED", "candidate_sha": BASE,
                "source_tree": subprocess.check_output(
                    ["git", "rev-parse", f"{BASE}^{{tree}}"], cwd=ROOT, text=True).strip(),
                "lane": LANE, "target": "jvm", "runtime": "Java",
                "version": "minimum", "configuration": "no-optimize",
                "runtime_identity": "review CLI", "artifact_hashes": hashes,
                "process": {"command": ["codex", "exec", "review"], "exit_code": 0,
                            "started_ns": started, "finished_ns": finished},
            }

            def write():
                files = [file for file in root.iterdir() if file.name != "receipt.json"]
                for file in files:
                    os.utime(file, ns=(started + 1, started + 1))
                receipt["files"] = [{"path": file.name,
                                     "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                                     "mtime_ns": started + 1} for file in files]
                (root / "receipt.json").write_text(json.dumps(receipt))

            def status():
                return independent_gates.evaluate(
                    self.manifest, BASE, LANE, {"independent-review": root}, ROOT,
                    hashes, "review CLI",
                    {"independent-review": independent_gates.archive_digest(root)})["gates"]["independent-review"]["status"]

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
                        os.utime(file, ns=(started + 1, started + 1))
                receipt["files"] = [{"path": file.name,
                                     "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                                     "mtime_ns": started + 1}
                                    for file in root.iterdir() if file.name != "receipt.json"]
                (root / "receipt.json").write_text(json.dumps(receipt))

            def status():
                return independent_gates.evaluate(
                    self.manifest, BASE, LANE, {"staged-consumer": root},
                    ROOT, hashes, "OpenJDK 8",
                    {"staged-consumer": independent_gates.archive_digest(root)})["gates"]["staged-consumer"]

            write()
            self.assertEqual("PASSED", status()["status"])
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

    def test_full_suite_consumer_route_accepts_approved_nonfoundation_case_set(self):
        lane_id = next(key for key, lane in self.manifest["lanes"].items()
                       if lane["target"] == "androidNativeArm64")
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
                f"QUALIFICATION_LANE={lane_id}\nQUALIFICATION_PROCESS_EXIT=0\n"
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
                os.utime(file, ns=(started + 1, started + 1))
            receipt = {"schema": 1, "status": "PASSED", "candidate_sha": BASE,
                       "source_tree": subprocess.check_output(
                           ["git", "rev-parse", f"{BASE}^{{tree}}"], cwd=ROOT, text=True).strip(),
                       "lane": lane_id, **{key: lane[key] for key in
                                           ("target", "runtime", "version", "configuration")},
                       "runtime_identity": "selected device fixture", "artifact_hashes": hashes,
                       "process": {"command": ["adb", "shell", "consumer", lane_id],
                                   "exit_code": 0, "started_ns": started,
                                   "finished_ns": started + 2_000_000, "stdout": "stdout.txt"},
                       "consumer_group": "full-suite",
                       "consumer_contract_sha256": independent_gates.digest(contract),
                       "consumer_xml": ["consumer.xml"], "provider_graph": "graph.txt",
                       "resolved_artifacts": {"dyn4k-core": "core.bin", "dyn4k": "api.bin"},
                       "files": [{"path": file.name,
                                  "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                                  "mtime_ns": started + 1} for file in files]}
            (root / "receipt.json").write_text(json.dumps(receipt))
            def result():
                return independent_gates.evaluate(
                    self.manifest, BASE, lane_id, {"staged-consumer": root}, ROOT,
                    hashes, "selected device fixture",
                    {"staged-consumer": independent_gates.archive_digest(root)})["gates"]["staged-consumer"]
            self.assertEqual("PASSED", result()["status"], result()["reason"])
            suite.find("testcase").set("id", "invented:case")
            (root / "consumer.xml").write_bytes(ET.tostring(suite))
            os.utime(root / "consumer.xml", ns=(started + 1, started + 1))
            receipt["files"][0]["sha256"] = hashlib.sha256((root / "consumer.xml").read_bytes()).hexdigest()
            (root / "receipt.json").write_text(json.dumps(receipt))
            self.assertEqual("FAILED", result()["status"])

    def test_java_source_rejects_legacy_case_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "reviewed full_ci raw archive contract"):
                independent_gates._java_full_ci(
                    Path(temporary), {"producer": "legacy-case-manifest"},
                    "java-source-compatibility", BASE, ROOT,
                    {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64})

    @unittest.skipUnless(Path("/tmp/dyn4k-archive-relocation-copy-7032/lane-manifest.json").is_file(),
                         "reviewed local full_ci archive is absent")
    def test_reviewed_full_ci_archive_replays_unchanged_and_strict_java_gates(self):
        source = Path("/tmp/dyn4k-archive-relocation-copy-7032")
        candidate = "7032b41c780a08c850226eb2c984fb15af444a23"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(source, root / "full-ci")
            (root / "facade.bin").write_bytes(b"separate facade fixture")
            evidence = json.loads((root / "full-ci/result.json").read_text())
            hashes = {"dyn4k-core": evidence["archives"]["staged_jvm_jar"],
                      "dyn4k": hashlib.sha256((root / "facade.bin").read_bytes()).hexdigest()}
            started = time.time_ns() - 1_000_000_000
            finished = time.time_ns() + 1_000_000_000
            receipt = {"schema": 1, "status": "PASSED", "candidate_sha": candidate,
                       "source_tree": subprocess.check_output(
                           ["git", "rev-parse", f"{candidate}^{{tree}}"], cwd=ROOT, text=True).strip(),
                       "lane": LANE, "target": "jvm", "runtime": "Java",
                       "version": "minimum", "configuration": "no-optimize",
                       "runtime_identity": "reviewed local archive", "artifact_hashes": hashes,
                       "process": {"command": ["python3", "tools/compatibility/full_ci.py", "verify"],
                                   "exit_code": 0, "started_ns": started, "finished_ns": finished},
                       "producer": "reviewed-full-ci", "full_ci_archive": "full-ci",
                       "full_ci_manifest_sha256": hashlib.sha256(
                           (root / "full-ci/lane-manifest.json").read_bytes()).hexdigest(),
                       "resolved_artifacts": {
                           "dyn4k-core": "full-ci/archives/dyn4k-core-jvm-0.1.0-alpha.1.jar",
                           "dyn4k": "facade.bin"}}
            files = [path for path in root.rglob("*") if path.is_file()]
            for path in files:
                os.utime(path, ns=(started + 1, started + 1))
            receipt["files"] = [{"path": path.relative_to(root).as_posix(),
                                 "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                 "mtime_ns": started + 1} for path in files]
            (root / "receipt.json").write_text(json.dumps(receipt))
            pin = independent_gates.archive_digest(root)
            for gate in ("unchanged-java-corpus", "java-source-compatibility"):
                with self.subTest(gate=gate):
                    result = independent_gates.evaluate(
                        self.manifest, candidate, LANE, {gate: root}, ROOT, hashes,
                        "reviewed local archive", {gate: pin})["gates"][gate]
                    self.assertEqual("PASSED", result["status"], result["reason"])
            (root / "full-ci/logs/run-candidate-javac8-java8.log").write_text("mutated\n")
            result = independent_gates.evaluate(
                self.manifest, candidate, LANE, {"unchanged-java-corpus": root}, ROOT,
                hashes, "reviewed local archive", {"unchanged-java-corpus": pin})
            self.assertEqual("FAILED", result["gates"]["unchanged-java-corpus"]["status"])

    @unittest.skipUnless(Path("/tmp/dyn4k-merge-complete-corpus-rotation-migration-journeys-0681a8cd/summary.json").is_file(),
                         "reviewed local migration archive is absent")
    def test_historical_migration_raw_scenes_replay_and_input_mutation_fails(self):
        source = Path("/tmp/dyn4k-merge-complete-corpus-rotation-migration-journeys-0681a8cd")
        samples = Path("/tmp/dyn4k-migration-preflight/samples")
        if not samples.is_dir():
            self.skipTest("pinned unchanged sample checkout is absent")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "evidence"
            shutil.copytree(source, evidence)
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
            candidate_jar = Path("/tmp/dyn4k-archive-relocation-copy-7032/archives/dyn4k-core-jvm-0.1.0-alpha.1.jar")
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
            report = json.loads((evidence / "summary.json").read_text())
            journeys.write_summary(evidence, report)
            hashes = {"dyn4k-core": hashlib.sha256(candidate_jar.read_bytes()).hexdigest()}
            self.assertIn("ten pinned migration journeys",
                          independent_gates._migration_journeys(root, report["candidate_commit"], hashes))
            (root / "facade.bin").write_bytes(b"separate facade fixture")
            hashes["dyn4k"] = hashlib.sha256((root / "facade.bin").read_bytes()).hexdigest()
            started = time.time_ns() - 1_000_000_000
            finished = time.time_ns() + 1_000_000_000
            files = [path for path in root.rglob("*") if path.is_file()]
            for path in files:
                os.utime(path, ns=(started + 1, started + 1))
            receipt = {"schema": 1, "status": "PASSED",
                       "candidate_sha": report["candidate_commit"],
                       "source_tree": subprocess.check_output(
                           ["git", "rev-parse", f"{report['candidate_commit']}^{{tree}}"],
                           cwd=ROOT, text=True).strip(),
                       "lane": LANE, "target": "jvm", "runtime": "Java",
                       "version": "minimum", "configuration": "no-optimize",
                       "runtime_identity": "historical migration archive", "artifact_hashes": hashes,
                       "process": {"command": ["python3", "tools/migration/journeys.py", "run"],
                                   "exit_code": 0, "started_ns": started, "finished_ns": finished},
                       "files": [{"path": path.relative_to(root).as_posix(),
                                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                  "mtime_ns": started + 1} for path in files]}
            (root / "receipt.json").write_text(json.dumps(receipt))
            pin = independent_gates.archive_digest(root)
            selected = independent_gates.evaluate(
                self.manifest, report["candidate_commit"], LANE,
                {"migration-journeys": root}, ROOT, hashes,
                "historical migration archive", {"migration-journeys": pin})
            self.assertEqual("PASSED", selected["gates"]["migration-journeys"]["status"])
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
