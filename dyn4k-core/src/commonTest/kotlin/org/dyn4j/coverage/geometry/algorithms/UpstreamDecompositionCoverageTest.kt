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
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Polygon
import org.dyn4j.geometry.Vector2
import org.dyn4j.geometry.Wound
import org.dyn4j.geometry.decompose.*
import kotlin.math.abs
import kotlin.math.max
import kotlin.test.*

val UpstreamDecompositionCoverageTest by testSuite {
    test("Bayazit_lessThan4Vertices") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_lessThan4Vertices() } }
    test("Bayazit_nullVertex") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_nullVertex() } }
    test("Bayazit_coincidentVertex") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_coincidentVertex() } }
    test("Bayazit_success1") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_success1() } }
    test("Bayazit_success2") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_success2() } }
    test("Bayazit_success3") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_success3() } }
    test("Bayazit_success4") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_success4() } }
    test("Bayazit_success5") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_success5() } }
    test("Bayazit_successBird") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_successBird() } }
    test("Bayazit_successTank") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_successTank() } }
    test("Bayazit_successNazcaMonkey") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_successNazcaMonkey() } }
    test("Bayazit_successNazcaHeron") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_successNazcaHeron() } }
    test("Bayazit_successZoom1") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_successZoom1() } }
    test("Bayazit_successZoom2") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_successZoom2() } }
    test("Bayazit_successZoom3") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_successZoom3() } }
    test("Bayazit_successZoom4") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_successZoom4() } }
    test("Bayazit_successZoom5") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_successZoom5() } }
    test("Bayazit_successZoom6") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_successZoom6() } }
    test("Bayazit_successZoom7") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_successZoom7() } }
    test("Bayazit_successTridol1") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_successTridol1() } }
    test("Bayazit_successTridol2") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_successTridol2() } }
    test("Bayazit_successTridol3") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_successTridol3() } }
    test("Bayazit_decomposeFailSelfIntersection1") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_decomposeFailSelfIntersection1() } }
    test("Bayazit_decomposeFailSelfIntersection2") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_decomposeFailSelfIntersection2() } }
    test("Bayazit_decomposeFailSelfIntersection3") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_decomposeFailSelfIntersection3() } }
    test("Bayazit_decomposeFailSelfIntersection4") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_decomposeFailSelfIntersection4() } }
    test("Bayazit_decomposeFailSelfIntersection5") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_decomposeFailSelfIntersection5() } }
    test("Bayazit_decomposeFailSelfIntersection6") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_decomposeFailSelfIntersection6() } }
    test("Bayazit_decomposeFailureDegenerateGusAsf") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_decomposeFailureDegenerateGusAsf() } }
    test("Bayazit_nsoftTriangulateFailure") { UpstreamDecompositionCoverageTestFixture().run { Bayazit_nsoftTriangulateFailure() } }
    test("EarClipping_lessThan4Vertices") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_lessThan4Vertices() } }
    test("EarClipping_nullVertex") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_nullVertex() } }
    test("EarClipping_coincidentVertex") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_coincidentVertex() } }
    test("EarClipping_success1") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_success1() } }
    test("EarClipping_triangulateSuccess1") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_triangulateSuccess1() } }
    test("EarClipping_success2") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_success2() } }
    test("EarClipping_triangulateSuccess2") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_triangulateSuccess2() } }
    test("EarClipping_success3") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_success3() } }
    test("EarClipping_triangulateSuccess3") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_triangulateSuccess3() } }
    test("EarClipping_success4") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_success4() } }
    test("EarClipping_triangulateSuccess4") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_triangulateSuccess4() } }
    test("EarClipping_success5") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_success5() } }
    test("EarClipping_triangulateSuccess5") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_triangulateSuccess5() } }
    test("EarClipping_successBird") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_successBird() } }
    test("EarClipping_triangulateSuccessBird") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_triangulateSuccessBird() } }
    test("EarClipping_successTank") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_successTank() } }
    test("EarClipping_triangulateSuccessTank") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_triangulateSuccessTank() } }
    test("EarClipping_successNazcaMonkey") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_successNazcaMonkey() } }
    test("EarClipping_triangulateSuccessNazcaMonkey") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_triangulateSuccessNazcaMonkey() } }
    test("EarClipping_successNazcaHeron") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_successNazcaHeron() } }
    test("EarClipping_triangulateSuccessNazcaHeron") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_triangulateSuccessNazcaHeron() } }
    test("EarClipping_successZoom1") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_successZoom1() } }
    test("EarClipping_triangulateSuccessZoom1") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_triangulateSuccessZoom1() } }
    test("EarClipping_successZoom2") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_successZoom2() } }
    test("EarClipping_triangulateSuccessZoom2") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_triangulateSuccessZoom2() } }
    test("EarClipping_successZoom3") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_successZoom3() } }
    test("EarClipping_triangulateSuccessZoom3") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_triangulateSuccessZoom3() } }
    test("EarClipping_successZoom4") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_successZoom4() } }
    test("EarClipping_triangulateSuccessZoom4") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_triangulateSuccessZoom4() } }
    test("EarClipping_successZoom5") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_successZoom5() } }
    test("EarClipping_triangulateSuccessZoom5") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_triangulateSuccessZoom5() } }
    test("EarClipping_successZoom6") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_successZoom6() } }
    test("EarClipping_triangulateSuccessZoom6") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_triangulateSuccessZoom6() } }
    test("EarClipping_successZoom7") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_successZoom7() } }
    test("EarClipping_triangulateSuccessZoom7") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_triangulateSuccessZoom7() } }
    test("EarClipping_successTridol1") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_successTridol1() } }
    test("EarClipping_triangulateSuccessTridol1") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_triangulateSuccessTridol1() } }
    test("EarClipping_successTridol2") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_successTridol2() } }
    test("EarClipping_triangulateSuccessTridol2") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_triangulateSuccessTridol2() } }
    test("EarClipping_successTridol3") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_successTridol3() } }
    test("EarClipping_triangulateSuccessTridol3") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_triangulateSuccessTridol3() } }
    test("EarClipping_triangulateFailSelfIntersection1") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_triangulateFailSelfIntersection1() } }
    test("EarClipping_triangulateFailSelfIntersection2") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_triangulateFailSelfIntersection2() } }
    test("EarClipping_triangulateFailSelfIntersection3") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_triangulateFailSelfIntersection3() } }
    test("EarClipping_triangulateFailSelfIntersection4") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_triangulateFailSelfIntersection4() } }
    test("EarClipping_triangulateFailSelfIntersection5") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_triangulateFailSelfIntersection5() } }
    test("EarClipping_triangulateFailSelfIntersection6") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_triangulateFailSelfIntersection6() } }
    test("EarClipping_triangulateFailureDegenerateGusAsf") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_triangulateFailureDegenerateGusAsf() } }
    test("EarClipping_nsoftTriangulateFailure") { UpstreamDecompositionCoverageTestFixture().run { EarClipping_nsoftTriangulateFailure() } }
    test("SweepLine_lessThan4Vertices") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_lessThan4Vertices() } }
    test("SweepLine_nullVertex") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_nullVertex() } }
    test("SweepLine_coincidentVertex") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_coincidentVertex() } }
    test("SweepLine_success1") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_success1() } }
    test("SweepLine_triangulateSuccess1") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_triangulateSuccess1() } }
    test("SweepLine_success2") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_success2() } }
    test("SweepLine_triangulateSuccess2") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_triangulateSuccess2() } }
    test("SweepLine_success3") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_success3() } }
    test("SweepLine_triangulateSuccess3") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_triangulateSuccess3() } }
    test("SweepLine_success4") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_success4() } }
    test("SweepLine_triangulateSuccess4") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_triangulateSuccess4() } }
    test("SweepLine_success5") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_success5() } }
    test("SweepLine_triangulateSuccess5") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_triangulateSuccess5() } }
    test("SweepLine_successBird") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_successBird() } }
    test("SweepLine_triangulateSuccessBird") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_triangulateSuccessBird() } }
    test("SweepLine_successTank") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_successTank() } }
    test("SweepLine_triangulateSuccessTank") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_triangulateSuccessTank() } }
    test("SweepLine_successNazcaMonkey") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_successNazcaMonkey() } }
    test("SweepLine_triangulateSuccessNazcaMonkey") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_triangulateSuccessNazcaMonkey() } }
    test("SweepLine_successNazcaHeron") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_successNazcaHeron() } }
    test("SweepLine_triangulateSuccessNazcaHeron") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_triangulateSuccessNazcaHeron() } }
    test("SweepLine_successZoom1") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_successZoom1() } }
    test("SweepLine_triangulateSuccessZoom1") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_triangulateSuccessZoom1() } }
    test("SweepLine_successZoom2") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_successZoom2() } }
    test("SweepLine_triangulateSuccessZoom2") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_triangulateSuccessZoom2() } }
    test("SweepLine_successZoom3") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_successZoom3() } }
    test("SweepLine_triangulateSuccessZoom3") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_triangulateSuccessZoom3() } }
    test("SweepLine_successZoom4") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_successZoom4() } }
    test("SweepLine_triangulateSuccessZoom4") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_triangulateSuccessZoom4() } }
    test("SweepLine_successZoom5") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_successZoom5() } }
    test("SweepLine_triangulateSuccessZoom5") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_triangulateSuccessZoom5() } }
    test("SweepLine_successZoom6") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_successZoom6() } }
    test("SweepLine_triangulateSuccessZoom6") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_triangulateSuccessZoom6() } }
    test("SweepLine_successZoom7") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_successZoom7() } }
    test("SweepLine_triangulateSuccessZoom7") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_triangulateSuccessZoom7() } }
    test("SweepLine_successTridol1") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_successTridol1() } }
    test("SweepLine_triangulateSuccessTridol1") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_triangulateSuccessTridol1() } }
    test("SweepLine_successTridol2") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_successTridol2() } }
    test("SweepLine_triangulateSuccessTridol2") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_triangulateSuccessTridol2() } }
    test("SweepLine_successTridol3") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_successTridol3() } }
    test("SweepLine_triangulateSuccessTridol3") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_triangulateSuccessTridol3() } }
    test("SweepLine_triangulateFailSelfIntersection1") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_triangulateFailSelfIntersection1() } }
    test("SweepLine_triangulateFailSelfIntersection2") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_triangulateFailSelfIntersection2() } }
    test("SweepLine_triangulateFailSelfIntersection3") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_triangulateFailSelfIntersection3() } }
    test("SweepLine_triangulateFailSelfIntersection4") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_triangulateFailSelfIntersection4() } }
    test("SweepLine_triangulateFailSelfIntersection5") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_triangulateFailSelfIntersection5() } }
    test("SweepLine_triangulateFailSelfIntersection6") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_triangulateFailSelfIntersection6() } }
    test("SweepLine_triangulateFailureDegenerateGusAsf") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_triangulateFailureDegenerateGusAsf() } }
    test("SweepLine_nsoftTriangulateFailure") { UpstreamDecompositionCoverageTestFixture().run { SweepLine_nsoftTriangulateFailure() } }
}

private fun decomposePoints(id: String): Array<out Vector2?> = when (id) {
    "array1" -> arrayOf(
        Vector2(2.0, 0.5),
        Vector2(1.0, 1.0),
        Vector2(-0.25, 0.25),
        Vector2(-0.75, 1.5),
        Vector2(-1.0, 2.0),
        Vector2(-1.0, 0.0),
        Vector2(-0.5, -0.75),
        Vector2(0.25, -0.4),
        Vector2(1.0, 0.3),
        Vector2(0.25, -0.5)
    )
    "array2" -> arrayOf(
        Vector2(-0.07792188619765694, 0.10364292899125216),
        Vector2(0.1, -0.2),
        Vector2(0.15, 0.0),
        Vector2(0.2, 0.07),
        Vector2(0.21037640391727175, 0.06289919008100842),
        Vector2(0.3079072605141815, -0.20863138522549773)
    )
    "array3" -> arrayOf(
        Vector2(-0.07792188619765694, 0.10364292899125216),
        Vector2(0.2412466770151972, -0.3145214553981004),
        Vector2(0.21037640391727175, 0.06289919008100842),
        Vector2(0.3079072605141815, -0.20863138522549773)
    )
    "array4" -> arrayOf(
        Vector2(-0.07792188619765694, 0.10364292899125216),
        Vector2(0.1, -0.2),
        Vector2(0.2412466770151972, -0.3145214553981004),
        Vector2(0.21037640391727175, 0.06289919008100842),
        Vector2(0.3079072605141815, -0.20863138522549773)
    )
    "array5" -> arrayOf(
        Vector2(-0.22574647794211955, 0.3562272754868271),
        Vector2(-0.24724056392833493, -0.06552204150010887),
        Vector2(0.2551995234048088, -0.4678431592201415),
        Vector2(-0.11272047497863902, -0.40936273068655504)
    )
    "array6" -> arrayOf(
        Vector2(0.187521000630546, -0.2171227524343904),
        Vector2(-0.05418163781638374, -0.4552384293706746),
        Vector2(-0.12615265827683775, 0.08842525905551823),
        Vector2(-0.4197343412893181, -0.45293439849558936)
    )
    "array7" -> arrayOf(
        Vector2(0.1595990921676319, 0.20158036631684495),
        Vector2(0.3627243978540108, -0.2125801642934565),
        Vector2(0.4972213824759445, -0.2197501458724339),
        Vector2(-0.17530050402164232, -0.10202036313267437)
    )
    "array8" -> arrayOf(
        Vector2(70.5, 360.0),
        Vector2(70.947212, 360.89444),
        Vector2(71.394424, 361.78884899999997),
        Vector2(71.158356, 361.316711),
        Vector2(70.71114299999999, 360.422302)
    )
    "short" -> arrayOfNulls<Vector2>(3)
    "nullVertex" -> arrayOf(Vector2(1.0, 2.0), Vector2(-1.0, 2.0), null, Vector2(-1.0, 0.5), Vector2(0.5, -1.0))
    "coincidentVertex" -> arrayOf(Vector2(1.0, 2.0), Vector2(-1.0, 2.0), Vector2(-1.0, 2.0), Vector2(-1.0, 0.5), Vector2(0.5, -1.0))
    else -> PolygonFixtures.load(id)
}

private class UpstreamDecompositionCoverageTestFixture  {
    private fun area(points: Array<out Vector2?>): Double {
        var twice = 0.0
        for (i in points.indices) {
            val first = points[i]!!
            val second = points[(i + 1) % points.size]!!
            twice += first.x * second.y - second.x * first.y
        }
        return twice / 2.0
    }

    private fun check(kind: String, operation: String, fixture: String, expected: String) {
        val points = decomposePoints(fixture)
        val algorithm: Decomposer = when (kind) {
            "Bayazit" -> Bayazit()
            "EarClipping" -> EarClipping()
            "SweepLine" -> SweepLine()
            else -> error(kind)
        }
        fun execute(): List<Convex> = if (operation == "triangulate") {
            (algorithm as Triangulator).triangulate(*points)
        } else {
            algorithm.decompose(*points)
        }
        when (expected) {
            "IllegalArgumentException" -> assertFailsWith<IllegalArgumentException> { execute() }
            "NullPointerException" -> assertFailsWith<NullPointerException> { execute() }
            else -> {
                val result = execute()
                assertTrue(result.isNotEmpty())
                val originalArea = abs(area(points))
                var combinedArea = 0.0
                for (piece in result) {
                    assertTrue(piece is Wound)
                    val vertices = piece.getVertices()
                    Polygon(*vertices)
                    val pieceArea = area(vertices)
                    assertTrue(
                        pieceArea >= -max(1.0e-9, originalArea * 1.0e-12),
                        "$kind/$operation/$fixture piece area $pieceArea"
                    )
                    combinedArea += pieceArea
                }
                if (fixture != "nsoft1") {
                    assertEquals(originalArea, combinedArea, max(1.0e-7, originalArea * 1.0e-7))
                }
                when (expected) {
                    "Equals" -> assertEquals(points.size - 2, result.size)
                    "True" -> assertTrue(result.size <= points.size - 2)
                    else -> error("Missing upstream assertion: $kind/$operation/$fixture")
                }
            }
        }
    }
fun Bayazit_lessThan4Vertices() = check("Bayazit", "decompose", "short", "IllegalArgumentException")
fun Bayazit_nullVertex() = check("Bayazit", "decompose", "nullVertex", "NullPointerException")
fun Bayazit_coincidentVertex() = check("Bayazit", "decompose", "coincidentVertex", "IllegalArgumentException")
fun Bayazit_success1() = check("Bayazit", "decompose", "array1", "True")
fun Bayazit_success2() = check("Bayazit", "decompose", "polygon1", "True")
fun Bayazit_success3() = check("Bayazit", "decompose", "polygon2", "True")
fun Bayazit_success4() = check("Bayazit", "decompose", "polygon3", "True")
fun Bayazit_success5() = check("Bayazit", "decompose", "polygon4", "True")
fun Bayazit_successBird() = check("Bayazit", "decompose", "bird", "True")
fun Bayazit_successTank() = check("Bayazit", "decompose", "tank", "True")
fun Bayazit_successNazcaMonkey() = check("Bayazit", "decompose", "nazca_monkey", "True")
fun Bayazit_successNazcaHeron() = check("Bayazit", "decompose", "nazca_heron", "True")
fun Bayazit_successZoom1() = check("Bayazit", "decompose", "zoom1", "True")
fun Bayazit_successZoom2() = check("Bayazit", "decompose", "zoom2", "True")
fun Bayazit_successZoom3() = check("Bayazit", "decompose", "zoom3", "True")
fun Bayazit_successZoom4() = check("Bayazit", "decompose", "zoom4", "True")
fun Bayazit_successZoom5() = check("Bayazit", "decompose", "zoom5", "True")
fun Bayazit_successZoom6() = check("Bayazit", "decompose", "zoom6", "True")
fun Bayazit_successZoom7() = check("Bayazit", "decompose", "zoom7", "True")
fun Bayazit_successTridol1() = check("Bayazit", "decompose", "tridol1", "True")
fun Bayazit_successTridol2() = check("Bayazit", "decompose", "tridol2", "True")
fun Bayazit_successTridol3() = check("Bayazit", "decompose", "tridol3", "True")
fun Bayazit_decomposeFailSelfIntersection1() = check("Bayazit", "decompose", "array2", "IllegalArgumentException")
fun Bayazit_decomposeFailSelfIntersection2() = check("Bayazit", "decompose", "array3", "IllegalArgumentException")
fun Bayazit_decomposeFailSelfIntersection3() = check("Bayazit", "decompose", "array4", "IllegalArgumentException")
fun Bayazit_decomposeFailSelfIntersection4() = check("Bayazit", "decompose", "array5", "IllegalArgumentException")
fun Bayazit_decomposeFailSelfIntersection5() = check("Bayazit", "decompose", "array6", "IllegalArgumentException")
fun Bayazit_decomposeFailSelfIntersection6() = check("Bayazit", "decompose", "array7", "IllegalArgumentException")
fun Bayazit_decomposeFailureDegenerateGusAsf() = check("Bayazit", "decompose", "array8", "IllegalArgumentException")
fun Bayazit_nsoftTriangulateFailure() = check("Bayazit", "decompose", "nsoft1", "True")
fun EarClipping_lessThan4Vertices() = check("EarClipping", "decompose", "short", "IllegalArgumentException")
fun EarClipping_nullVertex() = check("EarClipping", "decompose", "nullVertex", "NullPointerException")
fun EarClipping_coincidentVertex() = check("EarClipping", "decompose", "coincidentVertex", "IllegalArgumentException")
fun EarClipping_success1() = check("EarClipping", "decompose", "array1", "True")
fun EarClipping_triangulateSuccess1() = check("EarClipping", "triangulate", "array1", "Equals")
fun EarClipping_success2() = check("EarClipping", "decompose", "polygon1", "True")
fun EarClipping_triangulateSuccess2() = check("EarClipping", "triangulate", "polygon1", "Equals")
fun EarClipping_success3() = check("EarClipping", "decompose", "polygon2", "True")
fun EarClipping_triangulateSuccess3() = check("EarClipping", "triangulate", "polygon2", "Equals")
fun EarClipping_success4() = check("EarClipping", "decompose", "polygon3", "True")
fun EarClipping_triangulateSuccess4() = check("EarClipping", "triangulate", "polygon3", "Equals")
fun EarClipping_success5() = check("EarClipping", "decompose", "polygon4", "True")
fun EarClipping_triangulateSuccess5() = check("EarClipping", "triangulate", "polygon4", "Equals")
fun EarClipping_successBird() = check("EarClipping", "decompose", "bird", "True")
fun EarClipping_triangulateSuccessBird() = check("EarClipping", "triangulate", "bird", "Equals")
fun EarClipping_successTank() = check("EarClipping", "decompose", "tank", "True")
fun EarClipping_triangulateSuccessTank() = check("EarClipping", "triangulate", "tank", "Equals")
fun EarClipping_successNazcaMonkey() = check("EarClipping", "decompose", "nazca_monkey", "True")
fun EarClipping_triangulateSuccessNazcaMonkey() = check("EarClipping", "triangulate", "nazca_monkey", "Equals")
fun EarClipping_successNazcaHeron() = check("EarClipping", "decompose", "nazca_heron", "True")
fun EarClipping_triangulateSuccessNazcaHeron() = check("EarClipping", "triangulate", "nazca_heron", "Equals")
fun EarClipping_successZoom1() = check("EarClipping", "decompose", "zoom1", "True")
fun EarClipping_triangulateSuccessZoom1() = check("EarClipping", "triangulate", "zoom1", "Equals")
fun EarClipping_successZoom2() = check("EarClipping", "decompose", "zoom2", "True")
fun EarClipping_triangulateSuccessZoom2() = check("EarClipping", "triangulate", "zoom2", "Equals")
fun EarClipping_successZoom3() = check("EarClipping", "decompose", "zoom3", "True")
fun EarClipping_triangulateSuccessZoom3() = check("EarClipping", "triangulate", "zoom3", "Equals")
fun EarClipping_successZoom4() = check("EarClipping", "decompose", "zoom4", "True")
fun EarClipping_triangulateSuccessZoom4() = check("EarClipping", "triangulate", "zoom4", "Equals")
fun EarClipping_successZoom5() = check("EarClipping", "decompose", "zoom5", "True")
fun EarClipping_triangulateSuccessZoom5() = check("EarClipping", "triangulate", "zoom5", "Equals")
fun EarClipping_successZoom6() = check("EarClipping", "decompose", "zoom6", "True")
fun EarClipping_triangulateSuccessZoom6() = check("EarClipping", "triangulate", "zoom6", "Equals")
fun EarClipping_successZoom7() = check("EarClipping", "decompose", "zoom7", "True")
fun EarClipping_triangulateSuccessZoom7() = check("EarClipping", "triangulate", "zoom7", "Equals")
fun EarClipping_successTridol1() = check("EarClipping", "decompose", "tridol1", "True")
fun EarClipping_triangulateSuccessTridol1() = check("EarClipping", "triangulate", "tridol1", "Equals")
fun EarClipping_successTridol2() = check("EarClipping", "decompose", "tridol2", "True")
fun EarClipping_triangulateSuccessTridol2() = check("EarClipping", "triangulate", "tridol2", "Equals")
fun EarClipping_successTridol3() = check("EarClipping", "decompose", "tridol3", "True")
fun EarClipping_triangulateSuccessTridol3() = check("EarClipping", "triangulate", "tridol3", "Equals")
fun EarClipping_triangulateFailSelfIntersection1() = check("EarClipping", "triangulate", "array2", "IllegalArgumentException")
fun EarClipping_triangulateFailSelfIntersection2() = check("EarClipping", "triangulate", "array3", "IllegalArgumentException")
fun EarClipping_triangulateFailSelfIntersection3() = check("EarClipping", "triangulate", "array4", "IllegalArgumentException")
fun EarClipping_triangulateFailSelfIntersection4() = check("EarClipping", "triangulate", "array5", "IllegalArgumentException")
fun EarClipping_triangulateFailSelfIntersection5() = check("EarClipping", "triangulate", "array6", "IllegalArgumentException")
fun EarClipping_triangulateFailSelfIntersection6() = check("EarClipping", "triangulate", "array7", "IllegalArgumentException")
fun EarClipping_triangulateFailureDegenerateGusAsf() = check("EarClipping", "triangulate", "array8", "IllegalArgumentException")
fun EarClipping_nsoftTriangulateFailure() = check("EarClipping", "triangulate", "nsoft1", "Equals")
fun SweepLine_lessThan4Vertices() = check("SweepLine", "decompose", "short", "IllegalArgumentException")
fun SweepLine_nullVertex() = check("SweepLine", "decompose", "nullVertex", "NullPointerException")
fun SweepLine_coincidentVertex() = check("SweepLine", "decompose", "coincidentVertex", "IllegalArgumentException")
fun SweepLine_success1() = check("SweepLine", "triangulate", "array1", "True")
fun SweepLine_triangulateSuccess1() = check("SweepLine", "triangulate", "array1", "Equals")
fun SweepLine_success2() = check("SweepLine", "decompose", "polygon1", "True")
fun SweepLine_triangulateSuccess2() = check("SweepLine", "triangulate", "polygon1", "Equals")
fun SweepLine_success3() = check("SweepLine", "decompose", "polygon2", "True")
fun SweepLine_triangulateSuccess3() = check("SweepLine", "triangulate", "polygon2", "Equals")
fun SweepLine_success4() = check("SweepLine", "decompose", "polygon3", "True")
fun SweepLine_triangulateSuccess4() = check("SweepLine", "triangulate", "polygon3", "Equals")
fun SweepLine_success5() = check("SweepLine", "decompose", "polygon4", "True")
fun SweepLine_triangulateSuccess5() = check("SweepLine", "triangulate", "polygon4", "Equals")
fun SweepLine_successBird() = check("SweepLine", "decompose", "bird", "True")
fun SweepLine_triangulateSuccessBird() = check("SweepLine", "triangulate", "bird", "Equals")
fun SweepLine_successTank() = check("SweepLine", "decompose", "tank", "True")
fun SweepLine_triangulateSuccessTank() = check("SweepLine", "triangulate", "tank", "Equals")
fun SweepLine_successNazcaMonkey() = check("SweepLine", "decompose", "nazca_monkey", "True")
fun SweepLine_triangulateSuccessNazcaMonkey() = check("SweepLine", "triangulate", "nazca_monkey", "Equals")
fun SweepLine_successNazcaHeron() = check("SweepLine", "decompose", "nazca_heron", "True")
fun SweepLine_triangulateSuccessNazcaHeron() = check("SweepLine", "triangulate", "nazca_heron", "Equals")
fun SweepLine_successZoom1() = check("SweepLine", "decompose", "zoom1", "True")
fun SweepLine_triangulateSuccessZoom1() = check("SweepLine", "triangulate", "zoom1", "Equals")
fun SweepLine_successZoom2() = check("SweepLine", "decompose", "zoom2", "True")
fun SweepLine_triangulateSuccessZoom2() = check("SweepLine", "triangulate", "zoom2", "Equals")
fun SweepLine_successZoom3() = check("SweepLine", "decompose", "zoom3", "True")
fun SweepLine_triangulateSuccessZoom3() = check("SweepLine", "triangulate", "zoom3", "Equals")
fun SweepLine_successZoom4() = check("SweepLine", "decompose", "zoom4", "True")
fun SweepLine_triangulateSuccessZoom4() = check("SweepLine", "triangulate", "zoom4", "Equals")
fun SweepLine_successZoom5() = check("SweepLine", "decompose", "zoom5", "True")
fun SweepLine_triangulateSuccessZoom5() = check("SweepLine", "triangulate", "zoom5", "Equals")
fun SweepLine_successZoom6() = check("SweepLine", "decompose", "zoom6", "True")
fun SweepLine_triangulateSuccessZoom6() = check("SweepLine", "triangulate", "zoom6", "Equals")
fun SweepLine_successZoom7() = check("SweepLine", "decompose", "zoom7", "True")
fun SweepLine_triangulateSuccessZoom7() = check("SweepLine", "triangulate", "zoom7", "Equals")
fun SweepLine_successTridol1() = check("SweepLine", "decompose", "tridol1", "True")
fun SweepLine_triangulateSuccessTridol1() = check("SweepLine", "triangulate", "tridol1", "Equals")
fun SweepLine_successTridol2() = check("SweepLine", "decompose", "tridol2", "True")
fun SweepLine_triangulateSuccessTridol2() = check("SweepLine", "triangulate", "tridol2", "Equals")
fun SweepLine_successTridol3() = check("SweepLine", "decompose", "tridol3", "True")
fun SweepLine_triangulateSuccessTridol3() = check("SweepLine", "triangulate", "tridol3", "Equals")
fun SweepLine_triangulateFailSelfIntersection1() = check("SweepLine", "triangulate", "array2", "IllegalArgumentException")
fun SweepLine_triangulateFailSelfIntersection2() = check("SweepLine", "triangulate", "array3", "IllegalArgumentException")
fun SweepLine_triangulateFailSelfIntersection3() = check("SweepLine", "triangulate", "array4", "IllegalArgumentException")
fun SweepLine_triangulateFailSelfIntersection4() = check("SweepLine", "triangulate", "array5", "IllegalArgumentException")
fun SweepLine_triangulateFailSelfIntersection5() = check("SweepLine", "triangulate", "array6", "IllegalArgumentException")
fun SweepLine_triangulateFailSelfIntersection6() = check("SweepLine", "triangulate", "array7", "IllegalArgumentException")
fun SweepLine_triangulateFailureDegenerateGusAsf() = check("SweepLine", "triangulate", "array8", "IllegalArgumentException")
fun SweepLine_nsoftTriangulateFailure() = check("SweepLine", "triangulate", "nsoft1", "Equals")
}
