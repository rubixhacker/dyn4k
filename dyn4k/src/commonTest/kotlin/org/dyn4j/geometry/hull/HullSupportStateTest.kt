package org.dyn4j.geometry.hull

import kotlin.test.Test
import kotlin.test.assertNull
import org.dyn4j.geometry.Vector2

class HullSupportStateTest {
    @Test
    fun newVertexHasNoLinks() {
        val vertex = LinkedVertex(Vector2(0.0, 0.0))
        assertNull(vertex.next)
        assertNull(vertex.prev)
        val singleton = LinkedVertexHull(Vector2(5.0, 6.0)).toArray()
        kotlin.test.assertEquals(1, singleton.size)
    }
}
