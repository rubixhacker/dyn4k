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
package org.dyn4j.collision.continuous

import kotlin.math.abs
import kotlin.math.pow
import org.dyn4j.Copyable
import org.dyn4j.Epsilon
import org.dyn4j.JvmFieldBridge
import org.dyn4j.collision.narrowphase.DistanceDetector
import org.dyn4j.collision.narrowphase.Gjk
import org.dyn4j.collision.narrowphase.Separation
import org.dyn4j.exception.ArgumentNullException
import org.dyn4j.exception.ValueOutOfRangeException
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2

open class TimeOfImpact : Copyable<TimeOfImpact> {
    @get:kotlin.jvm.JvmName("timeField")
    @set:kotlin.jvm.JvmName("setTimeField")
    @JvmFieldBridge protected var time: Double = 0.0
    @get:kotlin.jvm.JvmName("separationField")
    @JvmFieldBridge protected val separation: Separation

    constructor() { separation = Separation() }
    protected constructor(time: Double, separation: Separation) {
        this.time = time; this.separation = separation.copy()
    }
    open fun getTime() = time
    open fun setTime(value: Double) { time = value }
    open fun getSeparation() = separation
    open fun setSeparation(value: Separation) { separation.set(value) }
    @Deprecated("Use set")
    open fun copy(other: TimeOfImpact) = set(other)
    open fun set(other: TimeOfImpact) { time = other.time; separation.set(other.separation) }
    override fun copy(): TimeOfImpact = TimeOfImpact(time, separation)
    override fun toString() = "TimeOfImpact[Time=$time|Separation=$separation]"
    internal fun setDirect(time: Double, separation: Separation) {
        this.time = time
        this.separation.set(separation)
    }
}

interface TimeOfImpactDetector {
    fun getTimeOfImpact(
        convex1: Convex, transform1: Transform, dp1: Vector2, da1: Double,
        convex2: Convex, transform2: Transform, dp2: Vector2, da2: Double,
        toi: TimeOfImpact
    ): Boolean
    fun getTimeOfImpact(
        convex1: Convex, transform1: Transform, dp1: Vector2, da1: Double,
        convex2: Convex, transform2: Transform, dp2: Vector2, da2: Double,
        t1: Double, t2: Double, toi: TimeOfImpact
    ): Boolean
}

open class ConservativeAdvancement : TimeOfImpactDetector {
    @get:kotlin.jvm.JvmName("distanceDetectorField")
    @set:kotlin.jvm.JvmName("setDistanceDetectorField")
    @JvmFieldBridge protected var distanceDetector: DistanceDetector = Gjk()
    @get:kotlin.jvm.JvmName("distanceEpsilonField")
    @set:kotlin.jvm.JvmName("setDistanceEpsilonField")
    @JvmFieldBridge protected var distanceEpsilon = DEFAULT_DISTANCE_EPSILON
    @get:kotlin.jvm.JvmName("maxIterationsField")
    @set:kotlin.jvm.JvmName("setMaxIterationsField")
    @JvmFieldBridge protected var maxIterations = DEFAULT_MAX_ITERATIONS

    constructor()
    constructor(distanceDetector: DistanceDetector?) {
        this.distanceDetector = distanceDetector ?: throw ArgumentNullException("distanceDetector")
    }

    override fun getTimeOfImpact(
        convex1: Convex, transform1: Transform, dp1: Vector2, da1: Double,
        convex2: Convex, transform2: Transform, dp2: Vector2, da2: Double, toi: TimeOfImpact
    ): Boolean = getTimeOfImpact(convex1, transform1, dp1, da1, convex2, transform2, dp2, da2, 0.0, 1.0, toi)

    override fun getTimeOfImpact(
        convex1: Convex, transform1: Transform, dp1: Vector2, da1: Double,
        convex2: Convex, transform2: Transform, dp2: Vector2, da2: Double,
        t1: Double, t2: Double, toi: TimeOfImpact
    ): Boolean {
        var iterations = 0
        val lerpTx1 = Transform()
        val lerpTx2 = Transform()
        val separation = Separation()
        var separated = distanceDetector.distance(convex1, transform1, convex2, transform2, separation)
        if (!separated) return false
        var distance = separation.getDistance()
        if (distance < distanceEpsilon) return false
        var normal = separation.getNormal()
        val rmax1 = convex1.getRadius()
        val rmax2 = convex2.getRadius()
        val relativeVelocity = dp1.difference(dp2)
        val relativeSpeed = relativeVelocity.getMagnitude()
        val angularMaximum = rmax1 * abs(da1) + rmax2 * abs(da2)
        if (relativeSpeed + angularMaximum == 0.0) return false
        var lambda = t1
        var lastLambda = lambda
        while (distance > distanceEpsilon && iterations < maxIterations) {
            val relativeDistance = relativeVelocity.dot(normal) + angularMaximum
            if (relativeDistance <= Epsilon.E) return false
            val step = distance / relativeDistance
            lambda += step
            if (lambda < t1 || lambda > t2) return false
            if (lambda <= lastLambda) break
            lastLambda = lambda
            iterations++
            transform1.lerp(dp1, da1, lambda, lerpTx1)
            transform2.lerp(dp2, da2, lambda, lerpTx2)
            separation.clear()
            separated = distanceDetector.distance(convex1, lerpTx1, convex2, lerpTx2, separation)
            if (!separated) break
            normal = separation.getNormal()
            distance = separation.getDistance()
        }
        toi.setDirect(lambda, separation)
        return true
    }

    open fun getDistanceDetector() = distanceDetector
    open fun setDistanceDetector(value: DistanceDetector?) {
        distanceDetector = value ?: throw ArgumentNullException("distanceDetector")
    }
    open fun getDistanceEpsilon() = distanceEpsilon
    open fun setDistanceEpsilon(value: Double) {
        if (value <= 0.0) throw ValueOutOfRangeException("distanceEpsilon", value, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
        distanceEpsilon = value
    }
    open fun getMaxIterations() = maxIterations
    open fun setMaxIterations(value: Int) {
        if (value < 5) throw ValueOutOfRangeException("maxIterations", value, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 5)
        maxIterations = value
    }
    companion object {
        @kotlin.jvm.JvmField val DEFAULT_DISTANCE_EPSILON = Epsilon.E.pow(1.0 / 3.0)
        const val DEFAULT_MAX_ITERATIONS = 30
    }
}
