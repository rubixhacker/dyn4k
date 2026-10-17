#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path

from measure import sha256


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(root):
    root = Path(root)
    identity_file = root / "candidate-identity-at-pilot.json"
    identity = json.loads(identity_file.read_text())
    identity_hash = sha256(identity_file)
    counts = {}
    for name in ("pilot", "noise", "memory", "plateau", "discovery-plateau-v0"):
        directory = root / name
        evidence = json.loads((directory / "evidence.json").read_text())
        require(evidence["candidate_identity_sha256"] == identity_hash,
                f"{name} uses a different candidate identity")
        require(evidence["candidate_identity"] == identity,
                f"{name} embedded identity differs")
        if name != "discovery-plateau-v0":
            require(len(evidence["results"]) == evidence["expected_runs"] and not evidence["failures"],
                    f"{name} has an incomplete or failed run")
        for item in evidence["results"]:
            require(sha256(directory / item["raw"]) == item["raw_sha256"],
                    f"{name} measured CSV checksum differs")
            require(sha256(directory / item["warmup_raw"]) == item["warmup_sha256"],
                    f"{name} warm-up CSV checksum differs")
            if name == "plateau":
                with (directory / item["warmup_raw"]).open(newline="") as stream:
                    require(next(csv.reader(stream)) == ["warmup_step", "elapsed_ns"],
                            "plateau warm-up CSV header is invalid")
                require(item["cycles"] == 100, "plateau cycle count differs")
        counts[name] = len(evidence["results"])
    provider = json.loads((root / "provider-identity.json").read_text())
    require(provider["candidate_identity_sha256"] == identity_hash,
            "provider proof uses a different candidate identity")
    core = next(path for path in identity["sha256"] if path.endswith("/dyn4k-core-jvm-0.1.0-alpha.1.jar"))
    api = next(path for path in identity["sha256"] if path.endswith("/dyn4k-jvm-0.1.0-alpha.1.jar"))
    require(provider["routes"]["direct_kotlin"]["origin"]["core"] == core and
            provider["routes"]["direct_kotlin"]["origin"]["api"] == api and
            provider["routes"]["compatibility"]["origin"]["core"] == core and
            provider["routes"]["compatibility"]["origin"]["api"] == "unavailable",
            "provider origins differ from staged routes")
    controls_dir = root / "negative-controls"
    controls = json.loads((controls_dir / "negative-controls.json").read_text())
    require(controls["candidate_identity_sha256"] == identity_hash and
            len(controls["controls"]) == 6 and
            all(item["status"] == "rejected_as_expected" for item in controls["controls"].values()),
            "negative controls are incomplete")
    require(sha256(controls_dir / "synthetic-empty-scene.csv") == controls["synthetic_empty_sha256"] and
            sha256(controls_dir / "synthetic-inactive-scene.csv") == controls["synthetic_inactive_sha256"],
            "negative-control CSV checksum differs")
    analysis = json.loads((root / "analysis.json").read_text())
    require(analysis["qualification"] == "unpassed" and analysis["pilot_runs"] == counts["pilot"] and
            analysis["noise_runs"] == counts["noise"], "analysis index differs from raw counts")
    return {"identity_sha256": identity_hash, "runs": counts,
            "negative_controls": len(controls["controls"]), "qualification": "unpassed"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive")
    args = parser.parse_args()
    print(json.dumps(verify(args.archive), sort_keys=True))


if __name__ == "__main__":
    main()
