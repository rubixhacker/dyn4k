package org.dyn4j.geometry.decompose

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse

class DecompositionSupportStateTest {
    @Test
    fun emptyFaceReportsAnUnlinkedEdge() {
        assertEquals("Face[Edge=null]", DoubleEdgeListFace().toString())
    }

    @Test
    fun unlinkedVerticesAreNotAdjacent() {
        assertFalse(MonotoneVertex("a").isAdjacent(MonotoneVertex("b")))
    }
}
