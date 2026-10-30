/*
 * Copyright (c) 2010-2024 William Bittle  http://www.dyn4j.org/
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
package org.dyn4j.coverage.collision.detection.narrowphase

import de.infix.testBalloon.framework.core.testSuite
import kotlin.math.PI
import kotlin.test.*
import org.dyn4j.collision.narrowphase.*
import org.dyn4j.geometry.*

val GjkCoverageTest by testSuite {
    test("createGetSet") { GjkCoverageTestFixture().run { createGetSet() } }
    test("createWithNullMinkowskiPenetrationSolver") { GjkCoverageTestFixture().run { createWithNullMinkowskiPenetrationSolver() } }
    test("nullMinkowskiPenetrationSolver") { GjkCoverageTestFixture().run { nullMinkowskiPenetrationSolver() } }
    test("setZeroDetectEpsilon") { GjkCoverageTestFixture().run { setZeroDetectEpsilon() } }
    test("setNegativeDetectEpsilon") { GjkCoverageTestFixture().run { setNegativeDetectEpsilon() } }
    test("setZeroDistanceEpsilon") { GjkCoverageTestFixture().run { setZeroDistanceEpsilon() } }
    test("setNegativeDistanceEpsilon") { GjkCoverageTestFixture().run { setNegativeDistanceEpsilon() } }
    test("setZeroRaycastEpsilon") { GjkCoverageTestFixture().run { setZeroRaycastEpsilon() } }
    test("setNegativeRaycastEpsilon") { GjkCoverageTestFixture().run { setNegativeRaycastEpsilon() } }
    test("setTooLowDetectMaxIterations") { GjkCoverageTestFixture().run { setTooLowDetectMaxIterations() } }
    test("setZeroDetectMaxIterations") { GjkCoverageTestFixture().run { setZeroDetectMaxIterations() } }
    test("setNegativeDetectMaxIterations") { GjkCoverageTestFixture().run { setNegativeDetectMaxIterations() } }
    test("setTooLowDistanceMaxIterations") { GjkCoverageTestFixture().run { setTooLowDistanceMaxIterations() } }
    test("setZeroDistanceMaxIterations") { GjkCoverageTestFixture().run { setZeroDistanceMaxIterations() } }
    test("setNegativeDistanceMaxIterations") { GjkCoverageTestFixture().run { setNegativeDistanceMaxIterations() } }
    test("setTooLowRaycastMaxIterations") { GjkCoverageTestFixture().run { setTooLowRaycastMaxIterations() } }
    test("setZeroRaycastMaxIterations") { GjkCoverageTestFixture().run { setZeroRaycastMaxIterations() } }
    test("setNegativeRaycastMaxIterations") { GjkCoverageTestFixture().run { setNegativeRaycastMaxIterations() } }
    test("raycastRectangle") { GjkCoverageTestFixture().run { raycastRectangle() } }
    test("raycastPolygon") { GjkCoverageTestFixture().run { raycastPolygon() } }
    test("raycastTriangle") { GjkCoverageTestFixture().run { raycastTriangle() } }
    test("raycastCircle") { GjkCoverageTestFixture().run { raycastCircle() } }
    test("raycastEllipse") { GjkCoverageTestFixture().run { raycastEllipse() } }
    test("raycastHalfEllipse") { GjkCoverageTestFixture().run { raycastHalfEllipse() } }
    test("raycastSlice") { GjkCoverageTestFixture().run { raycastSlice() } }
    test("raycastCapsule") { GjkCoverageTestFixture().run { raycastCapsule() } }
    test("raycastSegment") { GjkCoverageTestFixture().run { raycastSegment() } }
    test("raycastParallelSegment") { GjkCoverageTestFixture().run { raycastParallelSegment() } }
}

private class GjkCoverageTestFixture  {
fun createGetSet() {
        var gjk = Gjk()
        assertTrue(gjk.getMinkowskiPenetrationSolver() is Epa)
        assertEquals(Gjk.DEFAULT_DETECT_EPSILON, gjk.getDetectEpsilon())
        assertEquals(Gjk.DEFAULT_DISTANCE_EPSILON, gjk.getDistanceEpsilon())
        assertEquals(Gjk.DEFAULT_RAYCAST_EPSILON, gjk.getRaycastEpsilon())
        assertEquals(Gjk.DEFAULT_MAX_ITERATIONS, gjk.getMaxDetectIterations())
        assertEquals(Gjk.DEFAULT_MAX_ITERATIONS, gjk.getMaxDistanceIterations())
        assertEquals(Gjk.DEFAULT_MAX_ITERATIONS, gjk.getMaxRaycastIterations())
        val epa = Epa()
        gjk.setMinkowskiPenetrationSolver(epa)
        gjk.setDetectEpsilon(0.1); gjk.setDistanceEpsilon(0.2); gjk.setRaycastEpsilon(0.3)
        gjk.setMaxDetectIterations(6); gjk.setMaxDistanceIterations(7); gjk.setMaxRaycastIterations(8)
        assertSame(epa, gjk.getMinkowskiPenetrationSolver())
        assertEquals(0.1, gjk.getDetectEpsilon()); assertEquals(0.2, gjk.getDistanceEpsilon())
        assertEquals(0.3, gjk.getRaycastEpsilon()); assertEquals(6, gjk.getMaxDetectIterations())
        assertEquals(7, gjk.getMaxDistanceIterations()); assertEquals(8, gjk.getMaxRaycastIterations())
        gjk = Gjk(epa); assertSame(epa, gjk.getMinkowskiPenetrationSolver())
    }
fun createWithNullMinkowskiPenetrationSolver() { assertFailsWith<NullPointerException> { Gjk(null) } }
fun nullMinkowskiPenetrationSolver() { assertFailsWith<NullPointerException> { Gjk().setMinkowskiPenetrationSolver(null) } }
fun setZeroDetectEpsilon() { val gjk = Gjk(); gjk.setDetectEpsilon(0.0); assertEquals(0.0, gjk.getDetectEpsilon()) }
fun setNegativeDetectEpsilon() { assertFailsWith<IllegalArgumentException> { Gjk().setDetectEpsilon(-0.1) } }
fun setZeroDistanceEpsilon() { assertFailsWith<IllegalArgumentException> { Gjk().setDistanceEpsilon(0.0) } }
fun setNegativeDistanceEpsilon() { assertFailsWith<IllegalArgumentException> { Gjk().setDistanceEpsilon(-0.1) } }
fun setZeroRaycastEpsilon() { assertFailsWith<IllegalArgumentException> { Gjk().setRaycastEpsilon(0.0) } }
fun setNegativeRaycastEpsilon() { assertFailsWith<IllegalArgumentException> { Gjk().setRaycastEpsilon(-0.1) } }
fun setTooLowDetectMaxIterations() { assertFailsWith<IllegalArgumentException> { Gjk().setMaxDetectIterations(4) } }
fun setZeroDetectMaxIterations() { assertFailsWith<IllegalArgumentException> { Gjk().setMaxDetectIterations(0) } }
fun setNegativeDetectMaxIterations() { assertFailsWith<IllegalArgumentException> { Gjk().setMaxDetectIterations(-5) } }
fun setTooLowDistanceMaxIterations() { assertFailsWith<IllegalArgumentException> { Gjk().setMaxDistanceIterations(4) } }
fun setZeroDistanceMaxIterations() { assertFailsWith<IllegalArgumentException> { Gjk().setMaxDistanceIterations(0) } }
fun setNegativeDistanceMaxIterations() { assertFailsWith<IllegalArgumentException> { Gjk().setMaxDistanceIterations(-5) } }
fun setTooLowRaycastMaxIterations() { assertFailsWith<IllegalArgumentException> { Gjk().setMaxRaycastIterations(4) } }
fun setZeroRaycastMaxIterations() { assertFailsWith<IllegalArgumentException> { Gjk().setMaxRaycastIterations(0) } }
fun setNegativeRaycastMaxIterations() { assertFailsWith<IllegalArgumentException> { Gjk().setMaxRaycastIterations(-5) } }

    private fun raycast(
        shape: Convex, direction: Vector2, translateX: Double, translateY: Double,
        x: Double, y: Double, nx: Double, ny: Double, distance: Double,
        tooShort: Double, longEnough: Double, missDirection: Vector2
    ) {
        val ray = Ray(direction); val transform = Transform(); transform.translate(translateX, translateY)
        val cast = Raycast(); val gjk = Gjk()
        assertTrue(gjk.raycast(ray, 0.0, shape, transform, cast))
        assertEquals(x, cast.getPoint().x, 1e-3); assertEquals(y, cast.getPoint().y, 1e-3)
        assertEquals(nx, cast.getNormal().x, 1e-3); assertEquals(ny, cast.getNormal().y, 1e-3)
        assertEquals(distance, cast.getDistance(), 1e-3)
        cast.clear()
        assertFalse(gjk.raycast(ray, tooShort, shape, transform, cast))
        assertTrue(gjk.raycast(ray, longEnough, shape, transform, cast))
        ray.getDirectionVector().negate()
        assertFalse(gjk.raycast(ray, 0.0, shape, transform, cast))
        ray.getDirectionVector().set(missDirection)
        assertFalse(gjk.raycast(ray, 0.0, shape, transform, cast))
        ray.getStart().set(transform.getTransformed(shape.getCenter()))
        assertFalse(gjk.raycast(ray, 0.0, shape, transform, cast))
    }
    private fun unit(x: Double, y: Double) = Vector2(x, y).also { it.normalize() }
fun raycastRectangle() = raycast(Geometry.createRectangle(1.0, 1.0), Vector2(1.0, 0.0), 2.0, 0.0, 1.500, 0.000, -1.000, 0.000, 1.500, 1.4, 1.6, Vector2(1.0, 1.0))
fun raycastPolygon() = raycast(Geometry.createUnitCirclePolygon(5, 1.0), unit(1.0, 1.0), 2.0, 1.0, 1.190, 1.190, -1.000, 0.000, 1.684, 1.4, 1.7, Vector2(1.0, 2.0))
fun raycastTriangle() = raycast(Geometry.createEquilateralTriangle(1.0), unit(2.0, 1.0), 2.0, 1.0, 1.458, 0.729, -0.866, 0.500, 1.631, 1.4, 1.7, Vector2(1.0, 2.0))
fun raycastCircle() {
        val circle = Geometry.createCircle(0.5)
        raycast(circle, Vector2(2.0, 1.0), 2.0, 0.5, 1.599, 0.799, -0.800, 0.599, 1.788, 1.7, 1.8, Vector2(1.0, 2.0))
        val ray = Ray(Vector2(1.0, 1.0)); val transform = Transform(); transform.translate(2.0, 0.5)
        val cast = Raycast(); val gjk = Gjk()
        assertFalse(gjk.raycast(ray, 0.0, circle, transform, cast))
        ray.setDirection(Vector2(1.0, 0.5))
        assertFalse(gjk.raycast(ray, 1.0, circle, transform, cast))
        assertTrue(gjk.raycast(ray, 0.0, circle, transform, cast))
        ray.setStart(Vector2(2.0, -1.0)); ray.setDirection(Vector2(0.0, 1.0))
        assertTrue(gjk.raycast(ray, 0.0, circle, transform, cast))
    }
fun raycastEllipse() = raycast(Ellipse(1.0, 0.5), unit(2.0, 1.0), 2.1, 1.0, 1.699, 0.849, -0.548, -0.836, 1.900, 1.7, 1.95, Vector2(1.0, 2.0))
fun raycastHalfEllipse() = raycast(HalfEllipse(0.8, 0.25), Vector2(130.0 * PI / 180.0), -1.0, 0.8, -0.671, 0.800, 0.000, -1.000, 1.044, 0.7, 1.2, Vector2(120.0 * PI / 180.0))
fun raycastSlice() = raycast(Slice(0.5, 60.0 * PI / 180.0), Vector2(-30.0 * PI / 180.0), 1.0, -0.8, 1.192, -0.688, -0.500, 0.866, 1.377, 1.3, 1.5, Vector2(-45.0 * PI / 180.0))
fun raycastCapsule() = raycast(Capsule(1.0, 0.5), Vector2(-130.0 * PI / 180.0), -1.0, -0.8, -0.547, -0.652, 0.816, 0.577, 0.852, 0.7, 0.9, Vector2(-115.0 * PI / 180.0))
fun raycastSegment() = raycast(Geometry.createHorizontalSegment(1.0), unit(2.0, 1.0), 2.0, 1.0, 2.000, 1.000, 0.000, -1.000, 2.236, 2.2, 2.4, Vector2(1.0, 2.0))
fun raycastParallelSegment() {
        val segment = Geometry.createHorizontalSegment(1.0); val transform = Transform(); transform.translate(2.0, 0.0)
        val ray = Ray(Vector2(1.0, 0.0)); val cast = Raycast(); val gjk = Gjk()
        assertTrue(gjk.raycast(ray, 0.0, segment, transform, cast))
        assertEquals(1.500, cast.getPoint().x, 1e-3); assertEquals(0.000, cast.getPoint().y, 1e-3)
        assertEquals(-1.000, cast.getNormal().x, 1e-3); assertEquals(0.000, cast.getNormal().y, 1e-3)
        assertEquals(1.500, cast.getDistance(), 1e-3); cast.clear()
        assertFalse(gjk.raycast(ray, 1.4, segment, transform, cast)); assertTrue(gjk.raycast(ray, 2.0, segment, transform, cast))
        ray.getDirectionVector().negate(); assertFalse(gjk.raycast(ray, 0.0, segment, transform, cast))
        ray.getStart().set(Vector2(0.0, 1.0)); assertFalse(gjk.raycast(ray, 0.0, segment, transform, cast))
        ray.getStart().set(transform.getTransformed(segment.getCenter()))
        assertFalse(gjk.raycast(ray, 0.0, segment, transform, cast))
    }
}
