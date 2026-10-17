package org.dyn4j.world

internal class WorldTrackedArrayList<E>(initialCapacity: Int = 10) : AbstractMutableList<E>() {
    private val backing = ArrayList<E>(initialCapacity)
    private var structuralVersion = 0

    override val size: Int get() = backing.size
    override fun get(index: Int): E = backing[index]
    override fun set(index: Int, element: E): E = backing.set(index, element)

    override fun add(element: E): Boolean {
        val added = backing.add(element)
        structuralVersion++
        return added
    }

    override fun add(index: Int, element: E) {
        backing.add(index, element)
        structuralVersion++
    }

    override fun addAll(elements: Collection<E>): Boolean {
        val added = backing.addAll(elements)
        structuralVersion++
        return added
    }

    override fun addAll(index: Int, elements: Collection<E>): Boolean {
        val added = backing.addAll(index, elements)
        structuralVersion++
        return added
    }

    override fun remove(element: E): Boolean {
        val removed = backing.remove(element)
        if (removed) structuralVersion++
        return removed
    }

    override fun removeAt(index: Int): E {
        val removed = backing.removeAt(index)
        structuralVersion++
        return removed
    }

    override fun removeAll(elements: Collection<E>): Boolean {
        val removed = backing.removeAll(elements)
        if (removed) structuralVersion++
        return removed
    }

    override fun retainAll(elements: Collection<E>): Boolean {
        val removed = backing.retainAll(elements)
        if (removed) structuralVersion++
        return removed
    }

    override fun clear() {
        backing.clear()
        structuralVersion++
    }

    override fun iterator(): MutableIterator<E> = listIterator()

    override fun listIterator(): MutableListIterator<E> = listIterator(0)

    override fun listIterator(index: Int): MutableListIterator<E> {
        if (index < 0 || index > size) throw IndexOutOfBoundsException()
        var expectedVersion = structuralVersion
        var cursor = index
        var lastReturned = -1
        return object : MutableListIterator<E> {
            private fun checkVersion() {
                if (structuralVersion != expectedVersion) throw ConcurrentModificationException()
            }

            override fun hasNext(): Boolean = cursor < size
            override fun hasPrevious(): Boolean = cursor > 0
            override fun nextIndex(): Int = cursor
            override fun previousIndex(): Int = cursor - 1

            override fun next(): E {
                checkVersion()
                if (!hasNext()) throw NoSuchElementException()
                lastReturned = cursor
                return get(cursor++)
            }

            override fun previous(): E {
                checkVersion()
                if (!hasPrevious()) throw NoSuchElementException()
                lastReturned = --cursor
                return get(cursor)
            }

            override fun remove() {
                if (lastReturned < 0) throw IllegalStateException()
                checkVersion()
                this@WorldTrackedArrayList.removeAt(lastReturned)
                if (lastReturned < cursor) cursor--
                lastReturned = -1
                expectedVersion = structuralVersion
            }

            override fun set(element: E) {
                if (lastReturned < 0) throw IllegalStateException()
                checkVersion()
                this@WorldTrackedArrayList[lastReturned] = element
            }

            override fun add(element: E) {
                checkVersion()
                this@WorldTrackedArrayList.add(cursor, element)
                cursor++
                lastReturned = -1
                expectedVersion = structuralVersion
            }
        }
    }

    @kotlin.jvm.JvmSynthetic
    fun liveView(): List<E> = worldPlatformUnmodifiableList(ReadOnlyView(0, null, null))

    private inner class ReadOnlyView(
        private val offset: Int,
        private val fixedSize: Int?,
        private val expectedVersion: Int?
    ) : AbstractMutableList<E>() {
        private fun checkVersion() {
            if (expectedVersion != null && structuralVersion != expectedVersion) {
                throw ConcurrentModificationException()
            }
        }

        override val size: Int
            get() {
                checkVersion()
                return fixedSize ?: backing.size
            }

        override fun get(index: Int): E {
            checkVersion()
            if (index < 0 || index >= size) throw IndexOutOfBoundsException()
            return backing[offset + index]
        }

        override fun subList(fromIndex: Int, toIndex: Int): MutableList<E> {
            checkVersion()
            if (fromIndex < 0 || toIndex > size || fromIndex > toIndex) {
                throw IndexOutOfBoundsException()
            }
            return ReadOnlyView(offset + fromIndex, toIndex - fromIndex, structuralVersion)
        }

        override fun set(index: Int, element: E): E = throw UnsupportedOperationException()
        override fun add(index: Int, element: E): Unit = throw UnsupportedOperationException()
        override fun removeAt(index: Int): E = throw UnsupportedOperationException()
        override fun clear(): Unit = throw UnsupportedOperationException()
        override fun addAll(elements: Collection<E>): Boolean = throw UnsupportedOperationException()
        override fun addAll(index: Int, elements: Collection<E>): Boolean = throw UnsupportedOperationException()
        override fun removeAll(elements: Collection<E>): Boolean = throw UnsupportedOperationException()
        override fun retainAll(elements: Collection<E>): Boolean = throw UnsupportedOperationException()

        fun sort(comparator: Comparator<in E>?): Unit = throw UnsupportedOperationException()

        override fun iterator(): MutableIterator<E> = listIterator()
        override fun listIterator(): MutableListIterator<E> = listIterator(0)

        override fun listIterator(index: Int): MutableListIterator<E> {
            if (index < 0 || index > size) throw IndexOutOfBoundsException()
            val iteratorVersion = structuralVersion
            var cursor = index
            return object : MutableListIterator<E> {
                override fun hasNext(): Boolean = cursor < size
                override fun hasPrevious(): Boolean = cursor > 0
                override fun nextIndex(): Int = cursor
                override fun previousIndex(): Int = cursor - 1

                override fun next(): E {
                    if (structuralVersion != iteratorVersion) throw ConcurrentModificationException()
                    if (!hasNext()) throw NoSuchElementException()
                    return get(cursor++)
                }

                override fun previous(): E {
                    if (structuralVersion != iteratorVersion) throw ConcurrentModificationException()
                    if (!hasPrevious()) throw NoSuchElementException()
                    return get(--cursor)
                }

                override fun remove(): Unit = throw UnsupportedOperationException()
                override fun set(element: E): Unit = throw UnsupportedOperationException()
                override fun add(element: E): Unit = throw UnsupportedOperationException()
            }
        }
    }
}
