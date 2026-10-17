/*
 * Copyright (c) 2010-2021 William Bittle  http://www.dyn4j.org/
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

import org.dyn4j.geometry.Vector2
import org.dyn4j.geometry.simplify.*
import kotlin.test.*

private fun simplifyPoints(id: String): Array<out Vector2?> = when (id) {
    "array1" -> arrayOf(null, Vector2(), null)
    "array2" -> arrayOf(null, Vector2(), Vector2(), Vector2(1.0, 1.0), null)
    "array3" -> arrayOf(null, Vector2(1.1, 0.0), Vector2(1.1, 0.0), Vector2(1.2, 0.0), Vector2(1.25, 0.0), Vector2(1.4, 0.0), Vector2(1.4, 0.0), Vector2(1.7, 0.0), null)
    "array4" -> arrayOf(null, null, null)
    "array5" -> arrayOf(Vector2(1.1, 0.0), Vector2(1.11, 0.0), Vector2(1.12, 0.0), Vector2(1.13, 0.0), Vector2(1.14, 0.0))
    "array6" -> arrayOf(Vector2(-2.058, -3.576), Vector2(1.066, -3.422), Vector2(0.626, -1.816), Vector2(0.758, -1.09), Vector2(1.946, -0.87), Vector2(3.134, -1.992), Vector2(0.802, -1.838), Vector2(1.11, -2.674), Vector2(3.442, -3.246), Vector2(2.364, -6.81), Vector2(-3.092, -5.05))
    else -> PolygonFixtures.load(id)
}

class UpstreamSimplificationCoverageTest {
    private fun create(kind: String, first: Double, second: Double): Simplifier = when (kind) {
        "DouglasPeucker" -> DouglasPeucker(first, second)
        "Visvalingam" -> Visvalingam(first, second)
        "VertexClusterReduction" -> VertexClusterReduction(first)
        else -> error(kind)
    }

    private fun check(kind: String, first: Double, second: Double, scenario: String, expected: Int) {
        if (scenario == "invalid") {
            assertFailsWith<IllegalArgumentException> { create(kind, first, second) }
            return
        }
        val simplifier = create(kind, first, second)
        if (scenario == "nullList") {
            assertNull(simplifier.simplify(null as List<Vector2?>?))
            return
        }
        if (scenario == "emptyList") {
            val points = mutableListOf<Vector2?>()
            val output = assertNotNull(simplifier.simplify(points))
            assertEquals(0, output.size)
            assertTrue(points === output)
            points.add(Vector2(1.0, 2.0))
            assertSame(points[0], output[0])
            return
        }
        val points = if (scenario == "emptyArray") emptyArray<Vector2?>() else simplifyPoints(scenario)
        val original = points.toList()
        val output = assertNotNull(simplifier.simplify(*points))
        assertEquals(if (expected < 0) points.size else expected, output.size)
        for (i in points.indices) assertSame(original[i], points[i])
        for (point in output) assertTrue(points.any { it === point })
    }
    @Test fun DouglasPeucker_createInvalidTolerance() = check("DouglasPeucker", -1.0, 0.0, "invalid", 0)
    @Test fun DouglasPeucker_createInvalidEpsilon() = check("DouglasPeucker", 0.0, -1.0, "invalid", 0)
    @Test fun DouglasPeucker_createInvalidBoth() = check("DouglasPeucker", -1.0, -1.0, "invalid", 0)
    @Test fun DouglasPeucker_noChange() = check("DouglasPeucker", 0.0, 0.0, "bird", -1)
    @Test fun DouglasPeucker_emptyArray() = check("DouglasPeucker", 0.0, 0.0, "emptyArray", 0)
    @Test fun DouglasPeucker_emptyList() = check("DouglasPeucker", 0.0, 0.0, "emptyList", 0)
    @Test fun DouglasPeucker_nullList() = check("DouglasPeucker", 0.0, 0.0, "nullList", 0)
    @Test fun DouglasPeucker_nullElements() = check("DouglasPeucker", 0.0, 0.0, "array1", 1)
    @Test fun DouglasPeucker_coincidentElements() = check("DouglasPeucker", 0.0, 0.0, "array2", 2)
    @Test fun DouglasPeucker_closeElements() = check("DouglasPeucker", 0.11, 0.1, "array3", 2)
    @Test fun DouglasPeucker_allNull() = check("DouglasPeucker", 0.0, 0.0, "array4", 0)
    @Test fun DouglasPeucker_allSamePoints() = check("DouglasPeucker", 0.0, 1.0, "array5", 2)
    @Test fun DouglasPeucker_successBird() = check("DouglasPeucker", 0.5, 0.5, "bird", 38)
    @Test fun DouglasPeucker_successTank() = check("DouglasPeucker", 10.0, 10.0, "tank", 21)
    @Test fun DouglasPeucker_successSelfIntersection() = check("DouglasPeucker", 2.0, 1.0, "array6", 6)
    @Test fun DouglasPeucker_successNazcaMonkey() = check("DouglasPeucker", 0.5, 0.5, "nazca_monkey", 304)
    @Test fun DouglasPeucker_successNazcaHeron() = check("DouglasPeucker", 0.5, 0.5, "nazca_heron", 115)
    @Test fun DouglasPeucker_successZoom1() = check("DouglasPeucker", 0.5, 0.5, "zoom1", 41)
    @Test fun DouglasPeucker_successZoom2() = check("DouglasPeucker", 0.5, 0.5, "zoom2", 47)
    @Test fun DouglasPeucker_successZoom3() = check("DouglasPeucker", 0.5, 0.5, "zoom3", 37)
    @Test fun DouglasPeucker_successZoom4() = check("DouglasPeucker", 0.5, 0.5, "zoom4", 28)
    @Test fun DouglasPeucker_successZoom5() = check("DouglasPeucker", 0.5, 0.5, "zoom5", 35)
    @Test fun DouglasPeucker_successZoom6() = check("DouglasPeucker", 0.5, 0.5, "zoom6", 42)
    @Test fun DouglasPeucker_successZoom7() = check("DouglasPeucker", 0.5, 0.5, "zoom7", 22)
    @Test fun DouglasPeucker_successTridol1() = check("DouglasPeucker", 1.5, 0.5, "tridol1", 18)
    @Test fun DouglasPeucker_successTridol2() = check("DouglasPeucker", 1.5, 0.5, "tridol2", 11)
    @Test fun DouglasPeucker_successTridol3() = check("DouglasPeucker", 1.5, 0.5, "tridol3", 17)
    @Test fun DouglasPeucker_successNsoft1() = check("DouglasPeucker", 0.1, 0.1, "nsoft1", 11)
    @Test fun VertexClusterReduction_createInvalidTolerance() = check("VertexClusterReduction", -1.0, 0.0, "invalid", 0)
    @Test fun VertexClusterReduction_noChange() = check("VertexClusterReduction", 0.0, 0.0, "bird", -1)
    @Test fun VertexClusterReduction_nullList() = check("VertexClusterReduction", 0.0, 0.0, "nullList", 0)
    @Test fun VertexClusterReduction_emptyArray() = check("VertexClusterReduction", 0.0, 0.0, "emptyArray", 0)
    @Test fun VertexClusterReduction_emptyList() = check("VertexClusterReduction", 0.0, 0.0, "emptyList", 0)
    @Test fun VertexClusterReduction_nullElements() = check("VertexClusterReduction", 0.0, 0.0, "array1", 1)
    @Test fun VertexClusterReduction_coincidentElements() = check("VertexClusterReduction", 0.0, 0.0, "array2", 2)
    @Test fun VertexClusterReduction_allNull() = check("VertexClusterReduction", 0.1, 0.0, "array4", 0)
    @Test fun VertexClusterReduction_allSamePoints() = check("VertexClusterReduction", 0.1, 0.0, "array5", 1)
    @Test fun VertexClusterReduction_closeElements() = check("VertexClusterReduction", 0.11, 0.0, "array3", 4)
    @Test fun VertexClusterReduction_successBird() = check("VertexClusterReduction", 1.0, 0.0, "bird", 88)
    @Test fun VertexClusterReduction_successTank() = check("VertexClusterReduction", 10.0, 0.0, "tank", 41)
    @Test fun VertexClusterReduction_successSelfIntersection() = check("VertexClusterReduction", 2.0, 0.0, "array6", 8)
    @Test fun VertexClusterReduction_successNazcaMonkey() = check("VertexClusterReduction", 0.5, 0.0, "nazca_monkey", 1197)
    @Test fun VertexClusterReduction_successNazcaHeron() = check("VertexClusterReduction", 0.5, 0.0, "nazca_heron", 950)
    @Test fun VertexClusterReduction_successZoom1() = check("VertexClusterReduction", 0.5, 0.0, "zoom1", 66)
    @Test fun VertexClusterReduction_successZoom2() = check("VertexClusterReduction", 0.5, 0.0, "zoom2", 62)
    @Test fun VertexClusterReduction_successZoom3() = check("VertexClusterReduction", 0.5, 0.0, "zoom3", 59)
    @Test fun VertexClusterReduction_successZoom4() = check("VertexClusterReduction", 0.5, 0.0, "zoom4", 40)
    @Test fun VertexClusterReduction_successZoom5() = check("VertexClusterReduction", 0.5, 0.0, "zoom5", 58)
    @Test fun VertexClusterReduction_successZoom6() = check("VertexClusterReduction", 0.5, 0.0, "zoom6", 78)
    @Test fun VertexClusterReduction_successZoom7() = check("VertexClusterReduction", 0.5, 0.0, "zoom7", 22)
    @Test fun VertexClusterReduction_successTridol1() = check("VertexClusterReduction", 1.5, 0.0, "tridol1", 18)
    @Test fun VertexClusterReduction_successTridol2() = check("VertexClusterReduction", 1.5, 0.0, "tridol2", 11)
    @Test fun VertexClusterReduction_successTridol3() = check("VertexClusterReduction", 1.5, 0.0, "tridol3", 18)
    @Test fun VertexClusterReduction_successNsoft1() = check("VertexClusterReduction", 0.1, 0.0, "nsoft1", 78)
    @Test fun Visvalingam_createInvalidTolerance() = check("Visvalingam", -1.0, 0.0, "invalid", 0)
    @Test fun Visvalingam_createInvalidEpsilon() = check("Visvalingam", 0.0, -1.0, "invalid", 0)
    @Test fun Visvalingam_createInvalidBoth() = check("Visvalingam", -1.0, -1.0, "invalid", 0)
    @Test fun Visvalingam_noChange() = check("Visvalingam", 0.0, 0.0, "bird", -1)
    @Test fun Visvalingam_nullList() = check("Visvalingam", 0.0, 0.0, "nullList", 0)
    @Test fun Visvalingam_emptyArray() = check("Visvalingam", 0.0, 0.0, "emptyArray", 0)
    @Test fun Visvalingam_emptyList() = check("Visvalingam", 0.0, 0.0, "emptyList", 0)
    @Test fun Visvalingam_nullElements() = check("Visvalingam", 0.0, 0.0, "array1", 1)
    @Test fun Visvalingam_coincidentElements() = check("Visvalingam", 0.0, 0.0, "array2", 2)
    @Test fun Visvalingam_closeElements() = check("Visvalingam", 0.11, 0.1, "array3", 0)
    @Test fun Visvalingam_allNull() = check("Visvalingam", 0.0, 0.0, "array4", 0)
    @Test fun Visvalingam_allSamePoints() = check("Visvalingam", 0.0, 1.0, "array5", 0)
    @Test fun Visvalingam_successBird() = check("Visvalingam", 0.1, 0.5, "bird", 35)
    @Test fun Visvalingam_successTank() = check("Visvalingam", 10.0, 10.0, "tank", 40)
    @Test fun Visvalingam_successSelfIntersection() = check("Visvalingam", 2.0, 1.0, "array6", 6)
    @Test fun Visvalingam_successNazcaMonkey() = check("Visvalingam", 0.5, 0.5, "nazca_monkey", 446)
    @Test fun Visvalingam_successNazcaHeron() = check("Visvalingam", 0.5, 0.5, "nazca_heron", 198)
    @Test fun Visvalingam_successZoom1() = check("Visvalingam", 0.5, 0.5, "zoom1", 46)
    @Test fun Visvalingam_successZoom2() = check("Visvalingam", 0.5, 0.5, "zoom2", 46)
    @Test fun Visvalingam_successZoom3() = check("Visvalingam", 0.5, 0.5, "zoom3", 46)
    @Test fun Visvalingam_successZoom4() = check("Visvalingam", 0.5, 0.5, "zoom4", 30)
    @Test fun Visvalingam_successZoom5() = check("Visvalingam", 0.5, 0.5, "zoom5", 45)
    @Test fun Visvalingam_successZoom6() = check("Visvalingam", 0.5, 0.5, "zoom6", 59)
    @Test fun Visvalingam_successZoom7() = check("Visvalingam", 0.5, 0.5, "zoom7", 21)
    @Test fun Visvalingam_successTridol1() = check("Visvalingam", 1.5, 0.5, "tridol1", 18)
    @Test fun Visvalingam_successTridol2() = check("Visvalingam", 1.5, 0.5, "tridol2", 11)
    @Test fun Visvalingam_successTridol3() = check("Visvalingam", 1.5, 0.5, "tridol3", 18)
    @Test fun Visvalingam_successNsoft1() = check("Visvalingam", 0.1, 0.1, "nsoft1", 9)
}
