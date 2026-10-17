package org.dyn4j.collision.broadphase

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotSame
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.geometry.AABB
import org.dyn4j.geometry.Ray
import org.dyn4j.geometry.Vector2

class BroadphaseQueryTest {
    private val producer = object : AABBProducer<AABB> {
        override fun compute(item: AABB): AABB = item.copy()
        override fun compute(item: AABB, result: AABB) { result.set(item) }
    }
    private val filter = object : BroadphaseFilter<AABB> {
        override fun isAllowed(first: AABB?, second: AABB?) = first !== second
    }

    @Test
    fun bruteForceQueriesReturnMutablePairsAndSnapshotListCopies() {
        val broadphase = BruteForceBroadphase(filter, producer)
        val a = AABB(0.0, 0.0, 2.0, 2.0)
        val b = AABB(1.0, 1.0, 3.0, 3.0)
        val c = AABB(1.5, 1.5, 2.5, 2.5)
        broadphase.add(a)
        broadphase.add(b)
        broadphase.add(c)
        val iterator = broadphase.detectIterator(true)
        assertTrue(iterator.hasNext())
        val first = iterator.next()
        val second = iterator.next()
        assertSame(first, second)
        val pairs = broadphase.detect(true)
        assertEquals(3, pairs.size)
        assertNotSame(pairs[0], pairs[1])
        assertEquals(listOf(a, b, c), broadphase.detect(AABB(-1.0, -1.0, 4.0, 4.0)))
        assertEquals(listOf(a, b, c), broadphase.raycast(Ray(Vector2(-1.0, 1.6), Vector2(1.0, 0.0)), 0.0))
    }

    @Test
    fun sapTracksUpdatedObjectsAndExposesExpandedBounds() {
        val broadphase = Sap(filter, producer, StaticValueAABBExpansionMethod(0.2))
        val a = AABB(0.0, 0.0, 1.0, 1.0)
        val b = AABB(0.5, 0.5, 1.5, 1.5)
        broadphase.add(a)
        broadphase.add(b)
        assertEquals(1, broadphase.detect(true).size)
        assertEquals(-0.1, broadphase.getAABB(a).getMinX())
        broadphase.setUpdateTrackingEnabled(true)
        broadphase.clearUpdates()
        assertEquals(0, broadphase.detect(false).size)
        broadphase.setUpdated(a)
        assertTrue(broadphase.isUpdated(a))
        assertEquals(1, broadphase.detect(false).size)
    }

    @Test
    fun dynamicTreeBalancesAndReturnsOverlappingPairs() {
        val broadphase = DynamicAABBTree(filter, producer, NullAABBExpansionMethod())
        val a = AABB(0.0, 0.0, 2.0, 2.0)
        val b = AABB(1.0, 1.0, 3.0, 3.0)
        val c = AABB(4.0, 4.0, 5.0, 5.0)
        broadphase.add(a)
        broadphase.add(b)
        broadphase.add(c)
        assertEquals(1, broadphase.detect(true).size)
        assertTrue(broadphase.getHeight() > 0)
        assertTrue(broadphase.getPerimeterRatio() > 0.0)
        broadphase.optimize()
        assertEquals(1, broadphase.detect(true).size)
        assertEquals(listOf(a, b), broadphase.detect(AABB(0.5, 0.5, 2.5, 2.5)))
    }
}
