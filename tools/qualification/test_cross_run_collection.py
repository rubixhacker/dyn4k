import copy
import io
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
import types
import unittest
import warnings
import zipfile
import tarfile
from pathlib import Path
from unittest import mock

import collection
import independent_gates


ROOT = Path(__file__).resolve().parents[2]
HEAD = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                               text=True).strip()
TREE = collection.source_tree(ROOT, HEAD)
LANE = "tvosSimulatorArm64:tvOS simulator ARM64:current:debug-g"


class CrossRunCollectionTests(unittest.TestCase):
    def public_verify(self, root):
        return subprocess.run(
            ["python3", "-B", str(ROOT / "tools/qualification/collection.py"),
             "--repository", str(ROOT), "--candidate-sha", HEAD,
             "--artifacts-dir", str(root / "artifacts"),
             "--output", str(root / "collection"), "--verify"],
            capture_output=True, text=True)

    def test_workflow_exposes_cross_run_route_without_recapturing_producers(self):
        workflow = (ROOT / ".github/workflows/qualification.yml").read_text()
        self.assertIn("cross_run_only:\n", workflow)
        self.assertIn("cross_run_source_index:\n", workflow)
        for job in ("staged-jvm-and-linux", "hosted-publications", "hosted-native"):
            body = workflow.split(f"  {job}:\n", 1)[1].split("\n  ", 1)[0]
            self.assertIn("inputs.cross_run_only != true", body)
        central = workflow.split("  central-qualification-collection:\n", 1)[1]
        self.assertLess(central.index("Download every retained producer artifact"),
                        central.index("Retain explicit cross-run source index"))
        self.assertLess(central.index("Retain explicit cross-run source index"),
                        central.index("Provision pinned upstream source for raw replay"))
        for contract in ("actions: read", "contents: read", "--source-index",
                         "--run-id", "--run-attempt", "DYN4K_GITHUB_TOKEN",
                         "${{ github.token }}", "${{ runner.temp }}/cross-run-source-index.json"):
            self.assertIn(contract, central)

    def fixture(self, root, members=None):
        archive = root / "mobile.zip"
        if members is None:
            members = {
                "build/stage-receipt.json": json.dumps(
                    {"candidate_sha": HEAD, "targets": ["tvosSimulatorArm64"]}).encode(),
                "captures/compatibility/result.json": json.dumps(
                    {"source_sha": HEAD, "target": "tvosSimulatorArm64",
                     "format": "portable-mobile-capture-v1",
                     "qualification": "unpassed"}).encode(),
            }
        with zipfile.ZipFile(archive, "w") as packed:
            for name, value in members.items():
                packed.writestr(name, value)
        index = {"schema": 1, "candidate_sha": HEAD, "source_tree": TREE,
                 "sources": [{"id": "mobile", "origin": {"kind": "local",
                                                      "path": str(archive)},
                              "transport": {"format": "zip", "size": archive.stat().st_size,
                                            "sha256": collection.digest(archive)}}],
                 "bindings": [{"source_id": "mobile", "lane": None,
                               "gate": "performance-resource",
                               "target": "tvosSimulatorArm64"}]}
        index_path = root / "index.json"
        index_path.write_text(json.dumps(index))
        return archive, index_path, index

    def collect_fixture(self, root, index_path):
        artifacts = root / "artifacts"
        artifacts.mkdir()
        return collection.collect(ROOT, HEAD, [], root / "collection",
                                  source_index=index_path, artifacts_dir=artifacts)

    def test_mobile_zip_is_frozen_and_source_bound_without_gate_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, index_path, _ = self.fixture(root)
            result = self.collect_fixture(root, index_path)
            self.assertEqual("NOT_RUN", result["status"])
            row = result["cross_run"]["sources"][0]
            self.assertEqual("NOT_RUN", row["status"])
            self.assertIn("portable-mobile-capture-v1 source and target bound",
                          row["reason"])
            self.assertEqual(archive.read_bytes(),
                             (root / "collection/raw/sources/mobile/original").read_bytes())
            inputs = json.loads((root / "collection/assembly-inputs.json").read_text())
            self.assertEqual(112, len(inputs))
            self.assertTrue(all(value == {"archives": {}} for value in inputs.values()))
            self.assertTrue(collection.verify_collection(ROOT, HEAD, [],
                                                         root / "collection"))
            extra = root / "collection/raw/sources/mobile/unrecorded"
            extra.write_bytes(b"x")
            with self.assertRaisesRegex(ValueError, "unrecorded files"):
                collection.verify_collection(ROOT, HEAD, [], root / "collection")
            extra.unlink()
            normalized = root / "collection/normalized/mobile/build/stage-receipt.json"
            normalized.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "normalized source archive bytes differ"):
                collection.verify_collection(ROOT, HEAD, [], root / "collection")
            normalized.write_text(json.dumps(
                {"candidate_sha": HEAD, "targets": ["tvosSimulatorArm64"]}))
            (root / "collection/raw/sources/mobile/original").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "frozen source archive bytes differ"):
                collection.verify_collection(ROOT, HEAD, [], root / "collection")

    def test_public_verify_requires_exact_failed_packed_snapshot_children(self):
        for alteration in ("delete", "alternate"):
            with self.subTest(alteration=alteration), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                _, index_path, _ = self.fixture(root, {"../escape": b"x"})
                result = self.collect_fixture(root, index_path)
                self.assertEqual("FAILED", result["cross_run"]["sources"][0]["status"])
                self.assertEqual(0, self.public_verify(root).returncode)
                folder = root / "collection/raw/sources/mobile"
                if alteration == "delete":
                    (folder / "original").unlink()
                else:
                    alternate = folder / "original-directory"
                    alternate.mkdir()
                    (alternate / "other.txt").write_text("unrecorded")
                self.assertNotEqual(0, self.public_verify(root).returncode)

    def test_public_verify_requires_exact_failed_directory_snapshot_children(self):
        for alteration in ("delete", "alternate"):
            with self.subTest(alteration=alteration), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = root / "directory"
                source.mkdir()
                (source / "receipt.json").write_text("raw failure\n")
                files = collection._file_inventory(source)
                index = {"schema": 1, "candidate_sha": HEAD, "source_tree": TREE,
                         "sources": [{"id": "failed", "origin": {"kind": "local",
                                   "path": str(source)}, "transport": {
                                   "format": "directory", "files": files,
                                   "inventory_sha256": collection._inventory_digest(files)}}],
                         "bindings": [{"source_id": "failed", "lane": LANE,
                                       "gate": "staged-consumer"}]}
                index["sources"][0]["transport"]["files"]["receipt.json"]["sha256"] = "0" * 64
                index["sources"][0]["transport"]["inventory_sha256"] = (
                    collection._inventory_digest(index["sources"][0]["transport"]["files"]))
                index_path = root / "index.json"
                index_path.write_text(json.dumps(index))
                result = self.collect_fixture(root, index_path)
                self.assertEqual("FAILED", result["cross_run"]["sources"][0]["status"])
                self.assertEqual(0, self.public_verify(root).returncode)
                folder = root / "collection/raw/sources/failed"
                if alteration == "delete":
                    shutil.rmtree(folder / "original-directory")
                else:
                    (folder / "original").write_bytes(b"unrecorded")
                self.assertNotEqual(0, self.public_verify(root).returncode)

    def test_same_run_rerun_attempt_requires_artifact_provenance(self):
        manifest = independent_gates.load_approved_manifest(ROOT)
        index = {"schema": 1, "candidate_sha": HEAD, "source_tree": TREE,
                 "sources": [{"id": "rerun", "origin": {
                     "kind": "same_run", "repository": "rubixhacker/dyn4k",
                     "workflow": ".github/workflows/qualification.yml", "run_id": 42,
                     "run_attempt": 2, "name": f"full-ci-{HEAD}", "head_sha": HEAD},
                     "transport": {"format": "zip", "size": 10, "sha256": "a" * 64}}],
                 "bindings": [{"source_id": "rerun", "lane": LANE,
                               "gate": "staged-consumer"}]}
        with self.assertRaisesRegex(ValueError, "attempt ownership"):
            collection._validate_index(index, HEAD, TREE, manifest,
                                       "rubixhacker/dyn4k", 42, 2)

    def test_lane_binding_rejects_conflicting_declared_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, index_path, index = self.fixture(root)
            index["bindings"] = [{"source_id": "mobile", "lane": LANE,
                                  "gate": "staged-consumer", "target": "jvm"}]
            index_path.write_text(json.dumps(index))
            result = self.collect_fixture(root, index_path)
            self.assertEqual("FAILED", result["status"])
            self.assertIn("lane binding target differs", result["cross_run"]["reason"])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, index_path, index = self.fixture(root)
            index["bindings"] = [{"source_id": "mobile", "lane": LANE,
                                  "gate": "staged-consumer",
                                  "target": "tvosSimulatorArm64"}]
            index_path.write_text(json.dumps(index))
            result = self.collect_fixture(root, index_path)
            self.assertEqual("NOT_RUN", result["status"])
            self.assertEqual(0, self.public_verify(root).returncode)

    def test_actual_local_and_external_file_size_checked_before_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, index_path, index = self.fixture(root)
            archive = Path(index["sources"][0]["origin"]["path"])
            archive.write_bytes(b"x" * 2048)
            index["sources"][0]["transport"]["size"] = 512
            index_path.write_text(json.dumps(index))
            with mock.patch.object(collection, "MAX_SOURCE_BYTES", 1024), \
                 mock.patch.object(collection, "_copy_regular", wraps=collection._copy_regular) as copied:
                result = self.collect_fixture(root, index_path)
                self.assertEqual(0, copied.call_count)

            self.assertEqual("FAILED", result["status"])
            self.assertIn("source archive exceeds byte bound",
                          result["cross_run"]["sources"][0]["reason"])
            self.assertEqual(0, self.public_verify(root).returncode)
            stable = root / "external"
            stable.mkdir()
            manifest = independent_gates.load_approved_manifest(ROOT)
            lanes = {lane: {} for lane in manifest["lanes"]}
            lanes[LANE] = {"staged-consumer": str(archive)}
            archive_map = {"schema": 1, "candidate_sha": HEAD, "lanes": lanes}
            with mock.patch.object(collection, "MAX_SOURCE_BYTES", 1024), \
                 mock.patch.object(collection, "_copy_regular", wraps=collection._copy_regular) as copied:
                with self.assertRaisesRegex(ValueError, "external archive exceeds byte bound"):
                    collection._snapshot_external_references(archive_map, manifest, stable)
                self.assertEqual(0, copied.call_count)

    def test_copy_stream_cap_preserves_only_bounded_partial_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "growing.bin"
            frozen = root / "frozen.bin"
            source.write_bytes(b"x" * (2 * 1024 * 1024))
            actual = source.stat()
            reported = types.SimpleNamespace(st_mode=stat.S_IFREG, st_size=1024 * 1024,
                                             st_dev=actual.st_dev, st_ino=actual.st_ino)
            with mock.patch.object(collection.os, "fstat", return_value=reported):
                with self.assertRaisesRegex(ValueError, "exceeds byte bound while copied"):
                    collection._copy_regular(source, frozen, limit=1024 * 1024 + 512)
            self.assertEqual(1024 * 1024 + 512, frozen.stat().st_size)
            smaller = root / "smaller.bin"
            with mock.patch.object(collection.os, "fstat", return_value=reported):
                with self.assertRaisesRegex(ValueError, "exceeds byte bound while copied"):
                    collection._copy_regular(source, smaller, limit=512 * 1024,
                                             preflight=False)
            self.assertEqual(512 * 1024, smaller.stat().st_size)
            with self.assertRaisesRegex(ValueError, "source file exceeds byte bound"):
                collection.digest(source, 1024 * 1024)

    def test_windows_open_route_keeps_bound_archive_and_rejects_replacement(self):
        for behavior in ("regular", "reparse", "replacement"):
            with self.subTest(behavior=behavior), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive, index_path, _ = self.fixture(root)
                windows_os = types.SimpleNamespace(**vars(os))
                windows_os.name = "nt"
                replaced = False

                def lstat_source(path):
                    info = os.lstat(path)
                    if behavior == "replacement" and replaced and Path(path) == archive:
                        return types.SimpleNamespace(
                            st_mode=info.st_mode, st_dev=info.st_dev,
                            st_ino=info.st_ino + 1)
                    return info

                windows_os.lstat = lstat_source

                def open_source(path):
                    nonlocal replaced
                    if behavior == "reparse":
                        raise ValueError("symbolic source path is forbidden")
                    descriptor = os.open(path, os.O_RDONLY)
                    if behavior == "replacement" and Path(path) == archive:
                        replaced = True
                    return descriptor

                with mock.patch.object(collection, "os", windows_os), \
                     mock.patch.object(collection, "_open_windows_no_reparse",
                                       side_effect=open_source) as opened:
                    result = self.collect_fixture(root, index_path)
                self.assertGreater(opened.call_count, 0)
                row = result["cross_run"]["sources"][0]
                if behavior == "regular":
                    self.assertEqual("NOT_RUN", row["status"])
                    self.assertTrue(collection.verify_collection(
                        ROOT, HEAD, [], root / "collection"))
                else:
                    self.assertEqual("FAILED", row["status"])
                    self.assertIn("symbolic" if behavior == "reparse" else "changed",
                                  row["reason"])
                    self.assertEqual(0, self.public_verify(root).returncode)

    def test_directory_growth_after_inventory_keeps_bounded_raw_bytes(self):
        limit = 1024 * 1024
        manifest = independent_gates.load_approved_manifest(ROOT)
        for route in ("local", "external"):
            with self.subTest(route=route), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = root / "source"
                source.mkdir()
                member = source / "receipt.bin"
                member.write_bytes(b"x" * (limit // 2))
                files = collection._file_inventory(source)
                original_inventory = collection._file_inventory
                grown = False

                def grow_after_inventory(path):
                    nonlocal grown
                    inventory = original_inventory(path)
                    if Path(path) == source and not grown:
                        member.write_bytes(b"y" * (limit * 2 + limit // 2))
                        grown = True
                    return inventory

                with mock.patch.object(collection, "MAX_EXPANDED_BYTES", limit), \
                     mock.patch.object(collection, "_file_inventory",
                                       side_effect=grow_after_inventory):
                    if route == "local":
                        index = {"schema": 1, "candidate_sha": HEAD,
                                 "source_tree": TREE,
                                 "sources": [{"id": "grown", "origin": {
                                     "kind": "local", "path": str(source)},
                                     "transport": {"format": "directory",
                                                   "files": files,
                                                   "inventory_sha256":
                                                   collection._inventory_digest(files)}}],
                                 "bindings": [{"source_id": "grown", "lane": LANE,
                                               "gate": "staged-consumer"}]}
                        index_path = root / "index.json"
                        index_path.write_text(json.dumps(index))
                        result = self.collect_fixture(root, index_path)
                        row = result["cross_run"]["sources"][0]
                        self.assertEqual("FAILED", row["status"])
                        self.assertIn("transport bounds", row["reason"])
                        frozen = root / "collection/raw/sources/grown/original-directory/receipt.bin"
                    else:
                        stable = root / "stable"
                        stable.mkdir()
                        lanes = {lane: {} for lane in manifest["lanes"]}
                        lanes[LANE] = {"staged-consumer": str(source)}
                        archive_map = {"schema": 1, "candidate_sha": HEAD,
                                       "lanes": lanes}
                        with self.assertRaisesRegex(ValueError, "transport bounds"):
                            collection._snapshot_external_references(
                                archive_map, manifest, stable)
                        frozen = stable / "references/0/receipt.bin"
                self.assertTrue(grown)
                self.assertTrue(frozen.is_file())
                self.assertGreater(frozen.stat().st_size, 0)
                self.assertLessEqual(frozen.stat().st_size, limit)
                if route == "local":
                    self.assertEqual(frozen.stat().st_size,
                                     row["raw_inventory"]["receipt.bin"]["size"])
                    self.assertEqual(0, self.public_verify(root).returncode)

    def test_directory_member_growth_keeps_bounded_raw_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "one.bin").write_bytes(b"one")
            (source / "two.bin").write_bytes(b"two")
            files = collection._file_inventory(source)
            index = {"schema": 1, "candidate_sha": HEAD, "source_tree": TREE,
                     "sources": [{"id": "grown", "origin": {"kind": "local",
                                  "path": str(source)}, "transport": {
                                  "format": "directory", "files": files,
                                  "inventory_sha256": collection._inventory_digest(files)}}],
                     "bindings": [{"source_id": "grown", "lane": LANE,
                                   "gate": "staged-consumer"}]}
            index_path = root / "index.json"
            index_path.write_text(json.dumps(index))
            original_inventory = collection._file_inventory
            grown = False

            def grow_after_inventory(path):
                nonlocal grown
                inventory = original_inventory(path)
                if Path(path) == source and not grown:
                    (source / "three.bin").write_bytes(b"three")
                    grown = True
                return inventory

            with mock.patch.object(collection, "MAX_MEMBERS", 2), \
                 mock.patch.object(collection, "_file_inventory",
                                   side_effect=grow_after_inventory):
                result = self.collect_fixture(root, index_path)
            row = result["cross_run"]["sources"][0]
            self.assertEqual("FAILED", row["status"])
            self.assertIn("transport bounds", row["reason"])
            frozen = root / "collection/raw/sources/grown/original-directory"
            self.assertLessEqual(len(list(frozen.iterdir())), 2)
            self.assertEqual(len(list(frozen.iterdir())), len(row["raw_inventory"]))
            self.assertEqual(0, self.public_verify(root).returncode)

    def test_wrong_candidate_target_and_duplicate_bindings_fail(self):
        for mutation, reason in ((lambda value: value.update(candidate_sha="0" * 40),
                                  "candidate or tree differs"),
                                 (lambda value: value.update(source_tree="0" * 40),
                                  "candidate or tree differs"),
                                 (lambda value: value["bindings"][0].update(
                                     target="jvm"), "bound lane or target differs"),
                                 (lambda value: value["bindings"].append(
                                     copy.deepcopy(value["bindings"][0])),
                                  "duplicate lane or global gate binding"),
                                 (lambda value: value["sources"].append(
                                     copy.deepcopy(value["sources"][0])),
                                  "duplicate or unsafe source ID")):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                _, index_path, index = self.fixture(root)
                mutation(index)
                index_path.write_text(json.dumps(index))
                result = self.collect_fixture(root, index_path)
                self.assertEqual("FAILED", result["status"])
                self.assertIn(reason, (result["cross_run"].get("reason") or
                                       result["cross_run"]["sources"][0]["reason"]))

    def test_directory_and_unsupported_format_remain_not_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "raw-directory"
            source.mkdir()
            (source / "receipt.json").write_text(json.dumps(
                {"candidate_sha": HEAD, "status": "PASSED"}))
            files = collection._file_inventory(source)
            index = {"schema": 1, "candidate_sha": HEAD, "source_tree": TREE,
                     "sources": [{"id": "rawdir", "origin": {"kind": "local",
                                                         "path": str(source)},
                                  "transport": {"format": "directory", "files": files,
                                                "inventory_sha256":
                                                collection._inventory_digest(files)}}],
                     "bindings": [{"source_id": "rawdir", "lane": LANE,
                                   "gate": "staged-consumer"}]}
            index_path = root / "index.json"
            index_path.write_text(json.dumps(index))
            result = self.collect_fixture(root, index_path)
            self.assertEqual("NOT_RUN", result["status"])
            self.assertIn("unsupported producer format",
                          result["cross_run"]["sources"][0]["reason"])
            self.assertTrue(collection.verify_collection(ROOT, HEAD, [],
                                                         root / "collection"))
            (root / "collection/raw/sources/rawdir/original-directory/receipt.json").write_text(
                "altered")
            with self.assertRaisesRegex(ValueError, "frozen source directory bytes differ"):
                collection.verify_collection(ROOT, HEAD, [], root / "collection")

    def test_same_run_directory_requires_current_run_and_freezes_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifacts = root / "artifacts"
            source = artifacts / f"qualification-{HEAD}"
            source.mkdir(parents=True)
            (source / "failed.log").write_text("raw failure\n")
            files = collection._file_inventory(source)
            index = {"schema": 1, "candidate_sha": HEAD, "source_tree": TREE,
                     "sources": [{"id": "current", "origin": {
                         "kind": "same_run", "repository": "rubixhacker/dyn4k",
                         "workflow": ".github/workflows/qualification.yml",
                         "run_id": 42, "run_attempt": 1,
                         "name": source.name, "head_sha": HEAD},
                         "transport": {"format": "directory", "files": files,
                                       "inventory_sha256":
                                       collection._inventory_digest(files)}}],
                     "bindings": [{"source_id": "current", "lane": LANE,
                                   "gate": "staged-consumer"}]}
            index_path = root / "index.json"
            index_path.write_text(json.dumps(index))
            output = root / "transport"
            output.mkdir()
            result = collection.snapshot_source_index(index_path, HEAD, TREE,
                independent_gates.load_approved_manifest(ROOT), artifacts, output,
                run_id=42, run_attempt=1)
            self.assertEqual("NOT_RUN", result["status"])
            self.assertEqual((source / "failed.log").read_bytes(),
                             (output / "raw/sources/current/original-directory/failed.log")
                             .read_bytes())
            self.assertTrue(collection.verify_source_snapshot(output, HEAD, TREE))

    def test_missing_wrong_pin_and_duplicate_json_key_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, _, index = self.fixture(root)
            with self.assertRaisesRegex(ValueError, "cannot read arbitrary local source"):
                collection._validate_index(index, HEAD, TREE,
                    independent_gates.load_approved_manifest(ROOT),
                    "rubixhacker/dyn4k", None, None, allow_local=False)
        for mutation, reason in ((lambda value, root: value["sources"][0]["origin"].update(
                                      path=str(root / "missing/archive.zip")),
                                  "source archive is missing"),
                                 (lambda value, root: value["sources"][0]["transport"].update(
                                      sha256="0" * 64),
                                  "source archive bytes differ from exact pin")):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                _, index_path, index = self.fixture(root)
                mutation(index, root)
                index_path.write_text(json.dumps(index))
                result = self.collect_fixture(root, index_path)
                self.assertEqual("FAILED", result["cross_run"]["status"])
                self.assertIn(reason, result["cross_run"]["sources"][0]["reason"])
                self.assertEqual(0, self.public_verify(root).returncode)
                if reason == "source archive is missing":
                    self.assertEqual([], list((root / "collection/raw/sources/mobile").iterdir()))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, index_path, _ = self.fixture(root)
            index_path.write_text('{"schema":1,"schema":1}')
            result = self.collect_fixture(root, index_path)
            self.assertEqual("FAILED", result["status"])
            self.assertIn("duplicate JSON key", result["cross_run"]["reason"])
            self.assertEqual(index_path.read_bytes(),
                             (root / "collection/source-index.rejected").read_bytes())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, index_path, index = self.fixture(root)
            alias = root / "alias.zip"
            alias.symlink_to(archive)
            index["sources"][0]["origin"]["path"] = str(alias)
            index_path.write_text(json.dumps(index))
            result = self.collect_fixture(root, index_path)
            self.assertEqual("FAILED", result["status"])
            self.assertIn("symbolic source path", result["cross_run"]["reason"])

    def test_unsafe_zip_members_and_source_mutation_fail_with_raw_retained(self):
        for members, reason in (({"../escape": b"x"}, "unsafe archive path"),
                                ({"build/ok": b"a", "build/../ok": b"b"},
                                 "unsafe archive path")):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive, index_path, _ = self.fixture(root, members)
                result = self.collect_fixture(root, index_path)
                self.assertEqual("FAILED", result["cross_run"]["status"])
                self.assertIn(reason, result["cross_run"]["sources"][0]["reason"])
                self.assertEqual(archive.read_bytes(),
                                 (root / "collection/raw/sources/mobile/original").read_bytes())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, index_path, _ = self.fixture(root)
            original_copy = collection._copy_regular

            def changing_copy(source, destination):
                original_copy(source, destination)
                Path(source).write_bytes(Path(source).read_bytes() + b"changed")

            with mock.patch.object(collection, "_copy_regular", side_effect=changing_copy):
                result = self.collect_fixture(root, index_path)
            self.assertEqual("FAILED", result["cross_run"]["status"])
            self.assertIn("changed while copied", result["cross_run"]["sources"][0]
                          ["reason"])
            self.assertTrue((root / "collection/raw/sources/mobile/original").is_file())

    def test_duplicate_zip_member_and_symbolic_member_fail(self):
        for member, reason in (("duplicate", "duplicate archive member"),
                               ("symbolic", "nonregular ZIP member")):
            with self.subTest(member=member), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive, index_path, index = self.fixture(root)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    with zipfile.ZipFile(archive, "w") as packed:
                        if member == "duplicate":
                            packed.writestr("same.txt", b"a")
                            packed.writestr("same.txt", b"b")
                        else:
                            info = zipfile.ZipInfo("link")
                            info.create_system = 3
                            info.external_attr = (stat.S_IFLNK | 0o777) << 16
                            packed.writestr(info, b"target")
                index["sources"][0]["transport"] = {
                    "format": "zip", "size": archive.stat().st_size,
                    "sha256": collection.digest(archive)}
                index_path.write_text(json.dumps(index))
                result = self.collect_fixture(root, index_path)
                self.assertEqual("FAILED", result["cross_run"]["status"])
                self.assertIn(reason, result["cross_run"]["sources"][0]["reason"])

    def test_tar_traversal_and_duplicate_members_fail(self):
        for names, reason in ((("../escape",), "unsafe archive path"),
                              (("same", "same"), "duplicate archive member")):
            with self.subTest(names=names), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive, index_path, index = self.fixture(root)
                packed = root / "raw.tar"
                with tarfile.open(packed, "w") as tar:
                    for name in names:
                        member = tarfile.TarInfo(name)
                        member.size = 1
                        tar.addfile(member, io.BytesIO(b"x"))
                index["sources"][0]["origin"]["path"] = str(packed)
                index["sources"][0]["transport"] = {
                    "format": "tar", "size": packed.stat().st_size,
                    "sha256": collection.digest(packed)}
                index_path.write_text(json.dumps(index))
                result = self.collect_fixture(root, index_path)
                self.assertEqual("FAILED", result["cross_run"]["status"])
                self.assertIn(reason, result["cross_run"]["sources"][0]["reason"])

    def test_github_source_requires_exact_metadata_and_attempt(self):
        origin = {"kind": "github_actions", "repository": "rubixhacker/dyn4k",
                  "workflow": ".github/workflows/qualification.yml", "run_id": 42,
                  "run_attempt": 1, "artifact_id": 77, "api_size_in_bytes": 10,
                  "name": "pinned", "head_sha": HEAD}
        run = {"id": 42, "head_sha": HEAD, "run_attempt": 1,
               "path": ".github/workflows/qualification.yml@main",
               "repository": {"full_name": "rubixhacker/dyn4k", "id": 12}}
        artifact = {"id": 77, "name": "pinned", "expired": False,
                    "size_in_bytes": 10,
                    "workflow_run": {"id": 42, "head_sha": HEAD, "repository_id": 12}}
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "raw.zip"
            with mock.patch.object(collection, "_github_request",
                                   side_effect=[run, artifact, 10]) as request:
                observed = collection._github_artifact(origin, HEAD, "secret", destination,
                                                       10)
            self.assertEqual(77, observed["artifact_id"])
            self.assertEqual(3, request.call_count)
            for changed in ({**run, "head_sha": "0" * 40},
                            {**run, "run_attempt": 2},
                            {**run, "path": ".github/workflows/other.yml@main"}):
                with mock.patch.object(collection, "_github_request",
                                       side_effect=[changed, artifact]):
                    with self.assertRaisesRegex(ValueError, "source identity differs"):
                        collection._github_artifact(origin, HEAD, "secret", destination, 10)
            for changed in ({**artifact, "id": 78}, {**artifact, "name": "other"},
                            {**artifact, "expired": True},
                            {**artifact, "size_in_bytes": 11}):
                with mock.patch.object(collection, "_github_request",
                                       side_effect=[run, changed]):
                    with self.assertRaises(ValueError):
                        collection._github_artifact(origin, HEAD, "secret", destination, 10)
            rerun = {**origin, "run_attempt": 2}
            with mock.patch.object(collection, "_github_request",
                                   side_effect=[{**run, "run_attempt": 2}, artifact]):
                with self.assertRaisesRegex(ValueError, "rerun attempt ownership"):
                    collection._github_artifact(rerun, HEAD, "secret", destination, 10)

    def test_duplicate_artifact_id_and_wrong_same_run_identity_fail_before_copy(self):
        manifest = independent_gates.load_approved_manifest(ROOT)
        origin = {"kind": "github_actions", "repository": "rubixhacker/dyn4k",
                  "workflow": ".github/workflows/qualification.yml", "run_id": 42,
                  "run_attempt": 1, "artifact_id": 77, "api_size_in_bytes": 10,
                  "name": "pinned", "head_sha": HEAD}
        transport = {"format": "zip", "size": 10, "sha256": "a" * 64}
        index = {"schema": 1, "candidate_sha": HEAD, "source_tree": TREE,
                 "sources": [{"id": "one", "origin": origin, "transport": transport},
                             {"id": "two", "origin": dict(origin),
                              "transport": transport}],
                 "bindings": [{"source_id": "one", "lane": LANE,
                               "gate": "staged-consumer"},
                              {"source_id": "two", "lane": LANE,
                               "gate": "staged-artifacts"}]}
        with self.assertRaisesRegex(ValueError, "duplicate or invalid GitHub artifact ID"):
            collection._validate_index(index, HEAD, TREE, manifest,
                                       "rubixhacker/dyn4k", 42, 1)
        index["sources"] = [{"id": "one", "origin": {
            "kind": "same_run", "repository": "rubixhacker/dyn4k",
            "workflow": ".github/workflows/qualification.yml", "run_id": 41,
            "run_attempt": 1, "name": f"full-ci-{HEAD}", "head_sha": HEAD},
            "transport": transport}]
        index["bindings"] = index["bindings"][:1]
        with self.assertRaisesRegex(ValueError, "same-run source identity differs"):
            collection._validate_index(index, HEAD, TREE, manifest,
                                       "rubixhacker/dyn4k", 42, 1)

    def test_external_archive_map_uses_frozen_referenced_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "receipt.json").write_text("raw receipt\n")
            stable = root / "stable"
            stable.mkdir()
            manifest = independent_gates.load_approved_manifest(ROOT)
            lanes = {lane: {} for lane in manifest["lanes"]}
            lanes[LANE] = {"staged-consumer": str(source)}
            archive_map = {"schema": 1, "candidate_sha": HEAD, "lanes": lanes}
            frozen_map, snapshots = collection._snapshot_external_references(
                archive_map, manifest, stable)
            frozen = Path(json.loads(frozen_map.read_text())["lanes"][LANE]
                          ["staged-consumer"])
            self.assertNotEqual(source, frozen)
            self.assertEqual((source / "receipt.json").read_bytes(),
                             (frozen / "receipt.json").read_bytes())
            collection._verify_external_references(snapshots)
            (frozen / "receipt.json").write_text("changed\n")
            with self.assertRaisesRegex(ValueError, "frozen external archive"):
                collection._verify_external_references(snapshots)

    def test_external_handoff_passes_only_frozen_paths_and_explicit_key(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            (repository / "build/staging-repository").mkdir(parents=True)
            output = root / "collection"
            output.mkdir()
            raw = root / "raw-gate"
            raw.mkdir()
            (raw / "receipt.json").write_text("raw\n")
            key = root / "independent-performance.pem"
            key.write_text("external verification key\n")
            pin = hashlib.sha256(key.read_bytes()).hexdigest()
            inputs = root / "audit-inputs"
            inputs.mkdir()
            manifest = independent_gates.load_approved_manifest(ROOT)
            lanes = {lane: {} for lane in manifest["lanes"]}
            lanes[LANE] = {"staged-consumer": str(raw)}
            (inputs / "archive-map.json").write_text(json.dumps(
                {"schema": 1, "candidate_sha": HEAD, "lanes": lanes}))
            for name in ("candidate-manifest.json", "staged-audit.json"):
                (inputs / name).write_text(json.dumps({"candidate_sha": HEAD}))
            for name in ("audit.json", "audit.sig", "public.pem", "evidence.json"):
                (inputs / name).write_text("external input\n")
            process = subprocess.CompletedProcess([], 1, b"", b"failed verification")
            with mock.patch.object(collection, "verify_collection", return_value=True), \
                 mock.patch.object(independent_gates, "load_approved_manifest",
                                   return_value=manifest), \
                 mock.patch.object(collection.subprocess, "run", return_value=process) as run:
                result = collection.ingest_external(repository, HEAD, [], output,
                    inputs, trusted_key_sha256="a" * 64,
                    independent_performance_key=key, performance_key_sha256=pin)
            self.assertEqual("FAILED", result["status"])
            command = run.call_args.args[0]
            archive_map = Path(command[command.index("--independent-archives") + 1])
            performance_key = Path(command[command.index("--independent-performance-key")
                                           + 1])
            self.assertNotEqual(inputs / "archive-map.json", archive_map)
            self.assertNotEqual(key, performance_key)
            self.assertEqual(pin, collection.digest(performance_key))
            frozen = Path(json.loads(archive_map.read_text())["lanes"][LANE]
                          ["staged-consumer"])
            self.assertNotEqual(raw, frozen)
            self.assertEqual((raw / "receipt.json").read_bytes(),
                             (frozen / "receipt.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
