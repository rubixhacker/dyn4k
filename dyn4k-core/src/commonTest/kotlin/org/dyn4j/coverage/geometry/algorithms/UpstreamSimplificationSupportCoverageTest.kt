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

package org.dyn4j.geometry.simplify

import de.infix.testBalloon.framework.core.testSuite
import org.dyn4j.geometry.Vector2
import org.dyn4j.geometry.simplify.SegmentTreeLeaf
import org.dyn4j.geometry.simplify.SegmentTreeNode
import org.dyn4j.geometry.simplify.SimplePolygonVertex
import kotlin.test.*

val UpstreamSimplificationSupportCoverageTest by testSuite {
    test("SegmentTreeTest_createLeaf") { UpstreamSimplificationSupportCoverageTestFixture().run { SegmentTreeTest_createLeaf() } }
    test("SegmentTreeTest_createNode") { UpstreamSimplificationSupportCoverageTestFixture().run { SegmentTreeTest_createNode() } }
    test("SimplePolygonVertexTest_create") { UpstreamSimplificationSupportCoverageTestFixture().run { SimplePolygonVertexTest_create() } }
}

private class UpstreamSimplificationSupportCoverageTestFixture  {
fun SegmentTreeTest_createLeaf() {
        val first = Vector2(1.0, 2.0)
        val second = Vector2(3.0, 4.0)
        val leaf = SegmentTreeLeaf(first, second, 6, 8)
        assertSame(first, leaf.point1)
        assertSame(second, leaf.point2)
        assertNotNull(leaf.aabb)
        assertEquals(0, leaf.height)
        assertEquals(6, leaf.index1)
        assertEquals(8, leaf.index2)
        assertNull(leaf.left)
        assertNull(leaf.parent)
        assertNull(leaf.right)
        assertNotNull(leaf.toString())
    }

fun SegmentTreeTest_createNode() {
        val node = SegmentTreeNode()
        assertNotNull(node.aabb)
        assertEquals(0, node.height)
        assertNull(node.left)
        assertNull(node.parent)
        assertNull(node.right)
        assertNotNull(node.toString())
    }

fun SimplePolygonVertexTest_create() {
        val point = Vector2(1.0, 2.0)
        val vertex = SimplePolygonVertex(2, point)
        assertSame(point, vertex.point)
        assertEquals(2, vertex.index)
        assertNull(vertex.next)
        assertNull(vertex.nextSegment)
        assertNull(vertex.prev)
        assertNull(vertex.prevSegment)
        assertNotNull(vertex.toString())
    }
}
