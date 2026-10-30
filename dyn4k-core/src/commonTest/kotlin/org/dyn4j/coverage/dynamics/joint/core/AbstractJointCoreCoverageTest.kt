/*
 * Copyright (c) 2010-2022 William Bittle  http://www.dyn4j.org/
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
package org.dyn4j.coverage.dynamics.joint.core

import de.infix.testBalloon.framework.core.testSuite
import kotlin.math.PI
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.dynamics.joint.AbstractJoint
import org.dyn4j.dynamics.joint.AbstractPairedBodyJoint
import org.dyn4j.dynamics.joint.AbstractSingleBodyJoint
import org.dyn4j.exception.ArgumentNullException
import org.dyn4j.exception.EmptyCollectionException
import org.dyn4j.exception.InvalidIndexException
import org.dyn4j.exception.NullElementException
import org.dyn4j.exception.SameObjectException
import org.dyn4j.geometry.Mass
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2

val AbstractJointCoreCoverageTest by testSuite {
    test("create") { AbstractJointCoreCoverageTestFixture().run { create() } }
    test("createNullList") { AbstractJointCoreCoverageTestFixture().run { createNullList() } }
    test("createListWithNullElement") { AbstractJointCoreCoverageTestFixture().run { createListWithNullElement() } }
    test("createEmptyList") { AbstractJointCoreCoverageTestFixture().run { createEmptyList() } }
    test("getBodies") { AbstractJointCoreCoverageTestFixture().run { getBodies() } }
    test("getBodiesAndAdd") { AbstractJointCoreCoverageTestFixture().run { getBodiesAndAdd() } }
    test("getBodiesAndRemove") { AbstractJointCoreCoverageTestFixture().run { getBodiesAndRemove() } }
    test("getBodyAtValidIndex") { AbstractJointCoreCoverageTestFixture().run { getBodyAtValidIndex() } }
    test("getBodyAtNegativeIndex") { AbstractJointCoreCoverageTestFixture().run { getBodyAtNegativeIndex() } }
    test("getBodyAtTooHighIndex") { AbstractJointCoreCoverageTestFixture().run { getBodyAtTooHighIndex() } }
    test("getBodyCount") { AbstractJointCoreCoverageTestFixture().run { getBodyCount() } }
    test("getBodyIterator") { AbstractJointCoreCoverageTestFixture().run { getBodyIterator() } }
    test("getBodyIteratorRemove") { AbstractJointCoreCoverageTestFixture().run { getBodyIteratorRemove() } }
    test("isMember") { AbstractJointCoreCoverageTestFixture().run { isMember() } }
    test("isEnabled") { AbstractJointCoreCoverageTestFixture().run { isEnabled() } }
    test("getSetCollisionAllowed") { AbstractJointCoreCoverageTestFixture().run { getSetCollisionAllowed() } }
    test("getSetUserData") { AbstractJointCoreCoverageTestFixture().run { getSetUserData() } }
    test("getSetOwner") { AbstractJointCoreCoverageTestFixture().run { getSetOwner() } }
    test("getConstraintImpulseMixing") { AbstractJointCoreCoverageTestFixture().run { getConstraintImpulseMixing() } }
    test("getErrorReductionParameter") { AbstractJointCoreCoverageTestFixture().run { getErrorReductionParameter() } }
    test("getFrequency") { AbstractJointCoreCoverageTestFixture().run { getFrequency() } }
    test("getSpringStiffness") { AbstractJointCoreCoverageTestFixture().run { getSpringStiffness() } }
    test("getNaturalFrequency") { AbstractJointCoreCoverageTestFixture().run { getNaturalFrequency() } }
    test("getSpringDampingCoefficient") { AbstractJointCoreCoverageTestFixture().run { getSpringDampingCoefficient() } }
}

val AbstractPairedBodyJointCoreCoverageTest by testSuite {
    test("create") { AbstractPairedBodyJointCoreCoverageTestFixture().run { create() } }
    test("createNullBody1") { AbstractPairedBodyJointCoreCoverageTestFixture().run { createNullBody1() } }
    test("createNullBody2") { AbstractPairedBodyJointCoreCoverageTestFixture().run { createNullBody2() } }
    test("createNullBoth") { AbstractPairedBodyJointCoreCoverageTestFixture().run { createNullBoth() } }
    test("createSame") { AbstractPairedBodyJointCoreCoverageTestFixture().run { createSame() } }
    test("getBodies") { AbstractPairedBodyJointCoreCoverageTestFixture().run { getBodies() } }
    test("getBodiesAndAdd") { AbstractPairedBodyJointCoreCoverageTestFixture().run { getBodiesAndAdd() } }
    test("getBodiesAndRemove") { AbstractPairedBodyJointCoreCoverageTestFixture().run { getBodiesAndRemove() } }
    test("getBodyAtValidIndex") { AbstractPairedBodyJointCoreCoverageTestFixture().run { getBodyAtValidIndex() } }
    test("getBodyAtNegativeIndex") { AbstractPairedBodyJointCoreCoverageTestFixture().run { getBodyAtNegativeIndex() } }
    test("getBodyAtTooHighIndex") { AbstractPairedBodyJointCoreCoverageTestFixture().run { getBodyAtTooHighIndex() } }
    test("getBodyCount") { AbstractPairedBodyJointCoreCoverageTestFixture().run { getBodyCount() } }
    test("getBodyIterator") { AbstractPairedBodyJointCoreCoverageTestFixture().run { getBodyIterator() } }
    test("getBodyIteratorRemove") { AbstractPairedBodyJointCoreCoverageTestFixture().run { getBodyIteratorRemove() } }
    test("isMember") { AbstractPairedBodyJointCoreCoverageTestFixture().run { isMember() } }
    test("isEnabled") { AbstractPairedBodyJointCoreCoverageTestFixture().run { isEnabled() } }
    test("getOtherBody") { AbstractPairedBodyJointCoreCoverageTestFixture().run { getOtherBody() } }
    test("getReducedInertia") { AbstractPairedBodyJointCoreCoverageTestFixture().run { getReducedInertia() } }
    test("getReducedMass") { AbstractPairedBodyJointCoreCoverageTestFixture().run { getReducedMass() } }
}

val AbstractSingleBodyJointCoreCoverageTest by testSuite {
    test("create") { AbstractSingleBodyJointCoreCoverageTestFixture().run { create() } }
    test("createNullBody") { AbstractSingleBodyJointCoreCoverageTestFixture().run { createNullBody() } }
    test("getBodies") { AbstractSingleBodyJointCoreCoverageTestFixture().run { getBodies() } }
    test("getBodiesAndAdd") { AbstractSingleBodyJointCoreCoverageTestFixture().run { getBodiesAndAdd() } }
    test("getBodiesAndRemove") { AbstractSingleBodyJointCoreCoverageTestFixture().run { getBodiesAndRemove() } }
    test("getBodyAtValidIndex") { AbstractSingleBodyJointCoreCoverageTestFixture().run { getBodyAtValidIndex() } }
    test("getBodyAtNegativeIndex") { AbstractSingleBodyJointCoreCoverageTestFixture().run { getBodyAtNegativeIndex() } }
    test("getBodyAtTooHighIndex") { AbstractSingleBodyJointCoreCoverageTestFixture().run { getBodyAtTooHighIndex() } }
    test("getBodyCount") { AbstractSingleBodyJointCoreCoverageTestFixture().run { getBodyCount() } }
    test("getBodyIterator") { AbstractSingleBodyJointCoreCoverageTestFixture().run { getBodyIterator() } }
    test("getBodyIteratorRemove") { AbstractSingleBodyJointCoreCoverageTestFixture().run { getBodyIteratorRemove() } }
    test("isMember") { AbstractSingleBodyJointCoreCoverageTestFixture().run { isMember() } }
    test("isEnabled") { AbstractSingleBodyJointCoreCoverageTestFixture().run { isEnabled() } }
}

private class General(bodies: List<Body>?) : AbstractJoint<Body>(bodies) {
    fun constraintImpulseMixing() = getConstraintImpulseMixing(2.0, 3.0, 4.0)
    fun errorReductionParameter() = getErrorReductionParameter(2.0, 3.0, 4.0)
    fun frequency() = getFrequency(4.0)
    fun springStiffness() = getSpringStiffness(2.0, 3.0)
    fun naturalFrequencyFromFrequency() = getNaturalFrequency(3.0)
    fun naturalFrequencyFromStiffness() = getNaturalFrequency(8.0, 2.0)
    fun springDampingCoefficient() = getSpringDampingCoefficient(2.0, 3.0, 4.0)
    override fun copy() = General(getBodies())
    override fun shift(shift: Vector2) {}
    override fun initializeConstraints(step: TimeStep?, settings: Settings?) {}
    override fun solveVelocityConstraints(step: TimeStep?, settings: Settings?) {}
    override fun solvePositionConstraints(step: TimeStep?, settings: Settings?) = false
    override fun getReactionForce(invdt: Double) = Vector2()
    override fun getReactionTorque(invdt: Double) = 0.0
}

private class Pair(first: Body?, second: Body?) : AbstractPairedBodyJoint<Body>(first, second) {
    fun reducedInertia() = getReducedInertia()
    fun reducedMass() = getReducedMass()
    override fun copy() = Pair(getBody1(), getBody2())
    override fun copy(body1: Body?, body2: Body?) = Pair(body1, body2)
    override fun shift(shift: Vector2) {}
    override fun initializeConstraints(step: TimeStep?, settings: Settings?) {}
    override fun solveVelocityConstraints(step: TimeStep?, settings: Settings?) {}
    override fun solvePositionConstraints(step: TimeStep?, settings: Settings?) = false
    override fun getReactionForce(invdt: Double) = Vector2()
    override fun getReactionTorque(invdt: Double) = 0.0
}

private class Single(body: Body?) : AbstractSingleBodyJoint<Body>(body) {
    override fun copy() = Single(getBody())
    override fun copy(body: Body?) = Single(body)
    override fun shift(shift: Vector2) {}
    override fun initializeConstraints(step: TimeStep?, settings: Settings?) {}
    override fun solveVelocityConstraints(step: TimeStep?, settings: Settings?) {}
    override fun solvePositionConstraints(step: TimeStep?, settings: Settings?) = false
    override fun getReactionForce(invdt: Double) = Vector2()
    override fun getReactionTorque(invdt: Double) = 0.0
}

private fun checkDefaults(joint: AbstractJoint<Body>, bodies: List<Body>) {
    assertEquals(bodies.size, joint.getBodyCount())
    assertNull(joint.getOwner())
    assertNull(joint.getUserData())
    assertFalse(joint.isCollisionAllowed())
    bodies.forEachIndexed { index, body -> assertSame(body, joint.getBody(index)) }
    assertNotNull(joint.getBodies())
    assertNotNull(joint.getBodyIterator())
    assertTrue(joint.toString().isNotEmpty())
}

private fun checkReadOnlyBodies(joint: AbstractJoint<Body>, expected: List<Body>) {
    val actual = joint.getBodies()
    assertEquals(expected.size, actual.size)
    expected.forEachIndexed { index, body -> assertSame(body, actual[index]) }
}

private fun checkIterator(joint: AbstractJoint<Body>, expected: List<Body>) {
    val iterator = joint.getBodyIterator()
    val actual = mutableListOf<Body>()
    while (iterator.hasNext()) actual.add(iterator.next())
    assertEquals(expected.size, actual.size)
    expected.forEachIndexed { index, body -> assertSame(body, actual[index]) }
}

private class AbstractJointCoreCoverageTestFixture  {
    private val first = Body()
    private val second = Body()
    private fun joint() = General(listOf(first, second))

fun create() = checkDefaults(joint(), listOf(first, second))
fun createNullList() { assertFailsWith<ArgumentNullException> { General(null) } }
fun createListWithNullElement() {
        @Suppress("UNCHECKED_CAST") val bodies = listOf(first, null) as List<Body>
        assertFailsWith<NullElementException> { General(bodies) }
    }
fun createEmptyList() { assertFailsWith<EmptyCollectionException> { General(emptyList()) } }
fun getBodies() = checkReadOnlyBodies(joint(), listOf(first, second))
fun getBodiesAndAdd() { assertFailsWith<UnsupportedOperationException> { joint().getBodies().add(Body()) } }
fun getBodiesAndRemove() { assertFailsWith<UnsupportedOperationException> { joint().getBodies().removeAt(0) } }
fun getBodyAtValidIndex() { val j = joint(); assertSame(first, j.getBody(0)); assertSame(second, j.getBody(1)) }
fun getBodyAtNegativeIndex() { assertFailsWith<IndexOutOfBoundsException> { joint().getBody(-1) } }
fun getBodyAtTooHighIndex() { assertFailsWith<IndexOutOfBoundsException> { joint().getBody(2) } }
fun getBodyCount() { assertEquals(2, joint().getBodyCount()) }
fun getBodyIterator() = checkIterator(joint(), listOf(first, second))
fun getBodyIteratorRemove() { val it = joint().getBodyIterator(); it.next(); assertFailsWith<UnsupportedOperationException> { it.remove() } }
fun isMember() { val j = joint(); assertTrue(j.isMember(first)); assertTrue(j.isMember(second)); assertFalse(j.isMember(null)); assertFalse(j.isMember(Body())) }
fun isEnabled() { val j = joint(); assertTrue(j.isEnabled()); first.setEnabled(false); assertFalse(j.isEnabled()); second.setEnabled(false); assertFalse(j.isEnabled()); first.setEnabled(true); second.setEnabled(true); assertTrue(j.isEnabled()) }
fun getSetCollisionAllowed() { val j = joint(); j.setCollisionAllowed(false); assertFalse(j.isCollisionAllowed()); j.setCollisionAllowed(true); assertTrue(j.isCollisionAllowed()); j.setCollisionAllowed(false); assertFalse(j.isCollisionAllowed()) }
fun getSetUserData() { val j = joint(); val marker = Any(); j.setUserData(null); assertNull(j.getUserData()); j.setUserData(marker); assertSame(marker, j.getUserData()); j.setUserData(null); assertNull(j.getUserData()) }
fun getSetOwner() { val j = joint(); val marker = Any(); j.setOwner(null); assertNull(j.getOwner()); j.setOwner(marker); assertSame(marker, j.getOwner()); j.setOwner(null); assertNull(j.getOwner()) }
fun getConstraintImpulseMixing() { assertEquals(1.0 / 20.0, joint().constraintImpulseMixing()) }
fun getErrorReductionParameter() { assertEquals(0.3, joint().errorReductionParameter()) }
fun getFrequency() { assertEquals(2.0 / PI, joint().frequency()) }
fun getSpringStiffness() { assertEquals(18.0, joint().springStiffness()) }
fun getNaturalFrequency() { val j = joint(); assertEquals(6.0 * PI, j.naturalFrequencyFromFrequency()); assertEquals(2.0, j.naturalFrequencyFromStiffness()) }
fun getSpringDampingCoefficient() { assertEquals(48.0, joint().springDampingCoefficient()) }
}

private class AbstractPairedBodyJointCoreCoverageTestFixture  {
    private val first = Body()
    private val second = Body()
    private fun joint() = Pair(first, second)

fun create() { val j = joint(); checkDefaults(j, listOf(first, second)); assertSame(first, j.getBody1()); assertSame(second, j.getBody2()) }
fun createNullBody1() { assertFailsWith<NullElementException> { Pair(null, second) } }
fun createNullBody2() { assertFailsWith<NullElementException> { Pair(first, null) } }
fun createNullBoth() { assertFailsWith<NullElementException> { Pair(null, null) } }
fun createSame() { assertFailsWith<SameObjectException> { Pair(first, first) } }
fun getBodies() { val j = joint(); checkReadOnlyBodies(j, listOf(first, second)); assertSame(first, j.getBody1()); assertSame(second, j.getBody2()) }
fun getBodiesAndAdd() { assertFailsWith<UnsupportedOperationException> { joint().getBodies().add(Body()) } }
fun getBodiesAndRemove() { assertFailsWith<UnsupportedOperationException> { joint().getBodies().removeAt(0) } }
fun getBodyAtValidIndex() { assertSame(first, joint().getBody(0)) }
fun getBodyAtNegativeIndex() { assertFailsWith<IndexOutOfBoundsException> { joint().getBody(-1) } }
fun getBodyAtTooHighIndex() { assertFailsWith<IndexOutOfBoundsException> { joint().getBody(2) } }
fun getBodyCount() { assertEquals(2, joint().getBodyCount()) }
fun getBodyIterator() = checkIterator(joint(), listOf(first, second))
fun getBodyIteratorRemove() { val it = joint().getBodyIterator(); it.next(); assertFailsWith<UnsupportedOperationException> { it.remove() } }
fun isMember() { val j = joint(); assertTrue(j.isMember(first)); assertTrue(j.isMember(second)); assertFalse(j.isMember(null)); assertFalse(j.isMember(Body())) }
fun isEnabled() { val j = joint(); assertTrue(j.isEnabled()); first.setEnabled(false); assertFalse(j.isEnabled()); second.setEnabled(false); assertFalse(j.isEnabled()); first.setEnabled(true); second.setEnabled(true); assertTrue(j.isEnabled()) }
fun getOtherBody() { val j = joint(); assertSame(second, j.getOtherBody(first)); assertSame(first, j.getOtherBody(second)); assertNull(j.getOtherBody(null)); assertNull(j.getOtherBody(Body())) }
fun getReducedInertia() {
        val j = joint(); first.setMass(Mass(Vector2(), 1.0, 2.0)); second.setMass(Mass(Vector2(), 1.0, 2.0))
        assertEquals(1.0, j.reducedInertia()); first.setMassType(MassType.INFINITE); assertEquals(2.0, j.reducedInertia())
        first.setMassType(MassType.NORMAL); second.setMassType(MassType.INFINITE); assertEquals(2.0, j.reducedInertia())
        first.setMassType(MassType.INFINITE); assertEquals(0.0, j.reducedInertia())
    }
fun getReducedMass() {
        val j = joint(); first.setMass(Mass(Vector2(), 1.0, 2.0)); second.setMass(Mass(Vector2(), 1.0, 2.0))
        assertEquals(0.5, j.reducedMass()); first.setMassType(MassType.INFINITE); assertEquals(1.0, j.reducedMass())
        first.setMassType(MassType.NORMAL); second.setMassType(MassType.INFINITE); assertEquals(1.0, j.reducedMass())
        first.setMassType(MassType.INFINITE); assertEquals(0.0, j.reducedMass())
    }
}

private class AbstractSingleBodyJointCoreCoverageTestFixture  {
    private val body = Body()
    private fun joint() = Single(body)

fun create() { val j = joint(); checkDefaults(j, listOf(body)); assertSame(body, j.getBody()) }
fun createNullBody() { assertFailsWith<NullElementException> { Single(null) } }
fun getBodies() = checkReadOnlyBodies(joint(), listOf(body))
fun getBodiesAndAdd() { assertFailsWith<UnsupportedOperationException> { joint().getBodies().add(Body()) } }
fun getBodiesAndRemove() { assertFailsWith<UnsupportedOperationException> { joint().getBodies().removeAt(0) } }
fun getBodyAtValidIndex() { assertSame(body, joint().getBody(0)) }
fun getBodyAtNegativeIndex() { assertFailsWith<IndexOutOfBoundsException> { joint().getBody(-1) } }
fun getBodyAtTooHighIndex() { assertFailsWith<IndexOutOfBoundsException> { joint().getBody(1) } }
fun getBodyCount() { assertEquals(1, joint().getBodyCount()) }
fun getBodyIterator() = checkIterator(joint(), listOf(body))
fun getBodyIteratorRemove() { val it = joint().getBodyIterator(); it.next(); assertFailsWith<UnsupportedOperationException> { it.remove() } }
fun isMember() { val j = joint(); assertTrue(j.isMember(body)); assertFalse(j.isMember(null)); assertFalse(j.isMember(Body())) }
fun isEnabled() { val j = joint(); assertTrue(j.isEnabled()); body.setEnabled(false); assertFalse(j.isEnabled()); body.setEnabled(true); assertTrue(j.isEnabled()) }
}
