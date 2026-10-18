import re


def parse_instrumentation(raw):
    lines = raw.splitlines()
    terminal = [index for index, line in enumerate(lines) if line.startswith("INSTRUMENTATION_CODE:")]
    if len(terminal) != 1 or lines[terminal[0]] != "INSTRUMENTATION_CODE: -1":
        raise ValueError("expected exactly one successful instrumentation terminal code")
    if terminal[0] != next(index for index in range(len(lines) - 1, -1, -1) if lines[index].strip()):
        raise ValueError("instrumentation terminal code is not final")
    summaries = [line for line in lines if line.startswith("OK (")]
    if len(summaries) != 1 or not (summary := re.fullmatch(r"OK \(([1-9]\d*) tests?\)", summaries[0])):
        raise ValueError("expected exactly one successful instrumentation summary")
    final_result = next((line for line in reversed(lines[:terminal[0]]) if line.strip()), None)
    if final_result != summaries[0]:
        raise ValueError("instrumentation summary is not final")
    if any(line.startswith("FAILURES!!!") for line in lines):
        raise ValueError("instrumentation failure summary present")
    result = {"instrumentation": {"cases": {}, "passed": 0, "failed": 0, "skipped": 0},
              "portable": {"cases": {}, "passed": 0, "failed": 0, "skipped": 0},
              "completed": True, "summary_tests": int(summary.group(1)), "reported_totals": []}
    fields = {}
    stack_open = False
    for line in lines:
        if line.startswith("INSTRUMENTATION_STATUS: "):
            key, separator, value = line[len("INSTRUMENTATION_STATUS: "):].partition("=")
            if separator:
                fields[key] = value
                stack_open = key in ("stack", "dyn4k_stack")
        elif line.startswith("INSTRUMENTATION_STATUS_CODE: "):
            code = int(line.rsplit(": ", 1)[1])
            if "numtests" in fields:
                result["reported_totals"].append(int(fields["numtests"]))
            if "dyn4k_case" in fields:
                name = fields["dyn4k_case"]
                status = fields.get("dyn4k_status")
                if code != 0 or status not in ("PASSED", "FAILED", "SKIPPED"):
                    raise ValueError(f"invalid portable status: {name}")
                group = result["portable"]
                if name in group["cases"]:
                    raise ValueError(f"duplicate portable case: {name}")
                group["cases"][name] = {"status": status, "stack": fields.get("dyn4k_stack")}
                group[status.lower() if status != "SKIPPED" else "skipped"] += 1
            elif code in (0, -2, -3) and "class" in fields and "test" in fields:
                name = fields["class"] + "#" + fields["test"]
                group = result["instrumentation"]
                if name in group["cases"]:
                    raise ValueError(f"duplicate instrumentation case: {name}")
                status = {0: "PASSED", -2: "FAILED", -3: "SKIPPED"}[code]
                group["cases"][name] = {"status": status, "stack": fields.get("stack")}
                group[status.lower() if status != "SKIPPED" else "skipped"] += 1
            fields = {}
            stack_open = False
        elif line.startswith("INSTRUMENTATION_RESULT: shortMsg="):
            result["runner_error"] = line.partition("=")[2]
        elif stack_open and fields:
            key = "dyn4k_stack" if "dyn4k_stack" in fields else "stack"
            fields[key] += "\n" + line
    return result


def validate_lane(result, expected_portable, expected_instrumentation, process_exit_code):
    if process_exit_code != 0:
        raise ValueError(f"instrumentation process exit: {process_exit_code}")
    if not result["completed"] or result.get("runner_error"):
        raise ValueError("instrumentation did not complete")
    actual_total = len(result["instrumentation"]["cases"])
    if result["summary_tests"] != actual_total or any(
            total != result["summary_tests"] for total in result["reported_totals"]):
        raise ValueError(f"instrumentation summary mismatch: {result['summary_tests']} vs {actual_total}")
    for name, expected in (("portable", expected_portable),
                           ("instrumentation", expected_instrumentation)):
        group = result[name]
        actual = set(group["cases"])
        if missing := expected - actual:
            raise ValueError(f"missing {name} cases: {sorted(missing)}")
        if extra := actual - expected:
            raise ValueError(f"unexpected {name} cases: {sorted(extra)}")
        if group["skipped"]:
            raise ValueError(f"skipped {name} cases: {group['skipped']}")
        if group["failed"]:
            raise ValueError(f"failed {name} cases: {group['failed']}")
    if not expected_instrumentation or not result["instrumentation"]["passed"]:
        raise ValueError("empty instrumentation suite")
