/*
 * Copyright (c) 2010-2021 William Bittle  http://www.dyn4j.org/
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
package org.dyn4j.collision.broadphase

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotSame
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import org.dyn4j.collision.AbstractCollisionBody
import org.dyn4j.collision.BasicCollisionItem
import org.dyn4j.collision.CollisionItem
import org.dyn4j.collision.CollisionPair
import org.dyn4j.collision.Fixture
import org.dyn4j.collision.broadphase.BruteForceBroadphase
import org.dyn4j.collision.broadphase.AABBBroadphaseProxy
import org.dyn4j.collision.broadphase.BroadphaseItem
import org.dyn4j.collision.broadphase.BroadphasePair
import org.dyn4j.collision.broadphase.CollisionBodyAABBProducer
import org.dyn4j.collision.broadphase.CollisionBodyBroadphaseFilter
import org.dyn4j.collision.broadphase.CollisionItemAABBProducer
import org.dyn4j.collision.broadphase.CollisionItemBroadphaseDetector
import org.dyn4j.collision.broadphase.CollisionItemBroadphaseDetectorAdapter
import org.dyn4j.collision.broadphase.CollisionItemBroadphaseFilter
import org.dyn4j.collision.broadphase.DynamicAABBTree
import org.dyn4j.collision.broadphase.DynamicAABBTreeLeaf
import org.dyn4j.collision.broadphase.DynamicAABBTreeNode
import org.dyn4j.collision.broadphase.NullAABBExpansionMethod
import org.dyn4j.collision.broadphase.Sap
import org.dyn4j.collision.broadphase.StaticValueAABBExpansionMethod
import org.dyn4j.geometry.AABB
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.Ray
import org.dyn4j.geometry.Vector2

private class Body : AbstractCollisionBody<Fixture> {
    constructor() : super()
    constructor(radius: Double) : this() { addFixture(Circle(radius)) }
    private constructor(source: Body) : super(source)
    override fun addFixture(convex: org.dyn4j.geometry.Convex?): Fixture = Fixture(convex).also { addFixture(it) }
    override fun getLocalCenter() = Vector2()
    override fun copy() = Body(this)
}

private typealias Item = CollisionItem<Body, Fixture>
private typealias Detector = CollisionItemBroadphaseDetector<Body, Fixture>

private class ConstructorProbe(
    filter: BroadphaseFilter<Body>?,
    producer: AABBProducer<Body>?,
    expansion: AABBExpansionMethod<Body>?
) : AbstractBroadphaseDetector<Body>(filter, producer, expansion) {
    override fun add(item: Body) = error("unused")
    override fun remove(item: Body): Boolean = error("unused")
    override fun update() = error("unused")
    override fun update(item: Body) = error("unused")
    override fun setUpdated(item: Body) = error("unused")
    override fun isUpdated(item: Body): Boolean = error("unused")
    override fun clearUpdates() = error("unused")
    override fun getAABB(item: Body): AABB = error("unused")
    override fun contains(item: Body): Boolean = error("unused")
    override fun clear() = error("unused")
    override fun size(): Int = error("unused")
    override fun detectIterator(forceFullDetection: Boolean): MutableIterator<CollisionPair<Body>> = error("unused")
    override fun detectIterator(aabb: AABB): MutableIterator<Body> = error("unused")
    override fun raycastIterator(ray: Ray, length: Double): MutableIterator<Body> = error("unused")
    override fun shift(shift: Vector2) = error("unused")
    override fun isUpdateTrackingSupported(): Boolean = error("unused")
    override fun optimize() = error("unused")
}

private fun item(body: Body, index: Int = 0): Item = BasicCollisionItem(body, body.getFixture(index))

private fun detector(variant: Int): Detector {
    val filter = CollisionItemBroadphaseFilter<Body, Fixture>()
    val producer = CollisionItemAABBProducer<Body, Fixture>()
    val expansion = StaticValueAABBExpansionMethod<Item>(0.2)
    val delegate = when (variant) {
        0 -> BruteForceBroadphase(filter, producer)
        1, 2 -> Sap(filter, producer, expansion)
        3, 4 -> DynamicAABBTree(filter, producer, expansion)
        else -> error("unknown broadphase variant")
    }
    return CollisionItemBroadphaseDetectorAdapter(delegate).also {
        it.setUpdateTrackingEnabled(variant == 2 || variant == 4)
    }
}

class ItemBroadphaseCoverageTest {
    @Test fun addContainsBody_brute_force() = verify("addContainsBody", 0)
    @Test fun addContainsBody_sap_untracked() = verify("addContainsBody", 1)
    @Test fun addContainsBody_sap_tracked() = verify("addContainsBody", 2)
    @Test fun addContainsBody_tree_untracked() = verify("addContainsBody", 3)
    @Test fun addContainsBody_tree_tracked() = verify("addContainsBody", 4)

    @Test fun addContainsCollisionItem_brute_force() = verify("addContainsCollisionItem", 0)
    @Test fun addContainsCollisionItem_sap_untracked() = verify("addContainsCollisionItem", 1)
    @Test fun addContainsCollisionItem_sap_tracked() = verify("addContainsCollisionItem", 2)
    @Test fun addContainsCollisionItem_tree_untracked() = verify("addContainsCollisionItem", 3)
    @Test fun addContainsCollisionItem_tree_tracked() = verify("addContainsCollisionItem", 4)

    @Test fun addContainsFixture_brute_force() = verify("addContainsFixture", 0)
    @Test fun addContainsFixture_sap_untracked() = verify("addContainsFixture", 1)
    @Test fun addContainsFixture_sap_tracked() = verify("addContainsFixture", 2)
    @Test fun addContainsFixture_tree_untracked() = verify("addContainsFixture", 3)
    @Test fun addContainsFixture_tree_tracked() = verify("addContainsFixture", 4)

    @Test fun clear_brute_force() = verify("clear", 0)
    @Test fun clear_sap_untracked() = verify("clear", 1)
    @Test fun clear_sap_tracked() = verify("clear", 2)
    @Test fun clear_tree_untracked() = verify("clear", 3)
    @Test fun clear_tree_tracked() = verify("clear", 4)

    @Test fun updateTargeted_brute_force() = verify("updateTargeted", 0)
    @Test fun updateTargeted_sap_untracked() = verify("updateTargeted", 1)
    @Test fun updateTargeted_sap_tracked() = verify("updateTargeted", 2)
    @Test fun updateTargeted_tree_untracked() = verify("updateTargeted", 3)
    @Test fun updateTargeted_tree_tracked() = verify("updateTargeted", 4)

    @Test fun update_brute_force() = verify("update", 0)
    @Test fun update_sap_untracked() = verify("update", 1)
    @Test fun update_sap_tracked() = verify("update", 2)
    @Test fun update_tree_untracked() = verify("update", 3)
    @Test fun update_tree_tracked() = verify("update", 4)

    @Test fun removeContainsBody_brute_force() = verify("removeContainsBody", 0)
    @Test fun removeContainsBody_sap_untracked() = verify("removeContainsBody", 1)
    @Test fun removeContainsBody_sap_tracked() = verify("removeContainsBody", 2)
    @Test fun removeContainsBody_tree_untracked() = verify("removeContainsBody", 3)
    @Test fun removeContainsBody_tree_tracked() = verify("removeContainsBody", 4)

    @Test fun removeContainsFixture_brute_force() = verify("removeContainsFixture", 0)
    @Test fun removeContainsFixture_sap_untracked() = verify("removeContainsFixture", 1)
    @Test fun removeContainsFixture_sap_tracked() = verify("removeContainsFixture", 2)
    @Test fun removeContainsFixture_tree_untracked() = verify("removeContainsFixture", 3)
    @Test fun removeContainsFixture_tree_tracked() = verify("removeContainsFixture", 4)

    @Test fun getAABB_brute_force() = verify("getAABB", 0)
    @Test fun getAABB_sap_untracked() = verify("getAABB", 1)
    @Test fun getAABB_sap_tracked() = verify("getAABB", 2)
    @Test fun getAABB_tree_untracked() = verify("getAABB", 3)
    @Test fun getAABB_tree_tracked() = verify("getAABB", 4)

    @Test fun getAABBProducer_brute_force() = verify("getAABBProducer", 0)
    @Test fun getAABBProducer_sap_untracked() = verify("getAABBProducer", 1)
    @Test fun getAABBProducer_sap_tracked() = verify("getAABBProducer", 2)
    @Test fun getAABBProducer_tree_untracked() = verify("getAABBProducer", 3)
    @Test fun getAABBProducer_tree_tracked() = verify("getAABBProducer", 4)

    @Test fun getBroadphaseFilter_brute_force() = verify("getBroadphaseFilter", 0)
    @Test fun getBroadphaseFilter_sap_untracked() = verify("getBroadphaseFilter", 1)
    @Test fun getBroadphaseFilter_sap_tracked() = verify("getBroadphaseFilter", 2)
    @Test fun getBroadphaseFilter_tree_untracked() = verify("getBroadphaseFilter", 3)
    @Test fun getBroadphaseFilter_tree_tracked() = verify("getBroadphaseFilter", 4)

    @Test fun getAABBExpansionMethod_brute_force() = verify("getAABBExpansionMethod", 0)
    @Test fun getAABBExpansionMethod_sap_untracked() = verify("getAABBExpansionMethod", 1)
    @Test fun getAABBExpansionMethod_sap_tracked() = verify("getAABBExpansionMethod", 2)
    @Test fun getAABBExpansionMethod_tree_untracked() = verify("getAABBExpansionMethod", 3)
    @Test fun getAABBExpansionMethod_tree_tracked() = verify("getAABBExpansionMethod", 4)

    @Test fun updateSmall_brute_force() = verify("updateSmall", 0)
    @Test fun updateSmall_sap_untracked() = verify("updateSmall", 1)
    @Test fun updateSmall_sap_tracked() = verify("updateSmall", 2)
    @Test fun updateSmall_tree_untracked() = verify("updateSmall", 3)
    @Test fun updateSmall_tree_tracked() = verify("updateSmall", 4)

    @Test fun updateLarge_brute_force() = verify("updateLarge", 0)
    @Test fun updateLarge_sap_untracked() = verify("updateLarge", 1)
    @Test fun updateLarge_sap_tracked() = verify("updateLarge", 2)
    @Test fun updateLarge_tree_untracked() = verify("updateLarge", 3)
    @Test fun updateLarge_tree_tracked() = verify("updateLarge", 4)

    @Test fun getSetUpdateTrackingEnabled_brute_force() = verify("getSetUpdateTrackingEnabled", 0)
    @Test fun getSetUpdateTrackingEnabled_sap_untracked() = verify("getSetUpdateTrackingEnabled", 1)
    @Test fun getSetUpdateTrackingEnabled_sap_tracked() = verify("getSetUpdateTrackingEnabled", 2)
    @Test fun getSetUpdateTrackingEnabled_tree_untracked() = verify("getSetUpdateTrackingEnabled", 3)
    @Test fun getSetUpdateTrackingEnabled_tree_tracked() = verify("getSetUpdateTrackingEnabled", 4)

    @Test fun isUpdateTrackingSupported_brute_force() = verify("isUpdateTrackingSupported", 0)
    @Test fun isUpdateTrackingSupported_sap_untracked() = verify("isUpdateTrackingSupported", 1)
    @Test fun isUpdateTrackingSupported_sap_tracked() = verify("isUpdateTrackingSupported", 2)
    @Test fun isUpdateTrackingSupported_tree_untracked() = verify("isUpdateTrackingSupported", 3)
    @Test fun isUpdateTrackingSupported_tree_tracked() = verify("isUpdateTrackingSupported", 4)

    @Test fun optimize_brute_force() = verify("optimize", 0)
    @Test fun optimize_sap_untracked() = verify("optimize", 1)
    @Test fun optimize_sap_tracked() = verify("optimize", 2)
    @Test fun optimize_tree_untracked() = verify("optimize", 3)
    @Test fun optimize_tree_tracked() = verify("optimize", 4)

    @Test fun setUpdated_brute_force() = verify("setUpdated", 0)
    @Test fun setUpdated_sap_untracked() = verify("setUpdated", 1)
    @Test fun setUpdated_sap_tracked() = verify("setUpdated", 2)
    @Test fun setUpdated_tree_untracked() = verify("setUpdated", 3)
    @Test fun setUpdated_tree_tracked() = verify("setUpdated", 4)

    @Test fun size_brute_force() = verify("size", 0)
    @Test fun size_sap_untracked() = verify("size", 1)
    @Test fun size_sap_tracked() = verify("size", 2)
    @Test fun size_tree_untracked() = verify("size", 3)
    @Test fun size_tree_tracked() = verify("size", 4)

    @Test fun detectConvexAndTransform_brute_force() = verify("detectConvexAndTransform", 0)
    @Test fun detectConvexAndTransform_sap_untracked() = verify("detectConvexAndTransform", 1)
    @Test fun detectConvexAndTransform_sap_tracked() = verify("detectConvexAndTransform", 2)
    @Test fun detectConvexAndTransform_tree_untracked() = verify("detectConvexAndTransform", 3)
    @Test fun detectConvexAndTransform_tree_tracked() = verify("detectConvexAndTransform", 4)

    @Test fun detectIteratorFailure_brute_force() = verify("detectIteratorFailure", 0)
    @Test fun detectIteratorFailure_sap_untracked() = verify("detectIteratorFailure", 1)
    @Test fun detectIteratorFailure_sap_tracked() = verify("detectIteratorFailure", 2)
    @Test fun detectIteratorFailure_tree_untracked() = verify("detectIteratorFailure", 3)
    @Test fun detectIteratorFailure_tree_tracked() = verify("detectIteratorFailure", 4)

    @Test fun raycastIteratorFailure_brute_force() = verify("raycastIteratorFailure", 0)
    @Test fun raycastIteratorFailure_sap_untracked() = verify("raycastIteratorFailure", 1)
    @Test fun raycastIteratorFailure_sap_tracked() = verify("raycastIteratorFailure", 2)
    @Test fun raycastIteratorFailure_tree_untracked() = verify("raycastIteratorFailure", 3)
    @Test fun raycastIteratorFailure_tree_tracked() = verify("raycastIteratorFailure", 4)

    @Test fun detectAABBIteratorFailure_brute_force() = verify("detectAABBIteratorFailure", 0)
    @Test fun detectAABBIteratorFailure_sap_untracked() = verify("detectAABBIteratorFailure", 1)
    @Test fun detectAABBIteratorFailure_sap_tracked() = verify("detectAABBIteratorFailure", 2)
    @Test fun detectAABBIteratorFailure_tree_untracked() = verify("detectAABBIteratorFailure", 3)
    @Test fun detectAABBIteratorFailure_tree_tracked() = verify("detectAABBIteratorFailure", 4)

    @Test fun detectEmptyIterator_brute_force() = verify("detectEmptyIterator", 0)
    @Test fun detectEmptyIterator_sap_untracked() = verify("detectEmptyIterator", 1)
    @Test fun detectEmptyIterator_sap_tracked() = verify("detectEmptyIterator", 2)
    @Test fun detectEmptyIterator_tree_untracked() = verify("detectEmptyIterator", 3)
    @Test fun detectEmptyIterator_tree_tracked() = verify("detectEmptyIterator", 4)

    @Test fun detect_brute_force() = verify("detect", 0)
    @Test fun detect_sap_untracked() = verify("detect", 1)
    @Test fun detect_sap_tracked() = verify("detect", 2)
    @Test fun detect_tree_untracked() = verify("detect", 3)
    @Test fun detect_tree_tracked() = verify("detect", 4)

    @Test fun detectAABB_brute_force() = verify("detectAABB", 0)
    @Test fun detectAABB_sap_untracked() = verify("detectAABB", 1)
    @Test fun detectAABB_sap_tracked() = verify("detectAABB", 2)
    @Test fun detectAABB_tree_untracked() = verify("detectAABB", 3)
    @Test fun detectAABB_tree_tracked() = verify("detectAABB", 4)

    @Test fun detectRay_brute_force() = verify("detectRay", 0)
    @Test fun detectRay_sap_untracked() = verify("detectRay", 1)
    @Test fun detectRay_sap_tracked() = verify("detectRay", 2)
    @Test fun detectRay_tree_untracked() = verify("detectRay", 3)
    @Test fun detectRay_tree_tracked() = verify("detectRay", 4)

    @Test fun shiftCoordinates_brute_force() = verify("shiftCoordinates", 0)
    @Test fun shiftCoordinates_sap_untracked() = verify("shiftCoordinates", 1)
    @Test fun shiftCoordinates_sap_tracked() = verify("shiftCoordinates", 2)
    @Test fun shiftCoordinates_tree_untracked() = verify("shiftCoordinates", 3)
    @Test fun shiftCoordinates_tree_tracked() = verify("shiftCoordinates", 4)

    @Test fun randomizedTest_brute_force() = verify("randomizedTest", 0)
    @Test fun randomizedTest_sap_untracked() = verify("randomizedTest", 1)
    @Test fun randomizedTest_sap_tracked() = verify("randomizedTest", 2)
    @Test fun randomizedTest_tree_untracked() = verify("randomizedTest", 3)
    @Test fun randomizedTest_tree_tracked() = verify("randomizedTest", 4)

    @Test fun AABBBroadphaseProxyTest_helpers() {
        val proxy = AABBBroadphaseProxy(Body())
        assertTrue(proxy.toString().contains("AABB"))
    }

    @Test fun AABBBroadphaseProxyTest_compareTo() {
        val a = AABBBroadphaseProxy(Body())
        val b = AABBBroadphaseProxy(Body())
        a.aabb.set(AABB(0.0, 0.0, 10.0, 10.0))
        b.aabb.set(AABB(1.0, 1.0, 2.0, 2.0))
        assertTrue(a.compareTo(b) < 0)
        b.aabb.set(AABB(-1.0, 0.0, 5.0, 5.0))
        assertTrue(a.compareTo(b) > 0)
        b.aabb.set(AABB(0.0, 1.0, 5.0, 5.0))
        assertTrue(a.compareTo(b) < 0)
        b.aabb.set(AABB(0.0, 0.0, 5.0, 5.0))
        assertTrue(a.compareTo(b) > 0)
        assertEquals(0, a.compareTo(a))
    }

    @Test fun AbstractBroadphaseDetectorTest_createNullFilter() {
        assertFailsWith<NullPointerException> {
            ConstructorProbe(null, CollisionBodyAABBProducer(), NullAABBExpansionMethod())
        }
    }

    @Test fun AbstractBroadphaseDetectorTest_createNullAABBProducer() {
        assertFailsWith<NullPointerException> {
            ConstructorProbe(CollisionBodyBroadphaseFilter(), null, NullAABBExpansionMethod())
        }
    }

    @Test fun AbstractBroadphaseDetectorTest_createNullAABBExpansionMethod() {
        assertFailsWith<NullPointerException> {
            ConstructorProbe(CollisionBodyBroadphaseFilter(), CollisionBodyAABBProducer(), null)
        }
    }

    @Test fun AbstractBroadphaseDetectorTest_createSuccess() {
        val filter = CollisionBodyBroadphaseFilter<Body>()
        val producer = CollisionBodyAABBProducer<Body>()
        val expansion = NullAABBExpansionMethod<Body>()
        val bp = Sap(filter, producer, expansion)
        assertFalse(bp.isUpdateTrackingEnabled())
        assertTrue(bp.getBroadphaseFilter() === filter)
        assertTrue(bp.getAABBProducer() === producer)
        assertTrue(bp.getAABBExpansionMethod() === expansion)
    }

    @Test fun AbstractBroadphaseDetectorTest_updateTracking() {
        val bp = Sap(CollisionBodyBroadphaseFilter<Body>(), CollisionBodyAABBProducer<Body>(), NullAABBExpansionMethod<Body>())
        assertFalse(bp.isUpdateTrackingEnabled())
        bp.setUpdateTrackingEnabled(true)
        assertTrue(bp.isUpdateTrackingEnabled())
        bp.setUpdateTrackingEnabled(false)
        assertFalse(bp.isUpdateTrackingEnabled())
    }

    @Test fun AbstractBroadphaseDetectorTest_detectConvexAndTransform() {
        val bp = Sap(CollisionBodyBroadphaseFilter<Body>(), CollisionBodyAABBProducer<Body>(), NullAABBExpansionMethod<Body>())
        val a = Body(1.0)
        val b = Body(0.5)
        a.translate(-1.0, 0.0)
        assertTrue(bp.detect(a, b))
        assertTrue(bp.detect(a.getFixture(0).getShape(), a.getTransform(), b.getFixture(0).getShape(), b.getTransform()))
        a.translate(-3.0, 0.0)
        assertFalse(bp.detect(a, b))
        assertFalse(bp.detect(a.getFixture(0).getShape(), a.getTransform(), b.getFixture(0).getShape(), b.getTransform()))
    }

    @Test fun AssortedBroadphaseTest_dynamicAABBSpecial() {
        val bp = DynamicAABBTree(CollisionItemBroadphaseFilter<Body, Fixture>(), CollisionItemAABBProducer<Body, Fixture>(), StaticValueAABBExpansionMethod<Item>(0.2))
        assertTrue(bp.isValid())
        assertEquals(0, bp.getHeight())
        val a = Body(1.0)
        val b = Body(0.5)
        bp.add(item(a)); bp.add(item(b))
        assertTrue(bp.isValid())
        assertTrue(bp.getHeight() > 0)
        assertTrue(bp.getPerimeterRatio() > 0.0)
        bp.remove(item(a))
        assertTrue(bp.isValid())
        assertEquals(1, bp.size())
    }

    @Test fun AssortedBroadphaseTest_bruteForceSpecial() {
        val filter = CollisionItemBroadphaseFilter<Body, Fixture>()
        val producer = CollisionItemAABBProducer<Body, Fixture>()
        val bp = BruteForceBroadphase(filter, producer)
        assertTrue(bp.getBroadphaseFilter() === filter)
        assertTrue(bp.getAABBProducer() === producer)
        assertTrue(bp.getAABBExpansionMethod() is NullAABBExpansionMethod<*>)
        assertFalse(bp.isUpdateTrackingSupported())
        bp.setUpdateTrackingEnabled(true)
        assertFalse(bp.isUpdateTrackingEnabled())
    }

    @Test fun AssortedBroadphaseTest_helpers() {
        val leaf = DynamicAABBTreeLeaf(Body())
        assertTrue(leaf.isLeaf())
        assertTrue(leaf.toString().contains("AABB"))
        val node = DynamicAABBTreeNode()
        node.left = DynamicAABBTreeNode()
        node.right = DynamicAABBTreeNode()
        assertFalse(node.isLeaf())
        assertTrue(node.toString().contains("AABB"))
    }

    @Test fun BroadphaseItemTest_create() {
        val body = Body()
        val fixture = Fixture(Circle(0.5))
        val result = BroadphaseItem(body, fixture)
        assertTrue(result.getBody() === body)
        assertTrue(result.getFixture() === fixture)
        assertTrue(result.hashCode() != 0)
    }

    @Test fun BroadphaseItemTest_copy() {
        val source = BroadphaseItem(Body(), Fixture(Circle(0.5)))
        val copy = source.copy()
        assertNotSame(source, copy)
        assertEquals(source, copy)
        assertTrue(source.getBody() === copy.getBody())
        assertTrue(source.getFixture() === copy.getFixture())
        assertEquals(source.hashCode(), copy.hashCode())
    }

    @Test fun BroadphaseItemTest_tostring() {
        val result = BroadphaseItem(Body(), Fixture(Circle(0.5)))
        assertTrue(result.toString().contains("Body="))
        assertTrue(result.toString().contains("Fixture="))
    }

    @Test fun CollisionBodyAABBProducerTest_computeSuccess() {
        val producer = CollisionBodyAABBProducer<Body>()
        val body = Body(1.0)
        body.translate(2.0, -3.0)
        assertBox(producer.compute(body), 1.0, -4.0, 3.0, -2.0)
        val result = AABB(-9.0,-9.0,-8.0,-8.0)
        producer.compute(body, result)
        assertBox(result, 1.0, -4.0, 3.0, -2.0)
        producer.compute(Body(), result)
        assertBox(result, 0.0, 0.0, 0.0, 0.0)
    }

    @Test fun CollisionBodyBroadphaseFilterTest_isAllowed() {
        val filter = CollisionBodyBroadphaseFilter<Body>()
        val a = Body(1.0)
        val b = Body(1.0)
        assertFalse(filter.isAllowed(null, null))
        assertTrue(filter.isAllowed(null, a))
        assertTrue(filter.isAllowed(a, null))
        assertTrue(filter.isAllowed(a, b))
        assertFalse(filter.isAllowed(a, a))
    }

    @Test fun CollisionItemAABBProducerTest_computeSuccess() {
        val producer = CollisionItemAABBProducer<Body, Fixture>()
        val body = Body(1.0)
        body.translate(-2.0, 3.0)
        assertBox(producer.compute(item(body)), -3.0, 2.0, -1.0, 4.0)
        val result = AABB(7.0,7.0,8.0,8.0)
        producer.compute(item(body), result)
        assertBox(result, -3.0, 2.0, -1.0, 4.0)
    }

    @Test fun CollisionItemBroadphaseFilterTest_isAllowed() {
        val filter = CollisionItemBroadphaseFilter<Body, Fixture>()
        val a = Body(1.0)
        val b = Body(1.0)
        b.addFixture(Circle(0.5))
        assertFalse(filter.isAllowed(null, null))
        assertTrue(filter.isAllowed(item(a), item(b)))
        assertTrue(filter.isAllowed(item(b), item(a)))
        assertFalse(filter.isAllowed(item(a), item(a)))
        assertFalse(filter.isAllowed(item(b), item(b,1)))
    }

    @Test fun CollisionItemBroadphasePairTest_create() {
        val a = Body(1.0); val b = Body(1.0)
        val pair = BroadphasePair(item(a), item(b))
        assertTrue(pair.getFirst().getBody() === a)
        assertTrue(pair.getSecond().getBody() === b)
        assertTrue(pair.hashCode() != 0)
    }

    @Test fun CollisionItemBroadphasePairTest_hashcodeEquals() {
        val a = Body(1.0); val b = Body(1.0)
        val forward = BroadphasePair(item(a), item(b))
        val reverse = BroadphasePair(item(b), item(a))
        val duplicate = BroadphasePair(item(a), item(a))
        assertEquals(forward, reverse)
        assertEquals(forward.hashCode(), reverse.hashCode())
        assertFalse(forward == duplicate)
    }

    @Test fun CollisionItemBroadphasePairTest_copy() {
        val pair = BroadphasePair(item(Body(1.0)), item(Body(1.0)))
        val copy = pair.copy()
        assertNotSame(pair, copy)
        assertEquals(pair, copy)
        assertTrue(pair.getFirst() === copy.getFirst())
        assertTrue(pair.getSecond() === copy.getSecond())
    }

    @Test fun CollisionItemBroadphasePairTest_tostring() {
        val pair = BroadphasePair(item(Body(1.0)), item(Body(1.0)))
        assertTrue(pair.toString().contains("First="))
        assertTrue(pair.toString().contains("Second="))
    }

    @Test fun NullAABBExpansionMethodTest_expand() {
        val method = NullAABBExpansionMethod<Any>()
        val box = AABB(-3.0,-2.0,1.0,5.0)
        method.expand(Any(), box)
        assertBox(box,-3.0,-2.0,1.0,5.0)
    }

    @Test fun StaticValueAABBExpansionMethodTest_expand() {
        val method = StaticValueAABBExpansionMethod<Any>(4.0)
        assertEquals(4.0, method.getExpansion())
        val box = AABB(-3.0,-2.0,1.0,5.0)
        method.expand(Any(), box)
        assertBox(box,-5.0,-4.0,3.0,7.0)
    }

private fun assertBox(box: AABB, minX: Double, minY: Double, maxX: Double, maxY: Double) {
    assertEquals(minX, box.getMinX(), 1e-12)
    assertEquals(minY, box.getMinY(), 1e-12)
    assertEquals(maxX, box.getMaxX(), 1e-12)
    assertEquals(maxY, box.getMaxY(), 1e-12)
}

private fun pairBodies(detector: Detector): Set<Set<Body>> = detector.detect().map {
    setOf(it.getFirst().getBody()!!, it.getSecond().getBody()!!)
}.toSet()

    private fun verify(sourceMethod: String, variant: Int) {
        val bp = detector(variant)
        when (sourceMethod) {
            "addContainsBody" -> {
                val body = Body(1.0)
                assertFalse(bp.contains(body))
                bp.add(body)
                assertEquals(1, bp.size())
                assertTrue(bp.contains(body))
                assertTrue(bp.contains(item(body)))
                body.addFixture(Circle(0.5))
                assertFalse(bp.contains(body))
                bp.add(body)
                assertEquals(2, bp.size())
                assertTrue(bp.contains(body))
                assertTrue(bp.contains(body, body.getFixture(1)))
                assertFalse(bp.contains(Body()))
            }
            "addContainsCollisionItem" -> {
                val body = Body(1.0)
                val first = item(body)
                bp.add(first)
                assertEquals(1, bp.size())
                assertTrue(bp.contains(body, body.getFixture(0)))
                body.addFixture(Circle(0.5))
                assertFalse(bp.contains(body))
                bp.add(item(body, 1))
                assertEquals(2, bp.size())
                assertTrue(bp.contains(first))
                assertTrue(bp.contains(body))
            }
            "addContainsFixture" -> {
                val body = Body(1.0)
                body.addFixture(Circle(0.5))
                bp.add(body, body.getFixture(0))
                assertFalse(bp.contains(body))
                bp.add(body, body.getFixture(1))
                assertEquals(2, bp.size())
                assertTrue(bp.contains(body))
            }
            "clear" -> {
                val a = Body(1.0); val b = Body(1.0)
                bp.add(a); bp.add(b)
                assertEquals(2, bp.size())
                bp.clear()
                assertEquals(0, bp.size())
                assertFalse(bp.contains(a))
                assertTrue(bp.detect().isEmpty())
            }
            "updateTargeted" -> {
                val a = Body(1.0); a.addFixture(Circle(0.5))
                val b = Body(1.0)
                bp.add(a); bp.add(b)
                assertTrue(bp.isUpdated(a))
                bp.clearUpdates()
                assertEquals(!bp.isUpdateTrackingEnabled(), bp.isUpdated(a))
                a.addFixture(Circle(0.25))
                bp.update(a)
                assertEquals(4, bp.size())
                assertTrue(bp.isUpdated(a, a.getFixture(2)))
                bp.clearUpdates()
                a.translate(0.5, 0.0)
                bp.update(a, a.getFixture(0))
                assertTrue(bp.isUpdated(a, a.getFixture(0)))
                if (bp.isUpdateTrackingEnabled()) assertFalse(bp.isUpdated(a, a.getFixture(1)))
                bp.clearUpdates()
                a.translate(0.5, 0.0)
                bp.update(item(a, 1))
                assertTrue(bp.isUpdated(item(a, 1)))
                assertFalse(bp.isUpdated(Body()))
            }
            "update" -> {
                val a = Body(1.0); val b = Body(1.0)
                bp.add(a); bp.add(b)
                bp.clearUpdates()
                a.translate(1.0, 0.0)
                bp.update()
                assertTrue(bp.isUpdated(a))
                if (bp.isUpdateTrackingEnabled()) assertFalse(bp.isUpdated(b))
                assertTrue(bp.getAABB(a).getMaxX() > 1.5)
            }
            "removeContainsBody" -> {
                val body = Body(1.0); body.addFixture(Circle(0.5))
                bp.add(body)
                assertTrue(bp.remove(body))
                assertEquals(0, bp.size())
                assertFalse(bp.remove(body))
                assertFalse(bp.contains(body))
            }
            "removeContainsFixture" -> {
                val body = Body(1.0); body.addFixture(Circle(0.5))
                bp.add(body)
                assertTrue(bp.remove(body, body.getFixture(1)))
                assertEquals(1, bp.size())
                assertFalse(bp.contains(body))
                assertTrue(bp.contains(item(body)))
                assertFalse(bp.remove(body, body.getFixture(1)))
                assertTrue(bp.remove(item(body)))
                assertEquals(0, bp.size())
            }
            "getAABB" -> {
                val body = Body(1.0)
                bp.add(body)
                val margin = if (variant == 0) 0.0 else 0.1
                val live = bp.getAABB(body)
                assertBox(live, -1.0-margin, -1.0-margin, 1.0+margin, 1.0+margin)
                assertEquals(bp.getAABB(body), bp.getAABB(body, body.getFixture(0)))
                assertEquals(bp.getAABB(body), bp.getAABB(item(body)))
                assertBox(bp.getAABB(Body()), 0.0, 0.0, 0.0, 0.0)
                val other = Body(1.0); other.addFixture(Circle(0.5))
                assertBox(bp.getAABB(other), -1.0-margin, -1.0-margin, 1.0+margin, 1.0+margin)
                body.translate(2.0, 0.0)
                bp.update(body)
                assertTrue(live === bp.getAABB(body))
                assertBox(live, 1.0-margin, -1.0-margin, 3.0+margin, 1.0+margin)
            }
            "getAABBProducer" -> assertTrue(bp.getAABBProducer() is CollisionItemAABBProducer<*, *>)
            "getBroadphaseFilter" -> assertTrue(bp.getBroadphaseFilter() is CollisionItemBroadphaseFilter<*, *>)
            "getAABBExpansionMethod" -> {
                if (variant == 0) assertTrue(bp.getAABBExpansionMethod() is NullAABBExpansionMethod<*>)
                else {
                    val method = bp.getAABBExpansionMethod()
                    assertTrue(method is StaticValueAABBExpansionMethod<*>)
                    assertEquals(0.2, method.getExpansion())
                }
            }
            "updateSmall" -> {
                val body = Body(1.0)
                bp.add(body)
                val before = bp.getAABB(body).copy()
                bp.clearUpdates()
                body.translate(0.05, 0.0)
                bp.update(body)
                if (variant == 0) assertBox(bp.getAABB(body), -0.95, -1.0, 1.05, 1.0)
                else assertEquals(before, bp.getAABB(body))
                if (bp.isUpdateTrackingEnabled()) assertFalse(bp.isUpdated(body))
            }
            "updateLarge" -> {
                val body = Body(1.0)
                bp.add(body)
                val before = bp.getAABB(body).copy()
                body.translate(0.5, 0.0)
                bp.update(body)
                assertFalse(before == bp.getAABB(body))
                assertTrue(bp.isUpdated(body))
            }
            "getSetUpdateTrackingEnabled" -> {
                assertEquals(variant == 2 || variant == 4, bp.isUpdateTrackingEnabled())
                bp.setUpdateTrackingEnabled(false)
                assertFalse(bp.isUpdateTrackingEnabled())
                bp.setUpdateTrackingEnabled(true)
                assertEquals(variant != 0, bp.isUpdateTrackingEnabled())
            }
            "isUpdateTrackingSupported" -> assertEquals(variant != 0, bp.isUpdateTrackingSupported())
            "optimize" -> {
                bp.optimize()
                val a = Body(1.0); val b = Body(2.0)
                bp.add(a); bp.add(b)
                val before = pairBodies(bp)
                bp.optimize()
                assertEquals(2, bp.size())
                assertEquals(before, pairBodies(bp))
            }
            "setUpdated" -> {
                val a = Body(1.0); a.addFixture(Circle(0.5))
                val b = Body(1.0)
                bp.add(a); bp.add(b)
                bp.clearUpdates()
                bp.setUpdated(a, a.getFixture(0))
                if (bp.isUpdateTrackingEnabled()) {
                    assertTrue(bp.isUpdated(a, a.getFixture(0)))
                    assertFalse(bp.isUpdated(a, a.getFixture(1)))
                    assertFalse(bp.isUpdated(b))
                } else assertTrue(bp.isUpdated(b))
                bp.clearUpdates()
                bp.setUpdated(a)
                if (bp.isUpdateTrackingEnabled()) {
                    assertTrue(bp.isUpdated(a, a.getFixture(0)))
                    assertTrue(bp.isUpdated(a, a.getFixture(1)))
                    assertFalse(bp.isUpdated(b))
                }
            }
            "size" -> {
                val a = Body(1.0); a.addFixture(Circle(0.5))
                val b = Body(1.0)
                assertEquals(0, bp.size())
                bp.add(a); bp.add(b)
                assertEquals(3, bp.size())
                bp.remove(a, a.getFixture(0))
                assertEquals(2, bp.size())
                bp.clear()
                assertEquals(0, bp.size())
            }
            "detectConvexAndTransform" -> {
                val a = Body(1.0); val b = Body(0.5)
                a.translate(-1.0, 0.0); b.translate(0.0, 0.0)
                assertTrue(bp.detect(a, b))
                assertTrue(bp.detect(a, a.getFixture(0), b, b.getFixture(0)))
                assertTrue(bp.detect(a.getFixture(0).getShape(), a.getTransform(), b.getFixture(0).getShape(), b.getTransform()))
                a.translate(-3.0, 0.0)
                assertFalse(bp.detect(a, b))
                assertFalse(bp.detect(a, a.getFixture(0), b, b.getFixture(0)))
            }
            "detectIteratorFailure" -> {
                val a = Body(1.0); val b = Body(1.0)
                bp.add(a); bp.add(b)
                val iterator = bp.detectIterator(true)
                assertTrue(iterator.hasNext())
                val pair = iterator.next()
                assertEquals(setOf(a,b), setOf(pair.getFirst().getBody(), pair.getSecond().getBody()))
                assertFailsWith<NoSuchElementException> { iterator.next() }
                assertFailsWith<UnsupportedOperationException> { bp.detectIterator(true).remove() }
            }
            "raycastIteratorFailure" -> {
                bp.add(Body(1.0))
                val ray = Ray(Vector2(-3.0, 0.0), Vector2(1.0, 0.0))
                val iterator = bp.raycastIterator(ray, 5.0)
                assertTrue(iterator.hasNext())
                iterator.next()
                assertFailsWith<NoSuchElementException> { iterator.next() }
                assertFailsWith<UnsupportedOperationException> { bp.raycastIterator(ray, 5.0).remove() }
            }
            "detectAABBIteratorFailure" -> {
                bp.add(Body(1.0))
                val iterator = bp.detectIterator(AABB(-0.5,-0.5,0.5,0.5))
                assertTrue(iterator.hasNext())
                iterator.next()
                assertFailsWith<NoSuchElementException> { iterator.next() }
                assertFailsWith<UnsupportedOperationException> { bp.detectIterator(AABB(-0.5,-0.5,0.5,0.5)).remove() }
            }
            "detectEmptyIterator" -> {
                assertFalse(bp.detectIterator(true).hasNext())
                assertFalse(bp.detectIterator(AABB(-1.0,-1.0,1.0,1.0)).hasNext())
                assertFalse(bp.raycastIterator(Ray(Vector2(1.0,0.0)), 1.0).hasNext())
            }
            "detect" -> {
                val a = Body(1.0); val b = Body(1.0); val far = Body(1.0)
                b.translate(1.5,0.0); far.translate(8.0,0.0)
                bp.add(a); bp.add(b); bp.add(far)
                assertEquals(setOf(setOf(a,b)), pairBodies(bp))
                bp.clearUpdates()
                assertEquals(if (bp.isUpdateTrackingEnabled()) 0 else 1, bp.detect(false).size)
                assertEquals(1, bp.detect(true).size)
            }
            "detectAABB" -> {
                val a = Body(1.0); val b = Body(1.0); val far = Body(1.0)
                b.translate(4.0,0.0); far.translate(9.0,0.0)
                bp.add(a); bp.add(b); bp.add(far)
                assertEquals(setOf(a), bp.detect(AABB(-0.5,-0.5,0.5,0.5)).map { it.getBody() }.toSet())
                assertEquals(setOf(a,b), bp.detect(AABB(-0.5,-0.5,4.5,0.5)).map { it.getBody() }.toSet())
            }
            "detectRay" -> {
                val a = Body(1.0); val b = Body(1.0); val far = Body(1.0)
                b.translate(4.0,0.0); far.translate(9.0,3.0)
                bp.add(a); bp.add(b); bp.add(far)
                val ray = Ray(Vector2(-3.0,0.0), Vector2(1.0,0.0))
                assertEquals(setOf(a,b), bp.raycast(ray,0.0).map { it.getBody() }.toSet())
                assertEquals(setOf(a), bp.raycast(ray,3.0).map { it.getBody() }.toSet())
            }
            "shiftCoordinates" -> {
                val a = Body(1.0); val b = Body(1.0)
                b.translate(1.5,0.0)
                bp.add(a); bp.add(b)
                assertEquals(1, bp.detect().size)
                bp.shift(Vector2(3.0,-2.0))
                assertEquals(1, bp.detect().size)
                assertBox(bp.getAABB(a), 2.0 - if (variant==0) 0.0 else 0.1, -3.0 - if (variant==0) 0.0 else 0.1, 4.0 + if (variant==0) 0.0 else 0.1, -1.0 + if (variant==0) 0.0 else 0.1)
            }
            "randomizedTest" -> {
                val bodies = (0 until 16).map { index -> Body(0.5).also { it.translate(index * 0.8, if (index % 2 == 0) 0.0 else 0.2); bp.add(it) } }
                val detected = pairBodies(bp)
                for (i in bodies.indices) for (j in i+1 until bodies.size) {
                    val dx = (i-j) * 0.8
                    val dy = if (i % 2 == j % 2) 0.0 else 0.2
                    if (dx*dx + dy*dy < 1.0) assertTrue(setOf(bodies[i], bodies[j]) in detected)
                }
                for (index in 0 until 8) {
                    val left = index * 1.6
                    val hits = bp.detect(AABB(left, -0.2, left + 0.2, 0.2)).map { it.getBody() }.toSet()
                    val expected = bodies.filter { body -> body.createAABB().overlaps(AABB(left,-0.2,left+0.2,0.2)) }.toSet()
                    assertTrue(hits.containsAll(expected))
                }
                val crossing = Ray(Vector2(-2.0,0.0), Vector2(1.0,0.0))
                assertTrue(bp.raycast(crossing, 0.0).map { it.getBody() }.toSet().containsAll(bodies))
                val removed = bodies.filterIndexed { index, _ -> index % 4 == 0 }
                removed.forEach { assertTrue(bp.remove(it)) }
                assertTrue(bp.detect().none { it.getFirst().getBody() in removed || it.getSecond().getBody() in removed })
                assertTrue(bp.raycast(crossing, 0.0).none { it.getBody() in removed })
                bodies[1].translate(30.0, 0.0)
                bp.update(bodies[1])
                assertTrue(bp.detect(AABB(30.0,-1.0,33.0,1.0)).any { it.getBody() === bodies[1] })
            }
            else -> error("unmapped source method: $sourceMethod")
        }
    }
}
