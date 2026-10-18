package performance.portable

import io.github.rubixhacker.dyn4k.add
import io.github.rubixhacker.dyn4k.body
import io.github.rubixhacker.dyn4k.fixture
import io.github.rubixhacker.dyn4k.joint
import io.github.rubixhacker.dyn4k.world
import kotlin.math.abs
import kotlin.math.hypot
import org.dyn4j.collision.continuous.TimeOfImpact
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.joint.*
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2
import org.dyn4j.world.World
import org.dyn4j.world.listener.ContactListenerAdapter
import org.dyn4j.world.listener.TimeOfImpactListenerAdapter

internal class Fixture(
    val family: String,
    val variant: String,
    val count: Int,
    val hz: Int,
    val api: String,
) {
    val world: World<Body> = if (api == "direct_kotlin") world() else World()
    val dynamic = ArrayList<Body>(count)
    private lateinit var floor: Body
    private var nextCcdIndex = 0
    var contactBegins = 0L
        private set
    var contactEnds = 0L
        private set
    var toiEvents = 0L
        private set

    init {
        require(api == "direct_kotlin" || api == "compatibility")
        world.addContactListener(object : ContactListenerAdapter<Body>() {
            override fun begin(collision: org.dyn4j.world.ContactCollisionData<Body>?,
                               contact: org.dyn4j.dynamics.contact.Contact?) {
                contactBegins++
            }
            override fun end(collision: org.dyn4j.world.ContactCollisionData<Body>?,
                             contact: org.dyn4j.dynamics.contact.Contact?) {
                contactEnds++
            }
        })
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
        check(dynamic.size == count && world.getBodyCount() >= count)
    }

    private class CcdBody(private val index: Int) : Body() {
        override fun hashCode(): Int = index
    }

    private fun newBody(): Body =
        if (family == "ccd") CcdBody(nextCcdIndex++)
        else if (api == "direct_kotlin") body()
        else Body()

    private fun addBody(value: Body): Body {
        if (api == "direct_kotlin") world.add(value) else world.addBody(value)
        return value
    }

    private fun addJoint(value: Joint<Body>) {
        if (api == "direct_kotlin") world.joint(value) else world.addJoint(value)
    }

    private fun makeBody(shape: org.dyn4j.geometry.Convex, mass: MassType, x: Double, y: Double): Body {
        val value = newBody()
        val part = if (api == "direct_kotlin") value.fixture(shape) else value.addFixture(shape)
        part.setDensity(1.0)
        part.setFriction(0.5)
        part.setRestitution(0.0)
        value.setMass(mass)
        value.translate(x, y)
        return value
    }

    private fun circle(x: Double, y: Double): Body =
        makeBody(Geometry.createCircle(0.25), MassType.NORMAL, x, y)

    private fun rectangle(x: Double, y: Double, width: Double, height: Double): Body =
        addBody(makeBody(Geometry.createRectangle(width, height), MassType.INFINITE, x, y))

    private fun addDynamic(value: Body) {
        dynamic.add(addBody(value))
    }

    private fun buildSeparated() {
        world.setGravity(0.0, 0.0)
        for (i in 0 until count) {
            val moving = circle(-48.0 + i % 32 * 3.0, 2.0 + i / 32 * 3.0)
            moving.setLinearVelocity(0.75, 0.0)
            addDynamic(moving)
        }
    }

    private fun buildPile() {
        floor = rectangle(0.0, -0.5, 200.0, 1.0)
        for (i in 0 until count) addDynamic(circle((i % 10 - 4.5) * 0.48, 0.3 + i / 10 * 0.48))
        if (family == "lifecycle") for (i in 0 until count step 10) attachLifecycleJoint(dynamic[i])
    }

    private fun attachLifecycleJoint(value: Body) {
        addJoint(DistanceJoint(floor, value, floor.getWorldCenter(), value.getWorldCenter()))
    }

    private fun buildCcd() {
        world.setGravity(0.0, 0.0)
        rectangle(-10.0, 10.0, 0.5, 20.0)
        rectangle(10.0, 10.0, 0.5, 20.0)
        for (i in 0 until count) {
            val moving = circle(if (i % 2 == 0) -8.0 else 8.0, 0.5 + i % 20 * 0.45)
            moving.setBullet(true)
            moving.setLinearVelocity(if (i % 2 == 0) 18.0 else -18.0, 0.0)
            addDynamic(moving)
        }
    }

    private fun buildJoint() {
        val kind = if (variant == "mixed_all_types") "mixed" else variant.substringBefore('_')
        val mode = if (variant == "mixed_all_types") "mixed" else variant.substringAfter('_')
        val kinds = listOf("angle", "distance", "friction", "motor", "pin",
            "prismatic", "pulley", "revolute", "weld", "wheel")
        for (i in 0 until count) {
            val x = i * 3.0
            val anchor = rectangle(x, 3.0, 0.25, 0.25)
            val moving = circle(x, 2.0)
            moving.setAtRestDetectionEnabled(false)
            addDynamic(moving)
            val selected = if (kind == "mixed") kinds[i % kinds.size] else kind
            val selectedMode = if (mode == "mixed") defaultMode(selected) else mode
            addJoint(makeJoint(selected, selectedMode, anchor, moving, x))
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

    private fun makeJoint(kind: String, mode: String, a: Body, b: Body, x: Double): Joint<Body> {
        val point = Vector2(x, 2.5)
        val axis = Vector2(1.0, 0.0)
        return when (kind) {
            "angle" -> AngleJoint(a, b).apply {
                if (mode == "limits") setLimitsEnabled(-0.5, 0.5)
                if (mode == "ratio") setRatio(2.0)
            }
            "distance" -> DistanceJoint(a, b, a.getWorldCenter(), b.getWorldCenter()).apply {
                if (mode == "limits") setLimitsEnabled(0.8, 1.2)
                if (mode.startsWith("spring")) {
                    setSpringEnabled(true); setSpringFrequency(4.0)
                    setSpringDamperEnabled(mode == "spring_damper"); setSpringDampingRatio(0.5)
                }
            }
            "friction" -> FrictionJoint(a, b, point).apply {
                setMaximumForce(10.0); setMaximumTorque(10.0)
            }
            "motor" -> MotorJoint(a, b).apply {
                setLinearTarget(0.0, 1.0); setAngularTarget(0.25)
                setMaximumForce(10.0); setMaximumTorque(10.0)
            }
            "pin" -> PinJoint(b, Vector2(x, 3.0)).apply {
                setSpringEnabled(true); setSpringFrequency(4.0)
                setSpringDamperEnabled(mode == "spring_damper"); setSpringDampingRatio(0.5)
            }
            "prismatic" -> PrismaticJoint(a, b, point, axis).apply {
                if (mode == "limits") setLimitsEnabled(-0.5, 0.5)
                if (mode == "motor") {
                    setMotorEnabled(true); setMotorSpeed(1.0)
                    setMaximumMotorForce(10.0); setMaximumMotorForceEnabled(true)
                }
                if (mode.startsWith("spring")) {
                    setSpringEnabled(true); setSpringFrequency(4.0)
                    setSpringDamperEnabled(mode == "spring_damper"); setSpringDampingRatio(0.5)
                }
            }
            "pulley" -> PulleyJoint(a, b, Vector2(x - 1.0, 5.0), Vector2(x + 1.0, 5.0),
                a.getWorldCenter(), b.getWorldCenter()).apply {
                if (mode == "ratio") setRatio(2.0)
                if (mode == "slack") setSlackEnabled(true)
            }
            "revolute" -> RevoluteJoint(a, b, point).apply {
                if (mode == "limits") setLimitsEnabled(-0.5, 0.5)
                if (mode == "motor") {
                    setMotorEnabled(true); setMotorSpeed(1.0)
                    setMaximumMotorTorque(10.0); setMaximumMotorTorqueEnabled(true)
                }
            }
            "weld" -> WeldJoint(a, b, point).apply {
                if (mode == "limits") setLimitsEnabled(-0.5, 0.5)
                if (mode.startsWith("spring")) {
                    setSpringEnabled(true); setSpringFrequency(4.0)
                    setSpringDamperEnabled(mode == "spring_damper"); setSpringDampingRatio(0.5)
                }
            }
            "wheel" -> WheelJoint(a, b, point, axis).apply {
                setSpringEnabled(true); setSpringFrequency(4.0)
                if (mode == "spring_damper") {
                    setSpringDamperEnabled(true); setSpringDampingRatio(0.5)
                }
                if (mode == "limits") setLimitsEnabled(-0.5, 0.5)
                if (mode == "motor") {
                    setMotorEnabled(true); setMotorSpeed(1.0)
                    setMaximumMotorTorque(10.0); setMaximumMotorTorqueEnabled(true)
                }
            }
            else -> error("unknown joint kind: $kind")
        }
    }

    fun mutate(step: Int) {
        if (step == 0 || step % hz != 0) return
        when {
            family == "ccd" -> dynamic.forEachIndexed { i, moving ->
                val desired = if (i % 2 == 0) -8.0 else 8.0
                moving.translate(desired - moving.getWorldCenter().x, 0.0)
                moving.setLinearVelocity(if (i % 2 == 0) 18.0 else -18.0, 0.0)
            }
            family == "joint" -> dynamic.forEach {
                it.applyImpulse(Vector2(0.5, 1.0)); it.applyImpulse(0.01)
            }
            family == "lifecycle" && variant == "wake" ->
                for (i in dynamic.indices step 10) dynamic[i].applyImpulse(Vector2(0.2, 0.5))
            family == "lifecycle" && variant == "replace" ->
                repeat((count + 99) / 100) { offset ->
                    val index = (17017 + step / hz + offset) % count
                    world.removeBody(dynamic[index], true)
                    val next = circle((index % 10 - 4.5) * 0.48, 0.3 + index / 10 * 0.48)
                    addBody(next)
                    dynamic[index] = next
                    if (index % 10 == 0) attachLifecycleJoint(next)
                }
            family == "separated" -> dynamic.forEach {
                val x = it.getWorldCenter().x
                if (x > 48.0) it.translate(-96.0, 0.0)
                if (x < -48.0) it.translate(96.0, 0.0)
            }
        }
    }

    fun activity(): Triple<Int, Double, Double> {
        var awake = 0
        var speed = 0.0
        var rotation = 0.0
        for (item in dynamic) {
            if (!item.isAtRest()) awake++
            val velocity = item.getLinearVelocity()
            speed += hypot(velocity.x, velocity.y)
            rotation += abs(item.getAngularVelocity())
        }
        return Triple(awake, speed, rotation)
    }

    fun pairs(): Triple<Int, Int, Int> {
        var broad = 0
        val candidates = world.getBroadphaseDetector().detectIterator(true)
        while (candidates.hasNext()) { candidates.next(); broad++ }
        var pairs = 0
        var points = 0
        val collisions = world.getCollisionDataIterator()
        while (collisions.hasNext()) {
            val collision = collisions.next()
            val constraint = collision.getContactConstraint()
            if (collision.isContactConstraintCollision()) {
                pairs++
                points += constraint.getContacts().size
            }
        }
        return Triple(broad, pairs, points)
    }
}
