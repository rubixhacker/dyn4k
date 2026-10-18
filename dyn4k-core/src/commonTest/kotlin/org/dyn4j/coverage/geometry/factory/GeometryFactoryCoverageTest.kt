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

package org.dyn4j.coverage.geometry.factory

import org.dyn4j.geometry.*
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.sin
import kotlin.test.*

private fun radians(degrees: Double): Double = degrees * PI / 180.0

class GeometryFactoryCoverageTest {
    @Test
    fun getAverageCenterArray() {

		val vertices = arrayOfNulls<Vector2>(6)
		vertices[0] = Vector2(-2.0, 1.0)
		vertices[1] = Vector2(-1.0, 2.0)
		vertices[2] = Vector2(1.2, 0.5)
		vertices[3] = Vector2(1.3, 0.3)
		vertices[4] = Vector2(1.4, 0.2)
		vertices[5] = Vector2(0.0, -1.0)
		var c = Geometry.getAverageCenter(*vertices)
		assertEquals(0.150, c.x, 1.0e-3)
		assertEquals(0.500, c.y, 1.0e-3)
		c = Geometry.getAverageCenter(vertices[0])
		assertEquals(-2.000, c.x, 1.0e-3)
		assertEquals( 1.000, c.y, 1.0e-3)

    }
    @Test
    fun getAverageCenterList() {

		val vertices = mutableListOf<Vector2>()
		vertices.add(Vector2(-2.0, 1.0))
		vertices.add(Vector2(-1.0, 2.0))
		vertices.add(Vector2(1.2, 0.5))
		vertices.add(Vector2(1.3, 0.3))
		vertices.add(Vector2(1.4, 0.2))
		vertices.add(Vector2(0.0, -1.0))
		var c = Geometry.getAverageCenter(vertices)
		assertEquals(0.150, c.x, 1.0e-3)
		assertEquals(0.500, c.y, 1.0e-3)
		c = Geometry.getAverageCenter(vertices.subList(0, 1))
		assertEquals(-2.000, c.x, 1.0e-3)
		assertEquals( 1.000, c.y, 1.0e-3)

    }
    @Test
    fun getAverageCenterEmptyArray() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.getAverageCenter(*arrayOf<Vector2?>())

        }
    }
    @Test
    fun getAverageCenterArrayNullElements() {
        assertFailsWith<NullPointerException> {

		Geometry.getAverageCenter(*arrayOf<Vector2?>(
			Vector2(1.0, 0.0),
			null,
			Vector2(4.0, 3.0),
			Vector2(-2.0, -1.0),
			null
		))

        }
    }
    @Test
    fun getAverageCenterArrayNullOnlyElement() {
        assertFailsWith<NullPointerException> {

		Geometry.getAverageCenter(*arrayOf<Vector2?>(
			null
		))

        }
    }
    @Test
    fun getAverageCenterNullList() {
        assertFailsWith<NullPointerException> {

		Geometry.getAverageCenter(null as List<Vector2?>?)

        }
    }
    @Test
    fun getAverageCenterEmptyList() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.getAverageCenter(mutableListOf<Vector2>())

        }
    }
    @Test
    fun getAverageCenterListNullElements() {
        assertFailsWith<NullPointerException> {

		val vertices = mutableListOf<Vector2?>()
		vertices.add(Vector2(0.0, -1.0))
		vertices.add(null)
		vertices.add(Vector2(2.0, -1.0))
		vertices.add(Vector2(-3.0, -1.0))
		vertices.add(null)
		Geometry.getAverageCenter(vertices)

        }
    }
    @Test
    fun getAverageCenterListNullOnlyElement() {
        assertFailsWith<NullPointerException> {

		val vertices = mutableListOf<Vector2?>()
		vertices.add(null)
		Geometry.getAverageCenter(vertices)

        }
    }
    @Test
    fun getAreaWeightedCenter() {

		val vertices = arrayOfNulls<Vector2>(6)
		vertices[0] = Vector2(-2.0, 1.0)
		vertices[1] = Vector2(-1.0, 2.0)
		vertices[2] = Vector2(1.2, 0.5)
		vertices[3] = Vector2(1.3, 0.3)
		vertices[4] = Vector2(1.4, 0.2)
		vertices[5] = Vector2(0.0, -1.0)
		var c = Geometry.getAreaWeightedCenter(*vertices)
		assertEquals(-0.318, c.x, 1.0e-3)
		assertEquals( 0.527, c.y, 1.0e-3)
		c = Geometry.getAreaWeightedCenter(vertices.toList())
		assertEquals(-0.318, c.x, 1.0e-3)
		assertEquals( 0.527, c.y, 1.0e-3)

    }
    @Test
    fun getAreaWeightedCenterOffset() {

		val vertices = arrayOfNulls<Vector2>(6)
		vertices[0] = Vector2(-1.0, 2.0)
		vertices[1] = Vector2(0.0, 3.0)
		vertices[2] = Vector2(2.2, 1.5)
		vertices[3] = Vector2(2.3, 1.3)
		vertices[4] = Vector2(2.4, 1.2)
		vertices[5] = Vector2(1.0, 0.0)
		var c = Geometry.getAreaWeightedCenter(*vertices)
		assertEquals(0.682, c.x, 1.0e-3)
		assertEquals(1.527, c.y, 1.0e-3)
		c = Geometry.getAreaWeightedCenter(vertices.toList())
		assertEquals(0.682, c.x, 1.0e-3)
		assertEquals(1.527, c.y, 1.0e-3)

    }
    @Test
    fun getAreaWeightedCenterEmptyArray() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.getAreaWeightedCenter(*arrayOf<Vector2?>())

        }
    }
    @Test
    fun getAreaWeightedCenterArrayNullElements() {
        assertFailsWith<NullPointerException> {

		Geometry.getAreaWeightedCenter(*arrayOf<Vector2?>(
			Vector2(1.0, 0.0),
			null,
			Vector2(4.0, 3.0),
			Vector2(-2.0, -1.0),
			null
		))

        }
    }
    @Test
    fun getAreaWeightedCenterNullList() {
        assertFailsWith<NullPointerException> {

		Geometry.getAreaWeightedCenter(null as List<Vector2?>?)

        }
    }
    @Test
    fun getAreaWeightedCenterEmptyList() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.getAreaWeightedCenter(mutableListOf<Vector2>())

        }
    }
    @Test
    fun getAreaWeightedCenterListNullElements() {
        assertFailsWith<NullPointerException> {

		val vertices = mutableListOf<Vector2?>()
		vertices.add(Vector2(0.0, -1.0))
		vertices.add(null)
		vertices.add(Vector2(2.0, -1.0))
		vertices.add(Vector2(-3.0, -1.0))
		vertices.add(null)
		Geometry.getAreaWeightedCenter(vertices)

        }
    }
    @Test
    fun getAreaWeightedCenterZeroAreaList() {

		val points = mutableListOf<Vector2>()
		points.add(Vector2(2.0, 1.0))
		points.add(Vector2(2.0, 1.0))
		points.add(Vector2(2.0, 1.0))
		points.add(Vector2(2.0, 1.0))
		val c = Geometry.getAreaWeightedCenter(points)
		assertEquals(2.000, c.x, 1.0e-3)
		assertEquals(1.000, c.y, 1.0e-3)

    }
    @Test
    fun getAreaWeightedCenterZeroAreaArray() {

		val points = arrayOfNulls<Vector2>(4)
		points[0] = Vector2(2.0, 1.0)
		points[1] = Vector2(2.0, 1.0)
		points[2] = Vector2(2.0, 1.0)
		points[3] = Vector2(2.0, 1.0)
		val c = Geometry.getAreaWeightedCenter(*points)
		assertEquals(2.000, c.x, 1.0e-3)
		assertEquals(1.000, c.y, 1.0e-3)

    }
    @Test
    fun createUnitCirclePolygon() {

		var p = Geometry.createUnitCirclePolygon(5, 0.5)
		assertEquals( 0.154, p.getVertices()[4].x, 1.0e-3)
		assertEquals(-0.475, p.getVertices()[4].y, 1.0e-3)
		assertEquals(-0.404, p.getVertices()[3].x, 1.0e-3)
		assertEquals(-0.293, p.getVertices()[3].y, 1.0e-3)
		assertEquals(-0.404, p.getVertices()[2].x, 1.0e-3)
		assertEquals( 0.293, p.getVertices()[2].y, 1.0e-3)
		assertEquals( 0.154, p.getVertices()[1].x, 1.0e-3)
		assertEquals( 0.475, p.getVertices()[1].y, 1.0e-3)
		assertEquals( 0.500, p.getVertices()[0].x, 1.0e-3)
		assertEquals( 0.000, p.getVertices()[0].y, 1.0e-3)
		val v11 = p.getVertices()[0]
		p = Geometry.createUnitCirclePolygon(5, 0.5, PI / 2.0)
		assertEquals( 0.475, p.getVertices()[4].x, 1.0e-3)
		assertEquals( 0.154, p.getVertices()[4].y, 1.0e-3)
		assertEquals( 0.293, p.getVertices()[3].x, 1.0e-3)
		assertEquals(-0.404, p.getVertices()[3].y, 1.0e-3)
		assertEquals(-0.293, p.getVertices()[2].x, 1.0e-3)
		assertEquals(-0.404, p.getVertices()[2].y, 1.0e-3)
		assertEquals(-0.475, p.getVertices()[1].x, 1.0e-3)
		assertEquals( 0.154, p.getVertices()[1].y, 1.0e-3)
		assertEquals( 0.000, p.getVertices()[0].x, 1.0e-3)
		assertEquals( 0.500, p.getVertices()[0].y, 1.0e-3)
		val v21 = p.getVertices()[0]
		val angle = v11.getAngleBetween(v21)
		assertEquals(PI / 2.0, angle, 1.0e-3)

    }
    @Test
    fun createNegativeRadiusUnitCirclePolygon() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createUnitCirclePolygon(5, -0.5)

        }
    }
    @Test
    fun createZeroRadiusUnitCirclePolygon() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createUnitCirclePolygon(5, 0.0)

        }
    }
    @Test
    fun createLessThan3PointsUnitCirclePolygon() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createUnitCirclePolygon(2, 0.5)

        }
    }
    @Test
    fun createCircle() {

		Geometry.createCircle(1.0)

    }
    @Test
    fun createNegativeRadiusCircle() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createCircle(-1.0)

        }
    }
    @Test
    fun createZeroRadiusCircle() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createCircle(0.0)

        }
    }
    @Test
    fun createPolygonNullPoint() {
        assertFailsWith<NullPointerException> {

		val vertices = arrayOfNulls<Vector2>(5)
		Geometry.createPolygon(*vertices)

        }
    }
    @Test
    fun createPolygon() {

		val vertices = arrayOfNulls<Vector2>(5)
		vertices[0] = Vector2(1.0, 0.0)
		vertices[1] = Vector2(0.5, 1.0)
		vertices[2] = Vector2(-0.5, 1.0)
		vertices[3] = Vector2(-1.0, 0.0)
		vertices[4] = Vector2(0.0, -1.0)
		val p = Geometry.createPolygon(*vertices)
		assertFalse(p.getVertices() === vertices)
		for (i in 0 until 5) {
			assertFalse(p.getVertices()[0] === vertices[0])
		}
		val copied = p.getVertices()
		val expectedX = doubleArrayOf(1.0, 0.5, -0.5, -1.0, 0.0)
		val expectedY = doubleArrayOf(0.0, 1.0, 1.0, 0.0, -1.0)
		for (i in vertices.indices) {
			assertNotSame(vertices[i], copied[i])
			assertEquals(expectedX[i], copied[i].x, 1e-12)
			assertEquals(expectedY[i], copied[i].y, 1e-12)
		}
		vertices[1]!!.x = 42.0
		assertEquals(0.5, copied[1].x, 1e-12)
		copied[2].y = 42.0
		assertEquals(1.0, vertices[2]!!.y, 1e-12)

    }
    @Test
    fun createPolygonAtOrigin() {

		val vertices = arrayOfNulls<Vector2>(5)
		vertices[0] = Vector2(1.0, 0.0)
		vertices[1] = Vector2(0.5, 1.0)
		vertices[2] = Vector2(-0.5, 1.0)
		vertices[3] = Vector2(-1.0, 0.0)
		vertices[4] = Vector2(0.0, -1.0)
		val p = Geometry.createPolygonAtOrigin(*vertices)
		assertFalse(p.getVertices() === vertices)
		for (i in 0 until 5) {
			assertFalse(p.getVertices()[0] === vertices[0])
		}
		val c = p.getCenter()
		assertEquals(0.000, c.x, 1.0e-3)
		assertEquals(0.000, c.y, 1.0e-3)
		val copied = p.getVertices()
		val expectedX = doubleArrayOf(1.0, 0.5, -0.5, -1.0, 0.0)
		val expectedY = doubleArrayOf(
			-0.1333333333333334,
			0.8666666666666666,
			0.8666666666666666,
			-0.1333333333333334,
			-1.1333333333333333
		)
		for (i in vertices.indices) {
			assertNotSame(vertices[i], copied[i])
			assertEquals(expectedX[i], copied[i].x, 1e-12)
			assertEquals(expectedY[i], copied[i].y, 1e-12)
		}
		vertices[1]!!.x = 42.0
		assertEquals(0.5, copied[1].x, 1e-12)
		copied[2].y = 42.0
		assertEquals(1.0, vertices[2]!!.y, 1e-12)

    }
    @Test
    fun createZeroSizeSquare() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createSquare(0.0)

        }
    }
    @Test
    fun createNegativeSizeSquare() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createSquare(-1.0)

        }
    }
    @Test
    fun createSquare() {

		val r = Geometry.createSquare(1.0)
		assertEquals(1.000, r.getWidth(), 1.0e-3)
		assertEquals(1.000, r.getHeight(), 1.0e-3)

    }
    @Test
    fun createRectangle() {

		Geometry.createRectangle(1.0, 2.0)

    }
    @Test
    fun createNegativeWidthRectangle() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createRectangle(-1.0, 2.0)

        }
    }
    @Test
    fun createNegativeHeightRectangle() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createRectangle(1.0, -2.0)

        }
    }
    @Test
    fun createZeroWidthRectangle() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createRectangle(0.0, 2.0)

        }
    }
    @Test
    fun createZeroHeightRectangle() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createRectangle(1.0, 0.0)

        }
    }
    @Test
    fun createTriangleNullPoint() {
        assertFailsWith<NullPointerException> {

		val p1 = Vector2(1.0, 0.0)
		val p2 = Vector2(0.5, 1.0)
		Geometry.createTriangle(p1, p2, null)

        }
    }
    @Test
    fun createTriangle() {

		val p1 = Vector2(1.0, 0.0)
		val p2 = Vector2(0.5, 1.0)
		val p3 = Vector2(-0.5, 1.0)
		val t = Geometry.createTriangle(p1, p2, p3)
		assertFalse(t.getVertices()[0] === p1)
		assertFalse(t.getVertices()[1] === p2)
		assertFalse(t.getVertices()[2] === p3)

    }
    @Test
    fun createTriangleAtOrigin() {

		val p1 = Vector2(1.0, 0.0)
		val p2 = Vector2(0.5, 1.0)
		val p3 = Vector2(-0.5, 1.0)
		val t = Geometry.createTriangleAtOrigin(p1, p2, p3)
		assertFalse(t.getVertices()[0] === p1)
		assertFalse(t.getVertices()[1] === p2)
		assertFalse(t.getVertices()[2] === p3)
		val c = t.getCenter()
		assertEquals(0.000, c.x, 1.0e-3)
		assertEquals(0.000, c.y, 1.0e-3)

    }
    @Test
    fun createZeroWidthRightTriangle() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createRightTriangle(0.0, 2.0)

        }
    }
    @Test
    fun createZeroHeightRightTriangle() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createRightTriangle(1.0, 0.0)

        }
    }
    @Test
    fun createNegativeWidthRightTriangle() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createRightTriangle(-1.0, 2.0)

        }
    }
    @Test
    fun createNegativeHeightRightTriangle() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createRightTriangle(2.0, -2.0)

        }
    }
    @Test
    fun createRightTriangle() {

		val t = Geometry.createRightTriangle(1.0, 2.0)
		val center = t.getCenter()
		assertEquals(0.000, center.x, 1.0e-3)
		assertEquals(0.000, center.y, 1.0e-3)
		val v1 = t.getVertices()[0]
		val v2 = t.getVertices()[1]
		val v3 = t.getVertices()[2]
		val e1 = v1.to(v2)
		val e2 = v2.to(v3)
		val e3 = v3.to(v1)
		if (e1.dot(e2) < 0.00001 && e1.dot(e2) > -0.00001) {
			assertTrue(true)
			return
		}
		if (e2.dot(e3) < 0.00001 && e2.dot(e3) > -0.00001) {
			assertTrue(true)
			return
		}
		if (e3.dot(e1) < 0.00001 && e3.dot(e1) > -0.00001) {
			assertTrue(true)
			return
		}
		assertFalse(true)

    }
    @Test
    fun createRightTriangleMirror() {

		val t = Geometry.createRightTriangle(1.0, 2.0, true)
		val center = t.getCenter()
		assertEquals(0.000, center.x, 1.0e-3)
		assertEquals(0.000, center.y, 1.0e-3)
		val v1 = t.getVertices()[0]
		val v2 = t.getVertices()[1]
		val v3 = t.getVertices()[2]
		val e1 = v1.to(v2)
		val e2 = v2.to(v3)
		val e3 = v3.to(v1)
		if (e1.dot(e2) < 0.00001 && e1.dot(e2) > -0.00001) {
			assertTrue(true)
			return
		}
		if (e2.dot(e3) < 0.00001 && e2.dot(e3) > -0.00001) {
			assertTrue(true)
			return
		}
		if (e3.dot(e1) < 0.00001 && e3.dot(e1) > -0.00001) {
			assertTrue(true)
			return
		}
		assertFalse(true)

    }
    @Test
    fun createZeroHeightEquilateralTriangle() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createEquilateralTriangle(0.0)

        }
    }
    @Test
    fun createNegativeHeightEquilateralTriangle() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createEquilateralTriangle(-1.0)

        }
    }
    @Test
    fun createEquilateralTriangle() {

		val t = Geometry.createEquilateralTriangle(2.0)
		val center = t.getCenter()
		assertEquals(0.000, center.x, 1.0e-3)
		assertEquals(0.000, center.y, 1.0e-3)
		var previousA = t.getVertices()[0].getAngleBetween(t.getVertices()[1])
		previousA = abs(PI - abs(previousA))
		val previousD = t.getVertices()[0].distance(t.getVertices()[1])
		for (i in 1 until 3) {
			val v1 = t.getVertices()[i]
			val v2 = t.getVertices()[if (i + 1 == 3) 0 else i + 1]
			var angle = v1.getAngleBetween(v2)
			angle = abs(PI - abs(angle))
			if (angle < previousA * 0.9999 || angle > previousA * 1.0001) {
				assertFalse(true)
			}
			val distance = v1.distance(v2)
			if (distance < previousD * 0.9999 || distance > previousD * 1.0001) {
				assertFalse(true)
			}
		}
		assertTrue(true)

    }
    @Test
    fun createZeroWidthIsoscelesTriangle() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createIsoscelesTriangle(0.0, 1.0)

        }
    }
    @Test
    fun createZeroHeightIsoscelesTriangle() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createIsoscelesTriangle(1.0, 0.0)

        }
    }
    @Test
    fun createNegativeWidthIsoscelesTriangle() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createIsoscelesTriangle(-1.0, 2.0)

        }
    }
    @Test
    fun createNegativeHeightIsoscelesTriangle() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createIsoscelesTriangle(2.0, -2.0)

        }
    }
    @Test
    fun createIsoscelesTriangle() {

		val t = Geometry.createIsoscelesTriangle(2.0, 1.0)
		val center = t.getCenter()
		assertEquals(0.000, center.x, 1.0e-3)
		assertEquals(0.000, center.y, 1.0e-3)
		val v1 = t.getVertices()[0]
		val v2 = t.getVertices()[1]
		val v3 = t.getVertices()[2]
		val e1 = v1.to(v2)
		val e2 = v2.to(v3)
		val e3 = v3.to(v1)
		assertEquals(e1.getMagnitude(), e3.getMagnitude(), 1.0e-3)
		assertEquals(e1.getAngleBetween(e2), e2.getAngleBetween(e3), 1.0e-3)

    }
    @Test
    fun createSegmentNullPoint1() {
        assertFailsWith<NullPointerException> {

		Geometry.createSegment(null, Vector2())

        }
    }
    @Test
    fun createSegmentNullPoint2() {
        assertFailsWith<NullPointerException> {

		Geometry.createSegment(Vector2(), null)

        }
    }
    @Test
    fun createSegment() {

		Geometry.createSegment(Vector2(1.0, 1.0), Vector2(2.0, -1.0))

    }
    @Test
    fun createSegmentAtOrigin() {

		val s = Geometry.createSegmentAtOrigin(Vector2(1.0, 1.0), Vector2(2.0, -1.0))
		val center = s.getCenter()
		assertEquals(0.000, center.x, 1.0e-3)
		assertEquals(0.000, center.y, 1.0e-3)

    }
    @Test
    fun createSegmentEnd() {

		Geometry.createSegment(Vector2(1.0, 1.0))

    }
    @Test
    fun createZeroLengthHorizontalSegment() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createHorizontalSegment(0.0)

        }
    }
    @Test
    fun createNegativeLengthHorizontalSegment() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createHorizontalSegment(-1.0)

        }
    }
    @Test
    fun createHorizontalSegment() {

		val s = Geometry.createHorizontalSegment(5.0)
		val center = s.getCenter()
		assertEquals(0.000, center.x, 1.0e-3)
		assertEquals(0.000, center.y, 1.0e-3)

    }
    @Test
    fun createZeroLengthVerticalSegment() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createVerticalSegment(0.0)

        }
    }
    @Test
    fun createNegativeLengthVerticalSegment() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createVerticalSegment(-1.0)

        }
    }
    @Test
    fun createVerticalSegment() {

		val s = Geometry.createVerticalSegment(5.0)
		val center = s.getCenter()
		assertEquals(0.000, center.x, 1.0e-3)
		assertEquals(0.000, center.y, 1.0e-3)

    }
    @Test
    fun getWindingList() {

		val points = mutableListOf<Vector2>()
		points.add(Vector2(-1.0, -1.0))
		points.add(Vector2(1.0, -1.0))
		points.add(Vector2(1.0, 1.0))
		points.add(Vector2(-1.0, 1.0))
		assertTrue(Geometry.getWinding(points) > 0)
		points.reverse()
		assertTrue(Geometry.getWinding(points) < 0)

    }
    @Test
    fun getWindingNullList() {
        assertFailsWith<NullPointerException> {

		Geometry.getWinding(null as List<Vector2?>?)

        }
    }
    @Test
    fun getWindingListLessThan2Points() {
        assertFailsWith<IllegalArgumentException> {

		val points = mutableListOf<Vector2>()
		points.add(Vector2())
		Geometry.getWinding(points)

        }
    }
    @Test
    fun getWindingListNullPoint() {
        assertFailsWith<NullPointerException> {

		val points = mutableListOf<Vector2?>()
		points.add(Vector2())
		points.add(null)
		points.add(null)
		Geometry.getWinding(points)

        }
    }
    @Test
    fun getWindingArray() {

		val points = arrayOfNulls<Vector2>(4)
		points[0] = Vector2(-1.0, -1.0)
		points[1] = Vector2(1.0, -1.0)
		points[2] = Vector2(1.0, 1.0)
		points[3] = Vector2(-1.0, 1.0)
		assertTrue(Geometry.getWinding(*points) > 0)
		var p = points[0]
		points[0] = points[3]
		points[3] = p
		p = points[1]
		points[1] = points[2]
		points[2] = p
		assertTrue(Geometry.getWinding(*points) < 0)

    }
    @Test
    fun getWindingArrayLessThan2Points() {
        assertFailsWith<IllegalArgumentException> {

		val points = arrayOfNulls<Vector2>(1)
		points[0] = Vector2(-1.0, -1.0)
		Geometry.getWinding(*points)

        }
    }
    @Test
    fun getWindingArrayNullPoint() {
        assertFailsWith<NullPointerException> {

		val points = arrayOfNulls<Vector2>(4)
		points[0] = Vector2(-1.0, -1.0)
		points[1] = null
		points[2] = null
		points[3] = null
		Geometry.getWinding(*points)

        }
    }
    @Test
    fun reverseWindingNullList() {
        assertFailsWith<NullPointerException> {

		Geometry.reverseWinding(null as MutableList<Vector2?>?)

        }
    }
    @Test
    fun reverseWindingEmptyOrOneElement() {

		var array = arrayOf<Vector2?>()
		Geometry.reverseWinding(*array)
		array = arrayOf<Vector2?>(
			Vector2(1.0, 1.0)
		)
		Geometry.reverseWinding(*array)
        val list = mutableListOf<Vector2?>()
		Geometry.reverseWinding(list)
		list.add(Vector2(1.0, 1.0))
		Geometry.reverseWinding(list)

    }
    @Test
    fun cleanseNullList() {
        assertFailsWith<NullPointerException> {

		Geometry.cleanse(null as List<Vector2?>?)

        }
    }
    @Test
    fun cleanseListWithNullElements() {
        assertFailsWith<NullPointerException> {

		val list = mutableListOf<Vector2?>()
		list.add(Vector2())
		list.add(null)
		list.add(Vector2())
		list.add(Vector2())
		Geometry.cleanse(list)

        }
    }
    @Test
    fun cleanseArrayWithNullElements() {
        assertFailsWith<NullPointerException> {

		val array = arrayOfNulls<Vector2>(5)
		array[0] = Vector2()
		array[3] = Vector2()
		array[4] = Vector2()
		Geometry.cleanse(*array)

        }
    }
    @Test
    fun cleanseEmpty() {

		val points = mutableListOf<Vector2>()
		val result1 = Geometry.cleanse(points)
		val result2 = Geometry.cleanse(*arrayOf<Vector2?>())
		assertEquals(0, result1.size)
		assertEquals(0, result2.size)

    }
    @Test
    fun cleanseList() {

		val points = mutableListOf<Vector2>()
		points.add(Vector2(1.0, 0.0))
		points.add(Vector2(1.0, 0.0))
		points.add(Vector2(0.5, -0.5))
		points.add(Vector2(0.0, -0.5))
		points.add(Vector2(-0.5, -0.5))
		points.add(Vector2(-2.0, -0.5))
		points.add(Vector2(2.1, 0.5))
		points.add(Vector2(1.0, 0.0))
		var result = Geometry.cleanse(points)
		assertTrue(Geometry.getWinding(result) > 0.0)
		assertEquals(4, result.size)
	    points.reverse()
		result = Geometry.cleanse(points)
		assertTrue(Geometry.getWinding(result) > 0.0)
		assertEquals(4, result.size)

    }
    @Test
    fun cleanseArray() {

		var points = arrayOfNulls<Vector2>(8)
		points[0] = Vector2(1.0, 0.0)
		points[1] = Vector2(1.0, 0.0)
		points[2] = Vector2(0.5, -0.5)
		points[3] = Vector2(0.0, -0.5)
		points[4] = Vector2(-0.5, -0.5)
		points[5] = Vector2(-2.0, -0.5)
		points[6] = Vector2(2.1, 0.5)
		points[7] = Vector2(1.0, 0.0)
		var result = Geometry.cleanse(*points)
		assertTrue(Geometry.getWinding(*result) > 0.0)
		assertEquals(4, result.size)
		val pts = points.toMutableList()
		pts.reverse()
		points = pts.toTypedArray()
		result = Geometry.cleanse(*points)
		assertTrue(Geometry.getWinding(*result) > 0.0)
		assertEquals(4, result.size)

    }
    @Test
    fun createEllipse() {

		val e = Geometry.createEllipse(1.0, 0.5)
		assertEquals(1.0, e.getWidth())
		assertEquals(0.5, e.getHeight())
		assertEquals(0.000, e.getCenter().x, 1.0e-3)
		assertEquals(0.000, e.getCenter().y, 1.0e-3)

    }
    @Test
    fun createHalfEllipse() {

		val e = Geometry.createHalfEllipse(1.0, 0.5)
		assertEquals(1.0, e.getWidth())
		assertEquals(0.5, e.getHeight())
		assertEquals(0.000, e.getCenter().x, 1.0e-3)
		assertEquals(0.212, e.getCenter().y, 1.0e-3)

    }
    @Test
    fun createHalfEllipseAtOrigin() {

		val e = Geometry.createHalfEllipseAtOrigin(1.0, 0.5)
		assertEquals(1.0, e.getWidth())
		assertEquals(0.5, e.getHeight())
		assertEquals(0.000, e.getCenter().x, 1.0e-3)
		assertEquals(0.000, e.getCenter().y, 1.0e-3)

    }
    @Test
    fun createPolygonalEllipse() {

		val p = Geometry.createPolygonalEllipse(10, 2.0, 1.0)
		assertEquals(0.000, p.getCenter().x, 1.0e-3)
		assertEquals(0.000, p.getCenter().y, 1.0e-3)

    }
    @Test
    fun createPolygonalEllipseOddCount() {

		var p = Geometry.createPolygonalEllipse(5, 2.0, 1.0)
		assertEquals(4, p.getVertices().size)
		p = Geometry.createPolygonalEllipse(11, 2.0, 1.0)
		assertEquals(10, p.getVertices().size)

    }
    @Test
    fun createPolygonalEllipseLessCount() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createPolygonalEllipse(3, 2.0, 1.0)

        }
    }
    @Test
    fun createPolygonalEllipseZeroWidth() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createPolygonalEllipse(10, 0.0, 1.0)

        }
    }
    @Test
    fun createPolygonalEllipseZeroHeight() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createPolygonalEllipse(10, 2.0, 0.0)

        }
    }
    @Test
    fun createPolygonalEllipseNegativeWidth() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createPolygonalEllipse(10, -1.0, 1.0)

        }
    }
    @Test
    fun createPolygonalEllipseNegativeHeight() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createPolygonalEllipse(10, 2.0, -1.0)

        }
    }
    @Test
    fun createPolygonalSlice() {

		val p = Geometry.createPolygonalSlice(5, 1.0, radians(30.0))
		assertEquals(0.658, p.getCenter().x, 1.0e-3)
		assertEquals(0.000, p.getCenter().y, 1.0e-3)

    }
    @Test
    fun createPolygonalSliceAtOrigin() {

		val p = Geometry.createPolygonalSliceAtOrigin(5, 1.0, radians(30.0))
		assertEquals(0.000, p.getCenter().x, 1.0e-3)
		assertEquals(0.000, p.getCenter().y, 1.0e-3)

    }
    @Test
    fun createPolygonalSliceInvalidCount() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createPolygonalSlice(0, 1.0, radians(30.0))

        }
    }
    @Test
    fun createPolygonalSliceNegativeRadius() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createPolygonalSlice(5, -1.0, radians(30.0))

        }
    }
    @Test
    fun createPolygonalSliceZeroRadius() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createPolygonalSlice(5, 0.0, radians(30.0))

        }
    }
    @Test
    fun createPolygonalSliceThetaLessThanZero() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createPolygonalSlice(5, 1.0, -radians(30.0))

        }
    }
    @Test
    fun createPolygonalSliceThetaLessZero() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createPolygonalSlice(5, 1.0, 0.0)

        }
    }
    @Test
    fun createPolygonalSliceThetaGreaterThan180() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createPolygonalSlice(5, 1.0, radians(190.0))

        }
    }
    @Test
    fun createPolygonalHalfEllipse() {

		val p = Geometry.createPolygonalHalfEllipse(5, 1.0, 0.5)
		assertEquals(0.000, p.getCenter().x, 1.0e-3)
		assertEquals(0.103, p.getCenter().y, 1.0e-3)

    }
    @Test
    fun createPolygonalHalfEllipseAtOrigin() {

		val p = Geometry.createPolygonalHalfEllipseAtOrigin(5, 1.0, 0.5)
		assertEquals(0.000, p.getCenter().x, 1.0e-3)
		assertEquals(0.000, p.getCenter().y, 1.0e-3)

    }
    @Test
    fun createPolygonalHalfEllipseInvalidCount() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createPolygonalHalfEllipse(0, 1.0, 0.5)

        }
    }
    @Test
    fun createPolygonalHalfEllipseZeroWidth() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createPolygonalHalfEllipse(5, 0.0, 0.5)

        }
    }
    @Test
    fun createPolygonalHalfEllipseNegativeWidth() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createPolygonalHalfEllipse(5, -1.0, 0.5)

        }
    }
    @Test
    fun createPolygonalHalfEllipseNegativeHeight() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createPolygonalHalfEllipse(5, 1.0, -0.5)

        }
    }
    @Test
    fun createPolygonalHalfEllipseZeroHeight() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createPolygonalHalfEllipse(5, 1.0, 0.0)

        }
    }
    @Test
    fun createPolygonalCircle() {

		var p = Geometry.createPolygonalCircle(5, 1.0)
		assertEquals(0.000, p.getCenter().x, 1.0e-3)
		assertEquals(0.000, p.getCenter().y, 1.0e-3)
		assertEquals(1.000, p.getVertices()[0].x, 1.0e-3)
		assertEquals(0.000, p.getVertices()[0].y, 1.0e-3)
		assertEquals(5, p.getVertices().size)
		p = Geometry.createPolygonalCircle(5, 1.0, radians(30.0))
		assertEquals(0.000, p.getCenter().x, 1.0e-3)
		assertEquals(0.000, p.getCenter().y, 1.0e-3)
		assertEquals(cos(radians(30.0)), p.getVertices()[0].x, 1.0e-3)
		assertEquals(sin(radians(30.0)), p.getVertices()[0].y, 1.0e-3)
		assertEquals(5, p.getVertices().size)

    }
    @Test
    fun createPolygonalCircleInvalidCount() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createPolygonalCircle(2, 1.0)

        }
    }
    @Test
    fun createPolygonalCircleZeroCount() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createPolygonalCircle(0, 1.0)

        }
    }
    @Test
    fun createPolygonalCircleNegativeCount() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createPolygonalCircle(-1, 1.0)

        }
    }
    @Test
    fun createPolygonalCircleZeroRadius() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createPolygonalCircle(6, 0.0)

        }
    }
    @Test
    fun createPolygonalCircleNegativeRadius() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createPolygonalCircle(6, -1.0)

        }
    }
    @Test
    fun createPolygonalCapsule() {

		var p = Geometry.createPolygonalCapsule(5, 1.0, 0.5)
		assertEquals(0.000, p.getCenter().x, 1.0e-3)
		assertEquals(0.000, p.getCenter().y, 1.0e-3)
		p = Geometry.createPolygonalCapsule(5, 1.0, 1.0)
		assertEquals(0.000, p.getCenter().x, 1.0e-3)
		assertEquals(0.000, p.getCenter().y, 1.0e-3)
		p = Geometry.createPolygonalCapsule(5, 0.5, 1.0)
		assertEquals(0.000, p.getCenter().x, 1.0e-3)
		assertEquals(0.000, p.getCenter().y, 1.0e-3)

    }
    @Test
    fun createPolygonalCapsuleInvalidCount() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createPolygonalCapsule(0, 1.0, 0.5)

        }
    }
    @Test
    fun createPolygonalCapsuleZeroWidth() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createPolygonalCapsule(5, 0.0, 0.5)

        }
    }
    @Test
    fun createPolygonalCapsuleNegativeWidth() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createPolygonalCapsule(5, -1.0, 0.5)

        }
    }
    @Test
    fun createPolygonalCapsuleZeroHeight() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createPolygonalCapsule(5, 1.0, 0.0)

        }
    }
    @Test
    fun createPolygonalCapsuleNegativeHeight() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.createPolygonalCapsule(5, 1.0, -0.5)

        }
    }
    @Test
    fun flip() {

		val p = Geometry.createUnitCirclePolygon(5, 1.0)
		var flipped = Geometry.flip(p, Vector2(1.0, 1.0),  Vector2(0.0, 2.0))
		var vertices = flipped.getVertices()
		assertEquals(-2.951, vertices[0]!!.x, 1.0e-3)
		assertEquals( 2.309, vertices[0]!!.y, 1.0e-3)
		assertEquals(-2.587, vertices[1]!!.x, 1.0e-3)
		assertEquals( 1.190, vertices[1]!!.y, 1.0e-3)
		assertEquals(-1.412, vertices[2]!!.x, 1.0e-3)
		assertEquals( 1.190, vertices[2]!!.y, 1.0e-3)
		assertEquals(-1.048, vertices[3]!!.x, 1.0e-3)
		assertEquals( 2.309, vertices[3]!!.y, 1.0e-3)
		assertEquals(-2.000, vertices[4]!!.x, 1.0e-3)
		assertEquals( 3.000, vertices[4]!!.y, 1.0e-3)
		flipped = Geometry.flipAlongTheXAxis(p)
		vertices = flipped.getVertices()
		assertEquals( 0.309, vertices[0]!!.x, 1.0e-3)
		assertEquals( 0.951, vertices[0]!!.y, 1.0e-3)
		assertEquals(-0.809, vertices[1]!!.x, 1.0e-3)
		assertEquals( 0.587, vertices[1]!!.y, 1.0e-3)
		assertEquals(-0.809, vertices[2]!!.x, 1.0e-3)
		assertEquals(-0.587, vertices[2]!!.y, 1.0e-3)
		assertEquals( 0.309, vertices[3]!!.x, 1.0e-3)
		assertEquals(-0.951, vertices[3]!!.y, 1.0e-3)
		assertEquals( 1.000, vertices[4]!!.x, 1.0e-3)
		assertEquals( 0.000, vertices[4]!!.y, 1.0e-3)
		flipped = Geometry.flipAlongTheXAxis(p, Vector2(0.0, 1.0))
		vertices = flipped.getVertices()
		assertEquals( 0.309, vertices[0]!!.x, 1.0e-3)
		assertEquals( 2.951, vertices[0]!!.y, 1.0e-3)
		assertEquals(-0.809, vertices[1]!!.x, 1.0e-3)
		assertEquals( 2.587, vertices[1]!!.y, 1.0e-3)
		assertEquals(-0.809, vertices[2]!!.x, 1.0e-3)
		assertEquals( 1.412, vertices[2]!!.y, 1.0e-3)
		assertEquals( 0.309, vertices[3]!!.x, 1.0e-3)
		assertEquals( 1.048, vertices[3]!!.y, 1.0e-3)
		assertEquals( 1.000, vertices[4]!!.x, 1.0e-3)
		assertEquals( 2.000, vertices[4]!!.y, 1.0e-3)
		flipped = Geometry.flipAlongTheYAxis(p)
		vertices = flipped.getVertices()
		assertEquals(-0.309, vertices[0]!!.x, 1.0e-3)
		assertEquals(-0.951, vertices[0]!!.y, 1.0e-3)
		assertEquals( 0.809, vertices[1]!!.x, 1.0e-3)
		assertEquals(-0.587, vertices[1]!!.y, 1.0e-3)
		assertEquals( 0.809, vertices[2]!!.x, 1.0e-3)
		assertEquals( 0.587, vertices[2]!!.y, 1.0e-3)
		assertEquals(-0.309, vertices[3]!!.x, 1.0e-3)
		assertEquals( 0.951, vertices[3]!!.y, 1.0e-3)
		assertEquals(-1.000, vertices[4]!!.x, 1.0e-3)
		assertEquals(-0.000, vertices[4]!!.y, 1.0e-3)
		flipped = Geometry.flipAlongTheYAxis(p, Vector2(1.0, 0.0))
		vertices = flipped.getVertices()
		assertEquals( 1.690, vertices[0]!!.x, 1.0e-3)
		assertEquals(-0.951, vertices[0]!!.y, 1.0e-3)
		assertEquals( 2.809, vertices[1]!!.x, 1.0e-3)
		assertEquals(-0.587, vertices[1]!!.y, 1.0e-3)
		assertEquals( 2.809, vertices[2]!!.x, 1.0e-3)
		assertEquals( 0.587, vertices[2]!!.y, 1.0e-3)
		assertEquals( 1.690, vertices[3]!!.x, 1.0e-3)
		assertEquals( 0.951, vertices[3]!!.y, 1.0e-3)
		assertEquals( 1.000, vertices[4]!!.x, 1.0e-3)
		assertEquals(-0.000, vertices[4]!!.y, 1.0e-3)
		flipped = Geometry.flip(p, Vector2(1.0, 0.0))
		vertices = flipped.getVertices()
		assertEquals( 0.309, vertices[0]!!.x, 1.0e-3)
		assertEquals( 0.951, vertices[0]!!.y, 1.0e-3)
		assertEquals(-0.809, vertices[1]!!.x, 1.0e-3)
		assertEquals( 0.587, vertices[1]!!.y, 1.0e-3)
		assertEquals(-0.809, vertices[2]!!.x, 1.0e-3)
		assertEquals(-0.587, vertices[2]!!.y, 1.0e-3)
		assertEquals( 0.309, vertices[3]!!.x, 1.0e-3)
		assertEquals(-0.951, vertices[3]!!.y, 1.0e-3)
		assertEquals( 1.000, vertices[4]!!.x, 1.0e-3)
		assertEquals( 0.000, vertices[4]!!.y, 1.0e-3)

    }
    @Test
    fun flipNullPolygon() {
        assertFailsWith<NullPointerException> {

		Geometry.flip(null, Vector2(1.0, 1.0),  null)

        }
    }
    @Test
    fun flipNullAxis() {
        assertFailsWith<NullPointerException> {

		Geometry.flip(Geometry.createSquare(1.0), null,  null)

        }
    }
    @Test
    fun flipZeroAxis() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.flip(Geometry.createSquare(1.0), Vector2(),  null)

        }
    }
    @Test
    fun flipNullPoint() {

		Geometry.flip(Geometry.createSquare(1.0), Vector2(1.0, 1.0),  null)

    }
    @Test
    fun minkowskiSum() {

		var p = Geometry.minkowskiSum(Geometry.createUnitCirclePolygon(5, 0.5), Geometry.createCircle(0.2), 3)
		assertEquals(25, p.getVertices().size)
		p = Geometry.minkowskiSum(Geometry.createCircle(0.2), Geometry.createUnitCirclePolygon(5, 0.5), 3)
		assertEquals(25, p.getVertices().size)
		p = Geometry.minkowskiSum(Geometry.createUnitCirclePolygon(5, 0.5), 0.2, 3)
		assertEquals(25, p.getVertices().size)
		p = Geometry.minkowskiSum(Geometry.createSquare(1.0), Geometry.createUnitCirclePolygon(5, 0.2))
		assertEquals(8, p.getVertices().size)
		p = Geometry.minkowskiSum(Geometry.createSegment(Vector2(1.0, 0.0)), Geometry.createUnitCirclePolygon(5, 0.2))
		assertEquals(7, p.getVertices().size)
		p = Geometry.minkowskiSum(Geometry.createSegment(Vector2(1.0, 0.0)), Geometry.createSegment(Vector2(0.5, 0.5)))
		assertEquals(4, p.getVertices().size)
		p = Geometry.minkowskiSum(Geometry.createSquare(1.0), Geometry.createSquare(0.5))
		assertEquals(4, p.getVertices().size)
		val s = Geometry.createSquare(1.0)
		s.translate(1.0, 0.5)
		p = Geometry.minkowskiSum(s, Geometry.createSquare(0.5))
		assertEquals(4, p.getVertices().size)

    }
    @Test
    fun minkowskiSumInvalidSegments() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.minkowskiSum(Geometry.createSegment(Vector2(1.0, 0.0)), Geometry.createSegment(Vector2(-0.5, 0.0)))

        }
    }
    @Test
    fun minkowskiSumNullWound1() {
        assertFailsWith<NullPointerException> {

		Geometry.minkowskiSum(null, Geometry.createUnitCirclePolygon(5, 0.5))

        }
    }
    @Test
    fun minkowskiSumNullWound2() {
        assertFailsWith<NullPointerException> {

		Geometry.minkowskiSum(Geometry.createUnitCirclePolygon(5, 0.5), null)

        }
    }
    @Test
    fun minkowskiSumNullShape1() {
        assertFailsWith<NullPointerException> {

		Geometry.minkowskiSum(null, Geometry.createCircle(0.2), 3)

        }
    }
    @Test
    fun minkowskiSumNullShape2() {
        assertFailsWith<NullPointerException> {

		Geometry.minkowskiSum(Geometry.createUnitCirclePolygon(5, 0.5), null, 3)

        }
    }
    @Test
    fun minkowskiSumNullShape3() {
        assertFailsWith<NullPointerException> {

		Geometry.minkowskiSum(null, 0.2, 3)

        }
    }
    @Test
    fun minkowskiSumInvalidCount1() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.minkowskiSum(Geometry.createUnitCirclePolygon(5, 0.5), 0.2, 0)

        }
    }
    @Test
    fun minkowskiSumInvalidCount2() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.minkowskiSum(Geometry.createUnitCirclePolygon(5, 0.5), 0.2, -2)

        }
    }
    @Test
    fun minkowskiSumInvalidCount3() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.minkowskiSum(Geometry.createUnitCirclePolygon(5, 0.5), Geometry.createCircle(0.5), 0)

        }
    }
    @Test
    fun minkowskiSumInvalidCount4() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.minkowskiSum(Geometry.createUnitCirclePolygon(5, 0.5), Geometry.createCircle(0.5), -2)

        }
    }
    @Test
    fun minkowskiSumInvalidRadius1() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.minkowskiSum(Geometry.createUnitCirclePolygon(5, 0.5), 0.0, 3)

        }
    }
    @Test
    fun minkowskiSumInvalidRadius2() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.minkowskiSum(Geometry.createUnitCirclePolygon(5, 0.5), -2.0, 3)

        }
    }
    @Test
    fun scale() {

		var s1 = Geometry.scale(Geometry.createCircle(0.5), 2.0)
		var s2 = Geometry.scale(Geometry.createCapsule(1.0, 0.5), 2.0)
		var s3 = Geometry.scale(Geometry.createEllipse(1.0, 0.5), 2.0)
		var s4 = Geometry.scale(Geometry.createHalfEllipse(1.0, 0.25), 2.0)
		var s5 = Geometry.scale(Geometry.createSlice(0.5, radians(30.0)), 2.0)
		var s6 = Geometry.scale(Geometry.createUnitCirclePolygon(5, 0.5), 2.0)
		var s7 = Geometry.scale(Geometry.createSegment(Vector2(1.0, 0.0)), 2.0)
		assertEquals(1.000, s1.getRadius(), 1.0e-3)
		assertEquals(2.000, s2.getLength(), 1.0e-3)
		assertEquals(1.000, s2.getCapRadius() * 2.0, 1.0e-3)
		assertEquals(2.000, s3.getWidth(), 1.0e-3)
		assertEquals(1.000, s3.getHeight(), 1.0e-3)
		assertEquals(2.000, s4.getWidth(), 1.0e-3)
		assertEquals(0.500, s4.getHeight(), 1.0e-3)
		assertEquals(1.000, s5.getSliceRadius(), 1.0e-3)
		assertEquals(1.000, s6.getRadius(), 1.0e-3)
		assertEquals(2.000, s7.getLength(), 1.0e-3)
		s1 = Geometry.scale(Geometry.createCircle(0.5), 0.5)
		s2 = Geometry.scale(Geometry.createCapsule(1.0, 0.5), 0.5)
		s3 = Geometry.scale(Geometry.createEllipse(1.0, 0.5), 0.5)
		s4 = Geometry.scale(Geometry.createHalfEllipse(1.0, 0.25), 0.5)
		s5 = Geometry.scale(Geometry.createSlice(0.5, radians(30.0)), 0.5)
		s6 = Geometry.scale(Geometry.createUnitCirclePolygon(5, 0.5), 0.5)
		s7 = Geometry.scale(Geometry.createSegment(Vector2(1.0, 0.0)), 0.5)
		assertEquals(0.250, s1.getRadius(), 1.0e-3)
		assertEquals(0.500, s2.getLength(), 1.0e-3)
		assertEquals(0.250, s2.getCapRadius() * 2.0, 1.0e-3)
		assertEquals(0.500, s3.getWidth(), 1.0e-3)
		assertEquals(0.250, s3.getHeight(), 1.0e-3)
		assertEquals(0.500, s4.getWidth(), 1.0e-3)
		assertEquals(0.125, s4.getHeight(), 1.0e-3)
		assertEquals(0.250, s5.getSliceRadius(), 1.0e-3)
		assertEquals(0.250, s6.getRadius(), 1.0e-3)
		assertEquals(0.500, s7.getLength(), 1.0e-3)

    }
    @Test
    fun scaleNullCircle() {
        assertFailsWith<NullPointerException> {

		Geometry.scale(null as Circle?, 1.2)

        }
    }
    @Test
    fun scaleNullCapsule() {
        assertFailsWith<NullPointerException> {

		Geometry.scale(null as Capsule?, 1.2)

        }
    }
    @Test
    fun scaleNullEllipse() {
        assertFailsWith<NullPointerException> {

		Geometry.scale(null as Ellipse?, 1.2)

        }
    }
    @Test
    fun scaleNullHalfEllipse() {
        assertFailsWith<NullPointerException> {

		Geometry.scale(null as HalfEllipse?, 1.2)

        }
    }
    @Test
    fun scaleNullSlice() {
        assertFailsWith<NullPointerException> {

		Geometry.scale(null as Slice?, 1.2)

        }
    }
    @Test
    fun scaleNullPolygon() {
        assertFailsWith<NullPointerException> {

		Geometry.scale(null as Polygon?, 1.2)

        }
    }
    @Test
    fun scaleNullSegment() {
        assertFailsWith<NullPointerException> {

		Geometry.scale(null as Segment?, 1.2)

        }
    }
    @Test
    fun scaleCircleInvalid() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.scale(Geometry.createCircle(0.5), 0.0)

        }
    }
    @Test
    fun scaleCapsuleInvalid() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.scale(Geometry.createCapsule(1.0, 0.5), 0.0)

        }
    }
    @Test
    fun scaleEllipseInvalid() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.scale(Geometry.createEllipse(1.0, 0.5), 0.0)

        }
    }
    @Test
    fun scaleHalfEllipseInvalid() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.scale(Geometry.createHalfEllipse(1.0, 0.25), 0.0)

        }
    }
    @Test
    fun scaleSliceInvalid() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.scale(Geometry.createSlice(0.5, radians(30.0)), 0.0)

        }
    }
    @Test
    fun scalePolygonInvalid() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.scale(Geometry.createUnitCirclePolygon(5, 0.5), 0.0)

        }
    }
    @Test
    fun scaleSegmentInvalid() {
        assertFailsWith<IllegalArgumentException> {

		Geometry.scale(Geometry.createSegment(Vector2(1.0, 1.0)), 0.0)

        }
    }
    @Test
    fun createLinksWrap() {

		val a = Vector2(0.0, 0.0)
		val b = Vector2(2.4, 0.0)
		val c = Vector2(2.4, 1.6)
		val d = Vector2(0.0, 1.6)
		val links = Geometry.createLinks(listOf(a, b, c, d), true)
		assertEquals(4, links.size)
		assertEquals(links[0].getPoint1(), a)
		assertEquals(links[0].getPoint2(), b)
		assertEquals(links[1].getPoint1(), b)
		assertEquals(links[1].getPoint2(), c)
		assertEquals(links[2].getPoint1(), c)
		assertEquals(links[2].getPoint2(), d)
		assertEquals(links[3].getPoint1(), d)
		assertEquals(links[3].getPoint2(), a)

    }
    @Test
    fun createLinks() {

		val verts = mutableListOf<Vector2>()
		verts.add(Vector2(2.0, 1.5))
		verts.add(Vector2(1.0, 1.0))
		verts.add(Vector2(1.0, 0.0))
		verts.add(Vector2(0.0, 0.0))
		var links = Geometry.createLinks(verts, true)
		assertEquals(4, links.size)
		assertEquals(verts[3].x, links[0].getPoint0()!!.x)
		assertEquals(verts[3].y, links[0].getPoint0()!!.y)
		assertEquals(verts[0].x, links[0].getPoint1()!!.x)
		assertEquals(verts[0].y, links[0].getPoint1()!!.y)
		assertEquals(verts[1].x, links[0].getPoint2()!!.x)
		assertEquals(verts[1].y, links[0].getPoint2()!!.y)
		assertEquals(verts[2].x, links[0].getPoint3()!!.x)
		assertEquals(verts[2].y, links[0].getPoint3()!!.y)
		assertEquals(verts[0].x, links[1].getPoint0()!!.x)
		assertEquals(verts[0].y, links[1].getPoint0()!!.y)
		assertEquals(verts[1].x, links[1].getPoint1()!!.x)
		assertEquals(verts[1].y, links[1].getPoint1()!!.y)
		assertEquals(verts[2].x, links[1].getPoint2()!!.x)
		assertEquals(verts[2].y, links[1].getPoint2()!!.y)
		assertEquals(verts[3].x, links[1].getPoint3()!!.x)
		assertEquals(verts[3].y, links[1].getPoint3()!!.y)
		assertEquals(verts[1].x, links[2].getPoint0()!!.x)
		assertEquals(verts[1].y, links[2].getPoint0()!!.y)
		assertEquals(verts[2].x, links[2].getPoint1()!!.x)
		assertEquals(verts[2].y, links[2].getPoint1()!!.y)
		assertEquals(verts[3].x, links[2].getPoint2()!!.x)
		assertEquals(verts[3].y, links[2].getPoint2()!!.y)
		assertEquals(verts[0].x, links[2].getPoint3()!!.x)
		assertEquals(verts[0].y, links[2].getPoint3()!!.y)
		assertEquals(verts[2].x, links[3].getPoint0()!!.x)
		assertEquals(verts[2].y, links[3].getPoint0()!!.y)
		assertEquals(verts[3].x, links[3].getPoint1()!!.x)
		assertEquals(verts[3].y, links[3].getPoint1()!!.y)
		assertEquals(verts[0].x, links[3].getPoint2()!!.x)
		assertEquals(verts[0].y, links[3].getPoint2()!!.y)
		assertEquals(verts[1].x, links[3].getPoint3()!!.x)
		assertEquals(verts[1].y, links[3].getPoint3()!!.y)
		links = Geometry.createLinks(verts, false)
		assertEquals(3, links.size)
		assertEquals(null, links[0].getPoint0())
		assertEquals(verts[0].x, links[0].getPoint1()!!.x)
		assertEquals(verts[0].y, links[0].getPoint1()!!.y)
		assertEquals(verts[1].x, links[0].getPoint2()!!.x)
		assertEquals(verts[1].y, links[0].getPoint2()!!.y)
		assertEquals(verts[2].x, links[0].getPoint3()!!.x)
		assertEquals(verts[2].y, links[0].getPoint3()!!.y)
		assertEquals(verts[0].x, links[1].getPoint0()!!.x)
		assertEquals(verts[0].y, links[1].getPoint0()!!.y)
		assertEquals(verts[1].x, links[1].getPoint1()!!.x)
		assertEquals(verts[1].y, links[1].getPoint1()!!.y)
		assertEquals(verts[2].x, links[1].getPoint2()!!.x)
		assertEquals(verts[2].y, links[1].getPoint2()!!.y)
		assertEquals(verts[3].x, links[1].getPoint3()!!.x)
		assertEquals(verts[3].y, links[1].getPoint3()!!.y)
		assertEquals(verts[1].x, links[2].getPoint0()!!.x)
		assertEquals(verts[1].y, links[2].getPoint0()!!.y)
		assertEquals(verts[2].x, links[2].getPoint1()!!.x)
		assertEquals(verts[2].y, links[2].getPoint1()!!.y)
		assertEquals(verts[3].x, links[2].getPoint2()!!.x)
		assertEquals(verts[3].y, links[2].getPoint2()!!.y)
		assertEquals(null, links[2].getPoint3())

    }
    @Test
    fun createLinksNull() {
        assertFailsWith<NullPointerException> {

		Geometry.createLinks(null as Array<Vector2?>?, false)

        }
    }
    @Test
    fun createLinksOneVertex() {
        assertFailsWith<IllegalArgumentException> {

		val verts = mutableListOf<Vector2>()
		verts.add(Vector2(2.0, 1.5))
		Geometry.createLinks(verts, false)

        }
    }
    @Test
    fun createLinksNullVertex() {
        assertFailsWith<NullPointerException> {

		val verts = mutableListOf<Vector2?>()
		verts.add(Vector2(2.0, 1.5))
		verts.add(Vector2(1.0, 1.0))
		verts.add(null)
		verts.add(Vector2(3.0, 1.5))
		Geometry.createLinks(verts, false)

        }
    }
    @Test
    fun createSlice() {

		val s = Geometry.createSlice(1.0, radians(30.0))
		assertEquals(1.0, s.getSliceRadius())
		assertEquals(radians(30.0), s.getTheta())
		assertEquals(0.000, s.getCircleCenter().x)
		assertEquals(0.000, s.getCircleCenter().y)

    }
    @Test
    fun createSliceAtOrigin() {

		val s = Geometry.createSliceAtOrigin(1.0, radians(30.0))
		assertEquals(1.0, s.getSliceRadius())
		assertEquals(radians(30.0), s.getTheta())
		assertEquals(0.000, s.getCenter().x)
		assertEquals(0.000, s.getCenter().y)

    }
    @Test
    fun polygonIntersection() {

		val p1 = Polygon(
				Vector2(0.0, 0.0),
				Vector2(2.0, 1.0),
				Vector2(4.0, 3.0),
				Vector2(4.25, 4.0),
				Vector2(2.0, 5.0),
				Vector2(-2.0, 5.0),
				Vector2(-4.0, 3.75))
		val p2 = Polygon(
				Vector2(1.0, 0.0),
				Vector2(3.0, 1.0),
				Vector2(3.25, 3.75),
				Vector2(1.5, 4.75),
				Vector2(0.0, 5.25),
				Vector2(-2.5, 4.5),
				Vector2(-2.75, 3.25),
				Vector2(-2.5, 1.5))
		val tx1 = Transform()
		val tx2 = Transform()
		val result = Geometry.getIntersection(p1, tx1, p2, tx2)
		assertNotNull(result)
		assertEquals(11, result.getVertices().size)
		assertEquals(-0.842, result.getVertices()[0].x, 1e-3)
		assertEquals( 0.789, result.getVertices()[0].y, 1e-3)
		assertEquals( 0.461, result.getVertices()[1].x, 1e-3)
		assertEquals( 0.230, result.getVertices()[1].y, 1e-3)
		assertEquals( 2.000, result.getVertices()[2].x, 1e-3)
		assertEquals( 1.000, result.getVertices()[2].y, 1e-3)
		assertEquals( 3.100, result.getVertices()[3].x, 1e-3)
		assertEquals( 2.100, result.getVertices()[3].y, 1e-3)
		assertEquals( 3.250, result.getVertices()[4].x, 1e-3)
		assertEquals( 3.750, result.getVertices()[4].y, 1e-3)
		assertEquals( 1.500, result.getVertices()[5].x, 1e-3)
		assertEquals( 4.750, result.getVertices()[5].y, 1e-3)
		assertEquals( 0.750, result.getVertices()[6].x, 1e-3)
		assertEquals( 5.000, result.getVertices()[6].y, 1e-3)
		assertEquals(-0.833, result.getVertices()[7].x, 1e-3)
		assertEquals( 5.000, result.getVertices()[7].y, 1e-3)
		assertEquals(-2.500, result.getVertices()[8].x, 1e-3)
		assertEquals( 4.500, result.getVertices()[8].y, 1e-3)
		assertEquals(-2.750, result.getVertices()[9].x, 1e-3)
		assertEquals( 3.250, result.getVertices()[9].y, 1e-3)
		assertEquals(-2.639, result.getVertices()[10].x, 1e-3)
		assertEquals( 2.474, result.getVertices()[10].y, 1e-3)

    }
    @Test
    fun polygonIntersectionVertexOnEdgeA() {

		val p1 = Polygon(
				Vector2(0.0, 0.0),
				Vector2(2.0, 1.0),
				Vector2(4.0, 3.0),
				Vector2(4.25, 4.0),
				Vector2(2.0, 5.0),
				Vector2(-2.0, 5.0),
				Vector2(-2.6, 4.0))
		val p2 = Polygon(
				Vector2(1.0, 0.0),
				Vector2(3.0, 1.0),
				Vector2(3.25, 3.75),
				Vector2(1.5, 4.75),
				Vector2(0.0, 5.25),
				Vector2(-2.5, 4.5),
				Vector2(-2.75, 3.25),
				Vector2(-2.5, 1.5))
		val tx1 = Transform()
		val tx2 = Transform()
		val result = Geometry.getIntersection(p1, tx1, p2, tx2)
		assertNotNull(result)
		assertEquals(10, result.getVertices().size)
		assertEquals(-0.386, result.getVertices()[0].x, 1e-3)
		assertEquals( 0.594, result.getVertices()[0].y, 1e-3)
		assertEquals( 0.461, result.getVertices()[1].x, 1e-3)
		assertEquals( 0.230, result.getVertices()[1].y, 1e-3)
		assertEquals( 2.000, result.getVertices()[2].x, 1e-3)
		assertEquals( 1.000, result.getVertices()[2].y, 1e-3)
		assertEquals( 3.100, result.getVertices()[3].x, 1e-3)
		assertEquals( 2.100, result.getVertices()[3].y, 1e-3)
		assertEquals( 3.250, result.getVertices()[4].x, 1e-3)
		assertEquals( 3.750, result.getVertices()[4].y, 1e-3)
		assertEquals( 1.500, result.getVertices()[5].x, 1e-3)
		assertEquals( 4.750, result.getVertices()[5].y, 1e-3)
		assertEquals( 0.750, result.getVertices()[6].x, 1e-3)
		assertEquals( 5.000, result.getVertices()[6].y, 1e-3)
		assertEquals(-0.833, result.getVertices()[7].x, 1e-3)
		assertEquals( 5.000, result.getVertices()[7].y, 1e-3)
		assertEquals(-2.256, result.getVertices()[8].x, 1e-3)
		assertEquals( 4.573, result.getVertices()[8].y, 1e-3)
		assertEquals(-2.600, result.getVertices()[9].x, 1e-3)
		assertEquals( 4.000, result.getVertices()[9].y, 1e-3)

    }
    @Test
    fun polygonIntersectionVertexOnEdgeB() {

		val p1 = Polygon(
				Vector2(0.0, 0.0),
				Vector2(2.0, 1.0),
				Vector2(4.0, 3.0),
				Vector2(4.25, 4.0),
				Vector2(2.0, 5.0),
				Vector2(-2.0, 5.0),
				Vector2(-4.0, 3.75))
		val p2 = Polygon(
				Vector2(1.0, 0.0),
				Vector2(3.0, 1.0),
				Vector2(3.25, 3.75),
				Vector2(1.5, 4.75),
				Vector2(0.0, 5.0),
				Vector2(-2.5, 4.5),
				Vector2(-2.75, 3.25),
				Vector2(-2.5, 1.5))
		val tx1 = Transform()
		val tx2 = Transform()
		val result = Geometry.getIntersection(p1, tx1, p2, tx2)
		assertNotNull(result)
		assertEquals(10, result.getVertices().size)
		assertEquals(-0.842, result.getVertices()[0].x, 1e-3)
		assertEquals( 0.789, result.getVertices()[0].y, 1e-3)
		assertEquals( 0.461, result.getVertices()[1].x, 1e-3)
		assertEquals( 0.230, result.getVertices()[1].y, 1e-3)
		assertEquals( 2.000, result.getVertices()[2].x, 1e-3)
		assertEquals( 1.000, result.getVertices()[2].y, 1e-3)
		assertEquals( 3.100, result.getVertices()[3].x, 1e-3)
		assertEquals( 2.100, result.getVertices()[3].y, 1e-3)
		assertEquals( 3.250, result.getVertices()[4].x, 1e-3)
		assertEquals( 3.750, result.getVertices()[4].y, 1e-3)
		assertEquals( 1.500, result.getVertices()[5].x, 1e-3)
		assertEquals( 4.750, result.getVertices()[5].y, 1e-3)
		assertEquals( 0.000, result.getVertices()[6].x, 1e-3)
		assertEquals( 5.000, result.getVertices()[6].y, 1e-3)
		assertEquals(-2.500, result.getVertices()[7].x, 1e-3)
		assertEquals( 4.500, result.getVertices()[7].y, 1e-3)
		assertEquals(-2.750, result.getVertices()[8].x, 1e-3)
		assertEquals( 3.250, result.getVertices()[8].y, 1e-3)
		assertEquals(-2.639, result.getVertices()[9].x, 1e-3)
		assertEquals( 2.474, result.getVertices()[9].y, 1e-3)

    }
    @Test
    fun polygonIntersectionCoincidentVertexA() {

		val p1 = Polygon(
				Vector2(0.0, 0.0),
				Vector2(2.0, 1.0),
				Vector2(4.0, 3.0),
				Vector2(4.25, 4.0),
				Vector2(2.0, 5.0),
				Vector2(-2.0, 5.0),
				Vector2(-2.75, 3.25))
		val p2 = Polygon(
				Vector2(1.0, 0.0),
				Vector2(3.0, 1.0),
				Vector2(3.25, 3.75),
				Vector2(1.5, 4.75),
				Vector2(0.0, 5.25),
				Vector2(-2.5, 4.5),
				Vector2(-2.75, 3.25),
				Vector2(-2.5, 1.5))
		val tx1 = Transform()
		val tx2 = Transform()
		val result = Geometry.getIntersection(p1, tx1, p2, tx2)
		assertNotNull(result)
		assertEquals(10, result.getVertices().size)
		assertEquals(-0.568, result.getVertices()[0].x, 1e-3)
		assertEquals( 0.672, result.getVertices()[0].y, 1e-3)
		assertEquals( 0.461, result.getVertices()[1].x, 1e-3)
		assertEquals( 0.230, result.getVertices()[1].y, 1e-3)
		assertEquals( 2.000, result.getVertices()[2].x, 1e-3)
		assertEquals( 1.000, result.getVertices()[2].y, 1e-3)
		assertEquals( 3.100, result.getVertices()[3].x, 1e-3)
		assertEquals( 2.100, result.getVertices()[3].y, 1e-3)
		assertEquals( 3.250, result.getVertices()[4].x, 1e-3)
		assertEquals( 3.750, result.getVertices()[4].y, 1e-3)
		assertEquals( 1.500, result.getVertices()[5].x, 1e-3)
		assertEquals( 4.750, result.getVertices()[5].y, 1e-3)
		assertEquals( 0.750, result.getVertices()[6].x, 1e-3)
		assertEquals( 5.000, result.getVertices()[6].y, 1e-3)
		assertEquals(-0.833, result.getVertices()[7].x, 1e-3)
		assertEquals( 5.000, result.getVertices()[7].y, 1e-3)
		assertEquals(-2.172, result.getVertices()[8].x, 1e-3)
		assertEquals( 4.598, result.getVertices()[8].y, 1e-3)
		assertEquals(-2.750, result.getVertices()[9].x, 1e-3)
		assertEquals( 3.250, result.getVertices()[9].y, 1e-3)

    }
    @Test
    fun polygonIntersectionCoincidentVertexB() {

		val p1 = Polygon(
				Vector2(0.0, 0.0),
				Vector2(2.0, 1.0),
				Vector2(4.0, 3.0),
				Vector2(4.25, 4.0),
				Vector2(2.0, 5.0),
				Vector2(-2.0, 5.0),
				Vector2(-4.0, 3.75))
		val p2 = Polygon(
				Vector2(1.0, 0.0),
				Vector2(3.0, 1.0),
				Vector2(3.25, 3.75),
				Vector2(1.5, 4.75),
				Vector2(-2.0, 5.0),
				Vector2(-2.5, 4.5),
				Vector2(-2.75, 3.25),
				Vector2(-2.5, 1.5))
		val tx1 = Transform()
		val tx2 = Transform()
		val result = Geometry.getIntersection(p1, tx1, p2, tx2)
		assertNotNull(result)
		assertEquals(10, result.getVertices().size)
		assertEquals(-0.842, result.getVertices()[0].x, 1e-3)
		assertEquals( 0.789, result.getVertices()[0].y, 1e-3)
		assertEquals( 0.461, result.getVertices()[1].x, 1e-3)
		assertEquals( 0.230, result.getVertices()[1].y, 1e-3)
		assertEquals( 2.000, result.getVertices()[2].x, 1e-3)
		assertEquals( 1.000, result.getVertices()[2].y, 1e-3)
		assertEquals( 3.100, result.getVertices()[3].x, 1e-3)
		assertEquals( 2.100, result.getVertices()[3].y, 1e-3)
		assertEquals( 3.250, result.getVertices()[4].x, 1e-3)
		assertEquals( 3.750, result.getVertices()[4].y, 1e-3)
		assertEquals( 1.500, result.getVertices()[5].x, 1e-3)
		assertEquals( 4.750, result.getVertices()[5].y, 1e-3)
		assertEquals(-2.000, result.getVertices()[6].x, 1e-3)
		assertEquals( 5.000, result.getVertices()[6].y, 1e-3)
		assertEquals(-2.500, result.getVertices()[7].x, 1e-3)
		assertEquals( 4.500, result.getVertices()[7].y, 1e-3)
		assertEquals(-2.750, result.getVertices()[8].x, 1e-3)
		assertEquals( 3.250, result.getVertices()[8].y, 1e-3)
		assertEquals(-2.639, result.getVertices()[9].x, 1e-3)
		assertEquals( 2.474, result.getVertices()[9].y, 1e-3)

    }
    @Test
    fun polygonIntersectionColinearEdgeB() {

		val p1 = Polygon(
				Vector2(0.0, 0.0),
				Vector2(2.0, 1.0),
				Vector2(4.0, 3.0),
				Vector2(4.25, 4.0),
				Vector2(2.0, 5.0),
				Vector2(-2.0, 5.0),
				Vector2(-4.0, 3.75))
		val p2 = Polygon(
				Vector2(1.0, 0.0),
				Vector2(3.0, 1.0),
				Vector2(3.25, 3.75),
				Vector2(1.5, 4.75),
				Vector2(0.5, 5.0),
				Vector2(-0.5, 5.0),
				Vector2(-2.5, 4.5),
				Vector2(-2.75, 3.25),
				Vector2(-2.5, 1.5))
		val tx1 = Transform()
		val tx2 = Transform()
		val result = Geometry.getIntersection(p1, tx1, p2, tx2)
		assertNotNull(result)
		assertEquals(11, result.getVertices().size)
		assertEquals(-0.842, result.getVertices()[0].x, 1e-3)
		assertEquals( 0.789, result.getVertices()[0].y, 1e-3)
		assertEquals( 0.461, result.getVertices()[1].x, 1e-3)
		assertEquals( 0.230, result.getVertices()[1].y, 1e-3)
		assertEquals( 2.000, result.getVertices()[2].x, 1e-3)
		assertEquals( 1.000, result.getVertices()[2].y, 1e-3)
		assertEquals( 3.100, result.getVertices()[3].x, 1e-3)
		assertEquals( 2.100, result.getVertices()[3].y, 1e-3)
		assertEquals( 3.250, result.getVertices()[4].x, 1e-3)
		assertEquals( 3.750, result.getVertices()[4].y, 1e-3)
		assertEquals( 1.500, result.getVertices()[5].x, 1e-3)
		assertEquals( 4.750, result.getVertices()[5].y, 1e-3)
		assertEquals( 0.500, result.getVertices()[6].x, 1e-3)
		assertEquals( 5.000, result.getVertices()[6].y, 1e-3)
		assertEquals(-0.500, result.getVertices()[7].x, 1e-3)
		assertEquals( 5.000, result.getVertices()[7].y, 1e-3)
		assertEquals(-2.500, result.getVertices()[8].x, 1e-3)
		assertEquals( 4.500, result.getVertices()[8].y, 1e-3)
		assertEquals(-2.750, result.getVertices()[9].x, 1e-3)
		assertEquals( 3.250, result.getVertices()[9].y, 1e-3)
		assertEquals(-2.639, result.getVertices()[10].x, 1e-3)
		assertEquals( 2.474, result.getVertices()[10].y, 1e-3)

    }
    @Test
    fun polygonIntersectionEdgeTouching() {

		val p1 = Polygon(
				Vector2(0.0, 0.0),
				Vector2(2.0, 1.0),
				Vector2(4.0, 3.0),
				Vector2(4.25, 4.0),
				Vector2(2.0, 5.0),
				Vector2(-2.0, 5.0),
				Vector2(-4.0, 3.75))
		val p2 = Polygon(
				Vector2(-1.0, 5.0),
				Vector2(1.0, 5.0),
				Vector2(1.0, 6.0),
				Vector2(-1.0, 6.0))
		val tx1 = Transform()
		val tx2 = Transform()
		val result = Geometry.getIntersection(p1, tx1, p2, tx2)
		assertNull(result)

    }
    @Test
    fun polygonIntersectionVertexTouching() {

		val p1 = Polygon(
				Vector2(0.0, 0.0),
				Vector2(2.0, 1.0),
				Vector2(4.0, 3.0),
				Vector2(4.25, 4.0),
				Vector2(2.0, 5.0),
				Vector2(-2.0, 5.0),
				Vector2(-4.0, 3.75))
		val p2 = Polygon(
				Vector2(2.0, 5.0),
				Vector2(4.0, 5.0),
				Vector2(4.0, 6.0),
				Vector2(2.0, 6.0))
		val tx1 = Transform()
		val tx2 = Transform()
		val result = Geometry.getIntersection(p1, tx1, p2, tx2)
		assertNull(result)

    }
    @Test
    fun polygonIntersectionVertexTouchingCoincident() {

		val p1 = Polygon(
				Vector2(0.0, 0.0),
				Vector2(2.0, 1.0),
				Vector2(4.0, 3.0),
				Vector2(4.25, 4.0),
				Vector2(2.0, 5.0),
				Vector2(-2.0, 5.0),
				Vector2(-4.0, 3.75))
		val p2 = Polygon(
				Vector2(2.0, 5.0),
				Vector2(4.0, 5.0),
				Vector2(1.0, 6.0),
				Vector2(-1.0, 6.0))
		val tx1 = Transform()
		val tx2 = Transform()
		val result = Geometry.getIntersection(p1, tx1, p2, tx2)
		assertNull(result)

    }
    @Test
    fun polygonIntersectionNoIntersection() {

		val p1 = Polygon(
				Vector2(0.0, 0.0),
				Vector2(2.0, 1.0),
				Vector2(4.0, 3.0),
				Vector2(4.25, 4.0),
				Vector2(2.0, 5.0),
				Vector2(-2.0, 5.0),
				Vector2(-4.0, 3.75))
		val p2 = Polygon(
				Vector2(3.0, 5.0),
				Vector2(5.0, 5.0),
				Vector2(5.0, 6.0),
				Vector2(3.0, 6.0))
		val tx1 = Transform()
		val tx2 = Transform()
		val result = Geometry.getIntersection(p1, tx1, p2, tx2)
		assertNull(result)

    }
    @Test
    fun polygonIntersectionContainment() {

		val p1 = Polygon(
				Vector2(0.0, 0.0),
				Vector2(2.0, 1.0),
				Vector2(4.0, 3.0),
				Vector2(4.25, 4.0),
				Vector2(2.0, 5.0),
				Vector2(-2.0, 5.0),
				Vector2(-4.0, 3.75))
		val p2 = Polygon(
				Vector2(-1.0, 2.0),
				Vector2( 1.0, 2.0),
				Vector2( 1.0, 3.0),
				Vector2(-1.0, 3.0))
		val tx1 = Transform()
		val tx2 = Transform()
		val result = Geometry.getIntersection(p1, tx1, p2, tx2)
		assertNotNull(result)
		assertSame(result, p2)

    }
    @Test
    fun getRotationRadius() {

		val p1 = Geometry.createUnitCirclePolygon(5, 0.5)
		var r = Geometry.getRotationRadius(p1.getVertices())
		assertEquals(0.500, r, 1e-3)
		r = Geometry.getRotationRadius(Vector2(1.0, 0.0), arrayOf<Vector2?>( Vector2(-0.5, 0.0) ))
		assertEquals(1.500, r, 1e-3)
		r = Geometry.getRotationRadius(Vector2(-1.0, 0.0), p1.getVertices())
		assertEquals(1.500, r, 1e-3)
		r = Geometry.getRotationRadius(null as Array<Vector2?>?)
		assertEquals(0.000, r, 1e-3)
		r = Geometry.getRotationRadius(arrayOfNulls<Vector2>(0))
		assertEquals(0.000, r, 1e-3)
		r = Geometry.getRotationRadius(null, arrayOfNulls<Vector2>(0))
		assertEquals(0.000, r, 1e-3)
		r = Geometry.getRotationRadius(Vector2(1.0, 0.0), arrayOf<Vector2?>( Vector2(), null, Vector2() ))
		assertEquals(1.000, r, 1e-3)

    }
    @Test
    fun getCounterClockwiseEdgeNormals() {

		val p1 = Geometry.createUnitCirclePolygon(4, 0.5)
		var normals = Geometry.getCounterClockwiseEdgeNormals(p1.getVertices())
		assertEquals(0.707, normals!![0]!!.x, 1e-3)
		assertEquals(0.707, normals!![0]!!.y, 1e-3)
		assertEquals(-0.707, normals!![1]!!.x, 1e-3)
		assertEquals(0.707, normals!![1]!!.y, 1e-3)
		assertEquals(-0.707, normals!![2]!!.x, 1e-3)
		assertEquals(-0.707, normals!![2]!!.y, 1e-3)
		assertEquals(0.707, normals!![3]!!.x, 1e-3)
		assertEquals(-0.707, normals!![3]!!.y, 1e-3)
		normals = Geometry.getCounterClockwiseEdgeNormals(null as Array<Vector2?>?)
		assertEquals(null, normals)
		normals = Geometry.getCounterClockwiseEdgeNormals(arrayOfNulls<Vector2>(0))
		assertEquals(null, normals)

    }
    @Test
    fun getCounterClockwiseEdgeNormalsWithNullVertex() {
        assertFailsWith<NullPointerException> {

		Geometry.getCounterClockwiseEdgeNormals(arrayOf<Vector2?>(
			Vector2(1.0, 1.0),
			Vector2(2.0, 3.0),
			Vector2(),
			null,
			Vector2(3.0, -1.0)
		))

        }
    }
}
