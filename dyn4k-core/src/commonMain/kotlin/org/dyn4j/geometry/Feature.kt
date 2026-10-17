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
package org.dyn4j.geometry

import org.dyn4j.Copyable
import org.dyn4j.JvmFieldBridge

abstract class Feature : Copyable<Feature> {
    @get:kotlin.jvm.JvmName("getIndexField")
    @JvmFieldBridge private val index: Int

    constructor(index: Int) { this.index = index }
    protected constructor(feature: Feature) { index = feature.index }
    fun getIndex() = index
    companion object { const val NOT_INDEXED = -1 }
}

class PointFeature : Feature {
    @get:kotlin.jvm.JvmName("getPointField")
    @JvmFieldBridge private val point: Vector2?

    constructor(point: Vector2?) : this(point, NOT_INDEXED)
    constructor(point: Vector2?, index: Int) : super(index) { this.point = point }
    protected constructor(feature: PointFeature) : super(feature) { point = feature.point!!.copy() }

    override fun copy() = PointFeature(this)
    override fun toString() = "PointFeature[Point=$point|Index=${getIndex()}]"
    fun getPoint() = point
}

class EdgeFeature : Feature {
    @get:kotlin.jvm.JvmName("getVertex1Field")
    @JvmFieldBridge private val vertex1: PointFeature?
    @get:kotlin.jvm.JvmName("getVertex2Field")
    @JvmFieldBridge private val vertex2: PointFeature?
    @JvmFieldBridge private val max: PointFeature?
    @get:kotlin.jvm.JvmName("getEdgeField")
    @JvmFieldBridge private val edge: Vector2?

    constructor(vertex1: PointFeature?, vertex2: PointFeature?, max: PointFeature?, edge: Vector2?, index: Int) : super(index) {
        this.vertex1 = vertex1
        this.vertex2 = vertex2
        this.max = max
        this.edge = edge
    }
    protected constructor(feature: EdgeFeature) : super(feature) {
        vertex1 = feature.vertex1!!.copy()
        vertex2 = feature.vertex2!!.copy()
        max = feature.max!!.copy()
        edge = feature.edge!!.copy()
    }

    override fun copy() = EdgeFeature(this)
    override fun toString() = "EdgeFeature[Vertex1=$vertex1|Vertex2=$vertex2|Edge=$edge|Max=$max|Index=${getIndex()}]"
    fun getVertex1() = vertex1
    fun getVertex2() = vertex2
    fun getEdge() = edge
    fun getMaximum() = max
}
