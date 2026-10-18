import hashlib
import json
import os
import subprocess
import sys
import tarfile
import shutil
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path, PurePosixPath, PureWindowsPath
from unittest.mock import patch

import artifact
import qualify
import test_publication


def fixture_original_path(path, windows_host=None):
    if windows_host is None:
        windows_host = os.name == "nt"
    if windows_host:
        source = PureWindowsPath(path)
        return "/fixture/" + "/".join((source.drive.rstrip(":"), *source.parts[1:]))
    return str(Path(path).resolve())


class RawArtifactTests(unittest.TestCase):
    def _full_hosted_fixture(self, bundle, repository=None):
        repository = repository or Path(__file__).resolve().parents[2]
        original = fixture_original_path
        final_contract = (repository / "tools/qualification/full_hosted.py").is_file()
        sha = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"],
                                      text=True).strip()
        manifest = json.loads((repository / "tools/qualification/full-common-corpus.json").read_text())
        probe = json.loads((repository / "tools/qualification/foundation-probes.json").read_text())
        consumer_group = next(g for g in probe["groups"] if g["id"] == "consumer-macosArm64")
        consumer_cases = qualify.expected_probe_cases(probe, consumer_group)
        now = time.time_ns()
        receipt = {"schema": 2, "kind": "hosted-full-common-corpus", "candidate_sha": sha,
                   "target": "macosArm64", "status": "FULL_COMMON_PASSED",
                   "github_run_id": "1", "github_job": "fixture-job",
                   "runner_name": "fixture-runner", "runner_os": "macOS",
                   "runner_arch": "ARM64",
                   "runtime": {"system": "Darwin", "machine": "arm64",
                               "os_version": "26.6.2", "xcode_version": "26.4.1",
                               "java_version": "21.0.8", "gradle_version": "9.5.0",
                               "kgp_declared_version": "2.4.20",
                               "simulators": {}},
                   "manifest_sha256": qualify.manifest_digest(manifest),
                   "source_tree_sha256": manifest["source_tree_sha256"],
                   "map_sha256": qualify.digest(repository / "tools/qualification/full-common-original-map.tsv"),
                   "reviewed_pairs_sha256": qualify.digest(repository / "tools/qualification/full-common-reviewed-pairs.tsv"),
                   "artifact_hashes": {}, "configurations": [],
                   "staging_repository": original(repository / "build/staging-repository")}
        if final_contract:
            receipt.update(archive_root=original(bundle.resolve()),
                           repository_root=original(repository.resolve()))

        def write(relative, payload):
            path = bundle / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            return path

        for module in qualify.MODULES:
            relative = "staged/" + qualify.target_binary_path(module, "macosArm64")
            binary = write(relative, module.encode())
            receipt["artifact_hashes"][module] = qualify.digest(binary)
            write(relative + ".sha256", (qualify.digest(binary) + "\n").encode())

        names = set(qualify.MODULES)
        names.update(qualify.target_publication_name(module, "macosArm64")
                     for module in qualify.MODULES)
        receipt["staged_gav"] = [f"{qualify.GROUP}:{name}:{qualify.VERSION}"
                                 for name in sorted(names)]
        for name in names:
            base = (f"staged/{qualify.GROUP.replace('.', '/')}/{name}/"
                    f"{qualify.VERSION}/{name}-{qualify.VERSION}")
            core = name.replace("dyn4k", "dyn4k-core", 1)
            dependency = (f"<dependencies><dependency><groupId>{qualify.GROUP}</groupId>"
                          f"<artifactId>{core}</artifactId><version>{qualify.VERSION}</version>"
                          "</dependency></dependencies>") if name == "dyn4k" or name.startswith(
                              "dyn4k-") and not name.startswith("dyn4k-core") else ""
            pom = (f'<project xmlns="http://maven.apache.org/POM/4.0.0">'
                   f"<groupId>{qualify.GROUP}</groupId><artifactId>{name}</artifactId>"
                   f"<version>{qualify.VERSION}</version>{dependency}</project>")
            write(base + ".pom", pom.encode())
            root_name = name if name in qualify.MODULES else (
                "dyn4k-core" if name.startswith("dyn4k-core-") else "dyn4k")
            target_name = qualify.target_publication_name(name, "macosArm64")
            variants = ([{"available-at": {
                "group": qualify.GROUP, "module": target_name,
                "version": qualify.VERSION,
                "url": f"../../{target_name}/{qualify.VERSION}/{target_name}-{qualify.VERSION}.module"}}]
                if name in qualify.MODULES else [])
            component = {"group": qualify.GROUP, "module": root_name,
                         "version": qualify.VERSION}
            if name not in qualify.MODULES:
                component["url"] = (f"../../{root_name}/{qualify.VERSION}/"
                                    f"{root_name}-{qualify.VERSION}.module")
            write(base + ".module", json.dumps({"component": component,
                "variants": variants}).encode())
        if final_contract:
            for path in (bundle / "staged").rglob("*"):
                if path.is_file():
                    os.utime(path, ns=(now - 1_500_000_000, now - 1_500_000_000))
        inputs = ["tools/qualification/full-common-corpus.json",
                  "tools/qualification/full-common-original-map.tsv",
                  "tools/qualification/full-common-reviewed-pairs.tsv",
                  "tools/qualification/full_corpus.py",
                  "tools/qualification/foundation-probes.json"]
        if final_contract:
            inputs += ["tools/qualification/full_hosted.py",
                       "tools/qualification/hosted.py", "tools/qualification/qualify.py",
                       "tools/qualification/artifact.py", "build.gradle.kts",
                       "consumers/qualification/portable/build.gradle.kts"]
        for relative in inputs:
            write("inputs/" + relative, (repository / relative).read_bytes())
        for source in manifest["source_files"]:
            write("sources/" + source["path"], (repository / source["path"]).read_bytes())

        def process(folder, name, tasks, invocation, start, extra=""):
            stdout = ("\n".join(f"> Task {task}" for task in tasks) +
                      "\n" + extra + "BUILD SUCCESSFUL\n").encode()
            stderr = b""
            prefix = f"{folder}/{name}" if folder else name
            for stream, payload in (("stdout", stdout), ("stderr", stderr)):
                path = write(f"{prefix}/{stream}.txt", payload)
                os.utime(path, ns=(start + 1_000_000_001, start + 1_000_000_001))
            wrapper = original(repository / "gradlew") if final_contract else "./gradlew"
            command = [wrapper, "--rerun-tasks", *tasks]
            if invocation:
                command.append(f"-PqualificationInvocationId={invocation}")
            if name in ("source", "consumer"):
                script = (original(bundle / folder / "qualification.init.gradle") if final_contract
                          else f"/host/{folder}/qualification.init.gradle")
                command += ["--init-script", script]
            if name == "graph":
                script = (original(bundle / folder / "qualification-graph.init.gradle")
                          if final_contract else f"/host/{folder}/qualification-graph.init.gradle")
                command += ["--init-script", script]
            if name in ("consumer", "graph"):
                command.append(f"-PqualificationRepository={receipt['staging_repository']}")
                if final_contract:
                    command += ["-p", original(repository / "consumers/qualification/portable")]
            if name == "graph":
                command.remove("--rerun-tasks")
            return {"command": command,
                    "pid": 123, "exit_code": 0, "invocation_id": invocation,
                    "started_ns": start, "finished_ns": start + 1_000_000_000,
                    "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
                    "stderr_sha256": hashlib.sha256(stderr).hexdigest()}

        receipt["stage"] = process("", "stage", [
            f":{module}:publishKotlinMultiplatformPublicationToStagingRepository"
            for module in qualify.MODULES] + [
            f":{module}:publishMacosArm64PublicationToStagingRepository"
            for module in qualify.MODULES], None, now - 2_000_000_000)

        def report(folder, area, module, cases, start):
            suite = ET.Element("testsuite", tests=str(len(cases)), failures="0", errors="0",
                               skipped="0", time="1")
            for classname, method in sorted(cases):
                if area != "consumer":
                    classname = "macosArm64Test." + classname
                    method += "[macosArm64]"
                ET.SubElement(suite, "testcase", classname=classname, name=method, time="0")
            relative = f"{folder}/xml/{area}/TEST-{module}.xml"
            path = write(relative, ET.tostring(suite))
            os.utime(path, ns=(start + 1, start + 1))
            return {"expected": len(cases), "executed": len(cases),
                    "case_ids": [f"{name}#{method}" for name, method in sorted(cases)],
                    "reports": [{"path": f"xml/{area}/TEST-{module}.xml",
                                 "sha256": qualify.digest(path),
                                 "modified_ns": path.stat().st_mtime_ns}]}

        for config in ("debug-g", "optimized-opt"):
            invocation = "a" * 32 if config == "debug-g" else "b" * 32
            start = now if config == "debug-g" else now + 4_000_000_000
            tasks = [f":{module}:macosArm64Test" for module in qualify.MODULES]
            mode = "Release" if config == "optimized-opt" else "Debug"
            links = "".join(f"> Task :{module}:link{mode}TestMacosArm64\n"
                            for module in qualify.MODULES)
            lane = {"configuration": config, "status": "FULL_COMMON_PASSED",
                    "invocation_id": invocation,
                    "source_process": process(config, "source", tasks, invocation, start, links),
                    "consumer_process": process(config, "consumer", [":macosArm64Test"],
                                                invocation, start + 2_000_000_000),
                    "source": [], "source_executables": {}}
            for module in qualify.MODULES:
                cases = {(case["classname"], case["method"]) for case in manifest["cases"]
                         if case["module"] == module and case["source_set"] == "commonTest"}
                lane["source"].append({"module": module,
                                      **report(config, module, module, cases, start)})
                executable = write(f"{config}/executables/{module}/{module}.kexe", module.encode())
                os.utime(executable, ns=(start + 1, start + 1))
                build_mode = "releaseTest" if config == "optimized-opt" else "debugTest"
                lane["source_executables"][module] = {
                    "path": original(repository / module / "build/bin/macosArm64" / build_mode /
                                     f"{module}.kexe"),
                    "archive_path": executable.relative_to(bundle).as_posix(),
                    "sha256": qualify.digest(executable), "size": executable.stat().st_size,
                    "modified_ns": executable.stat().st_mtime_ns}
            lane["consumer"] = report(config, "consumer", "portable", consumer_cases,
                                      start + 2_000_000_000)
            script = b"source test configuration RELEASE\n" if config == "optimized-opt" else b"source test configuration\n"
            write(f"{config}/qualification.init.gradle", script)
            write(f"{config}/qualification-graph.init.gradle", b"consumer graph configuration\n")
            graph_artifacts = []
            for module in qualify.MODULES:
                name = qualify.target_publication_name(module, "macosArm64")
                graph_artifacts.append({"component": f"{qualify.GROUP}:{name}:{qualify.VERSION}",
                                        "file": str(PurePosixPath(receipt["staging_repository"]) /
                                                    qualify.target_binary_path(module, "macosArm64")),
                                        "name": name, "size": len(module),
                                        "sha256": receipt["artifact_hashes"][module]})
            lane["consumer_graph"] = {
                "configuration": "macosArm64CompileKlibraries",
                "components": [item["component"] for item in graph_artifacts],
                "artifacts": graph_artifacts}
            if final_contract:
                lane["resolved_artifacts"] = []
                for index, item in enumerate(graph_artifacts):
                    relative = f"{config}/resolved-artifacts/{index:03d}-{item['name']}"
                    write(relative, item["name"].split("-macosarm64")[0].encode())
                    lane["resolved_artifacts"].append({**item, "archive_path": relative})
            lane["graph_process"] = process(
                config, "graph", ["qualificationResolvedGraph"], invocation,
                start + 4_000_000_000,
                "DYN4K_RESOLVED_GRAPH=" + json.dumps(lane["consumer_graph"]) + "\n")
            executable = write(f"{config}/executables/consumer/consumer.kexe", b"consumer")
            os.utime(executable, ns=(start + 2_000_000_001, start + 2_000_000_001))
            lane["consumer_executable"] = {
                "path": original(repository / "consumers/qualification/portable/build/bin/macosArm64" /
                                 ("releaseTest" if config == "optimized-opt" else "debugTest") /
                                 "consumer.kexe"),
                "archive_path": executable.relative_to(bundle).as_posix(),
                "sha256": qualify.digest(executable), "size": executable.stat().st_size,
                "modified_ns": executable.stat().st_mtime_ns}
            receipt["configurations"].append(lane)
        self._seal_full_fixture(bundle, receipt)
        return sha

    def _seal_full_fixture(self, bundle, receipt):
        receipt["files"] = [{"path": path.relative_to(bundle).as_posix(),
                             "sha256": qualify.digest(path),
                             "size": path.stat().st_size,
                             "modified_ns": path.stat().st_mtime_ns}
                                    for path in sorted(bundle.rglob("*"))
                                    if path.is_file() and path.name != "receipt.json"]
        (bundle / "receipt.json").write_text(json.dumps(receipt))

    def test_full_hosted_archive_replay_and_adverse_controls(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "full"
            bundle.mkdir()
            sha = self._full_hosted_fixture(bundle)
            repository = Path(__file__).resolve().parents[2]
            self.assertEqual("FULL_COMMON_PASSED", artifact.verify_full_hosted(
                bundle, sha, repository)["status"])
            transport = Path(temporary) / "full.tar"
            with tarfile.open(transport, "w", format=tarfile.PAX_FORMAT) as packed:
                for path in sorted(bundle.rglob("*")):
                    if not path.is_file():
                        continue
                    info = packed.gettarinfo(str(path), arcname=path.relative_to(bundle).as_posix())
                    info.pax_headers["dyn4k.mtime_ns"] = str(path.stat().st_mtime_ns)
                    with path.open("rb") as stream:
                        packed.addfile(info, stream)
            transported = artifact.verify_full_hosted(transport, sha, repository)
            self.assertEqual("FULL_COMMON_PASSED", transported["status"])
            self.assertEqual(qualify.digest(transport), transported["_verified_transport_sha256"])
            duplicate_transport = Path(temporary) / "duplicate.tar"
            shutil.copy2(transport, duplicate_transport)
            with tarfile.open(duplicate_transport, "a") as packed:
                path = bundle / "receipt.json"
                info = packed.gettarinfo(str(path), arcname="receipt.json")
                info.pax_headers["dyn4k.mtime_ns"] = str(path.stat().st_mtime_ns)
                with path.open("rb") as stream:
                    packed.addfile(info, stream)
            with self.assertRaisesRegex(ValueError, "duplicate"):
                artifact.verify_full_hosted(duplicate_transport, sha, repository)
            invalid_transport = Path(temporary) / "invalid.tar"
            invalid_transport.write_bytes(b"not a tar archive")
            with self.assertRaisesRegex(ValueError, "transport archive"):
                artifact.verify_full_hosted(invalid_transport, sha, repository)
            receipt = json.loads((bundle / "receipt.json").read_text())
            scoped = qualify.full_hosted_lane(receipt, qualify.digest(bundle / "receipt.json"))
            self.assertEqual(2, len(scoped["configuration_lanes"]))
            self.assertTrue(all(":current:" in lane for lane in scoped["configuration_lanes"]))
            self.assertTrue(all(item["complete_lane_status"] == "NOT_RUN"
                                for item in scoped["observed_cases"]))
            self.assertEqual(2460, len(scoped["observed_cases"][0]
                                       ["common_case_ids"]["dyn4k-core"]))
            self.assertEqual(58, len(scoped["observed_cases"][0]
                                     ["common_case_ids"]["dyn4k"]))
            self.assertEqual(112, len(qualify.expand(qualify.matrix())))
            controls = 0

            def reject(label, edit, reason, reseal=False):
                nonlocal controls
                changed = Path(temporary) / label
                shutil.copytree(bundle, changed)
                data = json.loads((changed / "receipt.json").read_text())
                edit(changed, data)
                if reseal:
                    self._seal_full_fixture(changed, data)
                else:
                    (changed / "receipt.json").write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError, reason):
                    artifact.verify_full_hosted(changed, sha, repository)
                controls += 1

            reject("empty-configs", lambda _, data: data.update(configurations=[]),
                   "configuration", reseal=True)
            reject("wrong-target", lambda _, data: data.update(target="mingwX64"),
                   "runtime|configuration", reseal=True)
            reject("wrong-sha", lambda _, data: data.update(candidate_sha="f" * 40),
                   "candidate", reseal=True)
            reject("wrong-source", lambda _, data: data.update(source_tree_sha256="0" * 64),
                   "source", reseal=True)
            reject("wrong-runner", lambda _, data: data.update(runner_name=""),
                   "runner", reseal=True)
            reject("old-report", lambda _, data: data["configurations"][0]["source"][0]
                   ["reports"][0].update(modified_ns=1), "stale", reseal=True)
            reject("changed-log", lambda path, _: (path / "debug-g/source/stdout.txt")
                   .write_text("BUILD SUCCESSFUL\n"), "archive file hash")
            reject("changed-binary", lambda path, _: (path / "staged" /
                   qualify.target_binary_path("dyn4k-core", "macosArm64"))
                   .write_bytes(b"wrong"), "archive file hash")
            reject("changed-executable", lambda path, _: (path /
                   "debug-g/executables/dyn4k-core/dyn4k-core.kexe").write_bytes(b"wrong"),
                   "archive file hash")
            reject("wrong-product-path", lambda _, data: data["configurations"][1]
                   ["source_executables"]["dyn4k-core"].update(
                       path="/host/dyn4k-core/build/bin/macosArm64/debugTest/dyn4k-core.kexe"),
                   "configuration|executable", reseal=True)
            reject("extra-file", lambda path, _: (path / "extra.txt").write_text("x"),
                   "unlisted")

            def skipped_xml(path, data):
                relative = "debug-g/xml/dyn4k-core/TEST-dyn4k-core.xml"
                xml = path / relative
                original_time = data["configurations"][0]["source"][0]["reports"][0]["modified_ns"]
                root = ET.parse(xml).getroot()
                root.set("skipped", "1")
                ET.SubElement(root.find("testcase"), "skipped")
                xml.write_bytes(ET.tostring(root))
                os.utime(xml, ns=(original_time, original_time))
                data["configurations"][0]["source"][0]["reports"][0]["sha256"] = qualify.digest(xml)

            reject("skipped-xml", skipped_xml, "skipped", reseal=True)

            def alter_xml(path, data, mode):
                xml = path / "debug-g/xml/dyn4k-core/TEST-dyn4k-core.xml"
                original_time = data["configurations"][0]["source"][0]["reports"][0]["modified_ns"]
                root = ET.parse(xml).getroot()
                first = root.find("testcase")
                if mode == "failed":
                    root.set("failures", "1")
                    ET.SubElement(first, "failure")
                elif mode == "ignored":
                    ET.SubElement(first, "ignored")
                elif mode == "missing":
                    root.remove(first)
                    root.set("tests", str(int(root.get("tests")) - 1))
                elif mode == "duplicate":
                    ET.SubElement(root, "testcase", classname=first.get("classname"),
                                  name=first.get("name"), time="0")
                    root.set("tests", str(int(root.get("tests")) + 1))
                elif mode == "forged":
                    first.set("name", "forged[macosArm64]")
                xml.write_bytes(ET.tostring(root))
                os.utime(xml, ns=(original_time, original_time))
                data["configurations"][0]["source"][0]["reports"][0]["sha256"] = qualify.digest(xml)

            for mode, reason in (("failed", "failed"), ("ignored", "ignored"),
                                 ("missing", "missing"), ("duplicate", "duplicate"),
                                 ("forged", "missing")):
                reject(mode + "-xml", lambda path, data, mode=mode:
                       alter_xml(path, data, mode), reason, reseal=True)
            reject("wrong-graph", lambda _, data: data["configurations"][0]
                   ["consumer_graph"].update(configuration="wrong"),
                   "graph differs", reseal=True)
            reject("wrong-os", lambda _, data: data.update(runner_os="Windows"),
                   "runner", reseal=True)
            reject("same-invocation", lambda _, data: data["configurations"][1]
                   .update(invocation_id="a" * 32), "invocation", reseal=True)

            def change_metadata(path, name, field, value):
                base = (path / "staged" / qualify.GROUP.replace(".", "/") / name /
                        qualify.VERSION / f"{name}-{qualify.VERSION}.module")
                metadata = json.loads(base.read_text())
                if field == "root-link":
                    metadata["variants"][0]["available-at"]["url"] = value
                else:
                    metadata["component"][field] = value
                base.write_text(json.dumps(metadata))

            target_name = qualify.target_publication_name("dyn4k-core", "macosArm64")
            reject("wrong-root-link", lambda path, _: change_metadata(
                path, "dyn4k-core", "root-link", "../../wrong/0/wrong.module"),
                "root metadata", reseal=True)
            reject("wrong-target-root-url", lambda path, _: change_metadata(
                path, target_name, "url", "../../wrong/0/wrong.module"),
                "root link", reseal=True)
            reject("wrong-target-root-name", lambda path, _: change_metadata(
                path, target_name, "module", target_name),
                "metadata identity", reseal=True)

            def old_time(path, relative):
                member = path / relative
                os.utime(member, ns=(1, 1))

            reject("changed-xml-time", lambda path, _: old_time(
                path, "debug-g/xml/dyn4k-core/TEST-dyn4k-core.xml"),
                "timestamp")
            reject("resealed-old-xml", lambda path, data: (
                old_time(path, "debug-g/xml/dyn4k-core/TEST-dyn4k-core.xml"),
                data["configurations"][0]["source"][0]["reports"][0].update(
                    modified_ns=1)), "stale", reseal=True)
            reject("resealed-old-executable", lambda path, data: (
                old_time(path, "debug-g/executables/dyn4k-core/dyn4k-core.kexe"),
                data["configurations"][0]["source_executables"]["dyn4k-core"].update(
                    modified_ns=1)), "predates", reseal=True)
            reject("resealed-old-log", lambda path, _: old_time(
                path, "debug-g/source/stdout.txt"), "stale", reseal=True)
            self.assertEqual(27, controls)

            stale_transport = Path(temporary) / "stale-time.tar"
            with tarfile.open(stale_transport, "w", format=tarfile.PAX_FORMAT) as packed:
                for path in sorted(bundle.rglob("*")):
                    if not path.is_file():
                        continue
                    relative = path.relative_to(bundle).as_posix()
                    info = packed.gettarinfo(str(path), arcname=relative)
                    info.pax_headers["dyn4k.mtime_ns"] = str(
                        1 if relative == "debug-g/xml/dyn4k-core/TEST-dyn4k-core.xml"
                        else path.stat().st_mtime_ns)
                    with path.open("rb") as stream:
                        packed.addfile(info, stream)
            with self.assertRaisesRegex(ValueError, "timestamp"):
                artifact.verify_full_hosted(stale_transport, sha, repository)

    def test_full_hosted_verifier_rejects_empty_configuration_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            (bundle / "receipt.json").write_text(json.dumps({
                "schema": 2, "kind": "hosted-full-common-corpus",
                "candidate_sha": "a" * 40, "target": "macosArm64",
                "status": "FULL_COMMON_PASSED", "configurations": [],
            }))
            with self.assertRaisesRegex(ValueError, "configuration"):
                artifact.verify_full_hosted(bundle, "a" * 40, bundle)

    def test_windows_runner_paths_and_macos_fixture_paths_keep_their_own_format(self):
        windows = r"D:\a\dyn4k\dyn4k\build\staging-repository"
        self.assertEqual(PureWindowsPath(windows), artifact._full_original_path("mingwX64", windows))
        self.assertEqual("/fixture/D/a/dyn4k/dyn4k/build/staging-repository",
                         fixture_original_path(windows, windows_host=True))
        self.assertEqual(PurePosixPath("/fixture/D/a/dyn4k/dyn4k/build/staging-repository"),
                         artifact._full_original_path("macosArm64",
                                                      fixture_original_path(windows, windows_host=True)))
        for unsafe in (r"D:relative\stage", r"\stage", r"D:\a\..\stage"):
            with self.subTest(path=unsafe), self.assertRaisesRegex(ValueError, "invalid"):
                artifact._full_original_path("mingwX64", unsafe)

    def test_full_hosted_fixture_replays_through_var_path_alias(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_var = root / "private/var"
            real_var.mkdir(parents=True)
            (root / "var").symlink_to(real_var, target_is_directory=True)
            self.assertEqual(str((real_var / "candidate/build/staging-repository").resolve()),
                             fixture_original_path(root / "var/candidate/build/staging-repository"))
            bundle = root / "var/full"
            bundle.mkdir()
            sha = self._full_hosted_fixture(bundle)
            self.assertEqual("FULL_COMMON_PASSED", artifact.verify_full_hosted(
                bundle, sha, Path(__file__).resolve().parents[2])["status"])

    def test_runner_contract_public_directory_and_tar_clis(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(__file__).resolve().parents[2]
            repository = Path(temporary) / "candidate"
            subprocess.run(["git", "clone", "--quiet", "--shared", str(source),
                            str(repository)], check=True)
            for name in ("qualify.py", "artifact.py"):
                relative = Path("tools/qualification") / name
                shutil.copy2(source / relative, repository / relative)
            runner = Path("tools/qualification/full_hosted.py")
            self.assertTrue((source / runner).is_file())
            shutil.copy2(source / runner, repository / runner)
            manifest = Path("tools/qualification/full-suite-manifest.json")
            self.assertTrue((source / manifest).is_file())
            shutil.copy2(source / manifest, repository / manifest)
            subprocess.run(["git", "-C", str(repository), "add", "--",
                            "tools/qualification/qualify.py", "tools/qualification/artifact.py",
                            runner.as_posix(), manifest.as_posix()], check=True)
            subprocess.run(["git", "-C", str(repository), "-c", "user.name=Fixture",
                            "-c", "user.email=fixture@example.invalid", "commit", "--quiet",
                            "--allow-empty",
                            "-m", "Assemble local verifier fixture"], check=True)
            bundle = Path(temporary) / "bundle"
            bundle.mkdir()
            sha = self._full_hosted_fixture(bundle, repository=repository)
            command = [sys.executable, str(repository / "tools/qualification/artifact.py"),
                       "verify", "--candidate-sha", sha, "--output"]
            directory = subprocess.run(command + [str(bundle)], cwd=repository,
                                       capture_output=True, text=True)
            self.assertEqual(0, directory.returncode, directory.stderr)
            transport = Path(temporary) / "bundle.tar"
            with tarfile.open(transport, "w", format=tarfile.PAX_FORMAT) as packed:
                for path in sorted(bundle.rglob("*")):
                    if path.is_file():
                        info = packed.gettarinfo(str(path),
                                                 arcname=path.relative_to(bundle).as_posix())
                        info.pax_headers["dyn4k.mtime_ns"] = str(path.stat().st_mtime_ns)
                        with path.open("rb") as stream:
                            packed.addfile(info, stream)
            archived = subprocess.run(command + [str(transport)], cwd=repository,
                                      capture_output=True, text=True)
            self.assertEqual(0, archived.returncode, archived.stderr)
            result = Path(temporary) / "qualification.json"
            recorded = subprocess.run([
                sys.executable, str(repository / "tools/qualification/qualify.py"), "record",
                "--candidate-sha", sha, "--full-hosted-bundle", str(transport),
                "--output", str(result)], cwd=repository, capture_output=True, text=True)
            self.assertEqual(1, recorded.returncode)
            self.assertEqual({"PASSED": 0, "FAILED": 0, "UNAVAILABLE": 0,
                              "NOT_RUN": 112}, json.loads(recorded.stdout))
            self.assertEqual(2, len(json.loads(result.read_text())
                                    ["full_hosted_receipts"][0]["configuration_lanes"]))

            for key, wrong in (("java_version", "17.0.1"),
                               ("gradle_version", "8.0"),
                               ("kgp_declared_version", "1.9.0")):
                for value, label in ((wrong, "wrong"), (None, "missing")):
                    changed = Path(temporary) / f"{label}-{key}"
                    shutil.copytree(bundle, changed)
                    altered = json.loads((changed / "receipt.json").read_text())
                    if value is None:
                        altered["runtime"].pop(key)
                    else:
                        altered["runtime"][key] = value
                    self._seal_full_fixture(changed, altered)
                    rejected = subprocess.run(command + [str(changed)], cwd=repository,
                                              capture_output=True, text=True)
                    self.assertEqual(1, rejected.returncode, (key, label, rejected.stdout))
                    self.assertIn("toolchain", rejected.stderr)
                    altered_tar = Path(temporary) / f"{label}-{key}.tar"
                    with tarfile.open(altered_tar, "w", format=tarfile.PAX_FORMAT) as packed:
                        for path in sorted(changed.rglob("*")):
                            if path.is_file():
                                info = packed.gettarinfo(
                                    str(path), arcname=path.relative_to(changed).as_posix())
                                info.pax_headers["dyn4k.mtime_ns"] = str(
                                    path.stat().st_mtime_ns)
                                with path.open("rb") as stream:
                                    packed.addfile(info, stream)
                    rejected = subprocess.run(command + [str(altered_tar)], cwd=repository,
                                              capture_output=True, text=True)
                    self.assertEqual(1, rejected.returncode, (key, label, rejected.stdout))
                    self.assertIn("toolchain", rejected.stderr)

            old_directory = Path(temporary) / "old-directory"
            shutil.copytree(bundle, old_directory)
            stale_xml = old_directory / "debug-g/xml/dyn4k-core/TEST-dyn4k-core.xml"
            os.utime(stale_xml, ns=(1, 1))
            rejected = subprocess.run(command + [str(old_directory)], cwd=repository,
                                      capture_output=True, text=True)
            self.assertEqual(1, rejected.returncode)
            self.assertIn("timestamp", rejected.stderr)

            wrong_metadata = Path(temporary) / "wrong-metadata"
            shutil.copytree(bundle, wrong_metadata)
            module = (wrong_metadata / "staged" / qualify.GROUP.replace(".", "/") /
                      "dyn4k-core" / qualify.VERSION /
                      f"dyn4k-core-{qualify.VERSION}.module")
            changed = json.loads(module.read_text())
            changed["variants"][0]["available-at"]["url"] = "../../wrong/0/wrong.module"
            module.write_text(json.dumps(changed))
            sealed = json.loads((wrong_metadata / "receipt.json").read_text())
            self._seal_full_fixture(wrong_metadata, sealed)
            rejected = subprocess.run(command + [str(wrong_metadata)], cwd=repository,
                                      capture_output=True, text=True)
            self.assertEqual(1, rejected.returncode)
            self.assertIn("root metadata", rejected.stderr)

            old_transport = Path(temporary) / "old-transport.tar"
            with tarfile.open(old_transport, "w", format=tarfile.PAX_FORMAT) as packed:
                for path in sorted(bundle.rglob("*")):
                    if path.is_file():
                        relative = path.relative_to(bundle).as_posix()
                        info = packed.gettarinfo(str(path), arcname=relative)
                        modified = path.stat().st_mtime_ns
                        if relative == "debug-g/xml/dyn4k-core/TEST-dyn4k-core.xml":
                            modified = 1
                            info.mtime = 0
                        info.pax_headers["dyn4k.mtime_ns"] = str(modified)
                        with path.open("rb") as stream:
                            packed.addfile(info, stream)
            rejected = subprocess.run(command + [str(old_transport)], cwd=repository,
                                      capture_output=True, text=True)
            self.assertEqual(1, rejected.returncode)
            self.assertIn("timestamp", rejected.stderr)

            wrong_pax = Path(temporary) / "wrong-pax.tar"
            with tarfile.open(wrong_pax, "w", format=tarfile.PAX_FORMAT) as packed:
                for path in sorted(bundle.rglob("*")):
                    if path.is_file():
                        relative = path.relative_to(bundle).as_posix()
                        info = packed.gettarinfo(str(path), arcname=relative)
                        if relative == "debug-g/xml/dyn4k-core/TEST-dyn4k-core.xml":
                            info.mtime = 0
                        info.pax_headers["dyn4k.mtime_ns"] = str(path.stat().st_mtime_ns)
                        with path.open("rb") as stream:
                            packed.addfile(info, stream)
            rejected = subprocess.run(command + [str(wrong_pax)], cwd=repository,
                                      capture_output=True, text=True)
            self.assertEqual(1, rejected.returncode)
            self.assertIn("PAX timestamp", rejected.stderr)

            weakened = json.loads((repository / manifest).read_text())
            weakened["lanes"][next(iter(weakened["lanes"]))]["required_gates"] = [
                "staged-consumer"]
            (repository / manifest).write_text(json.dumps(weakened))
            subprocess.run(["git", "-C", str(repository), "add", "--",
                            manifest.as_posix()], check=True)
            subprocess.run(["git", "-C", str(repository), "-c", "user.name=Fixture",
                            "-c", "user.email=fixture@example.invalid", "commit", "--quiet",
                            "-m", "Weaken local manifest fixture"], check=True)
            weakened_sha = subprocess.check_output(
                ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
            weakened_bundle = Path(temporary) / "weakened-bundle"
            weakened_bundle.mkdir()
            self.assertEqual(weakened_sha, self._full_hosted_fixture(
                weakened_bundle, repository=repository))
            rejected = subprocess.run([
                sys.executable, str(repository / "tools/qualification/qualify.py"), "record",
                "--candidate-sha", weakened_sha, "--full-hosted-bundle", str(weakened_bundle),
                "--output", str(result)], cwd=repository, capture_output=True, text=True)
            self.assertEqual(2, rejected.returncode)
            self.assertIn("complete suite differs", rejected.stderr)

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
            started = time.time_ns() - 5_000_000_000
            finished = time.time_ns() + 5_000_000_000

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
                                  "os_version": "26.6.2", "xcode_version": "26.4.1",
                                  "simulators": {}},
                      "source_probe": source, "consumer_probe": consumer,
                      "artifact_hashes": hashes}
            probe_path = repository / "hosted-macosArm64.json"
            probe_path.write_text(json.dumps(hosted))
            probe_path.with_name("hosted-macosArm64-source.json").write_text(json.dumps(source))
            probe_path.with_name("hosted-macosArm64-consumer.json").write_text(json.dumps(consumer))
            matrix_path = repository / "matrix-macosArm64.json"
            lanes = [{"id": case["id"], "status": "NOT_RUN", "reason": "no evidence supplied"}
                     for case in qualify.expand(qualify.matrix())]
            matrix_path.write_text(json.dumps({"candidate_sha": sha,
                                               "total": 112,
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
            missing = artifact.stage_hosted(repository, manifest, sha, target, probe_path,
                                            matrix_path, repository / "bundle-missing")
            self.assertEqual("PROBE_FAILED", missing["status"])
            self.assertIn("core-macosArm64", missing["reason"])

            write_group("core-macosArm64", [("supplemental.FullReportTest", "extra-pass")])
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
            for name, ids in artifact.UBUNTU_PROBES.items():
                count = sum(len(qualify.expected_probe_cases(manifest, groups[group_id]))
                            for group_id in ids)
                (repository / name).write_text(json.dumps(probe(ids, count)))
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
                complete_ubuntu = artifact.stage_ubuntu(repository, manifest, sha, repository,
                                                         repository / "ubuntu-complete")
            self.assertEqual("PROBE_PASSED", complete_ubuntu["status"])
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


if __name__ == "__main__":
    unittest.main()
