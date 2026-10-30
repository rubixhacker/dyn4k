package portable

import de.infix.testBalloon.framework.core.testSuite
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardOpenOption.CREATE_NEW
import java.nio.file.StandardOpenOption.WRITE
import java.security.MessageDigest
import org.dyn4j.dynamics.Body
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2
import org.dyn4j.dynamics.joint.PulleyJoint
import org.dyn4j.world.World

val PulleyPreparationJdiV1TestSuite by testSuite {
    test("capturePreparation0") { PulleyPreparationJdiV1Test().run { capturePreparation0() } }
}

class PulleyPreparationJdiV1Test {
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

fun capturePreparation0() {
        val destination = System.getenv("DYN4K_PULLEY_JDI_V1_OUTPUT")
            ?: error("one-case output directory is absent")
        val nonce = System.getenv("DYN4K_PULLEY_JDI_V1_NONCE")
            ?: error("one-case nonce is absent")
        require(nonce.matches(Regex("[0-9a-f]{64}")))
        val root = Path.of(destination)
        require(Files.isDirectory(root) && !Files.isSymbolicLink(root))
        val output = root.toRealPath()
        require(output.startsWith(Path.of(System.getProperty("user.home")).toRealPath()))
        val artifact = Path.of(PulleyJoint::class.java.protectionDomain.codeSource.location.toURI())
            .toRealPath()
        require(Files.isRegularFile(artifact) && !Files.isSymbolicLink(artifact))
        val caseFile = output.resolve("case.jsonl")
        Files.newBufferedWriter(caseFile, StandardCharsets.UTF_8, CREATE_NEW, WRITE).use { writer ->
            val recorder = NumericalRecorder { line ->
                writer.write(line)
                writer.newLine()
                writer.flush()
            }
        val pulleyWorld = World<Body>()
        body(pulleyWorld, Geometry.createRectangle(10.0, 1.0), 0.0, -1.0, true, 0.0)
        val first = body(pulleyWorld, Geometry.createCircle(0.5), -1.0, 0.0, false, 0.0)
        val second = body(pulleyWorld, Geometry.createCircle(0.5), 1.0, 0.5, false, 0.0)
        val pulley = PulleyJoint(first, second, Vector2(-1.0, 1.0), Vector2(1.0, 1.0),
            Vector2(-1.0, 0.0), Vector2(1.0, 0.5))
        pulleyWorld.addJoint(pulley)
        recorder.capture(CaseSpec("P-JINT-Pulley-slack-transition-preparation-0",
            "joints-limits-motors", "frozen-weld-pulley", 60, 1,
            mapOf("jointType" to "Pulley", "segment" to "preparation-0",
                "sourceVelocity" to listOf(0.0, 0.0))), pulleyWorld)
        }
        val pid = ProcessHandle.current().pid()
        val caseHash = sha256(caseFile)
        val artifactHash = sha256(artifact)
        val receipt = "{" +
            "\"schema\":\"pulley-preparation-worker/1\"," +
            "\"pid\":$pid," +
            "\"case_id\":\"P-JINT-Pulley-slack-transition-preparation-0\"," +
            "\"step\":1," +
            "\"nonce\":\"$nonce\"," +
            "\"case_sha256\":\"$caseHash\"," +
            "\"artifact_sha256\":\"$artifactHash\"," +
            "\"class_source_uri\":\"${artifact.toUri()}\"}\n"
        Files.writeString(output.resolve("worker.json"), receipt, StandardCharsets.UTF_8,
            CREATE_NEW, WRITE)
    }

    private fun sha256(path: Path): String {
        val digest = MessageDigest.getInstance("SHA-256")
        Files.newInputStream(path).use { stream ->
            val buffer = ByteArray(65536)
            while (true) {
                val count = stream.read(buffer)
                if (count < 0) break
                digest.update(buffer, 0, count)
            }
        }
        return digest.digest().joinToString("") {
            (it.toInt() and 0xff).toString(16).padStart(2, '0')
        }
    }
}
