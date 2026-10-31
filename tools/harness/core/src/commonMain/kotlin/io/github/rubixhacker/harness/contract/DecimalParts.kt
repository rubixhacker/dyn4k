package io.github.rubixhacker.harness.contract

/**
 * Significant digits of a positive finite double, in the form `value = 0.digits * 10^(exponent + 1)`.
 */
internal class DecimalParts(val digits: String, val exponent: Int)

/**
 * Returns the shortest digit sequence that reads back as [value].
 *
 * Python's `repr` uses the shortest round-trip form. Java's `Double.toString` differs for
 * subnormal values, for example it prints `4.9E-324` where Python prints `5e-324`. The search
 * below returns the same digits as Python for every tested value.
 */
internal expect fun shortestDecimalParts(value: Double): DecimalParts
