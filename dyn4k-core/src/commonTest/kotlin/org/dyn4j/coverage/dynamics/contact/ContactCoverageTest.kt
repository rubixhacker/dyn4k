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
package org.dyn4j.coverage.dynamics.contact

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.collision.BasicCollisionItem
import org.dyn4j.collision.BasicCollisionPair
import org.dyn4j.collision.CollisionItem
import org.dyn4j.collision.continuous.TimeOfImpact
import org.dyn4j.collision.manifold.ClippingManifoldSolver
import org.dyn4j.collision.manifold.IndexedManifoldPointId
import org.dyn4j.collision.manifold.Manifold
import org.dyn4j.collision.manifold.ManifoldPoint
import org.dyn4j.collision.manifold.ManifoldPointId
import org.dyn4j.collision.narrowphase.Gjk
import org.dyn4j.collision.narrowphase.Penetration
import org.dyn4j.collision.narrowphase.Separation
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.dynamics.contact.Contact
import org.dyn4j.dynamics.contact.ContactConstraint
import org.dyn4j.dynamics.contact.ContactUpdateHandler
import org.dyn4j.dynamics.contact.ForceCollisionTimeOfImpactSolver
import org.dyn4j.dynamics.contact.SequentialImpulses
import org.dyn4j.dynamics.contact.SolvableContact
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2
import org.dyn4j.world.ValueMixer

val ContactConstraintCoverageTest by testSuite {
    test("create") { ContactConstraintCoverageTestFixture().run { create() } }
    test("update") { ContactConstraintCoverageTestFixture().run { update() } }
    test("getSetEnabled") { ContactConstraintCoverageTestFixture().run { getSetEnabled() } }
    test("getSetTangentSpeed") { ContactConstraintCoverageTestFixture().run { getSetTangentSpeed() } }
    test("tostring") { ContactConstraintCoverageTestFixture().run { tostring() } }
    test("shift") { ContactConstraintCoverageTestFixture().run { shift() } }
}

val ForceCollisionTimeOfImpactSolverCoverageTest by testSuite {
    test("simpleScenario1") { ForceCollisionTimeOfImpactSolverCoverageTestFixture().run { simpleScenario1() } }
    test("simpleScenario2") { ForceCollisionTimeOfImpactSolverCoverageTestFixture().run { simpleScenario2() } }
}

val SequentialImpulsesCoverageTest by testSuite {
    test("restitutionVelocity") { SequentialImpulsesCoverageTestFixture().run { restitutionVelocity() } }
    test("illConditioned") { SequentialImpulsesCoverageTestFixture().run { illConditioned() } }
}

val SolvableContactCoverageTest by testSuite {
    test("create") { SolvableContactCoverageTestFixture().run { create() } }
    test("isSolved") { SolvableContactCoverageTestFixture().run { isSolved() } }
}

private class ContactScene(square: Boolean = false) {
    val first = Body()
    val second = Body()
    val firstFixture = first.addFixture(if (square) Geometry.createSquare(0.5) else Geometry.createCircle(0.5))
    val secondFixture = second.addFixture(if (square) Geometry.createSquare(0.5) else Geometry.createCircle(0.5))
    val pair = BasicCollisionPair<CollisionItem<Body, BodyFixture>>(
        BasicCollisionItem(first, firstFixture), BasicCollisionItem(second, secondFixture))
    val constraint = ContactConstraint(pair)
}

private class CountingHandler : ContactUpdateHandler {
    val events = mutableListOf<String>()
    override fun getFriction(fixture1: BodyFixture, fixture2: BodyFixture) =
        ValueMixer.DEFAULT_MIXER.mixFriction(fixture1.getFriction(), fixture2.getFriction())
    override fun getRestitution(fixture1: BodyFixture, fixture2: BodyFixture) =
        ValueMixer.DEFAULT_MIXER.mixRestitution(fixture1.getRestitution(), fixture2.getRestitution())
    override fun getRestitutionVelocity(fixture1: BodyFixture, fixture2: BodyFixture) =
        ValueMixer.DEFAULT_MIXER.mixRestitutionVelocity(fixture1.getRestitutionVelocity(), fixture2.getRestitutionVelocity())
    override fun begin(contact: Contact) { events.add("begin") }
    override fun persist(oldContact: Contact, newContact: Contact) { events.add("persist") }
    override fun end(contact: Contact) { events.add("end") }
}

private fun point(id: ManifoldPointId, x: Double, y: Double, depth: Double): ManifoldPoint =
    ManifoldPoint(id).also { it.setPoint(Vector2(x, y)); it.setDepth(depth) }

private fun manifold(vararg points: ManifoldPoint): Manifold = Manifold().also {
    it.setNormal(Vector2(1.0, 1.0))
    it.getPoints().addAll(points)
}

private class ContactConstraintCoverageTestFixture  {
    private fun assertUpdatedState(scene: ContactScene, expectedCount: Int, expectedSensor: Boolean) {
        val contact = scene.constraint
        assertEquals(expectedCount, contact.getContacts().size)
        assertEquals(expectedCount, contact.solverContacts().size)
        assertTrue(contact.isEnabled())
        assertEquals(BodyFixture.DEFAULT_FRICTION, contact.getFriction())
        assertEquals(BodyFixture.DEFAULT_RESTITUTION, contact.getRestitution())
        assertEquals(BodyFixture.DEFAULT_RESTITUTION_VELOCITY, contact.getRestitutionVelocity())
        assertNull(contact.K); assertNull(contact.invK)
        assertSame(scene.pair, contact.getCollisionPair())
        assertSame(scene.first, contact.getBody1()); assertSame(scene.second, contact.getBody2())
        assertSame(scene.firstFixture, contact.getFixture1()); assertSame(scene.secondFixture, contact.getFixture2())
        assertEquals(1.0, contact.getNormal().x); assertEquals(1.0, contact.getNormal().y)
        assertEquals(1.0, contact.getTangent().x); assertEquals(-1.0, contact.getTangent().y)
        assertEquals(0.0, contact.getTangentSpeed())
        assertEquals(expectedSensor, contact.isSensor())
        assertSame(scene.first, contact.getBody(scene.first)); assertSame(scene.second, contact.getBody(scene.second))
        assertSame(scene.firstFixture, contact.getFixture(scene.first))
        assertSame(scene.secondFixture, contact.getFixture(scene.second))
        assertSame(scene.second, contact.getOtherBody(scene.first))
        assertSame(scene.first, contact.getOtherBody(scene.second))
        assertSame(scene.secondFixture, contact.getOtherFixture(scene.first))
        assertSame(scene.firstFixture, contact.getOtherFixture(scene.second))
        val alien = Body()
        assertNull(contact.getBody(alien)); assertNull(contact.getFixture(alien))
        assertNull(contact.getOtherBody(alien)); assertNull(contact.getOtherFixture(alien))
    }

fun create() {
        val scene = ContactScene(); val contact = scene.constraint
        val view = contact.getContacts()
        assertTrue(view.isEmpty()); assertEquals(0, contact.solverContacts().size)
        assertTrue(contact.isEnabled()); assertFalse(contact.isSensor())
        assertEquals(BodyFixture.DEFAULT_FRICTION, contact.getFriction())
        assertEquals(BodyFixture.DEFAULT_RESTITUTION, contact.getRestitution())
        assertEquals(BodyFixture.DEFAULT_RESTITUTION_VELOCITY, contact.getRestitutionVelocity())
        assertEquals(0.0, contact.getNormal().x); assertEquals(0.0, contact.getNormal().y)
        assertEquals(0.0, contact.getTangent().x); assertEquals(0.0, contact.getTangent().y)
        assertEquals(0.0, contact.getTangentSpeed())
        assertNull(contact.K); assertNull(contact.invK)
        assertSame(scene.pair, contact.getCollisionPair())
        assertSame(scene.first, contact.getBody1()); assertSame(scene.second, contact.getBody2())
        assertSame(scene.firstFixture, contact.getFixture1()); assertSame(scene.secondFixture, contact.getFixture2())
        assertSame(scene.first, contact.getBody(scene.first)); assertSame(scene.second, contact.getBody(scene.second))
        assertSame(scene.firstFixture, contact.getFixture(scene.first))
        assertSame(scene.secondFixture, contact.getFixture(scene.second))
        assertSame(scene.second, contact.getOtherBody(scene.first))
        assertSame(scene.first, contact.getOtherBody(scene.second))
        assertSame(scene.secondFixture, contact.getOtherFixture(scene.first))
        assertSame(scene.firstFixture, contact.getOtherFixture(scene.second))
        val alien = Body()
        assertNull(contact.getBody(alien)); assertNull(contact.getFixture(alien))
        assertNull(contact.getOtherBody(alien)); assertNull(contact.getOtherFixture(alien))
    }

fun update() {
        val scene = ContactScene(); val contact = scene.constraint
        val handler = CountingHandler(); val settings = Settings()
        val distance = point(ManifoldPointId.DISTANCE, 2.0, 2.0, 1.0)
        val indexed = point(IndexedManifoldPointId(0, 0, 0), 2.0, 3.0, 2.0)
        val manifold = manifold(distance, indexed)
        val liveView = contact.getContacts()
        contact.update(manifold, settings, handler)
        assertEquals(listOf("begin", "begin"), handler.events)
        assertEquals(2, liveView.size); assertEquals(2, contact.solverContacts().size)
        assertEquals(1.0, contact.getNormal().x); assertEquals(1.0, contact.getNormal().y)
        assertEquals(1.0, contact.getTangent().x); assertEquals(-1.0, contact.getTangent().y)
        assertEquals(BodyFixture.DEFAULT_FRICTION, contact.getFriction())
        assertFalse(contact.isSensor()); assertTrue(contact.isEnabled())
        assertUpdatedState(scene, 2, false)
        contact.solverContacts()[0].jn = 2.0
        contact.solverContacts()[0].jt = 3.0
        distance.getPoint().x = 2.0001
        indexed.getPoint().x = 2.0001
        manifold.getPoints().add(0, point(IndexedManifoldPointId(0, 0, 1), 2.0, 3.0, 2.0))
        scene.firstFixture.setSensor(true)
        handler.events.clear()
        contact.update(manifold, settings, handler)
        assertEquals(listOf("begin", "persist", "persist"), handler.events)
        assertEquals(3, liveView.size)
        assertTrue(contact.isSensor())
        assertEquals(2.0, contact.solverContacts()[1].jn)
        assertEquals(3.0, contact.solverContacts()[1].jt)
        assertUpdatedState(scene, 3, true)
        manifold.getPoints().removeAt(0)
        scene.firstFixture.setSensor(false)
        handler.events.clear()
        contact.update(manifold, settings, handler)
        assertEquals(listOf("persist", "persist", "end"), handler.events)
        assertEquals(2, liveView.size); assertFalse(contact.isSensor())
        assertUpdatedState(scene, 2, false)
    }

fun getSetEnabled() {
        val contact = ContactScene().constraint
        contact.setEnabled(true); assertTrue(contact.isEnabled())
        contact.setEnabled(false); assertFalse(contact.isEnabled())
        contact.setEnabled(true); assertTrue(contact.isEnabled())
    }

fun getSetTangentSpeed() {
        val contact = ContactScene().constraint
        for (speed in listOf(0.5, 0.0, 50.0, -0.5)) {
            contact.setTangentSpeed(speed); assertEquals(speed, contact.getTangentSpeed())
        }
    }

fun tostring() {
        val contact = ContactScene().constraint
        assertTrue(contact.toString().isNotEmpty())
        val points = manifold(point(ManifoldPointId.DISTANCE, 2.0, 2.0, 1.0),
            point(ManifoldPointId.DISTANCE, 3.0, 2.0, 2.0))
        contact.update(points, Settings(), CountingHandler())
        assertTrue(contact.toString().isNotEmpty())
    }

fun shift() {
        val contact = ContactScene().constraint
        contact.update(manifold(point(ManifoldPointId.DISTANCE, 2.0, 2.0, 1.0),
            point(ManifoldPointId.DISTANCE, 3.0, 2.0, 2.0)), Settings(), CountingHandler())
        assertEquals(2.0, contact.getContacts()[0].getPoint().x)
        assertEquals(3.0, contact.getContacts()[1].getPoint().x)
        contact.shift(Vector2(2.0, -1.0))
        assertEquals(1.0, contact.getNormal().x); assertEquals(1.0, contact.getNormal().y)
        assertEquals(1.0, contact.getTangent().x); assertEquals(-1.0, contact.getTangent().y)
        assertEquals(1.0, contact.getContacts()[0].getDepth())
        assertEquals(4.0, contact.getContacts()[0].getPoint().x)
        assertEquals(1.0, contact.getContacts()[0].getPoint().y)
        assertEquals(2.0, contact.getContacts()[1].getDepth())
        assertEquals(5.0, contact.getContacts()[1].getPoint().x)
        assertEquals(1.0, contact.getContacts()[1].getPoint().y)
    }
}

private class ForceCollisionTimeOfImpactSolverCoverageTestFixture  {
    private fun toi(distance: Double, secondX: Double, time: Double): TimeOfImpact {
        val separation = Separation().also {
            it.setDistance(distance); it.setNormal(Vector2(1.0, 0.0))
            it.setPoint1(Vector2(1.0, 0.0)); it.setPoint2(Vector2(secondX, 0.0))
        }
        return TimeOfImpact().also { it.setSeparation(separation); it.setTime(time) }
    }

fun simpleScenario1() {
        val first = Body().also { it.addFixture(Geometry.createCircle(1.0)); it.setMass(MassType.NORMAL) }
        val second = Body().also {
            it.addFixture(Geometry.createCircle(1.0)); it.translate(2.5, 0.0); it.setMass(MassType.INFINITE)
        }
        ForceCollisionTimeOfImpactSolver<Body>().solve(first, second, toi(0.5, 1.5, 0.5), Settings())
        assertEquals(0.2, first.getTransform().getTranslationX(), 1e-12)
        assertEquals(0.0, first.getTransform().getTranslationY())
        assertEquals(2.5, second.getTransform().getTranslationX())
        assertEquals(0.0, second.getTransform().getTranslationY())
    }

fun simpleScenario2() {
        val first = Body().also { it.addFixture(Geometry.createCircle(1.0)); it.setMass(MassType.NORMAL) }
        val second = Body().also {
            it.addFixture(Geometry.createCircle(1.0)); it.translate(2.0001, 0.0); it.setMass(MassType.NORMAL)
        }
        ForceCollisionTimeOfImpactSolver<Body>().solve(first, second, toi(0.0001, 1.0001, 1.0), Settings())
        assertEquals(0.00255, first.getTransform().getTranslationX(), 1e-12)
        assertEquals(0.0, first.getTransform().getTranslationY())
        assertEquals(1.99755, second.getTransform().getTranslationX(), 1e-12)
        assertEquals(0.0, second.getTransform().getTranslationY())
    }
}

private class SequentialImpulsesCoverageTestFixture  {
    private fun prepared(squareTranslationX: Double, squareTranslationY: Double):
        Triple<ContactScene, Manifold, Settings> {
        val scene = ContactScene(square = true)
        scene.firstFixture.setRestitution(0.1); scene.secondFixture.setRestitution(0.1)
        scene.first.translate(squareTranslationX, squareTranslationY)
        val penetration = Penetration()
        assertTrue(Gjk().detect(scene.firstFixture.getShape(), scene.first.getTransform(),
            scene.secondFixture.getShape(), scene.second.getTransform(), penetration))
        val manifold = Manifold()
        assertTrue(ClippingManifoldSolver().getManifold(penetration, scene.firstFixture.getShape(),
            scene.first.getTransform(), scene.secondFixture.getShape(), scene.second.getTransform(), manifold))
        return Triple(scene, manifold, Settings())
    }

fun restitutionVelocity() {
        val (scene, manifold, settings) = prepared(0.0, 0.45)
        scene.first.setLinearVelocity(0.0, -1.5)
        val handler = CountingHandler(); val solver = SequentialImpulses<Body>()
        val step = TimeStep(settings.getStepFrequency()); val constraints = listOf(scene.constraint)
        scene.constraint.update(manifold, settings, handler)
        solver.initialize(constraints, step, settings)
        assertEquals(2, scene.constraint.solverContacts().size)
        scene.constraint.solverContacts().forEach { assertEquals(0.15, it.vb, 1e-12) }
        scene.first.setLinearVelocity(0.0, -0.5)
        scene.constraint.update(manifold, settings, handler)
        solver.initialize(constraints, step, settings)
        scene.constraint.solverContacts().forEach { assertEquals(0.0, it.vb) }
    }

fun illConditioned() {
        val (scene, manifold, settings) = prepared(0.49995, 0.49995)
        scene.first.setMass(MassType.NORMAL); scene.second.setMass(MassType.NORMAL)
        scene.first.setLinearVelocity(0.0, -1.5)
        val solver = SequentialImpulses<Body>(); val step = TimeStep(settings.getStepFrequency())
        scene.constraint.update(manifold, settings, CountingHandler())
        solver.initialize(listOf(scene.constraint), step, settings)
        assertEquals(1, scene.constraint.solverSize())
        assertTrue(scene.constraint.solverContacts()[0].isSolved())
        assertFalse(scene.constraint.solverContacts()[1].isSolved())
        manifold.getPoints()[1].setDepth(manifold.getPoints()[1].getDepth() + 0.1)
        scene.constraint.update(manifold, settings, CountingHandler())
        val formerFirst = scene.constraint.solverContacts()[0]
        val formerSecond = scene.constraint.solverContacts()[1]
        solver.initialize(listOf(scene.constraint), step, settings)
        assertEquals(1, scene.constraint.solverSize())
        assertSame(formerSecond, scene.constraint.solverContacts()[0])
        assertSame(formerFirst, scene.constraint.solverContacts()[1])
        assertTrue(formerSecond.isSolved()); assertFalse(formerFirst.isSolved())
    }
}

private class SolvableContactCoverageTestFixture  {
    private fun contact() = SolvableContact(ManifoldPointId.DISTANCE, Vector2(1.0, 3.0), 5.0,
        Vector2(3.0, 4.0), Vector2(5.0, 6.0))

fun create() {
        val contact = contact()
        assertSame(ManifoldPointId.DISTANCE, contact.getId())
        assertEquals(1.0, contact.getPoint().x); assertEquals(3.0, contact.getPoint().y)
        assertEquals(3.0, contact.p1.x); assertEquals(4.0, contact.p1.y)
        assertEquals(5.0, contact.p2.x); assertEquals(6.0, contact.p2.y)
        assertEquals(5.0, contact.getDepth())
        assertEquals(0.0, contact.getNormalImpulse()); assertEquals(0.0, contact.getTangentialImpulse())
        assertEquals(0.0, contact.jp); assertEquals(0.0, contact.massN)
        assertEquals(0.0, contact.massT); assertEquals(0.0, contact.vb)
        assertFalse(contact.isIgnored()); assertFalse(contact.isSolved())
        assertNull(contact.r1); assertNull(contact.r2)
    }

fun isSolved() {
        val contact = contact()
        assertFalse(contact.isIgnored()); assertFalse(contact.isSolved())
        contact.ignored = true
        assertTrue(contact.isIgnored()); assertFalse(contact.isSolved())
        contact.solved = true
        assertTrue(contact.isIgnored()); assertTrue(contact.isSolved())
    }
}
