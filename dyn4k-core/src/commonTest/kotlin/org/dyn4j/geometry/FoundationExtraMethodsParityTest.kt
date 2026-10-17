package org.dyn4j.geometry

import kotlin.test.Test
import kotlin.test.assertEquals

class FoundationExtraMethodsParityTest {
    private class RotationExtension : Rotation() {
        init { cost = 0.0; sint = 1.0 }

        override fun getCost() = 17.0
        override fun getSint() = 19.0
    }

    private class TransformExtension : Transform() {
        init { cost = 0.0; sint = 1.0 }

        override fun getCost() = 23.0
        override fun getSint() = 29.0
    }

    @Test
    fun rotationKeepsFieldBasedMathAndGetterDispatch() {
        val rotation: Rotation = RotationExtension()

        assertEquals(17.0, rotation.getCost())
        assertEquals(19.0, rotation.getSint())
        assertEquals(0.0, rotation.costValue())
        assertEquals(1.0, rotation.sintValue())
        val turned = Vector2(1.0, 0.0).rotate(rotation)
        assertEquals(0.0, turned.x)
        assertEquals(1.0, turned.y)
        val destination = Transform()
        destination.rotate(rotation)
        val transformed = destination.getTransformedR(Vector2(1.0, 0.0))
        assertEquals(0.0, transformed.x)
        assertEquals(1.0, transformed.y)
    }

    @Test
    fun transformKeepsFieldBasedFactoryAndGetterDispatch() {
        val transform: Transform = TransformExtension()

        assertEquals(23.0, transform.getCost())
        assertEquals(29.0, transform.getSint())
        assertEquals(0.0, transform.costValue())
        assertEquals(1.0, transform.sintValue())
        val rotation = Rotation.of(transform)
        assertEquals(0.0, rotation.getCost())
        assertEquals(1.0, rotation.getSint())
    }
}
