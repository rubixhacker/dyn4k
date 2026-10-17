package org.dyn4j.world

internal class WorldTrackedArrayList<E>(initialCapacity: Int = 10) : AbstractMutableList<E>(), RandomAccess {
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

    override fun subList(fromIndex: Int, toIndex: Int): MutableList<E> {
        checkSubListRange(fromIndex, toIndex, size)
        return MutableSubList(null, fromIndex, toIndex - fromIndex, structuralVersion)
    }

    private fun checkSubListRange(fromIndex: Int, toIndex: Int, listSize: Int) {
        if (fromIndex < 0 || toIndex > listSize) throw IndexOutOfBoundsException()
        if (fromIndex > toIndex) throw IllegalArgumentException()
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

    private inner class MutableSubList(
        private val parent: MutableSubList?,
        private val offset: Int,
        private var viewSize: Int,
        private var expectedVersion: Int
    ) : AbstractMutableList<E>(), RandomAccess {
        private fun checkVersion() {
            if (structuralVersion != expectedVersion) throw ConcurrentModificationException()
        }

        private fun recordStructuralChange(delta: Int) {
            var current: MutableSubList? = this
            while (current != null) {
                current.viewSize += delta
                current.expectedVersion = structuralVersion
                current = current.parent
            }
        }

        override val size: Int
            get() {
                checkVersion()
                return viewSize
            }

        override fun get(index: Int): E {
            checkVersion()
            if (index < 0 || index >= viewSize) throw IndexOutOfBoundsException()
            return backing[offset + index]
        }

        override fun set(index: Int, element: E): E {
            checkVersion()
            if (index < 0 || index >= viewSize) throw IndexOutOfBoundsException()
            return this@WorldTrackedArrayList.set(offset + index, element)
        }

        override fun add(index: Int, element: E) {
            checkVersion()
            if (index < 0 || index > viewSize) throw IndexOutOfBoundsException()
            this@WorldTrackedArrayList.add(offset + index, element)
            recordStructuralChange(1)
        }

        override fun removeAt(index: Int): E {
            checkVersion()
            if (index < 0 || index >= viewSize) throw IndexOutOfBoundsException()
            val removed = this@WorldTrackedArrayList.removeAt(offset + index)
            recordStructuralChange(-1)
            return removed
        }

        override fun subList(fromIndex: Int, toIndex: Int): MutableList<E> {
            checkVersion()
            checkSubListRange(fromIndex, toIndex, viewSize)
            return MutableSubList(this, offset + fromIndex, toIndex - fromIndex, structuralVersion)
        }

        override fun iterator(): MutableIterator<E> = listIterator()
        override fun listIterator(): MutableListIterator<E> = listIterator(0)

        override fun listIterator(index: Int): MutableListIterator<E> {
            checkVersion()
            if (index < 0 || index > viewSize) throw IndexOutOfBoundsException()
            var iteratorVersion = structuralVersion
            var cursor = index
            var lastReturned = -1
            return object : MutableListIterator<E> {
                private fun checkIteratorVersion() {
                    if (structuralVersion != iteratorVersion) throw ConcurrentModificationException()
                }

                override fun hasNext(): Boolean = cursor < viewSize
                override fun hasPrevious(): Boolean = cursor > 0
                override fun nextIndex(): Int = cursor
                override fun previousIndex(): Int = cursor - 1

                override fun next(): E {
                    checkIteratorVersion()
                    if (!hasNext()) throw NoSuchElementException()
                    lastReturned = cursor
                    return get(cursor++)
                }

                override fun previous(): E {
                    checkIteratorVersion()
                    if (!hasPrevious()) throw NoSuchElementException()
                    lastReturned = --cursor
                    return get(cursor)
                }

                override fun remove() {
                    if (lastReturned < 0) throw IllegalStateException()
                    checkIteratorVersion()
                    this@MutableSubList.removeAt(lastReturned)
                    if (lastReturned < cursor) cursor--
                    lastReturned = -1
                    iteratorVersion = structuralVersion
                }

                override fun set(element: E) {
                    if (lastReturned < 0) throw IllegalStateException()
                    checkIteratorVersion()
                    this@MutableSubList[lastReturned] = element
                }

                override fun add(element: E) {
                    checkIteratorVersion()
                    this@MutableSubList.add(cursor, element)
                    cursor++
                    lastReturned = -1
                    iteratorVersion = structuralVersion
                }
            }
        }
    }

    private inner class ReadOnlyView(
        private val offset: Int,
        private val fixedSize: Int?,
        private val expectedVersion: Int?
    ) : AbstractMutableList<E>(), RandomAccess {
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
            checkSubListRange(fromIndex, toIndex, size)
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
