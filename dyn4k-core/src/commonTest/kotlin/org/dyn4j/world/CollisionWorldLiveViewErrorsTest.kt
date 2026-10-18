package org.dyn4j.world

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.dynamics.Body

class CollisionWorldLiveViewErrorsTest {
    @Test
    fun emptyBodyViewRejectsEveryListMutation() {
        val world = World<Body>()
        val view = world.getBodies() as MutableList<Body>
        val emptySubList = view.subList(0, 0)

        assertTrue(view is RandomAccess)
        assertSame(view, world.getBodies())
        assertFailsWith<UnsupportedOperationException> { view.add(Body()) }
        assertFailsWith<UnsupportedOperationException> { view.add(0, Body()) }
        assertFailsWith<UnsupportedOperationException> { view.addAll(emptyList()) }
        assertFailsWith<UnsupportedOperationException> { view.addAll(0, emptyList()) }
        assertFailsWith<UnsupportedOperationException> { view.remove(Body()) }
        assertFailsWith<UnsupportedOperationException> { view.removeAt(0) }
        assertFailsWith<UnsupportedOperationException> { view.removeAll(emptyList()) }
        assertFailsWith<UnsupportedOperationException> { view.retainAll(emptyList()) }
        assertFailsWith<UnsupportedOperationException> { view.clear() }
        assertFailsWith<UnsupportedOperationException> { emptySubList.clear() }

        val iterator = view.listIterator()
        assertFailsWith<UnsupportedOperationException> { iterator.remove() }
        assertFailsWith<UnsupportedOperationException> { iterator.set(Body()) }
        assertFailsWith<UnsupportedOperationException> { iterator.add(Body()) }
        assertTrue(world.isEmpty())
    }

    @Test
    fun savedBodyViewStaysLiveWithoutExposingMutation() {
        val world = World<Body>()
        val view = world.getBodies() as MutableList<Body>
        val first = Body()
        val second = Body()
        world.addBody(first)
        world.addBody(second)

        assertEquals(2, view.size)
        assertSame(first, view[0])
        assertSame(second, view[1])
        val subList = view.subList(0, 1)
        assertTrue(subList is RandomAccess)
        assertSame(first, subList[0])
        assertFailsWith<UnsupportedOperationException> { view[0] = second }
        assertFailsWith<UnsupportedOperationException> { view.removeAll(listOf(first)) }
        assertFailsWith<UnsupportedOperationException> { view.retainAll(listOf(first)) }
        assertFailsWith<UnsupportedOperationException> { subList[0] = second }
        assertFailsWith<UnsupportedOperationException> { subList.removeAt(0) }
        assertFailsWith<UnsupportedOperationException> { subList.add(Body()) }

        val iterator = view.listIterator()
        assertSame(first, iterator.next())
        assertFailsWith<UnsupportedOperationException> { iterator.remove() }
        assertFailsWith<UnsupportedOperationException> { iterator.set(second) }
        assertFailsWith<UnsupportedOperationException> { iterator.add(Body()) }
        assertEquals(2, world.getBodyCount())
        assertSame(first, world.getBody(0))
        assertSame(second, world.getBody(1))

        world.removeBody(first)
        assertSame(view, world.getBodies())
        assertEquals(1, view.size)
        assertSame(second, view[0])
    }

    @Test
    fun staleBodySubListsRejectAddBeforeReadingTheirSize() {
        val world = World<Body>()
        val first = Body()
        world.addBody(first)
        val view = world.getBodies() as MutableList<Body>
        val subList = view.subList(0, 1)
        val nestedSubList = subList.subList(0, 1)
        val iterator = view.listIterator()

        world.addBody(Body())

        assertFailsWith<UnsupportedOperationException> { subList.add(Body()) }
        assertFailsWith<UnsupportedOperationException> { nestedSubList.add(Body()) }
        assertFailsWith<UnsupportedOperationException> { subList.add(-1, Body()) }
        assertFailsWith<UnsupportedOperationException> { subList.addAll(-1, emptyList()) }
        assertFailsWith<UnsupportedOperationException> { iterator.remove() }
        assertEquals(2, view.size)
        assertSame(first, view[0])
    }

    @Test
    fun staleBodySubListsCannotCreateReadableNestedViews() {
        val world = World<Body>()
        val first = Body()
        world.addBody(first)
        val view = world.getBodies() as MutableList<Body>
        val subList = view.subList(0, 1)
        val nestedSubList = subList.subList(0, 1)
        assertSame(first, nestedSubList[0])

        world.addBody(Body())

        assertFailsWith<ConcurrentModificationException> { subList.subList(0, 1)[0] }
        assertFailsWith<ConcurrentModificationException> { nestedSubList.subList(0, 1)[0] }
        assertSame(first, view.subList(0, 1).subList(0, 1)[0])
    }

    @Test
    fun staleBodySubListChecksInvalidRangesBeforeFailFastRead() {
        val world = World<Body>()
        world.addBody(Body())
        val subList = (world.getBodies() as MutableList<Body>).subList(0, 1)

        world.addBody(Body())

        assertFailsWith<IndexOutOfBoundsException> { subList.subList(-1, 1) }
        assertFailsWith<IndexOutOfBoundsException> { subList.subList(0, 2) }
        assertFailsWith<IllegalArgumentException> { subList.subList(1, 0) }
    }

    @Test
    fun sameSizeBodyChangesStillInvalidateSavedSubLists() {
        val world = World<Body>()
        val first = Body()
        world.addBody(first)
        val view = world.getBodies() as MutableList<Body>
        val subList = view.subList(0, 1)

        world.removeBody(first)
        world.addBody(Body())

        assertEquals(1, view.size)
        assertFailsWith<ConcurrentModificationException> { subList.subList(0, 1)[0] }
    }
}
