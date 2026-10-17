package org.dyn4j.world

internal actual fun <E> worldTrackedArrayList(initialCapacity: Int): WorldTrackedArrayList<E> =
    WorldTrackedArrayList(initialCapacity)
