package org.dyn4j.world

internal expect fun <E> worldPlatformUnmodifiableList(view: List<E>): List<E>

internal expect fun <E> worldPlatformUnmodifiableBackingList(backing: MutableList<E>, portableView: List<E>): List<E>
