package org.dyn4j.geometry

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertEquals
import kotlin.test.assertNotSame
import kotlin.test.assertSame

val FoundationPackageBridgeTest by testSuite {
    test("rotationHelpersKeepIdentityAndReturnIndependentCopies") { FoundationPackageBridgeTestFixture().run { rotationHelpersKeepIdentityAndReturnIndependentCopies() } }
    test("componentRotationsAndAxisConstantsMatchBaseline") { FoundationPackageBridgeTestFixture().run { componentRotationsAndAxisConstantsMatchBaseline() } }
}

private class FoundationPackageBridgeTestFixture  {
fun rotationHelpersKeepIdentityAndReturnIndependentCopies() {
        val rotation = Rotation()
        assertSame(rotation, rotation.rotate(0.0, 1.0))
        assertEquals(0.0, rotation.getCost(), 1e-12)
        assertEquals(1.0, rotation.getSint(), 1e-12)
        assertEquals(0.0, rotation.dot(Vector2(1.0, 0.0)), 1e-12)
        assertEquals(-1.0, rotation.cross(Vector2(1.0, 0.0)), 1e-12)
        val copy = rotation.getRotated45Helper(1.0, 0.0)
        assertNotSame(rotation, copy)
        assertEquals(1.0 / kotlin.math.sqrt(2.0), copy.getCost(), 1e-12)
        assertSame(rotation, rotation.rotate45Helper(1.0, 0.0))
        assertEquals(copy.getSint(), rotation.getSint(), 1e-12)
    }

fun componentRotationsAndAxisConstantsMatchBaseline() {
        val vector = Vector2(1.0, 0.0)
        assertSame(vector, vector.rotate(0.0, 1.0))
        assertEquals(1.0, vector.y, 1e-12)
        assertSame(vector, vector.rotate(0.0, -1.0, 1.0, 1.0))
        assertEquals(1.0, vector.x, 1e-12)
        assertEquals(2.0, vector.y, 1e-12)
        assertEquals(1.0, Vector2.X_AXIS.x)
        assertEquals(1.0, Vector2.Y_AXIS.y)
        assertEquals(-1.0, Vector2.INV_X_AXIS.x)
        assertEquals(-1.0, Vector2.INV_Y_AXIS.y)

        val transform = Transform()
        transform.translate(2.0, 0.0)
        transform.rotate(0.0, 1.0)
        assertEquals(0.0, transform.getTranslationX(), 1e-12)
        assertEquals(2.0, transform.getTranslationY(), 1e-12)
        transform.rotate(0.0, -1.0, 1.0, 1.0)
        assertEquals(2.0, transform.getTranslationX(), 1e-12)
        assertEquals(2.0, transform.getTranslationY(), 1e-12)
        assertEquals(0.0, transform.getRotationAngle(), 1e-12)
    }
}
