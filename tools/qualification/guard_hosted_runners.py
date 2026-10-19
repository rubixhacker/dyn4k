from __future__ import annotations

import re
import sys
from pathlib import Path


HOSTED_LABEL = re.compile(
    r"(?:ubuntu-(?:latest|22\.04|24\.04|26\.04)|"
    r"ubuntu-24\.04-arm|windows-(?:latest|2022|2025))\Z"
)
MAC_LABEL = re.compile(r"(?i)\bmacos-[a-z0-9][a-z0-9_-]*\b")
JOB_HEADER = re.compile(r"  ([A-Za-z_][A-Za-z0-9_-]*):(?:\s*#.*)?\Z")
RUNNER_LINE = re.compile(r"    runs-on: (\S+)(?:\s*#.*)?\Z")
RUNNER_KEY = re.compile(r"(?:^|[\s,{])['\"]?runs-on['\"]?\s*:")
JOBS_KEY = re.compile(r"^['\"]?jobs['\"]?\s*:")


def check_workflow(path: Path) -> list[str]:
    errors: list[str] = []
    if path.is_symlink() or not path.is_file():
        return [f"{path}: active workflow must be a regular file"]
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        return [f"{path}: cannot read workflow: {error}"]

    for number, line in enumerate(source.splitlines(), 1):
        if MAC_LABEL.search(line):
            errors.append(f"{path}:{number}: macOS hosted label is forbidden")

    lines = source.splitlines()
    jobs_sections = [index for index, line in enumerate(lines) if JOBS_KEY.match(line)]
    if len(jobs_sections) != 1 or lines[jobs_sections[0]] != "jobs:":
        errors.append(f"{path}: require one block-style jobs section")
        return errors
    if any("\t" in line[: len(line) - len(line.lstrip())] for line in lines):
        errors.append(f"{path}: tab indentation is forbidden")
    if any(line.strip() in ("---", "...") for line in lines):
        errors.append(f"{path}: multiple YAML documents are forbidden")
    if any(re.match(r"\s*<<\s*:", line) for line in lines):
        errors.append(f"{path}: YAML merge keys are forbidden")

    jobs_start = jobs_sections[0] + 1
    jobs_end = next(
        (index for index in range(jobs_start, len(lines))
         if lines[index] and not lines[index][0].isspace() and not lines[index].startswith("#")),
        len(lines),
    )
    job_names: list[str] = []
    runner_count: dict[str, int] = {}
    current_job: str | None = None
    for index, line in enumerate(lines):
        number = index + 1
        if line.lstrip().startswith("#"):
            continue
        in_jobs = jobs_start <= index < jobs_end
        if in_jobs and line.startswith("  ") and not line.startswith("   "):
            match = JOB_HEADER.fullmatch(line)
            if match is None:
                errors.append(f"{path}:{number}: job must use a block-style header")
                current_job = None
            else:
                current_job = match.group(1)
                if current_job in runner_count:
                    errors.append(f"{path}:{number}: duplicate job {current_job}")
                job_names.append(current_job)
                runner_count[current_job] = 0
        if RUNNER_KEY.search(line):
            match = RUNNER_LINE.fullmatch(line) if in_jobs and current_job else None
            if match is None:
                errors.append(f"{path}:{number}: unsupported runs-on syntax")
                continue
            runner_count[current_job] += 1
            label = match.group(1).strip("'\"")
            if not HOSTED_LABEL.fullmatch(label) or match.group(1) not in (
                label, f"'{label}'", f'"{label}"'
            ):
                errors.append(f"{path}:{number}: runner must be an explicit Linux/Windows hosted label")
    if not job_names:
        errors.append(f"{path}: no jobs found")
    for job in job_names:
        if runner_count[job] != 1:
            errors.append(f"{path}: job {job} must have exactly one explicit runs-on")
    return errors


def scan(root: Path) -> tuple[int, list[str]]:
    directory = root / ".github" / "workflows"
    if not directory.is_dir():
        return 0, [f"{directory}: active workflow directory is missing"]
    paths = sorted((*directory.glob("*.yml"), *directory.glob("*.yaml")))
    if not paths:
        return 0, [f"{directory}: no active workflows found"]
    errors = [error for path in paths for error in check_workflow(path)]
    return len(paths), errors


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    count, errors = scan(root)
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print(f"Checked {count} active workflows: Linux/Windows hosted runners only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
