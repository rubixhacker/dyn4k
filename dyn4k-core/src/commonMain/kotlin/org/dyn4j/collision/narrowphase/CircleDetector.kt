/*
 * Copyright (c) 2010-2022 William Bittle  http://www.dyn4j.org/
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

import kotlin.math.sqrt
import org.dyn4j.JvmStaticBridge
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.Ray
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2

class CircleDetector private constructor() {
    companion object {
        private val X_AXIS = Vector2(1.0, 0.0)

        @JvmStaticBridge fun detect(circle1: Circle, transform1: Transform, circle2: Circle, transform2: Transform, penetration: Penetration): Boolean {
            val center1 = transform1.getTransformed(circle1.getCenter())
            val center2 = transform2.getTransformed(circle2.getCenter())
            val axis = center2.subtract(center1)
            val radii = circle1.getRadius() + circle2.getRadius()
            if (axis.getMagnitudeSquared() < radii * radii) {
                val depth = radii - axis.normalize()
                penetration.setDirect(axis.x, axis.y, depth)
                return true
            }
            return false
        }

        @JvmStaticBridge fun detect(circle1: Circle, transform1: Transform, circle2: Circle, transform2: Transform): Boolean {
            val center1 = transform1.getTransformed(circle1.getCenter())
            val center2 = transform2.getTransformed(circle2.getCenter())
            val axis = center2.subtract(center1)
            val radii = circle1.getRadius() + circle2.getRadius()
            return axis.getMagnitudeSquared() < radii * radii
        }

        @JvmStaticBridge fun distance(circle1: Circle, transform1: Transform, circle2: Circle, transform2: Transform, separation: Separation): Boolean {
            val center1 = transform1.getTransformed(circle1.getCenter())
            val center2 = transform2.getTransformed(circle2.getCenter())
            val radius1 = circle1.getRadius()
            val radius2 = circle2.getRadius()
            val axis = center1.to(center2)
            val radii = radius1 + radius2
            if (axis.getMagnitudeSquared() >= radii * radii) {
                val distance = axis.normalize() - radii
                separation.setDirect(axis.x, axis.y, distance,
                    center1.x + axis.x * radius1, center1.y + axis.y * radius1,
                    center2.x - axis.x * radius2, center2.y - axis.y * radius2)
                return true
            }
            return false
        }

        @JvmStaticBridge fun contains(circle1: Circle, transform1: Transform, circle2: Circle, transform2: Transform, containment: Containment): Boolean {
            val interval1 = circle1.project(X_AXIS, transform1)
            val interval2 = circle2.project(X_AXIS, transform2)
            val firstContainsSecond = interval1.containsExclusive(interval2)
            val secondContainsFirst = interval2.containsExclusive(interval1)
            if (firstContainsSecond || secondContainsFirst) {
                containment.setAContainedInB(secondContainsFirst)
                containment.setBContainedInA(firstContainsSecond)
                return true
            }
            return false
        }

        @JvmStaticBridge fun raycast(ray: Ray, maxLength: Double, circle: Circle, transform: Transform, raycast: Raycast): Boolean {
            val start = ray.getStart()
            val direction = ray.getDirectionVector()
            val center = transform.getTransformed(circle.getCenter())
            val radius = circle.getRadius()
            if (circle.contains(start, transform)) return false
            val startMinusCenter = start.difference(center)
            val a = direction.dot(direction)
            val b = 2.0 * direction.dot(startMinusCenter)
            val c = startMinusCenter.dot(startMinusCenter) - radius * radius
            val inverse2a = 1.0 / (2.0 * a)
            val discriminant = b * b - 4.0 * a * c
            if (discriminant < 0.0) return false
            val root = sqrt(discriminant)
            val t0 = (-b + root) * inverse2a
            val t1 = (-b - root) * inverse2a
            val t = if (t0 < 0.0) {
                if (t1 < 0.0) return false else t1
            } else if (t1 < 0.0 || t0 < t1) t0 else t1
            if (maxLength > 0.0 && t > maxLength) return false
            val point = direction.product(t).add(start)
            val normal = center.to(point)
            normal.normalize()
            raycast.setDirect(point.x, point.y, normal.x, normal.y, t)
            return true
        }
    }
}
