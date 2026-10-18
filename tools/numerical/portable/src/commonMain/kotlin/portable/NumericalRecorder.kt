package portable

import org.dyn4j.collision.continuous.TimeOfImpact
import org.dyn4j.collision.continuous.ConservativeAdvancement
import org.dyn4j.collision.Filter
import org.dyn4j.collision.narrowphase.Gjk
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.dynamics.TimeStep
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
import org.dyn4j.dynamics.contact.Contact
import org.dyn4j.dynamics.contact.SolvedContact
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.RotationOperationTap
import org.dyn4j.geometry.Vector2
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Polygon
import org.dyn4j.geometry.Rectangle
import org.dyn4j.world.ContactCollisionData
import org.dyn4j.world.BroadphaseCollisionData
import org.dyn4j.world.NarrowphaseCollisionData
import org.dyn4j.world.ManifoldCollisionData
import org.dyn4j.world.PhysicsWorld
import org.dyn4j.world.World
import org.dyn4j.world.ToiAcceptedResetTap
import org.dyn4j.world.listener.CollisionListener
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
    val startStep: Int = 0,
)

class NumericalRecorder(private val emit: (String) -> Unit) {
    private data class EndState(val world: World<Body>, val caseId: String,
        val bodies: List<Body>, val joints: List<Joint<Body>>, val rotations: List<Double>,
        val dt: Double, val origin: List<Double>, val state: Map<String, Any?>)
    private data class ChainState(val world: World<Body>, val previousCaseId: String,
        val operation: String, val previousEnd: Map<String, Any?>,
        val preAction: Map<String, Any?>, val postAction: Map<String, Any?>)
    private var lastEnd: EndState? = null
    private var pendingChain: ChainState? = null

    fun prepareFrozenContinuation(world: World<Body>, operation: String,
                                  action: () -> Unit) {
        val prior = lastEnd ?: error("frozen continuation has no preceding segment")
        check(prior.world === world) { "frozen continuation changed world identity" }
        check(pendingChain == null) { "frozen continuation action is already pending" }
        val before = FrozenState.capture(world, prior.bodies, prior.joints,
            prior.rotations, prior.dt, prior.origin, initial = true)
        check(before == prior.state) { "frozen world changed before continuation action" }
        action()
        val after = FrozenState.capture(world, prior.bodies, prior.joints,
            prior.rotations, prior.dt, prior.origin, initial = true)
        pendingChain = ChainState(world, prior.caseId, operation, prior.state,
            before, after)
    }

    fun capture(spec: CaseSpec, world: World<Body>,
                observe: (World<Body>) -> Map<String, Any?> = { emptyMap() },
                before: (Int, World<Body>) -> String? = { _, _ -> null }) {
        require(spec.hz in setOf(30, 60, 120))
        require(spec.steps > 0)
        require(spec.startStep >= 0)
        val dt = 1.0 / spec.hz
        val frozen = spec.id == "long-free-60" ||
            spec.id.startsWith("contacts-default-") || spec.id.startsWith("contacts-configured-") ||
            spec.profile == "frozen-weld-pulley"
        val origin = (spec.input["origin"] as? List<*>)?.let { listOf(it[0] as Double, it[1] as Double) } ?: listOf(0.0, 0.0)
        val bodies = (0 until world.getBodyCount()).map(world::getBody)
        val joints = (0 until world.getJointCount()).map(world::getJoint)
        val rotations = bodies.map { it.getTransform().getRotationAngle() }.toMutableList()
        val sums = MutableList(bodies.size) { 0.0 }
        var step = spec.startStep
        val previousRotationListener = RotationOperationTap.listener
        val previousResetListener = ToiAcceptedResetTap.listener
        val bodyTransforms = bodies.map { it.getTransform() }
        val bodyCalls = IntArray(bodies.size)
        var temporaryCalls = 0
        fun bits(value: Double) = value.toBits().toULong().toString(16).padStart(16, '0')
        fun pair(value: Transform) = listOf(bits(value.getCost()), bits(value.getSint()))
        var order = 0
        var frozenOrder = 0
        var precedingSecondAsleep = true
        var events = 0
        var endpoints = 0
        fun event(name: String, payload: Any?, time: TimeStep? = null,
                  projection: ((Int) -> Map<String, Any?>)? = null) {
            val frozenEvent = if (frozen) {
                val value = if (name.startsWith("step."))
                    FrozenEvent.step(spec, name, step, frozenOrder, time)
                    else projection?.invoke(frozenOrder)
                        ?: error("frozen callback has no projection: $name")
                frozenOrder++
                mapOf("frozenEvent" to value)
            } else emptyMap()
            line(mapOf("kind" to "event", "id" to spec.id, "step" to step,
                "order" to order++, "name" to name, "payload" to payload) + frozenEvent)
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
            override fun begin(collision: ContactCollisionData<Body>?, contact: Contact?) =
                event("contact.begin", detail(collision, contact), projection = { position ->
                    FrozenEvent.contactEvent("begin", step, position, collision, listOf(contact), bodies) })
            override fun persist(collision: ContactCollisionData<Body>?, oldContact: Contact?, newContact: Contact?) =
                event("contact.persist", mapOf("old" to detail(collision, oldContact), "new" to detail(collision, newContact)),
                    projection = { position -> FrozenEvent.contactEvent("persist", step, position,
                        collision, listOf(oldContact, newContact), bodies) })
            override fun end(collision: ContactCollisionData<Body>?, contact: Contact?) =
                event("contact.end", detail(collision, contact), projection = { position ->
                    FrozenEvent.contactEvent("end", step, position, collision, listOf(contact), bodies) })
            override fun destroyed(collision: ContactCollisionData<Body>?, contact: Contact?) =
                event("contact.destroyed", detail(collision, contact), projection = { position ->
                    FrozenEvent.contactEvent("destroyed", step, position, collision, listOf(contact), bodies) })
            override fun collision(collision: ContactCollisionData<Body>?) =
                event("contact.collision", collision?.getPenetration()?.getDepth(), projection = { position ->
                    FrozenEvent.contactEvent("collision", step, position, collision, emptyList(), bodies) })
            override fun preSolve(collision: ContactCollisionData<Body>?, contact: Contact?) =
                event("contact.preSolve", detail(collision, contact), projection = { position ->
                    FrozenEvent.contactEvent("preSolve", step, position, collision, listOf(contact), bodies) })
            override fun postSolve(collision: ContactCollisionData<Body>?, contact: SolvedContact?) =
                event("contact.postSolve", detail(collision, contact), projection = { position ->
                    FrozenEvent.contactEvent("postSolve", step, position, collision, listOf(contact), bodies) })
        }
        val collisions = object : CollisionListener<Body, BodyFixture> {
            override fun collision(collision: BroadphaseCollisionData<Body, BodyFixture>?): Boolean {
                event("collision.broadphase", collision?.getBody1()?.let(bodies::indexOf),
                    projection = { position -> FrozenEvent.collisionEvent("Broadphase", step,
                        position, collision, bodies) })
                return true
            }
            override fun collision(collision: NarrowphaseCollisionData<Body, BodyFixture>?): Boolean {
                event("collision.narrowphase", collision?.getPenetration()?.getDepth(),
                    projection = { position -> FrozenEvent.collisionEvent("Narrowphase", step,
                        position, collision, bodies) })
                return true
            }
            override fun collision(collision: ManifoldCollisionData<Body, BodyFixture>?): Boolean {
                event("collision.manifold", collision?.getManifold()?.getPoints()?.size,
                    projection = { position -> FrozenEvent.collisionEvent("Manifold", step,
                        position, collision, bodies) })
                return true
            }
        }
        val timeOfImpact = object : TimeOfImpactListener<Body> {
            override fun collision(body1: Body?, body2: Body?): Boolean {
                event("toi.bodies", listOf(bodies.indexOf(body1), bodies.indexOf(body2)),
                    projection = { position -> FrozenEvent.toiEvent(step, position,
                        body1, null, body2, null, null, bodies) })
                return true
            }
            override fun collision(body1: Body?, fixture1: BodyFixture?, body2: Body?, fixture2: BodyFixture?): Boolean {
                event("toi.fixtures", listOf(bodies.indexOf(body1), body1?.getFixtures()?.indexOf(fixture1), bodies.indexOf(body2), body2?.getFixtures()?.indexOf(fixture2)),
                    projection = { position -> FrozenEvent.toiEvent(step, position,
                        body1, fixture1, body2, fixture2, null, bodies) })
                return true
            }
            override fun collision(body1: Body?, fixture1: BodyFixture?, body2: Body?, fixture2: BodyFixture?, toi: TimeOfImpact?): Boolean {
                event("toi.payload.fixtures", mapOf("bodies" to listOf(bodies.indexOf(body1), bodies.indexOf(body2)), "time" to toi?.getTime(), "distance" to toi?.getSeparation()?.getDistance()),
                    projection = { position -> FrozenEvent.toiEvent(step, position,
                        body1, fixture1, body2, fixture2, toi, bodies) })
                return true
            }
            override fun collision(body1: Body?, body2: Body?, toi: TimeOfImpact?): Boolean {
                event("toi.payload.bodies", mapOf("bodies" to listOf(bodies.indexOf(body1), bodies.indexOf(body2)), "time" to toi?.getTime(), "distance" to toi?.getSeparation()?.getDistance()),
                    projection = { position -> FrozenEvent.toiEvent(step, position,
                        body1, null, body2, null, toi, bodies) })
                return true
            }
        }
        val steps = object : StepListener<Body> {
            override fun begin(step: TimeStep?, world: PhysicsWorld<Body, *>?) = event("step.begin", step?.getDeltaTime(), step)
            override fun updatePerformed(step: TimeStep?, world: PhysicsWorld<Body, *>?) = event("step.updatePerformed", step?.getDeltaTime(), step)
            override fun postSolve(step: TimeStep?, world: PhysicsWorld<Body, *>?) = event("step.postSolve", step?.getDeltaTime(), step)
            override fun end(step: TimeStep?, world: PhysicsWorld<Body, *>?) = event("step.end", step?.getDeltaTime(), step)
        }
        val chain = if (spec.profile == "frozen-weld-pulley" &&
            spec.id.startsWith("P-JINT-Pulley-") &&
            !spec.id.endsWith("preparation-0")) {
            val proof = pendingChain ?: error("frozen Pulley post-action chain is absent")
            check(proof.world === world) { "frozen Pulley world identity changed" }
            check(proof.postAction == FrozenState.capture(world, bodies, joints, sums,
                dt, origin, initial = true)) { "frozen Pulley header is not post-action state" }
            pendingChain = null
            mapOf("frozenChain" to mapOf("previousCaseId" to proof.previousCaseId,
                "operation" to proof.operation, "previousEnd" to proof.previousEnd,
                "preAction" to proof.preAction, "postAction" to proof.postAction))
        } else emptyMap()
        val frozenConfiguration = if (frozen) {
            val settings = FrozenConfiguration.settings(world.getSettings())
            val worldConfiguration = FrozenConfiguration.world(world)
            val initialState = FrozenState.capture(world, bodies, joints, sums, dt, origin,
                initial = true)
            val frozenInput = mutableMapOf<String, Any?>(
                "kind" to "inputs", "id" to FrozenEvent.id(spec), "dt" to dt,
                "steps" to spec.steps, "origin" to origin,
                "scale" to (spec.input["scale"] ?: 1.0),
                "settings" to settings, "world" to worldConfiguration,
                "state" to initialState)
            if (spec.id.startsWith("contacts-configured-")) {
                val outerHz = spec.input["outerHz"] as Int
                frozenInput["grouping"] = mapOf(
                    "outerHz" to outerHz, "repetition" to (spec.input["repetition"] as Int),
                    "innerPerOuter" to spec.outerGroup,
                    "outerDt" to 1.0 / outerHz,
                    "outerSteps" to spec.steps / spec.outerGroup,
                    "actionInnerStep" to (spec.input["actionStep"] as Int))
            }
            mapOf("frozenInput" to frozenInput,
                "frozenConfiguration" to mapOf(
                "settings" to settings,
                "world" to worldConfiguration,
                "state" to initialState))
        } else emptyMap()
        var contactRegistered = false
        var toiRegistered = false
        var collisionRegistered = false
        var stepRegistered = false
        try {
            if (previousRotationListener != null) {
                RotationOperationTap.listener = { call ->
                    val index = bodyTransforms.indexOfFirst { it === call.target }
                    if (index < 0) temporaryCalls++ else bodyCalls[index]++
                    previousRotationListener(call.copy(caseId = spec.id, step = step,
                        bodyId = if (index < 0) null else "b$index"))
                }
                ToiAcceptedResetTap.listener = { first, second, time, secondDynamic ->
                    val firstIndex = bodies.indexOfFirst { it === first }
                    val secondIndex = bodies.indexOfFirst { it === second }
                    check(firstIndex >= 0 && secondIndex >= 0)
                    val resets = if (secondDynamic) listOf("b$firstIndex", "b$secondIndex")
                        else listOf("b$firstIndex")
                    println("PROSPECTIVE_BINDING_JSON " + json(mapOf(
                        "kind" to "toi-accepted", "case_id" to spec.id, "step" to step,
                        "body_ids" to listOf("b$firstIndex", "b$secondIndex"),
                        "reset_body_ids" to resets, "time_bits" to bits(time))))
                    previousResetListener?.invoke(first, second, time, secondDynamic)
                }
            }
            line(mapOf("kind" to "inputs", "id" to spec.id, "family" to spec.family,
            "profile" to spec.profile, "hz" to spec.hz, "steps" to spec.steps,
            "startStep" to spec.startStep,
            "dt" to dt, "input" to spec.input,
            "settings" to settings(world), "setup" to setup(world, bodies, joints),
            "initial" to (snapshot(world, bodies, joints, sums, dt, origin) +
                mapOf("observations" to observe(world)))) + frozenConfiguration + chain)
            contactRegistered = true
            world.addContactListener(contacts)
            toiRegistered = true
            world.addTimeOfImpactListener(timeOfImpact)
            if (frozen) {
                collisionRegistered = true
                world.addCollisionListener(collisions)
            }
            stepRegistered = true
            world.addStepListener(steps)
            for (number in 1..spec.steps) {
                step = spec.startStep + number
                bodyCalls.fill(0)
                temporaryCalls = 0
                val preRotations = bodyTransforms.map(::pair)
                order = 0
                frozenOrder = 0
                val wakeCase = frozen && (spec.id.startsWith("contacts-default-") ||
                    spec.id.startsWith("contacts-configured-"))
                if (wakeCase && number - 1 in 299 * spec.hz..300 * spec.hz)
                    precedingSecondAsleep = precedingSecondAsleep && bodies.last().isAtRest()
                val wakeStep = wakeCase && step == spec.input["actionStep"]
                fun wakeRecord(name: String) {
                    val state = FrozenState.capture(world, bodies, joints, sums, dt, origin,
                        initial = true)
                    val projection = FrozenEvent.wakeState(spec, name, step, frozenOrder++, state)
                    line(mapOf("kind" to "instrumented-callback", "id" to spec.id,
                        "step" to step, "order" to order++, "event" to name,
                        "values" to listOf(state), "frozenRecord" to projection))
                    events++
                }
                if (number == 1 && spec.id in setOf("P-JINT-Weld-enabled-equal",
                        "P-JINT-Pulley-slack-transition-main")) {
                    val binding = FrozenEvent.experimentalBinding(spec, step, frozenOrder++)
                    line(mapOf("kind" to "instrumented-callback", "id" to spec.id,
                        "step" to step, "order" to order++,
                        "event" to "experimental-input-binding",
                        "values" to binding["values"], "frozenRecord" to binding))
                    events++
                }
                if (wakeStep) wakeRecord("before-wake")
                val sleepingBefore = bodies.last().isAtRest()
                val action = before(number, world)
                if (action != null) {
                    val frozenActions = if (frozen) FrozenEvent.actions(spec, step,
                        frozenOrder, sleepingBefore, precedingSecondAsleep) else emptyList()
                    frozenOrder += frozenActions.size
                    line(mapOf("kind" to "action", "id" to spec.id, "step" to step,
                        "order" to order++, "name" to action) +
                        if (frozen) mapOf("frozenRecords" to frozenActions) else emptyMap())
                    events++
                }
                if (wakeStep) wakeRecord("after-wake")
                val pulleyBranch = if (spec.profile == "frozen-weld-pulley") {
                    val pulley = joints.singleOrNull() as? PulleyJoint<*>
                    if (pulley != null) {
                        val current = pulley.getCurrentLength()
                        val target = pulley.getLength()
                        val slack = pulley.isSlackEnabled()
                        mapOf("frozenBranch" to mapOf("currentLength" to current,
                            "length1" to pulley.getCurrentLength1(),
                            "length2" to pulley.getCurrentLength2(),
                            "ratio" to pulley.getRatio(),
                            "anchor1" to vector(pulley.getAnchor1()),
                            "anchor2" to vector(pulley.getAnchor2()),
                            "pulleyAnchor1" to vector(pulley.getPulleyAnchor1()),
                            "pulleyAnchor2" to vector(pulley.getPulleyAnchor2()),
                            "targetLength" to target, "slackEnabled" to slack,
                            "overLength" to (current > target || !slack)))
                    } else emptyMap()
                } else emptyMap()
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
                val frozenState = if (frozen) mapOf("frozenState" to
                    FrozenState.capture(world, bodies, joints, sums, dt, origin,
                        initial = false)) else emptyMap()
                line(mapOf("kind" to "state", "id" to spec.id, "step" to step,
                    "order" to order++, "state" to state) + frozenState + pulleyBranch)
                if (spec.outerGroup > 0 && number % spec.outerGroup == 0) {
                    line(mapOf("kind" to "endpoint", "id" to spec.id, "step" to step,
                        "order" to order++, "state" to state) + frozenState)
                    endpoints++
                }
                if (previousRotationListener != null) {
                    println("PROSPECTIVE_BINDING_JSON " + json(mapOf(
                        "kind" to "body-step", "case_id" to spec.id, "step" to step,
                        "bodies" to bodyTransforms.mapIndexed { index, transform -> mapOf(
                            "body_id" to "b$index", "calls" to bodyCalls[index],
                            "pre" to preRotations[index], "post" to pair(transform)) },
                        "temporary_calls" to temporaryCalls)))
                }
            }
            val end = if (spec.profile == "frozen-weld-pulley")
                FrozenState.capture(world, bodies, joints, sums, dt, origin,
                    initial = true) else null
            line(mapOf("kind" to "case-end", "id" to spec.id, "steps" to spec.steps,
                "events" to events, "endpoints" to endpoints) +
                if (end != null) mapOf("frozenEndState" to end) else emptyMap())
            if (end != null) lastEnd = EndState(world, spec.id, bodies, joints,
                sums.toList(), dt, origin, end)
        } finally {
            try {
                if (stepRegistered) world.removeStepListener(steps)
            } finally {
                try {
                    if (collisionRegistered) world.removeCollisionListener(collisions)
                } finally {
                    try {
                        if (toiRegistered) world.removeTimeOfImpactListener(timeOfImpact)
                    } finally {
                        try {
                            if (contactRegistered) world.removeContactListener(contacts)
                        } finally {
                            RotationOperationTap.listener = previousRotationListener
                            ToiAcceptedResetTap.listener = previousResetListener
                        }
                    }
                }
            }
        }
    }

    private fun snapshot(world: World<Body>, bodies: List<Body>, joints: List<Joint<Body>>, sums: List<Double>, dt: Double, origin: List<Double>): Map<String, Any?> =
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
                "reactionTorque" to joint.getReactionTorque(1.0 / dt),
                "mode" to jointMode(joint)) })

    private fun settings(world: World<Body>): Map<String, Any?> {
        val value = world.getSettings()
        val toi = world.getTimeOfImpactDetector() as? ConservativeAdvancement
            ?: error("unsupported time-of-impact detector")
        val narrowphase = world.getNarrowphaseDetector() as? Gjk
            ?: error("unsupported narrowphase detector")
        return mapOf(
            "gravity" to vector(world.getGravity()),
            "stepFrequency" to value.getStepFrequency(),
            "maximumTranslation" to value.getMaximumTranslation(),
            "maximumRotation" to value.getMaximumRotation(),
            "atRestDetectionEnabled" to value.isAtRestDetectionEnabled(),
            "maximumAtRestLinearVelocity" to value.getMaximumAtRestLinearVelocity(),
            "maximumAtRestAngularVelocity" to value.getMaximumAtRestAngularVelocity(),
            "minimumAtRestTime" to value.getMinimumAtRestTime(),
            "velocityIterations" to value.getVelocityConstraintSolverIterations(),
            "positionIterations" to value.getPositionConstraintSolverIterations(),
            "warmStartingEnabled" to value.isWarmStartingEnabled(),
            "maximumWarmStartDistance" to value.getMaximumWarmStartDistance(),
            "linearTolerance" to value.getLinearTolerance(),
            "angularTolerance" to value.getAngularTolerance(),
            "maximumLinearCorrection" to value.getMaximumLinearCorrection(),
            "maximumAngularCorrection" to value.getMaximumAngularCorrection(),
            "baumgarte" to value.getBaumgarte(),
            "continuousDetectionMode" to value.getContinuousDetectionMode().name,
            "narrowphase" to mapOf("type" to "Gjk", "distanceEpsilon" to narrowphase.getDistanceEpsilon(),
                "raycastEpsilon" to narrowphase.getRaycastEpsilon()),
            "timeOfImpact" to mapOf("type" to "ConservativeAdvancement",
                "distanceEpsilon" to toi.getDistanceEpsilon(), "maxIterations" to toi.getMaxIterations()))
    }

    private fun setup(world: World<Body>, bodies: List<Body>, joints: List<Joint<Body>>): Map<String, Any?> =
        mapOf("bodies" to bodies.mapIndexed { index, body -> mapOf(
            "id" to "b$index", "transform" to transform(body.getTransform()),
            "massType" to body.getMass().getType().name,
            "mass" to body.getMass().getMass(), "inertia" to body.getMass().getInertia(),
            "massCenter" to vector(body.getMass().getCenter()),
            "linearDamping" to body.getLinearDamping(), "angularDamping" to body.getAngularDamping(),
            "initialVelocity" to vector(body.getLinearVelocity()),
            "initialAngularVelocity" to body.getAngularVelocity(),
            "atRestDetectionEnabled" to body.isAtRestDetectionEnabled(),
            "bullet" to body.isBullet(),
            "fixtures" to body.getFixtures().mapIndexed { fixtureIndex, fixture -> mapOf(
                "id" to "b${index}f$fixtureIndex", "density" to fixture.getDensity(),
                "friction" to fixture.getFriction(), "restitution" to fixture.getRestitution(),
                "restitutionVelocity" to fixture.getRestitutionVelocity(),
                "sensor" to fixture.isSensor(),
                "filter" to if (fixture.getFilter() === Filter.DEFAULT_FILTER) "DEFAULT_FILTER"
                    else error("unsupported fixture filter"),
                "shape" to shape(fixture.getShape())) }) },
            "joints" to joints.mapIndexed { index, joint -> mapOf(
                "id" to "j$index", "bodies" to joint.getBodies().map { bodies.indexOf(it) },
                "collisionAllowed" to joint.isCollisionAllowed(), "enabled" to joint.isEnabled(),
                "mode" to jointMode(joint)) })

    private fun shape(value: Convex): Map<String, Any?> = when (value) {
        is Circle -> mapOf("type" to "Circle", "radius" to value.getRadius(),
            "center" to vector(value.getCenter()))
        is Rectangle -> mapOf("type" to "Rectangle", "width" to value.getWidth(),
            "height" to value.getHeight(), "vertices" to value.getVertices().map(::vector))
        is Polygon -> mapOf("type" to "Polygon", "vertices" to value.getVertices().map(::vector))
        else -> error("unsupported fixture shape: ${value::class}")
    }

    private fun jointMode(value: Joint<Body>): Map<String, Any?> = when (value) {
        is AngleJoint<*> -> mapOf("type" to "Angle", "ratio" to value.getRatio(),
            "limitsEnabled" to value.isLimitsEnabled(), "lowerLimit" to value.getLowerLimit(),
            "upperLimit" to value.getUpperLimit())
        is DistanceJoint<*> -> mapOf("type" to "Distance", "anchor1" to vector(value.getAnchor1()),
            "anchor2" to vector(value.getAnchor2()), "restDistance" to value.getRestDistance(),
            "springEnabled" to value.isSpringEnabled(), "springDamperEnabled" to value.isSpringDamperEnabled(),
            "springFrequency" to value.getSpringFrequency(), "springDampingRatio" to value.getSpringDampingRatio(),
            "maximumSpringForceEnabled" to value.isMaximumSpringForceEnabled(),
            "maximumSpringForce" to value.getMaximumSpringForce(),
            "lowerLimitEnabled" to value.isLowerLimitEnabled(), "lowerLimit" to value.getLowerLimit(),
            "upperLimitEnabled" to value.isUpperLimitEnabled(), "upperLimit" to value.getUpperLimit())
        is FrictionJoint<*> -> mapOf("type" to "Friction", "anchor1" to vector(value.getAnchor1()),
            "anchor2" to vector(value.getAnchor2()), "maximumForce" to value.getMaximumForce(),
            "maximumTorque" to value.getMaximumTorque())
        is MotorJoint<*> -> mapOf("type" to "Motor", "linearTarget" to vector(value.getLinearTarget()),
            "angularTarget" to value.getAngularTarget(), "maximumForce" to value.getMaximumForce(),
            "maximumTorque" to value.getMaximumTorque(), "correctionFactor" to value.getCorrectionFactor())
        is PinJoint<*> -> mapOf("type" to "Pin", "target" to vector(value.getTarget()),
            "springEnabled" to value.isSpringEnabled(), "springDamperEnabled" to value.isSpringDamperEnabled(),
            "springFrequency" to value.getSpringFrequency(), "springDampingRatio" to value.getSpringDampingRatio(),
            "maximumSpringForceEnabled" to value.isMaximumSpringForceEnabled(),
            "maximumSpringForce" to value.getMaximumSpringForce(),
            "correctionFactor" to value.getCorrectionFactor(),
            "maximumCorrectionForce" to value.getMaximumCorrectionForce())
        is PrismaticJoint<*> -> mapOf("type" to "Prismatic", "axis" to vector(value.getAxis()),
            "anchor1" to vector(value.getAnchor1()), "anchor2" to vector(value.getAnchor2()),
            "referenceAngle" to value.getReferenceAngle(),
            "motorEnabled" to value.isMotorEnabled(), "motorSpeed" to value.getMotorSpeed(),
            "maximumMotorForceEnabled" to value.isMaximumMotorForceEnabled(),
            "maximumMotorForce" to value.getMaximumMotorForce(),
            "springEnabled" to value.isSpringEnabled(), "springDamperEnabled" to value.isSpringDamperEnabled(),
            "springFrequency" to value.getSpringFrequency(), "springDampingRatio" to value.getSpringDampingRatio(),
            "maximumSpringForceEnabled" to value.isMaximumSpringForceEnabled(),
            "maximumSpringForce" to value.getMaximumSpringForce(),
            "lowerLimitEnabled" to value.isLowerLimitEnabled(), "lowerLimit" to value.getLowerLimit(),
            "upperLimitEnabled" to value.isUpperLimitEnabled(), "upperLimit" to value.getUpperLimit())
        is PulleyJoint<*> -> mapOf("type" to "Pulley", "ratio" to value.getRatio(),
            "slackEnabled" to value.isSlackEnabled(), "length" to value.getLength(),
            "anchor1" to vector(value.getAnchor1()), "anchor2" to vector(value.getAnchor2()),
            "pulleyAnchor1" to vector(value.getPulleyAnchor1()),
            "pulleyAnchor2" to vector(value.getPulleyAnchor2()))
        is RevoluteJoint<*> -> mapOf("type" to "Revolute", "anchor1" to vector(value.getAnchor1()),
            "anchor2" to vector(value.getAnchor2()), "motorEnabled" to value.isMotorEnabled(),
            "motorSpeed" to value.getMotorSpeed(), "maximumMotorTorqueEnabled" to value.isMaximumMotorTorqueEnabled(),
            "maximumMotorTorque" to value.getMaximumMotorTorque(),
            "limitsEnabled" to value.isLimitsEnabled(), "lowerLimit" to value.getLowerLimit(),
            "upperLimit" to value.getUpperLimit())
        is WeldJoint<*> -> mapOf("type" to "Weld", "anchor1" to vector(value.getAnchor1()),
            "anchor2" to vector(value.getAnchor2()), "springEnabled" to value.isSpringEnabled(),
            "springDamperEnabled" to value.isSpringDamperEnabled(), "springFrequency" to value.getSpringFrequency(),
            "springDampingRatio" to value.getSpringDampingRatio(),
            "maximumSpringTorqueEnabled" to value.isMaximumSpringTorqueEnabled(),
            "maximumSpringTorque" to value.getMaximumSpringTorque(),
            "limitsEnabled" to value.isLimitsEnabled(), "lowerLimit" to value.getLowerLimit(),
            "upperLimit" to value.getUpperLimit())
        is WheelJoint<*> -> mapOf("type" to "Wheel", "axis" to vector(value.getAxis()),
            "anchor1" to vector(value.getAnchor1()), "anchor2" to vector(value.getAnchor2()),
            "motorEnabled" to value.isMotorEnabled(), "motorSpeed" to value.getMotorSpeed(),
            "maximumMotorTorqueEnabled" to value.isMaximumMotorTorqueEnabled(),
            "maximumMotorTorque" to value.getMaximumMotorTorque(),
            "springEnabled" to value.isSpringEnabled(), "springDamperEnabled" to value.isSpringDamperEnabled(),
            "springFrequency" to value.getSpringFrequency(), "springDampingRatio" to value.getSpringDampingRatio(),
            "maximumSpringForceEnabled" to value.isMaximumSpringForceEnabled(),
            "maximumSpringForce" to value.getMaximumSpringForce(),
            "lowerLimitEnabled" to value.isLowerLimitEnabled(), "lowerLimit" to value.getLowerLimit(),
            "upperLimitEnabled" to value.isUpperLimitEnabled(), "upperLimit" to value.getUpperLimit())
        else -> error("unsupported joint type: ${value::class}")
    }

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
        is Double -> when {
            value == 0.0 && 1.0 / value < 0.0 -> "-0.0"
            value.isFinite() -> value.toString()
            else -> json(mapOf("nonfinite" to value.toString()))
        }
        is Float -> when {
            value == 0.0f && 1.0f / value < 0.0f -> "-0.0"
            value.isFinite() -> value.toString()
            else -> json(mapOf("nonfinite" to value.toString()))
        }
        is Number, is Boolean -> value.toString()
        is List<*> -> value.joinToString(prefix = "[", postfix = "]", separator = ",") { json(it) }
        is Map<*, *> -> value.entries.sortedBy { it.key.toString() }.joinToString(prefix = "{", postfix = "}", separator = ",") { json(it.key.toString()) + ":" + json(it.value) }
        else -> error("unsupported recorder value: ${value::class}")
    }
}
