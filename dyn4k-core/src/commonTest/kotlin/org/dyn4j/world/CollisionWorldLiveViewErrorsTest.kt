package org.dyn4j.world

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.world.listener.BoundsListener
import org.dyn4j.world.listener.BoundsListenerAdapter
import org.dyn4j.world.listener.CollisionListener
import org.dyn4j.world.listener.CollisionListenerAdapter

val CollisionWorldLiveViewErrorsTest by testSuite {
    test("emptyBodyViewRejectsEveryListMutation") { CollisionWorldLiveViewErrorsTestFixture().run { emptyBodyViewRejectsEveryListMutation() } }
    test("savedBodyViewStaysLiveWithoutExposingMutation") { CollisionWorldLiveViewErrorsTestFixture().run { savedBodyViewStaysLiveWithoutExposingMutation() } }
    test("staleBodySubListsRejectAddBeforeReadingTheirSize") { CollisionWorldLiveViewErrorsTestFixture().run { staleBodySubListsRejectAddBeforeReadingTheirSize() } }
    test("staleBodySubListsCannotCreateReadableNestedViews") { CollisionWorldLiveViewErrorsTestFixture().run { staleBodySubListsCannotCreateReadableNestedViews() } }
    test("staleBodySubListChecksInvalidRangesBeforeFailFastRead") { CollisionWorldLiveViewErrorsTestFixture().run { staleBodySubListChecksInvalidRangesBeforeFailFastRead() } }
    test("sameSizeBodyChangesStillInvalidateSavedSubLists") { CollisionWorldLiveViewErrorsTestFixture().run { sameSizeBodyChangesStillInvalidateSavedSubLists() } }
    test("boundsListenerChildCreatedAfterAddKeepsStaleVersion") { CollisionWorldLiveViewErrorsTestFixture().run { boundsListenerChildCreatedAfterAddKeepsStaleVersion() } }
    test("boundsListenerChildCreatedAfterSameSizeChangeKeepsStaleVersion") { CollisionWorldLiveViewErrorsTestFixture().run { boundsListenerChildCreatedAfterSameSizeChangeKeepsStaleVersion() } }
    test("collisionListenerChildCreatedAfterAddKeepsStaleVersion") { CollisionWorldLiveViewErrorsTestFixture().run { collisionListenerChildCreatedAfterAddKeepsStaleVersion() } }
    test("collisionListenerChildCreatedAfterSameSizeChangeKeepsStaleVersion") { CollisionWorldLiveViewErrorsTestFixture().run { collisionListenerChildCreatedAfterSameSizeChangeKeepsStaleVersion() } }
}

internal enum class WorldViewOperation {
    CHILD_AFTER_ADD, GRANDCHILD_AFTER_ADD, CHILD_AFTER_REPLACE,
    READ_AFTER_ADD, GRANDCHILD_READ_AFTER_ADD, READ_AFTER_REPLACE, SAVED_NESTED_SIZE,
    NEGATIVE_RANGE, OVERSIZED_RANGE, REVERSED_RANGE,
    EMPTY_CLEAR_CHILD_SIZE, EMPTY_CLEAR_PARENT_READ, EMPTY_CLEAR_ROOT_ITERATOR,
    EMPTY_CLEAR_SIBLING_READ, EMPTY_CLEAR_PUBLIC_READ
}

internal enum class WorldViewOutcome { VALUE, CONCURRENT_MODIFICATION, INDEX_OUT_OF_BOUNDS, ILLEGAL_ARGUMENT }

internal expect fun worldNestedViewOutcome(operation: WorldViewOperation): WorldViewOutcome

internal fun <T> assertWorldViewOutcome(expected: WorldViewOutcome, action: () -> T): T? {
    var value: T? = null
    val outcome = try {
        value = action()
        WorldViewOutcome.VALUE
    } catch (_: ConcurrentModificationException) {
        WorldViewOutcome.CONCURRENT_MODIFICATION
    } catch (_: IndexOutOfBoundsException) {
        WorldViewOutcome.INDEX_OUT_OF_BOUNDS
    } catch (_: IllegalArgumentException) {
        WorldViewOutcome.ILLEGAL_ARGUMENT
    }
    assertEquals(expected, outcome)
    return value
}

private class CollisionWorldLiveViewErrorsTestFixture  {
    private fun <T> assertNestedViewMatchesRuntime(view: List<T>?, readableElement: T, operation: WorldViewOperation) {
        if (view != null) {
            val expected = worldNestedViewOutcome(operation)
            val read = assertWorldViewOutcome(expected) { view[0] }
            if (expected == WorldViewOutcome.VALUE) assertSame(readableElement, read)
        }
    }

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

fun staleBodySubListsCannotCreateReadableNestedViews() {
        val world = World<Body>()
        val first = Body()
        world.addBody(first)
        val view = world.getBodies() as MutableList<Body>
        val subList = view.subList(0, 1)
        val nestedSubList = subList.subList(0, 1)
        assertSame(first, nestedSubList[0])

        world.addBody(Body())

        val child = assertWorldViewOutcome(worldNestedViewOutcome(WorldViewOperation.CHILD_AFTER_ADD)) { subList.subList(0, 1) }
        val grandchild = assertWorldViewOutcome(worldNestedViewOutcome(WorldViewOperation.GRANDCHILD_AFTER_ADD)) { nestedSubList.subList(0, 1) }
        assertFailsWith<ConcurrentModificationException> { subList.size }
        val nestedSizeOutcome = worldNestedViewOutcome(WorldViewOperation.SAVED_NESTED_SIZE)
        val nestedSize = assertWorldViewOutcome(nestedSizeOutcome) { nestedSubList.size }
        if (nestedSizeOutcome == WorldViewOutcome.VALUE) assertEquals(1, nestedSize)
        assertNestedViewMatchesRuntime(child, first, WorldViewOperation.READ_AFTER_ADD)
        assertNestedViewMatchesRuntime(grandchild, first, WorldViewOperation.GRANDCHILD_READ_AFTER_ADD)
        assertSame(first, view.subList(0, 1).subList(0, 1)[0])
    }

fun staleBodySubListChecksInvalidRangesBeforeFailFastRead() {
        val world = World<Body>()
        world.addBody(Body())
        val subList = (world.getBodies() as MutableList<Body>).subList(0, 1)

        world.addBody(Body())

        assertWorldViewOutcome(worldNestedViewOutcome(WorldViewOperation.NEGATIVE_RANGE)) { subList.subList(-1, 1) }
        assertWorldViewOutcome(worldNestedViewOutcome(WorldViewOperation.OVERSIZED_RANGE)) { subList.subList(0, 2) }
        assertWorldViewOutcome(worldNestedViewOutcome(WorldViewOperation.REVERSED_RANGE)) { subList.subList(1, 0) }
    }

fun sameSizeBodyChangesStillInvalidateSavedSubLists() {
        val world = World<Body>()
        val first = Body()
        world.addBody(first)
        val view = world.getBodies() as MutableList<Body>
        val subList = view.subList(0, 1)

        world.removeBody(first)
        world.addBody(Body())

        assertEquals(1, view.size)
        val child = assertWorldViewOutcome(worldNestedViewOutcome(WorldViewOperation.CHILD_AFTER_REPLACE)) { subList.subList(0, 1) }
        assertFailsWith<ConcurrentModificationException> { subList.size }
        assertNestedViewMatchesRuntime(child, view[0], WorldViewOperation.READ_AFTER_REPLACE)
    }

fun boundsListenerChildCreatedAfterAddKeepsStaleVersion() {
        val world = World<Body>()
        val first = BoundsListenerAdapter<Body, BodyFixture>()
        world.addBoundsListener(first)
        val view = world.getBoundsListeners() as MutableList<BoundsListener<Body, BodyFixture>>
        val stale = view.subList(0, 1)

        world.addBoundsListener(BoundsListenerAdapter())

        val child = assertWorldViewOutcome(worldNestedViewOutcome(WorldViewOperation.CHILD_AFTER_ADD)) { stale.subList(0, 1) }
        assertFailsWith<ConcurrentModificationException> { stale.size }
        assertNestedViewMatchesRuntime(child, first, WorldViewOperation.READ_AFTER_ADD)
        if (child != null) assertFailsWith<UnsupportedOperationException> { child.add(first) }
        assertSame(view, world.getBoundsListeners())
        assertSame(first, view[0])
    }

fun boundsListenerChildCreatedAfterSameSizeChangeKeepsStaleVersion() {
        val world = World<Body>()
        val first = BoundsListenerAdapter<Body, BodyFixture>()
        val second = BoundsListenerAdapter<Body, BodyFixture>()
        world.addBoundsListener(first)
        val view = world.getBoundsListeners() as MutableList<BoundsListener<Body, BodyFixture>>
        val stale = view.subList(0, 1)

        world.removeBoundsListener(first)
        world.addBoundsListener(second)

        val child = assertWorldViewOutcome(worldNestedViewOutcome(WorldViewOperation.CHILD_AFTER_REPLACE)) { stale.subList(0, 1) }
        assertFailsWith<ConcurrentModificationException> { stale.size }
        assertNestedViewMatchesRuntime(child, second, WorldViewOperation.READ_AFTER_REPLACE)
        if (child != null) assertFailsWith<UnsupportedOperationException> { child.add(first) }
        assertSame(second, view[0])
    }

fun collisionListenerChildCreatedAfterAddKeepsStaleVersion() {
        val world = World<Body>()
        val first = CollisionListenerAdapter<Body, BodyFixture>()
        world.addCollisionListener(first)
        val view = world.getCollisionListeners() as MutableList<CollisionListener<Body, BodyFixture>>
        val stale = view.subList(0, 1)

        world.addCollisionListener(CollisionListenerAdapter())

        val child = assertWorldViewOutcome(worldNestedViewOutcome(WorldViewOperation.CHILD_AFTER_ADD)) { stale.subList(0, 1) }
        assertFailsWith<ConcurrentModificationException> { stale.size }
        assertNestedViewMatchesRuntime(child, first, WorldViewOperation.READ_AFTER_ADD)
        if (child != null) assertFailsWith<UnsupportedOperationException> { child.add(first) }
        assertSame(view, world.getCollisionListeners())
        assertSame(first, view[0])
    }

fun collisionListenerChildCreatedAfterSameSizeChangeKeepsStaleVersion() {
        val world = World<Body>()
        val first = CollisionListenerAdapter<Body, BodyFixture>()
        val second = CollisionListenerAdapter<Body, BodyFixture>()
        world.addCollisionListener(first)
        val view = world.getCollisionListeners() as MutableList<CollisionListener<Body, BodyFixture>>
        val stale = view.subList(0, 1)

        world.removeCollisionListener(first)
        world.addCollisionListener(second)

        val child = assertWorldViewOutcome(worldNestedViewOutcome(WorldViewOperation.CHILD_AFTER_REPLACE)) { stale.subList(0, 1) }
        assertFailsWith<ConcurrentModificationException> { stale.size }
        assertNestedViewMatchesRuntime(child, second, WorldViewOperation.READ_AFTER_REPLACE)
        if (child != null) assertFailsWith<UnsupportedOperationException> { child.add(first) }
        assertSame(second, view[0])
    }
}
