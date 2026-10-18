import json
import hashlib
import subprocess
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import independent_gates
import qualify


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

    def test_duplicate_provider_requires_raw_graph_and_diagnostic(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            graph = "org.dyn4j:dyn4j:6.0.0\nio.github.rubixhacker:dyn4k-core-jvm:0.1.0-alpha.1\n"
            (root / "graph.txt").write_text(graph)
            (root / "stderr.txt").write_text(
                "duplicate org.dyn4j provider: exclude org.dyn4j:dyn4j\n")
            started = time.time_ns() - 1_000_000
            finished = time.time_ns() + 1_000_000
            artifact_hashes = {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64}
            receipt = {
                "schema": 1, "status": "PASSED", "candidate_sha": BASE,
                "source_tree": subprocess.check_output(
                    ["git", "rev-parse", f"{BASE}^{{tree}}"], cwd=ROOT, text=True).strip(),
                "lane": LANE, "target": "jvm", "runtime": "Java",
                "version": "minimum", "configuration": "no-optimize",
                "runtime_identity": "OpenJDK 8 test fixture", "artifact_hashes": artifact_hashes,
                "process": {"command": ["./gradlew", "diagnoseDuplicateProviders"],
                            "exit_code": 1, "started_ns": started,
                            "finished_ns": finished, "stderr": "stderr.txt"},
                "provider_graph": "graph.txt",
                "files": [{"path": name,
                           "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest(),
                           "mtime_ns": started + 1}
                          for name in ("graph.txt", "stderr.txt")],
            }
            (root / "receipt.json").write_text(json.dumps(receipt))

            def status():
                return independent_gates.evaluate(
                    self.manifest, BASE, LANE, {"duplicate-provider": root}, ROOT,
                    artifact_hashes, "OpenJDK 8 test fixture")["gates"]["duplicate-provider"]

            self.assertEqual("PASSED", status()["status"])
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
                        self.manifest, BASE, LANE, {gate: root}, ROOT)
                    self.assertEqual("FAILED", observed["gates"][gate]["status"])

    def test_every_route_rejects_wrong_lane_and_candidate(self):
        names = (set(self.manifest["lanes"][LANE]["required_gates"])
                 | set(self.manifest["global_gates"]))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "stdout.txt").write_text("execution\n")
            started = time.time_ns() - 1_000_000
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
                            receipt["artifact_hashes"], "OpenJDK 8")["gates"][gate]
                        self.assertEqual("FAILED", result["status"])
                        self.assertIn("candidate" if field == "candidate_sha" else "lane",
                                      result["reason"])
                receipt[field] = BASE if field == "candidate_sha" else LANE
            (root / "receipt.json").write_text(json.dumps(receipt))
            for gate in names:
                with self.subTest(gate=gate, missing="producer raw"):
                    result = independent_gates.evaluate(
                        self.manifest, BASE, LANE, {gate: root}, ROOT,
                        receipt["artifact_hashes"], "OpenJDK 8")["gates"][gate]
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
                receipt["files"] = [{"path": file.name,
                                     "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                                     "mtime_ns": started + 1}
                                    for file in root.iterdir() if file.name != "receipt.json"]
                (root / "receipt.json").write_text(json.dumps(receipt))

            def status():
                return independent_gates.evaluate(
                    self.manifest, BASE, LANE, {"independent-review": root}, ROOT,
                    hashes, "review CLI")["gates"]["independent-review"]["status"]

            for kind, session in (("standards", "session-a"), ("spec", "session-b")):
                report = {"review_kind": kind, "candidate_sha": BASE,
                          "model": "gpt-6-sol", "session_id": session,
                          "findings": []}
                (root / f"{kind}.json").write_text(json.dumps(report))
                (root / f"{kind}.jsonl").write_text("\n".join(json.dumps(item) for item in (
                    {"type": "session_meta", "payload": {"id": session}},
                    {"type": "turn_context", "payload": {"model": "gpt-6-sol"}},
                    {"type": "response_item", "payload": {"review": kind,
                                                            "candidate_sha": BASE}},
                )) + "\n")
                write()
                self.assertEqual("FAILED" if kind == "standards" else "PASSED", status())
            report["findings"] = [{"id": "finding-1"}]
            (root / "spec.json").write_text(json.dumps(report))
            write()
            self.assertEqual("FAILED", status())
            report["findings"][0]["resolution"] = {
                "status": "RESOLVED", "candidate_sha": BASE, "evidence": "README.md"}
            (root / "spec.json").write_text(json.dumps(report))
            write()
            self.assertEqual("PASSED", status())
            report["findings"][0]["resolution"]["evidence"] = "../README.md"
            (root / "spec.json").write_text(json.dumps(report))
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
                "process": {"command": ["./gradlew", "jvmTest"], "exit_code": 0,
                            "started_ns": started, "finished_ns": started + 2_000_000},
                "consumer_group": "consumer-jvm", "consumer_xml": ["consumer.xml"],
                "provider_graph": "graph.txt",
                "resolved_artifacts": {"dyn4k-core": "core.bin", "dyn4k": "api.bin"},
            }

            def write():
                receipt["files"] = [{"path": file.name,
                                     "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                                     "mtime_ns": started + 1}
                                    for file in root.iterdir() if file.name != "receipt.json"]
                (root / "receipt.json").write_text(json.dumps(receipt))

            def status():
                return independent_gates.evaluate(
                    self.manifest, BASE, LANE, {"staged-consumer": root},
                    ROOT, hashes, "OpenJDK 8")["gates"]["staged-consumer"]

            write()
            self.assertEqual("PASSED", status()["status"])
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
