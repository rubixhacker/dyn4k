package org.dyn4j.world

internal actual fun <E> worldTrackedArrayList(initialCapacity: Int): MutableList<E> =
    WorldTrackedArrayList(initialCapacity)
