# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# How to run: python3 nominal-rotation-comparator-verify.py EXACT_RAW_GZIP NEW_OUTPUT_DIRECTORY
"""Independent decoder, boundary and rejection checks for the bounded comparator."""

from decimal import Decimal, localcontext
from fractions import Fraction
from hashlib import sha256
from importlib import import_module
from pathlib import Path
import gzip
import json
import struct
import sys

n = import_module("nominal-rotation-comparator-numbers")
c = import_module("nominal-rotation-comparator")

def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)

def reject_number(token: str) -> None:
    try:
        n.decode(token)
    except (n.RejectedInput, ValueError):
        return
    raise AssertionError(f"number unexpectedly accepted: {token}")

def reject_line(line: bytes) -> None:
    try:
        c.parse_line(line)
    except (n.RejectedInput, json.JSONDecodeError, ValueError):
        return
    raise AssertionError(f"line unexpectedly accepted: {line!r}")

def decimal_fraction(value: Fraction) -> str:
    with localcontext() as context:
        context.prec = 200
        return format(Decimal(value.numerator)/Decimal(value.denominator), "f")

def run(raw: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    check(sha256(raw.read_bytes()).hexdigest() == c.RAW_HASH, "wrong verification input")
    checked = []
    one_bits = 0x3ff0000000000000
    for value, bits in [(Fraction(1)+Fraction(1, 2**53), one_bits),
                        (Fraction(1)+Fraction(3, 2**53), one_bits+2),
                        (Fraction(2)-Fraction(1, 2**53), 0x4000000000000000)]:
        for sign in (1, -1):
            actual = n.decode(decimal_fraction(sign*value))
            check(actual.bits == bits | ((sign < 0) << 63), "tie parity/sign/binade error")
    checked.append("six exact halfway ties: even lower, even upper, binade carry, both signs")
    check(n.decode("0.1").value == Fraction(3602879701896397, 36028797018963968), "decimal treated as exact")
    check(n.decode("-0.0").bits == 1 << 63 and n.decode("0.0").bits == 0, "signed zero lost")
    check(n.decode("-0.0").value == n.decode("0.0").value, "numerical zero equivalence")
    checked.append("known 0.1 rational and signed-zero encoding/numerical equality")
    for exponent in (-1000, -500, -100, -1, 0, 1, 100, 500, 1000):
        for mantissa in (0, 1, 2, 2**51-1, 2**52-1):
            for sign in (0, 1):
                bits = (sign << 63) | ((exponent+1023) << 52) | mantissa
                host_value = struct.unpack(">d", bits.to_bytes(8, "big"))[0]
                check(n.decode(repr(host_value)).bits == bits, "normal round-trip bit mismatch")
    checked.append("90 independently constructed binary64 normal round-trips across exponent ranges")
    for token in ("1.7976931348623157e308", "2.2250738585072014e-308"):
        check(n.decode(token).bits == int.from_bytes(struct.pack(">d", float(token)), "big"), "range endpoint mismatch")
    for token in ("NaN", "Infinity", "1e309", "1e-400", "5e-324", "1e999999", "bad", "1.7976931348623159e308"):
        reject_number(token)
    checked.append("finite range endpoints; eight malformed/nonfinite/unsupported/overflow numeric rejections")
    cap = Fraction("5e-8")
    eps = Fraction(1, 10**70)
    cases = [(n.Bounds(cap, cap), "PASS"), (n.Bounds(cap-eps, cap), "PASS"),
             (n.Bounds(cap+eps, cap+eps), "FAIL"), (n.Bounds(cap-eps, cap+eps), "INCONCLUSIVE"),
             (n.Bounds(cap, cap+eps), "INCONCLUSIVE")]
    for error, verdict in cases:
        check(n.classify(error, cap) == verdict, f"endpoint verdict mismatch: {verdict}")
    checked.append("inclusive cap, strict failure, two straddling cases including lower endpoint exactly cap")
    p = c.oracle.pi_interval()
    pi = n.Bounds(Fraction(p.lo, c.oracle.SCALE), Fraction(p.hi, c.oracle.SCALE))
    near_pi = n.decode("3.141592653589793").value
    across = n.wrapped_distance(n.Bounds.point(near_pi), n.Bounds.point(-near_pi), pi)
    expected = n.Bounds(2*(pi.lo-near_pi), 2*(pi.hi-near_pi))
    check(across == expected and across.hi < Fraction("1e-15"), "wrap cut exact-point enclosure")
    across_intervals = n.wrapped_distance(pi, pi.scaled(-1), pi)
    check(across_intervals.lo == 0 and across_intervals.hi < Fraction("1e-65"), "wrap cut interval enclosure")
    check(n.classify(n.wrapped_distance(n.Bounds.point(Fraction(0)), pi, pi), cap) == "FAIL", "half turn accepted")
    checked.append("opposite wrap-cut sides; narrow intervals at +/-pi; half-turn rejection")
    zero = (Fraction(0),)*4
    check(n.differential(zero, zero, pi) == ("PASS",)*4, "identical differential")
    check(n.differential(zero, n.PARITY_CAPS, pi) == ("PASS",)*4, "differential inclusive caps")
    check(n.differential(zero, tuple(x+eps for x in n.PARITY_CAPS), pi) == ("FAIL",)*4, "differential over caps")
    check(n.differential((Fraction(0), Fraction(0), near_pi, Fraction(0)),
                         (Fraction(0), Fraction(0), -near_pi, Fraction(0)), pi) == ("PASS",)*4,
          "differential cut handling")
    checked.append("16 synthetic differential outcomes: identity, inclusive cap, over cap and wrap cut")
    a = c.parse_line(b'{"x":0.0,"values":[1.0,-0.0]}')
    b = c.parse_line(b'{"x":-0.0,"values":[1.0,0.0]}')
    changed = c.parse_line(b'{"x":0.0,"values":[1.0000000000000002,0.0]}')
    check(c.exact_copy(a, b) and not c.exact_copy(a, changed), "inheritance equality/mutation error")
    checked.append("full nested numerical inheritance with zero signs and one-ulp changed value")
    for line in (b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e99999}', b'{"x":1.0',
                 b'{"x":0,"x":1}', b'{"x":9007199254740993}', b'[]', b'not json'):
        reject_line(line)
    checked.append("eight malformed/nonfinite/truncated/duplicate/unsafe-integer/schema JSON rejections")
    for index, data in enumerate((b"", raw.read_bytes()[:100], gzip.compress(b'{"kind":NaN}\n'))):
        bad = destination/f"rejected-{index}.gz"
        bad.write_bytes(data)
        try:
            c.audit(bad, destination/f"rejected-{index}-output")
        except n.RejectedInput as error:
            check(str(error) == "raw gzip hash mismatch", "unexpected rejection route")
        else:
            raise AssertionError("mismatched/truncated input was accepted")
        check(not (destination/f"rejected-{index}-output"/"manifest.json").exists(), "rejection published success")
    checked.append("three full-entry hash mismatch/empty/truncated gzip rejections with no success manifest")
    seen: set[str] = set()
    def independent_float(token: str) -> int:
        if token not in seen:
            actual_bits = n.decode(token).bits
            host_bits = int.from_bytes(struct.pack(">d", float(token)), "big")
            check(actual_bits == host_bits, f"archived token decoder disagreement: {token}")
            seen.add(token)
        return 0
    with gzip.open(raw, "rb") as source:
        for line in source:
            json.loads(line, parse_float=independent_float, parse_constant=n.reject_constant)
    checked.append(f"all {len(seen)} distinct archived floating tokens agree with independent CPython decoder bits")
    result = {"status": "PASS", "checks": checked, "distinct_archived_float_tokens": len(seen),
              "verification_script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
              "checker_sha256": sha256(Path(c.__file__).read_bytes()).hexdigest(),
              "numeric_helper_sha256": sha256(Path(n.__file__).read_bytes()).hexdigest(),
              "qualification_scope": "bounded manual-proof and executed checks; no formal machine proof or port run"}
    (destination/"verification.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    check(len(sys.argv) == 3, "usage: verify.py EXACT_RAW_GZIP NEW_OUTPUT_DIRECTORY")
    run(Path(sys.argv[1]), Path(sys.argv[2]))
