import argparse
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path


CONFIGURED_REVISION = "44dd7cf05502fa4b5fdc3523e3271c3cba335de8"
DEFAULT_REVISION = "cd610b696f1f7be2f3c1590840139a7cc596b04c"
NOMINAL_REVISION = "f5053629d68dc134092434310c3d130ee1c0d9b5"
DEFAULT_FILES = ("sleep-wake-exact-checks.mjs", "initial-reference-review-manifest.json")
CONFIGURED_FILES = (
    "sleep-wake-quality-exact-checks.mjs",
    "sleep-wake-exact-checks.mjs",
    "sleep-wake-quality-acceptance.mjs",
    "sleep-wake-penetration-acceptance.mjs",
    "sleep-wake-quality-candidate-manifest.json",
    "initial-reference-review-manifest.json",
)
NOMINAL_FILES = (
    "nominal-rotation-comparator.py",
    "nominal-rotation-comparator-verify.py",
    "nominal-rotation-comparator-numbers.py",
    "nominal-rotation-error-model-certificate.py",
)


def restore(repo, revision, names, target):
    for name in names:
        path = f"docs/research/{name}"
        result = subprocess.run(("git", "-C", str(repo), "show", f"{revision}:{path}"),
                                capture_output=True)
        if result.returncode:
            raise RuntimeError(f"missing pinned Git object: {revision}:{path}")
        (target / name).write_bytes(result.stdout)
    if revision in (CONFIGURED_REVISION, DEFAULT_REVISION):
        actual = hashlib.sha256((target / "sleep-wake-exact-checks.mjs").read_bytes()).hexdigest()
        if actual != "803f78a03aca84b4177de0d22d6d4f3b2bef79ce258e16d8028e65fcaeb7346a":
            raise RuntimeError("approved semantic checker hash differs")


def main():
    parser = argparse.ArgumentParser(description="Replay approved frozen baseline checkers")
    parser.add_argument("mode", choices=("default-exact", "configured-exact", "nominal-rotation"))
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--package")
    parser.add_argument("--archive")
    parser.add_argument("--raw")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.mode == "configured-exact" and not all((args.package, args.archive)):
        parser.error("configured-exact needs --package and --archive")
    if args.mode == "default-exact" and not args.package:
        parser.error("default-exact needs --package")
    if args.mode == "nominal-rotation" and not args.raw:
        parser.error("nominal-rotation needs --raw")
    with tempfile.TemporaryDirectory(prefix="dyn4k-approved-check-") as directory:
        target = Path(directory)
        if args.mode == "configured-exact":
            restore(args.repo, CONFIGURED_REVISION, CONFIGURED_FILES, target)
            command = ("node", str(target / "sleep-wake-quality-exact-checks.mjs"),
                       args.package, args.archive, args.output)
        elif args.mode == "default-exact":
            restore(args.repo, DEFAULT_REVISION, DEFAULT_FILES, target)
            command = ("node", str(target / "sleep-wake-exact-checks.mjs"), args.package)
        else:
            restore(args.repo, NOMINAL_REVISION, NOMINAL_FILES, target)
            command = (sys.executable, str(target / "nominal-rotation-comparator.py"),
                       args.raw, args.output)
        completed = subprocess.run(command, check=False,
                                   stdout=subprocess.PIPE if args.mode == "default-exact" else None)
        if args.mode == "default-exact" and completed.returncode == 0:
            Path(args.output).write_bytes(completed.stdout)
            print(completed.stdout.decode())
        raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
