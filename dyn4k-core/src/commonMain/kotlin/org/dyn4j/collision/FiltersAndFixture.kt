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
package org.dyn4j.collision

import org.dyn4j.Copyable
import org.dyn4j.DataContainer
import org.dyn4j.runtimeClassName
import org.dyn4j.exception.ArgumentNullException
import org.dyn4j.geometry.Convex

interface Filter : Copyable<Filter> {
    fun isAllowed(filter: Filter?): Boolean

    companion object {
        @kotlin.jvm.JvmField val DEFAULT_FILTER: Filter = object : Filter {
            override fun isAllowed(filter: Filter?) = true
            override fun copy(): Filter = this
            override fun toString() = "DefaultFilter[]"
        }
    }
}

class CategoryFilter : Filter {
    @kotlin.jvm.JvmField protected val category: Long
    @kotlin.jvm.JvmField protected val mask: Long

    constructor() { category = 1L; mask = Long.MAX_VALUE }
    constructor(category: Long, mask: Long) { this.category = category; this.mask = mask }
    protected constructor(filter: CategoryFilter) : this(filter.category, filter.mask)

    override fun copy() = CategoryFilter(this)
    override fun isAllowed(filter: Filter?): Boolean = filter !is CategoryFilter ||
        (category and filter.mask) > 0L && (filter.category and mask) > 0L
    override fun equals(other: Any?) = other is CategoryFilter && category == other.category && mask == other.mask
    override fun hashCode(): Int {
        var hash = 17
        hash = hash * 31 + (category xor (category ushr 32)).toInt()
        hash = hash * 31 + (mask xor (mask ushr 32)).toInt()
        return hash
    }
    override fun toString() = "CategoryFilter[Category=$category|Mask=$mask]"
    open fun getCategory() = category
    open fun getMask() = mask
}

abstract class TypeFilter : Filter {
    override fun copy(): TypeFilter = this
    override fun isAllowed(filter: Filter?): Boolean = filter is TypeFilter &&
        (this::class.isInstance(filter) || filter::class.isInstance(this))
    override fun toString() = "TypeFilter[ClassName=${runtimeClassName(this)}]"
}

open class Fixture : DataContainer, Copyable<Fixture> {
    @kotlin.jvm.JvmField protected val shape: Convex
    @kotlin.jvm.JvmField protected var filter: Filter = Filter.DEFAULT_FILTER
    @kotlin.jvm.JvmField protected var sensor: Boolean = false
    @kotlin.jvm.JvmField protected var userData: Any? = null

    constructor(shape: Convex?) {
        this.shape = shape ?: throw ArgumentNullException("shape")
    }

    protected constructor(fixture: Fixture) {
        shape = fixture.shape.copy() as Convex
        filter = fixture.filter.copy()
        sensor = fixture.sensor
    }

    override fun copy() = Fixture(this)
    open fun getShape() = shape
    open fun getFilter() = filter
    open fun setFilter(filter: Filter?) { this.filter = filter ?: throw ArgumentNullException("filter") }
    open fun isSensor() = sensor
    open fun setSensor(flag: Boolean) { sensor = flag }
    override fun getUserData() = userData
    override fun setUserData(data: Any?) { userData = data }
    override fun toString() = "Fixture[HashCode=${hashCode()}|Shape=$shape|Filter=$filter|IsSensor=$sensor]"
}
