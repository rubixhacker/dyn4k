package org.dyn4j.collision

import kotlin.jvm.JvmField
import org.dyn4j.geometry.Transform

open class Fixture
abstract class AbstractCollisionBody<T : Fixture> {
    @JvmField protected val transform = Transform()
    open fun getTransform(): Transform = transform
    open fun translate(x: Double, y: Double) = transform.translate(x, y)
}
