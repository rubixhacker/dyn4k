from __future__ import annotations

import re
import subprocess
from pathlib import Path


def signature(item: dict, artifact: Path, oracle: object) -> dict:
    identity = item["id"]
    parts = identity.split("|")
    name = parts[0]
    if (len(parts) not in {2, 3} or not re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_.$]*", name)
            or (len(parts) == 2 and parts[1] != "type")):
        raise ValueError("invalid declaration identity for JVM probe")
    command = ["javap", "-classpath", str(artifact), "-protected", "-s", name]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)
    surface = oracle.surface(result.stdout) if result.returncode == 0 else None
    actual = None
    if surface is not None:
        if len(parts) == 2:
            actual = surface[0]
        else:
            actual = surface[1].get((parts[1], parts[2]))
    matched = result.returncode == 0 and actual == item["signature"]
    cases = int(matched)
    failures = int(not matched)
    output = result.stdout + f"ACTUAL_TESTS={cases}\nFAILURES={failures}\nIGNORED=0\n"
    return {"command": command, "expected_cases": 1, "actual_executed_cases": cases,
            "failures": failures, "ignored": 0, "process_exit_code": result.returncode,
            "raw_stdout": result.stdout, "raw_stderr": result.stderr, "output": output}
