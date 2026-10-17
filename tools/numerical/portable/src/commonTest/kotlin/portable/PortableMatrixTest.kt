package portable

import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.ContinuousDetectionMode
import org.dyn4j.dynamics.joint.AngleJoint
import org.dyn4j.dynamics.joint.DistanceJoint
import org.dyn4j.dynamics.joint.FrictionJoint
import org.dyn4j.dynamics.joint.Joint
import org.dyn4j.dynamics.joint.MotorJoint
import org.dyn4j.dynamics.joint.PinJoint
import org.dyn4j.dynamics.joint.PrismaticJoint
import org.dyn4j.dynamics.joint.PulleyJoint
import org.dyn4j.dynamics.joint.RevoluteJoint
import org.dyn4j.dynamics.joint.WeldJoint
import org.dyn4j.dynamics.joint.WheelJoint
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2
import org.dyn4j.collision.narrowphase.Gjk
import org.dyn4j.collision.narrowphase.Penetration
import org.dyn4j.collision.narrowphase.Sat
import org.dyn4j.collision.narrowphase.Separation
import org.dyn4j.world.World
import kotlin.math.PI
import kotlin.test.Test

class PortableMatrixTest {
    private val recorder = NumericalRecorder { println("NUMERICAL_JSON $it") }

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
    fun geometryCollisionBoundaryAndScale() {
        for (scale in listOf(0.01, 1.0, 100.0)) for ((ox, oy) in listOf(
            0.0 to 0.0, 1000.0 to 1000.0, -1000.0 to 1000.0,
            1000000.0 to -1000000.0, -1000000.0 to 1000000.0))
            for (delta in listOf(-1e-8, -1e-12, 0.0, 1e-12, 1e-8)) {
            val world = World<Body>()
            world.setGravity(0.0, 0.0)
            val first = body(world, Geometry.createCircle(scale), ox, oy, true)
            val second = body(world, Geometry.createCircle(0.5 * scale),
                ox + scale * (1.5 + delta), oy, false)
            recorder.capture(CaseSpec("geometry-boundary-s$scale-o$ox,$oy-d$delta", "geometry-collision",
                "default", 60, 1, mapOf("scale" to scale, "origin" to listOf(ox, oy),
                    "delta" to delta, "signedZero" to -0.0)), world, observe = {
                val a = first.getFixture(0).getShape()
                val b = second.getFixture(0).getShape()
                val ta = first.getTransform()
                val tb = second.getTransform()
                val satDepth = Penetration()
                val gjkDepth = Penetration()
                val separation = Separation()
                val gjk = Gjk()
                val sat = Sat()
                mapOf("sat" to mapOf("detected" to sat.detect(a, ta, b, tb, satDepth),
                    "normal" to listOf(satDepth.getNormal().x, satDepth.getNormal().y),
                    "depth" to satDepth.getDepth()),
                    "gjk" to mapOf("detected" to gjk.detect(a, ta, b, tb, gjkDepth),
                        "normal" to listOf(gjkDepth.getNormal().x, gjkDepth.getNormal().y),
                        "depth" to gjkDepth.getDepth(),
                        "distanceAvailable" to gjk.distance(a, ta, b, tb, separation),
                        "distance" to separation.getDistance(),
                        "separationNormal" to listOf(separation.getNormal().x, separation.getNormal().y)))
            })
        }
    }

    @Test
    fun freeMotionForcesDampingAndRestitution() {
        val world = World<Body>()
        world.setGravity(0.0, 0.0)
        val moving = body(world, Geometry.createCircle(0.5), 0.0, 0.0, false)
        moving.setLinearDamping(0.1)
        moving.setAngularDamping(0.1)
        recorder.capture(CaseSpec("motion-forces-60", "free-motion", "default", 60, 600,
            mapOf("force" to listOf(1.0, 0.0), "torque" to 0.25,
                "damping" to 0.1, "durationSeconds" to 10)), world) { step, _ ->
            if (step <= 60) {
                moving.applyForce(Vector2(1.0, 0.0))
                moving.applyTorque(0.25)
                "force-and-torque"
            } else null
        }
        for (hz in listOf(30, 60, 120)) for (restitution in listOf(0.0, 0.5, 1.0)) {
            val bounceWorld = World<Body>()
            bounceWorld.setGravity(0.0, -9.8)
            val ground = body(bounceWorld, Geometry.createRectangle(20.0, 0.5), 0.0, -0.25, true)
            val ball = body(bounceWorld, Geometry.createCircle(0.5), 0.0, 2.0, false)
            ground.getFixture(0).setRestitution(restitution)
            ball.getFixture(0).setRestitution(restitution)
            ground.getFixture(0).setRestitutionVelocity(0.0)
            ball.getFixture(0).setRestitutionVelocity(0.0)
            recorder.capture(CaseSpec("motion-restitution-e$restitution-$hz", "free-motion",
                "default", hz, 10 * hz, mapOf("restitution" to restitution,
                    "gravity" to listOf(0.0, -9.8), "durationSeconds" to 10)), bounceWorld)
        }
    }

    private fun sleepWorld(configured: Boolean): Pair<World<Body>, Body> {
        val world = World<Body>()
        world.setGravity(0.0, -9.8)
        if (configured) {
            world.getSettings().setLinearTolerance(1.0 / 4096.0)
            world.getSettings().setPositionConstraintSolverIterations(8)
        }
        body(world, Geometry.createRectangle(20.0, 0.5), 0.0, -0.25, true, 0.5)
        return world to body(world, Geometry.createRectangle(1.0, 1.0), 0.0, 0.51, false, 0.5)
    }

    @Test
    fun defaultContactsFrictionSleepAndWake() {
        for (hz in listOf(30, 60, 120)) {
            val (world, target) = sleepWorld(false)
            recorder.capture(CaseSpec("contacts-default-$hz", "contacts-friction-sleep-wake",
                "default", hz, 600 * hz,
                mapOf("impulse" to listOf(1.0, 0.0), "actionStep" to 300 * hz + 1,
                    "gravity" to listOf(0.0, -9.8), "friction" to 0.5)), world) { step, _ ->
                if (step == 300 * hz + 1) {
                    val sleeping = target.isAtRest()
                    target.applyImpulse(Vector2(1.0, 0.0), target.getWorldCenter())
                    "wake-impulse; sleepingBefore=$sleeping"
                } else null
            }
        }
    }

    @Test
    fun configuredContactsKeepInnerTimeAndOuterEndpointsSeparate() {
        for ((outerHz, group) in listOf(30 to 4, 60 to 2, 120 to 1)) {
            for (repetition in 1..2) {
                val (world, target) = sleepWorld(true)
                recorder.capture(CaseSpec("contacts-configured-$outerHz-r$repetition",
                    "contacts-friction-sleep-wake", "configured", 120, 72000,
                    mapOf("outerHz" to outerHz, "repetition" to repetition, "innerHz" to 120,
                        "linearTolerance" to 1.0 / 4096.0, "positionIterations" to 8,
                        "impulse" to listOf(1.0, 0.0), "actionStep" to 36001), group), world) { step, _ ->
                    if (step == 36001) {
                        val sleeping = target.isAtRest()
                        target.applyImpulse(Vector2(1.0, 0.0), target.getWorldCenter())
                        "wake-impulse; sleepingBefore=$sleeping"
                    } else null
                }
            }
        }
    }

    private fun joint(type: String, mode: String, a: Body, b: Body): Joint<Body> {
        val active = mode == "active"
        return when (type) {
            "Angle" -> AngleJoint(a, b).apply { if (active) setLimitsEnabled(-PI / 6, PI / 6) }
            "Distance" -> DistanceJoint(a, b, a.getWorldCenter(), b.getWorldCenter()).apply {
                if (active) { setSpringEnabled(true); setSpringFrequency(8.0); setLimitsEnabled(1.0, 3.0) }
            }
            "Friction" -> FrictionJoint(a, b, b.getWorldCenter()).apply {
                if (active) { setMaximumForce(10.0); setMaximumTorque(0.25) }
            }
            "Motor" -> MotorJoint(a, b).apply {
                if (active) { setLinearTarget(Vector2(0.5, 0.5)); setMaximumForce(10.0); setMaximumTorque(0.25) }
            }
            "Pin" -> PinJoint(b, b.getWorldCenter()).apply {
                if (active) { setSpringEnabled(true); setSpringFrequency(8.0); setMaximumSpringForce(10.0) }
            }
            "Prismatic" -> PrismaticJoint(a, b, b.getWorldCenter(), Vector2(1.0, 0.0)).apply {
                if (active) { setMotorEnabled(true); setMotorSpeed(1.0); setLimitsEnabled(-1.0, 1.0); setSpringEnabled(true) }
            }
            "Pulley" -> PulleyJoint(a, b, Vector2(-1.0, 3.0), Vector2(1.0, 3.0),
                a.getWorldCenter(), b.getWorldCenter()).apply {
                if (active) { setRatio(2.0); setSlackEnabled(true) }
            }
            "Revolute" -> RevoluteJoint(a, b, b.getWorldCenter()).apply {
                if (active) { setMotorEnabled(true); setMotorSpeed(PI / 2); setLimitsEnabled(-PI / 6, PI / 6) }
            }
            "Weld" -> WeldJoint(a, b, b.getWorldCenter()).apply {
                if (active) { setSpringEnabled(true); setSpringFrequency(8.0); setLimitsEnabled(-PI / 6, PI / 6) }
            }
            "Wheel" -> WheelJoint(a, b, b.getWorldCenter(), Vector2(0.0, 1.0)).apply {
                if (active) { setMotorEnabled(true); setMotorSpeed(PI / 2); setLimitsEnabled(-1.0, 5.0); setSpringEnabled(true) }
            }
            else -> error("unknown joint type $type")
        }
    }

    @Test
    fun everyJointWithInitialAndApplicableActiveModes() {
        for (type in listOf("Angle", "Distance", "Friction", "Motor", "Pin", "Prismatic",
            "Pulley", "Revolute", "Weld", "Wheel")) {
            for (mode in listOf("initial", "active")) {
                val world = World<Body>()
                world.setGravity(0.0, 0.0)
                val ground = body(world, Geometry.createRectangle(10.0, 0.5), 0.0, 0.0, true)
                val moving = body(world, Geometry.createCircle(0.5), 0.0, 2.0, false)
                val joint = joint(type, mode, ground, moving)
                world.addJoint(joint)
                recorder.capture(CaseSpec("joint-$type-$mode", "joints-limits-motors", "default",
                    60, 600, mapOf("jointType" to type, "mode" to mode, "durationSeconds" to 10)), world) { step, _ ->
                    if (mode != "active" || step != 201 && step != 401) null
                    else {
                        val reverse = step == 201
                        when (joint) {
                            is AngleJoint<*> -> joint.setLimitsEnabled(!reverse)
                            is DistanceJoint<*> -> joint.setLimitsEnabled(!reverse)
                            is FrictionJoint<*> -> joint.setMaximumForce(if (reverse) 0.0 else 10.0)
                            is PrismaticJoint<*> -> joint.setMotorSpeed(if (reverse) -1.0 else 1.0)
                            is PulleyJoint<*> -> joint.setSlackEnabled(!reverse)
                            is RevoluteJoint<*> -> joint.setMotorSpeed(if (reverse) -PI / 2 else PI / 2)
                            is WeldJoint<*> -> joint.setLimitsEnabled(!reverse)
                            is WheelJoint<*> -> joint.setMotorSpeed(if (reverse) -PI / 2 else PI / 2)
                            is MotorJoint<*> -> joint.setLinearTarget(Vector2(if (reverse) -0.5 else 0.5, 0.5))
                            is PinJoint<*> -> joint.setTarget(Vector2(if (reverse) -0.5 else 0.5, 2.0))
                        }
                        "mode-transition-$step"
                    }
                }
            }
        }
        val weldWorld = World<Body>()
        weldWorld.setGravity(0.0, 0.0)
        val weldGround = body(weldWorld, Geometry.createRectangle(10.0, 0.5), 0.0, 0.0, true, 0.0)
        val weldBody = body(weldWorld, Geometry.createRectangle(1.0, 0.5), 0.0, 2.0, false, 0.0)
        val weld = WeldJoint(weldGround, weldBody, weldBody.getWorldCenter().sum(-0.5, 0.0))
        weld.setSpringEnabled(true)
        weld.setSpringDamperEnabled(true)
        weld.setSpringDampingRatio(0.3)
        weld.setSpringFrequency(8.0)
        weld.setLimitsEnabled(0.0, 0.0)
        weldWorld.addJoint(weld)
        weldBody.applyForce(Vector2(0.0, -10.0), Vector2(0.5, 2.0))
        recorder.capture(CaseSpec("P-JINT-Weld-enabled-equal", "joints-limits-motors",
            "frozen-weld-pulley", 60, 600,
            mapOf("jointType" to "Weld", "limits" to listOf(0.0, 0.0),
                "offCenterForce" to listOf(0.0, -10.0))), weldWorld)

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
        second.setLinearVelocity(0.0, 10.0)
        recorder.capture(CaseSpec("P-JINT-Pulley-slack-transition-preparation-1",
            "joints-limits-motors", "frozen-weld-pulley", 60, 2,
            mapOf("jointType" to "Pulley", "segment" to "preparation-1",
                "sourceVelocity" to listOf(0.0, 10.0))), pulleyWorld)
        recorder.capture(CaseSpec("P-JINT-Pulley-slack-transition-main",
            "joints-limits-motors", "frozen-weld-pulley", 60, 600,
            mapOf("jointType" to "Pulley", "segment" to "main",
                "sourceVelocity" to listOf(0.0, 10.0))), pulleyWorld) { step, _ ->
            when (step) {
                201 -> { second.setLinearVelocity(0.0, 10.0); second.translate(0.0, 0.1); pulley.setSlackEnabled(true); "slack-on-and-reexcite" }
                401 -> { pulley.setSlackEnabled(false); "slack-off" }
                else -> null
            }
        }
    }

    @Test
    fun continuousCollisionCasesAtFrozenRates() {
        for (hz in listOf(30, 60, 120)) for (shape in listOf("circle", "pentagon"))
            for (mode in listOf(ContinuousDetectionMode.ALL, ContinuousDetectionMode.NONE)) {
                val world = World<Body>()
                world.setGravity(0.0, 0.0)
                world.getSettings().setContinuousDetectionMode(mode)
                body(world, Geometry.createRectangle(20.0, 0.05), 0.0, 0.0, true)
                val bullet = body(world,
                    if (shape == "circle") Geometry.createCircle(0.1) else Geometry.createUnitCirclePolygon(5, 0.1),
                    0.0, 1.0, false)
                bullet.setLinearVelocity(0.0, -120.0)
                bullet.setBullet(true)
                if (shape == "pentagon") bullet.setAngularVelocity(20.0)
                recorder.capture(CaseSpec("ccd-$shape-${mode.name}-$hz", "ccd", "default", hz, hz,
                    mapOf("shape" to shape, "mode" to mode.name, "speed" to -120.0,
                        "durationSeconds" to 1)), world)
            }
    }

    @Test
    fun longRunningFreeMotionInvariantScene() {
        val world = World<Body>()
        world.setGravity(0.0, 0.0)
        world.getSettings().setAtRestDetectionEnabled(false)
        val moving = body(world, Geometry.createCircle(0.5), 0.0, 0.0, false)
        moving.setLinearVelocity(0.25, -0.125)
        moving.setAngularVelocity(0.5)
        recorder.capture(CaseSpec("long-free-60", "long-running-invariant", "default", 60, 36000,
            mapOf("velocity" to listOf(0.25, -0.125), "angularVelocity" to 0.5,
                "durationSeconds" to 600)), world)
    }
}
