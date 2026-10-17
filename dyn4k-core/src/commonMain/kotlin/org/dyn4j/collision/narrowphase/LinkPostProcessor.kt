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
import org.dyn4j.geometry.Link
import org.dyn4j.geometry.Transform

class LinkPostProcessor : NarrowphasePostProcessor {
    override fun process(convex1: Convex, transform1: Transform, convex2: Convex, transform2: Transform, penetration: Penetration) {
        if (convex1 is Link) process(convex1, penetration)
        else if (convex2 is Link) {
            penetration.getNormal().negate()
            process(convex2, penetration)
            penetration.getNormal().negate()
        }
    }

    fun process(link: Link, penetration: Penetration) {
        val previous = link.getPoint0()
        val next = link.getPoint3()
        if (previous == null && next == null) return

        val normal = penetration.getNormal().copy()
        val edge = link.getEdgeVector()
        val edgeNormal = edge.getLeftHandOrthogonalVector()
        val side = normal.dot(edge)
        val back = normal.dot(edgeNormal)
        if (side <= 0.0) {
            if (previous == null) return
            val previousEdge = link.getPreviousEdgeVector()
            previousEdge.normalize()
            val convex = previousEdge.cross(edge) > 0.0
            if (convex) {
                if (normal.cross(previousEdge.getLeftHandOrthogonalVector()) > 0.0) penetration.clear()
            } else if (back < 0.0) penetration.clear()
            else {
                penetration.getNormal().x = edgeNormal.x
                penetration.getNormal().y = edgeNormal.y
            }
        } else {
            if (next == null) return
            val nextEdge = link.getNextEdgeVector()
            nextEdge.normalize()
            val convex = edge.cross(nextEdge) > 0.0
            if (convex) {
                if (nextEdge.getLeftHandOrthogonalVector().cross(normal) > 0.0) penetration.clear()
            } else if (back < 0.0) penetration.clear()
            else {
                penetration.getNormal().x = edgeNormal.x
                penetration.getNormal().y = edgeNormal.y
            }
        }
    }
}
