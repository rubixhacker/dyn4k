# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# How to run: imported by nominal-rotation-comparator.py and its verification script.
"""Exact binary64 decoding and closed-interval metric operations for one fixture."""

from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from typing import Final

class RejectedInput(Exception):
    """The input is outside this comparator's explicitly supported domain."""

def require(condition: bool, reason: str) -> None:
    if not condition:
        raise RejectedInput(reason)

@dataclass(frozen=True, slots=True)
class Decoded:
    value: Fraction
    bits: int

def power_two(exponent: int) -> Fraction:
    return Fraction(2**exponent) if exponent >= 0 else Fraction(1, 2**(-exponent))

@lru_cache(maxsize=65536)
def decode(token: str) -> Decoded:
    """Round a finite decimal rational to a normal/zero binary64 using integer ties-to-even."""
    require(len(token) <= 200, "numeric token too long")
    exponent_part = token.lower().split("e")
    require(len(exponent_part) <= 2, "invalid numeric exponent")
    if len(exponent_part) == 2:
        require(abs(int(exponent_part[1])) <= 4000, "unsupported decimal exponent")
    sign = int(token.startswith("-"))
    value = abs(Fraction(token))
    if value == 0:
        return Decoded(Fraction(0), sign << 63)
    exponent = value.numerator.bit_length() - value.denominator.bit_length()
    if value < power_two(exponent):
        exponent -= 1
    require(-1022 <= exponent <= 1023, "nonzero subnormal/overflow input unsupported")
    quotient = value / power_two(exponent - 52)
    significand, remainder = divmod(quotient.numerator, quotient.denominator)
    doubled = 2*remainder
    if doubled > quotient.denominator or (doubled == quotient.denominator and significand % 2):
        significand += 1
    if significand == 2**53:
        significand //= 2
        exponent += 1
    require(exponent <= 1023, "rounded result overflows")
    rounded = significand * power_two(exponent - 52)
    bits = (sign << 63) | ((exponent + 1023) << 52) | (significand - 2**52)
    return Decoded(-rounded if sign else rounded, bits)

def numeric_token(token: str) -> Fraction:
    return decode(token).value

def integer_token(token: str) -> int:
    value = int(token)
    require(abs(value) <= 2**53, "integer token outside exact binary64 range")
    return value

def reject_constant(token: str) -> Fraction:
    raise RejectedInput(f"nonfinite JSON constant {token}")

@dataclass(frozen=True, slots=True)
class Bounds:
    lo: Fraction
    hi: Fraction

    def __post_init__(self) -> None:
        require(self.lo <= self.hi, "reversed interval")

    @staticmethod
    def point(value: Fraction) -> "Bounds":
        return Bounds(value, value)

    def __sub__(self, other: "Bounds") -> "Bounds":
        return Bounds(self.lo-other.hi, self.hi-other.lo)

    def scaled(self, scale: int) -> "Bounds":
        ends = (scale*self.lo, scale*self.hi)
        return Bounds(min(ends), max(ends))

    def absolute(self) -> "Bounds":
        lower = Fraction(0) if self.lo <= 0 <= self.hi else min(abs(self.lo), abs(self.hi))
        return Bounds(lower, max(abs(self.lo), abs(self.hi)))

def wrapped_distance(a: Bounds, b: Bounds, pi: Bounds) -> Bounds:
    """For operands in [-4,4], k=-2..2 contains every minimizing 2pi branch."""
    require(-4 <= a.lo <= a.hi <= 4 and -4 <= b.lo <= b.hi <= 4, "angle outside bounded domain")
    require(3 < pi.lo <= pi.hi < 4, "invalid pi enclosure")
    difference = a-b
    candidates = [(difference - pi.scaled(2*k)).absolute() for k in range(-2, 3)]
    return Bounds(min(c.lo for c in candidates), min(c.hi for c in candidates))

def classify(error: Bounds, cap: Fraction) -> str:
    require(error.lo >= 0 and cap >= 0, "invalid error or cap")
    if error.hi <= cap:
        return "PASS"
    if error.lo > cap:
        return "FAIL"
    return "INCONCLUSIVE"

ANALYTIC_CAPS: Final = (Fraction("7e-11"), Fraction("7e-11"), Fraction("5e-8"), Fraction("6e-8"))
PARITY_CAPS: Final = tuple(2*c for c in ANALYTIC_CAPS)

def differential(a: tuple[Fraction, Fraction, Fraction, Fraction],
                 b: tuple[Fraction, Fraction, Fraction, Fraction], pi: Bounds) -> tuple[str, ...]:
    """Apply parity caps to exact values in cosine/sine/public-angle/recorder order."""
    errors = [(Bounds.point(x)-Bounds.point(y)).absolute() for x, y in zip(a, b, strict=True)]
    errors[2] = wrapped_distance(Bounds.point(a[2]), Bounds.point(b[2]), pi)
    return tuple(classify(error, cap) for error, cap in zip(errors, PARITY_CAPS, strict=True))
