import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[2]
QUALIFICATION = REPOSITORY / "tools/qualification"
PERFORMANCE = REPOSITORY / "tools/performance"
sys.path.insert(0, str(QUALIFICATION))
sys.path.insert(0, str(PERFORMANCE))
import full_hosted  # noqa: E402
import independent_gates  # noqa: E402
import verify_candidate_archive  # noqa: E402


SUSTAINED_VERIFIER_INPUTS = {
    "tools/performance/sustained_archive.py",
    "tools/performance/manifest.py",
    "tools/performance/measure.py",
    "tools/performance/analyze.py",
    "tools/performance/candidate_runner.py",
    "tools/performance/stress_monitor.py",
    "docs/research/performance-manifest-v1.json",
    "tools/performance/candidate_pilot.py",
    "tools/performance/provider_probe.py",
}

BASELINE_NUMERICAL_VERIFIER_INPUTS = {
    "tools/numerical/portable/baseline_capture.py",
    "tools/numerical/portable/run.py",
    "tools/numerical/portable/cases.py",
    "tools/numerical/portable/receipt.py",
}

COMPATIBILITY_VERIFIER_INPUTS = {
    "tools/compatibility/PinnedCorpusReport.java",
    "tools/compatibility/fixtures/java_source_projection/frozen-adverse-audit.json",
    "tools/compatibility/fixtures/java_source_projection/extra/Names.java",
    "tools/compatibility/fixtures/java_source_projection/org/dyn4j/geometry/simplify/NodeDispatchProbe.java",
    "tools/compatibility/exception-public-api-projection.json",
    "tools/compatibility/fixtures/exception_serialization/verify.py",
    "tools/compatibility/fixtures/exception_serialization/ExceptionSerializationProbe.java",
    "tools/baseline/fixtures/CopyExceptionAmbiguity.java",
    "tools/baseline/fixtures/ExtraMethodsAuditFixture.java",
    "tools/baseline/fixtures/ExtraMethodsProbe.java",
}


def hash_guarded_source_paths():
    corpus = json.loads((REPOSITORY / full_hosted.MANIFEST).read_bytes())
    paths = set(full_hosted.INPUTS)
    paths.update(item["path"] for item in corpus["source_files"])
    paths.update(independent_gates.APPROVED_POLICY)
    paths.update(independent_gates.APPROVED_NOMINAL)
    paths.update(
        f"tools/numerical/portable/{name}"
        for name in independent_gates.APPROVED_P2_PRODUCERS
    )
    paths.update(
        f"tools/numerical/portable/{name}"
        for name in independent_gates.APPROVED_PROSPECTIVE_CHECKERS
    )
    paths.add(independent_gates.PROSPECTIVE_POLICY_PATH)
    paths.update(BASELINE_NUMERICAL_VERIFIER_INPUTS)
    paths.update(SUSTAINED_VERIFIER_INPUTS)
    paths.update(COMPATIBILITY_VERIFIER_INPUTS)
    paths.update(verify_candidate_archive.SOURCE_FILES)

    tracked = subprocess.check_output(
        ["git", "-C", str(REPOSITORY), "ls-files", "-z"]
    ).split(b"\0")
    for raw_path in tracked:
        if not raw_path:
            continue
        path = raw_path.decode("utf-8")
        if (path.startswith(("dyn4k-core/src/", "dyn4k/src/"))
                and path.endswith((".kt", ".java"))):
            paths.add(path)
        if path.startswith("tools/diagnostic/windows_collision/"):
            paths.add(path)
    return paths


def changed_paths(candidate, checkout, relative_paths):
    changed = []
    for path in relative_paths:
        expected = subprocess.check_output(
            ["git", "-C", str(REPOSITORY), "show", f"{candidate}:{path}"]
        )
        actual = (checkout / path).read_bytes()
        if actual != expected:
            changed.append(path)
    return changed


class CheckoutBytePolicyTests(unittest.TestCase):
    def test_fresh_git_autocrlf_true_checkout_preserves_hash_guarded_source_inputs(self):
        candidate = subprocess.check_output(
            ["git", "-C", str(REPOSITORY), "rev-parse", "HEAD"], text=True
        ).strip()
        relative_paths = sorted(hash_guarded_source_paths())
        with tempfile.TemporaryDirectory(prefix="dyn4k-autocrlf-") as temporary:
            checkout = Path(temporary) / "checkout"
            subprocess.run(
                ["git", "-C", str(REPOSITORY), "-c", "core.autocrlf=true",
                 "worktree", "add", "--detach", "--force", str(checkout), candidate],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                changed = changed_paths(candidate, checkout, relative_paths)
                diagnostic_paths = [
                    path for path in relative_paths
                    if path.startswith("tools/diagnostic/windows_collision/")
                ]
                adverse_path = "tools/diagnostic/windows_collision/SqrtOperationNativeProbe.kt"
                adverse_file = checkout / adverse_path
                adverse_file.write_bytes(adverse_file.read_bytes() + b"\n// adverse source mutation\n")
                self.assertIn(adverse_path,
                              changed_paths(candidate, checkout, diagnostic_paths))
            finally:
                subprocess.run(
                    ["git", "-C", str(REPOSITORY), "worktree", "remove", "--force",
                     str(checkout)],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

        if changed:
            self.fail(
                "core.autocrlf=true changed committed bytes for "
                f"{len(changed)} hash-guarded inputs; first paths: "
                + ", ".join(changed[:12])
            )


if __name__ == "__main__":
    unittest.main()
