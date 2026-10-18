from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


DECLARATION_FLAGS = ("ACC_PUBLIC", "ACC_PROTECTED", "ACC_BRIDGE", "ACC_SYNTHETIC")


def ledger_signature(signature: str) -> str:
    declaration, marker, descriptor = signature.partition("; descriptor: ")
    if marker and "(" in declaration and " static " in declaration:
        declaration = re.sub(r"\bfinal ", "", declaration, count=1)
    return declaration + marker + descriptor


def declarations(plain: str, verbose: str, oracle: object) -> tuple[str, dict[tuple[str, str], tuple[str, list[str]]]]:
    header = next((line.strip() for line in plain.splitlines() if line.strip().endswith("{")), None)
    if header is None:
        raise ValueError("type header missing from plain javap output")
    api = oracle.surface(verbose)
    if api is None:
        return header, {}
    _, records = oracle.member_inventory(verbose)
    classfile = {}
    for record in records:
        key = (record["name"], record["descriptor"])
        if key in classfile:
            raise ValueError(f"duplicate class-file member: {key}")
        classfile[key] = record
    members = {}
    for key, signatures in api[1].items():
        if not signatures:
            raise ValueError(f"member signatures missing: {key}")
        for signature in signatures:
            declaration, marker, descriptor = signature.partition("; descriptor: ")
            if not marker or not descriptor:
                raise ValueError(f"member descriptor missing: {signature}")
            record = classfile.get((key[0], descriptor))
            if record is None or ledger_signature(signature) != ledger_signature(
                    f"{re.sub(r'\s+', ' ', str(record['declaration']))} descriptor: {descriptor}"):
                raise ValueError(f"strict surface differs from class-file member: {signature}")
            member_key = (key[0], descriptor if "(" in descriptor else "")
            if member_key in members:
                raise ValueError(f"duplicate declaration: {member_key}")
            members[member_key] = (ledger_signature(signature),
                                   [flag for flag in DECLARATION_FLAGS if flag in record["flags"]])
    for record in records:
        if ("ACC_BRIDGE" not in record["flags"]
                or not any(flag in record["flags"] for flag in ("ACC_PUBLIC", "ACC_PROTECTED"))):
            continue
        key = (record["name"], record["descriptor"])
        if key in members:
            raise ValueError(f"duplicate declaration: {key}")
        signature = re.sub(r"\s+", " ", str(record["declaration"]))
        members[key] = (ledger_signature(f"{signature} descriptor: {record['descriptor']}"),
                        [flag for flag in DECLARATION_FLAGS if flag in record["flags"]])
    return header, members


def signature(item: dict, artifact: Path, oracle: object) -> dict:
    identity = item["id"]
    parts = identity.split("|")
    name = parts[0]
    if (len(parts) not in {2, 3} or not re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_.$]*", name)
            or (len(parts) == 2 and parts[1] != "type")):
        raise ValueError("invalid declaration identity for JVM probe")
    candidate = item.get("candidate")
    if (not isinstance(candidate, dict) or candidate.get("identity") != identity
            or not isinstance(candidate.get("artifact_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", candidate["artifact_sha256"])):
        raise ValueError("candidate artifact identity is missing or invalid")
    artifact_sha = candidate["artifact_sha256"]
    if artifact_sha == oracle.BINARY_SHA256:
        raise ValueError("pinned baseline JAR cannot be a candidate artifact")
    if hashlib.sha256(artifact.read_bytes()).hexdigest() != artifact_sha:
        raise ValueError("candidate artifact SHA-256 differs")
    plain_command = ["javap", "-classpath", str(artifact), "-protected", "-s", name]
    verbose_command = ["javap", "-classpath", str(artifact), "-protected", "-s", "-v", name]
    plain = subprocess.run(plain_command, capture_output=True, text=True, check=False, timeout=30)
    verbose = subprocess.run(verbose_command, capture_output=True, text=True, check=False, timeout=30)
    if hashlib.sha256(artifact.read_bytes()).hexdigest() != artifact_sha:
        raise ValueError("candidate artifact SHA-256 changed during probe")
    actual = None
    if plain.returncode == 0 and verbose.returncode == 0:
        header, members = declarations(plain.stdout, verbose.stdout, oracle)
        if len(parts) == 2:
            actual = header
        else:
            actual = members.get((parts[1], parts[2]))
    wanted = item["signature"] if len(parts) == 2 else (item["signature"], item.get("flags"))
    matched = plain.returncode == 0 and verbose.returncode == 0 and actual == wanted
    cases = int(matched)
    failures = int(not matched)
    raw_stdout = json.dumps({"plain": plain.stdout, "verbose": verbose.stdout}, sort_keys=True)
    raw_stderr = json.dumps({"plain": plain.stderr, "verbose": verbose.stderr}, sort_keys=True)
    output = raw_stdout + f"\nACTUAL_TESTS={cases}\nFAILURES={failures}\nIGNORED=0\n"
    return {"command": [plain_command, verbose_command], "expected_cases": 1,
            "actual_executed_cases": cases, "failures": failures, "ignored": 0,
            "process_exit_code": plain.returncode or verbose.returncode,
            "raw_stdout": raw_stdout, "raw_stderr": raw_stderr, "output": output}
