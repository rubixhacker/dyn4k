package org.dyn4j

internal actual fun runtimeClassName(value: Any): String = value::class.simpleName ?: ""
