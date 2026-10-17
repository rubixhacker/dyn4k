/*
 * Copyright (c) 2010-2020 William Bittle  http://www.dyn4j.org/
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

class BinarySearchTreeIterator<E : Comparable<E>> private constructor(
    private val root: BinarySearchTreeNode<E>?,
    private val from: E?,
    private val to: E?,
    private val inOrder: Boolean
) : MutableIterator<E> {
    constructor(root: BinarySearchTreeNode<E>?) : this(root, null, null, true)
    constructor(root: BinarySearchTreeNode<E>?, inOrder: Boolean) : this(root, null, null, inOrder)
    constructor(root: BinarySearchTreeNode<E>?, from: E?, to: E?) : this(root, from, to, true)

    private val stack = mutableListOf<BinarySearchTreeNode<E>>()

    init {
        if (inOrder) {
            if (from == null) pushLeft(root) else pushLeftFrom(from)
        } else pushRight(root)
    }

    private fun pushLeftFrom(from: E) {
        var node = root
        while (node != null) {
            val cmp = from.compareTo(node.comparable)
            when {
                cmp < 0 -> { stack.add(node); node = node.left }
                cmp > 0 -> node = node.right
                else -> { stack.add(node); break }
            }
        }
    }

    private fun pushLeft(start: BinarySearchTreeNode<E>?) {
        var node = start
        while (node != null) {
            if (to == null || to.compareTo(node.comparable) >= 0) stack.add(node)
            node = node.left
        }
    }

    private fun pushRight(start: BinarySearchTreeNode<E>?) {
        var node = start
        while (node != null) { stack.add(node); node = node.right }
    }

    override fun hasNext(): Boolean = stack.isNotEmpty()

    override fun next(): E {
        if (stack.isEmpty()) throw NoSuchElementException()
        val node = stack.removeAt(stack.lastIndex)
        if (inOrder) pushLeft(node.right) else pushRight(node.left)
        return node.comparable
    }

    override fun remove(): Unit = throw UnsupportedOperationException()
}
