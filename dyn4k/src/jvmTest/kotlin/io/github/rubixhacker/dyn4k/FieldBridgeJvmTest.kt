package io.github.rubixhacker.dyn4k

import kotlin.test.Test
import kotlin.test.assertEquals
import org.dyn4j.geometry.Rotation
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2

private class KotlinRotationExtension : Rotation() {
    fun setRawCost(value: Double) { cost = value }
    fun rawCost() = cost
}

private class KotlinTransformExtension : Transform() {
    fun setRawX(value: Double) { x = value }
    fun rawX() = x
}

class FieldBridgeJvmTest {
    @Test
    fun javaBeanMethodsRemainSeparateFromKotlinFields() {
        val vector = VectorAccessorExtension(4.0, 2.0)
        val shared: Vector2 = vector
        assertEquals(4.0, shared.x)
        assertEquals(8.0, vector.readBeanX())
        shared.x = 5.0
        assertEquals(5.0, shared.x)
        assertEquals(10.0, vector.readBeanX())
        vector.writeBeanX(2.0)
        assertEquals(6.0, shared.x)

        val vector3 = FieldAccessorExtensions.Vector3Extension()
        val shared3: org.dyn4j.geometry.Vector3 = vector3
        shared3.z = 4.0
        assertEquals(4.0, shared3.z)
        assertEquals(8.0, vector3.readBean())
        vector3.writeBean(2.0)
        assertEquals(6.0, shared3.z)

        val matrix22 = FieldAccessorExtensions.Matrix22Extension()
        val shared22: org.dyn4j.geometry.Matrix22 = matrix22
        shared22.m00 = 4.0
        assertEquals(4.0, shared22.m00)
        assertEquals(8.0, matrix22.readBean())
        matrix22.writeBean(2.0)
        assertEquals(6.0, shared22.m00)

        val matrix33 = FieldAccessorExtensions.Matrix33Extension()
        val shared33: org.dyn4j.geometry.Matrix33 = matrix33
        shared33.m22 = 4.0
        assertEquals(4.0, shared33.m22)
        assertEquals(8.0, matrix33.readBean())
        matrix33.writeBean(2.0)
        assertEquals(6.0, shared33.m22)

        val reference = FieldAccessorExtensions.ReferenceExtension()
        val sharedReference: org.dyn4j.Reference<String> = reference
        assertEquals("raw", sharedReference.value)
        assertEquals("bean:raw", reference.readBean())
        sharedReference.value = "direct"
        assertEquals("direct", sharedReference.value)
        assertEquals("bean:direct", reference.readBean())
        reference.writeBean("custom")
        assertEquals("stored:custom", sharedReference.value)
    }

    @Test
    fun protectedFieldsKeepSubclassAccess() {
        val javaRotation = FieldAccessorExtensions.RotationExtension()
        assertEquals(1.0, javaRotation.rawCost())
        javaRotation.writeBean(2.0)
        assertEquals(6.0, javaRotation.rawCost())
        assertEquals(12.0, javaRotation.readBean())

        val javaTransform = FieldAccessorExtensions.TransformExtension()
        javaTransform.writeBean(2.0)
        assertEquals(6.0, javaTransform.rawX())
        assertEquals(12.0, javaTransform.readBean())

        val kotlinRotation = KotlinRotationExtension()
        kotlinRotation.setRawCost(3.0)
        assertEquals(3.0, kotlinRotation.rawCost())
        val kotlinTransform = KotlinTransformExtension()
        kotlinTransform.setRawX(3.0)
        assertEquals(3.0, kotlinTransform.rawX())
    }
}
