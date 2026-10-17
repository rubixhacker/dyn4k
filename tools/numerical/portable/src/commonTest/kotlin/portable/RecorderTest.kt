package portable

import org.dyn4j.dynamics.Body
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.world.World
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class RecorderTest {
    @Test
    fun recordsPublicWorldStateAndSignedZeroAtEveryStep() {
        val world = World<Body>()
        world.setGravity(0.0, 0.0)
        val body = Body()
        body.addFixture(Geometry.createCircle(0.5))
        body.setMass(MassType.NORMAL)
        body.setLinearVelocity(-0.0, 1.0)
        world.addBody(body)
        val lines = mutableListOf<String>()
        NumericalRecorder(lines::add).capture(
            CaseSpec("red-green", "free-motion", "default", 60, 2,
                mapOf("velocity" to listOf(-0.0, 1.0))), world,
            observe = { mapOf("signedZero" to -0.0) }
        )
        assertTrue(lines.size >= 4)
        assertTrue(lines.first().contains("\"velocity\":[-0.0,"))
        assertTrue(lines.first().contains("\"fixtures\""))
        assertTrue(lines.first().contains("\"radius\":0.5"))
        assertTrue(lines.any { it.contains("\"kind\":\"state\"") && it.contains("\"signedZero\":-0.0") })
        assertEquals(2, lines.count { it.contains("\"kind\":\"state\"") })
        assertTrue(lines.any { it.contains("\"kind\":\"state\"") && it.contains("\"step\":1") })
        assertTrue(lines.any { it.contains("\"kind\":\"state\"") && it.contains("\"step\":2") })
        assertTrue(lines.last().contains("\"kind\":\"case-end\""))
    }
}
