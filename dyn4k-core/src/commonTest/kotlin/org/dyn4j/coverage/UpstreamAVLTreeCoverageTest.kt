package org.dyn4j

import de.infix.testBalloon.framework.core.testSuite
import kotlin.random.Random
import kotlin.test.*

val UpstreamAVLTreeCoverageTest by testSuite {
    test("insertDuplicate") { UpstreamAVLTreeCoverageTestFixture().run { insertDuplicate() } }
    test("insertSequential") { UpstreamAVLTreeCoverageTestFixture().run { insertSequential() } }
    test("insertInOrder") { UpstreamAVLTreeCoverageTestFixture().run { insertInOrder() } }
    test("insertReverseOrder") { UpstreamAVLTreeCoverageTestFixture().run { insertReverseOrder() } }
    test("insertReverseOrderSorted") { UpstreamAVLTreeCoverageTestFixture().run { insertReverseOrderSorted() } }
    test("insertShuffled") { UpstreamAVLTreeCoverageTestFixture().run { insertShuffled() } }
    test("sequentialRemoval") { UpstreamAVLTreeCoverageTestFixture().run { sequentialRemoval() } }
    test("removeRoot") { UpstreamAVLTreeCoverageTestFixture().run { removeRoot() } }
    test("removeRootNodeAndReplaceWithRight") { UpstreamAVLTreeCoverageTestFixture().run { removeRootNodeAndReplaceWithRight() } }
    test("random") { UpstreamAVLTreeCoverageTestFixture().run { random() } }
    test("remove") { UpstreamAVLTreeCoverageTestFixture().run { remove() } }
    test("removeNotFound") { UpstreamAVLTreeCoverageTestFixture().run { removeNotFound() } }
    test("getDepth") { UpstreamAVLTreeCoverageTestFixture().run { getDepth() } }
    test("getMinimum") { UpstreamAVLTreeCoverageTestFixture().run { getMinimum() } }
    test("getMaximum") { UpstreamAVLTreeCoverageTestFixture().run { getMaximum() } }
    test("isEmpty") { UpstreamAVLTreeCoverageTestFixture().run { isEmpty() } }
    test("clear") { UpstreamAVLTreeCoverageTestFixture().run { clear() } }
    test("contains") { UpstreamAVLTreeCoverageTestFixture().run { contains() } }
    test("get") { UpstreamAVLTreeCoverageTestFixture().run { get() } }
    test("size") { UpstreamAVLTreeCoverageTestFixture().run { size() } }
    test("iterator") { UpstreamAVLTreeCoverageTestFixture().run { iterator() } }
    test("tailIterator") { UpstreamAVLTreeCoverageTestFixture().run { tailIterator() } }
    test("headIterator") { UpstreamAVLTreeCoverageTestFixture().run { headIterator() } }
    test("subsetIterator") { UpstreamAVLTreeCoverageTestFixture().run { subsetIterator() } }
    test("tailIteratorMissing") { UpstreamAVLTreeCoverageTestFixture().run { tailIteratorMissing() } }
    test("headIteratorMissing") { UpstreamAVLTreeCoverageTestFixture().run { headIteratorMissing() } }
    test("subsetIteratorMissing") { UpstreamAVLTreeCoverageTestFixture().run { subsetIteratorMissing() } }
    test("goncaloMarquesIssue") { UpstreamAVLTreeCoverageTestFixture().run { goncaloMarquesIssue() } }
    test("insertSimple") { UpstreamAVLTreeCoverageTestFixture().run { insertSimple() } }
}

private class UpstreamAVLTreeCoverageTestFixture  {
    private val VALUES = intArrayOf(10, 3, -3, 4, 0, 1, 11, 19, 6, -1, 2, 9, -4, -8, 14, -5, 7, 31, 20, 8, -15, -11, -6, 16, -40)
    private val tree = AVLTree<Int>().apply { VALUES.forEach { insert(it) } }
    private val list = VALUES.toMutableList()

fun insertDuplicate() {
        assertFailsWith<IllegalArgumentException> {
            tree.insert(3)
        }
    }

fun insertSequential() {
        var tree = AVLTree<Int>()
        for (i in 0 until VALUES.size) {
            tree.insert(VALUES[i])
            assertEquals(i + 1, tree.size())
            assertTrue(tree.isBalanced())
            assertTrue(tree.isValid())
            assertTrue(tree.contains(VALUES[i]))
        }
    }

fun insertInOrder() {
        var tree = AVLTree<Int>()
        list.sort()
        for (i in 0 until list.size) {
            tree.insert(list[i])
            assertEquals(i + 1, tree.size())
            assertTrue(tree.isBalanced())
            assertTrue(tree.isValid())
            assertTrue(tree.contains(list[i]))
        }
    }

fun insertReverseOrder() {
        var tree = AVLTree<Int>()
        list.reverse()
        for (i in 0 until list.size) {
            tree.insert(list[i])
            assertEquals(i + 1, tree.size())
            assertTrue(tree.isBalanced())
            assertTrue(tree.isValid())
            assertTrue(tree.contains(list[i]))
        }
    }

fun insertReverseOrderSorted() {
        var tree = AVLTree<Int>()
        list.sort()
        list.reverse()
        for (i in 0 until list.size) {
            tree.insert(list[i])
            assertEquals(i + 1, tree.size())
            assertTrue(tree.isBalanced())
            assertTrue(tree.isValid())
            assertTrue(tree.contains(list[i]))
        }
    }

fun insertShuffled() {
        var tree = AVLTree<Int>()
        val javaSeed17Order = intArrayOf(
            7, -11, 10, -40, -3, 2, -15, 1, 0, -6, 11, -1, 9, 31, -5, 8, 14, 4, 20, -8, 19, 16, 6, -4, 3
        )
        for (i in javaSeed17Order.indices) {
            tree.insert(javaSeed17Order[i])
            assertEquals(i + 1, tree.size())
            assertTrue(tree.isBalanced())
            assertTrue(tree.isValid())
            assertTrue(tree.contains(javaSeed17Order[i]))
        }
    }

fun sequentialRemoval() {
        tree.remove(4)
        assertEquals(VALUES.size - 1, tree.size())
        assertTrue(tree.isBalanced())
        assertTrue(tree.isValid())
        assertFalse(tree.contains(4))
        tree.insert(4)
        assertEquals(VALUES.size, tree.size())
        assertTrue(tree.isBalanced())
        assertTrue(tree.isValid())
        assertTrue(tree.contains(4))
        tree.remove(-11)
        assertEquals(VALUES.size - 1, tree.size())
        assertTrue(tree.isBalanced())
        assertTrue(tree.isValid())
        assertFalse(tree.contains(-11))
        tree.remove(-6)
        assertEquals(VALUES.size - 2, tree.size())
        assertTrue(tree.isBalanced())
        assertTrue(tree.isValid())
        assertFalse(tree.contains(-6))
        tree.remove(9)
        assertEquals(VALUES.size - 3, tree.size())
        assertTrue(tree.isBalanced())
        assertTrue(tree.isValid())
        assertFalse(tree.contains(9))
        tree.remove(10)
        assertEquals(VALUES.size - 4, tree.size())
        assertTrue(tree.isBalanced())
        assertTrue(tree.isValid())
        assertFalse(tree.contains(10))
        tree.remove(16)
        assertEquals(VALUES.size - 5, tree.size())
        assertTrue(tree.isBalanced())
        assertTrue(tree.isValid())
        assertFalse(tree.contains(16))
        tree.remove(-5)
        assertEquals(VALUES.size - 6, tree.size())
        assertTrue(tree.isBalanced())
        assertTrue(tree.isValid())
        assertFalse(tree.contains(-5))
        tree.remove(6)
        assertEquals(VALUES.size - 7, tree.size())
        assertTrue(tree.isBalanced())
        assertTrue(tree.isValid())
        assertFalse(tree.contains(6))
        tree.remove(3)
        assertEquals(VALUES.size - 8, tree.size())
        assertTrue(tree.isBalanced())
        assertTrue(tree.isValid())
        assertFalse(tree.contains(3))
    }

fun removeRoot() {
        tree.remove(19)
        assertEquals(VALUES.size - 1, tree.size())
        assertTrue(tree.isBalanced())
        assertTrue(tree.isValid())
        assertFalse(tree.contains(19))
        tree.remove(3)
        assertEquals(VALUES.size - 2, tree.size())
        assertTrue(tree.isBalanced())
        assertTrue(tree.isValid())
        assertFalse(tree.contains(3))
    }

fun removeRootNodeAndReplaceWithRight() {
        tree.remove(3)
        tree.remove(-8)
        tree.remove(11)
        tree.remove(6)
        tree.remove(14)
        tree.remove(3)
        tree.remove(14)
        tree.remove(-40)
        tree.remove(31)
        tree.remove(8)
        tree.remove(20)
        tree.remove(31)
        tree.remove(-3)
        tree.remove(0)
        tree.remove(20)
        tree.remove(-4)
        tree.remove(-1)
        tree.remove(-6)
        tree.remove(31)
        tree.remove(-4)
        tree.remove(0)
        tree.remove(10)
        tree.remove(-15)
        tree.remove(20)
        tree.remove(20)
        tree.remove(-1)
        tree.remove(-11)
        tree.remove(3)
        tree.remove(14)
        tree.remove(-1)
        tree.remove(11)
        tree.remove(4)
        tree.remove(-1)
        tree.remove(8)
        tree.remove(9)
        tree.remove(9)
        tree.remove(7)
        assertEquals(5, tree.size())
        assertTrue(tree.isBalanced())
        assertTrue(tree.isValid())
        assertFalse(tree.contains(7))
    }

fun random() {
        for (n in 0 until 1000) {
            var tree = AVLTree<Int>()
            for (i in 0 until VALUES.size) {
                tree.insert(VALUES[i])
                assertEquals(i + 1, tree.size())
                assertTrue(tree.isBalanced())
                assertTrue(tree.isValid())
                assertTrue(tree.contains(VALUES[i]))
            }

            var r = Random.Default
            while (tree.size() > 0) {
                var index = r.nextInt(VALUES.size)
                var value = VALUES[index]
                tree.remove(value)
                assertTrue(tree.isBalanced())
                assertTrue(tree.isValid())
                assertFalse(tree.contains(value))
            }
        }
    }

fun remove() {
        assertNotNull(tree.remove(-3))
        assertFalse(tree.contains(-3))
        assertTrue(tree.contains(-4))
        assertTrue(tree.contains(0))
        assertTrue(tree.contains(1))
        assertTrue(tree.contains(2))
        assertTrue(tree.contains(3))
        var size = tree.size()
        tree.removeMinimum()
        assertTrue(tree.isBalanced())
        assertTrue(tree.isValid())
        assertFalse(tree.contains(-40))
        assertEquals(size - 1, tree.size())
        var node = tree.get(10)
        tree.removeMinimum(node)
        assertTrue(tree.isBalanced())
        assertTrue(tree.isValid())
        assertFalse(tree.contains(4))
        assertEquals(size - 2, tree.size())
        tree.removeMaximum()
        assertTrue(tree.isBalanced())
        assertTrue(tree.isValid())
        assertFalse(tree.contains(31))
        assertEquals(size - 3, tree.size())
        node = tree.get(0)
        tree.removeMaximum(node)
        assertTrue(tree.isBalanced())
        assertTrue(tree.isValid())
        assertFalse(tree.contains(2))
        assertEquals(size - 4, tree.size())
    }

fun removeNotFound() {
        assertFalse(tree.remove(44))
    }

fun getDepth() {
        assertEquals(5, tree.getHeight())
        var node = tree.get(-3)
        assertEquals(2, tree.getHeight(node))
    }

fun getMinimum() {
        assertEquals(-40, tree.getMinimum())
        var node = tree.get(10)
        assertEquals(4, tree.getMinimum(node)!!.comparable)
        node = tree.get(1)
        assertEquals(1, tree.getMinimum(node)!!.comparable)
    }

fun getMaximum() {
        assertEquals(31, tree.getMaximum())
        var node = tree.get(-3)
        assertEquals(-1, tree.getMaximum(node)!!.comparable)
        node = tree.get(6)
        assertEquals(9, tree.getMaximum(node)!!.comparable)
    }

fun isEmpty() {
        assertFalse(tree.isEmpty())
        var test = AVLTree<Int>()
        assertTrue(test.isEmpty())
    }

fun clear() {
        assertFalse(tree.isEmpty())
        assertEquals(VALUES.size, tree.size())
        tree.clear()
        assertTrue(tree.isEmpty())
        assertEquals(0, tree.size())
        assertEquals(0, tree.getHeight())
        assertEquals(null, tree.getRoot())
    }

fun contains() {
        assertTrue(tree.contains(9))
        assertFalse(tree.contains(-60))
    }

fun get() {
        assertNotNull(tree.get(-3))
        assertNull(tree.get(45))
    }

fun size() {
        assertEquals(VALUES.size, tree.size())
        var node = tree.get(-3)
        assertEquals(3, tree.size(node))
    }

fun iterator() {
        var it = tree.inOrderIterator()
        var last = Int.MIN_VALUE
        while (it.hasNext()) {
            var i = it.next()
            if (i < last) {
                fail()
            }
            last = i
        }

        it = tree.reverseOrderIterator()
        last = Int.MAX_VALUE
        while (it.hasNext()) {
            var i = it.next()
            if (i > last) {
                fail()
            }
            last = i
        }
    }

fun tailIterator() {
        var it = tree.tailIterator(0)
        var last = Int.MIN_VALUE
        var n = 0
        while (it.hasNext()) {
            var i = it.next()
            if (i < last) {
                fail()
            }
            last = i
            n++
        }
        assertEquals(16, n)
    }

fun headIterator() {
        var it = tree.headIterator(6)
        var last = Int.MIN_VALUE
        var n = 0
        while (it.hasNext()) {
            var i = it.next()
            if (i < last) {
                fail()
            }
            last = i
            n++
        }
        assertEquals(15, n)
    }

fun subsetIterator() {
        var it = tree.subsetIterator(1, 6)
        var last = Int.MIN_VALUE
        var n = 0
        while (it.hasNext()) {
            var i = it.next()
            if (i < last) {
                fail()
            }
            last = i
            n++
        }
        assertEquals(5, n)
    }

fun tailIteratorMissing() {
        var it = tree.tailIterator(5)
        var last = Int.MIN_VALUE
        var n = 0
        while (it.hasNext()) {
            var i = it.next()
            if (i < last) {
                fail()
            }
            last = i
            n++
        }
        assertEquals(11, n)
    }

fun headIteratorMissing() {
        var it = tree.headIterator(5)
        var last = Int.MIN_VALUE
        var n = 0
        while (it.hasNext()) {
            var i = it.next()
            if (i < last) {
                fail()
            }
            last = i
            n++
        }
        assertEquals(14, n)
    }

fun subsetIteratorMissing() {
        var it = tree.subsetIterator(-2, 5)
        var last = Int.MIN_VALUE
        var n = 0
        while (it.hasNext()) {
            var i = it.next()
            if (i < last) {
                fail()
            }
            last = i
            n++
        }
        assertEquals(6, n)
    }

fun goncaloMarquesIssue() {
        var tree = AVLTree<Int>()
        tree.insert(3)
        tree.insert(1)
        tree.insert(2)
        assertTrue(tree.isBalanced())
        assertTrue(tree.isValid())
        assertEquals(2, tree.getHeight())
    }

fun insertSimple() {
        var tree = AVLTree<Int>()
        tree.insert(5)
        tree.insert(1)
        tree.insert(2)
        tree.insert(3)
        assertTrue(tree.isBalanced())
        assertTrue(tree.isValid())
        assertEquals(3, tree.getHeight())
    }
}
