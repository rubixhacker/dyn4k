package io.github.rubixhacker.dyn4k

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertEquals
import kotlin.test.assertSame
import kotlin.test.assertTrue

val DynamicsTest by testSuite {
    test("kotlinNamesShareTheBodyAndFixture") { DynamicsTestFixture().run { kotlinNamesShareTheBodyAndFixture() } }
}

private class DynamicsTestFixture  {
fun kotlinNamesShareTheBodyAndFixture() {
        val body: Body = Body()
        val compatibility: org.dyn4j.dynamics.PhysicsBody = body
        val fixture = body.addFixture(Circle(1.0))
        assertSame(fixture, compatibility.getFixture(0))
        compatibility.setMass(MassType.NORMAL)
        body.applyForce(Vector2(2.0, 0.0))
        assertEquals(2.0, compatibility.getAccumulatedForce().x)
        compatibility.applyImpulse(Vector2(1.0, 0.0))
        assertTrue(body.getLinearVelocity().x > 0.0)
    }
}
