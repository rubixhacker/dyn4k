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
package org.dyn4j.world

import org.dyn4j.DataContainer
import org.dyn4j.collision.Bounds
import org.dyn4j.collision.CollisionBody
import org.dyn4j.collision.Fixture
import org.dyn4j.collision.broadphase.CollisionItemBroadphaseDetector
import org.dyn4j.collision.continuous.TimeOfImpactDetector
import org.dyn4j.collision.manifold.ManifoldSolver
import org.dyn4j.collision.narrowphase.NarrowphaseDetector
import org.dyn4j.collision.narrowphase.NarrowphasePostProcessor
import org.dyn4j.collision.narrowphase.RaycastDetector
import org.dyn4j.geometry.AABB
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Ray
import org.dyn4j.geometry.Shiftable
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2
import org.dyn4j.world.listener.BoundsListener
import org.dyn4j.world.listener.CollisionListener
import org.dyn4j.world.result.ConvexCastResult
import org.dyn4j.world.result.ConvexDetectResult
import org.dyn4j.world.result.DetectResult
import org.dyn4j.world.result.RaycastResult

interface CollisionWorld<T : CollisionBody<E>, E : Fixture, V : CollisionData<T, E>> : Shiftable, DataContainer {
    companion object {
        const val DEFAULT_INITIAL_BODY_CAPACITY = 64
    }

    fun addBody(body: T?)
    fun containsBody(body: T?): Boolean
    fun removeBody(index: Int): Boolean
    fun removeBody(body: T?): Boolean
    fun removeAllBodies()
    fun getBodyCount(): Int
    fun getBody(index: Int): T
    fun getBodies(): List<T>
    fun getBodyIterator(): MutableIterator<T>
    fun isEmpty(): Boolean

    fun setBounds(bounds: Bounds?)
    fun getBounds(): Bounds?
    fun getCollisionListeners(): List<CollisionListener<T, E>>
    fun getBoundsListeners(): List<BoundsListener<T, E>>
    fun removeAllListeners()
    fun removeAllCollisionListeners()
    fun removeAllBoundsListeners()
    fun removeCollisionListener(listener: CollisionListener<T, E>?): Boolean
    fun removeBoundsListener(listener: BoundsListener<T, E>?): Boolean
    fun addCollisionListener(listener: CollisionListener<T, E>?): Boolean
    fun addBoundsListener(listener: BoundsListener<T, E>?): Boolean

    fun setBroadphaseDetector(broadphaseDetector: CollisionItemBroadphaseDetector<T, E>?)
    fun getBroadphaseDetector(): CollisionItemBroadphaseDetector<T, E>
    fun setBroadphaseCollisionDataFilter(filter: BroadphaseCollisionDataFilter<T, E>?)
    fun getBroadphaseCollisionDataFilter(): BroadphaseCollisionDataFilter<T, E>
    fun setNarrowphaseDetector(narrowphaseDetector: NarrowphaseDetector?)
    fun getNarrowphaseDetector(): NarrowphaseDetector
    fun setNarrowphasePostProcessor(narrowphasePostProcessor: NarrowphasePostProcessor?)
    fun getNarrowphasePostProcessor(): NarrowphasePostProcessor
    fun setManifoldSolver(manifoldSolver: ManifoldSolver?)
    fun getManifoldSolver(): ManifoldSolver
    fun setRaycastDetector(raycastDetector: RaycastDetector?)
    fun getRaycastDetector(): RaycastDetector
    fun setTimeOfImpactDetector(timeOfImpactDetector: TimeOfImpactDetector?)
    fun getTimeOfImpactDetector(): TimeOfImpactDetector

    fun getCollisionData(body1: T?, fixture1: E?, body2: T?, fixture2: E?): V?
    fun getCollisionDataIterator(): MutableIterator<V>

    fun detect(aabb: AABB?, filter: DetectFilter<T, E>?): List<DetectResult<T, E>>
    fun detectIterator(aabb: AABB?, filter: DetectFilter<T, E>?): MutableIterator<DetectResult<T, E>>
    fun detect(aabb: AABB?, body: T?, filter: DetectFilter<T, E>?): List<DetectResult<T, E>>
    fun detectIterator(aabb: AABB?, body: T?, filter: DetectFilter<T, E>?): MutableIterator<DetectResult<T, E>>
    fun detect(convex: Convex?, transform: Transform?, filter: DetectFilter<T, E>?): List<ConvexDetectResult<T, E>>
    fun detectIterator(convex: Convex?, transform: Transform?, filter: DetectFilter<T, E>?): MutableIterator<ConvexDetectResult<T, E>>
    fun detect(convex: Convex?, transform: Transform?, body: T?, filter: DetectFilter<T, E>?): List<ConvexDetectResult<T, E>>
    fun detectIterator(convex: Convex?, transform: Transform?, body: T?, filter: DetectFilter<T, E>?): MutableIterator<ConvexDetectResult<T, E>>

    fun raycast(ray: Ray?, maxLength: Double, filter: DetectFilter<T, E>?): List<RaycastResult<T, E>>
    fun raycastIterator(ray: Ray?, maxLength: Double, filter: DetectFilter<T, E>?): MutableIterator<RaycastResult<T, E>>
    fun raycast(ray: Ray?, maxLength: Double, body: T?, filter: DetectFilter<T, E>?): List<RaycastResult<T, E>>
    fun raycastIterator(ray: Ray?, maxLength: Double, body: T?, filter: DetectFilter<T, E>?): MutableIterator<RaycastResult<T, E>>
    fun raycastClosest(ray: Ray?, maxLength: Double, filter: DetectFilter<T, E>?): RaycastResult<T, E>?
    fun raycastClosest(ray: Ray?, maxLength: Double, body: T?, filter: DetectFilter<T, E>?): RaycastResult<T, E>?

    fun convexCast(convex: Convex?, transform: Transform?, deltaPosition: Vector2?, deltaAngle: Double, filter: DetectFilter<T, E>?): List<ConvexCastResult<T, E>>
    fun convexCastIterator(convex: Convex?, transform: Transform?, deltaPosition: Vector2?, deltaAngle: Double, filter: DetectFilter<T, E>?): MutableIterator<ConvexCastResult<T, E>>
    fun convexCastClosest(convex: Convex?, transform: Transform?, deltaPosition: Vector2?, deltaAngle: Double, filter: DetectFilter<T, E>?): ConvexCastResult<T, E>?
    fun convexCastClosest(convex: Convex?, transform: Transform?, deltaPosition: Vector2?, deltaAngle: Double, body: T?, filter: DetectFilter<T, E>?): ConvexCastResult<T, E>?
}
