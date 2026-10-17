package io.github.rubixhacker.dyn4k

import kotlin.test.Test
import kotlin.test.assertEquals
import org.dyn4j.geometry.Vector2
import org.dyn4j.geometry.simplify.VertexClusterReduction

class PolygonSubclassExtensionTest {
    private class Extension : VertexClusterReduction(0.1) {
        fun getClusterTolerance(): String = "extension"
    }

    @Test
    fun subclassCanUseItsOwnHelperAndInheritedAlgorithm() {
        val extension = Extension()
        assertEquals("extension", extension.getClusterTolerance())
        assertEquals(0.1, extension.clusterTolerance)
        val points = arrayOf(
            Vector2(0.0, 0.0), Vector2(2.0, 0.0),
            Vector2(2.0, 2.0), Vector2(0.0, 2.0)
        )
        assertEquals(4, extension.simplify(*points)!!.size)
    }
}
