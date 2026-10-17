#!/usr/bin/env python3
import math
import sys


def rows(path):
    with open(path, encoding="utf-8") as stream:
        return [line.rstrip("\n").split("\t") for line in stream]


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: verify-detection-parity.py baseline.tsv candidate.tsv")
    expected, actual = rows(sys.argv[1]), rows(sys.argv[2])
    if len(expected) != 1288 or len(actual) != 1288:
        raise SystemExit(f"incomplete query matrix: {len(expected)} baseline, {len(actual)} candidate")
    failures = []
    maximum = 0.0
    for index, (left, right) in enumerate(zip(expected, actual)):
        if left[:2] != right[:2] or len(left) != len(right):
            failures.append(f"row {index}: query key, hit state, or value count differs: {left} != {right}")
            continue
        for baseline_value, candidate_value in zip(left[2:], right[2:]):
            baseline_number = float(baseline_value)
            candidate_number = float(candidate_value)
            difference = abs(baseline_number - candidate_number)
            if not math.isnan(difference):
                maximum = max(maximum, difference)
            if not (math.isclose(baseline_number, candidate_number, rel_tol=1e-8, abs_tol=1e-8)
                    or math.isnan(baseline_number) and math.isnan(candidate_number)):
                failures.append(f"{left[0]}: {baseline_value} != {candidate_value}")
    if failures:
        for failure in failures[:20]:
            print(failure, file=sys.stderr)
        raise SystemExit(f"{len(failures)} detection query differences")
    print(f"Detection parity: {len(expected)} rows, zero differences beyond 1e-8, maximum absolute difference {maximum:.17g}")


if __name__ == "__main__":
    main()
