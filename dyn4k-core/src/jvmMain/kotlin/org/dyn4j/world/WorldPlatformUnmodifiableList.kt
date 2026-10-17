package org.dyn4j.world

internal actual fun <E> worldPlatformUnmodifiableList(view: List<E>): List<E> =
    java.util.Collections.unmodifiableList(view)

internal actual fun <E> worldPlatformUnmodifiableBackingList(backing: MutableList<E>, portableView: List<E>): List<E> =
    java.util.Collections.unmodifiableList(backing)
