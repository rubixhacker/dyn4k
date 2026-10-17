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
package org.dyn4j.collision.narrowphase

import org.dyn4j.JvmFieldBridge
import org.dyn4j.exception.ArgumentNullException
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Transform

interface FallbackCondition : Comparable<FallbackCondition> {
    fun isMatch(convex1: Convex, convex2: Convex): Boolean
    fun getSortIndex(): Int
}

abstract class AbstractFallbackCondition(private val sortIndex: Int) : FallbackCondition {
    override fun compareTo(other: FallbackCondition): Int = getSortIndex() - other.getSortIndex()
    override fun getSortIndex() = sortIndex
}

abstract class TypedFallbackCondition : AbstractFallbackCondition {
    constructor() : super(0)
    constructor(sortIndex: Int) : super(sortIndex)
    override fun isMatch(convex1: Convex, convex2: Convex): Boolean =
        isMatch(runtimeConvexClass(convex1), runtimeConvexClass(convex2))
    abstract fun isMatch(type1: ConvexClass<out Convex>, type2: ConvexClass<out Convex>): Boolean
}

open class SingleTypedFallbackCondition : TypedFallbackCondition {
    private val type: ConvexClass<out Convex>?
    private val strict: Boolean
    constructor(type: ConvexClass<out Convex>?) : this(type, 0, true)
    constructor(type: ConvexClass<out Convex>?, sortIndex: Int) : this(type, sortIndex, true)
    constructor(type: ConvexClass<out Convex>?, strict: Boolean) : this(type, 0, strict)
    constructor(type: ConvexClass<out Convex>?, sortIndex: Int, strict: Boolean) : super(sortIndex) {
        this.type = type; this.strict = strict
    }
    override fun isMatch(type1: ConvexClass<out Convex>, type2: ConvexClass<out Convex>): Boolean {
        if (strict) return type == type1 || type == type2
        return convexClassAssignable(type!!, type1) || convexClassAssignable(type, type2)
    }
    open fun getType() = type
    open fun isStrict() = strict
    override fun toString() = "SingleTypedFallbackCondition[Type=${convexClassName(type!!)}|IsStrict=$strict]"
}

open class PairwiseTypedFallbackCondition : TypedFallbackCondition {
    private val type1: ConvexClass<out Convex>?
    private val strict1: Boolean
    private val type2: ConvexClass<out Convex>?
    private val strict2: Boolean

    constructor(type1: ConvexClass<out Convex>?, type2: ConvexClass<out Convex>?) :
        this(type1, true, type2, true, 0)
    constructor(type1: ConvexClass<out Convex>?, type2: ConvexClass<out Convex>?, sortIndex: Int) :
        this(type1, true, type2, true, sortIndex)
    constructor(type1: ConvexClass<out Convex>?, type2: ConvexClass<out Convex>?, strict: Boolean) :
        this(type1, strict, type2, strict, 0)
    constructor(type1: ConvexClass<out Convex>?, type2: ConvexClass<out Convex>?, strict: Boolean, sortIndex: Int) :
        this(type1, strict, type2, strict, sortIndex)
    constructor(type1: ConvexClass<out Convex>?, strict1: Boolean, type2: ConvexClass<out Convex>?, strict2: Boolean) :
        this(type1, strict1, type2, strict2, 0)
    constructor(type1: ConvexClass<out Convex>?, strict1: Boolean, type2: ConvexClass<out Convex>?, strict2: Boolean, sortIndex: Int) :
        super(sortIndex) {
        this.type1 = type1; this.strict1 = strict1; this.type2 = type2; this.strict2 = strict2
    }

    override fun isMatch(type1: ConvexClass<out Convex>, type2: ConvexClass<out Convex>): Boolean {
        val first = this.type1!!
        val second = this.type2!!
        return if (strict1) {
            if (strict2) (first == type1 && second == type2) || (first == type2 && second == type1)
            else (first == type1 && convexClassAssignable(second, type2)) ||
                (first == type2 && convexClassAssignable(second, type1))
        } else {
            if (strict2) (convexClassAssignable(first, type1) && second == type2) ||
                (convexClassAssignable(first, type2) && second == type1)
            else (convexClassAssignable(first, type1) && convexClassAssignable(second, type2)) ||
                (convexClassAssignable(first, type2) && convexClassAssignable(second, type1))
        }
    }
    open fun getType1() = type1
    open fun getType2() = type2
    open fun isStrict1() = strict1
    open fun isStrict2() = strict2
    override fun toString() = "PairwiseTypedFallbackCondition[Type1=${convexClassName(type1!!)}|IsStrict1=$strict1|Type2=${convexClassName(type2!!)}|IsStrict2=$strict2]"
}

open class FallbackNarrowphaseDetector : NarrowphaseDetector {
    @kotlin.jvm.JvmField protected val primaryNarrowphaseDetector: NarrowphaseDetector
    @kotlin.jvm.JvmField protected val fallbackNarrowphaseDetector: NarrowphaseDetector
    @kotlin.jvm.JvmField protected val fallbackConditions: MutableList<FallbackCondition?>

    constructor(primary: NarrowphaseDetector?, fallback: NarrowphaseDetector?) : this(primary, fallback, null)
    constructor(primary: NarrowphaseDetector?, fallback: NarrowphaseDetector?, conditions: MutableList<FallbackCondition?>?) {
        primaryNarrowphaseDetector = primary ?: throw ArgumentNullException("primaryNarrowphaseDetector")
        fallbackNarrowphaseDetector = fallback ?: throw ArgumentNullException("fallbackNarrowphaseDetector")
        fallbackConditions = conditions ?: ArrayList()
    }

    open fun addCondition(condition: FallbackCondition?) {
        fallbackConditions.add(condition)
        fallbackConditions.sortWith { first, second -> first!!.compareTo(second!!) }
    }
    open fun removeCondition(condition: FallbackCondition?) = fallbackConditions.remove(condition)
    open fun containsCondition(condition: FallbackCondition?) = fallbackConditions.contains(condition)
    open fun getConditionCount() = fallbackConditions.size
    open fun getCondition(index: Int): FallbackCondition? = fallbackConditions[index]
    open fun isFallbackRequired(convex1: Convex, convex2: Convex): Boolean {
        val size = fallbackConditions.size
        for (i in 0 until size) {
            val condition = fallbackConditions[i]
            if (condition != null && condition.isMatch(convex1, convex2)) return true
        }
        return false
    }
    override fun detect(convex1: Convex, transform1: Transform, convex2: Convex, transform2: Transform): Boolean =
        if (isFallbackRequired(convex1, convex2)) fallbackNarrowphaseDetector.detect(convex1, transform1, convex2, transform2)
        else primaryNarrowphaseDetector.detect(convex1, transform1, convex2, transform2)
    override fun detect(convex1: Convex, transform1: Transform, convex2: Convex, transform2: Transform, penetration: Penetration): Boolean =
        if (isFallbackRequired(convex1, convex2)) fallbackNarrowphaseDetector.detect(convex1, transform1, convex2, transform2, penetration)
        else primaryNarrowphaseDetector.detect(convex1, transform1, convex2, transform2, penetration)
    open fun getPrimaryNarrowphaseDetector() = primaryNarrowphaseDetector
    open fun getFallbackNarrowphaseDetector() = fallbackNarrowphaseDetector
}
