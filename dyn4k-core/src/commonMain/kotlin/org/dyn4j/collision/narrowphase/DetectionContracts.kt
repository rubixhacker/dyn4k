/*
 * Copyright (c) 2010-2024 William Bittle  http://www.dyn4j.org/
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
package org.dyn4j.collision.narrowphase

import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Ray
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2

interface NarrowphaseDetector {
    fun detect(convex1: Convex, transform1: Transform, convex2: Convex, transform2: Transform, penetration: Penetration): Boolean
    fun detect(convex1: Convex, transform1: Transform, convex2: Convex, transform2: Transform): Boolean
}

interface DistanceDetector {
    fun distance(convex1: Convex, transform1: Transform, convex2: Convex, transform2: Transform, separation: Separation): Boolean
}

interface RaycastDetector {
    fun raycast(ray: Ray, maxLength: Double, convex: Convex, transform: Transform, raycast: Raycast): Boolean
}

interface ContainmentDetector {
    fun contains(convex1: Convex, transform1: Transform, convex2: Convex, transform2: Transform, containment: Containment): Boolean
}

interface MinkowskiPenetrationSolver {
    fun getPenetration(simplex: List<@kotlin.jvm.JvmSuppressWildcards Vector2>, minkowskiSum: MinkowskiSum, penetration: Penetration)
}

interface NarrowphasePostProcessor {
    fun process(convex1: Convex, transform1: Transform, convex2: Convex, transform2: Transform, penetration: Penetration)
}

open class MinkowskiSum(
    private val convex1: Convex,
    private val transform1: Transform,
    private val convex2: Convex,
    private val transform2: Transform
) {
    fun getSupportPoint(direction: Vector2): Vector2 {
        val point1 = convex1.getFarthestPoint(direction, transform1)
        direction.negate()
        val point2 = convex2.getFarthestPoint(direction, transform2)
        direction.negate()
        return point1.subtract(point2)
    }

    fun getSupportPoints(direction: Vector2): MinkowskiSumPoint {
        val point1 = convex1.getFarthestPoint(direction, transform1)
        direction.negate()
        val point2 = convex2.getFarthestPoint(direction, transform2)
        direction.negate()
        return MinkowskiSumPoint(point1, point2)
    }

    open fun getConvex1() = convex1
    open fun getConvex2() = convex2
    open fun getTransform1() = transform1
    open fun getTransform2() = transform2
    override fun toString() = "MinkowskiSum[Convex1=${convex1.hashCode()}|Transform1=$transform1|Convex2=${convex2.hashCode()}|Transform2=$transform2]"
}

open class MinkowskiSumPoint(supportPoint1: Vector2, supportPoint2: Vector2) {
    @get:kotlin.jvm.JvmName("supportPoint1-dyn4k")
    internal val supportPoint1: Vector2 = supportPoint1
    @get:kotlin.jvm.JvmName("supportPoint2-dyn4k")
    internal val supportPoint2: Vector2 = supportPoint2
    @get:kotlin.jvm.JvmName("point-dyn4k")
    internal val point: Vector2 = supportPoint1.difference(supportPoint2)
    open fun getSupportPoint1() = supportPoint1
    open fun getSupportPoint2() = supportPoint2
    open fun getPoint() = point
    override fun toString() = "MinkowskiSum.Point[Point=$point|SupportPoint1=$supportPoint1|SupportPoint2=$supportPoint2]"
}
