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

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotSame
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.dynamics.ContinuousDetectionMode
import org.dyn4j.dynamics.Force
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.dynamics.Torque
import org.dyn4j.exception.ArgumentNullException
import org.dyn4j.exception.ValueOutOfRangeException
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2

class BodyValueCoverageTest {
    private fun assertChangedSettings(settings: Settings) {
        assertEquals(Settings.DEFAULT_STEP_FREQUENCY * 2.0, settings.getStepFrequency())
        assertEquals(Settings.DEFAULT_ANGULAR_TOLERANCE * 2.0, settings.getAngularTolerance())
        assertEquals(Settings.DEFAULT_BAUMGARTE * 2.0, settings.getBaumgarte())
        assertEquals(Settings.DEFAULT_LINEAR_TOLERANCE * 2.0, settings.getLinearTolerance())
        assertEquals(Settings.DEFAULT_MAXIMUM_ANGULAR_CORRECTION * 2.0, settings.getMaximumAngularCorrection())
        assertEquals(Settings.DEFAULT_MAXIMUM_AT_REST_ANGULAR_VELOCITY * 2.0, settings.getMaximumAtRestAngularVelocity())
        assertEquals(Settings.DEFAULT_MAXIMUM_AT_REST_LINEAR_VELOCITY * 2.0, settings.getMaximumAtRestLinearVelocity())
        assertEquals(Settings.DEFAULT_MAXIMUM_LINEAR_CORRECTION * 2.0, settings.getMaximumLinearCorrection())
        assertEquals(Settings.DEFAULT_MAXIMUM_ROTATION * 2.0, settings.getMaximumRotation())
        assertEquals(Settings.DEFAULT_MAXIMUM_TRANSLATION * 2.0, settings.getMaximumTranslation())
        assertEquals(Settings.DEFAULT_MAXIMUM_WARM_START_DISTANCE * 2.0, settings.getMaximumWarmStartDistance())
        assertEquals(Settings.DEFAULT_MINIMUM_AT_REST_TIME * 2.0, settings.getMinimumAtRestTime())
        assertEquals(Settings.DEFAULT_POSITION_CONSTRAINT_SOLVER_ITERATIONS * 2, settings.getPositionConstraintSolverIterations())
        assertEquals(Settings.DEFAULT_VELOCITY_CONSTRAINT_SOLVER_ITERATIONS * 2, settings.getVelocityConstraintSolverIterations())
        assertFalse(settings.isAtRestDetectionEnabled())
        assertFalse(settings.isWarmStartingEnabled())
        assertEquals(ContinuousDetectionMode.NONE, settings.getContinuousDetectionMode())
    }

    private fun assertAppliedForce(force: Force) {
        assertEquals(2.0, force.getForce().x)
        assertEquals(3.0, force.getForce().y)
    }

    @Test
    fun controlledWrongForceGetterFailsThePortableOracle() {
        assertAppliedForce(Force(2.0, 3.0))
        val wrong = object : Force(2.0, 3.0) {
            override fun getForce() = Vector2(0.0, 0.0)
        }
        assertFailsWith<AssertionError> { assertAppliedForce(wrong) }
    }

    @Test
    fun forceConstructionSetCopyAndLiveVector() {
        val force = Force(0.3, 2.0)
        assertEquals(0.3, force.getForce().x)
        assertEquals(2.0, force.getForce().y)
        val live = force.getForce()
        force.set(3.0, -2.0)
        assertSame(live, force.getForce())
        assertEquals(-2.0, live.y)
        force.set(Vector2(2.0, 1.0))
        assertEquals(2.0, live.x)
        val other = Force(0.5, -2.0)
        force.set(other)
        assertEquals(0.5, live.x)
        assertEquals(-2.0, live.y)
        assertNotSame(other.getForce(), live)
        val copy = force.copy()
        assertNotSame(force, copy)
        assertNotSame(live, copy.getForce())
        assertEquals(0.5, copy.getForce().x)
        assertEquals(-2.0, copy.getForce().y)
        assertEquals(0.5, Force(force).getForce().x)
        assertEquals(1.0, Force(Vector2(2.0, 1.0)).getForce().y)
        assertTrue(force.isComplete(0.0))
        assertTrue(force.toString().isNotEmpty())
        assertEquals(0.0, Force().getForce().x)
    }

    @Test
    fun forceNullOverloadsRejectTheirArgument() {
        assertFailsWith<ArgumentNullException> { Force(null as Force?) }
        assertFailsWith<ArgumentNullException> { Force(null as Vector2?) }
        val force = Force()
        assertFailsWith<ArgumentNullException> { force.set(null as Force?) }
        assertFailsWith<ArgumentNullException> { force.set(null as Vector2?) }
    }

    @Test
    fun torqueConstructionSetCopyAndCompletion() {
        val torque = Torque(-3.5)
        assertEquals(-3.5, torque.getTorque())
        torque.set(0.32)
        assertEquals(0.32, torque.getTorque())
        torque.set(Torque(3.42))
        assertEquals(3.42, torque.getTorque())
        val copy = torque.copy()
        assertNotSame(torque, copy)
        assertEquals(3.42, copy.getTorque())
        assertEquals(3.42, Torque(torque).getTorque())
        assertEquals(0.0, Torque().getTorque())
        assertTrue(torque.isComplete(0.0))
        assertTrue(torque.toString().isNotEmpty())
    }

    @Test
    fun torqueNullOverloadsRejectTheirArgument() {
        assertFailsWith<ArgumentNullException> { Torque(null as Torque?) }
        assertFailsWith<ArgumentNullException> { Torque().set(null as Torque?) }
    }

    @Test
    fun timestepTracksPreviousValuesAndRejectsInvalidUpdates() {
        val step = TimeStep(0.3)
        assertEquals(0.3, step.getDeltaTime())
        assertEquals(0.3, step.getPrevousDeltaTime())
        assertEquals(1.0, step.getDeltaTimeRatio())
        assertEquals(1.0 / 0.3, step.getInverseDeltaTime())
        assertEquals(1.0 / 0.3, step.getPreviousInverseDeltaTime())
        step.update(0.4)
        assertEquals(0.4, step.getDeltaTime())
        assertEquals(0.3, step.getPrevousDeltaTime())
        assertEquals(0.4 / 0.3, step.getDeltaTimeRatio())
        assertEquals(1.0 / 0.4, step.getInverseDeltaTime())
        step.update(0.2)
        assertEquals(0.4, step.getPrevousDeltaTime())
        assertEquals(0.2 / 0.4, step.getDeltaTimeRatio())
        assertEquals(1.0 / 0.4, step.getPreviousInverseDeltaTime())
        assertFailsWith<ValueOutOfRangeException> { TimeStep(0.0) }
        assertFailsWith<ValueOutOfRangeException> { TimeStep(-1.0) }
        assertFailsWith<ValueOutOfRangeException> { step.update(0.0) }
        assertFailsWith<ValueOutOfRangeException> { step.update(-1.0) }
        assertEquals(0.2, step.getDeltaTime())
        assertTrue(step.toString().contains("0.2"))
    }

    @Test
    fun fixturePropertiesMassAndErrors() {
        assertFailsWith<ArgumentNullException> { BodyFixture(null) }
        val shape = Circle(0.5)
        val fixture = BodyFixture(shape)
        assertSame(shape, fixture.getShape())
        assertEquals(BodyFixture.DEFAULT_DENSITY, fixture.getDensity())
        assertEquals(BodyFixture.DEFAULT_FRICTION, fixture.getFriction())
        assertEquals(BodyFixture.DEFAULT_RESTITUTION, fixture.getRestitution())
        assertEquals(BodyFixture.DEFAULT_RESTITUTION_VELOCITY, fixture.getRestitutionVelocity())
        fixture.setDensity(0.001)
        assertEquals(0.001, fixture.getDensity())
        fixture.setDensity(1000.0)
        assertEquals(1000.0, fixture.getDensity())
        assertFailsWith<ValueOutOfRangeException> { fixture.setDensity(-1.0) }
        fixture.setFriction(5.0)
        assertEquals(5.0, fixture.getFriction())
        fixture.setFriction(0.0)
        assertEquals(0.0, fixture.getFriction())
        assertFailsWith<ValueOutOfRangeException> { fixture.setFriction(-2.0) }
        fixture.setRestitution(5.0)
        assertEquals(5.0, fixture.getRestitution())
        fixture.setRestitution(0.0)
        assertEquals(0.0, fixture.getRestitution())
        assertFailsWith<ValueOutOfRangeException> { fixture.setRestitution(-1.0) }
        fixture.setDensity(1.0)
        val mass = fixture.createMass()
        assertEquals(MassType.NORMAL, mass.getType())
        assertTrue(mass.getMass() > 0.0)
        assertTrue(mass.getInertia() > 0.0)
        fixture.setDensity(0.0)
        assertEquals(0.0, fixture.getDensity())
        val zeroMass = fixture.createMass()
        assertEquals(MassType.INFINITE, zeroMass.getType())
        assertEquals(0.0, zeroMass.getMass())
        assertEquals(0.0, zeroMass.getInertia())
        fixture.setRestitutionVelocity(-1.0)
        assertEquals(-1.0, fixture.getRestitutionVelocity())
        assertTrue(fixture.toString().isNotEmpty())
    }

    @Test
    fun settingsValidateScalarsAndKeepDerivedSquares() {
        val settings = Settings()
        settings.setStepFrequency(1.0 / 70.0)
        assertEquals(1.0 / 70.0, settings.getStepFrequency())
        assertFailsWith<ValueOutOfRangeException> { settings.setStepFrequency(-1.0 / 30.0) }
        assertFailsWith<ValueOutOfRangeException> { settings.setStepFrequency(0.0) }
        val values = listOf(
            Triple<(Double) -> Unit, () -> Double, () -> Double>(settings::setMaximumTranslation, settings::getMaximumTranslation, settings::getMaximumTranslationSquared),
            Triple(settings::setMaximumRotation, settings::getMaximumRotation, settings::getMaximumRotationSquared),
            Triple(settings::setMaximumAtRestLinearVelocity, settings::getMaximumAtRestLinearVelocity, settings::getMaximumAtRestLinearVelocitySquared),
            Triple(settings::setMaximumAtRestAngularVelocity, settings::getMaximumAtRestAngularVelocity, settings::getMaximumAtRestAngularVelocitySquared),
            Triple(settings::setMaximumWarmStartDistance, settings::getMaximumWarmStartDistance, settings::getMaximumWarmStartDistanceSquared),
            Triple(settings::setLinearTolerance, settings::getLinearTolerance, settings::getLinearToleranceSquared),
            Triple(settings::setAngularTolerance, settings::getAngularTolerance, settings::getAngularToleranceSquared),
            Triple(settings::setMaximumLinearCorrection, settings::getMaximumLinearCorrection, settings::getMaximumLinearCorrectionSquared),
            Triple(settings::setMaximumAngularCorrection, settings::getMaximumAngularCorrection, settings::getMaximumAngularCorrectionSquared)
        )
        for ((set, get, square) in values) {
            set(2.0)
            assertEquals(2.0, get())
            assertEquals(4.0, square())
            assertFailsWith<ValueOutOfRangeException> { set(-1.0) }
            assertEquals(2.0, get())
        }
        settings.setMinimumAtRestTime(12.0)
        assertEquals(12.0, settings.getMinimumAtRestTime())
        assertFailsWith<ValueOutOfRangeException> { settings.setMinimumAtRestTime(-1.0) }
        settings.setBaumgarte(0.3)
        assertEquals(0.3, settings.getBaumgarte())
        assertFailsWith<ValueOutOfRangeException> { settings.setBaumgarte(-0.3) }
    }

    @Test
    fun settingsValidateIterationsAndFlags() {
        val settings = Settings()
        settings.setVelocityConstraintSolverIterations(17)
        assertEquals(17, settings.getVelocityConstraintSolverIterations())
        assertFailsWith<ValueOutOfRangeException> { settings.setVelocityConstraintSolverIterations(-3) }
        assertFailsWith<ValueOutOfRangeException> { settings.setVelocityConstraintSolverIterations(0) }
        settings.setPositionConstraintSolverIterations(17)
        assertEquals(17, settings.getPositionConstraintSolverIterations())
        assertFailsWith<ValueOutOfRangeException> { settings.setPositionConstraintSolverIterations(-3) }
        assertFailsWith<ValueOutOfRangeException> { settings.setPositionConstraintSolverIterations(0) }
        assertTrue(settings.isAtRestDetectionEnabled())
        settings.setAtRestDetectionEnabled(false)
        assertFalse(settings.isAtRestDetectionEnabled())
        settings.setAtRestDetectionEnabled(true)
        assertTrue(settings.isAtRestDetectionEnabled())
        assertTrue(settings.isWarmStartingEnabled())
        settings.setWarmStartingEnabled(false)
        assertFalse(settings.isWarmStartingEnabled())
        settings.setWarmStartingEnabled(true)
        assertTrue(settings.isWarmStartingEnabled())
        settings.setContinuousDetectionMode(ContinuousDetectionMode.NONE)
        assertEquals(ContinuousDetectionMode.NONE, settings.getContinuousDetectionMode())
        settings.setContinuousDetectionMode(ContinuousDetectionMode.ALL)
        assertEquals(ContinuousDetectionMode.ALL, settings.getContinuousDetectionMode())
        assertFailsWith<ArgumentNullException> { settings.setContinuousDetectionMode(null) }
        assertTrue(settings.toString().isNotEmpty())
    }

    @Test
    fun settingsCopySetAndResetPreserveValues() {
        val settings = Settings()
        settings.setStepFrequency(Settings.DEFAULT_STEP_FREQUENCY * 2.0)
        settings.setAngularTolerance(Settings.DEFAULT_ANGULAR_TOLERANCE * 2.0)
        settings.setBaumgarte(Settings.DEFAULT_BAUMGARTE * 2.0)
        settings.setLinearTolerance(Settings.DEFAULT_LINEAR_TOLERANCE * 2.0)
        settings.setMaximumAngularCorrection(Settings.DEFAULT_MAXIMUM_ANGULAR_CORRECTION * 2.0)
        settings.setMaximumAtRestAngularVelocity(Settings.DEFAULT_MAXIMUM_AT_REST_ANGULAR_VELOCITY * 2.0)
        settings.setMaximumAtRestLinearVelocity(Settings.DEFAULT_MAXIMUM_AT_REST_LINEAR_VELOCITY * 2.0)
        settings.setMaximumLinearCorrection(Settings.DEFAULT_MAXIMUM_LINEAR_CORRECTION * 2.0)
        settings.setMaximumRotation(Settings.DEFAULT_MAXIMUM_ROTATION * 2.0)
        settings.setMaximumTranslation(Settings.DEFAULT_MAXIMUM_TRANSLATION * 2.0)
        settings.setMaximumWarmStartDistance(Settings.DEFAULT_MAXIMUM_WARM_START_DISTANCE * 2.0)
        settings.setMinimumAtRestTime(Settings.DEFAULT_MINIMUM_AT_REST_TIME * 2.0)
        settings.setPositionConstraintSolverIterations(Settings.DEFAULT_POSITION_CONSTRAINT_SOLVER_ITERATIONS * 2)
        settings.setVelocityConstraintSolverIterations(Settings.DEFAULT_VELOCITY_CONSTRAINT_SOLVER_ITERATIONS * 2)
        settings.setAtRestDetectionEnabled(false)
        settings.setWarmStartingEnabled(false)
        settings.setContinuousDetectionMode(ContinuousDetectionMode.NONE)
        val assigned = Settings()
        assigned.set(settings)
        assertChangedSettings(assigned)
        val copy = settings.copy()
        assertNotSame(settings, copy)
        assertChangedSettings(copy)
        val wrongAssignment = settings.copy()
        wrongAssignment.setAngularTolerance(Settings.DEFAULT_ANGULAR_TOLERANCE)
        assertFailsWith<AssertionError> { assertChangedSettings(wrongAssignment) }
        assertFailsWith<NullPointerException> { assigned.set(null) }
        settings.reset()
        assertEquals(Settings.DEFAULT_STEP_FREQUENCY, settings.getStepFrequency())
        assertEquals(Settings.DEFAULT_MAXIMUM_TRANSLATION, settings.getMaximumTranslation())
        assertTrue(settings.isWarmStartingEnabled())
    }
}
