package io.github.rubixhacker.dyn4k

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertSame
import kotlin.test.assertTrue
import kotlin.test.assertFailsWith

class GeometryShapeTest {
    @Test
    fun boundsShareTheCompatibilityObjectAndCopyIndependently() {
        val bounds = AABB(-2.0, -1.0, 4.0, 3.0)
        val compatibility: org.dyn4j.geometry.AABB = bounds
        assertSame(bounds, compatibility)
        assertEquals(6.0, bounds.getWidth())
        assertEquals(4.0, bounds.getHeight())
        assertTrue(bounds.contains(Vector2(4.0, 3.0)))
        assertFalse(bounds.contains(Vector2(4.01, 3.0)))

        val copy = bounds.copy()
        bounds.translate(2.0, -1.0)
        assertEquals(-2.0, copy.getMinX())
        assertEquals(0.0, bounds.getMinX())
    }

    @Test
    fun projectedIntervalsRetainTheBaselineBoundaryRules() {
        val projection = Interval(-2.0, 3.0)
        val compatibility: org.dyn4j.geometry.Interval = projection
        assertSame(projection, compatibility)
        assertTrue(projection.includesInclusive(3.0))
        assertFalse(projection.includesExclusive(3.0))
        assertEquals(1.0, projection.getOverlap(Interval(2.0, 5.0)))
        val copy = projection.copy()
        projection.expand(2.0)
        assertEquals(-2.0, copy.getMin())
        assertEquals(-3.0, projection.getMin())
    }

    @Test
    fun rayPreservesItsLiveStartAndCopiesBothVectors() {
        val start = Vector2(2.0, -3.0)
        val ray = Ray(start, Vector2(3.0, 4.0))
        val compatibility: org.dyn4j.geometry.Ray = ray
        assertSame(start, compatibility.getStart())
        assertEquals(0.6, ray.getDirectionVector().x, 1e-12)
        assertEquals(0.8, ray.getDirectionVector().y, 1e-12)
        val copy = ray.copy()
        start.x = 9.0
        assertEquals(2.0, copy.getStart().x)
        val direction = Vector2(1.0, 2.0)
        ray.setDirection(direction)
        assertSame(direction, ray.getDirectionVector())
    }

    @Test
    fun combinedMassKeepsItsMutableCenterAndFixedModes() {
        val mass = Mass(Vector2(1.0, 0.0), 2.0, 3.0)
        val compatibility: org.dyn4j.geometry.Mass = mass
        assertSame(mass, compatibility)
        assertEquals(0.5, mass.getInverseMass())
        val center = mass.getCenter()
        assertSame(center, mass.getCenter())
        val copy = mass.copy()
        center.x = 4.0
        assertEquals(1.0, copy.getCenter().x)
        mass.setType(MassType.FIXED_LINEAR_VELOCITY)
        assertEquals(0.0, mass.getMass())
        assertEquals(3.0, mass.getInertia())
    }

    @Test
    fun circleQueriesUseOneMutableShapeThroughBothApis() {
        val circle = Circle(2.0)
        val compatibility: org.dyn4j.geometry.Shape = circle
        assertSame(circle, compatibility)
        circle.translate(3.0, -1.0)
        assertTrue(circle.contains(Vector2(5.0, -1.0)))
        assertFalse(circle.contains(Vector2(5.0, -1.0), Transform(), false))
        assertEquals(1.0, circle.project(Vector2(1.0, 0.0)).getMin())
        assertEquals(5.0, circle.createAABB().getMaxX())
        assertEquals(kotlin.math.PI * 4.0, circle.getArea(), 1e-12)
        val tag = Any()
        circle.setUserData(tag)
        assertSame(tag, circle.getUserData())
        val copy = circle.copy()
        assertEquals(null, copy.getUserData())
        assertEquals(3.0, copy.getCenter().x)
    }

    @Test
    fun polygonExposesLiveVerticesAndKeepsItsCopyIndependent() {
        val polygon = Polygon(Vector2(-1.0, -1.0), Vector2(1.0, -1.0), Vector2(1.0, 1.0), Vector2(-1.0, 1.0))
        val compatibility: org.dyn4j.geometry.Wound = polygon
        assertSame(polygon, compatibility)
        val vertices = polygon.getVertices()
        assertSame(vertices, polygon.getVertices())
        assertTrue(polygon.contains(Vector2(0.0, 0.0)))
        assertEquals(4.0, polygon.getArea(), 1e-12)
        val copy = polygon.copy()
        polygon.translate(2.0, 0.0)
        assertEquals(-1.0, copy.getVertices()[0].x)
        assertEquals(1.0, vertices[0].x)
    }

    @Test
    fun rectangleProjectsAndCopiesAfterRotation() {
        val rectangle = Rectangle(4.0, 2.0)
        val compatibility: org.dyn4j.geometry.Polygon = rectangle
        assertSame(rectangle, compatibility)
        assertEquals(8.0, rectangle.getArea(), 1e-12)
        assertEquals(2.0, rectangle.project(Vector2(1.0, 0.0)).getMax(), 1e-12)
        rectangle.rotate(kotlin.math.PI / 2.0)
        assertEquals(1.0, rectangle.project(Vector2(1.0, 0.0)).getMax(), 1e-12)
        val copy = rectangle.copy()
        rectangle.translate(3.0, 0.0)
        assertEquals(0.0, copy.getCenter().x, 1e-12)
        assertEquals(3.0, rectangle.getCenter().x, 1e-12)
    }

    @Test
    fun triangleUsesItsBaselineContainmentRule() {
        val triangle = Triangle(Vector2(0.0, 0.0), Vector2(2.0, 0.0), Vector2(0.0, 2.0))
        val compatibility: org.dyn4j.geometry.Polygon = triangle
        assertSame(triangle, compatibility)
        assertEquals(2.0, triangle.getArea(), 1e-12)
        assertTrue(triangle.contains(Vector2(0.5, 0.5), Transform()))
        assertFalse(triangle.contains(Vector2(0.0, 0.5), Transform()))
        assertEquals(2.0, triangle.copy().getArea(), 1e-12)
    }

    @Test
    fun segmentQueriesAndStaticIntersectionAgreeWithWorkedCoordinates() {
        val segment = Segment(Vector2(-2.0, 0.0), Vector2(2.0, 0.0))
        val compatibility: org.dyn4j.geometry.Wound = segment
        assertSame(segment, compatibility)
        assertEquals(4.0, segment.getLength(), 1e-12)
        assertTrue(segment.contains(Vector2(1.0, 0.0)))
        assertFalse(segment.contains(Vector2(1.0, 0.0), Transform(), false))
        val crossing = Segment.getSegmentIntersection(
            Vector2(-1.0, 0.0), Vector2(1.0, 0.0),
            Vector2(0.0, -1.0), Vector2(0.0, 1.0)
        )
        assertEquals(0.0, crossing!!.x, 1e-12)
        assertEquals(0.0, crossing.y, 1e-12)
    }

    @Test
    fun linkKeepsNeighborIdentityAndRejectsDirectTransform() {
        val previous = Vector2(-2.0, 0.0)
        val next = Vector2(2.0, 0.0)
        val link = Link(previous, Vector2(-1.0, 0.0), Vector2(1.0, 0.0), next)
        val compatibility: org.dyn4j.geometry.Segment = link
        assertSame(link, compatibility)
        assertSame(previous, link.getPoint0())
        assertSame(next, link.getPoint3())
        assertFailsWith<UnsupportedOperationException> { link.translate(1.0, 0.0) }
        val copy = link.copy()
        previous.x = -9.0
        assertEquals(-2.0, copy.getPoint0()!!.x)
    }

    @Test
    fun curvedShapesSupportQueriesThroughBothApis() {
        val capsule = Capsule(4.0, 2.0)
        val compatibilityCapsule: org.dyn4j.geometry.Shape = capsule
        assertSame(capsule, compatibilityCapsule)
        assertTrue(capsule.contains(Vector2(1.5, 0.0)))
        assertEquals(2.0, capsule.getLength() / 2.0)
        val ellipse = Ellipse(4.0, 2.0)
        val compatibilityEllipse: org.dyn4j.geometry.Convex = ellipse
        assertSame(ellipse, compatibilityEllipse)
        assertTrue(ellipse.contains(Vector2(0.0, 0.5)))
        assertEquals(2.0, ellipse.getFarthestPoint(Vector2(1.0, 0.0), Transform()).x, 1e-12)
        val copy = ellipse.copy()
        ellipse.translate(1.0, 0.0)
        assertEquals(0.0, copy.getCenter().x)
    }

    @Test
    fun halfEllipseRetainsItsLiveEllipseCenterAcrossTranslation() {
        val shape = HalfEllipse(4.0, 2.0)
        val compatibility: org.dyn4j.geometry.Shape = shape
        assertSame(shape, compatibility)
        assertTrue(shape.contains(Vector2(0.0, 0.5)))
        assertFalse(shape.contains(Vector2(0.0, -0.5)))
        val ellipseCenter = shape.getEllipseCenter()
        shape.translate(1.0, 2.0)
        assertSame(ellipseCenter, shape.getEllipseCenter())
        assertEquals(1.0, ellipseCenter.x)
        assertEquals(null, shape.copy().getUserData())
    }

    @Test
    fun sliceRetainsItsLiveCircleCenterAndQueriesItsArc() {
        val slice = Slice(2.0, kotlin.math.PI / 2.0)
        val compatibility: org.dyn4j.geometry.Convex = slice
        assertSame(slice, compatibility)
        assertTrue(slice.contains(Vector2(1.0, 0.0)))
        assertFalse(slice.contains(Vector2(-1.0, 0.0)))
        assertEquals(2.0, slice.getFarthestPoint(Vector2(1.0, 0.0), Transform()).x, 1e-12)
        val center = slice.getCircleCenter()
        slice.translate(1.0, 1.0)
        assertSame(center, slice.getCircleCenter())
        assertEquals(1.0, center.x)
        assertEquals(null, slice.copy().getUserData())
    }

    @Test
    fun geometryFactoriesConstructEveryCurvedBaselineShape() {
        val circle: org.dyn4j.geometry.Circle = Geometry.createCircle(2.0)
        val capsule: org.dyn4j.geometry.Capsule = Geometry.createCapsule(4.0, 2.0)
        val ellipse: org.dyn4j.geometry.Ellipse = Geometry.createEllipse(4.0, 2.0)
        val halfEllipse: org.dyn4j.geometry.HalfEllipse = Geometry.createHalfEllipse(4.0, 2.0)
        val slice: org.dyn4j.geometry.Slice = Geometry.createSlice(2.0, kotlin.math.PI / 2.0)
        assertEquals(2.0, circle.getRadius())
        assertEquals(4.0, capsule.getLength())
        assertEquals(4.0, ellipse.getWidth())
        assertEquals(2.0, halfEllipse.getHeight())
        assertEquals(2.0, slice.getSliceRadius())
    }
}
