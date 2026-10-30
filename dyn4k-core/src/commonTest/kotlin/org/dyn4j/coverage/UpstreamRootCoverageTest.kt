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
package org.dyn4j.coverage

import de.infix.testBalloon.framework.core.testSuite
import org.dyn4j.Reference
import org.dyn4j.Version
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

val UpstreamReferenceCoverageTest by testSuite {
    test("testCreate") { UpstreamReferenceCoverageTestFixture().run { testCreate() } }
    test("testToString") { UpstreamReferenceCoverageTestFixture().run { testToString() } }
    test("testEquals") { UpstreamReferenceCoverageTestFixture().run { testEquals() } }
    test("testHashcode") { UpstreamReferenceCoverageTestFixture().run { testHashcode() } }
}

val UpstreamVersionCoverageTest by testSuite {
    test("versions") { UpstreamVersionCoverageTestFixture().run { versions() } }
    test("getVersionString") { UpstreamVersionCoverageTestFixture().run { getVersionString() } }
}

private class UpstreamReferenceCoverageTestFixture  {
fun testCreate() {
        Reference<Int>()
        Reference(5)
    }

fun testToString() {
        assertEquals("null", Reference<Int>().toString())
        assertEquals(5.toString(), Reference(5).toString())
    }

fun testEquals() {
        val test = Reference(5)
        assertEquals(Reference<Int>(), Reference<Int>())
        assertEquals(Reference(5), Reference(5))
        assertEquals(test, Reference(5))
        assertEquals(test, test)

        val obj = Any()
        val test2 = Reference(obj)
        assertEquals(Reference<Any>(), Reference<Any>())
        assertEquals(Reference(obj), Reference(obj))
        assertEquals(test2, Reference(obj))
        assertEquals(test2, test2)

        assertFalse(Reference(1).equals(Reference<Int>()))
        assertFalse(Reference<Int>().equals(Reference(1)))
        assertFalse(Reference(1).equals(Reference(5)))
        assertFalse(test.equals(Reference(4)))
        assertFalse(test.equals(null))
    }

fun testHashcode() {
        val test = Reference(5)
        assertEquals(Reference<Int>().hashCode(), Reference<Int>().hashCode())
        assertEquals(Reference(5).hashCode(), Reference(5).hashCode())
        assertEquals(test.hashCode(), Reference(5).hashCode())
        assertEquals(test.hashCode(), test.hashCode())

        val obj = Any()
        val test2 = Reference(obj)
        assertEquals(Reference<Any>().hashCode(), Reference<Any>().hashCode())
        assertEquals(Reference(obj).hashCode(), Reference(obj).hashCode())
        assertEquals(test2.hashCode(), Reference(obj).hashCode())
        assertEquals(test2.hashCode(), test2.hashCode())

        assertFalse(Reference(1).hashCode() == Reference<Int>().hashCode())
        assertFalse(Reference<Int>().hashCode() == Reference(1).hashCode())
        assertFalse(Reference(1).hashCode() == Reference(5).hashCode())
        assertFalse(test.hashCode() == Reference(4).hashCode())
    }
}
private class UpstreamVersionCoverageTestFixture  {
fun versions() {
        val version = Version.getVersionNumbers()
        assertEquals(Version.getMajorNumber(), version[0])
        assertEquals(Version.getMinorNumber(), version[1])
        assertEquals(Version.getRevisionNumber(), version[2])
    }

fun getVersionString() {
        val version = Version.getVersion()
        assertNotNull(version)
        assertTrue(version.isNotEmpty())
    }
}
