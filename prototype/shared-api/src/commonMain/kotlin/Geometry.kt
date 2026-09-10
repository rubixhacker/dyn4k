package org.dyn4j.geometry

import kotlin.jvm.JvmField

// PROTOTYPE: only the translational, no-contact journey described in README.
open class Vector2(@JvmField var x: Double, @JvmField var y: Double) {
    constructor() : this(0.0, 0.0)
    open fun add(x: Double, y: Double): Vector2 { this.x += x; this.y += y; return this }
    open fun copy(): Vector2 = Vector2(x, y)
}
open class Transform {
    private var x = 0.0
    private var y = 0.0
    open fun getTranslationX(): Double = x
    open fun getTranslationY(): Double = y
    open fun translate(x: Double, y: Double) { this.x += x; this.y += y }
}
