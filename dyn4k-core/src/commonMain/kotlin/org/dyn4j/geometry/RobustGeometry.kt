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
package org.dyn4j.geometry

import kotlin.math.abs

class RobustGeometry {
    companion object {
     val SPLITTER: Int
        private val RESULT_ERROR_BOUND: Double
        private val ERROR_BOUND_A: Double
        private val ERROR_BOUND_B: Double
        private val ERROR_BOUND_C: Double

        init {
            var everyOther = true
            var epsilon = 1.0
            var splitter = 1
            while (1.0 + epsilon > 1.0) {
                if (everyOther) splitter *= 2
                epsilon *= 0.5
                everyOther = !everyOther
            }
            SPLITTER = splitter + 1
            RESULT_ERROR_BOUND = (3 + 8 * epsilon) * epsilon
            ERROR_BOUND_A = (3 + 16 * epsilon) * epsilon
            ERROR_BOUND_B = (2 + 12 * epsilon) * epsilon
            ERROR_BOUND_C = (9 + 64 * epsilon) * epsilon * epsilon
        }

     fun cross(ax: Double, ay: Double, bx: Double, by: Double): AdaptiveDecimal =
            cross(ax, ay, bx, by, null)

     fun cross(ax: Double, ay: Double, bx: Double, by: Double, result: AdaptiveDecimal?): AdaptiveDecimal {
            val axby = ax * by
            val aybx = bx * ay
            val axbyTail = AdaptiveDecimal.getErrorComponentFromProduct(ax, by, axby)
            val aybxTail = AdaptiveDecimal.getErrorComponentFromProduct(bx, ay, aybx)
            return AdaptiveDecimal.fromDiff(axbyTail, axby, aybxTail, aybx, result)
        }

     fun getLocation(point: Vector2, linePoint1: Vector2, linePoint2: Vector2): Double {
            val detLeft = (point.x - linePoint2.x) * (linePoint1.y - linePoint2.y)
            val detRight = (point.y - linePoint2.y) * (linePoint1.x - linePoint2.x)
            val det = detLeft - detRight
            if (detLeft == 0.0 || detRight == 0.0 || (detLeft > 0.0) != (detRight > 0.0)) return det
            val detSum = abs(detLeft + detRight)
            if (abs(det) >= ERROR_BOUND_A * detSum) return det
            return getLocationAdaptive(point, linePoint1, linePoint2, detSum)
        }

        private fun getLocationAdaptive(point: Vector2, linePoint1: Vector2, linePoint2: Vector2, detSum: Double): Double {
            val acx = point.x - linePoint2.x
            val acy = point.y - linePoint2.y
            val bcx = linePoint1.x - linePoint2.x
            val bcy = linePoint1.y - linePoint2.y
            val b = cross(acx, acy, bcx, bcy)
            var det = b.getEstimation()
            var errorBound = ERROR_BOUND_B * detSum
            if (abs(det) >= errorBound) return det
            val acxTail = AdaptiveDecimal.getErrorComponentFromDifference(point.x, linePoint2.x, acx)
            val acyTail = AdaptiveDecimal.getErrorComponentFromDifference(point.y, linePoint2.y, acy)
            val bcxTail = AdaptiveDecimal.getErrorComponentFromDifference(linePoint1.x, linePoint2.x, bcx)
            val bcyTail = AdaptiveDecimal.getErrorComponentFromDifference(linePoint1.y, linePoint2.y, bcy)
            if (acxTail == 0.0 && acyTail == 0.0 && bcxTail == 0.0 && bcyTail == 0.0) return det
            errorBound = ERROR_BOUND_C * detSum + RESULT_ERROR_BOUND * abs(det)
            det += (acx * bcyTail + bcy * acxTail) - (acy * bcxTail + bcx * acyTail)
            if (abs(det) >= errorBound) return det
            val buffer = AdaptiveDecimal(4)
            cross(acxTail, bcx, acyTail, bcy, buffer)
            val c1 = b.sum(buffer)
            cross(acx, bcxTail, acy, bcyTail, buffer)
            val c2 = c1.sum(buffer)
            cross(acxTail, bcxTail, acyTail, bcyTail, buffer)
            val d = c2.sum(buffer)
            return d.get(d.size() - 1)
        }
    }
}
