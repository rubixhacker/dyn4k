package org.dyn4j.collision.manifold

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertEquals
import kotlin.test.assertNotSame
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.collision.narrowphase.Penetration
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2

val ManifoldQueryTest by testSuite {
    test("exposedPointsStayLiveAndCopiesAreIndependent") { ManifoldQueryTestFixture().run { exposedPointsStayLiveAndCopiesAreIndependent() } }
    test("clippingCircleContactUsesDirectedNormal") { ManifoldQueryTestFixture().run { clippingCircleContactUsesDirectedNormal() } }
}

private class ManifoldQueryTestFixture  {
fun exposedPointsStayLiveAndCopiesAreIndependent() {
        val manifold = Manifold()
        val points = manifold.getPoints()
        val normal = manifold.getNormal()
        val point = ManifoldPoint(null)
        point.setPoint(Vector2(1.0, 2.0))
        points.add(point)
        manifold.shift(Vector2(2.0, 3.0))
        assertSame(points, manifold.getPoints())
        assertSame(normal, manifold.getNormal())
        assertEquals(Vector2(3.0, 5.0), point.getPoint())
        val copy = manifold.copy()
        assertNotSame(points, copy.getPoints())
        assertNotSame(point, copy.getPoints()[0])
        manifold.clear()
        assertTrue(points.isEmpty())
        assertEquals(1, copy.getPoints().size)
    }

fun clippingCircleContactUsesDirectedNormal() {
        val penetration = Penetration()
        penetration.setNormal(Vector2(1.0, 0.0))
        penetration.setDepth(0.5)
        val manifold = Manifold()
        assertTrue(ClippingManifoldSolver().getManifold(
            penetration, Circle(1.0), Transform(), Circle(1.0),
            Transform().also { it.translate(1.5, 0.0) }, manifold
        ))
        assertEquals(Vector2(-1.0, 0.0), manifold.getNormal())
        assertEquals(1, manifold.getPoints().size)
        assertEquals(0.5, manifold.getPoints()[0].getDepth())
    }
}
