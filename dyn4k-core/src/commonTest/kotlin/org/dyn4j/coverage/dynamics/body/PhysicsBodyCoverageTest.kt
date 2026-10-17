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
package org.dyn4j.coverage.dynamics.body

import kotlin.math.PI
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotSame
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.dynamics.Force
import org.dyn4j.dynamics.PhysicsBody
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.dynamics.Torque
import org.dyn4j.exception.ArgumentNullException
import org.dyn4j.exception.ValueOutOfRangeException
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.Mass
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2

class PhysicsBodyCoverageTest {
    private fun dynamicBody(): Body = Body().also {
        it.addFixture(Circle(1.0))
        it.setMass(MassType.NORMAL)
    }

    @Test
    fun defaultsAndFixtureOverloads() {
        val body = Body()
        assertEquals(PhysicsBody.DEFAULT_ANGULAR_DAMPING, body.getAngularDamping())
        assertEquals(PhysicsBody.DEFAULT_LINEAR_DAMPING, body.getLinearDamping())
        assertEquals(0.0, body.getAngularVelocity())
        assertEquals(0.0, body.getTorque())
        assertEquals(1.0, body.getGravityScale())
        assertFalse(body.isAtRest())
        assertTrue(body.isAtRestDetectionEnabled())
        assertFalse(body.isBullet())
        assertEquals(0, body.getFixtureCount())
        assertEquals(0.0, body.getLinearVelocity().x)
        assertEquals(0.0, body.getLinearVelocity().y)
        val shape = Circle(1.0)
        val first = body.addFixture(shape)
        assertSame(shape, first.getShape())
        assertSame(first, body.getFixture(0))
        assertEquals(BodyFixture.DEFAULT_DENSITY, first.getDensity())
        assertEquals(BodyFixture.DEFAULT_FRICTION, first.getFriction())
        val second = body.addFixture(Circle(0.5), 2.0, 0.5, 0.4)
        assertSame(second, body.getFixture(1))
        assertEquals(2.0, second.getDensity())
        assertEquals(0.5, second.getFriction())
        assertEquals(0.4, second.getRestitution())
        val third = body.addFixture(Circle(0.25), 0.1)
        assertEquals(0.1, third.getDensity())
        assertEquals(BodyFixture.DEFAULT_FRICTION, third.getFriction())
        assertEquals(3, body.getFixtureCount())
        Body(-3)
        Body(0)
        Body(3)
    }

    @Test
    fun fixtureNullOverloadsRejectBeforeMutation() {
        val body = Body()
        assertFailsWith<ArgumentNullException> { body.addFixture(null as org.dyn4j.geometry.Convex?) }
        assertFailsWith<ArgumentNullException> { body.addFixture(null, 0.2) }
        assertFailsWith<ArgumentNullException> { body.addFixture(null, 0.2, 0.2, 0.3) }
        assertFailsWith<ArgumentNullException> { body.addFixture(null as BodyFixture?) }
        assertEquals(0, body.getFixtureCount())
    }

    @Test
    fun appliedForcesAndTorquesAccumulateWithoutChangingInputs() {
        val body = dynamicBody()
        val force = Force(Vector2(1.0, 2.0))
        val forceVector = force.getForce()
        body.setAtRest(true)
        body.applyForce(force)
        assertFalse(body.isAtRest())
        assertEquals(1.0, body.getAccumulatedForce().x)
        assertEquals(2.0, body.getAccumulatedForce().y)
        assertEquals(0.0, body.getForce().x)
        body.applyForce(Vector2(0.5, -1.0))
        assertEquals(1.5, body.getAccumulatedForce().x)
        assertEquals(1.0, body.getAccumulatedForce().y)
        body.applyForce(Vector2(0.0, 2.0), Vector2(1.0, 0.0))
        assertEquals(1.5, body.getAccumulatedForce().x)
        assertEquals(3.0, body.getAccumulatedForce().y)
        assertEquals(2.0, body.getAccumulatedTorque())
        body.applyTorque(Torque(0.5))
        body.applyTorque(0.5)
        assertEquals(3.0, body.getAccumulatedTorque())
        assertSame(forceVector, force.getForce())
        assertEquals(1.0, forceVector.x)
        assertEquals(2.0, forceVector.y)
        assertEquals(0.0, body.getTorque())
        body.integrateVelocity(Vector2(), TimeStep(Settings.DEFAULT_STEP_FREQUENCY), Settings())
        assertEquals(1.5, body.getForce().x)
        assertEquals(3.0, body.getForce().y)
        assertEquals(3.0, body.getTorque())
        val returnedForce = body.getForce()
        returnedForce.x = 999.0
        assertEquals(1.5, body.getForce().x)
        assertEquals(0.0, body.getAccumulatedForce().x)
        assertEquals(0.0, body.getAccumulatedTorque())
        val inert = Body()
        inert.applyForce(Force(1.0, 1.0))
        inert.applyTorque(Torque(4.0))
        assertEquals(0.0, inert.getAccumulatedForce().x)
        assertEquals(0.0, inert.getAccumulatedTorque())
    }

    @Test
    fun forceAndImpulseNullOverloadsReject() {
        val body = Body()
        assertFailsWith<ArgumentNullException> { body.applyForce(null as Force?) }
        assertFailsWith<ArgumentNullException> { body.applyForce(null as Vector2?) }
        assertFailsWith<ArgumentNullException> { body.applyTorque(null as Torque?) }
        assertFailsWith<ArgumentNullException> { body.applyForce(null, Vector2()) }
        assertFailsWith<ArgumentNullException> { body.applyForce(Vector2(0.0, 1.0), null) }
        assertFailsWith<ArgumentNullException> { body.applyImpulse(null as Vector2?) }
        assertFailsWith<ArgumentNullException> { body.applyImpulse(null, Vector2()) }
        assertFailsWith<ArgumentNullException> { body.applyImpulse(Vector2(), null) }
    }

    @Test
    fun impulsesUseMassAndInertia() {
        val body = Body()
        body.addFixture(Geometry.createRectangle(1.0, 1.0))
        body.setMass(MassType.NORMAL)
        val mass = body.getMass().getMass()
        val inertia = body.getMass().getInertia()
        body.applyImpulse(Vector2(mass, mass))
        assertEquals(1.0, body.getLinearVelocity().x)
        assertEquals(1.0, body.getLinearVelocity().y)
        body.getLinearVelocity().zero()
        body.applyImpulse(inertia)
        assertEquals(1.0, body.getAngularVelocity())
        body.setAngularVelocity(0.0)
        body.applyImpulse(Vector2(0.0, inertia), Vector2(1.0, 0.0))
        assertEquals(1.0, body.getAngularVelocity())
        assertEquals(inertia, body.getLinearVelocity().y)
        val inert = Body()
        inert.applyImpulse(0.2)
        inert.applyImpulse(Vector2(2.0, 1.0))
        assertEquals(0.0, inert.getAngularVelocity())
        assertEquals(0.0, inert.getLinearVelocity().x)
    }

    @Test
    fun clearMethodsRemoveOnlyTheirOwnState() {
        val body = dynamicBody()
        body.applyForce(Vector2(0.0, 1.0))
        body.applyTorque(0.4)
        body.integrateVelocity(Vector2(), TimeStep(0.1), Settings())
        assertEquals(1.0, body.getForce().y)
        assertEquals(0.4, body.getTorque())
        body.applyForce(Vector2(2.0, 0.0))
        body.applyTorque(0.3)
        body.clearForce()
        assertEquals(0.0, body.getForce().y)
        assertEquals(2.0, body.getAccumulatedForce().x)
        body.clearTorque()
        assertEquals(0.0, body.getTorque())
        assertEquals(0.3, body.getAccumulatedTorque())
        body.clearAccumulatedForce()
        assertEquals(0.0, body.getAccumulatedForce().x)
        body.clearAccumulatedTorque()
        assertEquals(0.0, body.getAccumulatedTorque())
    }

    @Test
    fun velocityDampingGravityAndBulletAreObservable() {
        val body = Body()
        body.setLinearDamping(1.0)
        body.setAngularDamping(2.0)
        assertEquals(1.0, body.getLinearDamping())
        assertEquals(2.0, body.getAngularDamping())
        body.setLinearDamping(0.0)
        body.setAngularDamping(0.0)
        assertEquals(0.0, body.getLinearDamping())
        assertEquals(0.0, body.getAngularDamping())
        assertFailsWith<ValueOutOfRangeException> { body.setLinearDamping(-1.0) }
        assertFailsWith<ValueOutOfRangeException> { body.setAngularDamping(-2.0 * PI) }
        val velocity = body.getLinearVelocity()
        body.setLinearVelocity(Vector2(1.0, 2.0))
        assertSame(velocity, body.getLinearVelocity())
        assertEquals(1.0, velocity.x)
        body.setLinearVelocity(-4.0, 5.0)
        assertEquals(-4.0, velocity.x)
        assertEquals(5.0, velocity.y)
        assertFailsWith<ArgumentNullException> { body.setLinearVelocity(null) }
        body.setAngularVelocity(-3.0)
        assertEquals(-3.0, body.getAngularVelocity())
        body.setGravityScale(-1.0)
        assertEquals(-1.0, body.getGravityScale())
        body.setGravityScale(0.00001)
        assertEquals(0.00001, body.getGravityScale())
        assertFalse(body.isBullet())
        body.setBullet(true)
        assertTrue(body.isBullet())
        body.setBullet(false)
        assertFalse(body.isBullet())
    }

    @Test
    fun sweptBoundsAndPreviousTransformTrackTranslation() {
        val body = Body()
        body.addFixture(Circle(0.5))
        body.setMass(MassType.INFINITE)
        body.translate(2.0, -2.0)
        val bounds = body.createSweptAABB()
        assertEquals(-0.5, bounds.getMinX())
        assertEquals(2.5, bounds.getMaxX())
        assertEquals(-2.5, bounds.getMinY())
        assertEquals(0.5, bounds.getMaxY())
        val start = Transform()
        val end = Transform()
        end.translate(-2.0, 0.0)
        val explicit = body.createSweptAABB(start, end)
        assertEquals(-2.5, explicit.getMinX())
        assertEquals(0.5, explicit.getMaxX())
        body.getPreviousTransform().set(body.getTransform())
        body.translate(-3.0, 1.0)
        assertEquals(-3.0, body.getChangeInPosition().x)
        assertEquals(1.0, body.getChangeInPosition().y)
    }

    @Test
    fun orientationChangePreservesDirectionAcrossWraparound() {
        val body = Body()
        body.addFixture(Circle(0.5))
        body.rotate(PI / 6.0)
        body.setAngularVelocity(PI / 180.0)
        body.setMass(MassType.INFINITE)
        body.getPreviousTransform().set(body.getTransform())
        val positiveCases = listOf(50.0 to 20.0, 200.0 to 170.0, 20.0 to 350.0)
        for ((angle, expected) in positiveCases) {
            body.getTransform().identity()
            body.rotate(angle * PI / 180.0)
            assertEquals(expected, body.getChangeInOrientation() * 180.0 / PI, 1e-3)
        }
        body.setAngularVelocity(-PI / 180.0)
        val negativeCases = listOf(50.0 to -340.0, 200.0 to -190.0, 20.0 to -10.0)
        for ((angle, expected) in negativeCases) {
            body.getTransform().identity()
            body.rotate(angle * PI / 180.0)
            assertEquals(expected, body.getChangeInOrientation() * 180.0 / PI, 1e-3)
        }
        body.setAngularVelocity(0.0)
        val stationaryCases = listOf(50.0 to 20.0, 200.0 to 170.0, 20.0 to -10.0, 350.0 to -40.0)
        for ((angle, expected) in stationaryCases) {
            body.getTransform().identity()
            body.rotate(angle * PI / 180.0)
            assertEquals(expected, body.getChangeInOrientation() * 180.0 / PI, 1e-3)
        }
        body.getPreviousTransform().identity()
        body.getPreviousTransform().rotate(-PI / 6.0)
        body.setAngularVelocity(1.0)
        val reverseStartPositive = listOf(50.0 to 80.0, 200.0 to 230.0, 20.0 to 50.0)
        for ((angle, expected) in reverseStartPositive) {
            body.getTransform().identity()
            body.rotate(angle * PI / 180.0)
            assertEquals(expected, body.getChangeInOrientation() * 180.0 / PI, 1e-3)
        }
        body.setAngularVelocity(-PI / 180.0)
        val reverseStartNegative = listOf(50.0 to -280.0, 200.0 to -130.0, 20.0 to -310.0)
        for ((angle, expected) in reverseStartNegative) {
            body.getTransform().identity()
            body.rotate(angle * PI / 180.0)
            assertEquals(expected, body.getChangeInOrientation() * 180.0 / PI, 1e-3)
        }
        body.setAngularVelocity(0.0)
        val reverseStartStationary = listOf(50.0 to 80.0, 200.0 to -130.0, 20.0 to 50.0, 350.0 to 20.0)
        for ((angle, expected) in reverseStartStationary) {
            body.getTransform().identity()
            body.rotate(angle * PI / 180.0)
            assertEquals(expected, body.getChangeInOrientation() * 180.0 / PI, 1e-3)
        }
        assertEquals(0.0, Body().getChangeInOrientation())
    }

    @Test
    fun massIdentityAndTypeTransitions() {
        val body = Body()
        assertTrue(body.isStatic())
        body.setMass(MassType.INFINITE)
        assertTrue(body.getMass().isInfinite())
        val fixture = body.addFixture(Circle(1.0))
        body.setMass(MassType.NORMAL)
        assertTrue(body.isDynamic())
        assertEquals(fixture.createMass().getMass(), body.getMass().getMass())
        val mass = Mass(Vector2(0.2, 0.0), 2.3, 20.3)
        body.setMass(mass)
        assertSame(mass, body.getMass())
        body.setMassType(MassType.INFINITE)
        assertSame(mass, body.getMass())
        assertTrue(body.getMass().isInfinite())
        body.setMassType(MassType.NORMAL)
        assertEquals(2.3, body.getMass().getMass())
        assertEquals(20.3, body.getMass().getInertia())
        body.setMass(null as MassType?)
        assertEquals(MassType.NORMAL, body.getMass().getType())
        body.updateMass()
        assertEquals(fixture.createMass().getMass(), body.getMass().getMass())
        assertFailsWith<ArgumentNullException> { body.setMassType(null) }
        assertFailsWith<ArgumentNullException> { body.setMass(null as Mass?) }
        body.removeAllFixtures()
        body.addFixture(Circle(1.0), 0.0)
        body.setMass(MassType.NORMAL)
        assertEquals(MassType.INFINITE, body.getMass().getType())
        assertEquals(0.0, body.getMass().getMass())
    }

    @Test
    fun fixtureMassCompositionIgnoresZeroDensity() {
        val body = Body()
        val first = body.addFixture(Geometry.createUnitCirclePolygon(5, 0.5))
        val second = body.addFixture(Geometry.createIsoscelesTriangle(1.0, 1.0))
        body.setMass(MassType.NORMAL)
        val twoFixtureMass = body.getMass().getMass()
        assertTrue(twoFixtureMass > first.createMass().getMass())
        assertTrue(twoFixtureMass > second.createMass().getMass())
        val zero = body.addFixture(Circle(0.5))
        zero.setDensity(0.0)
        body.setMass(MassType.NORMAL)
        assertEquals(twoFixtureMass, body.getMass().getMass(), 1e-9)
        body.setMass(MassType.FIXED_ANGULAR_VELOCITY)
        assertEquals(0.0, body.getMass().getInverseInertia())
        body.setMass(MassType.FIXED_LINEAR_VELOCITY)
        assertEquals(0.0, body.getMass().getInverseMass())
        body.removeAllFixtures()
        repeat(3) { body.addFixture(Geometry.createSquare(1.0), 0.0) }
        body.setMass(MassType.NORMAL)
        assertEquals(MassType.INFINITE, body.getMass().getType())
        assertEquals(0.0, body.getMass().getMass())
        assertEquals(0.0, body.getMass().getInertia())
    }

    @Test
    fun staticKinematicDynamicAndRestStateTransitions() {
        val body = Body()
        assertTrue(body.isStatic())
        body.setLinearVelocity(0.0, 2.0)
        assertTrue(body.isKinematic())
        assertFalse(body.isDynamic())
        body.setLinearVelocity(0.0, 0.0)
        body.setAngularVelocity(0.4)
        assertTrue(body.isKinematic())
        body.setAngularVelocity(0.0)
        assertTrue(body.isStatic())
        body.addFixture(Circle(0.5))
        body.setMass(MassType.NORMAL)
        assertTrue(body.isDynamic())
        body.setAtRestDetectionEnabled(false)
        body.setAtRest(true)
        assertTrue(body.isAtRest())
        body.applyForce(Vector2(1.0, 0.0))
        assertFalse(body.isAtRest())
        body.setAtRest(true)
        assertEquals(0.0, body.getLinearVelocity().x)
        assertEquals(0.0, body.getAngularVelocity())
        assertEquals(0.0, body.getAccumulatedForce().x)
        body.setAtRest(false)
        body.applyForce(Vector2(1.0, 0.0))
        body.applyTorque(1.2)
        body.integrateVelocity(Vector2(), TimeStep(0.1), Settings())
        assertEquals(1.0, body.getForce().x)
        assertEquals(1.2, body.getTorque())
        body.setAtRest(true)
        assertEquals(1.0, body.getForce().x)
        assertEquals(1.2, body.getTorque())
    }

    @Test
    fun fixtureViewAndMassAreLiveAcrossRemoval() {
        val body = Body()
        val fixtures = body.getFixtures()
        val first = body.addFixture(Circle(1.0))
        val second = body.addFixture(Circle(0.5))
        assertSame(first, fixtures[0])
        assertSame(second, fixtures[1])
        body.setMass(MassType.NORMAL)
        val originalMass = body.getMass().getMass()
        body.setAtRest(true)
        assertTrue(body.removeFixture(first))
        assertFalse(body.isAtRest())
        assertEquals(1, fixtures.size)
        assertSame(second, fixtures.single())
        body.updateMass()
        assertTrue(body.getMass().getMass() < originalMass)
        body.removeAllFixtures()
        assertTrue(fixtures.isEmpty())
    }

    @Test
    fun sleepThresholdsCallGettersInOrder() {
        val body = dynamicBody()
        body.setLinearVelocity(10.0, 0.0)
        val calls = StringBuilder()
        val settings = object : Settings() {
            override fun getMaximumAtRestLinearVelocitySquared(): Double {
                calls.append('L')
                return super.getMaximumAtRestLinearVelocitySquared()
            }
            override fun getMaximumAtRestAngularVelocity(): Double {
                calls.append('A')
                return super.getMaximumAtRestAngularVelocity()
            }
        }
        assertEquals(0.0, body.updateAtRestTime(TimeStep(0.1), settings))
        assertEquals("LA", calls.toString())
        body.setLinearVelocity(0.0, 0.0)
        assertEquals(0.1, body.updateAtRestTime(TimeStep(0.1), Settings()))
        body.setAngularVelocity(10.0)
        assertEquals(0.0, body.updateAtRestTime(TimeStep(0.1), Settings()))
        body.setAngularVelocity(0.0)
        body.setMassType(MassType.INFINITE)
        assertEquals(-1.0, body.updateAtRestTime(TimeStep(0.1), Settings()))
    }

    @Test
    fun velocityAndPositionIntegrationUseStepAndLimits() {
        val body = Body()
        body.addFixture(Circle(0.5))
        body.setMass(MassType.NORMAL)
        val settings = Settings()
        val step = TimeStep(settings.getStepFrequency())
        body.integrateVelocity(Vector2(0.0, -9.8), step, settings)
        assertEquals(-9.8 * settings.getStepFrequency(), body.getLinearVelocity().y, 1e-9)
        body.setLinearVelocity(0.0, -2.0)
        body.integratePosition(step, settings)
        assertEquals(-2.0 * settings.getStepFrequency(), body.getWorldCenter().y, 1e-9)
        body.setLinearVelocity(0.0, -400.0)
        body.integratePosition(step, settings)
        assertEquals(-2.0 * settings.getStepFrequency() - settings.getMaximumTranslation(), body.getWorldCenter().y, 1e-9)
        body.setLinearVelocity(0.0, 0.0)
        body.setAngularVelocity(settings.getMaximumRotation() / settings.getStepFrequency() * 10.0)
        body.integratePosition(step, settings)
        assertEquals(settings.getMaximumRotation(), body.getTransform().getRotationAngle(), 1e-9)
    }

    @Test
    fun localCenterAndPointVelocityUseLiveMassAndVelocity() {
        val body = Body()
        assertEquals(0.0, body.getLocalCenter().x)
        body.addFixture(Circle(0.5))
        body.setMass(MassType.NORMAL)
        val offset = body.addFixture(Circle(0.5))
        offset.getShape().translate(-0.5, 0.0)
        body.setMass(MassType.NORMAL)
        assertEquals(-0.25, body.getLocalCenter().x, 1e-9)
        body.setLinearVelocity(5.0, 4.0)
        body.setAngularVelocity(PI)
        val center = body.getWorldCenter()
        val point = Vector2(center.x + 1.0, center.y)
        val velocity = body.getLinearVelocity(point)
        assertEquals(5.0, velocity.x, 1e-9)
        assertEquals(4.0 + PI, velocity.y, 1e-9)
        assertTrue(body.toString().isNotEmpty())
    }

    @Test
    fun bodyCopyKeepsStateButReplacesMutableObjects() {
        val body = dynamicBody()
        val originalFixture = body.getFixture(0)
        val appliedForce = Force(2.0, 3.0)
        val appliedTorque = Torque(0.4)
        body.applyForce(appliedForce)
        body.applyTorque(appliedTorque)
        body.integrateVelocity(Vector2(), TimeStep(0.1), Settings())
        body.applyForce(appliedForce)
        body.applyTorque(appliedTorque)
        body.setLinearVelocity(-1.0, 2.0)
        body.setAngularVelocity(0.5)
        body.setGravityScale(1.1)
        body.setBullet(true)
        body.setOwner(Any())
        body.setUserData(Any())
        val copy = body.copy()
        assertNotSame(body, copy)
        assertNotSame(originalFixture, copy.getFixture(0))
        assertNotSame(body.getLinearVelocity(), copy.getLinearVelocity())
        assertNotSame(body.getMass(), copy.getMass())
        assertEquals(body.getMass().getMass(), copy.getMass().getMass())
        assertEquals(-1.0, copy.getLinearVelocity().x)
        assertEquals(2.0, copy.getLinearVelocity().y)
        assertEquals(0.5, copy.getAngularVelocity())
        assertEquals(1.1, copy.getGravityScale())
        assertTrue(copy.isBullet())
        assertEquals(null, copy.getOwner())
        assertEquals(null, copy.getUserData())
        assertEquals(null, copy.getFixtureModificationHandler())
        appliedForce.set(9.0, 10.0)
        appliedTorque.set(2.0)
        assertEquals(9.0, body.getAccumulatedForce().x)
        assertEquals(2.0, copy.getAccumulatedForce().x)
        assertEquals(3.0, copy.getAccumulatedForce().y)
        assertEquals(0.4, copy.getAccumulatedTorque())
        body.clearForce()
        body.clearTorque()
        assertEquals(2.0, copy.getForce().x)
        assertEquals(0.4, copy.getTorque())
        body.getMass().getCenter().x = 5.0
        assertEquals(0.0, copy.getMass().getCenter().x)
    }

    @Test
    fun atRestTimeResetsAndDisabledDetectionKeepsBodyAwake() {
        val body = dynamicBody()
        val step = TimeStep(0.1)
        val settings = Settings()
        assertEquals(0.1, body.updateAtRestTime(step, settings))
        assertEquals(0.2, body.updateAtRestTime(step, settings))
        body.setLinearVelocity(settings.getMaximumAtRestLinearVelocity() + 1.0, 0.0)
        assertEquals(0.0, body.updateAtRestTime(step, settings))
        body.setLinearVelocity(0.0, 0.0)
        assertEquals(0.1, body.updateAtRestTime(step, settings))
        body.setAngularVelocity(settings.getMaximumAtRestAngularVelocity() + 1.0)
        assertEquals(0.0, body.updateAtRestTime(step, settings))
        body.setAngularVelocity(0.0)
        body.setAtRestDetectionEnabled(false)
        assertEquals(0.0, body.updateAtRestTime(step, settings))
        assertFalse(body.isAtRest())
    }
}
