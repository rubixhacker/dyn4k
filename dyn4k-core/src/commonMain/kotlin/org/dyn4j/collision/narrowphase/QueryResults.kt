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

import org.dyn4j.Copyable
import org.dyn4j.JvmFieldBridge
import org.dyn4j.geometry.Shiftable
import org.dyn4j.geometry.Vector2

open class Penetration : Shiftable, Copyable<Penetration> {
    @get:kotlin.jvm.JvmName("normalField")
    @JvmFieldBridge protected val normal: Vector2
    @get:kotlin.jvm.JvmName("depthField")
    @set:kotlin.jvm.JvmName("setDepthField")
    @JvmFieldBridge protected var depth: Double = 0.0

    constructor() { normal = Vector2() }
    protected constructor(normal: Vector2, depth: Double) { this.normal = normal.copy(); this.depth = depth }
    protected constructor(other: Penetration) { normal = other.normal.copy(); depth = other.depth }

    open fun clear() { normal.zero(); depth = 0.0 }
    open fun getNormal(): Vector2 = normal
    open fun getDepth(): Double = depth
    open fun setNormal(normal: Vector2) { this.normal.x = normal.x; this.normal.y = normal.y }
    open fun setDepth(depth: Double) { this.depth = depth }
    @Deprecated("Use set")
    open fun copy(other: Penetration) = set(other)
    open fun set(other: Penetration) { depth = other.depth; normal.x = other.normal.x; normal.y = other.normal.y }
    override fun shift(shift: Vector2) {}
    override fun copy(): Penetration = Penetration(this)
    override fun toString() = "Penetration[Normal=$normal|Depth=$depth]"
    internal fun setDirect(x: Double, y: Double, depth: Double) {
        normal.x = x; normal.y = y; this.depth = depth
    }
}

open class Separation : Shiftable, Copyable<Separation> {
    @get:kotlin.jvm.JvmName("normalField")
    @JvmFieldBridge protected val normal: Vector2
    @get:kotlin.jvm.JvmName("distanceField")
    @set:kotlin.jvm.JvmName("setDistanceField")
    @JvmFieldBridge protected var distance: Double = 0.0
    @get:kotlin.jvm.JvmName("point1Field")
    @JvmFieldBridge protected val point1: Vector2
    @get:kotlin.jvm.JvmName("point2Field")
    @JvmFieldBridge protected val point2: Vector2

    constructor() { normal = Vector2(); point1 = Vector2(); point2 = Vector2() }
    protected constructor(normal: Vector2, distance: Double, point1: Vector2, point2: Vector2) {
        this.normal = normal.copy(); this.distance = distance; this.point1 = point1.copy(); this.point2 = point2.copy()
    }
    protected constructor(other: Separation) {
        normal = other.normal.copy(); distance = other.distance; point1 = other.point1.copy(); point2 = other.point2.copy()
    }

    open fun clear() { normal.zero(); distance = 0.0; point1.zero(); point2.zero() }
    open fun getNormal(): Vector2 = normal
    open fun getDistance(): Double = distance
    open fun getPoint1(): Vector2 = point1
    open fun getPoint2(): Vector2 = point2
    open fun setNormal(value: Vector2) { normal.x = value.x; normal.y = value.y }
    open fun setDistance(value: Double) { distance = value }
    open fun setPoint1(value: Vector2) { point1.x = value.x; point1.y = value.y }
    open fun setPoint2(value: Vector2) { point2.x = value.x; point2.y = value.y }
    @Deprecated("Use set")
    open fun copy(other: Separation) = set(other)
    open fun set(other: Separation) {
        distance = other.distance
        normal.x = other.normal.x; normal.y = other.normal.y
        point1.x = other.point1.x; point1.y = other.point1.y
        point2.x = other.point2.x; point2.y = other.point2.y
    }
    override fun shift(shift: Vector2) {
        point1.x += shift.x; point1.y += shift.y
        point2.x += shift.x; point2.y += shift.y
    }
    override fun copy(): Separation = Separation(this)
    override fun toString() = "Separation[Point1=$point1|Point2=$point2|Normal=$normal|Distance=$distance]"
    internal fun setDirect(normalX: Double, normalY: Double, distance: Double, p1x: Double, p1y: Double, p2x: Double, p2y: Double) {
        normal.x = normalX; normal.y = normalY; this.distance = distance
        point1.x = p1x; point1.y = p1y; point2.x = p2x; point2.y = p2y
    }
}

open class Raycast : Shiftable, Copyable<Raycast> {
    @get:kotlin.jvm.JvmName("pointField")
    @JvmFieldBridge protected val point: Vector2
    @get:kotlin.jvm.JvmName("normalField")
    @JvmFieldBridge protected val normal: Vector2
    @get:kotlin.jvm.JvmName("distanceField")
    @set:kotlin.jvm.JvmName("setDistanceField")
    @JvmFieldBridge protected var distance: Double = 0.0

    constructor() { point = Vector2(); normal = Vector2() }
    protected constructor(point: Vector2, normal: Vector2, distance: Double) {
        this.point = point.copy(); this.normal = normal.copy(); this.distance = distance
    }
    protected constructor(other: Raycast) { point = other.point.copy(); normal = other.normal.copy(); distance = other.distance }

    open fun clear() { point.zero(); normal.zero(); distance = 0.0 }
    open fun getPoint(): Vector2 = point
    open fun setPoint(value: Vector2) { point.x = value.x; point.y = value.y }
    open fun getNormal(): Vector2 = normal
    open fun setNormal(value: Vector2) { normal.x = value.x; normal.y = value.y }
    open fun getDistance(): Double = distance
    open fun setDistance(value: Double) { distance = value }
    @Deprecated("Use set")
    open fun copy(other: Raycast) = set(other)
    open fun set(other: Raycast) {
        distance = other.distance
        normal.x = other.normal.x; normal.y = other.normal.y
        point.x = other.point.x; point.y = other.point.y
    }
    override fun shift(shift: Vector2) { point.x += shift.x; point.y += shift.y }
    override fun copy(): Raycast = Raycast(this)
    override fun toString() = "Raycast[Point=$point|Normal=$normal|Distance=$distance]"
    internal fun setDirect(pointX: Double, pointY: Double, normalX: Double, normalY: Double, distance: Double) {
        point.x = pointX; point.y = pointY; normal.x = normalX; normal.y = normalY; this.distance = distance
    }
}

open class Containment : Copyable<Containment> {
    @get:kotlin.jvm.JvmName("aContainedInBField")
    @set:kotlin.jvm.JvmName("setAContainedInBField")
    @JvmFieldBridge protected var aContainedInB: Boolean = false
    @get:kotlin.jvm.JvmName("bContainedInAField")
    @set:kotlin.jvm.JvmName("setBContainedInAField")
    @JvmFieldBridge protected var bContainedInA: Boolean = false

    constructor()
    protected constructor(a: Boolean, b: Boolean) { aContainedInB = a; bContainedInA = b }
    protected constructor(other: Containment) { aContainedInB = other.aContainedInB; bContainedInA = other.bContainedInA }

    open fun clear() { aContainedInB = false; bContainedInA = false }
    @Deprecated("Use set")
    open fun copy(other: Containment) = set(other)
    open fun set(other: Containment) { aContainedInB = other.aContainedInB; bContainedInA = other.bContainedInA }
    override fun copy(): Containment = Containment(this)
    open fun isAContainedInB(): Boolean = aContainedInB
    open fun setAContainedInB(flag: Boolean) { aContainedInB = flag }
    open fun isBContainedInA(): Boolean = bContainedInA
    open fun setBContainedInA(flag: Boolean) { bContainedInA = flag }
    override fun toString() = "Containment[IsAContainedInB=$aContainedInB|IsBContainedInA=$bContainedInA]"
}
