package org.dyn4j.world

internal actual fun <E> worldTrackedArrayList(initialCapacity: Int): WorldTrackedArrayList<E> =
    WorldJavaTrackedArrayList(initialCapacity)

private class WorldJavaTrackedArrayList<E>(initialCapacity: Int) : WorldTrackedArrayList<E>(initialCapacity) {
    fun sort(comparator: Comparator<in E>?) = sortElements(comparator)

    fun replaceAll(operator: java.util.function.UnaryOperator<E>) = replaceAllElements(operator::apply)

    fun removeIf(filter: java.util.function.Predicate<in E>): Boolean = removeIfElements(filter::test)
}
