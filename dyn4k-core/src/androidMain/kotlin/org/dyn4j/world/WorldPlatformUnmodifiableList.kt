package org.dyn4j.world

internal actual fun <E> worldPlatformUnmodifiableList(view: List<E>): List<E> =
    java.util.Collections.unmodifiableList(view)
