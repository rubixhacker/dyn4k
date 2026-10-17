package org.dyn4j.dynamics

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith
import kotlin.test.assertNotSame
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2
import org.dyn4j.exception.ValueOutOfRangeException

class BodyJourneyTest {
    @Test
    fun forceAndFixtureStateIsLive() {
        val body = Body()
        val fixtures = body.getFixtures()
        val fixture = body.addFixture(Circle(1.0))
        assertSame(fixture, fixtures.single())
        body.setMass(MassType.NORMAL)
        val force = Force(Vector2(2.0, 3.0))
        body.applyForce(force)
        assertEquals(2.0, body.getAccumulatedForce().x)
        assertEquals(3.0, body.getAccumulatedForce().y)
        body.setAtRest(true)
        body.applyImpulse(Vector2(1.0, 0.0))
        assertFalse(body.isAtRest())
        assertTrue(body.getLinearVelocity().x > 0.0)
    }

    @Test
    fun accumulatedForceCallbackAndDampingFollowTheStep() {
        val body = Body()
        body.addFixture(Circle(1.0))
        body.setMass(MassType.NORMAL)
        val force = object : Force(4.0, 0.0) {
            var calls = 0
            override fun isComplete(elapsedTime: Double): Boolean {
                assertEquals(0.5, elapsedTime)
                calls++
                return calls == 2
            }
        }
        body.applyForce(force)
        body.setLinearDamping(1.0)
        body.integrateVelocity(Vector2(), TimeStep(0.5), Settings())
        assertEquals(1, force.calls)
        assertEquals(4.0, body.getAccumulatedForce().x)
        assertEquals(4.0, body.getForce().x)
        body.integrateVelocity(Vector2(), TimeStep(0.5), Settings())
        assertEquals(2, force.calls)
        assertEquals(0.0, body.getAccumulatedForce().x)
    }

    @Test
    fun massAndRestStateTrackFixtureChanges() {
        val body = Body()
        assertTrue(body.isStatic())
        val fixture = body.addFixture(Circle(1.0))
        body.setMass(MassType.NORMAL)
        assertTrue(body.isDynamic())
        val mass = body.getMass()
        assertSame(mass, body.getMass())
        body.setAtRest(true)
        fixture.setDensity(2.0)
        body.updateMass()
        assertFalse(body.isAtRest())
        assertTrue(body.getMass().getMass() > mass.getMass())
        assertNotSame(fixture, body.copy().getFixture(0))
        body.removeFixture(fixture)
        body.updateMass()
        assertTrue(body.isStatic())
    }

    @Test
    fun settingsAndTimestepExposeValidatedState() {
        val settings = Settings()
        settings.setMaximumTranslation(3.0)
        assertEquals(9.0, settings.getMaximumTranslationSquared())
        assertFailsWith<ValueOutOfRangeException> { settings.setMaximumTranslation(-1.0) }
        assertEquals(3.0, settings.getMaximumTranslation())
        val copy = settings.copy()
        assertNotSame(settings, copy)
        assertEquals(9.0, copy.getMaximumTranslationSquared())
        settings.reset()
        assertEquals(Settings.DEFAULT_MAXIMUM_TRANSLATION, settings.getMaximumTranslation())

        val step = TimeStep(0.5)
        step.update(0.25)
        assertEquals(0.5, step.getDeltaTimeRatio())
        assertEquals(0.5, step.getPrevousDeltaTime())
        assertFailsWith<ValueOutOfRangeException> { step.update(0.0) }
        assertEquals(0.25, step.getDeltaTime())
    }

    @Test
    fun restThresholdsCallBothOverriddenGetters() {
        val body = Body()
        body.addFixture(Circle(1.0))
        body.setMass(MassType.NORMAL)
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
    }
}
