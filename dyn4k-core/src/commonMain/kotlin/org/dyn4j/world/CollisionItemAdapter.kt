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
package org.dyn4j.world

import org.dyn4j.collision.AbstractCollisionItem
import org.dyn4j.collision.CollisionBody
import org.dyn4j.collision.Fixture

internal class CollisionItemAdapter<T : CollisionBody<E>, E : Fixture>() : AbstractCollisionItem<T, E>() {
    private var body: T? = null
    private var fixture: E? = null

    constructor(body: T?, fixture: E?) : this() {
        this.body = body
        this.fixture = fixture
    }

    protected constructor(item: CollisionItemAdapter<T, E>) : this(item.body, item.fixture)

    fun set(body: T?, fixture: E?) {
        this.body = body
        this.fixture = fixture
    }

    fun set(item: CollisionItemAdapter<T, E>) {
        body = item.body
        fixture = item.fixture
    }

    override fun getBody() = body
    override fun getFixture() = fixture
    override fun copy() = CollisionItemAdapter(this)
    override fun hashCode() = AbstractCollisionItem.getHashCode(body, fixture)
    override fun equals(other: Any?) = AbstractCollisionItem.equals(this, other)
}
