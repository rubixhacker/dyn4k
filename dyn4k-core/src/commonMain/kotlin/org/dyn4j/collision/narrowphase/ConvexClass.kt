package org.dyn4j.collision.narrowphase

import org.dyn4j.geometry.Convex
import kotlin.reflect.KClass

expect class ConvexClass<T : Any>

internal expect fun runtimeConvexClass(convex: Convex): ConvexClass<out Convex>
internal expect fun convexClassName(type: ConvexClass<out Convex>): String
internal expect fun convexClassAssignable(type: ConvexClass<out Convex>, other: ConvexClass<out Convex>): Boolean
expect fun <T : Convex> convexClassOf(type: KClass<T>): ConvexClass<T>
