import argparse
import json
from pathlib import Path
import subprocess
import sys

import capture


def selected_artifact(inventory, module):
    matches = [item for item in inventory["resolved_artifacts"]
               if (f":{module}-" in item["module"] and
                   (module != "dyn4k" or ":dyn4k-core-" not in item["module"]))]
    if len(matches) != 1:
        raise ValueError(f"expected one resolved {module} target artifact")
    return matches[0]["path"]


def main():
    parser = argparse.ArgumentParser(description="Capture one Native host producer run")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--target", choices=sorted(capture.NATIVE_HOST_TARGETS), required=True)
    parser.add_argument("--build", choices=("development", "optimized"), required=True)
    parser.add_argument("--steps", type=int, required=True)
    parser.add_argument("--warmup", type=int, required=True)
    args = parser.parse_args()
    try:
        inventory_path = capture.required_file(str(args.inventory), "build inventory")
        inventory = json.loads(inventory_path.read_text())
        if inventory.get("target") != args.target or inventory.get("build") != args.build:
            raise ValueError("selected Native inventory target or build differs")
        harness = inventory["harness"]
        command = [sys.executable, str(Path(capture.__file__).resolve()),
                   "--archive", str(args.archive), "--inventory", str(inventory_path),
                   "--scenario", args.scenario, "--target", args.target,
                   "--build", args.build, "--source-sha", inventory["source_sha"],
                   "--runtime", harness, "--harness", harness,
                   "--core", selected_artifact(inventory, "dyn4k-core"),
                   "--kotlin", selected_artifact(inventory, "dyn4k"),
                   "--steps", str(args.steps), "--warmup", str(args.warmup)]
        raise SystemExit(subprocess.call(command))
    except (KeyError, ValueError, OSError) as error:
        parser.exit(1, f"qualification: unpassed; {error}\n")


if __name__ == "__main__":
    main()
