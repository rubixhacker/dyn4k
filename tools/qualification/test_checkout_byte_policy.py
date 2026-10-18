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
    return paths


class CheckoutBytePolicyTests(unittest.TestCase):
    def test_git_autocrlf_true_preserves_hash_guarded_source_inputs(self):
        candidate = subprocess.check_output(
            ["git", "-C", str(REPOSITORY), "rev-parse", "HEAD"], text=True
        ).strip()
        relative_paths = sorted(hash_guarded_source_paths())
        with tempfile.TemporaryDirectory(prefix="dyn4k-autocrlf-") as temporary:
            prefix = str(Path(temporary)) + "/"
            request = b"\0".join(path.encode("utf-8") for path in relative_paths) + b"\0"
            subprocess.run(
                ["git", "-C", str(REPOSITORY), "-c", "core.autocrlf=true",
                 "checkout-index", "--force", "-z", "--stdin", f"--prefix={prefix}"],
                input=request,
                check=True,
            )
            changed = []
            for path in relative_paths:
                expected = subprocess.check_output(
                    ["git", "-C", str(REPOSITORY), "show", f"{candidate}:{path}"]
                )
                actual = (Path(temporary) / path).read_bytes()
                if actual != expected:
                    changed.append(path)

        if changed:
            self.fail(
                "core.autocrlf=true changed committed bytes for "
                f"{len(changed)} hash-guarded inputs; first paths: "
                + ", ".join(changed[:12])
            )


if __name__ == "__main__":
    unittest.main()
