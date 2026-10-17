package org.dyn4j.world

internal class WorldTrackedArrayList<E> : ArrayList<E> {
    private var structuralVersion = 0

    constructor() : super()
    constructor(initialCapacity: Int) : super(initialCapacity)

    override fun add(element: E): Boolean {
        val added = super.add(element)
        structuralVersion++
        return added
    }

    override fun add(index: Int, element: E) {
        super.add(index, element)
        structuralVersion++
    }

    override fun addAll(elements: Collection<E>): Boolean {
        val added = super.addAll(elements)
        structuralVersion++
        return added
    }

    override fun addAll(index: Int, elements: Collection<E>): Boolean {
        val added = super.addAll(index, elements)
        structuralVersion++
        return added
    }

    override fun remove(element: E): Boolean {
        val removed = super.remove(element)
        if (removed) structuralVersion++
        return removed
    }

    override fun removeAt(index: Int): E {
        val removed = super.removeAt(index)
        structuralVersion++
        return removed
    }

    override fun removeAll(elements: Collection<E>): Boolean {
        val removed = super.removeAll(elements)
        if (removed) structuralVersion++
        return removed
    }

    override fun retainAll(elements: Collection<E>): Boolean {
        val removed = super.retainAll(elements)
        if (removed) structuralVersion++
        return removed
    }

    override fun clear() {
        super.clear()
        structuralVersion++
    }

    @kotlin.jvm.JvmSynthetic
    fun liveView(): List<E> = object : AbstractList<E>() {
        override val size: Int get() = this@WorldTrackedArrayList.size
        override fun get(index: Int): E = this@WorldTrackedArrayList[index]
        override fun iterator(): Iterator<E> = listIterator()
        override fun listIterator(): ListIterator<E> = listIterator(0)

        override fun listIterator(index: Int): ListIterator<E> {
            if (index < 0 || index > size) throw IndexOutOfBoundsException()
            val expectedVersion = structuralVersion
            var cursor = index
            return object : ListIterator<E> {
                override fun hasNext(): Boolean = cursor < size
                override fun hasPrevious(): Boolean = cursor > 0
                override fun nextIndex(): Int = cursor
                override fun previousIndex(): Int = cursor - 1

                override fun next(): E {
                    if (structuralVersion != expectedVersion) throw ConcurrentModificationException()
                    if (!hasNext()) throw NoSuchElementException()
                    return get(cursor++)
                }

                override fun previous(): E {
                    if (structuralVersion != expectedVersion) throw ConcurrentModificationException()
                    if (!hasPrevious()) throw NoSuchElementException()
                    return get(--cursor)
                }
            }
        }
    }
}
