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
import org.dyn4j.collision.CollisionItem
import org.dyn4j.collision.broadphase.CollisionBodyBroadphaseFilter
import org.dyn4j.collision.broadphase.CollisionItemAABBProducer
import org.dyn4j.collision.broadphase.CollisionItemBroadphaseDetectorAdapter
import org.dyn4j.collision.broadphase.CollisionItemBroadphaseFilter
import org.dyn4j.collision.broadphase.DynamicAABBTree
import org.dyn4j.collision.broadphase.StaticValueAABBExpansionMethod
import org.dyn4j.collision.narrowphase.Gjk
import org.dyn4j.collision.narrowphase.Penetration
import org.dyn4j.collision.narrowphase.Sat
import org.dyn4j.collision.narrowphase.Separation
import org.dyn4j.world.World
import org.dyn4j.world.PhysicsBodySweptAABBProducer
import org.dyn4j.dynamics.BodyFixture
import kotlin.math.PI
import kotlin.test.Test
import kotlin.test.assertEquals

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
        for ((scaleIndex, scale) in listOf(0.01, 1.0, 100.0).withIndex()) for ((originIndex, origin) in listOf(
            0.0 to 0.0, 1000.0 to 1000.0, -1000.0 to 1000.0,
            1000000.0 to -1000000.0, -1000000.0 to 1000000.0).withIndex())
            for ((deltaIndex, delta) in listOf(-1e-8, -1e-12, 0.0, 1e-12, 1e-8).withIndex()) {
            val (ox, oy) = origin
            val world = World<Body>()
            world.setGravity(0.0, 0.0)
            val first = body(world, Geometry.createCircle(scale), ox, oy, true)
            val second = body(world, Geometry.createCircle(0.5 * scale),
                ox + scale * (1.5 + delta), oy, false)
            recorder.capture(CaseSpec("geometry-boundary-s$scaleIndex-o$originIndex-d$deltaIndex", "geometry-collision",
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
        for (hz in listOf(30, 60, 120)) for ((restitutionIndex, restitution) in listOf(0.0, 0.5, 1.0).withIndex()) {
            val bounceWorld = World<Body>()
            bounceWorld.setGravity(0.0, -9.8)
            val ground = body(bounceWorld, Geometry.createRectangle(20.0, 0.5), 0.0, -0.25, true)
            val ball = body(bounceWorld, Geometry.createCircle(0.5), 0.0, 2.0, false)
            ground.getFixture(0).setRestitution(restitution)
            ball.getFixture(0).setRestitution(restitution)
            ground.getFixture(0).setRestitutionVelocity(0.0)
            ball.getFixture(0).setRestitutionVelocity(0.0)
            recorder.capture(CaseSpec("motion-restitution-e$restitutionIndex-$hz", "free-motion",
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

    private fun configuredContacts(outerHz: Int, group: Int, repetition: Int) {
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

    @Test fun configured30Repeat1() = configuredContacts(30, 4, 1)
    @Test fun configured30Repeat2() = configuredContacts(30, 4, 2)
    @Test fun configured60Repeat1() = configuredContacts(60, 2, 1)
    @Test fun configured60Repeat2() = configuredContacts(60, 2, 2)
    @Test fun configured120Repeat1() = configuredContacts(120, 1, 1)
    @Test fun configured120Repeat2() = configuredContacts(120, 1, 2)

    private fun joint(type: String, mode: String, a: Body, b: Body): Joint<Body> {
        val active = mode == "active"
        return when (type) {
            "Angle" -> AngleJoint(a, b).apply { if (active) setLimitsEnabled(-PI / 6, PI / 6) }
            "Distance" -> DistanceJoint(a, b, a.getWorldCenter(), b.getWorldCenter()).apply {
                if (active) { setSpringEnabled(true); setSpringFrequency(8.0); setLimitsEnabled(1.0, 3.0) }
            }
            "Friction" -> FrictionJoint(a, b, b.getWorldCenter()).apply {
                if (active) { setMaximumForce(20.0); setMaximumTorque(0.5) }
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
        weldWorld.setGravity(0.0, -9.8)
        val weldGround = body(weldWorld, Geometry.createRectangle(10.0, 0.5), 0.0, 0.0, true, 0.0)
        val weldBody = body(weldWorld, Geometry.createCircle(0.5), 0.0, 2.0, false, 0.0)
        weldBody.removeAllFixtures()
        weldBody.addFixture(Geometry.createRectangle(1.0, 0.5)).setFriction(0.0)
        weldBody.setMass(MassType.NORMAL)
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
        recorder.prepareFrozenContinuation(pulleyWorld,
            "body2.setLinearVelocity(0,10) before source step2") {
            second.setLinearVelocity(0.0, 10.0)
        }
        recorder.capture(CaseSpec("P-JINT-Pulley-slack-transition-preparation-1",
            "joints-limits-motors", "frozen-weld-pulley", 60, 2,
            mapOf("jointType" to "Pulley", "segment" to "preparation-1",
                "sourceVelocity" to listOf(0.0, 10.0)), startStep = 1), pulleyWorld)
        recorder.prepareFrozenContinuation(pulleyWorld, "no inter-segment action") { }
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

    private val booleanJointFields = mapOf(
        "Angle" to listOf("LimitsEnabled"),
        "Distance" to listOf("LimitsEnabled", "LowerLimitEnabled", "UpperLimitEnabled",
            "SpringEnabled", "SpringDamperEnabled", "MaximumSpringForceEnabled"),
        "Pin" to listOf("SpringEnabled", "SpringDamperEnabled", "MaximumSpringForceEnabled"),
        "Prismatic" to listOf("LimitsEnabled", "LowerLimitEnabled", "UpperLimitEnabled",
            "MotorEnabled", "MaximumMotorForceEnabled", "SpringEnabled",
            "SpringDamperEnabled", "MaximumSpringForceEnabled"),
        "Pulley" to listOf("SlackEnabled"),
        "Revolute" to listOf("LimitsEnabled", "MotorEnabled", "MaximumMotorTorqueEnabled"),
        "Weld" to listOf("LimitsEnabled", "SpringEnabled", "SpringDamperEnabled",
            "MaximumSpringTorqueEnabled"),
        "Wheel" to listOf("LimitsEnabled", "LowerLimitEnabled", "UpperLimitEnabled",
            "MotorEnabled", "MaximumMotorTorqueEnabled", "SpringEnabled",
            "SpringDamperEnabled", "MaximumSpringForceEnabled"),
    )

    private fun setBooleanMode(joint: Joint<Body>, field: String, value: Boolean) {
        when (field) {
            "LimitsEnabled" -> when (joint) {
                is AngleJoint<*> -> joint.setLimitsEnabled(value)
                is DistanceJoint<*> -> joint.setLimitsEnabled(value)
                is PrismaticJoint<*> -> joint.setLimitsEnabled(value)
                is RevoluteJoint<*> -> joint.setLimitsEnabled(value)
                is WeldJoint<*> -> joint.setLimitsEnabled(value)
                is WheelJoint<*> -> joint.setLimitsEnabled(value)
                else -> error("unsupported limits mode")
            }
            "LowerLimitEnabled" -> when (joint) {
                is DistanceJoint<*> -> joint.setLowerLimitEnabled(value)
                is PrismaticJoint<*> -> joint.setLowerLimitEnabled(value)
                is WheelJoint<*> -> joint.setLowerLimitEnabled(value)
                else -> error("unsupported lower limit mode")
            }
            "UpperLimitEnabled" -> when (joint) {
                is DistanceJoint<*> -> joint.setUpperLimitEnabled(value)
                is PrismaticJoint<*> -> joint.setUpperLimitEnabled(value)
                is WheelJoint<*> -> joint.setUpperLimitEnabled(value)
                else -> error("unsupported upper limit mode")
            }
            "MotorEnabled" -> when (joint) {
                is PrismaticJoint<*> -> joint.setMotorEnabled(value)
                is RevoluteJoint<*> -> joint.setMotorEnabled(value)
                is WheelJoint<*> -> joint.setMotorEnabled(value)
                else -> error("unsupported motor mode")
            }
            "MaximumMotorForceEnabled" -> (joint as PrismaticJoint<*>).setMaximumMotorForceEnabled(value)
            "MaximumMotorTorqueEnabled" -> when (joint) {
                is RevoluteJoint<*> -> joint.setMaximumMotorTorqueEnabled(value)
                is WheelJoint<*> -> joint.setMaximumMotorTorqueEnabled(value)
                else -> error("unsupported motor torque mode")
            }
            "SpringEnabled" -> when (joint) {
                is DistanceJoint<*> -> joint.setSpringEnabled(value)
                is PinJoint<*> -> joint.setSpringEnabled(value)
                is PrismaticJoint<*> -> joint.setSpringEnabled(value)
                is WeldJoint<*> -> joint.setSpringEnabled(value)
                is WheelJoint<*> -> joint.setSpringEnabled(value)
                else -> error("unsupported spring mode")
            }
            "SpringDamperEnabled" -> when (joint) {
                is DistanceJoint<*> -> joint.setSpringDamperEnabled(value)
                is PinJoint<*> -> joint.setSpringDamperEnabled(value)
                is PrismaticJoint<*> -> joint.setSpringDamperEnabled(value)
                is WeldJoint<*> -> joint.setSpringDamperEnabled(value)
                is WheelJoint<*> -> joint.setSpringDamperEnabled(value)
                else -> error("unsupported spring damper mode")
            }
            "MaximumSpringForceEnabled" -> when (joint) {
                is DistanceJoint<*> -> joint.setMaximumSpringForceEnabled(value)
                is PinJoint<*> -> joint.setMaximumSpringForceEnabled(value)
                is PrismaticJoint<*> -> joint.setMaximumSpringForceEnabled(value)
                is WheelJoint<*> -> joint.setMaximumSpringForceEnabled(value)
                else -> error("unsupported spring force mode")
            }
            "MaximumSpringTorqueEnabled" -> (joint as WeldJoint<*>).setMaximumSpringTorqueEnabled(value)
            "SlackEnabled" -> (joint as PulleyJoint<*>).setSlackEnabled(value)
            else -> error("unknown joint mode $field")
        }
    }

    @Test
    fun independentJointBooleanModes() {
        for ((type, fields) in booleanJointFields) for (field in fields)
            for (variant in listOf("false", "true", "toggle")) {
                val world = World<Body>()
                world.setGravity(0.0, 0.0)
                val ground = body(world, Geometry.createRectangle(10.0, 0.5), 0.0, 0.0, true)
                val moving = body(world, Geometry.createCircle(0.5), 0.0, 2.0, false)
                val selected = joint(type, "active", ground, moving)
                world.addJoint(selected)
                val initialValue = variant == "true"
                setBooleanMode(selected, field, initialValue)
                recorder.capture(CaseSpec("joint-$type-$field-$variant", "joints-limits-motors",
                    "default", 60, 600, mapOf("jointType" to type, "field" to field,
                        "variant" to variant, "initialValue" to initialValue)), world) { step, _ ->
                    if (variant == "toggle" && (step == 201 || step == 401)) {
                        setBooleanMode(selected, field, step == 201)
                        "set$field(${step == 201})"
                    } else null
                }
            }
    }

    private val numericJointFields = mapOf(
        "Angle" to mapOf("Ratio" to listOf(0.5, 1.0, 2.0, -1.0)),
        "Distance" to mapOf("SpringDampingRatio" to listOf(0.0, 0.2, 1.0),
            "SpringFrequency" to listOf(2.0, 8.0), "MaximumSpringForce" to listOf(0.0, 10.0, 1000.0)),
        "Friction" to mapOf("MaximumForce" to listOf(0.0, 10.0, 1000.0),
            "MaximumTorque" to listOf(0.0, 0.25, 10.0)),
        "Motor" to mapOf("CorrectionFactor" to listOf(0.0, 0.3, 1.0),
            "MaximumForce" to listOf(0.0, 10.0, 1000.0), "MaximumTorque" to listOf(0.0, 0.25, 10.0)),
        "Pin" to mapOf("SpringDampingRatio" to listOf(0.0, 0.2, 1.0),
            "SpringFrequency" to listOf(2.0, 8.0), "CorrectionFactor" to listOf(0.0, 0.3, 1.0),
            "MaximumSpringForce" to listOf(0.0, 10.0, 1000.0),
            "MaximumCorrectionForce" to listOf(0.0, 10.0, 1000.0)),
        "Prismatic" to mapOf("SpringDampingRatio" to listOf(0.0, 0.2, 1.0),
            "SpringFrequency" to listOf(2.0, 8.0), "MaximumSpringForce" to listOf(0.0, 10.0, 1000.0),
            "MaximumMotorForce" to listOf(0.0, 10.0, 1000.0), "MotorSpeed" to listOf(-1.0, 0.0, 1.0)),
        "Pulley" to mapOf("Ratio" to listOf(0.5, 1.0, 2.0)),
        "Revolute" to mapOf("MaximumMotorTorque" to listOf(0.0, 0.25, 10.0),
            "MotorSpeed" to listOf(-PI / 2, 0.0, PI / 2)),
        "Weld" to mapOf("SpringDampingRatio" to listOf(0.0, 0.2, 1.0),
            "SpringFrequency" to listOf(2.0, 8.0), "MaximumSpringTorque" to listOf(0.0, 0.25, 10.0)),
        "Wheel" to mapOf("SpringDampingRatio" to listOf(0.0, 0.2, 1.0),
            "SpringFrequency" to listOf(2.0, 8.0), "MaximumSpringForce" to listOf(0.0, 10.0, 1000.0),
            "MaximumMotorTorque" to listOf(0.0, 0.25, 10.0),
            "MotorSpeed" to listOf(-PI / 2, 0.0, PI / 2)),
    )

    private fun numericJointCaseId(type: String, field: String, value: Double) =
        "joint-$type-$field-${numericJointCaseLabel(value)}"

    private fun numericJointCaseLabel(value: Double) = when (value) {
        0.0 -> "0.0"
        0.2 -> "0.2"
        0.25 -> "0.25"
        0.3 -> "0.3"
        0.5 -> "0.5"
        1.0 -> "1.0"
        2.0 -> "2.0"
        8.0 -> "8.0"
        10.0 -> "10.0"
        1000.0 -> "1000.0"
        -1.0 -> "-1.0"
        -PI / 2 -> "-1.5707963267948966"
        PI / 2 -> "1.5707963267948966"
        else -> error("unsupported numeric joint case value: $value")
    }

    @Test
    fun numericAndLimitJointCaseIdsMatchPinnedBaseline() {
        val numericIds = numericJointFields.flatMap { (type, fields) ->
            fields.flatMap { (field, values) ->
                values.map { value -> numericJointCaseId(type, field, value) }
            }
        }
        val limitIds = listOf("Angle", "Distance", "Prismatic", "Revolute", "Weld", "Wheel")
            .flatMap { type -> listOf("range", "equal").map { variant ->
                "joint-$type-limits-$variant"
            } }

        assertEquals(pinnedNumericAndLimitCaseIds, numericIds + limitIds)
    }

    private val pinnedNumericAndLimitCaseIds = """
        joint-Angle-Ratio-0.5
        joint-Angle-Ratio-1.0
        joint-Angle-Ratio-2.0
        joint-Angle-Ratio--1.0
        joint-Distance-SpringDampingRatio-0.0
        joint-Distance-SpringDampingRatio-0.2
        joint-Distance-SpringDampingRatio-1.0
        joint-Distance-SpringFrequency-2.0
        joint-Distance-SpringFrequency-8.0
        joint-Distance-MaximumSpringForce-0.0
        joint-Distance-MaximumSpringForce-10.0
        joint-Distance-MaximumSpringForce-1000.0
        joint-Friction-MaximumForce-0.0
        joint-Friction-MaximumForce-10.0
        joint-Friction-MaximumForce-1000.0
        joint-Friction-MaximumTorque-0.0
        joint-Friction-MaximumTorque-0.25
        joint-Friction-MaximumTorque-10.0
        joint-Motor-CorrectionFactor-0.0
        joint-Motor-CorrectionFactor-0.3
        joint-Motor-CorrectionFactor-1.0
        joint-Motor-MaximumForce-0.0
        joint-Motor-MaximumForce-10.0
        joint-Motor-MaximumForce-1000.0
        joint-Motor-MaximumTorque-0.0
        joint-Motor-MaximumTorque-0.25
        joint-Motor-MaximumTorque-10.0
        joint-Pin-SpringDampingRatio-0.0
        joint-Pin-SpringDampingRatio-0.2
        joint-Pin-SpringDampingRatio-1.0
        joint-Pin-SpringFrequency-2.0
        joint-Pin-SpringFrequency-8.0
        joint-Pin-CorrectionFactor-0.0
        joint-Pin-CorrectionFactor-0.3
        joint-Pin-CorrectionFactor-1.0
        joint-Pin-MaximumSpringForce-0.0
        joint-Pin-MaximumSpringForce-10.0
        joint-Pin-MaximumSpringForce-1000.0
        joint-Pin-MaximumCorrectionForce-0.0
        joint-Pin-MaximumCorrectionForce-10.0
        joint-Pin-MaximumCorrectionForce-1000.0
        joint-Prismatic-SpringDampingRatio-0.0
        joint-Prismatic-SpringDampingRatio-0.2
        joint-Prismatic-SpringDampingRatio-1.0
        joint-Prismatic-SpringFrequency-2.0
        joint-Prismatic-SpringFrequency-8.0
        joint-Prismatic-MaximumSpringForce-0.0
        joint-Prismatic-MaximumSpringForce-10.0
        joint-Prismatic-MaximumSpringForce-1000.0
        joint-Prismatic-MaximumMotorForce-0.0
        joint-Prismatic-MaximumMotorForce-10.0
        joint-Prismatic-MaximumMotorForce-1000.0
        joint-Prismatic-MotorSpeed--1.0
        joint-Prismatic-MotorSpeed-0.0
        joint-Prismatic-MotorSpeed-1.0
        joint-Pulley-Ratio-0.5
        joint-Pulley-Ratio-1.0
        joint-Pulley-Ratio-2.0
        joint-Revolute-MaximumMotorTorque-0.0
        joint-Revolute-MaximumMotorTorque-0.25
        joint-Revolute-MaximumMotorTorque-10.0
        joint-Revolute-MotorSpeed--1.5707963267948966
        joint-Revolute-MotorSpeed-0.0
        joint-Revolute-MotorSpeed-1.5707963267948966
        joint-Weld-SpringDampingRatio-0.0
        joint-Weld-SpringDampingRatio-0.2
        joint-Weld-SpringDampingRatio-1.0
        joint-Weld-SpringFrequency-2.0
        joint-Weld-SpringFrequency-8.0
        joint-Weld-MaximumSpringTorque-0.0
        joint-Weld-MaximumSpringTorque-0.25
        joint-Weld-MaximumSpringTorque-10.0
        joint-Wheel-SpringDampingRatio-0.0
        joint-Wheel-SpringDampingRatio-0.2
        joint-Wheel-SpringDampingRatio-1.0
        joint-Wheel-SpringFrequency-2.0
        joint-Wheel-SpringFrequency-8.0
        joint-Wheel-MaximumSpringForce-0.0
        joint-Wheel-MaximumSpringForce-10.0
        joint-Wheel-MaximumSpringForce-1000.0
        joint-Wheel-MaximumMotorTorque-0.0
        joint-Wheel-MaximumMotorTorque-0.25
        joint-Wheel-MaximumMotorTorque-10.0
        joint-Wheel-MotorSpeed--1.5707963267948966
        joint-Wheel-MotorSpeed-0.0
        joint-Wheel-MotorSpeed-1.5707963267948966
        joint-Angle-limits-range
        joint-Angle-limits-equal
        joint-Distance-limits-range
        joint-Distance-limits-equal
        joint-Prismatic-limits-range
        joint-Prismatic-limits-equal
        joint-Revolute-limits-range
        joint-Revolute-limits-equal
        joint-Weld-limits-range
        joint-Weld-limits-equal
        joint-Wheel-limits-range
        joint-Wheel-limits-equal
    """.trimIndent().lines()

    private fun setNumericMode(joint: Joint<Body>, field: String, value: Double) {
        when (field) {
            "Ratio" -> when (joint) {
                is AngleJoint<*> -> joint.setRatio(value)
                is PulleyJoint<*> -> joint.setRatio(value)
                else -> error("unsupported ratio mode")
            }
            "SpringDampingRatio" -> when (joint) {
                is DistanceJoint<*> -> joint.setSpringDampingRatio(value)
                is PinJoint<*> -> joint.setSpringDampingRatio(value)
                is PrismaticJoint<*> -> joint.setSpringDampingRatio(value)
                is WeldJoint<*> -> joint.setSpringDampingRatio(value)
                is WheelJoint<*> -> joint.setSpringDampingRatio(value)
                else -> error("unsupported spring damping mode")
            }
            "SpringFrequency" -> when (joint) {
                is DistanceJoint<*> -> joint.setSpringFrequency(value)
                is PinJoint<*> -> joint.setSpringFrequency(value)
                is PrismaticJoint<*> -> joint.setSpringFrequency(value)
                is WeldJoint<*> -> joint.setSpringFrequency(value)
                is WheelJoint<*> -> joint.setSpringFrequency(value)
                else -> error("unsupported spring frequency mode")
            }
            "CorrectionFactor" -> when (joint) {
                is MotorJoint<*> -> joint.setCorrectionFactor(value)
                is PinJoint<*> -> joint.setCorrectionFactor(value)
                else -> error("unsupported correction mode")
            }
            "MaximumForce" -> when (joint) {
                is FrictionJoint<*> -> joint.setMaximumForce(value)
                is MotorJoint<*> -> joint.setMaximumForce(value)
                else -> error("unsupported maximum force mode")
            }
            "MaximumSpringForce" -> when (joint) {
                is DistanceJoint<*> -> joint.setMaximumSpringForce(value)
                is PinJoint<*> -> joint.setMaximumSpringForce(value)
                is PrismaticJoint<*> -> joint.setMaximumSpringForce(value)
                is WheelJoint<*> -> joint.setMaximumSpringForce(value)
                else -> error("unsupported spring force mode")
            }
            "MaximumMotorForce" -> (joint as PrismaticJoint<*>).setMaximumMotorForce(value)
            "MaximumCorrectionForce" -> (joint as PinJoint<*>).setMaximumCorrectionForce(value)
            "MaximumTorque" -> when (joint) {
                is FrictionJoint<*> -> joint.setMaximumTorque(value)
                is MotorJoint<*> -> joint.setMaximumTorque(value)
                else -> error("unsupported maximum torque mode")
            }
            "MaximumSpringTorque" -> (joint as WeldJoint<*>).setMaximumSpringTorque(value)
            "MaximumMotorTorque" -> when (joint) {
                is RevoluteJoint<*> -> joint.setMaximumMotorTorque(value)
                is WheelJoint<*> -> joint.setMaximumMotorTorque(value)
                else -> error("unsupported motor torque mode")
            }
            "MotorSpeed" -> when (joint) {
                is PrismaticJoint<*> -> joint.setMotorSpeed(value)
                is RevoluteJoint<*> -> joint.setMotorSpeed(value)
                is WheelJoint<*> -> joint.setMotorSpeed(value)
                else -> error("unsupported motor speed mode")
            }
            else -> error("unknown joint value $field")
        }
    }

    @Test
    fun independentJointNumericAndLimitModes() {
        fun seed(type: String): Pair<World<Body>, Joint<Body>> {
            val world = World<Body>()
            world.setGravity(0.0, 0.0)
            val ground = body(world, Geometry.createRectangle(10.0, 0.5), 0.0, 0.0, true)
            val moving = body(world, Geometry.createCircle(0.5), 0.0, 2.0, false)
            val selected = joint(type, "active", ground, moving)
            world.addJoint(selected)
            return world to selected
        }
        for ((type, fields) in numericJointFields) for ((field, values) in fields)
            for (value in values) {
                val (world, selected) = seed(type)
                if (type == "Pin" && field in listOf("CorrectionFactor", "MaximumCorrectionForce"))
                    (selected as PinJoint<*>).setSpringEnabled(false)
                setNumericMode(selected, field, value)
                recorder.capture(CaseSpec(numericJointCaseId(type, field, value), "joints-limits-motors",
                    "default", 60, 600, mapOf("jointType" to type, "field" to field,
                        "initialValue" to value)), world)
            }
        for (type in listOf("Angle", "Distance", "Prismatic", "Revolute", "Weld", "Wheel"))
            for (variant in listOf("range", "equal")) {
                val (world, selected) = seed(type)
                val limit = if (type in listOf("Angle", "Revolute", "Weld")) PI / 6 else 1.0
                val lower = if (variant == "range") { if (type == "Distance") 1.0 else -limit } else 0.0
                val upper = if (variant == "range") { if (type == "Distance") 3.0 else limit } else 0.0
                when (selected) {
                    is AngleJoint<*> -> selected.setLimitsEnabled(lower, upper)
                    is DistanceJoint<*> -> selected.setLimitsEnabled(lower, upper)
                    is PrismaticJoint<*> -> selected.setLimitsEnabled(lower, upper)
                    is RevoluteJoint<*> -> selected.setLimitsEnabled(lower, upper)
                    is WeldJoint<*> -> selected.setLimitsEnabled(lower, upper)
                    is WheelJoint<*> -> selected.setLimitsEnabled(lower, upper)
                    else -> error("unsupported joint limits")
                }
                recorder.capture(CaseSpec("joint-$type-limits-$variant", "joints-limits-motors",
                    "default", 60, 600, mapOf("jointType" to type, "limits" to variant,
                        "lowerLimit" to lower, "upperLimit" to upper)), world)
            }
    }

    @Test
    fun baselineAngleNegativeRatioRemainsAnIsolatedPhysicalFailure() {
        val world = World<Body>()
        world.setGravity(0.0, 0.0)
        val first = body(world, Geometry.createCircle(0.5), 0.0, 0.0, false)
        val second = body(world, Geometry.createCircle(0.5), 0.0, 2.0, false)
        second.setAngularVelocity(-PI / 6)
        val joint = AngleJoint(first, second)
        joint.setLimitsEnabled(false)
        joint.setRatio(-1.0)
        world.addJoint(joint)
        recorder.capture(CaseSpec("P-J-Angle-ratio-limits-off--1.0", "joints-limits-motors",
            "baseline-failed", 60, 600,
            mapOf("jointType" to "Angle", "ratio" to -1.0, "limitsEnabled" to false)), world)
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
        world.setBroadphaseDetector(CollisionItemBroadphaseDetectorAdapter(
            DynamicAABBTree<CollisionItem<Body, BodyFixture>>(
                CollisionItemBroadphaseFilter(), CollisionItemAABBProducer(),
                StaticValueAABBExpansionMethod(0.2))))
        world.setContinuousCollisionDetectionBroadphaseDetector(DynamicAABBTree<Body>(
            CollisionBodyBroadphaseFilter(), PhysicsBodySweptAABBProducer(),
            StaticValueAABBExpansionMethod(0.2)))
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
