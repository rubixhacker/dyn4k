package org.dyn4j.geometry.decompose

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertEquals
import kotlin.test.assertFalse

val DecompositionSupportStateTest by testSuite {
    test("emptyFaceReportsAnUnlinkedEdge") { DecompositionSupportStateTestFixture().run { emptyFaceReportsAnUnlinkedEdge() } }
    test("unlinkedVerticesAreNotAdjacent") { DecompositionSupportStateTestFixture().run { unlinkedVerticesAreNotAdjacent() } }
}

private class DecompositionSupportStateTestFixture  {
fun emptyFaceReportsAnUnlinkedEdge() {
        assertEquals("Face[Edge=null]", DoubleEdgeListFace().toString())
    }

fun unlinkedVerticesAreNotAdjacent() {
        assertFalse(MonotoneVertex("a").isAdjacent(MonotoneVertex("b")))
    }
}
