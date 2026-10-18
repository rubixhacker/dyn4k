import argparse
import json
from pathlib import Path
import subprocess
import sys

import capture


def selected_artifact(inventory, module, target):
    return capture.native_artifacts(inventory, target)[module]["path"]


def main():
    parser = argparse.ArgumentParser(description="Capture one Native host producer run")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--publication-root", type=Path, required=True)
    parser.add_argument("--source-link-receipt", type=Path)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--target", choices=sorted(capture.NATIVE_HOST_TARGETS), required=True)
    parser.add_argument("--build", choices=("development", "optimized"), required=True)
    parser.add_argument("--steps", type=int, required=True)
    parser.add_argument("--warmup", type=int, required=True)
    parser.add_argument("--host-timeout-seconds", type=float, default=45.0)
    args = parser.parse_args()
    try:
        inventory_path = capture.required_file(str(args.inventory), "build inventory")
        inventory = json.loads(inventory_path.read_text())
        if inventory.get("target") != args.target or inventory.get("build") != args.build:
            raise ValueError("selected Native inventory target or build differs")
        harness = inventory["harness"]
        command = [sys.executable, str(Path(capture.__file__).resolve()),
                   "--archive", str(args.archive), "--inventory", str(inventory_path),
                   "--publication-root", str(args.publication_root),
                   "--scenario", args.scenario, "--target", args.target,
                   "--build", args.build, "--source-sha", inventory["source_sha"],
                   "--runtime", harness, "--harness", harness,
                   "--core", selected_artifact(inventory, "dyn4k-core", args.target),
                   "--kotlin", selected_artifact(inventory, "dyn4k", args.target),
                   "--steps", str(args.steps), "--warmup", str(args.warmup),
                   "--host-timeout-seconds", str(args.host_timeout_seconds)]
        if args.source_link_receipt is not None:
            command += ["--source-link-receipt", str(args.source_link_receipt)]
        raise SystemExit(subprocess.call(command))
    except (KeyError, ValueError, OSError) as error:
        parser.exit(1, f"qualification: unpassed; {error}\n")


if __name__ == "__main__":
    main()
