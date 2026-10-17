package performance

import io.github.rubixhacker.dyn4k.AngleJoint
import io.github.rubixhacker.dyn4k.Body
import io.github.rubixhacker.dyn4k.DistanceJoint
import io.github.rubixhacker.dyn4k.FrictionJoint
import io.github.rubixhacker.dyn4k.Geometry
import io.github.rubixhacker.dyn4k.Joint
import io.github.rubixhacker.dyn4k.MassType
import io.github.rubixhacker.dyn4k.MotorJoint
import io.github.rubixhacker.dyn4k.PinJoint
import io.github.rubixhacker.dyn4k.PrismaticJoint
import io.github.rubixhacker.dyn4k.PulleyJoint
import io.github.rubixhacker.dyn4k.RevoluteJoint
import io.github.rubixhacker.dyn4k.Vector2
import io.github.rubixhacker.dyn4k.WeldJoint
import io.github.rubixhacker.dyn4k.WheelJoint
import io.github.rubixhacker.dyn4k.World
import io.github.rubixhacker.dyn4k.add
import io.github.rubixhacker.dyn4k.body
import io.github.rubixhacker.dyn4k.bullet
import io.github.rubixhacker.dyn4k.density
import io.github.rubixhacker.dyn4k.fixture
import io.github.rubixhacker.dyn4k.friction
import io.github.rubixhacker.dyn4k.joint
import io.github.rubixhacker.dyn4k.linearVelocity
import io.github.rubixhacker.dyn4k.massType
import io.github.rubixhacker.dyn4k.onContactBegin
import io.github.rubixhacker.dyn4k.onContactEnd
import io.github.rubixhacker.dyn4k.restitution
import io.github.rubixhacker.dyn4k.world
import org.dyn4j.collision.continuous.TimeOfImpact
import org.dyn4j.world.listener.TimeOfImpactListenerAdapter

internal class DirectFixture(
    val family: String,
    val variant: String,
    val count: Int,
    val hz: Int,
) {
    val world: World<Body> = world()
    val dynamic = ArrayList<Body>(count)
    private lateinit var floor: Body
    var contactBegins = 0L
        private set
    var contactEnds = 0L
        private set
    var toiEvents = 0L
        private set

    init {
        world.onContactBegin { _, _ -> contactBegins++ }
        world.onContactEnd { _, _ -> contactEnds++ }
        world.addTimeOfImpactListener(object : TimeOfImpactListenerAdapter<Body>() {
            override fun collision(body1: Body?, body2: Body?, toi: TimeOfImpact?): Boolean {
                toiEvents++
                return true
            }
        })
        when (family) {
            "separated" -> buildSeparated()
            "pile", "lifecycle" -> buildPile()
            "joint" -> buildJoint()
            "ccd" -> buildCcd()
            else -> error("unknown family: $family")
        }
        check(world.getBodyCount() >= count) { "incomplete fixture" }
    }

    private fun circle(x: Double, y: Double): Body = body {
        fixture(Geometry.createCircle(0.25)) {
            density = 1.0
            friction = 0.5
            restitution = 0.0
        }
        massType = MassType.NORMAL
        translate(x, y)
    }

    private fun staticRectangle(x: Double, y: Double, width: Double, height: Double): Body =
        world.add(body {
            fixture(Geometry.createRectangle(width, height)) {
                density = 1.0
                friction = 0.5
                restitution = 0.0
            }
            massType = MassType.INFINITE
            translate(x, y)
        })

    private fun addDynamic(body: Body) {
        dynamic.add(world.add(body))
    }

    private fun buildSeparated() {
        world.setGravity(0.0, 0.0)
        for (i in 0 until count) {
            addDynamic(circle(-48.0 + (i % 32) * 3.0, 2.0 + (i / 32) * 3.0).apply {
                linearVelocity = Vector2(0.75, 0.0)
            })
        }
    }

    private fun buildPile() {
        floor = staticRectangle(0.0, -0.5, 200.0, 1.0)
        for (i in 0 until count) {
            addDynamic(circle(((i % 10) - 4.5) * 0.48, 0.3 + (i / 10) * 0.48))
        }
        if (family == "lifecycle") {
            for (i in 0 until count step 10) attachLifecycleJoint(dynamic[i])
        }
    }

    private fun attachLifecycleJoint(body: Body) {
        world.joint(DistanceJoint(floor, body, floor.getWorldCenter(), body.getWorldCenter()))
    }

    private fun buildCcd() {
        world.setGravity(0.0, 0.0)
        staticRectangle(-10.0, 10.0, 0.5, 20.0)
        staticRectangle(10.0, 10.0, 0.5, 20.0)
        for (i in 0 until count) {
            addDynamic(circle(if (i % 2 == 0) -8.0 else 8.0, 0.5 + (i % 20) * 0.45).apply {
                bullet = true
                linearVelocity = Vector2(if (i % 2 == 0) 18.0 else -18.0, 0.0)
            })
        }
    }

    private fun buildJoint() {
        val kind = if (variant == "mixed_all_types") "mixed" else variant.substringBefore('_')
        val mode = if (variant == "mixed_all_types") "mixed" else variant.substringAfter('_')
        val kinds = arrayOf("angle", "distance", "friction", "motor", "pin", "prismatic", "pulley", "revolute", "weld", "wheel")
        for (i in 0 until count) {
            val x = i * 3.0
            val anchor = staticRectangle(x, 3.0, 0.25, 0.25)
            val moving = circle(x, 2.0).apply { setAtRestDetectionEnabled(false) }
            addDynamic(moving)
            val selected = if (kind == "mixed") kinds[i % kinds.size] else kind
            val selectedMode = if (mode == "mixed") defaultMode(selected) else mode
            world.joint(makeJoint(selected, selectedMode, anchor, moving, x))
        }
    }

    private fun defaultMode(kind: String): String = when (kind) {
        "distance", "weld" -> "rigid"
        "pin", "wheel" -> "spring"
        "pulley" -> "taut"
        "friction" -> "friction"
        "motor" -> "offset"
        else -> "free"
    }

    private fun makeJoint(kind: String, mode: String, anchor: Body, moving: Body, x: Double): Joint<Body> {
        val point = Vector2(x, 2.5)
        val axis = Vector2(1.0, 0.0)
        return when (kind) {
            "angle" -> AngleJoint(anchor, moving).apply {
                if (mode == "limits") setLimitsEnabled(-0.5, 0.5)
                if (mode == "ratio") setRatio(2.0)
            }
            "distance" -> DistanceJoint(anchor, moving, anchor.getWorldCenter(), moving.getWorldCenter()).apply {
                if (mode == "limits") setLimitsEnabled(0.8, 1.2)
                if (mode.startsWith("spring")) {
                    setSpringEnabled(true)
                    setSpringFrequency(4.0)
                    setSpringDamperEnabled(mode == "spring_damper")
                    setSpringDampingRatio(0.5)
                }
            }
            "friction" -> FrictionJoint(anchor, moving, point).apply {
                setMaximumForce(10.0)
                setMaximumTorque(10.0)
            }
            "motor" -> MotorJoint(anchor, moving).apply {
                setLinearTarget(0.0, 1.0)
                setAngularTarget(0.25)
                setMaximumForce(10.0)
                setMaximumTorque(10.0)
            }
            "pin" -> PinJoint(moving, Vector2(x, 3.0)).apply {
                setSpringEnabled(true)
                setSpringFrequency(4.0)
                setSpringDamperEnabled(mode == "spring_damper")
                setSpringDampingRatio(0.5)
            }
            "prismatic" -> PrismaticJoint(anchor, moving, point, axis).apply {
                if (mode == "limits") setLimitsEnabled(-0.5, 0.5)
                if (mode == "motor") {
                    setMotorEnabled(true)
                    setMotorSpeed(1.0)
                    setMaximumMotorForce(10.0)
                    setMaximumMotorForceEnabled(true)
                }
                if (mode.startsWith("spring")) {
                    setSpringEnabled(true)
                    setSpringFrequency(4.0)
                    setSpringDamperEnabled(mode == "spring_damper")
                    setSpringDampingRatio(0.5)
                }
            }
            "pulley" -> PulleyJoint(anchor, moving, Vector2(x - 1.0, 5.0), Vector2(x + 1.0, 5.0),
                anchor.getWorldCenter(), moving.getWorldCenter()).apply {
                if (mode == "ratio") setRatio(2.0)
                if (mode == "slack") setSlackEnabled(true)
            }
            "revolute" -> RevoluteJoint(anchor, moving, point).apply {
                if (mode == "limits") setLimitsEnabled(-0.5, 0.5)
                if (mode == "motor") {
                    setMotorEnabled(true)
                    setMotorSpeed(1.0)
                    setMaximumMotorTorque(10.0)
                    setMaximumMotorTorqueEnabled(true)
                }
            }
            "weld" -> WeldJoint(anchor, moving, point).apply {
                if (mode == "limits") setLimitsEnabled(-0.5, 0.5)
                if (mode.startsWith("spring")) {
                    setSpringEnabled(true)
                    setSpringFrequency(4.0)
                    setSpringDamperEnabled(mode == "spring_damper")
                    setSpringDampingRatio(0.5)
                }
            }
            "wheel" -> WheelJoint(anchor, moving, point, axis).apply {
                setSpringEnabled(true)
                setSpringFrequency(4.0)
                if (mode == "spring_damper") {
                    setSpringDamperEnabled(true)
                    setSpringDampingRatio(0.5)
                }
                if (mode == "limits") setLimitsEnabled(-0.5, 0.5)
                if (mode == "motor") {
                    setMotorEnabled(true)
                    setMotorSpeed(1.0)
                    setMaximumMotorTorque(10.0)
                    setMaximumMotorTorqueEnabled(true)
                }
            }
            else -> error("unknown joint: $kind")
        }
    }

    fun mutate(step: Int): Long {
        if (step == 0 || step % hz != 0) return 0
        if (family == "pile" || (family == "lifecycle" && variant == "settle")) return 0
        val started = System.nanoTime()
        when {
            family == "ccd" -> dynamic.forEachIndexed { i, moving ->
                val desired = if (i % 2 == 0) -8.0 else 8.0
                moving.translate(desired - moving.getWorldCenter().x, 0.0)
                moving.linearVelocity = Vector2(if (i % 2 == 0) 18.0 else -18.0, 0.0)
            }
            family == "joint" -> dynamic.forEach { moving ->
                moving.applyImpulse(Vector2(0.5, 1.0))
                moving.applyImpulse(0.01)
            }
            family == "lifecycle" && variant == "wake" -> {
                for (i in dynamic.indices step 10) dynamic[i].applyImpulse(Vector2(0.2, 0.5))
            }
            family == "lifecycle" && variant == "replace" -> {
                repeat((count + 99) / 100) { i ->
                    val index = (17017 + step / hz + i) % count
                    world.removeBody(dynamic[index], true)
                    val next = circle(((index % 10) - 4.5) * 0.48, 0.3 + (index / 10) * 0.48)
                    world.add(next)
                    dynamic[index] = next
                    if (index % 10 == 0) attachLifecycleJoint(next)
                }
            }
            family == "separated" -> dynamic.forEach { moving ->
                val x = moving.getWorldCenter().x
                if (x > 48.0) moving.translate(-96.0, 0.0)
                if (x < -48.0) moving.translate(96.0, 0.0)
            }
        }
        return System.nanoTime() - started
    }
}
