package org.dyn4j.geometry

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class GeometryCopyExtensionTest {
    @Test
    fun curvedShapeCopiesDispatchVectorCopiesAndKeepIndependentState() {
        val capsule = CopyAwareCapsule()
        val capsuleCopy = capsule.duplicate()
        assertTrue(capsuleCopy.firstFocus() is CopyTaggedVector)
        assertEquals(11.0, capsuleCopy.firstFocus().x)
        assertEquals(22.0, capsuleCopy.firstFocus().y)
        assertFalse(capsuleCopy.firstFocus() === capsule.firstFocus())
        capsule.firstFocus().x = 5.0
        assertEquals(11.0, capsuleCopy.firstFocus().x)

        val slice = CopyAwareSlice()
        val sliceCopy = slice.duplicate()
        assertTrue(sliceCopy.firstVertex() is CopyTaggedVector)
        assertEquals(11.0, sliceCopy.firstVertex().x)
        assertEquals(22.0, sliceCopy.firstVertex().y)
        assertTrue(sliceCopy.firstNormal() is CopyTaggedVector)
        assertEquals(13.0, sliceCopy.firstNormal().x)
        assertEquals(24.0, sliceCopy.firstNormal().y)
        assertFalse(sliceCopy.firstVertex() === slice.firstVertex())
        slice.firstVertex().y = 7.0
        assertEquals(22.0, sliceCopy.firstVertex().y)
        assertEquals(0.7, sliceCopy.getTheta())
    }

    private class CopyTaggedVector(x: Double, y: Double) : Vector2(x, y) {
        override fun copy(): Vector2 = CopyTaggedVector(x + 10.0, y + 20.0)
    }

    private class CopyAwareCapsule : Capsule {
        constructor() : super(2.0, 4.0) { foci[0] = CopyTaggedVector(1.0, 2.0) }
        private constructor(other: CopyAwareCapsule) : super(other)
        fun duplicate() = CopyAwareCapsule(this)
        fun firstFocus(): Vector2 = foci[0]
    }

    private class CopyAwareSlice : Slice {
        constructor() : super(2.0, 0.7) {
            vertices[0] = CopyTaggedVector(1.0, 2.0)
            normals[0] = CopyTaggedVector(3.0, 4.0)
        }
        private constructor(other: CopyAwareSlice) : super(other)
        fun duplicate() = CopyAwareSlice(this)
        fun firstVertex(): Vector2 = vertices[0]
        fun firstNormal(): Vector2 = normals[0]
    }
}
