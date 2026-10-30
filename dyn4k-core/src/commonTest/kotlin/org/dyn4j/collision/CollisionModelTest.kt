package org.dyn4j.collision

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertFalse
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotSame
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.AABB
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Vector2
import org.dyn4j.UnitConversion
import org.dyn4j.Unsafe
import org.dyn4j.exception.ArgumentNullException
import org.dyn4j.exception.CopyException

val CollisionModelTest by testSuite {
    test("typeFilterChecksBothDirectionsOfSubclassHierarchy") { CollisionModelTestFixture().run { typeFilterChecksBothDirectionsOfSubclassHierarchy() } }
    test("filtersAndFixtureCopyPreserveBaselineBehavior") { CollisionModelTestFixture().run { filtersAndFixtureCopyPreserveBaselineBehavior() } }
    test("nullableShapeOverrideReceivesNullThroughCollisionBody") { CollisionModelTestFixture().run { nullableShapeOverrideReceivesNullThroughCollisionBody() } }
    test("nullPointFailsWhenAFixtureUsesItsShape") { CollisionModelTestFixture().run { nullPointFailsWhenAFixtureUsesItsShape() } }
    test("fixtureViewsAndIteratorStayLive") { CollisionModelTestFixture().run { fixtureViewsAndIteratorStayLive() } }
    test("boundsAndPairsUseLiveObjects") { CollisionModelTestFixture().run { boundsAndPairsUseLiveObjects() } }
    test("collisionEstimatesAndUnitConversionsMatchBaseline") { CollisionModelTestFixture().run { collisionEstimatesAndUnitConversionsMatchBaseline() } }
    test("failuresPreservePublicBehavior") { CollisionModelTestFixture().run { failuresPreservePublicBehavior() } }
    test("copyExceptionFromNamesPreservesMessage") { CollisionModelTestFixture().run { copyExceptionFromNamesPreservesMessage() } }
    test("nullFirstPairThrowsDuringEquality") { CollisionModelTestFixture().run { nullFirstPairThrowsDuringEquality() } }
    test("nullCollisionItemCanBeCopied") { CollisionModelTestFixture().run { nullCollisionItemCanBeCopied() } }
    test("bodyCopyUsesOverriddenFixtureGetter") { CollisionModelTestFixture().run { bodyCopyUsesOverriddenFixtureGetter() } }
    test("fixtureViewIteratorFailsAfterBodyMutation") { CollisionModelTestFixture().run { fixtureViewIteratorFailsAfterBodyMutation() } }
    test("protectedFixtureIteratorFailsAfterBodyMutation") { CollisionModelTestFixture().run { protectedFixtureIteratorFailsAfterBodyMutation() } }
    test("fixtureViewSubListFailsAfterBodyMutation") { CollisionModelTestFixture().run { fixtureViewSubListFailsAfterBodyMutation() } }
    test("protectedFixtureSubListFailsAfterBodyMutation") { CollisionModelTestFixture().run { protectedFixtureSubListFailsAfterBodyMutation() } }
    test("nestedViewAndProtectedSubListIteratorsFailAfterMutation") { CollisionModelTestFixture().run { nestedViewAndProtectedSubListIteratorsFailAfterMutation() } }
    test("protectedSubListMutationsRemainLiveAndInvalidateIterators") { CollisionModelTestFixture().run { protectedSubListMutationsRemainLiveAndInvalidateIterators() } }
    test("nullPointOperationsOnEmptyBodyReturnEmptyResults") { CollisionModelTestFixture().run { nullPointOperationsOnEmptyBodyReturnEmptyResults() } }
    test("collisionItemEqualityCallsOtherGettersFirst") { CollisionModelTestFixture().run { collisionItemEqualityCallsOtherGettersFirst() } }
    test("emptyBodyDefersNullCenterAndTransformChecks") { CollisionModelTestFixture().run { emptyBodyDefersNullCenterAndTransformChecks() } }
    test("pairHashCallsEarlierObjectBeforeNullFailure") { CollisionModelTestFixture().run { pairHashCallsEarlierObjectBeforeNullFailure() } }
    test("fixtureCallbacksKeepInitialTraversalExtent") { CollisionModelTestFixture().run { fixtureCallbacksKeepInitialTraversalExtent() } }
}

private class CollisionModelTestFixture  {
    private open class RootFilter : TypeFilter()
    private class ChildFilter : RootFilter()
    private class OtherFilter : TypeFilter()

fun typeFilterChecksBothDirectionsOfSubclassHierarchy() {
        val parent = RootFilter()
        val child = ChildFilter()
        assertTrue(parent.isAllowed(child))
        assertTrue(child.isAllowed(parent))
        assertFalse(parent.isAllowed(OtherFilter()))
        assertFalse(parent.isAllowed(null))
        assertSame(child, child.copy())
    }

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
        override fun addFixture(convex: Convex?): Fixture = Fixture(convex).also { addFixture(it) }
        override fun getLocalCenter() = Vector2()
        override fun copy() = TestBody(this)
        fun addDirectly(fixture: Fixture) { fixtures.add(fixture) }
        fun protectedIterator(): MutableIterator<Fixture> = fixtures.iterator()
        fun protectedSubList(): MutableList<Fixture> = fixtures.subList(0, 1)
        fun updateRadiusWith(center: Vector2?): Double { setRotationDiscRadius(center); return radius }
    }

    private class NullableShapeBody : AbstractCollisionBody<Fixture>() {
        override fun addFixture(convex: Convex?): Fixture {
            val shape = convex ?: throw ArgumentNullException("convex")
            return Fixture(shape).also { addFixture(it) }
        }
        override fun getLocalCenter() = Vector2()
        override fun copy() = NullableShapeBody()
    }

fun nullableShapeOverrideReceivesNullThroughCollisionBody() {
        val body: CollisionBody<Fixture> = NullableShapeBody()
        val failure = assertFailsWith<ArgumentNullException> { body.addFixture(null as Convex?) }
        assertEquals("convex cannot be null", failure.message)
        val fixtureFailure = assertFailsWith<ArgumentNullException> { body.addFixture(null) }
        assertEquals("fixture cannot be null", fixtureFailure.message)
        val fixture = body.addFixture(Circle(1.0))
        assertSame(fixture, body.getFixture(0))
    }

fun nullPointFailsWhenAFixtureUsesItsShape() {
        val empty = TestBody()
        assertEquals(null, empty.getFixture(null))
        assertTrue(empty.getFixtures(null).isEmpty())
        assertFalse(empty.contains(null))
        assertEquals(null, empty.removeFixture(null as Vector2?))
        assertTrue(empty.removeFixtures(null).isEmpty())
        assertEquals(0.0, empty.updateRadiusWith(null))
        val emptyBounds = AABB(1.0, 1.0, 2.0, 2.0)
        empty.computeAABB(null, emptyBounds)
        assertEquals(AABB(0.0, 0.0, 0.0, 0.0), emptyBounds)

        val body = TestBody()
        var shapeReads = 0
        val fixture = object : Fixture(Circle(1.0)) {
            override fun getShape(): Convex {
                shapeReads++
                return super.getShape()
            }
        }
        body.addFixture(fixture)
        assertSame(fixture, body.getFixture(Vector2()))
        shapeReads = 0
        assertFailsWith<NullPointerException> { body.getFixture(null) }
        assertEquals(1, shapeReads)
        assertFailsWith<NullPointerException> { body.getFixtures(null) }
        assertFailsWith<NullPointerException> { body.contains(null) }
        assertFailsWith<NullPointerException> { body.removeFixture(null as Vector2?) }
        assertFailsWith<NullPointerException> { body.removeFixtures(null) }
        assertFailsWith<NullPointerException> { body.updateRadiusWith(null) }
        assertFailsWith<NullPointerException> { body.computeAABB(null, AABB(0.0, 0.0, 0.0, 0.0)) }
        assertSame(fixture, body.getFixture(0))
    }

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

fun boundsAndPairsUseLiveObjects() {
        val bounds = AxisAlignedBounds(4.0, 4.0)
        assertTrue(bounds.isOutside(org.dyn4j.geometry.AABB(3.0, 3.0, 4.0, 4.0)))
        bounds.translate(3.0, 3.0)
        assertFalse(bounds.isOutside(org.dyn4j.geometry.AABB(3.0, 3.0, 4.0, 4.0)))
        val first = BasicCollisionPair("a", "b")
        assertEquals(first, BasicCollisionPair("b", "a"))
        assertSame(first.getFirst(), first.copy().getFirst())
    }

fun collisionEstimatesAndUnitConversionsMatchBaseline() {
        assertEquals(20, Collisions.getEstimatedCollisionPairs(5))
        assertEquals(1, Collisions.getEstimatedRaycastCollisions(20))
        assertEquals(0.3048, UnitConversion.feetToMeters(1.0), 1.0e-12)
        assertEquals(1.0 / 0.3048, UnitConversion.metersToFeet(1.0), 1.0e-12)
    }

    private class BadFixture : Fixture(Circle(1.0))

fun failuresPreservePublicBehavior() {
        assertFailsWith<org.dyn4j.exception.ArgumentNullException> { Fixture(null) }
        assertFailsWith<org.dyn4j.exception.ArgumentNullException> { Fixture(Circle(1.0)).setFilter(null) }
        assertFailsWith<org.dyn4j.exception.ValueOutOfRangeException> { AxisAlignedBounds(0.0, 2.0) }
        assertFailsWith<CopyException> { Unsafe.copy(BadFixture()) }
        val iterator = TestBody().getFixtureIterator()
        assertFailsWith<IndexOutOfBoundsException> { iterator.next() }
    }

fun copyExceptionFromNamesPreservesMessage() {
        val exception = CopyException("Source", "Copy")
        assertEquals(
            "The copy method on class 'Source' returns an object of class 'Copy'. " +
                "You must override the copy method to return type 'Source'.",
            exception.message
        )
    }

fun nullFirstPairThrowsDuringEquality() {
        val first = BasicCollisionPair<Any?>(null, "x")
        val second = BasicCollisionPair<Any?>(null, "x")
        assertFailsWith<NullPointerException> { first == second }
    }

fun nullCollisionItemCanBeCopied() {
        val item = BasicCollisionItem<TestBody, Fixture>(null, null)
        assertSame(null, item.getBody())
        assertSame(null, item.getFixture())
        assertSame(null, item.copy().getBody())
    }

fun bodyCopyUsesOverriddenFixtureGetter() {
        val replacement = Fixture(Circle(2.0))
        class SubstitutingBody : AbstractCollisionBody<Fixture> {
            constructor() : super()
            private constructor(body: SubstitutingBody) : super(body)
            override fun getFixture(index: Int): Fixture = replacement
            override fun addFixture(convex: Convex?): Fixture = Fixture(convex).also { addFixture(it) }
            override fun getLocalCenter() = Vector2()
            override fun copy() = SubstitutingBody(this)
        }
        val body = SubstitutingBody()
        body.addFixture(Circle(1.0))
        val copy = body.copy()
        assertEquals(2.0, copy.getFixtures()[0].getShape().getRadius(Vector2()))
    }

fun fixtureViewIteratorFailsAfterBodyMutation() {
        val body = TestBody()
        body.addFixture(Circle(1.0))
        val iterator = body.getFixtures().iterator()
        body.addFixture(Circle(2.0))
        assertFailsWith<ConcurrentModificationException> { iterator.next() }
        val listIterator = body.getFixtures().listIterator()
        body.addDirectly(Fixture(Circle(3.0)))
        assertFailsWith<ConcurrentModificationException> { listIterator.next() }
        val empty = TestBody()
        val emptyIterator = empty.getFixtures().iterator()
        empty.removeAllFixtures()
        assertFailsWith<ConcurrentModificationException> { emptyIterator.next() }
    }

fun protectedFixtureIteratorFailsAfterBodyMutation() {
        val body = TestBody()
        body.addFixture(Circle(1.0))
        val iterator = body.protectedIterator()
        body.addFixture(Circle(2.0))
        assertFailsWith<ConcurrentModificationException> { iterator.next() }
    }

fun fixtureViewSubListFailsAfterBodyMutation() {
        val body = TestBody()
        body.addFixture(Circle(1.0))
        val subList = body.getFixtures().subList(0, 1)
        body.addFixture(Circle(2.0))
        assertFailsWith<ConcurrentModificationException> { subList[0] }
    }

fun protectedFixtureSubListFailsAfterBodyMutation() {
        val body = TestBody()
        body.addFixture(Circle(1.0))
        val subList = body.protectedSubList()
        body.addFixture(Circle(2.0))
        assertFailsWith<ConcurrentModificationException> { subList[0] }
    }

fun nestedViewAndProtectedSubListIteratorsFailAfterMutation() {
        val body = TestBody()
        body.addFixture(Circle(1.0))
        val nested = body.getFixtures().subList(0, 1).subList(0, 1)
        val protectedIterator = body.protectedSubList().iterator()
        body.addFixture(Circle(2.0))
        assertFailsWith<ConcurrentModificationException> { nested[0] }
        assertFailsWith<ConcurrentModificationException> { protectedIterator.next() }
    }

fun protectedSubListMutationsRemainLiveAndInvalidateIterators() {
        val body = TestBody()
        body.addFixture(Circle(1.0))
        val subList = body.protectedSubList()
        val added = Fixture(Circle(2.0))
        subList.add(added)
        assertSame(added, body.getFixture(1))
        assertEquals(2, subList.size)
        val iterator = subList.iterator()
        subList.removeAt(0)
        assertFailsWith<ConcurrentModificationException> { iterator.next() }
        assertSame(added, body.getFixtures().single())
    }

fun nullPointOperationsOnEmptyBodyReturnEmptyResults() {
        val body = TestBody()
        assertEquals(null, body.getFixture(null))
        assertTrue(body.getFixtures(null).isEmpty())
        assertEquals(null, body.removeFixture(null as Vector2?))
        assertTrue(body.removeFixtures(null).isEmpty())
        assertFalse(body.contains(null))
    }

fun collisionItemEqualityCallsOtherGettersFirst() {
        val calls = StringBuilder()
        class ObservedItem(private val tag: String) : CollisionItem<TestBody, Fixture> {
            override fun getBody(): TestBody? { calls.append(tag).append("body,"); return null }
            override fun getFixture(): Fixture? { calls.append(tag).append("fixture,"); return null }
            override fun copy(): CollisionItem<TestBody, Fixture> = this
        }
        assertTrue(AbstractCollisionItem.equals(ObservedItem("A"), ObservedItem("B")))
        assertEquals("Bbody,Abody,Bfixture,Afixture,", calls.toString())
    }

fun emptyBodyDefersNullCenterAndTransformChecks() {
        val body = TestBody()
        assertEquals(0.0, body.updateRadiusWith(null))
        assertEquals(AABB(0.0, 0.0, 0.0, 0.0), body.createAABB(null))
        val result = AABB(1.0, 1.0, 2.0, 2.0)
        body.computeAABB(null, result)
        assertEquals(AABB(0.0, 0.0, 0.0, 0.0), result)
    }

fun pairHashCallsEarlierObjectBeforeNullFailure() {
        class HashToken(private val calls: StringBuilder) {
            override fun hashCode(): Int { calls.append("first,"); return 7 }
        }
        val staticCalls = StringBuilder()
        assertFailsWith<NullPointerException> {
            AbstractCollisionPair.getHashCode(HashToken(staticCalls), null)
        }
        assertEquals("first,", staticCalls.toString())
        val pairCalls = StringBuilder()
        assertFailsWith<NullPointerException> {
            BasicCollisionPair<Any?>(HashToken(pairCalls), null).hashCode()
        }
        assertEquals("first,", pairCalls.toString())
    }

fun fixtureCallbacksKeepInitialTraversalExtent() {
        class MutatingFixture(private val body: TestBody) : Fixture(Circle(1.0)) {
            private var added = false
            override fun getShape(): Convex {
                if (!added) { added = true; body.addFixture(Circle(2.0)) }
                return super.getShape()
            }
        }
        fun body() = TestBody().also { it.addFixture(MutatingFixture(it)) }
        val point = Vector2(5.0, 5.0)
        val queried = body()
        assertEquals(null, queried.getFixture(point))
        assertEquals(2, queried.getFixtureCount())
        val queriedMany = body()
        assertTrue(queriedMany.getFixtures(point).isEmpty())
        assertEquals(2, queriedMany.getFixtureCount())
        val contained = body()
        assertFalse(contained.contains(point))
        assertEquals(2, contained.getFixtureCount())
        val radiusBody = body()
        assertEquals(1.0, radiusBody.updateRadiusWith(Vector2()))
        assertEquals(2, radiusBody.getFixtureCount())
        val aabbBody = body()
        assertEquals(AABB(-1.0, -1.0, 1.0, 1.0), aabbBody.createAABB())
        assertEquals(2, aabbBody.getFixtureCount())
    }
}
