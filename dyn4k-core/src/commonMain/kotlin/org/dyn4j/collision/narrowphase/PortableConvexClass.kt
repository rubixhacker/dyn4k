package org.dyn4j.collision.narrowphase

import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Link
import org.dyn4j.geometry.Polygon
import org.dyn4j.geometry.Rectangle
import org.dyn4j.geometry.Segment
import kotlin.reflect.KClass

class PortableConvexClass<T : Any> internal constructor(val type: KClass<T>) {
    internal var sample: Any? = null
    override fun equals(other: Any?): Boolean = other is PortableConvexClass<*> && type == other.type
    override fun hashCode(): Int = type.hashCode()
}

internal object PortableConvexClasses {
    private val directSupertypes = mutableMapOf<KClass<out Convex>, MutableSet<KClass<out Convex>>>()

    init {
        declare(Rectangle::class, Polygon::class)
        declare(Link::class, Segment::class)
    }

    fun <T : Convex> of(type: KClass<T>): PortableConvexClass<T> = PortableConvexClass(type)

    fun declare(type: KClass<out Convex>, directSupertype: KClass<out Convex>) {
        directSupertypes.getOrPut(type) { mutableSetOf() }.add(directSupertype)
    }

    fun runtime(convex: Convex): PortableConvexClass<out Convex> = of(convex::class).also { it.sample = convex }
    fun name(type: PortableConvexClass<out Convex>): String = type.type.simpleName ?: type.type.toString()
    fun assignable(type: PortableConvexClass<out Convex>, other: PortableConvexClass<out Convex>): Boolean =
        other.sample?.let(type.type::isInstance) ?: declaredAssignable(type.type, other.type)

    private fun declaredAssignable(type: KClass<out Convex>, other: KClass<out Convex>): Boolean {
        val pending = ArrayList<KClass<out Convex>>()
        val visited = mutableSetOf<KClass<out Convex>>()
        pending.add(other)
        while (pending.isNotEmpty()) {
            val current = pending.removeAt(pending.lastIndex)
            if (current == type) return true
            if (visited.add(current)) {
                if (type == Convex::class) return true
                directSupertypes[current]?.let(pending::addAll)
            }
        }
        return false
    }
}
