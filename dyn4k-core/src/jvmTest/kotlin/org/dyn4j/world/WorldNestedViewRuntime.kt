package org.dyn4j.world

internal actual fun worldNestedViewAllowsReadAfterChange(): Boolean {
    val first = Any()
    val backing = java.util.ArrayList<Any>()
    backing.add(first)
    val saved = java.util.Collections.unmodifiableList(backing).subList(0, 1)
    backing.add(Any())
    return try {
        saved.subList(0, 1)[0] === first
    } catch (_: ConcurrentModificationException) {
        false
    }
}
