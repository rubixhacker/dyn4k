package org.dyn4j.collision.narrowphase

import org.dyn4j.geometry.Convex
import kotlin.reflect.KClass

actual typealias ConvexClass<T> = PortableConvexClass<T>
internal actual fun runtimeConvexClass(convex: Convex): ConvexClass<out Convex> = PortableConvexClasses.runtime(convex)
internal actual fun convexClassName(type: ConvexClass<out Convex>): String = PortableConvexClasses.name(type)
internal actual fun convexClassAssignable(type: ConvexClass<out Convex>, other: ConvexClass<out Convex>): Boolean = PortableConvexClasses.assignable(type, other)
actual fun <T : Convex> convexClassOf(type: KClass<T>): ConvexClass<T> = PortableConvexClasses.of(type)
