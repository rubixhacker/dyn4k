package org.dyn4j.collision.narrowphase

import org.dyn4j.geometry.Convex
import kotlin.reflect.KClass

actual typealias ConvexClass<T> = java.lang.Class<T>
internal actual fun runtimeConvexClass(convex: Convex): ConvexClass<out Convex> = convex.javaClass
internal actual fun convexClassName(type: ConvexClass<out Convex>): String = type.name
internal actual fun convexClassAssignable(type: ConvexClass<out Convex>, other: ConvexClass<out Convex>): Boolean = type.isAssignableFrom(other)
actual fun <T : Convex> convexClassOf(type: KClass<T>): ConvexClass<T> = type.java
