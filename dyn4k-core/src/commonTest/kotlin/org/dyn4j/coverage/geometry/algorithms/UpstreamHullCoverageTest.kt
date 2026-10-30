/*
 * Copyright (c) 2010-2020 William Bittle  http://www.dyn4j.org/
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without modification, are permitted
 * provided that the following conditions are met:
 *
 *   * Redistributions of source code must retain the above copyright notice, this list of conditions
 *     and the following disclaimer.
 *   * Redistributions in binary form must reproduce the above copyright notice, this list of conditions
 *     and the following disclaimer in the documentation and/or other materials provided with the
 *     distribution.
 *   * Neither the name of the copyright holder nor the names of its contributors may be used to endorse or
 *     promote products derived from this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR
 * IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
 * FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
 * CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
 * DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 * DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER
 * IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT
 * OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

package org.dyn4j.coverage.geometry.algorithms

import de.infix.testBalloon.framework.core.testSuite
import org.dyn4j.Epsilon
import org.dyn4j.geometry.Polygon
import org.dyn4j.geometry.RobustGeometry
import org.dyn4j.geometry.Vector2
import org.dyn4j.geometry.hull.*
import kotlin.math.abs
import kotlin.test.*

val UpstreamHullCoverageTest by testSuite {
    test("monoRandom1") { UpstreamHullCoverageTestFixture().run { monoRandom1() } }
    test("monoRandom2") { UpstreamHullCoverageTestFixture().run { monoRandom2() } }
    test("mono22") { UpstreamHullCoverageTestFixture().run { mono22() } }
    test("mono2") { UpstreamHullCoverageTestFixture().run { mono2() } }
    test("mono3") { UpstreamHullCoverageTestFixture().run { mono3() } }
    test("mono4") { UpstreamHullCoverageTestFixture().run { mono4() } }
    test("mono6") { UpstreamHullCoverageTestFixture().run { mono6() } }
    test("mono7") { UpstreamHullCoverageTestFixture().run { mono7() } }
    test("mono5") { UpstreamHullCoverageTestFixture().run { mono5() } }
    test("mono5Part2") { UpstreamHullCoverageTestFixture().run { mono5Part2() } }
    test("mono5Part3") { UpstreamHullCoverageTestFixture().run { mono5Part3() } }
    test("mono8") { UpstreamHullCoverageTestFixture().run { mono8() } }
    test("mono9") { UpstreamHullCoverageTestFixture().run { mono9() } }
    test("mono10") { UpstreamHullCoverageTestFixture().run { mono10() } }
    test("mono11") { UpstreamHullCoverageTestFixture().run { mono11() } }
    test("mono12") { UpstreamHullCoverageTestFixture().run { mono12() } }
    test("mono13") { UpstreamHullCoverageTestFixture().run { mono13() } }
    test("mono14") { UpstreamHullCoverageTestFixture().run { mono14() } }
    test("gsRandom1") { UpstreamHullCoverageTestFixture().run { gsRandom1() } }
    test("gsRandom2") { UpstreamHullCoverageTestFixture().run { gsRandom2() } }
    test("gs22") { UpstreamHullCoverageTestFixture().run { gs22() } }
    test("gs2") { UpstreamHullCoverageTestFixture().run { gs2() } }
    test("gs3") { UpstreamHullCoverageTestFixture().run { gs3() } }
    test("gs4") { UpstreamHullCoverageTestFixture().run { gs4() } }
    test("gs6") { UpstreamHullCoverageTestFixture().run { gs6() } }
    test("gs7") { UpstreamHullCoverageTestFixture().run { gs7() } }
    test("gs5") { UpstreamHullCoverageTestFixture().run { gs5() } }
    test("gs5Part2") { UpstreamHullCoverageTestFixture().run { gs5Part2() } }
    test("gs5Part3") { UpstreamHullCoverageTestFixture().run { gs5Part3() } }
    test("gs8") { UpstreamHullCoverageTestFixture().run { gs8() } }
    test("gs9") { UpstreamHullCoverageTestFixture().run { gs9() } }
    test("gs10") { UpstreamHullCoverageTestFixture().run { gs10() } }
    test("gs11") { UpstreamHullCoverageTestFixture().run { gs11() } }
    test("gs12") { UpstreamHullCoverageTestFixture().run { gs12() } }
    test("gs13") { UpstreamHullCoverageTestFixture().run { gs13() } }
    test("gs14") { UpstreamHullCoverageTestFixture().run { gs14() } }
    test("giftWrapRandom1") { UpstreamHullCoverageTestFixture().run { giftWrapRandom1() } }
    test("giftWrapRandom2") { UpstreamHullCoverageTestFixture().run { giftWrapRandom2() } }
    test("giftWrap2") { UpstreamHullCoverageTestFixture().run { giftWrap2() } }
    test("giftWrap3") { UpstreamHullCoverageTestFixture().run { giftWrap3() } }
    test("giftWrap4") { UpstreamHullCoverageTestFixture().run { giftWrap4() } }
    test("giftWrap6") { UpstreamHullCoverageTestFixture().run { giftWrap6() } }
    test("giftWrap7") { UpstreamHullCoverageTestFixture().run { giftWrap7() } }
    test("giftWrap5") { UpstreamHullCoverageTestFixture().run { giftWrap5() } }
    test("giftWrap5Part2") { UpstreamHullCoverageTestFixture().run { giftWrap5Part2() } }
    test("giftWrap5Part3") { UpstreamHullCoverageTestFixture().run { giftWrap5Part3() } }
    test("giftWrap8") { UpstreamHullCoverageTestFixture().run { giftWrap8() } }
    test("giftWrap9") { UpstreamHullCoverageTestFixture().run { giftWrap9() } }
    test("giftWrap10") { UpstreamHullCoverageTestFixture().run { giftWrap10() } }
    test("giftWrap11") { UpstreamHullCoverageTestFixture().run { giftWrap11() } }
    test("giftWrap12") { UpstreamHullCoverageTestFixture().run { giftWrap12() } }
    test("giftWrap13") { UpstreamHullCoverageTestFixture().run { giftWrap13() } }
    test("giftWrap14") { UpstreamHullCoverageTestFixture().run { giftWrap14() } }
    test("dacRandom1") { UpstreamHullCoverageTestFixture().run { dacRandom1() } }
    test("dacRandom2") { UpstreamHullCoverageTestFixture().run { dacRandom2() } }
    test("dac22") { UpstreamHullCoverageTestFixture().run { dac22() } }
    test("dac2") { UpstreamHullCoverageTestFixture().run { dac2() } }
    test("dac3") { UpstreamHullCoverageTestFixture().run { dac3() } }
    test("dac4") { UpstreamHullCoverageTestFixture().run { dac4() } }
    test("dac6") { UpstreamHullCoverageTestFixture().run { dac6() } }
    test("dac7") { UpstreamHullCoverageTestFixture().run { dac7() } }
    test("dac5") { UpstreamHullCoverageTestFixture().run { dac5() } }
    test("dac5Part2") { UpstreamHullCoverageTestFixture().run { dac5Part2() } }
    test("dac5Part3") { UpstreamHullCoverageTestFixture().run { dac5Part3() } }
    test("dac8") { UpstreamHullCoverageTestFixture().run { dac8() } }
    test("dac9") { UpstreamHullCoverageTestFixture().run { dac9() } }
    test("dac10") { UpstreamHullCoverageTestFixture().run { dac10() } }
    test("dac11") { UpstreamHullCoverageTestFixture().run { dac11() } }
    test("dac12") { UpstreamHullCoverageTestFixture().run { dac12() } }
    test("dac13") { UpstreamHullCoverageTestFixture().run { dac13() } }
    test("dac14") { UpstreamHullCoverageTestFixture().run { dac14() } }
}

private class JavaCloudRandom(seed: Long) {
    private var state = (seed xor 0x5DEECE66DL) and ((1L shl 48) - 1L)
    private fun next(bits: Int): Int {
        state = (state * 0x5DEECE66DL + 11L) and ((1L shl 48) - 1L)
        return (state ushr (48 - bits)).toInt()
    }
    fun nextDouble(): Double = ((next(26).toLong() shl 27) + next(27)) / 9007199254740992.0
}

private fun randomCloud(seed: Long): Array<Vector2> {
    val random = JavaCloudRandom(seed)
    val size = kotlin.math.floor(random.nextDouble() * 96.0 + 4.0).toInt()
    return Array(size) { Vector2(random.nextDouble() * 2.0 - 1.0, random.nextDouble() * 2.0 - 1.0) }
}

private fun cloud(id: String): Array<Vector2> = when (id) {
    "Random1" -> randomCloud(0L)
    "Random2" -> randomCloud(5L)
    "22" -> arrayOf(
        Vector2(-0.9726201659613243, -0.061797000490076304),
        Vector2(-0.49116488082909115, 0.7678687827639961),
        Vector2(-0.48739204883444187, -0.9956524492331893),
        Vector2(-0.4537370168301149, -0.6616125022480972),
        Vector2(-0.34908102882750347, -0.7747234303505055),
        Vector2(-0.33139487141988466, 0.03531605400219706),
        Vector2(-0.280521830078756, -0.8019885163611113),
        Vector2(-0.18129485409799484, -0.20967044425834414),
        Vector2(0.06567685427976788, 0.08518030687971767),
        Vector2(0.18792402577067557, -0.47162922175654987),
        Vector2(0.4819840632260479, 0.36769528256486916),
        Vector2(0.5215540748770324, 0.47445238228262654),
        Vector2(0.527334528883231, 0.4308651755136941),
        Vector2(0.6152877195482263, 0.7025685140058535),
        Vector2(0.7757776753703407, 0.3215448776809937),
        Vector2(0.7785392212464266, 0.7209603726626324),
        Vector2(0.8940177489295154, -0.1882690653739989)
    )
    "2" -> arrayOf(
        Vector2(23.854242711277, 1.0),
        Vector2(57.707453390935676, 1.0),
        Vector2(13.0, 1.0),
        Vector2(27.918475169266998, 1.0)
    )
    "3" -> arrayOf(
        Vector2(1.5, 1.0),
        Vector2(2.0, 1.0),
        Vector2(2.5, 1.0),
        Vector2(3.5, 1.0),
        Vector2(1.0, 1.0),
        Vector2(5.0, 0.0)
    )
    "4" -> arrayOf(
        Vector2(1.0, 1.0),
        Vector2(1.0, 1.0),
        Vector2(9135172.538699752, 1594.2921033236523),
        Vector2(1.0, 3436.444789677664),
        Vector2(53371.47726301303, 63.201463180191396),
        Vector2(1.0, 1.0),
        Vector2(0.09713620217398017, 286668.0866273699),
        Vector2(104.83526669412421, 579.583503857007)
    )
    "6" -> arrayOf(
        Vector2(9.67305424383519, 114.09907896473986),
        Vector2(1.0, 1161.9752606517477),
        Vector2(1.0, 1.0),
        Vector2(1.0, 10.546088997659012),
        Vector2(22.088494561091807, 230.94365885699824),
        Vector2(2.8366426821689994, 1.0),
        Vector2(8.944224404040732, 6.315177488492587),
        Vector2(1.0, 59.98064323348245),
        Vector2(9.24861145190379, 8404.268678968832),
        Vector2(1.0, 0.03504029713737921),
        Vector2(1.0, 82.55330004652801)
    )
    "7" -> arrayOf(
        Vector2(1.0, 1.5767304065549268E12),
        Vector2(1.870841152451107, 6.534140012505794E23),
        Vector2(1.9603053816739006E12, 9.074076290143341E10),
        Vector2(3260266.640396411, 7.796498271329308E7),
        Vector2(28.709287118505284, 82447.5698720256),
        Vector2(1.8463774403168068E15, 0.013098511687408589),
        Vector2(3740193.601814064, 4682.6340006396895),
        Vector2(3170758.3618271016, 2.131083797649407E7),
        Vector2(143.83527343008367, 3.2294659543003845E15),
        Vector2(1.0, 5.956908518731977E17),
        Vector2(2.0531014115467064E-7, 2306510.1010659263),
        Vector2(1.2474786776966758E20, 1.4802417824918536E11),
        Vector2(1.0, 15.084034859698757)
    )
    "5" -> arrayOf(
        Vector2(69464.96179292782, 0.05006981639456297),
        Vector2(0.03735960666625501, 0.3783853688716485),
        Vector2(334.68865889609134, 3.955720227287777E-23),
        Vector2(5.758935896542613E22, 8.12199057379559E21)
    )
    "5Part2" -> arrayOf(
        Vector2(334.68865889609134, 3.955720227287777E-23),
        Vector2(5.758935896542613E22, 8.12199057379559E21),
        Vector2(69464.96179292782, 0.05006981639456297),
        Vector2(0.03735960666625501, 0.3783853688716485)
    )
    "5Part3" -> arrayOf(
        Vector2(334.68865889609134, 3.955720227287777E-23),
        Vector2(5.758935896542613E22, 8.12199057379559E21),
        Vector2(400.758935896542613E21, 8.12199057379559E20),
        Vector2(69464.96179292782, 0.05006981639456297),
        Vector2(0.03735960666625501, 0.3783853688716485)
    )
    "8" -> arrayOf(
        Vector2(24.00000000000005, 24.000000000000053),
        Vector2(54.85, 6.0),
        Vector2(24.000000000000068, 24.000000000000071),
        Vector2(54.850000000000357, 61.000000000000121),
        Vector2(24.0, 6.0),
        Vector2(6.0, 6.0)
    )
    "9" -> arrayOf(
        Vector2(23.0, 1.0),
        Vector2(57.0, 1.0),
        Vector2(13.0, 1.0),
        Vector2(27.0, 10.0)
    )
    "10" -> arrayOf(
        Vector2(-7.725662343635252, 3.239314248048395),
        Vector2(-7.725662343635252, 9.244107520658332),
        Vector2(-7.725662343635252, 5.6066430781506575),
        Vector2(-5.985432177897989, 1.0634285355681339),
        Vector2(2.7404621676247265, -4.946792659796997)
    )
    "11" -> arrayOf(
        Vector2(-5.214810023866061, -5.581528163221621),
        Vector2(-3.2956195481849493, 6.700146933201903),
        Vector2(2.159226322162535, -2.2353877725618476),
        Vector2(4.84788802330902, -6.921113359457114),
        Vector2(4.84788802330902, -6.921113359457114)
    )
    "12" -> arrayOf(
        Vector2(-0.33826889474805055, 8.329321811558497),
        Vector2(-3.5586156659982215, -3.467244912905423),
        Vector2(-3.5586156659982215, -4.566140779700733),
        Vector2(-3.5586156659982215, -3.05702346750299),
        Vector2(1.1178446483487536, -3.05702346750299)
    )
    "13" -> arrayOf(
        Vector2(-0.9025337983824699, 4.56709308364953),
        Vector2(-5.5168621708920345, 0.34366552069341916),
        Vector2(-2.400927400987851, 3.19563523962121),
        Vector2(-9.419896312210547, 3.19563523962121)
    )
    "14" -> arrayOf(
        Vector2(5.916275853509346, -4.228267720344762),
        Vector2(8.31483976082672, -0.3807196367883092),
        Vector2(3.9941738969349405, -0.491971233546733),
        Vector2(-5.952110964171484, -0.7480752942332325)
    )
    else -> error("Unknown upstream cloud: $id")
}

private fun robustContains(vertices: Array<Vector2>, point: Vector2): Boolean {
    var p1 = vertices.last()
    var p2 = vertices.first()
    var last = RobustGeometry.getLocation(point, p1, p2)
    for (i in 0 until vertices.size - 1) {
        p1 = p2
        p2 = vertices[i + 1]
        if (point == p1 || point == p2) return true
        val location = RobustGeometry.getLocation(point, p1, p2)
        if (last * location < 0.0) return false
        if (abs(location) > Epsilon.E) last = location
    }
    return true
}

private class UpstreamHullCoverageTestFixture  {
    private fun check(generator: HullGenerator, id: String) {
        val points = cloud(id)
        val original = points.toList()
        val hull = generator.generate(*points)
        assertTrue(hull.all { vertex -> original.any { it === vertex } })
        val list = original.toMutableList()
        val listHull = generator.generate(list)
        assertEquals(hull.size, listHull.size)
        assertTrue(listHull.all { vertex -> original.any { it === vertex } })
        if (id == "2") {
            assertFailsWith<IllegalArgumentException> { Polygon(*hull) }
            return
        }
        val polygon = Polygon(*hull)
        for (point in points) assertTrue(robustContains(polygon.getVertices(), point), "$id: $point")
    }
fun monoRandom1() = check(MonotoneChain(), "Random1")
fun monoRandom2() = check(MonotoneChain(), "Random2")
fun mono22() = check(MonotoneChain(), "22")
fun mono2() = check(MonotoneChain(), "2")
fun mono3() = check(MonotoneChain(), "3")
fun mono4() = check(MonotoneChain(), "4")
fun mono6() = check(MonotoneChain(), "6")
fun mono7() = check(MonotoneChain(), "7")
fun mono5() = check(MonotoneChain(), "5")
fun mono5Part2() = check(MonotoneChain(), "5Part2")
fun mono5Part3() = check(MonotoneChain(), "5Part3")
fun mono8() = check(MonotoneChain(), "8")
fun mono9() = check(MonotoneChain(), "9")
fun mono10() = check(MonotoneChain(), "10")
fun mono11() = check(MonotoneChain(), "11")
fun mono12() = check(MonotoneChain(), "12")
fun mono13() = check(MonotoneChain(), "13")
fun mono14() = check(MonotoneChain(), "14")
fun gsRandom1() = check(GrahamScan(), "Random1")
fun gsRandom2() = check(GrahamScan(), "Random2")
fun gs22() = check(GrahamScan(), "22")
fun gs2() = check(GrahamScan(), "2")
fun gs3() = check(GrahamScan(), "3")
fun gs4() = check(GrahamScan(), "4")
fun gs6() = check(GrahamScan(), "6")
fun gs7() = check(GrahamScan(), "7")
fun gs5() = check(GrahamScan(), "5")
fun gs5Part2() = check(GrahamScan(), "5Part2")
fun gs5Part3() = check(GrahamScan(), "5Part3")
fun gs8() = check(GrahamScan(), "8")
fun gs9() = check(GrahamScan(), "9")
fun gs10() = check(GrahamScan(), "10")
fun gs11() = check(GrahamScan(), "11")
fun gs12() = check(GrahamScan(), "12")
fun gs13() = check(GrahamScan(), "13")
fun gs14() = check(GrahamScan(), "14")
fun giftWrapRandom1() = check(GiftWrap(), "Random1")
fun giftWrapRandom2() = check(GiftWrap(), "Random2")
fun giftWrap2() = check(GiftWrap(), "2")
fun giftWrap3() = check(GiftWrap(), "3")
fun giftWrap4() = check(GiftWrap(), "4")
fun giftWrap6() = check(GiftWrap(), "6")
fun giftWrap7() = check(GiftWrap(), "7")
fun giftWrap5() = check(GiftWrap(), "5")
fun giftWrap5Part2() = check(GiftWrap(), "5Part2")
fun giftWrap5Part3() = check(GiftWrap(), "5Part3")
fun giftWrap8() = check(GiftWrap(), "8")
fun giftWrap9() = check(GiftWrap(), "9")
fun giftWrap10() = check(GiftWrap(), "10")
fun giftWrap11() = check(GiftWrap(), "11")
fun giftWrap12() = check(GiftWrap(), "12")
fun giftWrap13() = check(GiftWrap(), "13")
fun giftWrap14() = check(GiftWrap(), "14")
fun dacRandom1() = check(DivideAndConquer(), "Random1")
fun dacRandom2() = check(DivideAndConquer(), "Random2")
fun dac22() = check(DivideAndConquer(), "22")
fun dac2() = check(DivideAndConquer(), "2")
fun dac3() = check(DivideAndConquer(), "3")
fun dac4() = check(DivideAndConquer(), "4")
fun dac6() = check(DivideAndConquer(), "6")
fun dac7() = check(DivideAndConquer(), "7")
fun dac5() = check(DivideAndConquer(), "5")
fun dac5Part2() = check(DivideAndConquer(), "5Part2")
fun dac5Part3() = check(DivideAndConquer(), "5Part3")
fun dac8() = check(DivideAndConquer(), "8")
fun dac9() = check(DivideAndConquer(), "9")
fun dac10() = check(DivideAndConquer(), "10")
fun dac11() = check(DivideAndConquer(), "11")
fun dac12() = check(DivideAndConquer(), "12")
fun dac13() = check(DivideAndConquer(), "13")
fun dac14() = check(DivideAndConquer(), "14")
}
