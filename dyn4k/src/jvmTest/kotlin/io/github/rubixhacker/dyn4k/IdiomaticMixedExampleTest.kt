package io.github.rubixhacker.dyn4k

import IdiomaticJavaExample
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertSame

class IdiomaticMixedExampleTest {
    @Test
    fun javaBodyRunsInKotlinWorldWithoutConversion() {
        val javaBody = IdiomaticJavaExample.createBody()
        val world = world {
            gravity = Vector2(0.0, 0.0)
            add(javaBody)
        }
        assertSame(javaBody, world.bodies.single())
        val live = world.bodies.single().linearVelocity
        assertSame(javaBody.getLinearVelocity(), live)
        live.x = 3.0
        val calls = intArrayOf(0)
        world.addStepListener(IdiomaticJavaExample.observeBody(javaBody, calls))
        world.step(1)
        assertEquals(1, calls[0])
        assertEquals(3.0, javaBody.getLinearVelocity().x, 1e-12)
    }
}
