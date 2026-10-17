package org.dyn4j.collision.narrowphase

import org.dyn4j.geometry.Convex
import kotlin.reflect.KClass

class PortableConvexClass<T : Any> internal constructor(val type: KClass<T>) {
    internal var sample: Any? = null
    override fun equals(other: Any?): Boolean = other is PortableConvexClass<*> && type == other.type
    override fun hashCode(): Int = type.hashCode()
}

internal object PortableConvexClasses {
    fun <T : Convex> of(type: KClass<T>): PortableConvexClass<T> = PortableConvexClass(type)

    fun runtime(convex: Convex): PortableConvexClass<out Convex> = of(convex::class).also { it.sample = convex }
    fun name(type: PortableConvexClass<out Convex>): String = type.type.toString()
    fun assignable(type: PortableConvexClass<out Convex>, other: PortableConvexClass<out Convex>): Boolean =
        other.sample?.let(type.type::isInstance) ?: (type.type == other.type)
}
