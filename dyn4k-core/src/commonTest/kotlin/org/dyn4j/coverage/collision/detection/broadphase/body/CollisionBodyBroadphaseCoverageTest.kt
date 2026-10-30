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
package org.dyn4j.coverage.collision.detection.broadphase.body

import de.infix.testBalloon.framework.core.testSuite
import kotlin.math.max
import kotlin.math.min
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.collision.AbstractCollisionBody
import org.dyn4j.collision.CollisionPair
import org.dyn4j.collision.Fixture
import org.dyn4j.collision.broadphase.BroadphaseDetector
import org.dyn4j.collision.broadphase.BruteForceBroadphase
import org.dyn4j.collision.broadphase.CollisionBodyAABBProducer
import org.dyn4j.collision.broadphase.CollisionBodyBroadphaseFilter
import org.dyn4j.collision.broadphase.DynamicAABBTree
import org.dyn4j.collision.broadphase.Sap
import org.dyn4j.collision.broadphase.StaticValueAABBExpansionMethod
import org.dyn4j.geometry.AABB
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.Ray
import org.dyn4j.geometry.Vector2

val CollisionBodyBroadphaseCoverageTest by testSuite {
    test("addContainsBody_sap_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { addContainsBody_sap_untracked() } }
    test("addContainsBody_sap_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { addContainsBody_sap_tracked() } }
    test("addContainsBody_tree_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { addContainsBody_tree_untracked() } }
    test("addContainsBody_tree_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { addContainsBody_tree_tracked() } }
    test("addContainsBody_brute_force") { CollisionBodyBroadphaseCoverageTestFixture().run { addContainsBody_brute_force() } }
    test("clear_sap_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { clear_sap_untracked() } }
    test("clear_sap_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { clear_sap_tracked() } }
    test("clear_tree_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { clear_tree_untracked() } }
    test("clear_tree_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { clear_tree_tracked() } }
    test("clear_brute_force") { CollisionBodyBroadphaseCoverageTestFixture().run { clear_brute_force() } }
    test("updateTargeted_sap_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { updateTargeted_sap_untracked() } }
    test("updateTargeted_sap_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { updateTargeted_sap_tracked() } }
    test("updateTargeted_tree_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { updateTargeted_tree_untracked() } }
    test("updateTargeted_tree_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { updateTargeted_tree_tracked() } }
    test("updateTargeted_brute_force") { CollisionBodyBroadphaseCoverageTestFixture().run { updateTargeted_brute_force() } }
    test("update_sap_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { update_sap_untracked() } }
    test("update_sap_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { update_sap_tracked() } }
    test("update_tree_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { update_tree_untracked() } }
    test("update_tree_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { update_tree_tracked() } }
    test("update_brute_force") { CollisionBodyBroadphaseCoverageTestFixture().run { update_brute_force() } }
    test("removeContainsBody_sap_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { removeContainsBody_sap_untracked() } }
    test("removeContainsBody_sap_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { removeContainsBody_sap_tracked() } }
    test("removeContainsBody_tree_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { removeContainsBody_tree_untracked() } }
    test("removeContainsBody_tree_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { removeContainsBody_tree_tracked() } }
    test("removeContainsBody_brute_force") { CollisionBodyBroadphaseCoverageTestFixture().run { removeContainsBody_brute_force() } }
    test("getAABB_sap_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { getAABB_sap_untracked() } }
    test("getAABB_sap_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { getAABB_sap_tracked() } }
    test("getAABB_tree_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { getAABB_tree_untracked() } }
    test("getAABB_tree_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { getAABB_tree_tracked() } }
    test("getAABB_brute_force") { CollisionBodyBroadphaseCoverageTestFixture().run { getAABB_brute_force() } }
    test("getAABBExpansionMethod_sap_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { getAABBExpansionMethod_sap_untracked() } }
    test("getAABBExpansionMethod_sap_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { getAABBExpansionMethod_sap_tracked() } }
    test("getAABBExpansionMethod_tree_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { getAABBExpansionMethod_tree_untracked() } }
    test("getAABBExpansionMethod_tree_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { getAABBExpansionMethod_tree_tracked() } }
    test("getAABBExpansionMethod_brute_force") { CollisionBodyBroadphaseCoverageTestFixture().run { getAABBExpansionMethod_brute_force() } }
    test("updateSmall_sap_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { updateSmall_sap_untracked() } }
    test("updateSmall_sap_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { updateSmall_sap_tracked() } }
    test("updateSmall_tree_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { updateSmall_tree_untracked() } }
    test("updateSmall_tree_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { updateSmall_tree_tracked() } }
    test("updateSmall_brute_force") { CollisionBodyBroadphaseCoverageTestFixture().run { updateSmall_brute_force() } }
    test("updateLarge_sap_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { updateLarge_sap_untracked() } }
    test("updateLarge_sap_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { updateLarge_sap_tracked() } }
    test("updateLarge_tree_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { updateLarge_tree_untracked() } }
    test("updateLarge_tree_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { updateLarge_tree_tracked() } }
    test("updateLarge_brute_force") { CollisionBodyBroadphaseCoverageTestFixture().run { updateLarge_brute_force() } }
    test("getSetUpdateTrackingEnabled_sap_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { getSetUpdateTrackingEnabled_sap_untracked() } }
    test("getSetUpdateTrackingEnabled_sap_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { getSetUpdateTrackingEnabled_sap_tracked() } }
    test("getSetUpdateTrackingEnabled_tree_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { getSetUpdateTrackingEnabled_tree_untracked() } }
    test("getSetUpdateTrackingEnabled_tree_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { getSetUpdateTrackingEnabled_tree_tracked() } }
    test("getSetUpdateTrackingEnabled_brute_force") { CollisionBodyBroadphaseCoverageTestFixture().run { getSetUpdateTrackingEnabled_brute_force() } }
    test("isUpdateTrackingSupported_sap_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { isUpdateTrackingSupported_sap_untracked() } }
    test("isUpdateTrackingSupported_sap_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { isUpdateTrackingSupported_sap_tracked() } }
    test("isUpdateTrackingSupported_tree_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { isUpdateTrackingSupported_tree_untracked() } }
    test("isUpdateTrackingSupported_tree_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { isUpdateTrackingSupported_tree_tracked() } }
    test("isUpdateTrackingSupported_brute_force") { CollisionBodyBroadphaseCoverageTestFixture().run { isUpdateTrackingSupported_brute_force() } }
    test("optimize_sap_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { optimize_sap_untracked() } }
    test("optimize_sap_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { optimize_sap_tracked() } }
    test("optimize_tree_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { optimize_tree_untracked() } }
    test("optimize_tree_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { optimize_tree_tracked() } }
    test("optimize_brute_force") { CollisionBodyBroadphaseCoverageTestFixture().run { optimize_brute_force() } }
    test("setUpdated_sap_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { setUpdated_sap_untracked() } }
    test("setUpdated_sap_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { setUpdated_sap_tracked() } }
    test("setUpdated_tree_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { setUpdated_tree_untracked() } }
    test("setUpdated_tree_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { setUpdated_tree_tracked() } }
    test("setUpdated_brute_force") { CollisionBodyBroadphaseCoverageTestFixture().run { setUpdated_brute_force() } }
    test("size_sap_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { size_sap_untracked() } }
    test("size_sap_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { size_sap_tracked() } }
    test("size_tree_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { size_tree_untracked() } }
    test("size_tree_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { size_tree_tracked() } }
    test("size_brute_force") { CollisionBodyBroadphaseCoverageTestFixture().run { size_brute_force() } }
    test("detectConvexAndTransform_sap_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { detectConvexAndTransform_sap_untracked() } }
    test("detectConvexAndTransform_sap_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { detectConvexAndTransform_sap_tracked() } }
    test("detectConvexAndTransform_tree_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { detectConvexAndTransform_tree_untracked() } }
    test("detectConvexAndTransform_tree_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { detectConvexAndTransform_tree_tracked() } }
    test("detectConvexAndTransform_brute_force") { CollisionBodyBroadphaseCoverageTestFixture().run { detectConvexAndTransform_brute_force() } }
    test("detectIteratorFailure_sap_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { detectIteratorFailure_sap_untracked() } }
    test("detectIteratorFailure_sap_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { detectIteratorFailure_sap_tracked() } }
    test("detectIteratorFailure_tree_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { detectIteratorFailure_tree_untracked() } }
    test("detectIteratorFailure_tree_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { detectIteratorFailure_tree_tracked() } }
    test("detectIteratorFailure_brute_force") { CollisionBodyBroadphaseCoverageTestFixture().run { detectIteratorFailure_brute_force() } }
    test("raycastIteratorFailure_sap_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { raycastIteratorFailure_sap_untracked() } }
    test("raycastIteratorFailure_sap_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { raycastIteratorFailure_sap_tracked() } }
    test("raycastIteratorFailure_tree_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { raycastIteratorFailure_tree_untracked() } }
    test("raycastIteratorFailure_tree_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { raycastIteratorFailure_tree_tracked() } }
    test("raycastIteratorFailure_brute_force") { CollisionBodyBroadphaseCoverageTestFixture().run { raycastIteratorFailure_brute_force() } }
    test("detectAABBIteratorFailure_sap_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { detectAABBIteratorFailure_sap_untracked() } }
    test("detectAABBIteratorFailure_sap_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { detectAABBIteratorFailure_sap_tracked() } }
    test("detectAABBIteratorFailure_tree_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { detectAABBIteratorFailure_tree_untracked() } }
    test("detectAABBIteratorFailure_tree_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { detectAABBIteratorFailure_tree_tracked() } }
    test("detectAABBIteratorFailure_brute_force") { CollisionBodyBroadphaseCoverageTestFixture().run { detectAABBIteratorFailure_brute_force() } }
    test("detectEmptyIterator_sap_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { detectEmptyIterator_sap_untracked() } }
    test("detectEmptyIterator_sap_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { detectEmptyIterator_sap_tracked() } }
    test("detectEmptyIterator_tree_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { detectEmptyIterator_tree_untracked() } }
    test("detectEmptyIterator_tree_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { detectEmptyIterator_tree_tracked() } }
    test("detectEmptyIterator_brute_force") { CollisionBodyBroadphaseCoverageTestFixture().run { detectEmptyIterator_brute_force() } }
    test("detect_sap_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { detect_sap_untracked() } }
    test("detect_sap_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { detect_sap_tracked() } }
    test("detect_tree_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { detect_tree_untracked() } }
    test("detect_tree_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { detect_tree_tracked() } }
    test("detect_brute_force") { CollisionBodyBroadphaseCoverageTestFixture().run { detect_brute_force() } }
    test("detectAABB_sap_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { detectAABB_sap_untracked() } }
    test("detectAABB_sap_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { detectAABB_sap_tracked() } }
    test("detectAABB_tree_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { detectAABB_tree_untracked() } }
    test("detectAABB_tree_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { detectAABB_tree_tracked() } }
    test("detectAABB_brute_force") { CollisionBodyBroadphaseCoverageTestFixture().run { detectAABB_brute_force() } }
    test("detectRay_sap_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { detectRay_sap_untracked() } }
    test("detectRay_sap_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { detectRay_sap_tracked() } }
    test("detectRay_tree_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { detectRay_tree_untracked() } }
    test("detectRay_tree_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { detectRay_tree_tracked() } }
    test("detectRay_brute_force") { CollisionBodyBroadphaseCoverageTestFixture().run { detectRay_brute_force() } }
    test("shiftCoordinates_sap_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { shiftCoordinates_sap_untracked() } }
    test("shiftCoordinates_sap_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { shiftCoordinates_sap_tracked() } }
    test("shiftCoordinates_tree_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { shiftCoordinates_tree_untracked() } }
    test("shiftCoordinates_tree_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { shiftCoordinates_tree_tracked() } }
    test("shiftCoordinates_brute_force") { CollisionBodyBroadphaseCoverageTestFixture().run { shiftCoordinates_brute_force() } }
    test("getBroadphaseFilter_sap_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { getBroadphaseFilter_sap_untracked() } }
    test("getBroadphaseFilter_sap_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { getBroadphaseFilter_sap_tracked() } }
    test("getBroadphaseFilter_tree_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { getBroadphaseFilter_tree_untracked() } }
    test("getBroadphaseFilter_tree_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { getBroadphaseFilter_tree_tracked() } }
    test("getBroadphaseFilter_brute_force") { CollisionBodyBroadphaseCoverageTestFixture().run { getBroadphaseFilter_brute_force() } }
    test("randomizedTest_sap_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { randomizedTest_sap_untracked() } }
    test("randomizedTest_sap_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { randomizedTest_sap_tracked() } }
    test("randomizedTest_tree_untracked") { CollisionBodyBroadphaseCoverageTestFixture().run { randomizedTest_tree_untracked() } }
    test("randomizedTest_tree_tracked") { CollisionBodyBroadphaseCoverageTestFixture().run { randomizedTest_tree_tracked() } }
    test("randomizedTest_brute_force") { CollisionBodyBroadphaseCoverageTestFixture().run { randomizedTest_brute_force() } }
}

private class Body : AbstractCollisionBody<Fixture> {
    constructor() : super()
    constructor(shape: Convex) : this() { addFixture(shape) }
    override fun addFixture(convex: Convex?): Fixture = Fixture(convex).also { addFixture(it) }
    override fun getLocalCenter() = Vector2()
    override fun copy() = Body().also { copy ->
        for (fixture in getFixtures()) copy.addFixture(fixture.copy())
        copy.setTransform(getTransform().copy())
    }
}

private enum class Variant { SAP_UNTRACKED, SAP_TRACKED, TREE_UNTRACKED, TREE_TRACKED, BRUTE_FORCE }

private class CollisionBodyBroadphaseCoverageTestFixture  {
    private fun detector(variant: Variant): BroadphaseDetector<Body> {
        val filter = CollisionBodyBroadphaseFilter<Body>()
        val producer = CollisionBodyAABBProducer<Body>()
        val expansion = StaticValueAABBExpansionMethod<Body>(0.2)
        return when (variant) {
            Variant.SAP_UNTRACKED -> Sap(filter, producer, expansion).also { it.setUpdateTrackingEnabled(false) }
            Variant.SAP_TRACKED -> Sap(filter, producer, expansion).also { it.setUpdateTrackingEnabled(true) }
            Variant.TREE_UNTRACKED -> DynamicAABBTree(filter, producer, expansion).also { it.setUpdateTrackingEnabled(false) }
            Variant.TREE_TRACKED -> DynamicAABBTree(filter, producer, expansion).also { it.setUpdateTrackingEnabled(true) }
            Variant.BRUTE_FORCE -> BruteForceBroadphase(filter, producer)
        }
    }

    private fun body(radius: Double = 1.0) = Body(Geometry.createCircle(radius))
    private fun tracked(variant: Variant) = variant == Variant.SAP_TRACKED || variant == Variant.TREE_TRACKED
    private fun expanded(variant: Variant) = variant != Variant.BRUTE_FORCE

    private fun addContainsBody(variant: Variant) {
        val bp = detector(variant)
        val first = body()
        assertEquals(0, bp.size())
        assertFalse(bp.contains(first))
        bp.add(first)
        assertEquals(1, bp.size())
        assertTrue(bp.contains(first))
        first.addFixture(Geometry.createCircle(0.5))
        bp.add(first)
        assertEquals(1, bp.size())
        assertTrue(bp.contains(first))
        assertFalse(bp.contains(Body()))
        val second = body()
        bp.add(second)
        assertEquals(2, bp.size())
        assertTrue(bp.contains(first))
        assertTrue(bp.contains(second))
    }

    private fun clear(variant: Variant) {
        val bp = detector(variant)
        val first = body()
        val second = body()
        bp.add(first); bp.add(second)
        assertEquals(2, bp.size())
        assertTrue(bp.contains(first)); assertTrue(bp.contains(second))
        bp.clear()
        assertEquals(0, bp.size())
        assertFalse(bp.contains(first)); assertFalse(bp.contains(second))
    }

    private fun updateCase(variant: Variant, targeted: Boolean) {
        val bp = detector(variant)
        val first = body()
        first.addFixture(Geometry.createCircle(0.5))
        val second = body()
        bp.add(first); bp.add(second)
        assertTrue(bp.isUpdated(first)); assertTrue(bp.isUpdated(second))
        bp.clearUpdates()
        assertEquals(!tracked(variant), bp.isUpdated(first))
        assertEquals(!tracked(variant), bp.isUpdated(second))
        first.addFixture(Geometry.createCircle(0.25)).getShape().translate(1.0, 1.0)
        if (targeted) bp.update(first) else bp.update()
        assertTrue(bp.isUpdated(first))
        assertEquals(!tracked(variant), bp.isUpdated(second))
        bp.clearUpdates()
        assertEquals(!tracked(variant), bp.isUpdated(first))
        first.translate(0.4, 0.0)
        if (targeted) bp.update(first) else bp.update()
        assertTrue(bp.isUpdated(first))
        assertEquals(!tracked(variant), bp.isUpdated(second))
        bp.clearUpdates()
        assertFalse(bp.isUpdated(Body()))
    }

    private fun removeContainsBody(variant: Variant) {
        val bp = detector(variant)
        val first = body().also { it.addFixture(Geometry.createCircle(3.0)) }
        val second = body(2.0)
        bp.add(first); bp.add(second)
        assertTrue(bp.contains(first)); assertTrue(bp.contains(second))
        assertTrue(bp.remove(second))
        assertTrue(bp.contains(first)); assertFalse(bp.contains(second))
        bp.remove(Body())
        assertTrue(bp.contains(first)); assertFalse(bp.contains(second))
        assertTrue(bp.remove(first))
        assertFalse(bp.contains(first)); assertFalse(bp.contains(second))
        assertFalse(bp.remove(body()))
    }

    private fun getAABB(variant: Variant) {
        val bp = detector(variant)
        val first = body()
        bp.add(first)
        val stored = bp.getAABB(first)
        assertBounds(stored, if (expanded(variant)) -1.1 else -1.0, if (expanded(variant)) 1.1 else 1.0,
            if (expanded(variant)) -1.1 else -1.0, if (expanded(variant)) 1.1 else 1.0)
        assertSame(stored, bp.getAABB(first))
        val empty = bp.getAABB(Body())
        assertTrue(empty.isDegenerate())
        assertBounds(empty, 0.0, 0.0, 0.0, 0.0)
        val absent = body().also { it.addFixture(Geometry.createCircle(0.5)) }
        assertBounds(bp.getAABB(absent), if (expanded(variant)) -1.1 else -1.0,
            if (expanded(variant)) 1.1 else 1.0, if (expanded(variant)) -1.1 else -1.0,
            if (expanded(variant)) 1.1 else 1.0)
        assertFalse(bp.contains(absent))
    }

    private fun getAABBExpansionMethod(variant: Variant) {
        assertNotNull(detector(variant).getAABBExpansionMethod())
    }

    private fun assertBounds(aabb: AABB, minX: Double, maxX: Double, minY: Double, maxY: Double) {
        assertEquals(minX, aabb.getMinX(), 1e-12)
        assertEquals(maxX, aabb.getMaxX(), 1e-12)
        assertEquals(minY, aabb.getMinY(), 1e-12)
        assertEquals(maxY, aabb.getMaxY(), 1e-12)
    }

    private fun updateSmall(variant: Variant) {
        val bp = detector(variant)
        val first = body()
        bp.add(first); bp.clearUpdates()
        val old = bp.getAABB(first).copy()
        first.translate(0.1, 0.0)
        bp.update(first)
        if (expanded(variant)) {
            assertEquals(old, bp.getAABB(first))
            if (tracked(variant)) assertFalse(bp.isUpdated(first))
        } else {
            assertBounds(bp.getAABB(first), -0.9, 1.1, -1.0, 1.0)
        }
    }

    private fun updateLarge(variant: Variant) {
        val bp = detector(variant)
        val first = body()
        bp.add(first)
        val old = bp.getAABB(first).copy()
        first.translate(0.4, 0.0)
        bp.update(first)
        assertFalse(old == bp.getAABB(first))
        assertTrue(bp.isUpdated(first))
    }

    private fun getSetUpdateTrackingEnabled(variant: Variant) {
        val bp = detector(variant)
        bp.setUpdateTrackingEnabled(true)
        bp.setUpdateTrackingEnabled(false)
        assertFalse(bp.isUpdateTrackingEnabled())
        bp.setUpdateTrackingEnabled(true)
        assertEquals(expanded(variant), bp.isUpdateTrackingEnabled())
    }

    private fun isUpdateTrackingSupported(variant: Variant) {
        assertEquals(expanded(variant), detector(variant).isUpdateTrackingSupported())
    }

    private fun optimize(variant: Variant) {
        val bp = detector(variant)
        bp.optimize()
        val first = body().also { it.addFixture(Geometry.createCircle(3.0)) }
        val second = body(2.0)
        bp.add(first); bp.add(second)
        bp.optimize()
        assertEquals(2, bp.size())
        assertTrue(bp.contains(first)); assertTrue(bp.contains(second))
    }

    private fun setUpdated(variant: Variant) {
        val bp = detector(variant)
        val first = body().also { it.addFixture(Geometry.createCircle(0.5)) }
        val second = body()
        bp.add(first); bp.add(second)
        assertTrue(bp.isUpdated(first)); assertTrue(bp.isUpdated(second))
        bp.clearUpdates()
        assertEquals(!tracked(variant), bp.isUpdated(first))
        assertEquals(!tracked(variant), bp.isUpdated(second))
        bp.setUpdated(first)
        assertTrue(bp.isUpdated(first))
        assertEquals(!tracked(variant), bp.isUpdated(second))
        bp.clearUpdates(); bp.setUpdated(second)
        assertEquals(!tracked(variant), bp.isUpdated(first))
        assertTrue(bp.isUpdated(second))
        bp.clearUpdates()
        assertEquals(!tracked(variant), bp.isUpdated(first))
        assertEquals(!tracked(variant), bp.isUpdated(second))
    }

    private fun size(variant: Variant) {
        val bp = detector(variant)
        val first = body().also { it.addFixture(Geometry.createCircle(0.5)) }
        val second = body()
        assertEquals(0, bp.size())
        bp.add(first); bp.add(second)
        assertEquals(2, bp.size())
        bp.remove(first)
        assertEquals(1, bp.size())
        bp.clear()
        assertEquals(0, bp.size())
    }

    private fun detectConvexAndTransform(variant: Variant) {
        val bp = detector(variant)
        val first = body().also { it.translate(-2.0, 0.0) }
        val second = Body(Geometry.createUnitCirclePolygon(5, 0.5)).also { it.translate(-1.0, 1.0) }
        assertTrue(bp.detect(first, second))
        assertTrue(bp.detect(first.getFixture(0).getShape(), first.getTransform(),
            second.getFixture(0).getShape(), second.getTransform()))
        first.translate(-1.0, 0.0)
        assertFalse(bp.detect(first, second))
        assertFalse(bp.detect(first.getFixture(0).getShape(), first.getTransform(),
            second.getFixture(0).getShape(), second.getTransform()))
    }

    private data class Scene(val first: Body, val second: Body, val third: Body, val fourth: Body) {
        val bodies get() = listOf(first, second, third, fourth)
    }

    private fun scene(bp: BroadphaseDetector<Body>, fourthY: Double = 1.0): Scene {
        val first = body().also { it.translate(-2.0, 0.0) }
        val second = Body(Geometry.createUnitCirclePolygon(5, 0.5)).also { it.translate(-1.0, 1.0) }
        val third = Body(Geometry.createRectangle(1.0, 0.5)).also { it.translate(0.5, -2.0) }
        val fourth = Body(Geometry.createVerticalSegment(2.0)).also { it.translate(1.0, fourthY) }
        return Scene(first, second, third, fourth).also { it.bodies.forEach(bp::add) }
    }

    private fun pairIs(pair: CollisionPair<Body>, first: Body, second: Body): Boolean =
        pair.getFirst() === first && pair.getSecond() === second ||
            pair.getFirst() === second && pair.getSecond() === first

    private fun assertIdentities(actual: List<Body>, vararg expected: Body) {
        assertEquals(expected.size, actual.size)
        for (item in expected) assertEquals(1, actual.count { it === item })
    }

    private fun detectIteratorFailure(variant: Variant) {
        val bp = detector(variant)
        val bodies = scene(bp)
        val iterator = bp.detectIterator(false)
        assertTrue(iterator.hasNext())
        assertTrue(pairIs(iterator.next(), bodies.first, bodies.second))
        assertFailsWith<NoSuchElementException> { iterator.next() }
        val secondIterator = bp.detectIterator(false)
        secondIterator.next()
        assertFailsWith<UnsupportedOperationException> { secondIterator.remove() }
    }

    private fun raycastIteratorFailure(variant: Variant) {
        val bp = detector(variant)
        val bodies = scene(bp)
        val ray = Ray(Vector2(-2.0, -2.0), Vector2(1.0, 1.0).getNormalized())
        val iterator = bp.raycastIterator(ray, 3.0)
        assertTrue(iterator.hasNext())
        assertSame(bodies.first, iterator.next())
        assertFailsWith<NoSuchElementException> { iterator.next() }
        val secondIterator = bp.raycastIterator(ray, 0.0)
        secondIterator.next()
        assertFailsWith<UnsupportedOperationException> { secondIterator.remove() }
    }

    private fun detectAABBIteratorFailure(variant: Variant) {
        val bp = detector(variant)
        val bodies = scene(bp)
        val query = AABB(0.0, -2.0, 1.0, 1.0)
        val iterator = bp.detectIterator(query)
        assertTrue(iterator.hasNext())
        val result = listOf(iterator.next(), iterator.next())
        assertIdentities(result, bodies.third, bodies.fourth)
        assertSame(bodies.third, result[0])
        assertSame(bodies.fourth, result[1])
        assertFailsWith<NoSuchElementException> { iterator.next() }
        val secondIterator = bp.detectIterator(query)
        secondIterator.next()
        assertFailsWith<UnsupportedOperationException> { secondIterator.remove() }
    }

    private fun detectEmptyIterator(variant: Variant) {
        val bp = detector(variant)
        assertFalse(bp.detectIterator(true).hasNext())
        assertFalse(bp.detectIterator(AABB(0.0, -2.0, 1.0, 1.0)).hasNext())
        assertFalse(bp.raycastIterator(Ray(Vector2(-2.0, -2.0), Vector2(1.0, 1.0)), 3.0).hasNext())
    }

    private fun detect(variant: Variant) {
        val bp = detector(variant)
        val bodies = scene(bp)
        val pairs = bp.detect()
        assertEquals(1, pairs.size)
        assertTrue(pairIs(pairs.single(), bodies.first, bodies.second))
    }

    private fun detectAABB(variant: Variant) {
        val bp = detector(variant)
        val bodies = scene(bp)
        assertIdentities(bp.detect(AABB(0.0, -2.0, 1.0, 1.0)), bodies.third, bodies.fourth)
        assertIdentities(bp.detect(AABB(-0.75, -3.0, 2.0, 1.0)), bodies.second, bodies.third, bodies.fourth)
    }

    private fun detectRay(variant: Variant) {
        val bp = detector(variant)
        val bodies = scene(bp, 1.2)
        assertIdentities(bp.raycast(Ray(Vector2(1.0, 0.0)), 0.0))
        assertIdentities(bp.raycast(Ray(Vector2(-3.0, 0.75), Vector2(1.0, 0.0)), 0.0),
            bodies.first, bodies.second, bodies.fourth)
        assertIdentities(bp.raycast(Ray(Vector2(-3.0, -2.0), Vector2(1.0, 2.0).getNormalized()), 0.0),
            bodies.first, bodies.second)
        assertIdentities(bp.raycast(Ray(Vector2(-2.0, -1.5), Vector2(1.0, 1.0).getNormalized()), 0.4))
        assertIdentities(bp.raycast(Ray(Vector2(-5.0, -3.0), Vector2(-1.0, -2.0).getNormalized()), 0.0))
    }

    private fun shiftCoordinates(variant: Variant) {
        val bp = detector(variant)
        val bodies = scene(bp)
        assertEquals(1, bp.detect().size)
        val stored = bp.getAABB(bodies.first)
        val before = stored.copy()
        bp.shift(Vector2(1.0, -2.0))
        val pairs = bp.detect()
        assertEquals(1, pairs.size)
        assertTrue(pairIs(pairs.single(), bodies.first, bodies.second))
        assertSame(stored, bp.getAABB(bodies.first))
        assertEquals(before.getMinX() + 1.0, bp.getAABB(bodies.first).getMinX(), 1e-12)
        assertEquals(before.getMinY() - 2.0, bp.getAABB(bodies.first).getMinY(), 1e-12)
    }

    private fun getBroadphaseFilter(variant: Variant) {
        assertNotNull(detector(variant).getBroadphaseFilter())
    }

    private fun randomizedTest(variant: Variant) {
        val bp = detector(variant)
        val random = JavaRandom(0L)
        val live = mutableListOf<RectBody>()
        repeat(100) {
            val width = random.nextDouble() + 0.1
            val height = random.nextDouble() + 0.1
            val x = random.nextDouble() * 10.0 - 5.0
            val y = random.nextDouble() * 10.0 - 5.0
            val body = Body(Geometry.createRectangle(width, height)).also { it.translate(x, y) }
            val rect = RectBody(body, x - width / 2, y - height / 2, x + width / 2, y + height / 2)
            live.add(rect); bp.add(body)
            if (random.nextDouble() <= 0.25) {
                val removed = live.removeAt(random.nextInt(live.size))
                assertTrue(bp.remove(removed.body!!))
            }
            val pairs = bp.detect()
            for (i in live.indices) for (j in i + 1 until live.size) {
                if (live[i].overlaps(live[j])) {
                    assertTrue(pairs.any { pairIs(it, live[i].body!!, live[j].body!!) })
                }
            }
            repeat(10) {
                val queryWidth = random.nextDouble() * 9.5 + 0.5
                val queryHeight = random.nextDouble() * 9.5 + 0.5
                val queryX = -5.0 + random.nextDouble() * (10.0 - queryWidth)
                val queryY = -5.0 + random.nextDouble() * (10.0 - queryHeight)
                val query = RectBody(null, queryX, queryY, queryX + queryWidth, queryY + queryHeight)
                val result = bp.detect(AABB(query.minX, query.minY, query.maxX, query.maxY))
                for (rect in live) if (rect.overlaps(query)) assertTrue(result.any { it === rect.body })
            }
            repeat(10) {
                val length = if (random.nextBoolean()) random.nextDouble() * 10.0 else 0.0
                val startX = random.nextDouble() * 10.0 - 5.0
                val startY = random.nextDouble() * 10.0 - 5.0
                val angle = random.nextDouble() * Geometry.TWO_PI
                val ray = Ray(Vector2(startX, startY), angle)
                val direction = ray.getDirectionVector()
                val result = bp.raycast(ray, length)
                for (rect in live) if (rect.hitBy(startX, startY, direction.x, direction.y, length)) {
                    assertTrue(result.any { it === rect.body })
                }
            }
        }
    }

fun addContainsBody_sap_untracked() = addContainsBody(Variant.SAP_UNTRACKED)
fun addContainsBody_sap_tracked() = addContainsBody(Variant.SAP_TRACKED)
fun addContainsBody_tree_untracked() = addContainsBody(Variant.TREE_UNTRACKED)
fun addContainsBody_tree_tracked() = addContainsBody(Variant.TREE_TRACKED)
fun addContainsBody_brute_force() = addContainsBody(Variant.BRUTE_FORCE)

fun clear_sap_untracked() = clear(Variant.SAP_UNTRACKED)
fun clear_sap_tracked() = clear(Variant.SAP_TRACKED)
fun clear_tree_untracked() = clear(Variant.TREE_UNTRACKED)
fun clear_tree_tracked() = clear(Variant.TREE_TRACKED)
fun clear_brute_force() = clear(Variant.BRUTE_FORCE)

fun updateTargeted_sap_untracked() = updateCase(Variant.SAP_UNTRACKED, true)
fun updateTargeted_sap_tracked() = updateCase(Variant.SAP_TRACKED, true)
fun updateTargeted_tree_untracked() = updateCase(Variant.TREE_UNTRACKED, true)
fun updateTargeted_tree_tracked() = updateCase(Variant.TREE_TRACKED, true)
fun updateTargeted_brute_force() = updateCase(Variant.BRUTE_FORCE, true)

fun update_sap_untracked() = updateCase(Variant.SAP_UNTRACKED, false)
fun update_sap_tracked() = updateCase(Variant.SAP_TRACKED, false)
fun update_tree_untracked() = updateCase(Variant.TREE_UNTRACKED, false)
fun update_tree_tracked() = updateCase(Variant.TREE_TRACKED, false)
fun update_brute_force() = updateCase(Variant.BRUTE_FORCE, false)

fun removeContainsBody_sap_untracked() = removeContainsBody(Variant.SAP_UNTRACKED)
fun removeContainsBody_sap_tracked() = removeContainsBody(Variant.SAP_TRACKED)
fun removeContainsBody_tree_untracked() = removeContainsBody(Variant.TREE_UNTRACKED)
fun removeContainsBody_tree_tracked() = removeContainsBody(Variant.TREE_TRACKED)
fun removeContainsBody_brute_force() = removeContainsBody(Variant.BRUTE_FORCE)

fun getAABB_sap_untracked() = getAABB(Variant.SAP_UNTRACKED)
fun getAABB_sap_tracked() = getAABB(Variant.SAP_TRACKED)
fun getAABB_tree_untracked() = getAABB(Variant.TREE_UNTRACKED)
fun getAABB_tree_tracked() = getAABB(Variant.TREE_TRACKED)
fun getAABB_brute_force() = getAABB(Variant.BRUTE_FORCE)

fun getAABBExpansionMethod_sap_untracked() = getAABBExpansionMethod(Variant.SAP_UNTRACKED)
fun getAABBExpansionMethod_sap_tracked() = getAABBExpansionMethod(Variant.SAP_TRACKED)
fun getAABBExpansionMethod_tree_untracked() = getAABBExpansionMethod(Variant.TREE_UNTRACKED)
fun getAABBExpansionMethod_tree_tracked() = getAABBExpansionMethod(Variant.TREE_TRACKED)
fun getAABBExpansionMethod_brute_force() = getAABBExpansionMethod(Variant.BRUTE_FORCE)

fun updateSmall_sap_untracked() = updateSmall(Variant.SAP_UNTRACKED)
fun updateSmall_sap_tracked() = updateSmall(Variant.SAP_TRACKED)
fun updateSmall_tree_untracked() = updateSmall(Variant.TREE_UNTRACKED)
fun updateSmall_tree_tracked() = updateSmall(Variant.TREE_TRACKED)
fun updateSmall_brute_force() = updateSmall(Variant.BRUTE_FORCE)

fun updateLarge_sap_untracked() = updateLarge(Variant.SAP_UNTRACKED)
fun updateLarge_sap_tracked() = updateLarge(Variant.SAP_TRACKED)
fun updateLarge_tree_untracked() = updateLarge(Variant.TREE_UNTRACKED)
fun updateLarge_tree_tracked() = updateLarge(Variant.TREE_TRACKED)
fun updateLarge_brute_force() = updateLarge(Variant.BRUTE_FORCE)

fun getSetUpdateTrackingEnabled_sap_untracked() = getSetUpdateTrackingEnabled(Variant.SAP_UNTRACKED)
fun getSetUpdateTrackingEnabled_sap_tracked() = getSetUpdateTrackingEnabled(Variant.SAP_TRACKED)
fun getSetUpdateTrackingEnabled_tree_untracked() = getSetUpdateTrackingEnabled(Variant.TREE_UNTRACKED)
fun getSetUpdateTrackingEnabled_tree_tracked() = getSetUpdateTrackingEnabled(Variant.TREE_TRACKED)
fun getSetUpdateTrackingEnabled_brute_force() = getSetUpdateTrackingEnabled(Variant.BRUTE_FORCE)

fun isUpdateTrackingSupported_sap_untracked() = isUpdateTrackingSupported(Variant.SAP_UNTRACKED)
fun isUpdateTrackingSupported_sap_tracked() = isUpdateTrackingSupported(Variant.SAP_TRACKED)
fun isUpdateTrackingSupported_tree_untracked() = isUpdateTrackingSupported(Variant.TREE_UNTRACKED)
fun isUpdateTrackingSupported_tree_tracked() = isUpdateTrackingSupported(Variant.TREE_TRACKED)
fun isUpdateTrackingSupported_brute_force() = isUpdateTrackingSupported(Variant.BRUTE_FORCE)

fun optimize_sap_untracked() = optimize(Variant.SAP_UNTRACKED)
fun optimize_sap_tracked() = optimize(Variant.SAP_TRACKED)
fun optimize_tree_untracked() = optimize(Variant.TREE_UNTRACKED)
fun optimize_tree_tracked() = optimize(Variant.TREE_TRACKED)
fun optimize_brute_force() = optimize(Variant.BRUTE_FORCE)

fun setUpdated_sap_untracked() = setUpdated(Variant.SAP_UNTRACKED)
fun setUpdated_sap_tracked() = setUpdated(Variant.SAP_TRACKED)
fun setUpdated_tree_untracked() = setUpdated(Variant.TREE_UNTRACKED)
fun setUpdated_tree_tracked() = setUpdated(Variant.TREE_TRACKED)
fun setUpdated_brute_force() = setUpdated(Variant.BRUTE_FORCE)

fun size_sap_untracked() = size(Variant.SAP_UNTRACKED)
fun size_sap_tracked() = size(Variant.SAP_TRACKED)
fun size_tree_untracked() = size(Variant.TREE_UNTRACKED)
fun size_tree_tracked() = size(Variant.TREE_TRACKED)
fun size_brute_force() = size(Variant.BRUTE_FORCE)

fun detectConvexAndTransform_sap_untracked() = detectConvexAndTransform(Variant.SAP_UNTRACKED)
fun detectConvexAndTransform_sap_tracked() = detectConvexAndTransform(Variant.SAP_TRACKED)
fun detectConvexAndTransform_tree_untracked() = detectConvexAndTransform(Variant.TREE_UNTRACKED)
fun detectConvexAndTransform_tree_tracked() = detectConvexAndTransform(Variant.TREE_TRACKED)
fun detectConvexAndTransform_brute_force() = detectConvexAndTransform(Variant.BRUTE_FORCE)

fun detectIteratorFailure_sap_untracked() = detectIteratorFailure(Variant.SAP_UNTRACKED)
fun detectIteratorFailure_sap_tracked() = detectIteratorFailure(Variant.SAP_TRACKED)
fun detectIteratorFailure_tree_untracked() = detectIteratorFailure(Variant.TREE_UNTRACKED)
fun detectIteratorFailure_tree_tracked() = detectIteratorFailure(Variant.TREE_TRACKED)
fun detectIteratorFailure_brute_force() = detectIteratorFailure(Variant.BRUTE_FORCE)

fun raycastIteratorFailure_sap_untracked() = raycastIteratorFailure(Variant.SAP_UNTRACKED)
fun raycastIteratorFailure_sap_tracked() = raycastIteratorFailure(Variant.SAP_TRACKED)
fun raycastIteratorFailure_tree_untracked() = raycastIteratorFailure(Variant.TREE_UNTRACKED)
fun raycastIteratorFailure_tree_tracked() = raycastIteratorFailure(Variant.TREE_TRACKED)
fun raycastIteratorFailure_brute_force() = raycastIteratorFailure(Variant.BRUTE_FORCE)

fun detectAABBIteratorFailure_sap_untracked() = detectAABBIteratorFailure(Variant.SAP_UNTRACKED)
fun detectAABBIteratorFailure_sap_tracked() = detectAABBIteratorFailure(Variant.SAP_TRACKED)
fun detectAABBIteratorFailure_tree_untracked() = detectAABBIteratorFailure(Variant.TREE_UNTRACKED)
fun detectAABBIteratorFailure_tree_tracked() = detectAABBIteratorFailure(Variant.TREE_TRACKED)
fun detectAABBIteratorFailure_brute_force() = detectAABBIteratorFailure(Variant.BRUTE_FORCE)

fun detectEmptyIterator_sap_untracked() = detectEmptyIterator(Variant.SAP_UNTRACKED)
fun detectEmptyIterator_sap_tracked() = detectEmptyIterator(Variant.SAP_TRACKED)
fun detectEmptyIterator_tree_untracked() = detectEmptyIterator(Variant.TREE_UNTRACKED)
fun detectEmptyIterator_tree_tracked() = detectEmptyIterator(Variant.TREE_TRACKED)
fun detectEmptyIterator_brute_force() = detectEmptyIterator(Variant.BRUTE_FORCE)

fun detect_sap_untracked() = detect(Variant.SAP_UNTRACKED)
fun detect_sap_tracked() = detect(Variant.SAP_TRACKED)
fun detect_tree_untracked() = detect(Variant.TREE_UNTRACKED)
fun detect_tree_tracked() = detect(Variant.TREE_TRACKED)
fun detect_brute_force() = detect(Variant.BRUTE_FORCE)

fun detectAABB_sap_untracked() = detectAABB(Variant.SAP_UNTRACKED)
fun detectAABB_sap_tracked() = detectAABB(Variant.SAP_TRACKED)
fun detectAABB_tree_untracked() = detectAABB(Variant.TREE_UNTRACKED)
fun detectAABB_tree_tracked() = detectAABB(Variant.TREE_TRACKED)
fun detectAABB_brute_force() = detectAABB(Variant.BRUTE_FORCE)

fun detectRay_sap_untracked() = detectRay(Variant.SAP_UNTRACKED)
fun detectRay_sap_tracked() = detectRay(Variant.SAP_TRACKED)
fun detectRay_tree_untracked() = detectRay(Variant.TREE_UNTRACKED)
fun detectRay_tree_tracked() = detectRay(Variant.TREE_TRACKED)
fun detectRay_brute_force() = detectRay(Variant.BRUTE_FORCE)

fun shiftCoordinates_sap_untracked() = shiftCoordinates(Variant.SAP_UNTRACKED)
fun shiftCoordinates_sap_tracked() = shiftCoordinates(Variant.SAP_TRACKED)
fun shiftCoordinates_tree_untracked() = shiftCoordinates(Variant.TREE_UNTRACKED)
fun shiftCoordinates_tree_tracked() = shiftCoordinates(Variant.TREE_TRACKED)
fun shiftCoordinates_brute_force() = shiftCoordinates(Variant.BRUTE_FORCE)

fun getBroadphaseFilter_sap_untracked() = getBroadphaseFilter(Variant.SAP_UNTRACKED)
fun getBroadphaseFilter_sap_tracked() = getBroadphaseFilter(Variant.SAP_TRACKED)
fun getBroadphaseFilter_tree_untracked() = getBroadphaseFilter(Variant.TREE_UNTRACKED)
fun getBroadphaseFilter_tree_tracked() = getBroadphaseFilter(Variant.TREE_TRACKED)
fun getBroadphaseFilter_brute_force() = getBroadphaseFilter(Variant.BRUTE_FORCE)

fun randomizedTest_sap_untracked() = randomizedTest(Variant.SAP_UNTRACKED)
fun randomizedTest_sap_tracked() = randomizedTest(Variant.SAP_TRACKED)
fun randomizedTest_tree_untracked() = randomizedTest(Variant.TREE_UNTRACKED)
fun randomizedTest_tree_tracked() = randomizedTest(Variant.TREE_TRACKED)
fun randomizedTest_brute_force() = randomizedTest(Variant.BRUTE_FORCE)

    private data class RectBody(val body: Body?, val minX: Double, val minY: Double, val maxX: Double, val maxY: Double) {
        fun overlaps(other: RectBody) = minX <= other.maxX && maxX >= other.minX &&
            minY <= other.maxY && maxY >= other.minY
        fun hitBy(x: Double, y: Double, dx: Double, dy: Double, length: Double): Boolean {
            var entry = 0.0
            var exit = if (length <= 0.0) Double.POSITIVE_INFINITY else length
            for ((origin, direction, low, high) in listOf(listOf(x, dx, minX, maxX), listOf(y, dy, minY, maxY))) {
                if (direction == 0.0) {
                    if (origin < low || origin > high) return false
                } else {
                    entry = max(entry, min((low - origin) / direction, (high - origin) / direction))
                    exit = min(exit, max((low - origin) / direction, (high - origin) / direction))
                    if (entry > exit) return false
                }
            }
            return true
        }
    }

    private class JavaRandom(seed: Long) {
        private var state = (seed xor 0x5DEECE66DL) and ((1L shl 48) - 1)
        private fun bits(count: Int): Int {
            state = (state * 0x5DEECE66DL + 11L) and ((1L shl 48) - 1)
            return (state ushr (48 - count)).toInt()
        }
        fun nextDouble() = ((bits(26).toLong() shl 27) + bits(27)) / 9007199254740992.0
        fun nextBoolean() = bits(1) != 0
        fun nextInt(bound: Int): Int {
            if ((bound and -bound) == bound) return ((bound.toLong() * bits(31)) shr 31).toInt()
            while (true) {
                val value = bits(31)
                val result = value % bound
                if (value - result + (bound - 1) >= 0) return result
            }
        }
    }
}
