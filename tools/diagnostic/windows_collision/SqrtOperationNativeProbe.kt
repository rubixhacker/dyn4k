import org.dyn4j.geometry.nearestSqrt
import org.dyn4j.geometry.nearestSqrtFromCandidate
import kotlin.math.sqrt

private data class Input(val id: String, val xBits: Long, val yBits: Long, val sumBits: Long, val rootBits: Long)

private val inputs = arrayOf(
    Input("CirclePolygon.edge3", -4621899953565315924L, -4625196817309499400L, 4598175219545276415L, 4602678819172646911L),
    Input("CapsuleSlice.epa4", 4603460912955918154L, -4617903595553423057L, 4607182418800017407L, 4607182418800017407L),
    Input("CirclePolygon.epa3", -4619490269450149183L, -4618227961596862473L, 4607182418800017407L, 4607182418800017407L),
    Input("CircleSegment.epa2", -4621644133008675367L, -4617140533381304871L, 4607182418800017407L, 4607182418800017407L),
    Input("CircleSlice.epa35", 4606804953716818183L, 4598831979030654181L, 4607182418800017407L, 4607182418800017407L),
    Input("PolygonCapsule.sat1", -4624133661653997234L, 4606741575090066687L, 4607182418800017407L, 4607182418800017407L),
    Input("PolygonCapsule.sat4", 4605462196814083239L, -4619902518423102882L, 4607182418800017407L, 4607182418800017407L)
)

private fun equal(id: String, expected: Long, actual: Double) {
    check(actual.toRawBits() == expected) {
        "$id expected=$expected actual=${actual.toRawBits()}"
    }
}

fun main() {
    for (input in inputs) {
        val x = Double.fromBits(input.xBits)
        val y = Double.fromBits(input.yBits)
        val sum = x * x + y * y
        equal("${input.id}.sum", input.sumBits, sum)
        equal("${input.id}.corrected", input.rootBits, nearestSqrt(sum))
        equal("${input.id}.forcedUp", input.rootBits,
            nearestSqrtFromCandidate(sum, Double.fromBits(input.rootBits + 1L)))
        equal("${input.id}.forcedDown", input.rootBits,
            nearestSqrtFromCandidate(sum, Double.fromBits(input.rootBits - 1L)))
        val forcedUp = Double.fromBits(input.rootBits + 1L)
        println("input\t${input.id}\t${sum.toRawBits()}\t${sqrt(sum).toRawBits()}\t${forcedUp.toRawBits()}\t${nearestSqrtFromCandidate(sum, forcedUp).toRawBits()}\t${nearestSqrt(sum).toRawBits()}")
    }

    val centers = longArrayOf(4598175219545276415L, 4607182418800017407L)
    val expectedNeighbors = arrayOf(
        longArrayOf(4602678819172646909L, 4602678819172646910L, 4602678819172646910L,
            4602678819172646911L, 4602678819172646911L, 4602678819172646912L,
            4602678819172646912L, 4602678819172646913L, 4602678819172646913L),
        longArrayOf(4607182418800017405L, 4607182418800017406L, 4607182418800017406L,
            4607182418800017407L, 4607182418800017407L, 4607182418800017408L,
            4607182418800017408L, 4607182418800017409L, 4607182418800017409L)
    )
    for (center in centers.indices) {
        for (index in 0..8) {
            val bits = centers[center] + index - 4L
            val value = Double.fromBits(bits)
            val expected = expectedNeighbors[center][index]
            equal("neighbor.$center.$index", expected, nearestSqrt(value))
            equal("neighborUp.$center.$index", expected,
                nearestSqrtFromCandidate(value, Double.fromBits(expected + 1L)))
            equal("neighborDown.$center.$index", expected,
                nearestSqrtFromCandidate(value, Double.fromBits(expected - 1L)))
            println("neighbor\t$center\t${index - 4}\t$bits\t$expected\t${sqrt(value).toRawBits()}")
        }
    }

    val edgeBits = longArrayOf(1L, 2L, 4503599627370495L, 4503599627370496L,
        4598175219545276416L, 4607182418800017408L, 9218868437227405311L)
    val edgeRoots = longArrayOf(2188749418902061056L, 2190614870947216333L,
        2305843009213693951L, 2305843009213693952L, 4602678819172646912L,
        4607182418800017408L, 6913025428013711359L)
    for (index in edgeBits.indices) {
        val value = Double.fromBits(edgeBits[index])
        equal("edge.$index", edgeRoots[index], nearestSqrt(value))
        println("edge\t${edgeBits[index]}\t${edgeRoots[index]}\t${sqrt(value).toRawBits()}")
    }
    for (index in centers.indices) {
        val value = Double.fromBits(centers[index])
        val expected = expectedNeighbors[index][4]
        equal("fallbackZero.$index", expected, nearestSqrtFromCandidate(value, 0.0))
        equal("fallbackInfinity.$index", expected,
            nearestSqrtFromCandidate(value, Double.POSITIVE_INFINITY))
        equal("fallbackFar.$index", expected,
            nearestSqrtFromCandidate(value, Double.fromBits(expected + 6L)))
    }

    equal("positiveZero", 0L, nearestSqrt(0.0))
    equal("negativeZero", Long.MIN_VALUE, nearestSqrt(-0.0))
    equal("positiveInfinity", Double.POSITIVE_INFINITY.toRawBits(), nearestSqrt(Double.POSITIVE_INFINITY))
    check(nearestSqrt(Double.NaN).isNaN())
    check(nearestSqrt(-1.0).isNaN())
    check(nearestSqrt(Double.NEGATIVE_INFINITY).isNaN())
    println("PASS inputs=7 neighbors=18 edges=7 specials=6 fallback=6 forcedDirections=both")
}
