import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[2]
QUALIFICATION = REPOSITORY / "tools/qualification"
sys.path.insert(0, str(QUALIFICATION))
import full_hosted  # noqa: E402


class CheckoutBytePolicyTests(unittest.TestCase):
    def test_git_autocrlf_true_preserves_hash_guarded_source_inputs(self):
        candidate = subprocess.check_output(
            ["git", "-C", str(REPOSITORY), "rev-parse", "HEAD"], text=True
        ).strip()
        corpus = json.loads((REPOSITORY / full_hosted.MANIFEST).read_bytes())
        paths = set(full_hosted.INPUTS)
        paths.update(item["path"] for item in corpus["source_files"])

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

        relative_paths = sorted(paths)
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
