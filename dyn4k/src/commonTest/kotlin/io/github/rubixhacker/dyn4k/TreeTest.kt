package io.github.rubixhacker.dyn4k

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertSame
import kotlin.test.assertTrue

class TreeTest {
    @Test
    fun insertsAndTraversesInSortedOrder() {
        val tree: BinarySearchTree<Int> = AVLTree()
        val baselineObject: org.dyn4j.BinarySearchTree<Int> = tree
        assertSame(tree, baselineObject)
        listOf(4, 2, 6, 1, 3, 5, 7).forEach { tree.insert(it) }
        assertEquals(listOf(1, 2, 3, 4, 5, 6, 7), tree.toList())
        assertEquals(3, tree.getHeight())
        assertTrue(tree.isValid())
    }

    @Test
    fun searchAndRangeIteratorsFollowBaseline() {
        val tree = AVLTree<Int>()
        listOf(4, 2, 6, 1, 3, 5, 7).forEach { tree.insert(it) }
        val visited = mutableListOf<Int>()
        val criteria = BinarySearchTreeSearchCriteria<Int> { value ->
            visited += value
            5.compareTo(value)
        }
        assertTrue(tree.search(criteria) === criteria)
        assertEquals(listOf(4, 6, 5), visited)
        val subset = tree.subsetIterator(3, 5)
        val values = mutableListOf<Int>()
        while (subset.hasNext()) values += subset.next()
        assertEquals(listOf(3, 4, 5), values)
        assertFailsWith<UnsupportedOperationException> { subset.remove() }
    }

    @Test
    fun removesAndKeepsTreeBalanced() {
        val tree = AVLTree<Int>()
        (1..40).forEach { tree.insert(it) }
        (2..40 step 2).forEach { assertTrue(tree.remove(it)); assertTrue(tree.isValid()) }
        assertEquals((1..40 step 2).toList(), tree.toList())
        assertEquals(1, tree.removeMinimum())
        assertEquals(39, tree.removeMaximum())
    }

    @Test
    fun referenceAndVersionHaveBaselineValues() {
        val reference = Reference("one")
        reference.value = "two"
        assertEquals("two", reference.toString())
        assertEquals("6.0.0", Version.getVersion())
        assertEquals(listOf(6, 0, 0), Version.getVersionNumbers().toList())
    }
}
