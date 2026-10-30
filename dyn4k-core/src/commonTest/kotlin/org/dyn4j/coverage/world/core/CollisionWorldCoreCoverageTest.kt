/*
 * Copyright (c) 2010-2020 William Bittle  http://www.dyn4j.org/
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
package org.dyn4j.coverage.world.core

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import kotlin.test.assertNotSame
import kotlin.test.assertNull
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.collision.AxisAlignedBounds
import org.dyn4j.collision.CategoryFilter
import org.dyn4j.collision.CollisionItem
import org.dyn4j.collision.CollisionPair
import org.dyn4j.collision.broadphase.CollisionItemAABBProducer
import org.dyn4j.collision.broadphase.CollisionItemBroadphaseDetectorAdapter
import org.dyn4j.collision.broadphase.CollisionItemBroadphaseFilter
import org.dyn4j.collision.broadphase.Sap
import org.dyn4j.collision.broadphase.StaticValueAABBExpansionMethod
import org.dyn4j.collision.continuous.ConservativeAdvancement
import org.dyn4j.collision.manifold.ClippingManifoldSolver
import org.dyn4j.collision.narrowphase.Gjk
import org.dyn4j.collision.narrowphase.LinkPostProcessor
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.geometry.AABB
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Ray
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2
import org.dyn4j.world.AbstractCollisionWorld
import org.dyn4j.world.WorldCollisionData
import org.dyn4j.world.BroadphaseCollisionData
import org.dyn4j.world.NarrowphaseCollisionData
import org.dyn4j.world.ManifoldCollisionData
import org.dyn4j.world.DetectFilter
import org.dyn4j.world.listener.BoundsListenerAdapter
import org.dyn4j.world.listener.CollisionListenerAdapter
import kotlin.math.PI
import kotlin.math.sqrt

val CollisionWorldCoreCoverageTest by testSuite {
    test("createSuccess") { CollisionWorldCoreCoverageTestFixture().run { createSuccess() } }
    test("addBody") { CollisionWorldCoreCoverageTestFixture().run { addBody() } }
    test("addNullBody") { CollisionWorldCoreCoverageTestFixture().run { addNullBody() } }
    test("addSameBodyToSameWorld") { CollisionWorldCoreCoverageTestFixture().run { addSameBodyToSameWorld() } }
    test("addBodyFromOtherWorld") { CollisionWorldCoreCoverageTestFixture().run { addBodyFromOtherWorld() } }
    test("removeAllBodies") { CollisionWorldCoreCoverageTestFixture().run { removeAllBodies() } }
    test("containsBody") { CollisionWorldCoreCoverageTestFixture().run { containsBody() } }
    test("removeBodyNegativeIndex") { CollisionWorldCoreCoverageTestFixture().run { removeBodyNegativeIndex() } }
    test("removeBodyBadIndex") { CollisionWorldCoreCoverageTestFixture().run { removeBodyBadIndex() } }
    test("removeBody") { CollisionWorldCoreCoverageTestFixture().run { removeBody() } }
    test("getBodies") { CollisionWorldCoreCoverageTestFixture().run { getBodies() } }
    test("getBodiesAndRemove") { CollisionWorldCoreCoverageTestFixture().run { getBodiesAndRemove() } }
    test("getBodiesAndAdd") { CollisionWorldCoreCoverageTestFixture().run { getBodiesAndAdd() } }
    test("getBodyAtIndex") { CollisionWorldCoreCoverageTestFixture().run { getBodyAtIndex() } }
    test("getBodyAtNegativeIndex") { CollisionWorldCoreCoverageTestFixture().run { getBodyAtNegativeIndex() } }
    test("getBodyAtBadIndex") { CollisionWorldCoreCoverageTestFixture().run { getBodyAtBadIndex() } }
    test("getBodyCount") { CollisionWorldCoreCoverageTestFixture().run { getBodyCount() } }
    test("isEmpty") { CollisionWorldCoreCoverageTestFixture().run { isEmpty() } }
    test("getBodyIterator") { CollisionWorldCoreCoverageTestFixture().run { getBodyIterator() } }
    test("getBodyIteratorFailure") { CollisionWorldCoreCoverageTestFixture().run { getBodyIteratorFailure() } }
    test("getAndSetBounds") { CollisionWorldCoreCoverageTestFixture().run { getAndSetBounds() } }
    test("getAndSetBroadphaseDetector") { CollisionWorldCoreCoverageTestFixture().run { getAndSetBroadphaseDetector() } }
    test("setNullBroadphaseDetector") { CollisionWorldCoreCoverageTestFixture().run { setNullBroadphaseDetector() } }
    test("getAndSetBroadphaseFilter") { CollisionWorldCoreCoverageTestFixture().run { getAndSetBroadphaseFilter() } }
    test("setNullBroadphaseFilter") { CollisionWorldCoreCoverageTestFixture().run { setNullBroadphaseFilter() } }
    test("getAndSetNarrowphaseDetector") { CollisionWorldCoreCoverageTestFixture().run { getAndSetNarrowphaseDetector() } }
    test("setNullNarrowphaseDetector") { CollisionWorldCoreCoverageTestFixture().run { setNullNarrowphaseDetector() } }
    test("getAndSetNarrowphasePostProcessor") { CollisionWorldCoreCoverageTestFixture().run { getAndSetNarrowphasePostProcessor() } }
    test("setNullNarrowphasePostProcessor") { CollisionWorldCoreCoverageTestFixture().run { setNullNarrowphasePostProcessor() } }
    test("setManifoldSolver") { CollisionWorldCoreCoverageTestFixture().run { setManifoldSolver() } }
    test("setNullManifoldSolver") { CollisionWorldCoreCoverageTestFixture().run { setNullManifoldSolver() } }
    test("setTimeOfImpactDetector") { CollisionWorldCoreCoverageTestFixture().run { setTimeOfImpactDetector() } }
    test("setNullTimeOfImpactDetector") { CollisionWorldCoreCoverageTestFixture().run { setNullTimeOfImpactDetector() } }
    test("setRaycastDetector") { CollisionWorldCoreCoverageTestFixture().run { setRaycastDetector() } }
    test("setNullRaycastDetector") { CollisionWorldCoreCoverageTestFixture().run { setNullRaycastDetector() } }
    test("shift") { CollisionWorldCoreCoverageTestFixture().run { shift() } }
    test("getCollisionData") { CollisionWorldCoreCoverageTestFixture().run { getCollisionData() } }
    test("getCollisionDataIterator") { CollisionWorldCoreCoverageTestFixture().run { getCollisionDataIterator() } }
    test("getCollisionDataIteratorFailure") { CollisionWorldCoreCoverageTestFixture().run { getCollisionDataIteratorFailure() } }
    test("fixtureModification") { CollisionWorldCoreCoverageTestFixture().run { fixtureModification() } }
    test("listeners") { CollisionWorldCoreCoverageTestFixture().run { listeners() } }
    test("getSetUserData") { CollisionWorldCoreCoverageTestFixture().run { getSetUserData() } }
    test("detectBroadphaseFilterNotAllowed") { CollisionWorldCoreCoverageTestFixture().run { detectBroadphaseFilterNotAllowed() } }
    test("detectNoLongerColliding") { CollisionWorldCoreCoverageTestFixture().run { detectNoLongerColliding() } }
    test("detectIteratorRemove") { CollisionWorldCoreCoverageTestFixture().run { detectIteratorRemove() } }
    test("detectWithListeners") { CollisionWorldCoreCoverageTestFixture().run { detectWithListeners() } }
    test("detectWithFixtureModification") { CollisionWorldCoreCoverageTestFixture().run { detectWithFixtureModification() } }
    test("detectWithBounds") { CollisionWorldCoreCoverageTestFixture().run { detectWithBounds() } }
    test("detectWithDisabled") { CollisionWorldCoreCoverageTestFixture().run { detectWithDisabled() } }
    test("detectAABB") { CollisionWorldCoreCoverageTestFixture().run { detectAABB() } }
    test("detectAABBAgainstSingleBody") { CollisionWorldCoreCoverageTestFixture().run { detectAABBAgainstSingleBody() } }
    test("detectAABBIterator") { CollisionWorldCoreCoverageTestFixture().run { detectAABBIterator() } }
    test("detectAABBIteratorFailures") { CollisionWorldCoreCoverageTestFixture().run { detectAABBIteratorFailures() } }
    test("detectConvex") { CollisionWorldCoreCoverageTestFixture().run { detectConvex() } }
    test("detectConvexAgainstSingleBody") { CollisionWorldCoreCoverageTestFixture().run { detectConvexAgainstSingleBody() } }
    test("detectContexIterator") { CollisionWorldCoreCoverageTestFixture().run { detectContexIterator() } }
    test("detectConvexIteratorFailures") { CollisionWorldCoreCoverageTestFixture().run { detectConvexIteratorFailures() } }
    test("raycast") { CollisionWorldCoreCoverageTestFixture().run { raycast() } }
    test("raycastAgainstSingleBody") { CollisionWorldCoreCoverageTestFixture().run { raycastAgainstSingleBody() } }
    test("raycastIterator") { CollisionWorldCoreCoverageTestFixture().run { raycastIterator() } }
    test("raycastIteratorFailures") { CollisionWorldCoreCoverageTestFixture().run { raycastIteratorFailures() } }
    test("convexCast") { CollisionWorldCoreCoverageTestFixture().run { convexCast() } }
    test("convexCastAgainstSingleBody") { CollisionWorldCoreCoverageTestFixture().run { convexCastAgainstSingleBody() } }
    test("convexCastIterator") { CollisionWorldCoreCoverageTestFixture().run { convexCastIterator() } }
    test("convexCastIteratorFailures") { CollisionWorldCoreCoverageTestFixture().run { convexCastIteratorFailures() } }
}

internal open class CoreCollisionWorld(capacity: Int = 10) :
    AbstractCollisionWorld<Body, BodyFixture, WorldCollisionData<Body>>(capacity) {
    var created = 0
    override fun createCollisionData(pair: CollisionPair<CollisionItem<Body, BodyFixture>>): WorldCollisionData<Body> {
        created++
        return WorldCollisionData(pair)
    }
    override fun processCollisions(iterator: MutableIterator<WorldCollisionData<Body>>) {
        while (iterator.hasNext()) iterator.next()
    }
    fun scan() = detect()
    fun collisionCount() = collisionData.size
    fun broadphaseAabb(body: Body, fixture: BodyFixture) = broadphaseDetector.getAABB(body, fixture)
    fun bodyBackingSize() = bodies.size
    fun boundsListenerBackingSize() = boundsListeners.size
    fun collisionListenerBackingSize() = collisionListeners.size
    fun containsInBroadphase(body: Body, fixture: BodyFixture) =
        broadphaseDetector.contains(body) && broadphaseDetector.contains(body, fixture)
}

private fun circleBody(): Body = Body().also {
    it.addFixture(Circle(1.0))
    it.setMass(MassType.NORMAL)
}

private fun queryWorld(): Triple<CoreCollisionWorld, Body, Body> {
    val world = CoreCollisionWorld()
    val first = Body().also { it.addFixture(Circle(0.5)); it.setMass(MassType.NORMAL); it.translate(-1.0, 1.0) }
    val second = Body().also { it.addFixture(Geometry.createRectangle(1.0, 0.5)); it.setMass(MassType.NORMAL) }
    val category = CategoryFilter(1L, 3L)
    first.getFixture(0).setFilter(category)
    second.getFixture(0).setFilter(category)
    world.addBody(first)
    world.addBody(second)
    return Triple(world, first, second)
}

private fun castWorld(extraFixture: Boolean): Triple<CoreCollisionWorld, Body, Body> {
    val world = CoreCollisionWorld()
    val first = Body().also {
        it.addFixture(Circle(0.5))
        if (extraFixture) it.addFixture(Circle(0.5).also { shape -> shape.translate(0.75, 0.75) })
        it.setMass(MassType.NORMAL)
        it.translate(1.0, 1.0)
    }
    val second = Body().also { it.addFixture(Geometry.createRectangle(1.0, 0.5)); it.setMass(MassType.NORMAL) }
    val category = CategoryFilter(1L, 3L)
    first.getFixtures().forEach { it.setFilter(category) }
    second.getFixture(0).setFilter(category)
    world.addBody(first)
    world.addBody(second)
    return Triple(world, first, second)
}

private class CollisionWorldCoreCoverageTestFixture  {
fun createSuccess() {
        for (capacity in listOf(10, 16, -16, 0)) {
            val world = CoreCollisionWorld(capacity)
            assertTrue(world.getBodies().isEmpty())
            assertEquals(0, world.bodyBackingSize())
            assertEquals(0, world.collisionCount())
            assertEquals(0, world.boundsListenerBackingSize())
            assertEquals(0, world.collisionListenerBackingSize())
            assertNull(world.getBounds())
            assertNotNull(world.getBroadphaseDetector())
            assertNotNull(world.getBroadphaseCollisionDataFilter())
            assertNotNull(world.getNarrowphaseDetector())
            assertNotNull(world.getNarrowphasePostProcessor())
            assertNotNull(world.getManifoldSolver())
            assertNotNull(world.getRaycastDetector())
            assertNotNull(world.getTimeOfImpactDetector())
            assertNull(world.getUserData())
        }
    }

fun addBody() {
        val world = CoreCollisionWorld()
        val body = circleBody()
        val fixture = body.getFixture(0)
        assertNull(body.getOwner())
        assertNull(body.getFixtureModificationHandler())
        world.addBody(body)
        assertEquals(1, world.getBodyCount())
        assertEquals(1, world.bodyBackingSize())
        assertSame(world, body.getOwner())
        assertNotNull(body.getFixtureModificationHandler())
        assertTrue(world.containsInBroadphase(body, fixture))
    }

fun addNullBody() = assertFailsWith<NullPointerException> { CoreCollisionWorld().addBody(null) }.let { Unit }
fun addSameBodyToSameWorld() {
        val world = CoreCollisionWorld()
        val body = Body()
        world.addBody(body)
        assertFailsWith<IllegalArgumentException> { world.addBody(body) }
        assertEquals(1, world.getBodyCount())
    }
fun addBodyFromOtherWorld() {
        val first = CoreCollisionWorld()
        val second = CoreCollisionWorld()
        val body = Body()
        first.addBody(body)
        assertFailsWith<IllegalArgumentException> { second.addBody(body) }
        assertSame(first, body.getOwner())
    }

fun removeAllBodies() {
        val world = CoreCollisionWorld()
        val first = circleBody()
        val second = Body().also { it.addFixture(Geometry.createEquilateralTriangle(0.5)); it.setMass(MassType.NORMAL) }
        world.addBody(first)
        world.addBody(second)
        world.scan()
        assertEquals(1, world.collisionCount())
        assertEquals(1, world.created)
        assertTrue(world.containsInBroadphase(first, first.getFixture(0)))
        assertTrue(world.containsInBroadphase(second, second.getFixture(0)))
        world.removeAllBodies()
        for (body in listOf(first, second)) {
            assertNull(body.getOwner())
            assertNull(body.getFixtureModificationHandler())
            assertFalse(world.containsInBroadphase(body, body.getFixture(0)))
        }
        assertEquals(0, world.getBodyCount())
        assertEquals(0, world.collisionCount())
    }

fun containsBody() {
        val world = CoreCollisionWorld()
        val first = Body()
        val second = Body()
        world.addBody(first)
        world.addBody(second)
        assertTrue(world.containsBody(first))
        assertTrue(world.containsBody(second))
        assertFalse(world.containsBody(null))
        assertFalse(world.containsBody(Body()))
    }

fun removeBodyNegativeIndex() = assertFailsWith<IndexOutOfBoundsException> { CoreCollisionWorld().removeBody(-1) }.let { Unit }
fun removeBodyBadIndex() = assertFailsWith<IndexOutOfBoundsException> { CoreCollisionWorld().removeBody(2) }.let { Unit }

fun removeBody() {
        val world = CoreCollisionWorld()
        val first = circleBody()
        val second = Body().also { it.addFixture(Geometry.createEquilateralTriangle(0.5)); it.setMass(MassType.NORMAL) }
        world.addBody(first)
        world.addBody(second)
        world.scan()
        assertFalse(world.removeBody(null as Body?))
        assertFalse(world.removeBody(Body()))
        assertTrue(world.removeBody(first))
        assertNull(first.getOwner())
        assertNull(first.getFixtureModificationHandler())
        assertFalse(world.containsInBroadphase(first, first.getFixture(0)))
        assertSame(world, second.getOwner())
        assertTrue(world.containsInBroadphase(second, second.getFixture(0)))
        assertEquals(1, world.collisionCount())
        world.scan()
        assertEquals(0, world.collisionCount())
        assertTrue(world.removeBody(0))
        assertNull(second.getOwner())
        assertNull(second.getFixtureModificationHandler())
        assertEquals(0, world.getBodyCount())
    }

fun getBodies() {
        val world = CoreCollisionWorld()
        val view = world.getBodies()
        val first = Body()
        val second = Body()
        world.addBody(first)
        world.addBody(second)
        assertEquals(2, view.size)
        assertSame(first, view[0])
        assertSame(second, view[1])
    }
fun getBodiesAndRemove() {
        val world = CoreCollisionWorld()
        assertFailsWith<UnsupportedOperationException> { (world.getBodies() as MutableList<Body>).removeAt(0) }
    }
fun getBodiesAndAdd() {
        val world = CoreCollisionWorld()
        assertFailsWith<UnsupportedOperationException> { (world.getBodies() as MutableList<Body>).add(Body()) }
    }
fun getBodyAtIndex() {
        val world = CoreCollisionWorld()
        val first = Body()
        val second = Body()
        world.addBody(first)
        world.addBody(second)
        assertSame(first, world.getBody(0))
        assertSame(second, world.getBody(1))
    }
fun getBodyAtNegativeIndex() = assertFailsWith<IndexOutOfBoundsException> { CoreCollisionWorld().getBody(-1) }.let { Unit }
fun getBodyAtBadIndex() = assertFailsWith<IndexOutOfBoundsException> { CoreCollisionWorld().getBody(2) }.let { Unit }
fun getBodyCount() {
        val world = CoreCollisionWorld()
        assertEquals(0, world.getBodyCount())
        world.addBody(Body())
        world.addBody(Body())
        assertEquals(2, world.getBodyCount())
    }
fun isEmpty() {
        val world = CoreCollisionWorld()
        assertTrue(world.isEmpty())
        world.addBody(Body())
        world.addBody(Body())
        assertFalse(world.isEmpty())
    }
fun getBodyIterator() {
        val world = CoreCollisionWorld()
        val first = Body()
        val second = Body()
        world.addBody(first)
        world.addBody(second)
        val iterator = world.getBodyIterator()
        assertSame(first, iterator.next())
        assertSame(second, iterator.next())
        assertFalse(iterator.hasNext())
        val removing = world.getBodyIterator()
        assertSame(first, removing.next())
        removing.remove()
        assertEquals(1, world.getBodyCount())
        assertSame(second, removing.next())
        removing.remove()
        assertEquals(0, world.getBodyCount())
    }
fun getBodyIteratorFailure() {
        val world = CoreCollisionWorld()
        world.addBody(Body())
        world.addBody(Body())
        val overflow = world.getBodyIterator()
        overflow.next()
        overflow.next()
        assertFailsWith<IndexOutOfBoundsException> { overflow.next() }
        val beforeNext = world.getBodyIterator()
        assertFailsWith<IllegalStateException> { beforeNext.remove() }
        beforeNext.next()
        beforeNext.remove()
        assertFailsWith<IllegalStateException> { beforeNext.remove() }
        val modified = world.getBodyIterator()
        modified.next()
        world.removeAllBodies()
        assertFailsWith<IndexOutOfBoundsException> { modified.remove() }
    }

fun getAndSetBounds() {
        val world = CoreCollisionWorld()
        assertNull(world.getBounds())
        val bounds = AxisAlignedBounds(10.0, 10.0)
        world.setBounds(bounds)
        assertSame(bounds, world.getBounds())
        world.setBounds(null)
        assertNull(world.getBounds())
    }
fun getAndSetBroadphaseDetector() {
        val world = CoreCollisionWorld()
        val body = circleBody()
        world.addBody(body)
        val original = world.getBroadphaseDetector()
        val replacement = CollisionItemBroadphaseDetectorAdapter(
            Sap(CollisionItemBroadphaseFilter<Body, BodyFixture>(),
                CollisionItemAABBProducer<Body, BodyFixture>(),
                StaticValueAABBExpansionMethod<CollisionItem<Body, BodyFixture>>(0.2))
        )
        world.setBroadphaseDetector(replacement)
        assertSame(replacement, world.getBroadphaseDetector())
        assertNotSame(original, replacement)
        assertTrue(world.containsInBroadphase(body, body.getFixture(0)))
    }
fun setNullBroadphaseDetector() = assertFailsWith<NullPointerException> { CoreCollisionWorld().setBroadphaseDetector(null) }.let { Unit }
fun getAndSetBroadphaseFilter() {
        val world = CoreCollisionWorld()
        val original = world.getBroadphaseCollisionDataFilter()
        val replacement = org.dyn4j.world.CollisionBodyBroadphaseCollisionDataFilter<Body, BodyFixture>()
        world.setBroadphaseCollisionDataFilter(replacement)
        assertSame(replacement, world.getBroadphaseCollisionDataFilter())
        assertNotSame(original, replacement)
    }
fun setNullBroadphaseFilter() = assertFailsWith<NullPointerException> { CoreCollisionWorld().setBroadphaseCollisionDataFilter(null) }.let { Unit }
fun getAndSetNarrowphaseDetector() {
        val world = CoreCollisionWorld()
        val original = world.getNarrowphaseDetector()
        val replacement = Gjk()
        world.setNarrowphaseDetector(replacement)
        assertSame(replacement, world.getNarrowphaseDetector())
        assertNotSame(original, replacement)
    }
fun setNullNarrowphaseDetector() = assertFailsWith<NullPointerException> { CoreCollisionWorld().setNarrowphaseDetector(null) }.let { Unit }
fun getAndSetNarrowphasePostProcessor() {
        val world = CoreCollisionWorld()
        val original = world.getNarrowphasePostProcessor()
        val replacement = LinkPostProcessor()
        world.setNarrowphasePostProcessor(replacement)
        assertSame(replacement, world.getNarrowphasePostProcessor())
        assertNotSame(original, replacement)
    }
fun setNullNarrowphasePostProcessor() = assertFailsWith<NullPointerException> { CoreCollisionWorld().setNarrowphasePostProcessor(null) }.let { Unit }
fun setManifoldSolver() {
        val world = CoreCollisionWorld()
        val original = world.getManifoldSolver()
        val replacement = ClippingManifoldSolver()
        world.setManifoldSolver(replacement)
        assertSame(replacement, world.getManifoldSolver())
        assertNotSame(original, replacement)
    }
fun setNullManifoldSolver() = assertFailsWith<NullPointerException> { CoreCollisionWorld().setManifoldSolver(null) }.let { Unit }
fun setTimeOfImpactDetector() {
        val world = CoreCollisionWorld()
        val original = world.getTimeOfImpactDetector()
        val replacement = ConservativeAdvancement()
        world.setTimeOfImpactDetector(replacement)
        assertSame(replacement, world.getTimeOfImpactDetector())
        assertNotSame(original, replacement)
    }
fun setNullTimeOfImpactDetector() = assertFailsWith<NullPointerException> { CoreCollisionWorld().setTimeOfImpactDetector(null) }.let { Unit }
fun setRaycastDetector() {
        val world = CoreCollisionWorld()
        val original = world.getRaycastDetector()
        val replacement = Gjk()
        world.setRaycastDetector(replacement)
        assertSame(replacement, world.getRaycastDetector())
        assertNotSame(original, replacement)
    }
fun setNullRaycastDetector() = assertFailsWith<NullPointerException> { CoreCollisionWorld().setRaycastDetector(null) }.let { Unit }

fun shift() {
        val world = CoreCollisionWorld()
        val bounds = AxisAlignedBounds(20.0, 20.0)
        world.setBounds(bounds)
        val first = circleBody()
        val second = Body().also { it.addFixture(Geometry.createEquilateralTriangle(0.5)); it.setMass(MassType.NORMAL) }
        world.addBody(first)
        world.addBody(second)
        val firstAabb = world.broadphaseAabb(first, first.getFixture(0)).copy()
        val secondAabb = world.broadphaseAabb(second, second.getFixture(0)).copy()
        world.scan()
        val data = assertNotNull(world.getCollisionData(first, first.getFixture(0), second, second.getFixture(0)))
        val point = data.getManifold().getPoints()[0].getPoint().copy()
        world.shift(Vector2(1.0, 1.0))
        for (body in listOf(first, second)) {
            assertEquals(1.0, body.getWorldCenter().x)
            assertEquals(1.0, body.getWorldCenter().y)
        }
        for ((body, before) in listOf(first to firstAabb, second to secondAabb)) {
            val after = world.broadphaseAabb(body, body.getFixture(0))
            assertEquals(before.getMinX() + 1.0, after.getMinX())
            assertEquals(before.getMinY() + 1.0, after.getMinY())
            assertEquals(before.getMaxX() + 1.0, after.getMaxX())
            assertEquals(before.getMaxY() + 1.0, after.getMaxY())
        }
        assertEquals(1.0, bounds.getTranslation().x)
        assertEquals(1.0, bounds.getTranslation().y)
        assertEquals(point.x + 1.0, data.getManifold().getPoints()[0].getPoint().x)
        assertEquals(point.y + 1.0, data.getManifold().getPoints()[0].getPoint().y)
    }

fun getCollisionData() {
        val world = CoreCollisionWorld()
        val first = circleBody()
        val second = Body().also { it.addFixture(Geometry.createEquilateralTriangle(0.5)); it.setMass(MassType.NORMAL) }
        val distant = Body().also { it.addFixture(Circle(2.0)); it.translate(-5.0, 0.0) }
        listOf(first, second, distant).forEach(world::addBody)
        world.scan()
        val data = assertNotNull(world.getCollisionData(first, first.getFixture(0), second, second.getFixture(0)))
        assertNotNull(data.getPair())
        assertTrue(world.created > 0)
        assertEquals(setOf(first, second), setOf(data.getBody1(), data.getBody2()))
        assertEquals(setOf(first.getFixture(0), second.getFixture(0)), setOf(data.getFixture1(), data.getFixture2()))
        assertTrue(data.isBroadphaseCollision())
        assertTrue(data.isNarrowphaseCollision())
        assertTrue(data.isManifoldCollision())
        assertTrue(data.getManifold().getNormal().getMagnitude() > 0.0)
        assertEquals(1, data.getManifold().getPoints().size)
        assertNull(world.getCollisionData(first, first.getFixture(0), distant, distant.getFixture(0)))
        assertNull(world.getCollisionData(Body(), first.getFixture(0), second, second.getFixture(0)))
        assertNull(world.getCollisionData(first, first.getFixture(0), Body(), second.getFixture(0)))
        assertNull(world.getCollisionData(first, BodyFixture(Circle(0.5)), second, second.getFixture(0)))
        assertNull(world.getCollisionData(null, first.getFixture(0), second, second.getFixture(0)))
        assertNull(world.getCollisionData(first, first.getFixture(0), null, second.getFixture(0)))
        assertNull(world.getCollisionData(null, null, null, null))
    }

fun getCollisionDataIterator() {
        val world = CoreCollisionWorld()
        val first = circleBody()
        val second = Body().also { it.addFixture(Geometry.createEquilateralTriangle(0.5)); it.setMass(MassType.NORMAL) }
        world.addBody(first)
        world.addBody(second)
        world.scan()
        val firstData = world.getCollisionDataIterator().next()
        assertNotNull(firstData.getPair())
        assertEquals(setOf(first, second), setOf(firstData.getBody1(), firstData.getBody2()))
        assertEquals(setOf(first.getFixture(0), second.getFixture(0)), setOf(firstData.getFixture1(), firstData.getFixture2()))
        assertTrue(firstData.isBroadphaseCollision())
        assertTrue(firstData.isNarrowphaseCollision())
        assertTrue(firstData.isManifoldCollision())
        assertNotNull(firstData.getPenetration())
        assertTrue(firstData.getManifold().getNormal().getMagnitude() > 0.0)
        assertEquals(1, firstData.getManifold().getPoints().size)
        val third = Body().also { it.addFixture(Circle(1.0)); it.translate(-5.0, 0.0) }
        val fourth = Body().also { it.addFixture(Circle(1.0)); it.translate(-3.5, 1.5) }
        world.addBody(third)
        world.addBody(fourth)
        world.scan()
        val collisions = world.getCollisionDataIterator().asSequence().toList()
        assertEquals(2, collisions.size)
        val firstAgain = collisions.single { setOf(it.getBody1(), it.getBody2()) == setOf(first, second) }
        assertNotNull(firstAgain.getPair())
        assertEquals(setOf(first.getFixture(0), second.getFixture(0)), setOf(firstAgain.getFixture1(), firstAgain.getFixture2()))
        assertTrue(firstAgain.isBroadphaseCollision())
        assertTrue(firstAgain.isNarrowphaseCollision())
        assertTrue(firstAgain.isManifoldCollision())
        assertNotNull(firstAgain.getPenetration())
        val broadphaseOnly = collisions.single { setOf(it.getBody1(), it.getBody2()) == setOf(third, fourth) }
        assertNotNull(broadphaseOnly.getPair())
        assertEquals(setOf(third.getFixture(0), fourth.getFixture(0)), setOf(broadphaseOnly.getFixture1(), broadphaseOnly.getFixture2()))
        assertTrue(broadphaseOnly.isBroadphaseCollision())
        assertFalse(broadphaseOnly.isNarrowphaseCollision())
        assertFalse(broadphaseOnly.isManifoldCollision())
        world.removeBody(third)
        assertEquals(2, world.collisionCount())
        assertNull(world.getCollisionData(third, third.getFixture(0), fourth, fourth.getFixture(0)))
        assertEquals(1, world.getCollisionDataIterator().asSequence().count())
        world.addBody(third)
        world.scan()
        world.removeBody(fourth)
        assertEquals(2, world.collisionCount())
        assertEquals(1, world.getCollisionDataIterator().asSequence().count())
    }

fun getCollisionDataIteratorFailure() {
        val world = CoreCollisionWorld()
        world.addBody(circleBody())
        world.addBody(Body().also { it.addFixture(Geometry.createEquilateralTriangle(0.5)); it.setMass(MassType.NORMAL) })
        world.scan()
        val iterator = world.getCollisionDataIterator()
        assertTrue(iterator.hasNext())
        iterator.next()
        assertFailsWith<UnsupportedOperationException> { iterator.remove() }
        assertFailsWith<NoSuchElementException> { iterator.next() }
    }

fun fixtureModification() {
        val world = CoreCollisionWorld()
        val first = circleBody()
        val oldFixture = first.getFixture(0)
        val second = Body().also { it.addFixture(Geometry.createEquilateralTriangle(0.5)); it.setMass(MassType.NORMAL) }
        world.addBody(first)
        world.addBody(second)
        world.scan()
        assertTrue(world.containsInBroadphase(first, oldFixture))
        assertEquals(1, world.collisionCount())
        assertTrue(assertNotNull(world.getCollisionData(first, oldFixture, second, second.getFixture(0))).isManifoldCollision())
        val replacement = first.addFixture(Geometry.createEquilateralTriangle(0.5))
        assertTrue(world.containsInBroadphase(first, replacement))
        first.removeFixture(oldFixture)
        assertFalse(world.containsInBroadphase(first, oldFixture))
        assertNull(world.getCollisionData(first, oldFixture, second, second.getFixture(0)))
        assertEquals(1, world.collisionCount())
        world.scan()
        assertEquals(1, world.collisionCount())
        assertNotNull(world.getCollisionData(first, replacement, second, second.getFixture(0)))
        first.addFixture(oldFixture)
        world.scan()
        first.removeAllFixtures()
        assertFalse(world.containsInBroadphase(first, oldFixture))
        assertFalse(world.containsInBroadphase(first, replacement))
        assertEquals(2, world.collisionCount())
        world.scan()
        assertEquals(0, world.collisionCount())
    }

fun listeners() {
        val world = CoreCollisionWorld()
        val bounds = BoundsListenerAdapter<Body, BodyFixture>()
        val collision = CollisionListenerAdapter<Body, BodyFixture>()
        val boundsView = world.getBoundsListeners()
        val collisionView = world.getCollisionListeners()
        fun assertViews(boundsCount: Int, collisionCount: Int) {
            assertEquals(boundsCount, boundsView.size)
            assertEquals(collisionCount, collisionView.size)
            val currentBounds = world.getBoundsListeners()
            val currentCollision = world.getCollisionListeners()
            assertSame(boundsView, currentBounds)
            assertSame(collisionView, currentCollision)
            assertEquals(boundsCount, currentBounds.size)
            assertEquals(collisionCount, currentCollision.size)
            currentBounds.forEach { assertSame(bounds, it) }
            currentCollision.forEach { assertSame(collision, it) }
        }
        world.addBoundsListener(bounds)
        world.addCollisionListener(collision)
        assertEquals(1, world.boundsListenerBackingSize())
        assertEquals(1, world.collisionListenerBackingSize())
        assertViews(1, 1)
        assertSame(bounds, boundsView[0])
        assertSame(collision, collisionView[0])
        world.addBoundsListener(bounds)
        world.addCollisionListener(collision)
        assertViews(2, 2)
        world.removeBoundsListener(bounds)
        assertViews(1, 2)
        world.removeCollisionListener(collision)
        assertViews(1, 1)
        world.removeAllBoundsListeners()
        assertViews(0, 1)
        world.removeAllCollisionListeners()
        assertViews(0, 0)
        world.addBoundsListener(bounds)
        world.addBoundsListener(bounds)
        world.addCollisionListener(collision)
        assertViews(2, 1)
        world.removeAllListeners()
        assertViews(0, 0)
    }

fun getSetUserData() {
        val world = CoreCollisionWorld()
        assertNull(world.getUserData())
        val value = Any()
        world.setUserData(value)
        assertSame(value, world.getUserData())
        world.setUserData(null)
        assertNull(world.getUserData())
    }

fun detectBroadphaseFilterNotAllowed() {
        val world = CoreCollisionWorld()
        world.setBroadphaseCollisionDataFilter(object : org.dyn4j.world.CollisionBodyBroadphaseCollisionDataFilter<Body, BodyFixture>() {
            override fun isAllowed(body1: Body?, fixture1: BodyFixture?, body2: Body?, fixture2: BodyFixture?): Boolean =
                super.isAllowed(body1, fixture1, body2, fixture2) &&
                    (body1!!.getMass().getType() != MassType.INFINITE || body2!!.getMass().getType() != MassType.INFINITE)
        })
        val first = Body().also { it.addFixture(Circle(1.0)) }
        val second = Body().also { it.addFixture(Geometry.createEquilateralTriangle(0.5)) }
        world.addBody(first)
        world.addBody(second)
        world.scan()
        val data = assertNotNull(world.getCollisionDataIterator().next())
        assertFalse(data.isBroadphaseCollision())
        assertFalse(data.isNarrowphaseCollision())
        assertFalse(data.isManifoldCollision())
    }

fun detectNoLongerColliding() {
        val world = CoreCollisionWorld()
        val first = Body().also { it.addFixture(Circle(1.0)) }
        val second = Body().also { it.addFixture(Geometry.createEquilateralTriangle(0.5)) }
        world.addBody(first)
        world.addBody(second)
        world.scan()
        assertTrue(world.getCollisionDataIterator().hasNext())
        first.translate(10.0, 10.0)
        world.scan()
        assertFalse(world.getCollisionDataIterator().hasNext())
    }

fun detectIteratorRemove() {
        val world = object : CoreCollisionWorld() {
            override fun processCollisions(iterator: MutableIterator<WorldCollisionData<Body>>) {
                while (iterator.hasNext()) {
                    iterator.next()
                    iterator.remove()
                }
            }
        }
        world.addBody(circleBody())
        world.addBody(Body().also { it.addFixture(Geometry.createEquilateralTriangle(0.5)); it.setMass(MassType.NORMAL) })
        assertFailsWith<UnsupportedOperationException> { world.scan() }
    }

fun detectWithListeners() {
        val world = CoreCollisionWorld()
        val first = circleBody()
        val second = Body().also { it.addFixture(Geometry.createEquilateralTriangle(0.5)); it.setMass(MassType.NORMAL) }
        world.addBody(first)
        world.addBody(second)
        world.addCollisionListener(object : CollisionListenerAdapter<Body, BodyFixture>() {
            override fun collision(collision: BroadphaseCollisionData<Body, BodyFixture>?): Boolean = false
        })
        world.scan()
        var data = assertNotNull(world.getCollisionDataIterator().next())
        assertFalse(data.isBroadphaseCollision())
        assertFalse(data.isNarrowphaseCollision())
        assertFalse(data.isManifoldCollision())
        world.removeAllCollisionListeners()
        world.addCollisionListener(object : CollisionListenerAdapter<Body, BodyFixture>() {
            override fun collision(collision: NarrowphaseCollisionData<Body, BodyFixture>?): Boolean = false
        })
        world.scan()
        data = world.getCollisionDataIterator().next()
        assertTrue(data.isBroadphaseCollision())
        assertFalse(data.isNarrowphaseCollision())
        assertFalse(data.isManifoldCollision())
        world.removeAllCollisionListeners()
        world.addCollisionListener(object : CollisionListenerAdapter<Body, BodyFixture>() {
            override fun collision(collision: ManifoldCollisionData<Body, BodyFixture>?): Boolean = false
        })
        world.scan()
        data = world.getCollisionDataIterator().next()
        assertTrue(data.isBroadphaseCollision())
        assertTrue(data.isNarrowphaseCollision())
        assertFalse(data.isManifoldCollision())
    }

fun detectWithFixtureModification() {
        val world = CoreCollisionWorld()
        val first = Body().also {
            it.addFixture(Circle(0.5))
            it.addFixture(Circle(0.5))
            it.setMass(MassType.NORMAL)
        }
        val second = Body().also { it.addFixture(Geometry.createRectangle(1.0, 0.5)); it.setMass(MassType.NORMAL) }
        world.addBody(first)
        world.addBody(second)
        world.scan()
        assertEquals(2, world.getCollisionDataIterator().asSequence().count())
        first.removeFixture(1)
        assertEquals(2, world.collisionCount())
        assertEquals(1, world.getCollisionDataIterator().asSequence().count())
        world.scan()
        assertEquals(1, world.collisionCount())
        assertEquals(1, world.getCollisionDataIterator().asSequence().count())
    }

fun detectWithBounds() {
        val world = CoreCollisionWorld()
        var calls = 0
        world.setBounds(AxisAlignedBounds(10.0, 10.0))
        world.addBoundsListener(object : BoundsListenerAdapter<Body, BodyFixture>() {
            override fun outside(body: Body?) { calls++ }
        })
        val first = circleBody()
        val second = Body().also {
            it.addFixture(Circle(0.5))
            it.addFixture(Circle(0.5).also { shape -> shape.translate(1.0, 0.0) })
            it.setMass(MassType.NORMAL)
        }
        world.addBody(first)
        world.addBody(second)
        world.scan()
        assertEquals(0, calls)
        first.translate(20.0, 20.0)
        world.scan()
        assertEquals(1, calls)
        calls = 0
        first.translate(-20.0, -20.0)
        second.translate(5.0, 0.0)
        world.scan()
        assertEquals(0, calls)
    }

fun detectWithDisabled() {
        val world = CoreCollisionWorld()
        val first = circleBody()
        val second = Body().also { it.addFixture(Circle(0.5)); it.setMass(MassType.NORMAL) }
        world.addBody(first)
        world.addBody(second)
        world.scan()
        var data = world.getCollisionDataIterator().next()
        assertTrue(data.isBroadphaseCollision())
        assertTrue(data.isNarrowphaseCollision())
        assertTrue(data.isManifoldCollision())
        first.setEnabled(false)
        world.scan()
        data = world.getCollisionDataIterator().next()
        assertFalse(data.isBroadphaseCollision())
        assertFalse(data.isNarrowphaseCollision())
        assertFalse(data.isManifoldCollision())
    }

fun detectAABB() {
        val (world, first, second) = queryWorld()
        var filter = DetectFilter<Body, BodyFixture>(true, true, null)
        val full = AABB(-2.0, -2.0, 2.0, 2.0)
        assertEquals(2, world.detect(full, filter).size)
        first.setEnabled(false)
        assertEquals(1, world.detect(full, filter).size)
        second.getFixture(0).setSensor(true)
        assertEquals(0, world.detect(full, filter).size)
        first.setEnabled(true)
        second.getFixture(0).setSensor(false)
        assertEquals(1, world.detect(AABB(-2.0, 1.0, -1.0, 2.0), filter).size)
        filter = DetectFilter(true, true, CategoryFilter(4L, 4L))
        assertEquals(0, world.detect(full, filter).size)
    }

fun detectAABBAgainstSingleBody() {
        val (world, first, _) = queryWorld()
        var filter = DetectFilter<Body, BodyFixture>(true, true, null)
        val full = AABB(-2.0, -2.0, 2.0, 2.0)
        assertEquals(1, world.detect(full, first, filter).size)
        first.setEnabled(false)
        assertEquals(0, world.detect(full, first, filter).size)
        first.setEnabled(true)
        first.getFixture(0).setSensor(true)
        assertEquals(0, world.detect(full, first, filter).size)
        first.getFixture(0).setSensor(false)
        assertEquals(1, world.detect(AABB(-2.0, 1.0, -1.0, 2.0), first, filter).size)
        assertEquals(0, world.detect(AABB(0.0, -2.0, 2.0, 0.0), first, filter).size)
        filter = DetectFilter(true, true, CategoryFilter(4L, 4L))
        assertEquals(0, world.detect(full, first, filter).size)
        filter = DetectFilter(true, true, CategoryFilter(1L, 3L))
        assertEquals(1, world.detect(full, first, filter).size)
    }

fun detectAABBIterator() {
        val world = CoreCollisionWorld()
        val full = AABB(-2.0, -2.0, 2.0, 2.0)
        assertFalse(world.detectIterator(full, null).hasNext())
        assertFalse(world.detectIterator(full, Body(), null).hasNext())
        val (_, first, second) = queryWorld()
        world.addBody(first.copy())
        world.addBody(second.copy())
        val iterator = world.detectIterator(full, null)
        repeat(20) { assertTrue(iterator.hasNext()) }
        assertNotNull(iterator.next())
        val single = world.detectIterator(full, world.getBody(0), null)
        repeat(20) { assertTrue(single.hasNext()) }
        assertNotNull(single.next())
    }

fun detectAABBIteratorFailures() {
        val (world, first, _) = queryWorld()
        val full = AABB(-2.0, -2.0, 2.0, 2.0)
        for (body in listOf(null, first)) {
            val iterator = if (body == null) world.detectIterator(full, null) else world.detectIterator(full, body, null)
            assertTrue(iterator.hasNext())
            iterator.next()
            assertFailsWith<UnsupportedOperationException> { iterator.remove() }
            val overflow = if (body == null) world.detectIterator(full, null) else world.detectIterator(full, body, null)
            assertFailsWith<NoSuchElementException> { repeat(10) { overflow.next() } }
        }
    }

fun detectConvex() {
        val (world, first, second) = queryWorld()
        var filter = DetectFilter<Body, BodyFixture>(true, true, null)
        var shape = Circle(0.5)
        val transform = Transform().also { it.translate(-0.5, 0.0) }
        assertEquals(2, world.detect(shape, transform, filter).size)
        first.setEnabled(false)
        assertEquals(1, world.detect(shape, transform, filter).size)
        second.getFixture(0).setSensor(true)
        assertEquals(0, world.detect(shape, transform, filter).size)
        first.setEnabled(true)
        second.getFixture(0).setSensor(false)
        filter = DetectFilter(true, true, CategoryFilter(4L, 4L))
        assertEquals(0, world.detect(shape, transform, filter).size)
        shape = Circle(0.25)
        transform.identity()
        assertEquals(1, world.detect(shape, transform, DetectFilter(true, true, null)).size)
    }

fun detectConvexAgainstSingleBody() {
        val (world, first, second) = queryWorld()
        var filter = DetectFilter<Body, BodyFixture>(true, true, null)
        var shape = Circle(0.5)
        val transform = Transform().also { it.translate(-0.5, 0.0) }
        assertEquals(1, world.detect(shape, transform, first, filter).size)
        first.setEnabled(false)
        assertEquals(0, world.detect(shape, transform, first, filter).size)
        first.setEnabled(true)
        first.getFixture(0).setSensor(true)
        assertEquals(0, world.detect(shape, transform, first, filter).size)
        first.getFixture(0).setSensor(false)
        shape = Circle(0.25)
        assertEquals(0, world.detect(shape, transform, first, filter).size)
        transform.identity()
        assertEquals(1, world.detect(shape, transform, second, filter).size)
        filter = DetectFilter(true, true, CategoryFilter(4L, 4L))
        shape = Circle(0.5)
        assertEquals(0, world.detect(shape, transform, first, filter).size)
        filter = DetectFilter(true, true, CategoryFilter(1L, 3L))
        assertEquals(1, world.detect(shape, transform, first, filter).size)
    }

fun detectContexIterator() {
        val world = CoreCollisionWorld()
        val shape = Circle(0.5)
        val transform = Transform().also { it.translate(-0.5, 0.0) }
        assertFalse(world.detectIterator(shape, transform, null).hasNext())
        assertFalse(world.detectIterator(shape, transform, Body(), null).hasNext())
        val (populated, first, _) = queryWorld()
        val all = populated.detectIterator(shape, transform, null)
        repeat(20) { assertTrue(all.hasNext()) }
        assertNotNull(all.next())
        val single = populated.detectIterator(shape, transform, first, null)
        repeat(20) { assertTrue(single.hasNext()) }
        assertNotNull(single.next())
    }

fun detectConvexIteratorFailures() {
        val (world, first, _) = queryWorld()
        val shape = Circle(0.5)
        val transform = Transform().also { it.translate(-0.5, 0.0) }
        for (body in listOf(null, first)) {
            val iterator = if (body == null) world.detectIterator(shape, transform, null) else world.detectIterator(shape, transform, body, null)
            assertTrue(iterator.hasNext())
            iterator.next()
            assertFailsWith<UnsupportedOperationException> { iterator.remove() }
            val overflow = if (body == null) world.detectIterator(shape, transform, null) else world.detectIterator(shape, transform, body, null)
            assertFailsWith<NoSuchElementException> { repeat(10) { overflow.next() } }
        }
    }

fun raycast() {
        val (world, first, second) = castWorld(false)
        var filter = DetectFilter<Body, BodyFixture>(true, true, null)
        var ray = Ray(Vector2(-1.0, -1.0), Vector2(1.0, 1.0))
        assertEquals(2, world.raycast(ray, Double.MAX_VALUE, filter).size)
        first.setEnabled(false)
        assertEquals(1, world.raycast(ray, Double.MAX_VALUE, filter).size)
        second.getFixture(0).setSensor(true)
        assertEquals(0, world.raycast(ray, Double.MAX_VALUE, filter).size)
        first.setEnabled(true)
        second.getFixture(0).setSensor(false)
        filter = DetectFilter(true, true, CategoryFilter(4L, 4L))
        assertEquals(0, world.raycast(ray, Double.MAX_VALUE, filter).size)
        assertNull(world.raycastClosest(ray, 0.0, filter))
        filter = DetectFilter(true, true, null)
        val length = sqrt(1.5 * 1.5 + 1.3 * 1.3)
        assertEquals(1, world.raycast(ray, length, filter).size)
        for (limit in listOf(Double.MAX_VALUE, length)) {
            val closest = assertNotNull(world.raycastClosest(ray, limit, filter))
            assertSame(second, closest.getBody())
            assertSame(second.getFixture(0), closest.getFixture())
        }
        ray = Ray(Vector2(0.0, 0.0), Vector2(1.0, 1.0))
        assertEquals(1, world.raycast(ray, -1.0, filter).size)
        assertSame(first, world.raycastClosest(ray, Double.MAX_VALUE, filter)?.getBody())
        assertEquals(0, world.raycast(Ray(Vector2(0.0, 0.0), Vector2(-1.0, -1.0)), length, filter).size)
        assertEquals(0, world.raycast(Ray(Vector2(-1.0, 1.0), Vector2(-2.0, 2.0)), -1.0, filter).size)
    }

fun raycastAgainstSingleBody() {
        val (world, first, second) = castWorld(true)
        var filter = DetectFilter<Body, BodyFixture>(true, true, null)
        var ray = Ray(Vector2(-1.0, -1.0), Vector2(1.0, 1.0))
        assertEquals(2, world.raycast(ray, Double.MAX_VALUE, first, filter).size)
        assertSame(first, world.raycastClosest(ray, Double.MAX_VALUE, first, filter)?.getBody())
        first.setEnabled(false)
        assertEquals(0, world.raycast(ray, Double.MAX_VALUE, first, filter).size)
        first.setEnabled(true)
        first.getFixture(0).setSensor(true)
        assertEquals(1, world.raycast(ray, Double.MAX_VALUE, first, filter).size)
        first.getFixture(0).setSensor(false)
        filter = DetectFilter(true, true, CategoryFilter(4L, 4L))
        assertEquals(0, world.raycast(ray, Double.MAX_VALUE, first, filter).size)
        filter = DetectFilter(true, true, null)
        assertEquals(2, world.raycast(ray, Double.MAX_VALUE, first, filter).size)
        val length = sqrt(1.5 * 1.5 + 1.3 * 1.3)
        assertEquals(0, world.raycast(ray, length, first, filter).size)
        assertEquals(1, world.raycast(ray, length, second, filter).size)
        ray = Ray(Vector2(0.0, 0.0), Vector2(1.0, 1.0))
        assertEquals(2, world.raycast(ray, Double.MAX_VALUE, first, filter).size)
        assertSame(first.getFixture(0), world.raycastClosest(ray, Double.MAX_VALUE, first, filter)?.getFixture())
        assertEquals(0, world.raycast(Ray(Vector2(0.0, 0.0), Vector2(-1.0, -1.0)), length, first, filter).size)
        assertEquals(0, world.raycast(Ray(Vector2(-1.0, 1.0), Vector2(-2.0, 2.0)), -1.0, first, filter).size)
    }

fun raycastIterator() {
        val empty = CoreCollisionWorld()
        val ray = Ray(Vector2(-1.0, -1.0), Vector2(1.0, 1.0))
        assertFalse(empty.raycastIterator(ray, Double.MAX_VALUE, null).hasNext())
        assertFalse(empty.raycastIterator(ray, 0.0, Body(), null).hasNext())
        val (world, first, _) = castWorld(false)
        val all = world.raycastIterator(ray, Double.MAX_VALUE, null)
        repeat(20) { assertTrue(all.hasNext()) }
        assertNotNull(all.next())
        val single = world.raycastIterator(ray, Double.MAX_VALUE, first, null)
        repeat(20) { assertTrue(single.hasNext()) }
        assertNotNull(single.next())
    }

fun raycastIteratorFailures() {
        val (world, first, _) = castWorld(false)
        val ray = Ray(Vector2(-1.0, -1.0), Vector2(1.0, 1.0))
        for (body in listOf(null, first)) {
            val iterator = if (body == null) world.raycastIterator(ray, 0.0, null) else world.raycastIterator(ray, 0.0, body, null)
            assertTrue(iterator.hasNext())
            iterator.next()
            assertFailsWith<UnsupportedOperationException> { iterator.remove() }
            val overflow = if (body == null) world.raycastIterator(ray, 0.0, null) else world.raycastIterator(ray, 0.0, body, null)
            assertFailsWith<NoSuchElementException> { repeat(10) { overflow.next() } }
        }
    }

fun convexCast() {
        val (world, first, second) = castWorld(true)
        var filter = DetectFilter<Body, BodyFixture>(true, true, null)
        val shape = Geometry.createRectangle(0.5, 0.5)
        val transform = Transform().also { it.translate(-1.0, -1.0) }
        var movement = Vector2(3.0, 3.0)
        val angle = PI / 4.0
        assertEquals(3, world.convexCast(shape, transform, movement, angle, filter).size)
        first.setEnabled(false)
        assertEquals(1, world.convexCast(shape, transform, movement, angle, filter).size)
        second.getFixture(0).setSensor(true)
        assertEquals(0, world.convexCast(shape, transform, movement, angle, filter).size)
        first.setEnabled(true)
        second.getFixture(0).setSensor(false)
        filter = DetectFilter(true, true, CategoryFilter(4L, 4L))
        assertEquals(0, world.convexCast(shape, transform, movement, angle, filter).size)
        assertNull(world.convexCastClosest(shape, transform, movement, angle, filter))
        filter = DetectFilter(true, true, null)
        movement = Vector2(0.5, 0.5)
        assertEquals(1, world.convexCast(shape, transform, movement, angle, filter).size)
        assertSame(second, world.convexCastClosest(shape, transform, movement, angle, filter)?.getBody())
        movement = Vector2(5.0, 5.0)
        assertSame(second, world.convexCastClosest(shape, transform, movement, angle, filter)?.getBody())
        transform.identity()
        assertEquals(2, world.convexCast(shape, transform, movement, angle, filter).size)
        val closest = assertNotNull(world.convexCastClosest(shape, transform, movement, angle, filter))
        assertSame(first, closest.getBody())
        assertSame(first.getFixture(0), closest.getFixture())
        assertEquals(0, world.convexCast(shape, transform, Vector2(-5.0, 5.0), angle, filter).size)
        assertEquals(0, world.convexCast(shape, transform, Vector2(0.25, 0.25), angle, filter).size)
    }

fun convexCastAgainstSingleBody() {
        val (world, first, _) = castWorld(true)
        var filter = DetectFilter<Body, BodyFixture>(true, true, null)
        val shape = Geometry.createRectangle(0.5, 0.5)
        val transform = Transform().also { it.translate(-1.0, -1.0) }
        var movement = Vector2(3.0, 3.0)
        val angle = PI / 4.0
        assertNotNull(world.convexCastClosest(shape, transform, movement, angle, first, filter))
        first.setEnabled(false)
        assertNull(world.convexCastClosest(shape, transform, movement, angle, first, filter))
        first.setEnabled(true)
        first.getFixture(0).setSensor(true)
        assertNotNull(world.convexCastClosest(shape, transform, movement, angle, first, filter))
        first.getFixture(0).setSensor(false)
        filter = DetectFilter(true, true, CategoryFilter(4L, 4L))
        assertNull(world.convexCastClosest(shape, transform, movement, angle, first, filter))
        filter = DetectFilter(true, true, null)
        movement = Vector2(0.5, 0.5)
        assertNull(world.convexCastClosest(shape, transform, movement, angle, first, filter))
        movement = Vector2(5.0, 5.0)
        val firstHit = assertNotNull(world.convexCastClosest(shape, transform, movement, angle, first, filter))
        assertSame(first, firstHit.getBody())
        assertSame(first.getFixture(0), firstHit.getFixture())
        transform.identity()
        transform.translate(0.75, 0.75)
        val secondHit = assertNotNull(world.convexCastClosest(shape, transform, movement, angle, first, filter))
        assertSame(first, secondHit.getBody())
        assertSame(first.getFixture(1), secondHit.getFixture())
        assertNull(world.convexCastClosest(shape, transform, Vector2(-5.0, 5.0), angle, first, filter))
        assertNull(world.convexCastClosest(shape, transform, Vector2(0.25, 0.25), angle, first, filter))
    }

fun convexCastIterator() {
        val shape = Geometry.createRectangle(0.5, 0.5)
        val transform = Transform().also { it.translate(-1.0, -1.0) }
        val movement = Vector2(3.0, 3.0)
        val angle = PI / 4.0
        assertFalse(CoreCollisionWorld().convexCastIterator(shape, transform, movement, angle, null).hasNext())
        val (world, _, _) = castWorld(true)
        val iterator = world.convexCastIterator(shape, transform, movement, angle, null)
        repeat(20) { assertTrue(iterator.hasNext()) }
        assertNotNull(iterator.next())
    }

fun convexCastIteratorFailures() {
        val (world, _, _) = castWorld(true)
        val shape = Geometry.createRectangle(0.5, 0.5)
        val transform = Transform().also { it.translate(-1.0, -1.0) }
        val movement = Vector2(3.0, 3.0)
        val angle = PI / 4.0
        val iterator = world.convexCastIterator(shape, transform, movement, angle, null)
        assertTrue(iterator.hasNext())
        iterator.next()
        assertFailsWith<UnsupportedOperationException> { iterator.remove() }
        val overflow = world.convexCastIterator(shape, transform, movement, angle, null)
        assertFailsWith<NoSuchElementException> { repeat(10) { overflow.next() } }
    }
}
