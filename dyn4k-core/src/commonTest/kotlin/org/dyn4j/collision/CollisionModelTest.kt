package org.dyn4j.collision

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotSame
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Vector2
import org.dyn4j.UnitConversion
import org.dyn4j.Unsafe
import org.dyn4j.exception.CopyException

class CollisionModelTest {
    private open class RootFilter : TypeFilter()
    private class ChildFilter : RootFilter()
    private class OtherFilter : TypeFilter()

    @Test
    fun typeFilterChecksBothDirectionsOfSubclassHierarchy() {
        val parent = RootFilter()
        val child = ChildFilter()
        assertTrue(parent.isAllowed(child))
        assertTrue(child.isAllowed(parent))
        assertFalse(parent.isAllowed(OtherFilter()))
        assertFalse(parent.isAllowed(null))
        assertSame(child, child.copy())
    }

    @Test
    fun filtersAndFixtureCopyPreserveBaselineBehavior() {
        val first = CategoryFilter(1, 2)
        val second = CategoryFilter(2, 1)
        val blocked = CategoryFilter(4, 1)
        assertTrue(first.isAllowed(second))
        assertFalse(first.isAllowed(blocked))
        assertTrue(Filter.DEFAULT_FILTER.isAllowed(blocked))

        val fixture = Fixture(Circle(1.0))
        fixture.setFilter(first)
        fixture.setSensor(true)
        fixture.setUserData("private state")
        val copy = fixture.copy()
        assertNotSame(fixture, copy)
        assertNotSame(fixture.getShape(), copy.getShape())
        assertNotSame(first, copy.getFilter())
        assertTrue(copy.isSensor())
        assertSame(null, copy.getUserData())
    }

    private class TestBody : AbstractCollisionBody<Fixture> {
        constructor() : super()
        private constructor(body: TestBody) : super(body)
        override fun addFixture(convex: Convex): Fixture = Fixture(convex).also { addFixture(it) }
        override fun getLocalCenter() = Vector2()
        override fun copy() = TestBody(this)
    }

    @Test
    fun fixtureViewsAndIteratorStayLive() {
        val body = TestBody()
        val events = mutableListOf<String>()
        body.setFixtureModificationHandler(object : FixtureModificationHandler<Fixture> {
            override fun onFixtureAdded(fixture: Fixture) { events.add("add") }
            override fun onFixtureRemoved(fixture: Fixture) { events.add("remove") }
            override fun onAllFixturesRemoved() { events.add("all") }
        })
        val view = body.getFixtures()
        val first = body.addFixture(Circle(1.0))
        assertSame(first, view.single())
        val iterator = body.getFixtureIterator()
        assertFailsWith<IllegalStateException> { iterator.remove() }
        assertSame(first, iterator.next())
        iterator.remove()
        assertTrue(view.isEmpty())
        assertEquals(listOf("add", "remove"), events)
        body.addFixture(Circle(2.0))
        val copy = body.copy()
        assertNotSame(body.getFixture(0), copy.getFixture(0))
        assertEquals(null, copy.getFixtureModificationHandler())
    }

    @Test
    fun boundsAndPairsUseLiveObjects() {
        val bounds = AxisAlignedBounds(4.0, 4.0)
        assertTrue(bounds.isOutside(org.dyn4j.geometry.AABB(3.0, 3.0, 4.0, 4.0)))
        bounds.translate(3.0, 3.0)
        assertFalse(bounds.isOutside(org.dyn4j.geometry.AABB(3.0, 3.0, 4.0, 4.0)))
        val first = BasicCollisionPair("a", "b")
        assertEquals(first, BasicCollisionPair("b", "a"))
        assertSame(first.getFirst(), first.copy().getFirst())
    }

    @Test
    fun collisionEstimatesAndUnitConversionsMatchBaseline() {
        assertEquals(20, Collisions.getEstimatedCollisionPairs(5))
        assertEquals(1, Collisions.getEstimatedRaycastCollisions(20))
        assertEquals(0.3048, UnitConversion.feetToMeters(1.0), 1.0e-12)
        assertEquals(1.0 / 0.3048, UnitConversion.metersToFeet(1.0), 1.0e-12)
    }

    private class BadFixture : Fixture(Circle(1.0))

    @Test
    fun failuresPreservePublicBehavior() {
        assertFailsWith<org.dyn4j.exception.ArgumentNullException> { Fixture(null) }
        assertFailsWith<org.dyn4j.exception.ArgumentNullException> { Fixture(Circle(1.0)).setFilter(null) }
        assertFailsWith<org.dyn4j.exception.ValueOutOfRangeException> { AxisAlignedBounds(0.0, 2.0) }
        assertFailsWith<CopyException> { Unsafe.copy(BadFixture()) }
        val iterator = TestBody().getFixtureIterator()
        assertFailsWith<IndexOutOfBoundsException> { iterator.next() }
    }
}
