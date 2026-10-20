#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

import subclass_provider


BASELINE_SHA256 = "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e"
PROVIDERS = ("AngleJoint", "RevoluteJoint", "WeldJoint", "PulleyJoint", "AVLTree")
STATE_KEYS = tuple(f"{name}_state_{phase}" for name in ("angle", "revolute", "weld")
                   for phase in ("before", "changed", "noop"))
EXPECTED = {
    **{
        f"{name}_{suffix}": value
        for name in ("angle", "revolute", "weld")
        for suffix, value in (
            ("single", "1.0,1.0,calls=0"),
            ("noop", "1.0,1.0,calls=0"),
            ("enabled_single", "1.0,1.0,calls=1,enabled=true"),
            ("enabled_pair", "1.0,1.0,calls=2"),
            ("enabled_direct", "5.0,5.0,calls=2"),
            ("enabled_noop", "5.0,5.0,calls=2"),
        )
    },
    "pulley_total": "6.0,componentCalls=0,0",
    "pulley_components": "100.0,200.0,componentCalls=1,1",
    "tree_string": "BinarySearchTree[888],iteratorCalls=0,inOrderCalls=1",
    "tree_iterator": "777,iteratorCalls=1",
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execute(command, output, name, environment):
    result = subprocess.run(command, capture_output=True, env=environment, check=False)
    (output / f"{name}.stdout").write_bytes(result.stdout)
    (output / f"{name}.stderr").write_bytes(result.stderr)
    return result


def observations(raw, provider):
    values = {}
    for line in raw.decode("utf-8").splitlines():
        key, separator, value = line.partition("=")
        if not separator or key in values:
            raise ValueError(f"invalid or repeated observation: {line}")
        values[key] = value
    if set(values) != set(EXPECTED) | set(STATE_KEYS) | {f"provider_{name}" for name in PROVIDERS}:
        raise ValueError("missing or extra fixture observations")
    for name in PROVIDERS:
        if not subclass_provider.matches_provider(values.pop(f"provider_{name}"), provider):
            raise ValueError(f"{name} resolved from another provider")
    return values


def check_baseline_state(values):
    for name in ("angle", "revolute", "weld"):
        before = tuple(map(float, values[f"{name}_state_before"].split(",")))
        changed = tuple(map(float, values[f"{name}_state_changed"].split(",")))
        noop = tuple(map(float, values[f"{name}_state_noop"].split(",")))
        if len(before) != 7 or len(changed) != 7 or len(noop) != 7:
            raise ValueError(f"{name} state observation has wrong arity")
        if before[:2] != (2.8, 3.5) or before[2] == 0.0 or before[5:] != (7.0, 11.0):
            raise ValueError(f"{name} baseline setup did not seed adjusted state and impulses")
        if changed != (1.25, 1.25, 0.0, 1.25, 1.25, 0.0, 0.0):
            raise ValueError(f"{name} baseline changed-state control failed")
        if noop != (1.25, 1.25, 0.0, 1.25, 1.25, 13.0, 17.0):
            raise ValueError(f"{name} baseline unchanged-state control failed")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--java-home", type=Path, default=Path("/tmp/dyn4k-tools/jdk21"))
    parser.add_argument("--kotlin-stdlib", type=Path, required=True)
    parser.add_argument("--mutation-control", choices=("skip-reset", "skip-recalculation"))
    args = parser.parse_args()
    baseline, candidate, output = args.baseline.resolve(), args.candidate.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.pop("OLLAMA_API_KEY", None)
    receipt = {"baseline": str(baseline), "candidate": str(candidate), "status": "FAILED"}
    receipt["mutation_control"] = args.mutation_control
    try:
        kotlin_stdlib = args.kotlin_stdlib.resolve(strict=True)
        receipt["kotlin_stdlib"] = str(kotlin_stdlib)
        receipt["kotlin_stdlib_sha256"] = sha256(kotlin_stdlib)
        receipt["baseline_sha256"] = sha256(baseline)
        receipt["candidate_sha256"] = sha256(candidate)
        if receipt["baseline_sha256"] != BASELINE_SHA256:
            raise ValueError("baseline JAR differs from pinned dyn4j 6.0.0")
        if baseline == candidate or receipt["candidate_sha256"] == BASELINE_SHA256:
            raise ValueError("baseline JAR supplied as candidate")
        classes = output / "classes"
        classes.mkdir(exist_ok=True)
        source = Path(__file__).resolve().parent / "fixtures" / "JointSubclassDispatch.java"
        receipt["fixture_sha256"] = sha256(source)
        compiler = execute(
            [str(args.java_home / "bin/javac"), "-cp", str(baseline), "-d", str(classes), str(source)],
            output, "compile", environment)
        if compiler.returncode:
            raise ValueError(f"fixture compilation failed: {compiler.returncode}")
        for name, provider in (("baseline", baseline), ("candidate", candidate)):
            mutation_property = []
            if name == "candidate" and args.mutation_control:
                property_name = ("skipReset" if args.mutation_control == "skip-reset"
                                 else "skipRecalculation")
                mutation_property = [f"-Djoint.state.{property_name}=true"]
            result = execute(
                [str(args.java_home / "bin/java"), *mutation_property, "-cp",
                 os.pathsep.join((str(classes), str(provider), str(kotlin_stdlib))),
                 "org.dyn4j.dynamics.joint.JointSubclassDispatch"], output, name, environment)
            receipt[f"{name}_exit"] = result.returncode
            if result.returncode:
                raise ValueError(f"{name} fixture failed: {result.returncode}")
            receipt[f"{name}_observations"] = observations(result.stdout, provider)
        if {key: receipt["baseline_observations"][key] for key in EXPECTED} != EXPECTED:
            raise ValueError("pinned baseline observations changed")
        check_baseline_state(receipt["baseline_observations"])
        mismatches = {
            key: {"expected": expected, "actual": receipt["candidate_observations"].get(key)}
            for key, expected in {**EXPECTED, **{key: receipt["baseline_observations"][key]
                                                 for key in STATE_KEYS}}.items()
            if receipt["candidate_observations"].get(key) != expected
        }
        receipt["mismatches"] = mismatches
        if mismatches:
            raise ValueError(f"{len(mismatches)} candidate observations differ")
        receipt["status"] = "PASSED"
    except (OSError, ValueError) as error:
        receipt["error"] = str(error)
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": receipt["status"], "error": receipt.get("error"),
                      "cases": len(EXPECTED) + len(STATE_KEYS), "candidate_sha256": receipt.get("candidate_sha256")}))
    return 0 if receipt["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
