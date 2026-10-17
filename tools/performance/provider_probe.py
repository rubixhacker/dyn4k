#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
from pathlib import Path

from candidate_runner import API, CORE, FLAGS, IDENTITY, STAGING, check_route, git, read_paths, verify_hashes
from measure import sha256


def probe_routes(identity, identity_sha256):
    verify_hashes(identity["sha256"])
    paths = read_paths()
    result = {"schema": 1, "qualification": "unpassed",
              "candidate_identity_sha256": identity_sha256, "routes": {},
              "probe_tool_source_commit": git("rev-parse", "HEAD"),
              "probe_tool_sha256": sha256(Path(__file__))}
    for route in ("direct_kotlin", "compatibility"):
        check_route(route, paths[route])
        command = [identity["java"], *FLAGS, "-cp", os.pathsep.join(map(str, paths[route])),
                   "performance.ProviderIdentity"]
        process = subprocess.run(command, capture_output=True, text=True, check=True)
        values = dict(line.split("=", 1) for line in process.stdout.splitlines())
        expected_api = str(STAGING / API) if route == "direct_kotlin" else "unavailable"
        if values["core"] != str(STAGING / CORE) or values["api"] != expected_api:
            raise ValueError(f"provider origin differs from the staged {route} route")
        if int(values["pid"]) <= 0:
            raise ValueError("invalid provider process identity")
        result["routes"][route] = {"origin": values, "exit_code": process.returncode,
                                   "core_sha256": sha256(STAGING / CORE),
                                   "api_sha256": sha256(STAGING / API) if route == "direct_kotlin" else None}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = probe_routes(json.loads(IDENTITY.read_text()), sha256(IDENTITY))
    out = Path(args.output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"direct_and_compatibility_origins_verified": True, "output": str(out)}))


if __name__ == "__main__":
    main()
