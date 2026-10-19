/*
 * Copyright (c) 2010-2024 William Bittle  http://www.dyn4j.org/
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without modification, are permitted
 * provided that the following conditions are met:
 *
 *   * Redistributions of source code must retain the above copyright notice, this list of conditions
 *     and the following disclaimer.
 *   * Redistributions in binary form must reproduce the above copyright notice, this list of conditions
 *     and the following disclaimer in the documentation and/or other materials provided with the
 *     distribution.
 *   * Neither the name of the copyright holder nor the names of its contributors may be used to endorse or
 *     promote products derived from this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR
 * IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
 * FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
 * CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
 * DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 * DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER
 * IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT
 * OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */
package org.dyn4j

import kotlin.math.abs
import kotlin.math.ln
import kotlin.math.max

open class AVLTree<E : Comparable<E>> : BinarySearchTree<E> {
    private var root: BinarySearchTreeNode<E>? = null
    private var size: Int = 0

    override fun insert(comparable: E?): Boolean {
        if (comparable == null) return false
        return insert(BinarySearchTreeNode(comparable))
    }

    override fun remove(comparable: E?): Boolean {
        if (comparable == null || root == null) return false
        return remove(root, comparable) != null
    }

    override fun removeMinimum(): E? = removeMinimum(root)?.comparable
    override fun removeMaximum(): E? = removeMaximum(root)?.comparable
    override fun getMinimum(): E? = getMinimum(root)?.comparable
    override fun getMaximum(): E? = getMaximum(root)?.comparable
    override fun contains(comparable: E?): Boolean = comparable != null && contains(root, comparable) != null

    override fun <T : BinarySearchTreeSearchCriteria<E>> search(criteria: T?): T? {
        var node = root
        while (node != null) {
            node = when (criteria!!.evaluate(node.comparable).coerceIn(-1, 1)) {
                -1 -> node.left
                1 -> node.right
                else -> break
            }
        }
        return criteria
    }

    override fun getRoot(): E? = root?.comparable
    override fun clear() { root = null; size = 0 }
    override fun isEmpty(): Boolean = root == null
    override fun getHeight(): Int = getHeight(root)
    override fun size(): Int = size
    override fun isSelfBalancing(): Boolean = true
    override fun iterator(): MutableIterator<E> = inOrderIterator()
    override fun tailIterator(from: E?): MutableIterator<E> = BinarySearchTreeIterator(root, from, null)
    override fun headIterator(to: E?): MutableIterator<E> = BinarySearchTreeIterator(root, null, to)
    override fun subsetIterator(from: E?, to: E?): MutableIterator<E> = BinarySearchTreeIterator(root, from, to)
    override fun inOrderIterator(): MutableIterator<E> = BinarySearchTreeIterator(root, true)
    override fun reverseOrderIterator(): MutableIterator<E> = BinarySearchTreeIterator(root, false)
    override fun toString(): String = inOrderIterator().asSequence().joinToString(",", "BinarySearchTree[", "]")
    override fun isBalanced(): Boolean = isBalanced(root)
    override fun isValid(): Boolean = isValid(root) && isUnderHeightLimit()

    open fun isUnderHeightLimit(): Boolean {
        if (size <= 1) return true
        val height = getHeight()
        if (size <= 3 && height == 2) return true
        if (size == 4 && height == 3) return true
        val goldenRatio = (1.0 + kotlin.math.sqrt(5.0)) / 2.0
        val logBase2 = ln(2.0)
        val log2GoldenRatio = ln(goldenRatio) / logBase2
        return height <= (ln(size.toDouble()) / logBase2) * (1.0 / log2GoldenRatio)
    }

    override fun print() { print(root) }

    open fun print(node: BinarySearchTreeNode<E>?) {
        val height = getHeight(node)
        val rows = Array(height) { arrayOfNulls<BinarySearchTreeNode<E>>(1 shl it) }
        fun fill(node: BinarySearchTreeNode<E>?, row: Int, column: Int) {
            if (node == null) return
            rows[row][column] = node
            if (node.left != null) fill(node.left, row + 1, column * 2)
            if (node.right != null) fill(node.right, row + 1, column * 2 + 1)
        }
        rows[0][0] = node
        fill(node, 0, 0)
        val spacer = "      "
        for (row in rows.indices) {
            val offset = (1 shl (height - row - 1)) - 1
            val line = StringBuilder(spacer.repeat(offset))
            for (value in rows[row]) {
                line.append("[").append((value?.toString() ?: "null").padStart(4)).append("]")
                line.append(spacer.repeat(offset * 2 + 1))
            }
            println(line)
        }
        println()
    }

    open fun getMinimum(start: BinarySearchTreeNode<E>?): BinarySearchTreeNode<E>? {
        var node = start ?: return null
        while (node.left != null) node = node.left!!
        return node
    }

    open fun getMaximum(start: BinarySearchTreeNode<E>?): BinarySearchTreeNode<E>? {
        var node = start ?: return null
        while (node.right != null) node = node.right!!
        return node
    }

    open fun removeMinimum(start: BinarySearchTreeNode<E>?): BinarySearchTreeNode<E>? {
        val node = getMinimum(start) ?: return null
        remove(node)
        return node
    }

    open fun removeMaximum(start: BinarySearchTreeNode<E>?): BinarySearchTreeNode<E>? {
        val node = getMaximum(start) ?: return null
        remove(node)
        return node
    }

    open fun getHeight(node: BinarySearchTreeNode<E>?): Int =
        if (node == null) 0 else 1 + max(getHeight(node.left), getHeight(node.right))

    open fun size(node: BinarySearchTreeNode<E>?): Int =
        if (node == null) 0 else 1 + size(node.left) + size(node.right)

    open fun get(comparable: E?): BinarySearchTreeNode<E>? =
        if (comparable == null) null else contains(root, comparable)

    open fun insert(item: BinarySearchTreeNode<E>): Boolean {
        val start = root
        if (start == null) { root = item; size++; return true }
        return insert(item, start)
    }

    open fun rotateLeft(node: BinarySearchTreeNode<E>): BinarySearchTreeNode<E> {
        val parent = node.parent
        val right = node.right!!
        val rightLeft = right.left
        node.parent = right
        node.right = rightLeft
        right.left = node
        right.parent = parent
        rightLeft?.parent = node
        if (parent == null) root = right
        else if (parent.left === node) parent.left = right
        else if (parent.right === node) parent.right = right
        return right
    }

    open fun rotateRight(node: BinarySearchTreeNode<E>): BinarySearchTreeNode<E> {
        val parent = node.parent
        val left = node.left!!
        val leftRight = left.right
        node.parent = left
        node.left = leftRight
        left.right = node
        left.parent = parent
        leftRight?.parent = node
        if (parent == null) root = left
        else if (parent.left === node) parent.left = left
        else if (parent.right === node) parent.right = left
        return left
    }

    open fun getBalance(node: BinarySearchTreeNode<E>?): Int =
        if (node == null) 0 else getHeight(node.left) - getHeight(node.right)

    open fun insert(item: BinarySearchTreeNode<E>, start: BinarySearchTreeNode<E>): Boolean {
        var node: BinarySearchTreeNode<E> = start
        while (true) {
            val difference = item.compareTo(node)
            if (difference < 0) {
                val left = node.left
                if (left == null) { node.left = item; item.parent = node; break }
                node = left
            } else if (difference > 0) {
                val right = node.right
                if (right == null) { node.right = item; item.parent = node; break }
                node = right
            } else throw IllegalArgumentException("Cannot insert multiple of the same value: ${item.comparable}")
        }
        size++
        var ancestor: BinarySearchTreeNode<E>? = node
        while (ancestor != null) {
            if (getHeight(ancestor) > 2) {
                val balance = getBalance(ancestor)
                if (balance > 1) {
                    val leftDifference = item.comparable.compareTo(ancestor.left!!.comparable)
                    if (leftDifference < 0) rotateRight(ancestor)
                    else if (leftDifference > 0) { rotateLeft(ancestor.left!!); rotateRight(ancestor) }
                } else if (balance < -1) {
                    val rightDifference = item.comparable.compareTo(ancestor.right!!.comparable)
                    if (rightDifference > 0) rotateLeft(ancestor)
                    else if (rightDifference < 0) { rotateRight(ancestor.right!!); rotateLeft(ancestor) }
                }
            }
            ancestor = ancestor.parent
        }
        return true
    }

    open fun remove(start: BinarySearchTreeNode<E>?, comparable: E): BinarySearchTreeNode<E>? {
        val node = contains(start, comparable) ?: return null
        remove(node)
        return node
    }

    open fun remove(original: BinarySearchTreeNode<E>) {
        var node = original
        val isLeftChild = node.isLeftChild()
        if (node.left != null && node.right != null) {
            val minimum = getMinimum(node.right)!!
            val minimumRight = minimum.right
            val minimumParent = minimum.parent!!
            val nodeParent = node.parent
            val nodeLeft = node.left!!
            val nodeRight = node.right!!
            if (minimum === node.right) {
                minimum.parent = nodeParent
                minimum.left = nodeLeft
                nodeLeft.parent = minimum
                if (nodeParent == null) root = minimum
                else if (isLeftChild) nodeParent.left = minimum
                else nodeParent.right = minimum
                node.left = null; node.right = null; node.parent = null
                node = minimum
            } else {
                minimum.left = nodeLeft
                minimum.parent = nodeParent
                minimum.right = nodeRight
                nodeRight.parent = minimum
                nodeLeft.parent = minimum
                if (nodeParent == null) root = minimum
                else if (isLeftChild) nodeParent.left = minimum
                else nodeParent.right = minimum
                minimumParent.left = minimumRight
                minimumRight?.parent = minimumParent
                node.left = null; node.right = null; node.parent = null
                node = minimumParent
            }
        } else if (node.left != null) {
            val replacement = node.left!!
            if (node === root) root = replacement
            else if (isLeftChild) node.parent!!.left = replacement
            else node.parent!!.right = replacement
            replacement.parent = node.parent
            node = replacement
        } else if (node.right != null) {
            val replacement = node.right!!
            if (node === root) root = replacement
            else if (isLeftChild) node.parent!!.left = replacement
            else node.parent!!.right = replacement
            replacement.parent = node.parent
            node = replacement
        } else {
            if (node === root) root = null
            else if (isLeftChild) node.parent!!.left = null
            else node.parent!!.right = null
            node = node.parent ?: run { size--; return }
        }
        size--
        var ancestor: BinarySearchTreeNode<E>? = node
        while (ancestor != null) {
            if (getHeight(ancestor) > 2) {
                val balance = getBalance(ancestor)
                if (balance > 1) {
                    if (getBalance(ancestor.left) >= 0) rotateRight(ancestor)
                    else { rotateLeft(ancestor.left!!); rotateRight(ancestor) }
                } else if (balance < -1) {
                    if (getBalance(ancestor.right) <= 0) rotateLeft(ancestor)
                    else { rotateRight(ancestor.right!!); rotateLeft(ancestor) }
                }
            }
            ancestor = ancestor.parent
        }
    }

    open fun contains(start: BinarySearchTreeNode<E>?, comparable: E): BinarySearchTreeNode<E>? {
        var node = start
        while (node != null) {
            val difference = comparable.compareTo(node.comparable)
            if (difference == 0) return if (node.comparable == comparable) node else null
            node = if (difference < 0) node.left else node.right
        }
        return null
    }

    open fun isBalanced(node: BinarySearchTreeNode<E>?): Boolean = node == null ||
        (abs(getBalance(node)) <= 1 && isBalanced(node.left) && isBalanced(node.right))

    open fun isValid(node: BinarySearchTreeNode<E>?): Boolean {
        if (node == null) return true
        val left = node.left
        val right = node.right
        val leftValid = left == null ||
            (left.comparable.compareTo(node.comparable) < 0 && left.parent === node && isValid(left))
        val rightValid = right == null ||
            (right.comparable.compareTo(node.comparable) > 0 && right.parent === node && isValid(right))
        return leftValid && rightValid
    }
}
