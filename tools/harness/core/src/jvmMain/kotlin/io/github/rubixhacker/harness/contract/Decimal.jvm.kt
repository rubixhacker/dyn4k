package io.github.rubixhacker.harness.contract

import java.util.Locale

internal actual fun shortestDecimalParts(value: Double): DecimalParts {
    require(value > 0.0 && value.isFinite()) { "decimal parts need a positive finite value" }

    var chosen = ""
    for (precision in 0..17) {
        val text = String.format(Locale.ROOT, "%.${precision}e", value)
        if (text.toDouble() == value) {
            chosen = text
            break
        }
    }
    check(chosen.isNotEmpty()) { "no round-trip digits for $value" }

    val separator = chosen.indexOf('e')
    val mantissa = chosen.substring(0, separator)
    val exponent = chosen.substring(separator + 1).toInt()
    val digits = mantissa.replace(".", "").trimStart('0')
    val leadingZeros = mantissa.replace(".", "").length - digits.length
    return DecimalParts(digits, exponent - leadingZeros)
}
