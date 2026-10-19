import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import qualify
import subclass_audit


class SubclassAuditTest(unittest.TestCase):
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
