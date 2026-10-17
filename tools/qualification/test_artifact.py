import hashlib
import json
import os
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import artifact
import qualify


class RawArtifactTests(unittest.TestCase):
    def test_missing_core_xml_rejects_bounded_pass_then_complete_bundle_passes(self):
        sha = "a" * 40
        target = "macosArm64"
        manifest = qualify.load_json_strict(Path(__file__).with_name("foundation-probes.json"))
        groups = {group["id"]: group for group in manifest["groups"]}
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            staging = repository / "build/staging-repository"
            hashes = {}
            for module in qualify.MODULES:
                for artifact_target in (target, "jvm", "linuxX64", "js", "wasmJs", "wasmWasi", "android"):
                    binary = staging / qualify.target_binary_path(module, artifact_target)
                    binary.parent.mkdir(parents=True, exist_ok=True)
                    binary.write_bytes(module.encode())
                    digest = hashlib.sha256(module.encode()).hexdigest()
                    binary.with_name(binary.name + ".sha256").write_text(digest + "\n")
                    if artifact_target == target:
                        hashes[module] = digest
                for publication in (module, *(qualify.target_publication_name(module, item)
                                             for item in (target, "jvm", "linuxX64", "js", "wasmJs", "wasmWasi", "android"))):
                    base = staging / qualify.GROUP.replace(".", "/") / publication / qualify.VERSION
                    base.mkdir(parents=True, exist_ok=True)
                    (base / f"{publication}-{qualify.VERSION}.pom").write_text(
                        f'<project xmlns="http://maven.apache.org/POM/4.0.0">'
                        f'<groupId>{qualify.GROUP}</groupId><artifactId>{publication}</artifactId>'
                        f'<version>{qualify.VERSION}</version></project>')
                    (base / f"{publication}-{qualify.VERSION}.module").write_text(
                        json.dumps({"component": {"version": qualify.VERSION}}))
            started = time.time_ns() - 5_000_000_000
            finished = time.time_ns() + 5_000_000_000

            def probe(ids, count):
                selected = {**manifest, "groups": [groups[group_id] for group_id in ids]}
                return {"candidate_sha": sha, "status": "PROBE_PASSED", "expected": count,
                        "executed": count, "failures": 0, "skipped": 0, "exit_code": 0,
                        "manifest_sha256": qualify.manifest_digest(selected),
                        "started_at_ns": started, "finished_at_ns": finished}

            source = probe(("core-macosArm64", "macosArm64"), 475)
            consumer = probe(("consumer-macosArm64",), 2)
            hosted = {"candidate_sha": sha, "target": target, "status": "PROBE_PASSED",
                      "runtime": {"system": "Darwin", "machine": "arm64",
                                  "os_version": "26.6.2", "xcode_version": "26.4.1",
                                  "simulators": {}},
                      "source_probe": source, "consumer_probe": consumer,
                      "artifact_hashes": hashes}
            probe_path = repository / "hosted-macosArm64.json"
            probe_path.write_text(json.dumps(hosted))
            probe_path.with_name("hosted-macosArm64-source.json").write_text(json.dumps(source))
            probe_path.with_name("hosted-macosArm64-consumer.json").write_text(json.dumps(consumer))
            matrix_path = repository / "matrix-macosArm64.json"
            matrix_path.write_text(json.dumps({"candidate_sha": sha,
                                               "total": 112,
                                               "bounded_hosted_probes": [hosted],
                                               "counts": {"PASSED": 0, "FAILED": 0,
                                                          "UNAVAILABLE": 0, "NOT_RUN": 112}}))

            def write_group(group_id):
                group = groups[group_id]
                by_class = defaultdict(list)
                for classname, name in qualify.expected_probe_cases(manifest, group):
                    by_class[classname].append(name)
                directory = repository / Path(group["report_pattern"]).parent
                directory.mkdir(parents=True, exist_ok=True)
                for classname, names in by_class.items():
                    suite = ET.Element("testsuite", tests=str(len(names)), failures="0",
                                       errors="0", skipped="0", time="0.1")
                    for name in names:
                        ET.SubElement(suite, "testcase", classname=classname,
                                      name=name, time="0.1")
                    (directory / f"TEST-{classname}.xml").write_bytes(ET.tostring(suite))

            write_group(target)
            write_group("consumer-macosArm64")
            missing = artifact.stage_hosted(repository, manifest, sha, target, probe_path,
                                            matrix_path, repository / "bundle-missing")
            self.assertEqual("PROBE_FAILED", missing["status"])
            self.assertIn("core-macosArm64", missing["reason"])

            write_group("core-macosArm64")
            complete = artifact.stage_hosted(repository, manifest, sha, target, probe_path,
                                             matrix_path, repository / "bundle-complete")
            self.assertEqual("PROBE_PASSED", complete["status"])
            self.assertEqual(477, complete["executed"])
            self.assertEqual(432, complete["groups"]["core-macosArm64"])
            self.assertEqual(4, len(complete["gav"]))
            self.assertEqual(4, len(list((repository / "bundle-complete/staged").rglob("*.pom"))))
            workflow_bundle = repository / "bundle-workflow"
            workflow_result = artifact.stage_hosted(repository, manifest, sha, target,
                                                    probe_path, None, workflow_bundle)
            self.assertEqual("PROBE_PASSED", workflow_result["status"])
            artifact.verify_bundle(workflow_bundle, manifest, sha)
            (workflow_bundle / "json/matrix-macosArm64.json").write_bytes(matrix_path.read_bytes())
            artifact.verify_bundle(workflow_bundle, manifest, sha)
            inventory_path = workflow_bundle / "verification.json"
            inventory_bytes = inventory_path.read_bytes()
            windows_inventory = json.loads(inventory_bytes)
            for item in windows_inventory["files"] + windows_inventory["staged_files"]:
                item["path"] = item["path"].replace("/", "\\")
            inventory_path.write_text(json.dumps(windows_inventory))
            artifact.verify_bundle(workflow_bundle, manifest, sha)
            windows_inventory["files"][0]["path"] = "..\\outside.xml"
            inventory_path.write_text(json.dumps(windows_inventory))
            with self.assertRaisesRegex(ValueError, "inventory path is unsafe"):
                artifact.verify_bundle(workflow_bundle, manifest, sha)
            inventory_path.write_bytes(inventory_bytes)
            archived_xml = next((workflow_bundle / "xml").rglob("*.xml"))
            os.utime(archived_xml, ns=(1_000_000_000, 1_000_000_000))
            artifact.verify_bundle(workflow_bundle, manifest, sha)
            inventory = json.loads(inventory_bytes)
            inventory["files"][0]["mtime_ns"] = 1
            inventory_path.write_text(json.dumps(inventory))
            with self.assertRaisesRegex(ValueError, "stale report"):
                artifact.verify_bundle(workflow_bundle, manifest, sha)
            inventory_path.write_bytes(inventory_bytes)
            source_xml = next((repository / "dyn4k-core/build/test-results/macosArm64Test").glob("*.xml"))
            original = source_xml.read_bytes()

            def reject_changed_xml(label, edit):
                source_xml.write_bytes(original)
                edit()
                rejected = artifact.stage_hosted(repository, manifest, sha, target, probe_path,
                                                 matrix_path, repository / f"bundle-{label}")
                self.assertEqual("PROBE_FAILED", rejected["status"])
                source_xml.write_bytes(original)

            def rename_case():
                suite = ET.parse(source_xml).getroot()
                next(suite.iter("testcase")).set("name", "unexpectedCase")
                source_xml.write_bytes(ET.tostring(suite))

            def skip_case():
                suite = ET.parse(source_xml).getroot()
                ET.SubElement(next(suite.iter("testcase")), "skipped")
                suite.set("skipped", "1")
                source_xml.write_bytes(ET.tostring(suite))

            def remove_case():
                suite = ET.parse(source_xml).getroot()
                suite.remove(next(suite.iter("testcase")))
                suite.set("tests", str(int(suite.get("tests")) - 1))
                source_xml.write_bytes(ET.tostring(suite))

            reject_changed_xml("renamed", rename_case)
            reject_changed_xml("skipped", skip_case)
            reject_changed_xml("partial", remove_case)
            source_xml.write_bytes(original)
            os.utime(source_xml, ns=(started - 1, started - 1))
            stale_xml = artifact.stage_hosted(repository, manifest, sha, target, probe_path,
                                              matrix_path, repository / "bundle-old-xml")
            self.assertEqual("PROBE_FAILED", stale_xml["status"])
            self.assertIn("stale report", stale_xml["reason"])
            source_xml.write_bytes(original)
            self.assertEqual(477, artifact.verify_bundle(repository / "bundle-complete",
                                                          manifest, sha)["executed"])
            bundle = repository / "bundle-complete"
            bundled_sidecar = bundle / "json/hosted-macosArm64-source.json"
            sidecar_bytes = bundled_sidecar.read_bytes()
            bundled_sidecar.write_text(json.dumps({**source, "started_at_ns": started + 1}))
            with self.assertRaisesRegex(ValueError, "differs from hosted observation"):
                artifact.verify_bundle(bundle, manifest, sha)
            bundled_sidecar.write_bytes(sidecar_bytes)
            staged_pom = next((bundle / "staged").rglob("*.pom"))
            pom_bytes = staged_pom.read_bytes()
            staged_pom.write_bytes(pom_bytes + b" ")
            with self.assertRaisesRegex(ValueError, "descriptor or checksum differs"):
                artifact.verify_bundle(bundle, manifest, sha)
            staged_pom.write_bytes(pom_bytes)
            first_core = next((repository / "bundle-complete/xml/dyn4k-core/build/test-results/macosArm64Test").glob("*.xml"))
            first_core.unlink()
            with self.assertRaisesRegex(ValueError, "partial|missing"):
                artifact.verify_bundle(repository / "bundle-complete", manifest, sha)

            hosted.update(status="UNAVAILABLE", reason="runner is unavailable")
            probe_path.write_text(json.dumps(hosted))
            unavailable = artifact.stage_hosted(repository, manifest, sha, target, probe_path,
                                                matrix_path, repository / "bundle-unavailable")
            self.assertEqual("UNAVAILABLE", unavailable["status"])

            hosted["candidate_sha"] = "b" * 40
            probe_path.write_text(json.dumps(hosted))
            stale = artifact.stage_hosted(repository, manifest, sha, target, probe_path,
                                          matrix_path, repository / "bundle-stale")
            self.assertEqual("PROBE_FAILED", stale["status"])
            self.assertIn("candidate", stale["reason"])

            for ids in artifact.UBUNTU_PROBES.values():
                for group_id in ids:
                    if group_id != "core-jvm":
                        write_group(group_id)
            for name, ids in artifact.UBUNTU_PROBES.items():
                count = sum(len(qualify.expected_probe_cases(manifest, groups[group_id]))
                            for group_id in ids)
                (repository / name).write_text(json.dumps(probe(ids, count)))
            (repository / "artifact-audit.json").write_text(json.dumps(
                {"candidate_sha": sha, "status": "FAILED"}))
            (repository / "runtime-matrix.json").write_text(json.dumps(
                {"candidate_sha": sha, "total": 112,
                 "counts": {"PASSED": 0, "FAILED": 0, "UNAVAILABLE": 0, "NOT_RUN": 112}}))
            (repository / "provider.log").write_text("duplicate org.dyn4j provider\n")
            missing_ubuntu = artifact.stage_ubuntu(repository, manifest, sha, repository,
                                                    repository / "ubuntu-missing")
            self.assertEqual("PROBE_FAILED", missing_ubuntu["status"])
            self.assertIn("core-jvm", missing_ubuntu["reason"])
            write_group("core-jvm")
            complete_ubuntu = artifact.stage_ubuntu(repository, manifest, sha, repository,
                                                     repository / "ubuntu-complete")
            self.assertEqual("PROBE_PASSED", complete_ubuntu["status"])
            self.assertEqual("Linux", complete_ubuntu["runtime"]["system"])
            self.assertEqual(2864, complete_ubuntu["executed"])
            self.assertEqual(2864, artifact.verify_bundle(repository / "ubuntu-complete",
                                                           manifest, sha)["executed"])
            summary_path = repository / "ubuntu-complete/verification.json"
            summary = json.loads(summary_path.read_text())
            summary["runtime"]["system"] = "Windows"
            summary_path.write_text(json.dumps(summary))
            with self.assertRaisesRegex(ValueError, "Ubuntu bundle runtime"):
                artifact.verify_bundle(repository / "ubuntu-complete", manifest, sha)


if __name__ == "__main__":
    unittest.main()
