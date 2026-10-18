package org.dyn4j.geometry

internal object RotationVectorAccessFixture {
    fun dot(rotation: Rotation, vector: Vector2): Double = rotation.dot(vector)

    fun cross(rotation: Rotation, vector: Vector2): Double = rotation.cross(vector)
}
