import hashlib
import importlib.util
import json
import re
import subprocess
import tarfile
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import collection
import independent_gates


ROOT = Path(__file__).resolve().parents[2]
workflow_contract_spec = importlib.util.spec_from_file_location(
    "qualification_workflow_contract", ROOT / "tools/compatibility/test_qualification_workflow.py")
workflow_contract = importlib.util.module_from_spec(workflow_contract_spec)
workflow_contract_spec.loader.exec_module(workflow_contract)
HEAD = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                               text=True).strip()

EXPECTED_CENTRAL_NEEDS = ["staged-jvm-and-linux", "hosted-publications",
                          "hosted-native"]


def _mapping_block(lines, key, indentation, start=0, limit=None, required=True):
    limit = len(lines) if limit is None else limit
    header = " " * indentation + key
    matches = [index for index in range(start, limit) if lines[index] == header]
    if not matches:
        if required:
            raise AssertionError(f"missing workflow key: {key}")
        return None
    if len(matches) != 1:
        raise AssertionError(f"duplicate workflow key: {key}")
    header_index = matches[0]
    for index in range(header_index + 1, limit):
        line = lines[index]
        if (line.strip() and not line.lstrip().startswith("#")
                and line.startswith(" " * indentation)
                and len(line) > indentation
                and line[indentation] not in " \t"):
            return header_index, index
    return header_index, limit


def _block_list_values(lines, start, end, indentation):
    prefix = " " * indentation + "- "
    values = []
    for line in lines[start:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(prefix):
            raise AssertionError("unsupported workflow list syntax")
        value = line[len(prefix):]
        if not value or value != value.strip():
            raise AssertionError("unsupported workflow list value")
        if value.startswith("'"):
            if len(value) < 2 or not value.endswith("'"):
                raise AssertionError("unsupported quoted workflow list value")
            quoted = value[1:-1]
            decoded = []
            index = 0
            while index < len(quoted):
                if quoted[index] == "'":
                    if index + 1 >= len(quoted) or quoted[index + 1] != "'":
                        raise AssertionError("unsupported quoted workflow list value")
                    decoded.append("'")
                    index += 2
                else:
                    decoded.append(quoted[index])
                    index += 1
            value = "".join(decoded)
        elif value.startswith('"'):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as error:
                raise AssertionError("unsupported quoted workflow list value") from error
            if not isinstance(value, str):
                raise AssertionError("workflow list values must be strings")
        elif (any(character.isspace() for character in value)
              or "#" in value or value[0] in "!&*{}[]|>@`"):
            raise AssertionError("unsupported plain workflow list value")
        values.append(value)
    return values


def central_collection_needs(workflow):
    lines = workflow.splitlines()
    jobs_start, jobs_end = _mapping_block(lines, "jobs:", 0)
    central = _mapping_block(lines, "central-qualification-collection:", 2,
                             jobs_start + 1, jobs_end)
    needs = _mapping_block(lines, "needs:", 4, central[0] + 1, central[1],
                           required=False)
    if needs is None:
        return None
    return _block_list_values(lines, needs[0] + 1, needs[1], 6)


def assert_manual_qualification_trigger(workflow):
    if list(workflow_contract.workflow_event_blocks(workflow)) != ["workflow_dispatch"]:
        raise AssertionError("full qualification must require manual dispatch")


def central_collection_steps(workflow):
    job = workflow_contract.workflow_jobs(workflow)["central-qualification-collection"]
    steps = job.split("    steps:\n", 1)[1]
    matches = list(re.finditer(r"(?m)^      - (?:name|uses): .+$", steps))
    if not matches:
        raise AssertionError("central collection has no runnable steps")
    return [steps[match.start():matches[index + 1].start()
                  if index + 1 < len(matches) else len(steps)]
            for index, match in enumerate(matches)]


class CollectionTests(unittest.TestCase):
    def test_empty_collection_keeps_all_lanes_not_run_without_signature(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "collection"
            result = collection.collect(ROOT, HEAD, [], output)
            self.assertEqual("NOT_RUN", result["status"])
            self.assertEqual("MISSING", result["independent_signature"])
            self.assertEqual(112, result["required_lanes"])
            self.assertEqual(set(collection.REQUIRED), set(result["missing_artifacts"]))
            self.assertEqual([
                "all 112 exact-source common gate archives and runtime identities",
                "independently audited archive digests and 21-target artifact hashes",
                "complete candidate manifest bound to a verified staged audit",
                "exact staged repository bytes available to the public qualifier",
                "detached Ed25519 audit signature and pinned trusted public-key fingerprint",
            ], result["external_inputs_required"])
            inputs = json.loads((output / "assembly-inputs.json").read_text())
            self.assertEqual(112, len(inputs))
            self.assertTrue(all(value == {"archives": {}} for value in inputs.values()))
            self.assertTrue(collection.verify_collection(ROOT, HEAD, [], output))
            candidate = json.loads((output / "candidate-manifest-inputs.json").read_text())
            self.assertEqual("INCOMPLETE", candidate["status"])
            self.assertTrue(all(value["runtime_identity"] is None
                                for value in candidate["lanes"].values()))
            jvm_lanes = {lane_id: value for lane_id, value in candidate["lanes"].items()
                         if value["target"] == "jvm"}
            self.assertEqual(4, len(jvm_lanes))
            self.assertEqual({"default", "no-optimize"},
                             {value["jvm_mode_publication"]["mode"]
                              for value in jvm_lanes.values()})
            for lane_id, value in jvm_lanes.items():
                self.assertIsNone(value["artifact_hashes"])
                self.assertEqual(lane_id, value["jvm_mode_publication"]["lane"])
                self.assertEqual(HEAD, value["jvm_mode_publication"]["candidate_sha"])
                self.assertIsNone(value["jvm_mode_publication"]["publication_archive"])
                self.assertIsNone(value["jvm_mode_publication"]["archive_digest"])

    def test_staged_audit_does_not_assign_one_jvm_pair_to_both_modes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / f"publication-{HEAD}-ubuntu"
            receipt = artifact / "fixture-publication"
            receipt.mkdir(parents=True)
            audit = {"candidate_sha": HEAD, "status": "PASSED", "artifacts": [
                {"path": collection.qualify.target_binary_path(module, target),
                 "sha256": value}
                for target, value in (("jvm", "a" * 64), ("linuxX64", "b" * 64))
                for module in collection.qualify.MODULES]}
            (receipt / "artifact-audit.json").write_text(json.dumps(audit))
            output = root / "collected"
            with mock.patch.object(collection, "inspect_artifact",
                                   return_value="PRODUCER_VERIFIED"):
                collection.collect(ROOT, HEAD, [(artifact.name, artifact)], output)
            candidate = json.loads((output / "candidate-manifest-inputs.json").read_text())
            self.assertTrue(all(value["artifact_hashes"] is None
                                for value in candidate["lanes"].values()
                                if value["target"] == "jvm"))
            self.assertTrue(all(value["artifact_hashes"] == {
                                module: "b" * 64 for module in collection.qualify.MODULES}
                                for value in candidate["lanes"].values()
                                if value["target"] == "linuxX64"))

    def test_wrong_sha_and_duplicate_route_are_failed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wrong = "0" * 40 if HEAD != "0" * 40 else "1" * 40
            bad = root / f"full-ci-{wrong}"
            bad.mkdir()
            (bad / "raw.log").write_text("failed exact-source producer\n")
            result = collection.collect(ROOT, HEAD, [(bad.name, bad)], root / "wrong")
            self.assertEqual("FAILED", result["status"])
            self.assertIn("candidate", result["artifacts"][0]["reason"])
            self.assertEqual(collection.digest(bad / "raw.log"),
                             result["artifacts"][0]["files"]["raw.log"])
            self.assertIn("full-ci", result["missing_artifacts"])
            first, second = root / "first", root / "second"
            first.mkdir()
            second.mkdir()
            name = f"duplicate-provider-{HEAD}"
            duplicated = collection.collect(ROOT, HEAD, [(name, first), (name, second)],
                                            root / "duplicate")
            self.assertEqual("FAILED", duplicated["status"])
            self.assertIn("duplicate producer artifact route",
                          duplicated["artifacts"][1]["reason"])

    def test_forged_pass_cannot_enter_unsigned_map(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / f"duplicate-provider-{HEAD}"
            artifact.mkdir()
            (artifact / "receipt.json").write_text(json.dumps(
                {"schema": 1, "candidate_sha": HEAD,
                 "source_tree": collection.source_tree(ROOT, HEAD), "status": "PASSED"}))
            result = collection.collect(ROOT, HEAD, [(artifact.name, artifact)],
                                        root / "collection")
            self.assertEqual("FAILED", result["status"])
            self.assertIn("inventory", result["artifacts"][0]["reason"])
            inputs = json.loads((root / "collection/assembly-inputs.json").read_text())
            self.assertEqual({"duplicate-provider": str(artifact.resolve())},
                             inputs["jvm:Java:current:default"]["archives"])
            self.assertTrue(all(value == {"archives": {}} for lane, value in inputs.items()
                                if lane != "jvm:Java:current:default"))
            assembly = independent_gates.evaluate_assembly(
                independent_gates.load_approved_manifest(ROOT), HEAD, inputs, ROOT)
            self.assertEqual("FAILED", assembly["status"])
            self.assertEqual("FAILED", assembly["lane_results"]["jvm:Java:current:default"]
                             ["gates"]["duplicate-provider"]["status"])
            self.assertFalse(assembly["qualify_adapter"])

    def test_missing_external_signature_keeps_audit_ingestion_not_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "collection"
            collection.collect(ROOT, HEAD, [], output)
            external = root / "external"
            external.mkdir()
            (external / "audit.json").write_text(json.dumps(
                {"schema": 1, "candidate_sha": HEAD, "status": "PASSED"}))
            result = collection.ingest_external(ROOT, HEAD, [], output, external,
                                                trusted_key_sha256="a" * 64)
            self.assertEqual("NOT_RUN", result["status"])
            self.assertIn("audit.sig", result["missing_external_inputs"])
            self.assertFalse((output / "signed-runtime-matrix.json").exists())

    def test_retained_failed_route_and_changed_raw_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / f"duplicate-provider-{HEAD}"
            artifact.mkdir()
            raw = artifact / "task.log"
            raw.write_text("BUILD FAILED\n")
            started, finished = time.time_ns() - 1_000_000_000, time.time_ns() + 1_000_000_000
            receipt = {"schema": 1, "status": "FAILED", "candidate_sha": HEAD,
                       "source_tree": collection.source_tree(ROOT, HEAD),
                       "process": {"command": ["./gradlew", "verifySingleProvider"],
                                   "exit_code": 1, "started_ns": started,
                                   "finished_ns": finished, "stdout": "task.log"},
                       "files": [{"path": "task.log",
                                  "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
                                  "mtime_ns": raw.stat().st_mtime_ns}]}
            (artifact / "receipt.json").write_text(json.dumps(receipt))
            output = root / "collection"
            result = collection.collect(ROOT, HEAD, [(artifact.name, artifact)], output)
            self.assertEqual("FAILED", result["status"])
            self.assertNotIn("reason", result["artifacts"][0])
            self.assertTrue(raw.is_file())
            self.assertTrue(collection.verify_collection(ROOT, HEAD,
                                                         [(artifact.name, artifact)], output))
            raw.write_text("changed raw output\n")
            with self.assertRaisesRegex(ValueError, "raw artifact bytes differ"):
                collection.verify_collection(ROOT, HEAD, [(artifact.name, artifact)], output)
            changed = collection.collect(ROOT, HEAD, [(artifact.name, artifact)],
                                         root / "changed")
            self.assertIn("raw file hash differs", changed["artifacts"][0]["reason"])

    def test_altered_transport_archive_is_failed_and_retained(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / f"full-ci-{HEAD}"
            artifact.mkdir()
            packed = artifact / f"full-ci-{HEAD}.tar.gz"
            with tarfile.open(packed, "w:gz") as archive:
                pass
            sidecar = artifact / f"full-ci-{HEAD}.sha256"
            sidecar.write_text(f"{collection.digest(packed)}  {packed.name}\n")
            before = root / "before"
            collection.collect(ROOT, HEAD, [(artifact.name, artifact)], before)
            packed.write_bytes(packed.read_bytes() + b"altered")
            with self.assertRaisesRegex(ValueError, "raw artifact bytes differ"):
                collection.verify_collection(ROOT, HEAD, [(artifact.name, artifact)], before)
            result = collection.collect(ROOT, HEAD, [(artifact.name, artifact)],
                                        root / "after")
            self.assertEqual("FAILED", result["status"])
            self.assertIn("archive bytes differ", result["artifacts"][0]["reason"])
            self.assertTrue(packed.is_file())

    def test_workflow_runs_after_producers_and_retains_raw_results(self):
        workflow = (ROOT / ".github/workflows/qualification.yml").read_text()
        assert_manual_qualification_trigger(workflow)
        self.assertEqual(EXPECTED_CENTRAL_NEEDS, central_collection_needs(workflow))
        steps = central_collection_steps(workflow)

        def named_step(name):
            matches = [(index, step) for index, step in enumerate(steps)
                       if step.startswith(f"      - name: {name}\n")]
            self.assertEqual(1, len(matches), name)
            return matches[0]

        download_index, download = named_step("Download every retained producer artifact")
        collect_index, collect = named_step("Collect and independently enumerate 112 lanes")
        upload_index, upload = named_step("Upload central raw collection and failed routes")
        self.assertEqual(0, download_index)
        self.assertLess(download_index, collect_index)
        self.assertEqual(collect_index + 1, upload_index)
        self.assertIn("        id: raw_download\n", download)
        self.assertIn("        if: always()\n", download)
        self.assertIn("        continue-on-error: true\n", download)
        self.assertIn("        uses: actions/download-artifact@v4\n", download)
        self.assertIn("          pattern: '*'\n", download)
        self.assertIn("          path: ${{ runner.temp }}/producer-artifacts\n", download)
        self.assertIn("          merge-multiple: false\n", download)
        self.assertIn("        if: always()\n", collect)
        self.assertIn("        run: |\n", collect)
        self.assertIn(
            '          python3 tools/qualification/collection.py --verify \\\n'
            '            --repository "$GITHUB_WORKSPACE" \\\n'
            '            --candidate-sha "$GITHUB_SHA" \\\n'
            '            --artifacts-dir "$RUNNER_TEMP/producer-artifacts" \\\n'
            '            --output "$RUNNER_TEMP/central-collection" \\\n'
            '            > "$RUNNER_TEMP/central-logs/transport.stdout" \\\n'
            '            2> "$RUNNER_TEMP/central-logs/transport.stderr"\n',
            collect)
        self.assertIn("          transport_exit=$?\n", collect)
        self.assertIn('test "$transport_exit" -eq 0', collect)
        self.assertIn("        if: always()\n", upload)
        self.assertIn("        uses: actions/upload-artifact@v4\n", upload)
        self.assertIn("          name: qualification-central-${{ github.sha }}\n", upload)
        for path in ("central-collection/", "central-logs/", "producer-artifacts/"):
            self.assertIn("            ${{ runner.temp }}/" + path + "\n", upload)
        self.assertIn("          if-no-files-found: error\n", upload)
        for command in ("independent_gates.py", "qualify.py record",
                        "duplicate_provider.py", "qualification-central-${{ github.sha }}"):
            self.assertIn(command, workflow)

    def test_central_collection_rejects_inactive_or_misplaced_steps(self):
        workflow = (ROOT / ".github/workflows/qualification.yml").read_text()
        central = workflow_contract.workflow_jobs(workflow)["central-qualification-collection"]
        other = workflow_contract.workflow_jobs(workflow)["hosted-mac"]
        steps = central_collection_steps(workflow)
        required = (
            ("download", "Download every retained producer artifact",
             "        uses: actions/download-artifact@v4\n"),
            ("verify", "Collect and independently enumerate 112 lanes",
             "          python3 tools/qualification/collection.py --verify \\\n"),
            ("upload", "Upload central raw collection and failed routes",
             "        uses: actions/upload-artifact@v4\n"),
        )
        for name, step_name, line in required:
            self.assertIn(line, central)
            block = next(step for step in steps
                         if step.startswith(f"      - name: {step_name}\n"))
            if name == "verify":
                start = block.index(line)
                end = block.index("          transport_exit=$?\n", start)
                command = block[start:end]
                replacements = (
                    ("commented", block.replace(command,
                        "          # python3 tools/qualification/collection.py --verify\n", 1)),
                    ("no-op", block.replace(command,
                        "          echo skipped # python3 tools/qualification/collection.py --verify\n", 1)),
                )
            else:
                retained_name = ("        # qualification-central-${{ github.sha }}\n"
                                 if name == "upload" else "")
                prefix = (f"      - name: {step_name}\n"
                          + ("        id: raw_download\n" if name == "download" else "")
                          + "        if: always()\n")
                replacements = (
                    ("commented", prefix + "        # " + line.strip() + "\n"
                     + "        run: echo skipped\n" + retained_name),
                    ("no-op", prefix + "        run: echo skipped # "
                     + line.strip() + "\n" + retained_name),
                )
            for variant, replacement in replacements:
                with self.subTest(step=name, variant=variant):
                    altered = workflow.replace(central, central.replace(block, replacement, 1), 1)
                    with mock.patch.object(Path, "read_text", return_value=altered):
                        with self.assertRaises(AssertionError):
                            self.test_workflow_runs_after_producers_and_retains_raw_results()
            with self.subTest(step=name, variant="misplaced"):
                altered = workflow.replace(central, central.replace(block, "", 1), 1)
                altered = altered.replace(other, other.replace(
                    "    steps:\n", "    steps:\n" + block, 1), 1)
                with mock.patch.object(Path, "read_text", return_value=altered):
                    with self.assertRaises(AssertionError):
                        self.test_workflow_runs_after_producers_and_retains_raw_results()

        download, collect, upload = (next(step for step in steps
                                          if step.startswith(f"      - name: {name}\n"))
                                     for name in ("Download every retained producer artifact",
                                                  "Collect and independently enumerate 112 lanes",
                                                  "Upload central raw collection and failed routes"))
        for name, moved, anchor in (("download-after-collect", download, collect),
                                    ("upload-before-collect", upload, collect)):
            with self.subTest(order=name):
                reordered = central.replace(moved, "", 1).replace(
                    anchor, (anchor + moved if moved == download else moved + anchor), 1)
                altered = workflow.replace(central, reordered, 1)
                with mock.patch.object(Path, "read_text", return_value=altered):
                    with self.assertRaises(AssertionError):
                        self.test_workflow_runs_after_producers_and_retains_raw_results()

    def test_full_qualification_rejects_automatic_triggers(self):
        workflow = (ROOT / ".github/workflows/qualification.yml").read_text()
        for event in ("push", "pull_request", "schedule", "workflow_run"):
            with self.subTest(event=event):
                altered = workflow.replace("on:\n", f"on:\n  {event}:\n", 1)
                with self.assertRaisesRegex(AssertionError, "manual dispatch"):
                    assert_manual_qualification_trigger(altered)

    def test_cheap_source_checks_run_on_push_and_pull_request(self):
        workflow = (ROOT / ".github/workflows/qualification-source-checks.yml").read_text()
        self.assertEqual(["push", "pull_request"],
                         list(workflow_contract.workflow_event_blocks(workflow)))
        workflow_contract.QualificationWorkflowContractTest().assert_source_checks_job_contract(
            workflow)

    def test_source_checks_reject_comment_only_or_misplaced_invocations(self):
        workflow = (ROOT / ".github/workflows/qualification-source-checks.yml").read_text()
        comment_only = (workflow.split("    steps:\n", 1)[0]
                        + "    steps:\n      - run: echo no checks\n"
                        + "        # guard_hosted_runners.py test_qualification_workflow "
                        + "test_guard_hosted_runners python3 -B -m unittest\n")
        for altered in (comment_only,
                        workflow.replace("  workflow-source-contracts:\n", "  unrelated-job:\n"),
                        workflow.replace(
                            "        run: python3 -B tools/qualification/guard_hosted_runners.py",
                            "        run: echo no checks\n"
                            "        # python3 -B tools/qualification/guard_hosted_runners.py")):
            with self.subTest(workflow=altered), mock.patch.object(
                    Path, "read_text", return_value=altered):
                with self.assertRaises(AssertionError):
                    self.test_cheap_source_checks_run_on_push_and_pull_request()

    def test_central_workflow_dependencies_reject_invalid_and_later_job_lists(self):
        workflow = (ROOT / ".github/workflows/qualification.yml").read_text()
        expected = EXPECTED_CENTRAL_NEEDS
        approved_block = (
            "    needs:\n"
            "      - staged-jvm-and-linux\n"
            "      - hosted-publications\n"
            "      - hosted-native\n"
        )
        self.assertEqual(1, workflow.count(approved_block))

        for dependencies in (
                ["staged-jvm-and-linux"],
                expected + ["safari-browser"],
                ["staged-jvm-and-linux", "hosted-publications", "hosted-native",
                 "wrong-producer"],
                list(reversed(expected)),
        ):
            replacement = "    needs:\n" + "".join(
                f"      - {dependency}\n" for dependency in dependencies)
            with self.subTest(dependencies=dependencies):
                altered = workflow.replace(approved_block, replacement, 1)
                self.assertNotEqual(expected, central_collection_needs(altered))

        without_central_needs = workflow.replace(approved_block, "", 1)
        self.assertIsNone(central_collection_needs(without_central_needs))
        job_keys = ('"spare-diagnostic":', "spare-diagnostic :",
                    "spare-diagnostic: # diagnostic")
        for job_key in job_keys:
            with self.subTest(job_key=job_key):
                later_job_only = without_central_needs + (
                    f"\n  {job_key}\n"
                    "    needs:\n"
                    "      - staged-jvm-and-linux\n"
                    "      - hosted-publications\n"
                    "      - hosted-native\n"
                    "    runs-on: ubuntu-latest\n"
                    "    steps:\n"
                    "      - run: true\n"
                )
                self.assertIsNone(central_collection_needs(later_job_only))
                earlier_job_only = without_central_needs.replace(
                    "  central-qualification-collection:\n",
                    "\n  " + job_key + "\n"
                    "    needs:\n"
                    "      - staged-jvm-and-linux\n"
                    "      - hosted-publications\n"
                    "      - hosted-native\n"
                    "    runs-on: ubuntu-latest\n"
                    "    steps:\n"
                    "      - run: true\n"
                    "  central-qualification-collection:\n",
                    1,
                )
                self.assertIsNone(central_collection_needs(earlier_job_only))

    def test_workflow_download_survives_replay_setup_failure(self):
        workflow = (ROOT / ".github/workflows/qualification.yml").read_text()
        central = workflow.split("  central-qualification-collection:\n", 1)[1]

        def assert_download_contract(job):
            download = job.index("      - name: Download every retained producer artifact\n")
            next_step = job.index("      - ", download + 1)
            download_step = job[download:next_step]
            self.assertIn("        if: always()\n", download_step)
            self.assertIn("        id: raw_download\n", download_step)
            self.assertIn("        continue-on-error: true\n", download_step)
            for fallible in ("      - uses: actions/checkout@v4\n",
                             "      - uses: actions/setup-java@v4\n",
                             "      - uses: gradle/actions/setup-gradle@v4\n",
                             "      - name: Provision pinned upstream source for raw replay\n"):
                self.assertLess(download, job.index(fallible))
            self.assertIn("DYN4K_DOWNLOAD_OUTCOME: ${{ steps.raw_download.outcome }}", job)
            self.assertIn("test \"$DYN4K_DOWNLOAD_OUTCOME\" = success", job)
            self.assertIn("download=%s", job)
            self.assertIn("::error::Producer artifact download failed or was skipped", job)

        assert_download_contract(central)
        download = central.index("      - name: Download every retained producer artifact\n")
        next_step = central.index("      - ", download + 1)
        download_step = central[download:next_step]
        without_condition = central.replace(
            download_step, download_step.replace("        if: always()\n", ""))
        with self.assertRaises(AssertionError):
            assert_download_contract(without_condition)
        after_fetch = central.replace(download_step, "").replace(
            "      - name: Collect and independently enumerate 112 lanes\n",
            download_step + "      - name: Collect and independently enumerate 112 lanes\n")
        with self.assertRaises(AssertionError):
            assert_download_contract(after_fetch)


if __name__ == "__main__":
    unittest.main()
