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
package org.dyn4j.geometry

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import org.dyn4j.Copyable
import org.dyn4j.exception.ValueOutOfRangeException

open class AABB : Translatable, Copyable<AABB> {
    @kotlin.jvm.JvmField protected var minX: Double
    @kotlin.jvm.JvmField protected var minY: Double
    @kotlin.jvm.JvmField protected var maxX: Double
    @kotlin.jvm.JvmField protected var maxY: Double

    constructor(minX: Double, minY: Double, maxX: Double, maxY: Double) {
        if (minX > maxX) throw ValueOutOfRangeException("minX", minX, ValueOutOfRangeException.MUST_BE_LESS_THAN_OR_EQUAL_TO, "maxX", maxX)
        if (minY > maxY) throw ValueOutOfRangeException("minY", minY, ValueOutOfRangeException.MUST_BE_LESS_THAN_OR_EQUAL_TO, "maxY", maxY)
        this.minX = minX
        this.minY = minY
        this.maxX = maxX
        this.maxY = maxY
    }

    constructor(min: Vector2, max: Vector2) : this(min.x, min.y, max.x, max.y)
    constructor(radius: Double) : this(null, radius)
    constructor(center: Vector2?, radius: Double) : this(
        (center?.x ?: 0.0) - checkedRadius(radius),
        (center?.y ?: 0.0) - radius,
        (center?.x ?: 0.0) + radius,
        (center?.y ?: 0.0) + radius
    )
    constructor(aabb: AABB) : this(aabb.minX, aabb.minY, aabb.maxX, aabb.maxY)

    override fun copy() = AABB(this)

    open fun zero() {
        minX = 0.0
        minY = 0.0
        maxX = 0.0
        maxY = 0.0
    }

    open fun set(aabb: AABB): AABB {
        minX = aabb.minX
        minY = aabb.minY
        maxX = aabb.maxX
        maxY = aabb.maxY
        return this
    }

    override fun toString() = "AABB[Min=($minX, $minY)|Max=($maxX, $maxY)]"
    override fun equals(other: Any?): Boolean = other is AABB &&
        maxX == other.maxX && minX == other.minX && maxY == other.maxY && minY == other.minY

    override fun hashCode(): Int {
        var result = 1
        for (value in doubleArrayOf(maxX, maxY, minX, minY)) {
            val bits = value.toBits()
            result = 31 * result + (bits xor (bits ushr 32)).toInt()
        }
        return result
    }

    override fun translate(x: Double, y: Double) {
        minX += x
        minY += y
        maxX += x
        maxY += y
    }

    override fun translate(vector: Vector2) = translate(vector.x, vector.y)
    open fun getTranslated(vector: Vector2) = AABB(minX + vector.x, minY + vector.y, maxX + vector.x, maxY + vector.y)
    open fun getWidth() = maxX - minX
    open fun getHeight() = maxY - minY
    open fun getPerimeter() = 2.0 * (getWidth() + getHeight())
    open fun getArea() = getWidth() * getHeight()

    open fun union(aabb: AABB): AABB {
        minX = min(minX, aabb.minX)
        minY = min(minY, aabb.minY)
        maxX = max(maxX, aabb.maxX)
        maxY = max(maxY, aabb.maxY)
        return this
    }

    open fun union(aabb1: AABB, aabb2: AABB): AABB {
        minX = min(aabb1.minX, aabb2.minX)
        minY = min(aabb1.minY, aabb2.minY)
        maxX = max(aabb1.maxX, aabb2.maxX)
        maxY = max(aabb1.maxY, aabb2.maxY)
        return this
    }

    open fun getUnion(aabb: AABB) = copy().union(aabb)

    open fun intersection(aabb: AABB) = intersection(this, aabb)

    open fun intersection(aabb1: AABB, aabb2: AABB): AABB {
        minX = max(aabb1.minX, aabb2.minX)
        minY = max(aabb1.minY, aabb2.minY)
        maxX = min(aabb1.maxX, aabb2.maxX)
        maxY = min(aabb1.maxY, aabb2.maxY)
        if (minX > maxX || minY > maxY) zero()
        return this
    }

    open fun getIntersection(aabb: AABB) = copy().intersection(aabb)

    open fun expand(expansion: Double): AABB {
        val e = expansion * 0.5
        minX -= e
        minY -= e
        maxX += e
        maxY += e
        if (expansion < 0.0) {
            if (minX > maxX) {
                minX = (minX + maxX) * 0.5
                maxX = minX
            }
            if (minY > maxY) {
                minY = (minY + maxY) * 0.5
                maxY = minY
            }
        }
        return this
    }

    open fun getExpanded(expansion: Double) = copy().expand(expansion)
    open fun overlaps(aabb: AABB) = minX <= aabb.maxX && maxX >= aabb.minX && minY <= aabb.maxY && maxY >= aabb.minY
    open fun contains(aabb: AABB) = minX <= aabb.minX && maxX >= aabb.maxX && minY <= aabb.minY && maxY >= aabb.maxY
    open fun contains(point: Vector2) = contains(point.x, point.y)
    open fun contains(x: Double, y: Double) = minX <= x && maxX >= x && minY <= y && maxY >= y
    open fun isDegenerate() = minX == maxX || minY == maxY
    open fun isDegenerate(error: Double) = abs(maxX - minX) <= error || abs(maxY - minY) <= error
    open fun getCenter() = Vector2(minX + (maxX - minX) * 0.5, minY + (maxY - minY) * 0.5)
    open fun getMinX() = minX
    open fun getMinY() = minY
    open fun getMaxX() = maxX
    open fun getMaxY() = maxY

    companion object {
        private fun checkedRadius(radius: Double): Double {
            if (radius < 0.0) throw ValueOutOfRangeException("radius", radius, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
            return radius
        }
     fun createFromPoints(point1: Vector2, point2: Vector2) =
            createFromPoints(point1.x, point1.y, point2.x, point2.y)

     fun createFromPoints(point1x: Double, point1y: Double, point2x: Double, point2y: Double): AABB {
            val result = AABB(0.0, 0.0, 0.0, 0.0)
            setFromPoints(point1x, point1y, point2x, point2y, result)
            return result
        }

     fun setFromPoints(point1: Vector2, point2: Vector2, result: AABB) =
            setFromPoints(point1.x, point1.y, point2.x, point2.y, result)

     fun setFromPoints(point1x: Double, point1y: Double, point2x: Double, point2y: Double, result: AABB) {
            result.minX = min(point1x, point2x)
            result.minY = min(point1y, point2y)
            result.maxX = max(point1x, point2x)
            result.maxY = max(point1y, point2y)
        }
    }
}
