package io.github.rubixhacker.dyn4k

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import org.dyn4j.geometry.hull.DivideAndConquer
import org.dyn4j.geometry.hull.GiftWrap
import org.dyn4j.geometry.hull.GrahamScan
import org.dyn4j.geometry.hull.MonotoneChain
import org.dyn4j.geometry.decompose.Bayazit
import org.dyn4j.geometry.decompose.EarClipping
import org.dyn4j.geometry.decompose.SweepLine
import org.dyn4j.geometry.simplify.DouglasPeucker
import org.dyn4j.geometry.simplify.VertexClusterReduction
import org.dyn4j.geometry.simplify.Visvalingam

class PolygonAlgorithmTest {
    @Test
    fun pointCloudBecomesAUsableSquareThroughEveryHullGenerator() {
        val generators = listOf(MonotoneChain(), GrahamScan(), GiftWrap(), DivideAndConquer())
        for (generator in generators) {
            val hull = generator.generate(
                Vector2(1.0, 1.0), Vector2(2.0, 0.0), Vector2(0.0, 0.0),
                Vector2(2.0, 2.0), Vector2(0.0, 2.0), Vector2(1.0, 1.0)
            )
            assertEquals(4, hull.size)
            assertEquals(4.0, Polygon(*hull).getArea(), 1e-12)
        }
    }

    @Test
    fun concaveInputBecomesConvexShapesAndTriangles() {
        val polygon = arrayOf(
            Vector2(0.0, 0.0), Vector2(2.0, 0.0), Vector2(2.0, 1.0),
            Vector2(1.0, 1.0), Vector2(1.0, 2.0), Vector2(0.0, 2.0)
        )
        for (decomposer in listOf(Bayazit(), EarClipping(), SweepLine())) {
            val pieces = decomposer.decompose(*polygon)
            assertEquals(3.0, pieces.sumOf { it.getArea() }, 1e-12)
        }
        for (triangulator in listOf(EarClipping(), SweepLine())) {
            val triangles = triangulator.triangulate(*polygon)
            assertEquals(4, triangles.size)
            assertEquals(3.0, triangles.sumOf { it.getArea() }, 1e-12)
        }
    }

    @Test
    fun redundantBoundaryPointCanBeRemovedWithoutChangingTheSquare() {
        val polygon = listOf(
            Vector2(0.0, 0.0), Vector2(0.05, 0.0), Vector2(2.0, 0.0),
            Vector2(2.0, 2.0), Vector2(0.0, 2.0)
        )
        val simplifiers = listOf(
            VertexClusterReduction(0.1), DouglasPeucker(0.0, 0.1), Visvalingam(0.0, 0.1)
        )
        for (simplifier in simplifiers) {
            val simplified = simplifier.simplify(polygon)!!
            assertEquals(4, simplified.size)
            assertEquals(4.0, Polygon(*simplified.toTypedArray()).getArea(), 1e-12)
        }
    }

    @Test
    fun pinnedSeventeenVertexPolygonProducesValidShapesWithTheKnownArea() {
        val fixture = arrayOf(
            Vector2(1.0, 1.0), Vector2(0.8, 0.9), Vector2(0.7, 1.2),
            Vector2(-0.5, 0.7), Vector2(-0.2, 0.4), Vector2(-0.6, 0.2),
            Vector2(-0.4, -0.1), Vector2(-0.3, -0.5), Vector2(0.0, 0.0),
            Vector2(0.2, -0.3), Vector2(0.1, -0.5), Vector2(-0.2, -0.6),
            Vector2(0.2, -0.7), Vector2(0.4, -0.4), Vector2(0.8, -0.6),
            Vector2(0.4, 0.0), Vector2(0.6, 0.5)
        )
        for (decomposer in listOf(Bayazit(), EarClipping(), SweepLine())) {
            val pieces = decomposer.decompose(*fixture)
            assertTrue(pieces.size > 1)
            assertEquals(1.41, pieces.sumOf { it.getArea() }, 1e-12)
        }
        for (triangulator in listOf(EarClipping(), SweepLine())) {
            val triangles = triangulator.triangulate(*fixture)
            assertEquals(15, triangles.size)
            assertEquals(1.41, triangles.sumOf { it.getArea() }, 1e-12)
        }
    }

    @Test
    fun clockwiseConcaveInputKeepsTheSameAreaAndTriangleCount() {
        val clockwise = arrayOf(
            Vector2(0.0, 2.0), Vector2(1.0, 2.0), Vector2(1.0, 1.0),
            Vector2(2.0, 1.0), Vector2(2.0, 0.0), Vector2(0.0, 0.0)
        )
        for (decomposer in listOf(Bayazit(), EarClipping(), SweepLine())) {
            assertEquals(3.0, decomposer.decompose(*clockwise).sumOf { it.getArea() }, 1e-12)
        }
        for (triangulator in listOf(EarClipping(), SweepLine())) {
            assertEquals(4, triangulator.triangulate(*clockwise).size)
        }
    }

    @Test
    fun degenerateInputIsRejectedBeforeADecompositionIsReported() {
        for (decomposer in listOf(Bayazit(), EarClipping(), SweepLine())) {
            assertFailsWith<IllegalArgumentException> {
                decomposer.decompose(Vector2(0.0, 0.0), Vector2(1.0, 0.0), Vector2(0.0, 1.0))
            }
        }
        val coincident = arrayOf(
            Vector2(0.0, 0.0), Vector2(1.0, 0.0), Vector2(1.0, 0.0), Vector2(0.0, 1.0)
        )
        for (decomposer in listOf(EarClipping(), SweepLine())) {
            assertFailsWith<IllegalArgumentException> { decomposer.decompose(*coincident) }
        }
    }

    @Test
    fun simplifiersHandleEmptyAndNullElementsAndRejectNegativeThresholds() {
        assertFailsWith<IllegalArgumentException> { VertexClusterReduction(-0.1) }
        assertFailsWith<IllegalArgumentException> { DouglasPeucker(0.0, -0.1) }
        assertFailsWith<IllegalArgumentException> { Visvalingam(0.0, -0.1) }
        val polygon = listOf<Vector2?>(
            Vector2(0.0, 0.0), null, Vector2(2.0, 0.0),
            Vector2(2.0, 2.0), Vector2(0.0, 2.0)
        )
        for (simplifier in listOf(
            VertexClusterReduction(0.0), DouglasPeucker(0.0, 0.0), Visvalingam(0.0, 0.0)
        )) {
            assertEquals(emptyList(), simplifier.simplify(emptyList()))
            assertEquals(null, simplifier.simplify(null as List<Vector2?>?))
            assertEquals(4, simplifier.simplify(polygon)!!.size)
        }
    }
}
