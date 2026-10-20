import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import qualify
import geometry_subclass_dispatch
import joint_subclass_dispatch
import subclass_audit
import vector_subclass_dispatch


class SubclassAuditTest(unittest.TestCase):
    def test_run_refuses_to_overwrite_existing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            prior = output / "receipt.json"
            prior.write_text("preserved\n")
            argv = ["subclass_audit.py", "--baseline", "unused", "--stdlib", "unused",
                    "--java-home", "unused", "--jdk-major", "8", "--output", str(output)]
            with patch.object(sys, "argv", argv), self.assertRaisesRegex(ValueError, "already contains"):
                subclass_audit.main()
            self.assertEqual("preserved\n", prior.read_text())

    def test_process_replay_rejects_changed_stream_and_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            command = [sys.executable, "-c", "import sys; print('observed'); print('error', file=sys.stderr)"]
            environment = os.environ.copy()
            environment.pop("OLLAMA_API_KEY", None)
            expected_stdout = b"observed" + os.linesep.encode()
            self.assertEqual(expected_stdout.decode(),
                             subclass_audit.execute(command, output, "probe", environment))
            subclass_audit.verify_process(output, "probe", command)
            stdout = output / "probe.stdout"
            original_stdout = stdout.read_bytes()
            self.assertEqual(expected_stdout, original_stdout)
            recorded = json.loads((output / "probe.process.json").read_text())
            self.assertEqual(hashlib.sha256(original_stdout).hexdigest(), recorded["stdout_sha256"])
            stdout.write_text("changed\n")
            with self.assertRaisesRegex(ValueError, "stdout"):
                subclass_audit.verify_process(output, "probe", command)
            stdout.write_bytes(original_stdout)
            stderr = output / "probe.stderr"
            original_stderr = stderr.read_bytes()
            self.assertEqual(hashlib.sha256(original_stderr).hexdigest(), recorded["stderr_sha256"])
            stderr.write_text("changed error\n")
            with self.assertRaisesRegex(ValueError, "stderr"):
                subclass_audit.verify_process(output, "probe", command)
            stderr.write_bytes(original_stderr)
            metadata = output / "probe.process.json"
            original = metadata.read_text()
            changed = json.loads(original)
            changed["argv"][-1] = "wrong command"
            metadata.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError, "argv"):
                subclass_audit.verify_process(output, "probe", command)
            changed["argv"] = command
            changed["exit_code"] = 1
            metadata.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError, "exit"):
                subclass_audit.verify_process(output, "probe", command)
            changed["exit_code"] = 0
            changed["started_at_utc"] = "not a time"
            metadata.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError, "time"):
                subclass_audit.verify_process(output, "probe", command)
            metadata.write_text(original)
            subclass_audit.verify_process(output, "probe", command)

    def test_jdk_version_must_match_selected_major_and_compiler(self):
        self.assertEqual("1.8.0_504", subclass_audit.version_from_raw(
            'openjdk version "1.8.0_504"\n', "javac 1.8.0_504\n", 8))
        with self.assertRaisesRegex(ValueError, "major"):
            subclass_audit.version_from_raw('openjdk version "21.0.12.1"\n',
                                            "javac 21.0.12.1\n", 8)
        with self.assertRaisesRegex(ValueError, "differ"):
            subclass_audit.version_from_raw('openjdk version "21.0.12.1"\n',
                                            "javac 21.0.11\n", 21)

    def test_top_receipt_binds_every_family_control(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            controls = {}
            for family in subclass_audit.FAMILIES:
                folder = output / family
                folder.mkdir()
                (folder / "control.json").write_text('{"status":"PASSED"}\n')
                controls[family] = subclass_audit.sha256(folder / "control.json")
            receipt = {"status": "PASSED", "families": dict.fromkeys(subclass_audit.FAMILIES, "PASSED"),
                       "family_controls": controls}
            subclass_audit.verify_family_bindings(output, receipt)
            (output / "joint/control.json").write_text('{"status":"FAILED"}\n')
            with self.assertRaisesRegex(ValueError, "joint"):
                subclass_audit.verify_family_bindings(output, receipt)

    def test_vector_output_requires_the_original_completion_line(self):
        self.assertEqual(vector_subclass_dispatch.SUCCESS,
                         subclass_audit.parse_vector(vector_subclass_dispatch.SUCCESS))
        for incomplete in ("", "vector subclass dispatch passed", "other\n"):
            with self.subTest(incomplete=incomplete), self.assertRaisesRegex(ValueError, "vector"):
                subclass_audit.parse_vector(incomplete)

    def test_aabb_output_requires_all_five_cases_and_exact_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            jar = Path(directory) / "candidate.jar"
            jar.write_bytes(b"candidate")
            lines = [f"provider={jar.as_uri()}"] + [
                f"{key}={value}" for key, value in subclass_audit.AABB_EXPECTED.items()
            ]
            self.assertEqual(subclass_audit.AABB_EXPECTED,
                             subclass_audit.parse_aabb("\n".join(lines) + "\n", jar))
            with self.assertRaisesRegex(ValueError, "missing or extra"):
                subclass_audit.parse_aabb("\n".join(lines[:-1]) + "\n", jar)
            with self.assertRaisesRegex(ValueError, "provider"):
                subclass_audit.parse_aabb("\n".join(["provider=file:///wrong.jar"] + lines[1:]) + "\n", jar)

    def test_windows_drive_file_uri_uses_windows_path_rules(self):
        from pathlib import PureWindowsPath
        from subclass_provider import local_file_uri_path

        # The retained Windows run used a D: checkout and Path.as_uri() in this fixture.
        uri = "file:///D:/a/dyn4k/dyn4k/candidate%20jar.jar"
        expected = PureWindowsPath("D:/a/dyn4k/dyn4k/candidate jar.jar")
        self.assertEqual(expected, local_file_uri_path(uri, windows=True))
        self.assertEqual(expected, local_file_uri_path(uri.replace("file:///", "file:/"),
                                                       windows=True))
        for invalid in ("file://remote.invalid/D:/a/candidate.jar", "file:///D:/bad%ZZ.jar",
                        "file:///D:/bad%2Fname.jar", "file:///D:/candidate.jar#fragment"):
            with self.subTest(uri=invalid), self.assertRaisesRegex(ValueError, "provider URI"):
                local_file_uri_path(invalid, windows=True)

    def test_process_replay_preserves_crlf_stream_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            command = [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'windows\\r\\n')"]
            environment = os.environ.copy()
            environment.pop("OLLAMA_API_KEY", None)
            self.assertEqual("windows\r\n", subclass_audit.execute(command, output, "probe", environment))
            stream = output / "probe.stdout"
            original = stream.read_bytes()
            self.assertEqual(b"windows\r\n", original)
            metadata = subclass_audit.verify_process(output, "probe", command)
            self.assertEqual(hashlib.sha256(original).hexdigest(), metadata["stdout_sha256"])
            stream.write_bytes(original.replace(b"\r\n", b"\n"))
            with self.assertRaisesRegex(ValueError, "stdout"):
                subclass_audit.verify_process(output, "probe", command)

    def test_all_subclass_parsers_require_local_exact_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            jar = Path(directory) / "candidate jar.jar"
            jar.write_bytes(b"candidate")
            aabb = {**subclass_audit.AABB_EXPECTED, "provider": jar.as_uri()}
            geometry = {**dict.fromkeys(geometry_subclass_dispatch.CASES, "value"),
                        **{f"provider.{name}": jar.as_uri()
                           for name in geometry_subclass_dispatch.PROVIDERS}}
            joint = {**joint_subclass_dispatch.EXPECTED,
                     **dict.fromkeys(joint_subclass_dispatch.STATE_KEYS, "0"),
                     **{f"provider_{name}": jar.as_uri()
                        for name in joint_subclass_dispatch.PROVIDERS}}

            def lines(values):
                return "".join(f"{key}={value}\n" for key, value in values.items())

            parsers = (
                (subclass_audit.parse_aabb, aabb, "provider"),
                (geometry_subclass_dispatch.parse, geometry, "provider.Transform"),
                (lambda raw, provider: joint_subclass_dispatch.observations(raw.encode(), provider),
                 joint, "provider_AngleJoint"),
            )
            for parser, values, key in parsers:
                with self.subTest(parser=parser.__module__):
                    parser(lines(values), jar)
                    for invalid in ("file:///wrong.jar", "file://remote.invalid/share/candidate.jar",
                                    "file:///bad%ZZ.jar", "https:///candidate.jar",
                                    jar.as_uri() + "?query=1"):
                        with self.subTest(uri=invalid), self.assertRaisesRegex(ValueError, "provider"):
                            parser(lines({**values, key: invalid}), jar)

    def test_candidate_is_selected_only_from_replayed_current_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            relative = qualify.target_binary_path("dyn4k-core", "jvm")
            jar = root / "build/staging-repository" / relative
            jar.parent.mkdir(parents=True)
            jar.write_bytes(b"candidate")
            digest = hashlib.sha256(jar.read_bytes()).hexdigest()
            audit = {"candidate_sha": "a" * 40, "status": "PASSED", "targets": ["jvm"],
                     "artifacts": [{"path": relative, "sha256": digest}]}
            with patch.object(qualify, "require_clean_checkout") as clean, patch.object(
                    qualify, "verify_audit_against_staging") as replay:
                self.assertEqual(jar, subclass_audit.resolve_candidate(root, "a" * 40, audit,
                                                                          "b" * 64))
                clean.assert_called_once_with(root, "a" * 40)
                replay.assert_called_once_with(audit, root)
                for bad in (dict(audit, candidate_sha="c" * 40),
                            dict(audit, targets=["js"]),
                            dict(audit, status="FAILED"),
                            dict(audit, artifacts=[{"path": relative, "sha256": "0" * 64}])):
                    with self.assertRaises(ValueError):
                        subclass_audit.resolve_candidate(root, "a" * 40, bad, "b" * 64)
                jar.write_bytes(b"changed")
                with self.assertRaisesRegex(ValueError, "hash"):
                    subclass_audit.resolve_candidate(root, "a" * 40, audit, "b" * 64)
                jar.write_bytes(b"candidate")
                with self.assertRaisesRegex(ValueError, "baseline JAR"):
                    subclass_audit.resolve_candidate(root, "a" * 40, audit, digest)
                clean.side_effect = ValueError("stale checkout")
                with self.assertRaisesRegex(ValueError, "stale checkout"):
                    subclass_audit.resolve_candidate(root, "a" * 40, audit, "b" * 64)
                clean.side_effect = None
                replay.side_effect = ValueError("changed staged file")
                with self.assertRaisesRegex(ValueError, "changed staged file"):
                    subclass_audit.resolve_candidate(root, "a" * 40, audit, "b" * 64)


if __name__ == "__main__":
    unittest.main()
