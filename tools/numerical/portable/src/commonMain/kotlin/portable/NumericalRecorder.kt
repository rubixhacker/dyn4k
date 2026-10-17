package portable

import org.dyn4j.collision.continuous.TimeOfImpact
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.dynamics.contact.Contact
import org.dyn4j.dynamics.contact.SolvedContact
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2
import org.dyn4j.world.ContactCollisionData
import org.dyn4j.world.PhysicsWorld
import org.dyn4j.world.World
import org.dyn4j.world.listener.ContactListener
import org.dyn4j.world.listener.StepListener
import org.dyn4j.world.listener.TimeOfImpactListener
import kotlin.math.PI
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.sin

data class CaseSpec(
    val id: String,
    val family: String,
    val profile: String,
    val hz: Int,
    val steps: Int,
    val input: Map<String, Any?>,
    val outerGroup: Int = 0,
)

class NumericalRecorder(private val emit: (String) -> Unit) {
    fun capture(spec: CaseSpec, world: World<Body>,
                observe: (World<Body>) -> Map<String, Any?> = { emptyMap() },
                before: (Int, World<Body>) -> String? = { _, _ -> null }) {
        require(spec.hz in setOf(30, 60, 120))
        require(spec.steps > 0)
        val dt = 1.0 / spec.hz
        val origin = (spec.input["origin"] as? List<*>)?.let { listOf(it[0] as Double, it[1] as Double) } ?: listOf(0.0, 0.0)
        val bodies = (0 until world.getBodyCount()).map(world::getBody)
        val joints = (0 until world.getJointCount()).map(world::getJoint)
        val rotations = bodies.map { it.getTransform().getRotationAngle() }.toMutableList()
        val sums = MutableList(bodies.size) { 0.0 }
        var step = 0
        var order = 0
        var events = 0
        var endpoints = 0
        fun event(name: String, payload: Any?) {
            line(mapOf("kind" to "event", "id" to spec.id, "step" to step,
                "order" to order++, "name" to name, "payload" to payload))
            events++
        }
        val contacts = object : ContactListener<Body> {
            fun detail(collision: ContactCollisionData<Body>?, contact: Contact?): Any? =
                if (contact == null) null else mapOf(
                    "body1" to collision?.getBody1()?.let { bodies.indexOf(it) },
                    "body2" to collision?.getBody2()?.let { bodies.indexOf(it) },
                    "point" to vector(contact.getPoint()), "depth" to contact.getDepth(),
                    "ignored" to contact.isIgnored(),
                    "normalImpulse" to (contact as? SolvedContact)?.getNormalImpulse(),
                    "tangentialImpulse" to (contact as? SolvedContact)?.getTangentialImpulse(),
                    "solved" to (contact as? SolvedContact)?.isSolved())
            override fun begin(collision: ContactCollisionData<Body>?, contact: Contact?) = event("contact.begin", detail(collision, contact))
            override fun persist(collision: ContactCollisionData<Body>?, oldContact: Contact?, newContact: Contact?) =
                event("contact.persist", mapOf("old" to detail(collision, oldContact), "new" to detail(collision, newContact)))
            override fun end(collision: ContactCollisionData<Body>?, contact: Contact?) = event("contact.end", detail(collision, contact))
            override fun destroyed(collision: ContactCollisionData<Body>?, contact: Contact?) = event("contact.destroyed", detail(collision, contact))
            override fun collision(collision: ContactCollisionData<Body>?) = event("contact.collision", collision?.getPenetration()?.getDepth())
            override fun preSolve(collision: ContactCollisionData<Body>?, contact: Contact?) = event("contact.preSolve", detail(collision, contact))
            override fun postSolve(collision: ContactCollisionData<Body>?, contact: SolvedContact?) = event("contact.postSolve", detail(collision, contact))
        }
        val timeOfImpact = object : TimeOfImpactListener<Body> {
            override fun collision(body1: Body?, body2: Body?): Boolean {
                event("toi.bodies", listOf(bodies.indexOf(body1), bodies.indexOf(body2)))
                return true
            }
            override fun collision(body1: Body?, fixture1: BodyFixture?, body2: Body?, fixture2: BodyFixture?): Boolean {
                event("toi.fixtures", listOf(bodies.indexOf(body1), body1?.getFixtures()?.indexOf(fixture1), bodies.indexOf(body2), body2?.getFixtures()?.indexOf(fixture2)))
                return true
            }
            override fun collision(body1: Body?, fixture1: BodyFixture?, body2: Body?, fixture2: BodyFixture?, toi: TimeOfImpact?): Boolean {
                event("toi.payload.fixtures", mapOf("bodies" to listOf(bodies.indexOf(body1), bodies.indexOf(body2)), "time" to toi?.getTime(), "distance" to toi?.getSeparation()?.getDistance()))
                return true
            }
            override fun collision(body1: Body?, body2: Body?, toi: TimeOfImpact?): Boolean {
                event("toi.payload.bodies", mapOf("bodies" to listOf(bodies.indexOf(body1), bodies.indexOf(body2)), "time" to toi?.getTime(), "distance" to toi?.getSeparation()?.getDistance()))
                return true
            }
        }
        val steps = object : StepListener<Body> {
            override fun begin(step: TimeStep?, world: PhysicsWorld<Body, *>?) = event("step.begin", step?.getDeltaTime())
            override fun updatePerformed(step: TimeStep?, world: PhysicsWorld<Body, *>?) = event("step.updatePerformed", step?.getDeltaTime())
            override fun postSolve(step: TimeStep?, world: PhysicsWorld<Body, *>?) = event("step.postSolve", step?.getDeltaTime())
            override fun end(step: TimeStep?, world: PhysicsWorld<Body, *>?) = event("step.end", step?.getDeltaTime())
        }
        line(mapOf("kind" to "inputs", "id" to spec.id, "family" to spec.family,
            "profile" to spec.profile, "hz" to spec.hz, "steps" to spec.steps,
            "dt" to dt, "input" to spec.input,
            "settings" to mapOf("gravity" to vector(world.getGravity()),
                "linearTolerance" to world.getSettings().getLinearTolerance(),
                "positionIterations" to world.getSettings().getPositionConstraintSolverIterations(),
                "continuousDetectionMode" to world.getSettings().getContinuousDetectionMode().name),
            "initial" to (snapshot(world, bodies, joints, sums, dt, origin) +
                mapOf("observations" to observe(world)))))
        world.addContactListener(contacts)
        world.addTimeOfImpactListener(timeOfImpact)
        world.addStepListener(steps)
        try {
            for (number in 1..spec.steps) {
                step = number
                order = 0
                val action = before(number, world)
                if (action != null) {
                    line(mapOf("kind" to "action", "id" to spec.id, "step" to number,
                        "order" to order++, "name" to action))
                    events++
                }
                world.step(1, dt)
                for (index in bodies.indices) {
                    val angle = bodies[index].getTransform().getRotationAngle()
                    val difference = atan2(sin(angle - rotations[index]), cos(angle - rotations[index]))
                    if (kotlin.math.abs(difference) >= PI) error("rotation increment is ambiguous")
                    sums[index] += difference
                    rotations[index] = angle
                }
                val state = snapshot(world, bodies, joints, sums, dt, origin) +
                    mapOf("observations" to observe(world))
                line(mapOf("kind" to "state", "id" to spec.id, "step" to number,
                    "order" to order++, "state" to state))
                if (spec.outerGroup > 0 && number % spec.outerGroup == 0) {
                    line(mapOf("kind" to "endpoint", "id" to spec.id, "step" to number,
                        "order" to order++, "state" to state))
                    endpoints++
                }
            }
            line(mapOf("kind" to "case-end", "id" to spec.id, "steps" to spec.steps,
                "events" to events, "endpoints" to endpoints))
        } finally {
            world.removeContactListener(contacts)
            world.removeTimeOfImpactListener(timeOfImpact)
            world.removeStepListener(steps)
        }
    }

    private fun snapshot(world: World<Body>, bodies: List<Body>, joints: List<org.dyn4j.dynamics.joint.Joint<Body>>, sums: List<Double>, dt: Double, origin: List<Double>): Map<String, Any?> =
        mapOf("gravity" to vector(world.getGravity()),
            "bodies" to bodies.mapIndexed { index, body -> mapOf(
                "id" to "b$index", "transform" to transform(body.getTransform()),
                "previousTransform" to transform(body.getPreviousTransform()),
                "worldCenter" to vector(body.getWorldCenter()),
                "fixedOriginPosition" to listOf(body.getWorldCenter().x - origin[0], body.getWorldCenter().y - origin[1]),
                "velocity" to vector(body.getLinearVelocity()),
                "angularVelocity" to body.getAngularVelocity(),
                "kineticEnergy" to (0.5 * body.getMass().getMass() * body.getLinearVelocity().getMagnitudeSquared() +
                    0.5 * body.getMass().getInertia() * body.getAngularVelocity() * body.getAngularVelocity()),
                "linearMomentum" to listOf(body.getMass().getMass() * body.getLinearVelocity().x,
                    body.getMass().getMass() * body.getLinearVelocity().y),
                "angularMomentumCenter" to body.getMass().getInertia() * body.getAngularVelocity(),
                "force" to vector(body.getForce()), "torque" to body.getTorque(),
                "accumulatedForce" to vector(body.getAccumulatedForce()),
                "accumulatedTorque" to body.getAccumulatedTorque(),
                "atRest" to body.isAtRest(), "bullet" to body.isBullet(),
                "rotationIncrementSum" to sums[index]) },
            "joints" to joints.mapIndexed { index, joint -> mapOf(
                "id" to "j$index", "reactionForce" to vector(joint.getReactionForce(1.0 / dt)),
                "reactionTorque" to joint.getReactionTorque(1.0 / dt)) })

    private fun transform(value: Transform): Map<String, Any?> = mapOf(
        "getTranslation" to vector(value.getTranslation()),
        "getTranslationX" to value.getTranslationX(),
        "getTranslationY" to value.getTranslationY(),
        "getCost" to value.getCost(), "getSint" to value.getSint(),
        "getRotationAngle" to value.getRotationAngle(),
        "getValues" to value.getValues().toList())

    private fun vector(value: Vector2): List<Double> = listOf(value.x, value.y)

    private fun line(value: Map<String, Any?>) = emit(json(value))

    private fun json(value: Any?): String = when (value) {
        null -> "null"
        is String -> "\"" + value.flatMap { character -> when (character) {
            '"' -> listOf('\\', '"')
            '\\' -> listOf('\\', '\\')
            '\n' -> listOf('\\', 'n')
            '\r' -> listOf('\\', 'r')
            '\t' -> listOf('\\', 't')
            else -> listOf(character)
        } }.joinToString("") + "\""
        is Double -> if (value.isFinite()) value.toString() else json(mapOf("nonfinite" to value.toString()))
        is Float -> if (value.isFinite()) value.toString() else json(mapOf("nonfinite" to value.toString()))
        is Number, is Boolean -> value.toString()
        is List<*> -> value.joinToString(prefix = "[", postfix = "]", separator = ",") { json(it) }
        is Map<*, *> -> value.entries.sortedBy { it.key.toString() }.joinToString(prefix = "{", postfix = "}", separator = ",") { json(it.key.toString()) + ":" + json(it.value) }
        else -> error("unsupported recorder value: ${value::class}")
    }
}
