# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# How to run: python3 nominal-rotation-error-model-certificate.py OUTPUT_DIRECTORY
"""Certify conditional bounds with exact integers; never read observed residuals."""

from dataclasses import asdict, dataclass
from fractions import Fraction
from hashlib import sha256
from math import factorial, isqrt
from pathlib import Path
import json
import sys
from typing import Final

SCALE: Final = 10**70
STEPS: Final = 36000
U: Final = Fraction(1, 2**53)
ALPHA: Final = Fraction(4803839602528529, 2**59)


class CertificateFailure(Exception):
    """A mathematical precondition failed; no certificate may be issued."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CertificateFailure(message)


def ceiling(numerator: int, denominator: int) -> int:
    return -((-numerator) // denominator)


@dataclass(frozen=True, slots=True)
class Interval:
    """Closed outward-rounded interval with integer endpoints scaled by SCALE."""

    lo: int
    hi: int

    @staticmethod
    def rational(value: Fraction) -> "Interval":
        n = value.numerator * SCALE
        d = value.denominator
        return Interval(n // d, ceiling(n, d))

    def __add__(self, other: "Interval") -> "Interval":
        return Interval(self.lo + other.lo, self.hi + other.hi)

    def __neg__(self) -> "Interval":
        return Interval(-self.hi, -self.lo)

    def __sub__(self, other: "Interval") -> "Interval":
        return self + (-other)

    def __mul__(self, other: "Interval") -> "Interval":
        products = (self.lo * other.lo, self.lo * other.hi,
                    self.hi * other.lo, self.hi * other.hi)
        return Interval(min(products) // SCALE, ceiling(max(products), SCALE))

    def divide_integer(self, denominator: int) -> "Interval":
        require(denominator > 0, "division denominator must be positive")
        return Interval(self.lo // denominator, ceiling(self.hi, denominator))

    def magnitude(self) -> int:
        return max(abs(self.lo), abs(self.hi))


def atan_reciprocal(denominator: int) -> Interval:
    """Alternating rational series plus the first omitted term encloses atan(1/d)."""
    total = Fraction(0)
    for k in range(200):
        total += Fraction((-1)**k, (2*k + 1) * denominator**(2*k + 1))
    remainder = Fraction(1, 401 * denominator**401)
    return Interval.rational(total) + Interval.rational(remainder) * Interval(0, SCALE)


def pi_interval() -> Interval:
    """Machin identity pi = 16 atan(1/5) - 4 atan(1/239)."""
    return (Interval(16*SCALE, 16*SCALE) * atan_reciprocal(5)
            - Interval(4*SCALE, 4*SCALE) * atan_reciprocal(239))


def sin_cos(angle: Interval) -> tuple[Interval, Interval]:
    """Degree119/118 Taylor polynomials, rigorous Lagrange remainders for |x|<4."""
    require(angle.magnitude() < 4*SCALE, "Taylor argument out of range")
    square = angle * angle
    sine = sine_term = angle
    cosine = cosine_term = Interval(SCALE, SCALE)
    for k in range(1, 60):
        sine_term = -(sine_term * square).divide_integer(2*k * (2*k + 1))
        cosine_term = -(cosine_term * square).divide_integer((2*k - 1) * 2*k)
        sine = sine + sine_term
        cosine = cosine + cosine_term
    require(Fraction(4**120, factorial(120)) < Fraction(1, SCALE), "sine remainder")
    require(Fraction(4**119, factorial(119)) < Fraction(1, SCALE), "cosine remainder")
    remainder = Interval(-1, 1)
    return sine + remainder, cosine + remainder


def decimal_exact(scaled: int) -> str:
    sign = "-" if scaled < 0 else ""
    whole, fractional = divmod(abs(scaled), SCALE)
    return f"{sign}{whole}.{fractional:070d}"


def one_digit_cap(bound: Fraction) -> Fraction:
    """Round a positive derived bound upward to one significant decimal digit."""
    require(bound > 0, "nonpositive cap")
    quantum = Fraction(1)
    while quantum > bound:
        quantum /= 10
    return ceiling(bound.numerator * quantum.denominator,
                   bound.denominator * quantum.numerator) * quantum


@dataclass(frozen=True, slots=True)
class StepCertificate:
    step: int
    sine_sign_margin_lower: str
    acos_domain_margin_lower: str
    getter_error_upper: str


@dataclass(frozen=True, slots=True)
class Summary:
    status: str
    qualification_status: str
    steps: int
    alpha_exact: str
    unit_roundoff: str
    component_bound: str
    getter_bound: str
    getter_worst_step: int
    recorder_bound: str
    per_increment_wrapper_bound: str
    sum_roundoff_bound: str
    min_sine_sign_margin: str
    min_acos_domain_margin: str
    component_analytic_cap: str
    getter_analytic_cap: str
    recorder_analytic_cap: str
    component_parity_cap: str
    getter_parity_cap: str
    recorder_parity_cap: str
    relative_allowance: str
    step_certificate_sha256: str
    script_sha256: str


def run(destination: Path) -> Summary:
    """Write reproducible schedule certificate and summary of conditional inequalities."""
    destination.mkdir(parents=True, exist_ok=True)
    pi = pi_interval()
    require(3*SCALE < pi.lo < pi.hi < 4*SCALE, "invalid pi enclosure")
    require(ALPHA == Fraction.from_float(0.016666666666666666) / 2, "wrong timestep")
    max_getter = worst_step = 0
    min_sign = min_domain = SCALE
    certificates = destination / "steps.jsonl"
    with certificates.open("w") as output:
        for n in range(1, STEPS + 1):
            theta = Interval.rational(n*ALPHA)
            turns = (theta.lo + (pi.lo + pi.hi)//2) // (pi.lo + pi.hi)
            phase = theta - Interval(2*turns*SCALE, 2*turns*SCALE) * pi
            require(-pi.lo < phase.lo <= phase.hi < pi.lo, f"principal phase ambiguous at {n}")
            sine, cosine = sin_cos(phase)
            error = Interval.rational(16*n*U).hi
            sine_lower = min(abs(sine.lo), abs(sine.hi))
            require(sine.lo * sine.hi > 0, f"sine sign interval crosses zero at {n}")
            sign_margin = sine_lower - error
            cosine_upper = cosine.magnitude() + error
            domain_margin = SCALE - cosine_upper
            require(sign_margin > 0 and domain_margin > 0, f"getter margin failed at {n}")
            # sqrt(1-cosine_upper**2) rounded downward on the same lattice.
            derivative_denominator = isqrt(SCALE*SCALE - cosine_upper*cosine_upper)
            require(derivative_denominator > 0, f"zero derivative denominator at {n}")
            getter = ceiling(error*SCALE, derivative_denominator) + Interval.rational(4*U).hi
            if getter > max_getter:
                max_getter, worst_step = getter, n
            min_sign, min_domain = min(min_sign, sign_margin), min(min_domain, domain_margin)
            record = StepCertificate(n, decimal_exact(sign_margin), decimal_exact(domain_margin),
                                     decimal_exact(getter))
            output.write(json.dumps(asdict(record), sort_keys=True) + "\n")
    getter_bound = Fraction(max_getter, SCALE)
    component = 16*STEPS*U
    wrapper = 16*U
    # The reduced exact increment plus all perturbations stays strictly inside (0,pi).
    require(ALPHA - 2*getter_bound - wrapper > 0, "increment can reverse")
    require(ALPHA + 2*getter_bound + wrapper < Fraction(pi.lo, SCALE), "turn-count ambiguity")
    sum_abs = STEPS*(ALPHA + 2*getter_bound + wrapper)
    gamma = STEPS*U / (1 - STEPS*U)
    sum_roundoff = gamma*sum_abs
    recorder = getter_bound + STEPS*wrapper + sum_roundoff
    component_cap = one_digit_cap(component)
    getter_cap = one_digit_cap(getter_bound)
    recorder_cap = one_digit_cap(recorder)
    def upper(value: Fraction) -> str:
        return decimal_exact(Interval.rational(value).hi)
    summary = Summary(
        "PASS_CONDITIONAL_MODEL", "UNQUALIFIED_BASELINE_PRIMITIVES_AND_ALL_PORT_RUNTIMES",
        STEPS, str(ALPHA), str(U), upper(component), upper(getter_bound), worst_step,
        upper(recorder), upper(wrapper), upper(sum_roundoff), decimal_exact(min_sign),
        decimal_exact(min_domain), upper(component_cap), upper(getter_cap), upper(recorder_cap),
        upper(2*component_cap), upper(2*getter_cap), upper(2*recorder_cap), "0",
        sha256(certificates.read_bytes()).hexdigest(), sha256(Path(__file__).read_bytes()).hexdigest())
    (destination / "manifest.json").write_text(json.dumps(asdict(summary), indent=2) + "\n")
    return summary


if __name__ == "__main__":
    require(len(sys.argv) == 2, "usage: certificate.py OUTPUT_DIRECTORY")
    print(json.dumps(asdict(run(Path(sys.argv[1]))), indent=2))
