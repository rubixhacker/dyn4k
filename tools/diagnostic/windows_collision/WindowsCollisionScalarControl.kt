import kotlin.math.sqrt

private data class ScalarInput(val id: String, val xBits: Long, val yBits: Long)

private val inputs = listOf(
    ScalarInput("CirclePolygon.edge3", -4621899953565315924L, -4625196817309499400L),
    ScalarInput("CapsuleSlice.epa4", 4603460912955918154L, -4617903595553423057L),
    ScalarInput("CirclePolygon.epa3", -4619490269450149183L, -4618227961596862473L),
    ScalarInput("CircleSegment.epa2", -4621644133008675367L, -4617140533381304871L),
    ScalarInput("CircleSlice.epa35", 4606804953716818183L, 4598831979030654181L),
    ScalarInput("PolygonCapsule.sat1", -4624133661653997234L, 4606741575090066687L),
    ScalarInput("PolygonCapsule.sat4", 4605462196814083239L, -4619902518423102882L)
)

private fun number(value: Double) = "${value}@${value.toRawBits()}"

fun main() {
    for (input in inputs) {
        val x = Double.fromBits(input.xBits)
        val y = Double.fromBits(input.yBits)
        val xx = x * x
        val yy = y * y
        val sum = xx + yy
        val root = sqrt(sum)
        val reciprocal = 1.0 / root
        println(listOf(
            "DYN4K_COLLISION_SCALAR", "v1", "provider=kotlin-native", "id=${input.id}",
            "x=${number(x)}", "y=${number(y)}", "xSquared=${number(xx)}", "ySquared=${number(yy)}",
            "sum=${number(sum)}", "sqrt=${number(root)}", "reciprocal=${number(reciprocal)}",
            "normalized=${number(x * reciprocal)},${number(y * reciprocal)}"
        ).joinToString("\t"))
    }
}
