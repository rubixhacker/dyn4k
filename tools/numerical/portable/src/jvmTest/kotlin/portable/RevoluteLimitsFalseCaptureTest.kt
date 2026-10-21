package portable

import java.security.MessageDigest
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.joint.RevoluteJoint
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.RotationOperationTap
import org.dyn4j.world.World
import kotlin.math.PI
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class RevoluteLimitsFalseCaptureTest {
    private fun body(world: World<Body>, shape: Convex, x: Double, y: Double, fixed: Boolean,
                     friction: Double = 0.2): Body {
        val body = Body()
        val fixture = body.addFixture(shape)
        fixture.setDensity(1.0)
        fixture.setFriction(friction)
        fixture.setRestitution(0.0)
        body.setMass(if (fixed) MassType.INFINITE else MassType.NORMAL)
        body.setLinearDamping(0.0)
        body.setAngularDamping(0.0)
        body.translate(x, y)
        world.addBody(body)
        return body
    }

    @Test
    fun captureRevoluteLimitsFalse() {
        val rows = mutableListOf<String>()
        val recorder = NumericalRecorder { row ->
            rows.add(row)
            println("NUMERICAL_JSON $row")
        }
        RotationOperationTap.capture("independentJointBooleanModes") { capture ->
            val world = World<Body>()
            world.setGravity(0.0, 0.0)
            val ground = body(world, Geometry.createRectangle(10.0, 0.5), 0.0, 0.0, true)
            val moving = body(world, Geometry.createCircle(0.5), 0.0, 2.0, false)
            val selected = RevoluteJoint(ground, moving, moving.getWorldCenter()).apply {
                setMotorEnabled(true)
                setMotorSpeed(PI / 2)
                setLimitsEnabled(-PI / 6, PI / 6)
            }
            world.addJoint(selected)
            selected.setLimitsEnabled(false)
            recorder.capture(CaseSpec("joint-Revolute-LimitsEnabled-false", "joints-limits-motors",
                "default", 60, 600, mapOf("jointType" to "Revolute", "field" to "LimitsEnabled",
                    "variant" to "false", "initialValue" to false)), world) { _, _ -> null }
            assertTrue(capture.drain().isEmpty())
        }

        assertEquals(2403, rows.size)
        assertEquals(1, rows.count { it.contains("\"kind\":\"inputs\"") })
        assertEquals(600, rows.count { it.contains("\"kind\":\"state\"") })
        assertEquals(1, rows.count { it.contains("\"kind\":\"case-end\"") })
        assertEquals(0, rows.count { it.contains("\"kind\":\"action\"") })
        val inputSha256 = MessageDigest.getInstance("SHA-256")
            .digest((rows.first() + "\n").toByteArray(Charsets.UTF_8))
            .joinToString("") { byte -> (byte.toInt() and 0xff).toString(16).padStart(2, '0') }
        assertEquals("8966b3e0f34f2a6d442cb3b8348f4ea262186b9cd80daa5b8a7c58dbf8d8da17",
            inputSha256)
    }
}
