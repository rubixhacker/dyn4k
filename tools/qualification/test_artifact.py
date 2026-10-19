import hashlib
import json
import os
import shutil
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

import artifact
import full_hosted
import qualify
import test_publication


class RawArtifactTests(unittest.TestCase):

    def test_full_hosted_rejects_non_object_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "bundle"
            bundle.mkdir()
            (bundle / "receipt.json").write_text("[]")
            with self.assertRaisesRegex(ValueError, "receipt.*object"):
                artifact.verify_full_hosted(bundle, "a" * 40, root)
            archive = root / "bundle.tar"
            full_hosted.package_archive(bundle, archive)
            with self.assertRaisesRegex(ValueError, "receipt.*object"):
                artifact.verify_full_hosted(archive, "a" * 40, root)

    def test_missing_core_xml_rejects_bounded_pass_then_complete_bundle_passes(self):
        sha = "a" * 40
        target = "macosArm64"
        manifest = qualify.load_json_strict(Path(__file__).with_name("foundation-probes.json"))
        groups = {group["id"]: group for group in manifest["groups"]}
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            staging = test_publication.PublicationAuditTests().stage(
                repository, (target, "jvm", "linuxX64", "js", "wasmJs", "wasmWasi", "android"))
            hashes = {module: qualify.digest(staging / qualify.target_binary_path(module, target))
                      for module in qualify.MODULES}
            started = time.time_ns()
            finished = started

            def probe(ids, count, extra_reports=None):
                selected = {**manifest, "groups": [groups[group_id] for group_id in ids]}
                extra_reports = extra_reports or {}
                summaries = []
                for group_id in ids:
                    selected_count = len(qualify.expected_probe_cases(manifest, groups[group_id]))
                    summaries.append({"id": group_id, "expected": selected_count,
                                      "executed": selected_count,
                                      "reported": selected_count + extra_reports.get(group_id, 0),
                                      "failures": 0, "errors": 0, "skipped": 0})
                return {"candidate_sha": sha, "status": "PROBE_PASSED", "expected": count,
                        "executed": count,
                        "reported": sum(item["reported"] for item in summaries),
                        "groups": summaries, "failures": 0, "errors": 0,
                        "skipped": 0, "exit_code": 0,
                        "manifest_sha256": qualify.manifest_digest(selected),
                        "started_at_ns": started, "finished_at_ns": finished}

            source = probe(("core-macosArm64", "macosArm64"), 1111,
                           {"core-macosArm64": 1})
            consumer = probe(("consumer-macosArm64",), 3)
            hosted = {"candidate_sha": sha, "target": target, "status": "PROBE_PASSED",
                      "runtime": {"system": "Darwin", "machine": "arm64",
                                  "os_version": "26.6.2", "xcode_version": "26.5",
                                  "simulators": {}},
                      "source_probe": source, "consumer_probe": consumer,
                      "artifact_hashes": hashes}
            probe_path = repository / "hosted-macosArm64.json"
            matrix_path = repository / "matrix-macosArm64.json"
            lanes = [{"id": case["id"], "status": "NOT_RUN", "reason": "no evidence supplied"}
                     for case in qualify.expand(qualify.matrix())]

            def record_probe_window():
                finished_at = time.time_ns()
                source["finished_at_ns"] = finished_at
                consumer["finished_at_ns"] = finished_at
                probe_path.write_text(json.dumps(hosted))
                probe_path.with_name("hosted-macosArm64-source.json").write_text(json.dumps(source))
                probe_path.with_name("hosted-macosArm64-consumer.json").write_text(json.dumps(consumer))
                matrix_path.write_text(json.dumps({"candidate_sha": sha, "total": 112,
                                                   "bounded_hosted_probes": [hosted],
                                                   "lanes": lanes,
                                                   "counts": {"PASSED": 0, "FAILED": 0,
                                                              "UNAVAILABLE": 0, "NOT_RUN": 112}}))

            def write_group(group_id, extras=()):
                group = groups[group_id]
                by_class = defaultdict(list)
                for classname, name in qualify.expected_probe_cases(manifest, group):
                    by_class[classname].append(name)
                for classname, name in extras:
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
            record_probe_window()
            missing = artifact.stage_hosted(repository, manifest, sha, target, probe_path,
                                            matrix_path, repository / "bundle-missing")
            self.assertEqual("PROBE_FAILED", missing["status"])
            self.assertIn("core-macosArm64", missing["reason"])

            write_group("core-macosArm64", [("supplemental.FullReportTest", "extra-pass")])
            record_probe_window()
            complete = artifact.stage_hosted(repository, manifest, sha, target, probe_path,
                                             matrix_path, repository / "bundle-complete")
            self.assertEqual("PROBE_PASSED", complete["status"])
            self.assertEqual(1114, complete["executed"])
            self.assertEqual(1115, complete["reported"])
            self.assertEqual(1066, complete["groups"]["core-macosArm64"])
            self.assertEqual(1067, complete["reported_groups"]["core-macosArm64"])
            self.assertEqual(4, len(complete["gav"]))
            self.assertEqual(4, len(list((repository / "bundle-complete/staged").rglob("*.pom"))))
            workflow_bundle = repository / "bundle-workflow"
            workflow_result = artifact.stage_hosted(repository, manifest, sha, target,
                                                    probe_path, None, workflow_bundle)
            self.assertEqual("PROBE_PASSED", workflow_result["status"])
            with self.assertRaisesRegex(ValueError, "matrix.*missing"):
                artifact.verify_bundle(workflow_bundle, manifest, sha)
            artifact.verify_bundle(workflow_bundle, manifest, sha, require_matrix=False)
            (workflow_bundle / "json/matrix-macosArm64.json").write_bytes(matrix_path.read_bytes())
            artifact.verify_bundle(workflow_bundle, manifest, sha)
            missing_docs = repository / "bundle-missing-docs"
            shutil.copytree(workflow_bundle, missing_docs)
            docs = next((missing_docs / "staged").rglob("dyn4k-macosarm64-*-javadoc.jar"))
            docs.unlink()
            with self.assertRaisesRegex(ValueError, "staged GAV|partial"):
                artifact.verify_bundle(missing_docs, manifest, sha)

            def reject_matrix(label, edit, reason):
                changed = repository / f"bundle-matrix-{label}"
                shutil.copytree(workflow_bundle, changed)
                path = changed / "json/matrix-macosArm64.json"
                data = json.loads(path.read_text())
                edit(data)
                path.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError, reason):
                    artifact.verify_bundle(changed, manifest, sha)

            def empty_with_fabricated_passes(data):
                data["lanes"] = []
                data["counts"] = {"PASSED": 112, "FAILED": 0,
                                  "UNAVAILABLE": 0, "NOT_RUN": 0}

            def duplicate_lane(data):
                data["lanes"][1] = dict(data["lanes"][0])

            def unknown_lane(data):
                data["lanes"][1]["id"] = "unknown:runtime:minimum:default"

            def contradictory_counts(data):
                data["counts"].update(PASSED=1, NOT_RUN=111)

            reject_matrix("empty", empty_with_fabricated_passes, "matrix.*lane")
            reject_matrix("missing", lambda data: data["lanes"].pop(), "matrix.*lane")
            reject_matrix("duplicate", duplicate_lane, "matrix.*lane")
            reject_matrix("unknown", unknown_lane, "matrix.*lane")
            reject_matrix("contradictory", contradictory_counts, "matrix.*count")
            failed_top = repository / "bundle-failed-top"
            shutil.copytree(workflow_bundle, failed_top)
            top_path = failed_top / "json/hosted-macosArm64.json"
            top_result = json.loads(top_path.read_text())
            top_result.update(status="PROBE_FAILED", reason="source probe failed")
            top_path.write_text(json.dumps(top_result))
            with self.assertRaisesRegex(ValueError, "top.*PROBE_FAILED|hosted probe did not pass"):
                artifact.verify_bundle(failed_top, manifest, sha)
            inconsistent_matrix = repository / "bundle-inconsistent-matrix"
            shutil.copytree(workflow_bundle, inconsistent_matrix)
            matrix_result = json.loads((inconsistent_matrix / "json/matrix-macosArm64.json").read_text())
            matrix_result["bounded_hosted_probes"][0]["reason"] = "other observation"
            (inconsistent_matrix / "json/matrix-macosArm64.json").write_text(json.dumps(matrix_result))
            with self.assertRaisesRegex(ValueError, "matrix.*bounded|bounded.*matrix"):
                artifact.verify_bundle(inconsistent_matrix, manifest, sha)
            fabricated = repository / "bundle-fabricated-binary"
            shutil.copytree(workflow_bundle, fabricated)
            summary_path = fabricated / "verification.json"
            summary = json.loads(summary_path.read_text())
            top_path = fabricated / "json/hosted-macosArm64.json"
            top_result = json.loads(top_path.read_text())
            binary = fabricated / "staged" / qualify.target_binary_path("dyn4k-core", target)
            digest = "f" * 64
            sidecar = binary.with_name(binary.name + ".sha256")
            sidecar.write_text(digest + "\n")
            summary["artifact_hashes"]["dyn4k-core"] = digest
            top_result["artifact_hashes"]["dyn4k-core"] = digest
            for item in summary["staged_files"]:
                if item["path"] == sidecar.relative_to(fabricated).as_posix():
                    item["sha256"] = hashlib.sha256(sidecar.read_bytes()).hexdigest()
            summary_path.write_text(json.dumps(summary))
            top_path.write_text(json.dumps(top_result))
            (fabricated / "json/matrix-macosArm64.json").write_text(json.dumps({
                "candidate_sha": sha, "total": 112,
                "bounded_hosted_probes": [top_result]}))
            with self.assertRaisesRegex(ValueError, "binary.*missing|binary.*checksum|SHA-256 sidecar"):
                artifact.verify_bundle(fabricated, manifest, sha)
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
            selected_core_cases = set(qualify.expected_probe_cases(
                manifest, groups["core-macosArm64"]))
            source_xml = next(path for path in
                              (repository / "dyn4k-core/build/test-results/macosArm64Test").glob("*.xml")
                              if any((case.get("classname"), case.get("name")) in selected_core_cases
                                     for case in ET.parse(path).getroot().iter("testcase")))
            original = source_xml.read_bytes()
            original_mtime_ns = source_xml.stat().st_mtime_ns

            def reject_changed_xml(label, edit, reason):
                source_xml.write_bytes(original)
                try:
                    edit()
                    os.utime(source_xml, ns=(original_mtime_ns, original_mtime_ns))
                    rejected = artifact.stage_hosted(repository, manifest, sha, target, probe_path,
                                                     matrix_path, repository / f"bundle-{label}")
                    self.assertEqual("PROBE_FAILED", rejected["status"])
                    self.assertIn(reason, rejected["reason"])
                finally:
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

            for label, edit, reason in (("renamed", rename_case, "missing selected cases"),
                                        ("skipped", skip_case, "failed or skipped cases"),
                                        ("partial", remove_case, "missing selected cases")):
                with self.subTest(mutation=label):
                    reject_changed_xml(label, edit, reason)
            source_xml.write_bytes(original)
            os.utime(source_xml, ns=(started - 1, started - 1))
            stale_xml = artifact.stage_hosted(repository, manifest, sha, target, probe_path,
                                              matrix_path, repository / "bundle-old-xml")
            self.assertEqual("PROBE_FAILED", stale_xml["status"])
            self.assertIn("stale report", stale_xml["reason"])
            source_xml.write_bytes(original)
            self.assertEqual(1114, artifact.verify_bundle(repository / "bundle-complete",
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
            with self.assertRaisesRegex(ValueError, "report counts|partial|missing"):
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
            def record_ubuntu_probes():
                nonlocal finished
                finished = time.time_ns()
                for name, ids in artifact.UBUNTU_PROBES.items():
                    count = sum(len(qualify.expected_probe_cases(manifest, groups[group_id]))
                                for group_id in ids)
                    (repository / name).write_text(json.dumps(probe(ids, count)))

            record_ubuntu_probes()
            (repository / "artifact-audit.json").write_text(json.dumps(
                {"candidate_sha": sha, "status": "FAILED"}))
            (repository / "runtime-matrix.json").write_text(json.dumps(
                {"candidate_sha": sha, "total": 112,
                 "lanes": lanes,
                 "counts": {"PASSED": 0, "FAILED": 0, "UNAVAILABLE": 0, "NOT_RUN": 112}}))
            (repository / "provider.log").write_text("duplicate org.dyn4j provider\n")
            ubuntu_runtime = {"system": "Linux", "machine": "x86_64",
                              "kernel_release": "6.0.0", "distribution": "ubuntu",
                              "os_version": "24.04", "runner_image_os": "",
                              "runner_image_version": "", "github_actions": False,
                              "java_version": "21.0.8"}
            with (patch.object(artifact.platform, "freedesktop_os_release",
                               side_effect=OSError("Linux os-release is absent")),
                  patch.object(artifact, "ubuntu_runtime", return_value=ubuntu_runtime)):
                missing_ubuntu = artifact.stage_ubuntu(repository, manifest, sha, repository,
                                                        repository / "ubuntu-missing")
                self.assertEqual("PROBE_FAILED", missing_ubuntu["status"])
                self.assertIn("core-jvm", missing_ubuntu["reason"])
                write_group("core-jvm")
                record_ubuntu_probes()
                complete_ubuntu = artifact.stage_ubuntu(repository, manifest, sha, repository,
                                                         repository / "ubuntu-complete")
            self.assertEqual("PROBE_PASSED", complete_ubuntu["status"], complete_ubuntu["reason"])
            self.assertEqual("Linux", complete_ubuntu["runtime"]["system"])
            self.assertEqual(6686, complete_ubuntu["executed"])
            self.assertEqual(6686, artifact.verify_bundle(repository / "ubuntu-complete",
                                                           manifest, sha)["executed"])
            summary_path = repository / "ubuntu-complete/verification.json"
            summary = json.loads(summary_path.read_text())
            summary["runtime"]["system"] = "Windows"
            summary_path.write_text(json.dumps(summary))
            with self.assertRaisesRegex(ValueError, "Ubuntu bundle runtime"):
                artifact.verify_bundle(repository / "ubuntu-complete", manifest, sha)

    def test_slow_ubuntu_fixture_generation_retains_bound_report_times(self):
        original_stage_hosted = artifact.stage_hosted
        calls = 0

        def delayed_first_stage(*args, **kwargs):
            nonlocal calls
            result = original_stage_hosted(*args, **kwargs)
            calls += 1
            if calls == 1:
                time.sleep(6)
            return result

        with patch.object(artifact, "stage_hosted", side_effect=delayed_first_stage):
            self.test_missing_core_xml_rejects_bounded_pass_then_complete_bundle_passes()


if __name__ == "__main__":
    unittest.main()
