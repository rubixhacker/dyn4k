package portable

import org.dyn4j.collision.continuous.TimeOfImpact
import org.dyn4j.collision.manifold.IndexedManifoldPointId
import org.dyn4j.collision.manifold.ManifoldPointId
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.dynamics.contact.Contact
import org.dyn4j.dynamics.contact.SolvedContact
import org.dyn4j.geometry.Vector2
import org.dyn4j.world.BroadphaseCollisionData
import org.dyn4j.world.ContactCollisionData
import org.dyn4j.world.WorldCollisionData

internal object FrozenEvent {
    private fun vector(value: Vector2): List<Double> = listOf(value.x, value.y)

    private fun body(value: Body?, bodies: List<Body>): String =
        "b${bodies.indexOf(value).also { require(it >= 0) }}"

    private fun fixtureId(value: BodyFixture?, bodies: List<Body>): String {
        val matching = bodies.flatMapIndexed { bodyIndex, current ->
            current.getFixtures().mapIndexedNotNull { fixtureIndex, fixture ->
                if (fixture === value) "b${bodyIndex}f$fixtureIndex" else null
            }
        }
        require(matching.size == 1 && value != null)
        return matching.single()
    }

    private fun fixture(value: BodyFixture?, bodies: List<Body>): Map<String, Any?> {
        require(value != null)
        return FrozenState.fixture(value, fixtureId(value, bodies))
    }

    private fun contact(value: Contact?): Map<String, Any?> {
        require(value != null)
        val manifoldId = when (val id = value.getId()) {
            is IndexedManifoldPointId -> mapOf(
                "type" to "org.dyn4j.collision.manifold.IndexedManifoldPointId",
                "getReferenceEdgeIndex" to id.getReferenceEdgeIndex(),
                "getIncidentEdgeIndex" to id.getIncidentEdgeIndex(),
                "getIncidentVertexIndex" to id.getIncidentVertexIndex(),
                "isFlipped" to id.isFlipped())
            ManifoldPointId.DISTANCE -> mapOf("type" to "org.dyn4j.collision.manifold.ManifoldPointId\$1")
            else -> error("unsupported frozen manifold ID: ${id::class}")
        }
        val solved = value as? SolvedContact ?: error("frozen contact lacks impulses")
        return mapOf("type" to "org.dyn4j.dynamics.contact.SolvableContact",
            "getPoint" to vector(value.getPoint()), "getDepth" to value.getDepth(),
            "isIgnored" to value.isIgnored(), "manifoldId" to manifoldId,
            "getNormalImpulse" to solved.getNormalImpulse(),
            "getTangentialImpulse" to solved.getTangentialImpulse(),
            "isSolved" to solved.isSolved())
    }

    private fun collision(value: BroadphaseCollisionData<Body, BodyFixture>?,
                          bodies: List<Body>): Map<String, Any?> {
        val data = value as? WorldCollisionData<Body>
            ?: error("unsupported frozen collision data")
        val body1 = data.getBody1() ?: error("frozen collision lacks first body")
        val body2 = data.getBody2() ?: error("frozen collision lacks second body")
        val manifold = data.getManifold()
        val penetration = data.getPenetration()
        val constraint = data.getContactConstraint()
        return mapOf("type" to "org.dyn4j.world.WorldCollisionData",
            "body1" to body(body1, bodies),
            "body2" to body(body2, bodies),
            "fixture1" to fixtureId(data.getFixture1(), bodies),
            "fixture2" to fixtureId(data.getFixture2(), bodies),
            "velocity1" to vector(body1.getLinearVelocity()),
            "velocity2" to vector(body2.getLinearVelocity()),
            "angularVelocity1" to body1.getAngularVelocity(),
            "angularVelocity2" to body2.getAngularVelocity(),
            "isBroadphaseCollision" to data.isBroadphaseCollision(),
            "isNarrowphaseCollision" to data.isNarrowphaseCollision(),
            "isManifoldCollision" to data.isManifoldCollision(),
            "isContactConstraintCollision" to data.isContactConstraintCollision(),
            "penetration" to mapOf("type" to "org.dyn4j.collision.narrowphase.Penetration",
                "getNormal" to vector(penetration.getNormal()),
                "getDepth" to penetration.getDepth()),
            "manifold" to mapOf("type" to "org.dyn4j.collision.manifold.Manifold",
                "getNormal" to vector(manifold.getNormal()),
                "points" to manifold.getPoints().map { point -> mapOf(
                    "type" to "org.dyn4j.collision.manifold.ManifoldPoint",
                    "getPoint" to vector(point.getPoint()), "getDepth" to point.getDepth()) }),
            "constraint" to mapOf("type" to "org.dyn4j.dynamics.contact.ContactConstraint",
                "getNormal" to vector(constraint.getNormal()),
                "getTangent" to vector(constraint.getTangent()),
                "getFriction" to constraint.getFriction(),
                "getRestitution" to constraint.getRestitution(),
                "getRestitutionVelocity" to constraint.getRestitutionVelocity(),
                "getTangentSpeed" to constraint.getTangentSpeed(),
                "isEnabled" to constraint.isEnabled(), "isSensor" to constraint.isSensor(),
                "contacts" to constraint.getContacts().map(::contact)))
    }

    fun id(spec: CaseSpec): String = when {
        spec.id == "long-free-60" -> "L-free-s1.0-o0.0,0.0-hz60"
        spec.id.startsWith("contacts-default-") ->
            "S-sleep-wake-hz${spec.id.substringAfterLast('-')}"
        spec.id.startsWith("contacts-configured-") -> {
            val outer = spec.input["outerHz"] as Int
            val repetition = spec.input["repetition"] as Int
            "Q-sleep-wake-outer$outer-repeat$repetition"
        }
        spec.id == "P-JINT-Pulley-slack-transition-preparation-0" ||
            spec.id == "P-JINT-Pulley-slack-transition-preparation-1" ->
            "P-JINT-Pulley-slack-transition-preparation"
        spec.id == "P-JINT-Pulley-slack-transition-main" ->
            "P-JINT-Pulley-slack-transition"
        spec.id == "P-JINT-Weld-enabled-equal" -> spec.id
        else -> error("frozen event identity is unavailable for ${spec.id}")
    }

    fun step(spec: CaseSpec, name: String, number: Int, order: Int,
             value: TimeStep?): Map<String, Any?> {
        val time = value ?: error("step callback has no time step")
        val method = name.removePrefix("step.")
        require(method in setOf("begin", "updatePerformed", "postSolve", "end"))
        return mapOf("kind" to "event", "step" to number, "order" to order,
            "listener" to "StepListener",
            "method" to "public abstract void org.dyn4j.world.listener.StepListener.$method(org.dyn4j.dynamics.TimeStep,org.dyn4j.world.PhysicsWorld<T, ?>)",
            "payload" to listOf(mapOf(
                "type" to "org.dyn4j.dynamics.TimeStep",
                "getDeltaTime" to time.getDeltaTime(),
                "getDeltaTimeRatio" to time.getDeltaTimeRatio(),
                "getInverseDeltaTime" to time.getInverseDeltaTime(),
                "getPreviousInverseDeltaTime" to time.getPreviousInverseDeltaTime(),
                "getPrevousDeltaTime" to time.getPrevousDeltaTime()),
                mapOf("world" to id(spec))))
    }

    private fun event(number: Int, order: Int, listener: String, method: String,
                      payload: List<Any?>): Map<String, Any?> =
        mapOf("kind" to "event", "step" to number, "order" to order,
            "listener" to listener, "method" to method, "payload" to payload)

    fun collisionEvent(stage: String, number: Int, order: Int,
                       value: BroadphaseCollisionData<Body, BodyFixture>?,
                       bodies: List<Body>): Map<String, Any?> {
        require(stage in setOf("Broadphase", "Narrowphase", "Manifold"))
        return event(number, order, "CollisionListener",
            "public abstract boolean org.dyn4j.world.listener.CollisionListener.collision(org.dyn4j.world.${stage}CollisionData<T, E>)",
            listOf(collision(value, bodies)))
    }

    fun contactEvent(name: String, number: Int, order: Int,
                     value: ContactCollisionData<Body>?, contacts: List<Contact?>,
                     bodies: List<Body>): Map<String, Any?> {
        val arguments = when (name) {
            "collision" -> "org.dyn4j.world.ContactCollisionData<T>"
            "postSolve" -> "org.dyn4j.world.ContactCollisionData<T>,org.dyn4j.dynamics.contact.SolvedContact"
            "persist" -> "org.dyn4j.world.ContactCollisionData<T>,org.dyn4j.dynamics.contact.Contact,org.dyn4j.dynamics.contact.Contact"
            "begin", "end", "destroyed", "preSolve" ->
                "org.dyn4j.world.ContactCollisionData<T>,org.dyn4j.dynamics.contact.Contact"
            else -> error("unsupported frozen contact callback: $name")
        }
        val payload = listOf(collision(value, bodies)) + contacts.map(::contact)
        return event(number, order, "ContactListener",
            "public abstract void org.dyn4j.world.listener.ContactListener.$name($arguments)",
            payload)
    }

    private fun timeOfImpact(value: TimeOfImpact?): Map<String, Any?> {
        require(value != null)
        val separation = value.getSeparation()
        return mapOf("type" to "org.dyn4j.collision.continuous.TimeOfImpact",
            "getTime" to value.getTime(),
            "separation" to mapOf("type" to "org.dyn4j.collision.narrowphase.Separation",
                "getDistance" to separation.getDistance(),
                "getNormal" to vector(separation.getNormal()),
                "getPoint1" to vector(separation.getPoint1()),
                "getPoint2" to vector(separation.getPoint2())))
    }

    fun toiEvent(number: Int, order: Int, body1: Body?, fixture1: BodyFixture?,
                 body2: Body?, fixture2: BodyFixture?, toi: TimeOfImpact?,
                 bodies: List<Body>): Map<String, Any?> {
        val withFixtures = fixture1 != null || fixture2 != null
        require((fixture1 == null) == (fixture2 == null))
        val args = if (withFixtures)
            "T,org.dyn4j.dynamics.BodyFixture,T,org.dyn4j.dynamics.BodyFixture"
            else "T,T"
        val method = "public abstract boolean org.dyn4j.world.listener.TimeOfImpactListener.collision($args${if (toi != null) ",org.dyn4j.collision.continuous.TimeOfImpact" else ""})"
        val payload = if (withFixtures)
            listOf(body(body1, bodies), fixture(fixture1, bodies),
                body(body2, bodies), fixture(fixture2, bodies))
            else listOf(body(body1, bodies), body(body2, bodies))
        return event(number, order, "TimeOfImpactListener", method,
            payload + if (toi != null) listOf(timeOfImpact(toi)) else emptyList())
    }

    fun experimentalBinding(spec: CaseSpec, number: Int, order: Int): Map<String, Any?> {
        val description = when (spec.id) {
            "P-JINT-Weld-enabled-equal" -> listOf(
                "Weld enabled-equal experiment",
                "enabled equal limits[0,0]; source-compatible drive; Distance initialseparation2/rest10, Prism motor1/cap10, Revolute motorpi/2/cap.25, Weld source offcentre force; active type=Weld")
            "P-JINT-Pulley-slack-transition-main" -> listOf(
                "Pulley fresh slack-transition experiment",
                "withAndWithoutSlack exact3body preparation: step1,velocity(0,10),step2; slackfalse; before201 velocity(0,10),translate(0,.1),slacktrue; before401 slackfalse; same world retained")
            else -> error("experimental binding is unavailable for ${spec.id}")
        }
        return mapOf("kind" to "instrumented-callback", "step" to number,
            "order" to order, "id" to id(spec),
            "event" to "experimental-input-binding",
            "values" to listOf("058bf6d982a0fb89b54050f929f6ea9dae53b714",
                description[0], description[1],
                "new experimental input; not U or acceptance approval"))
    }

    fun wakeState(spec: CaseSpec, name: String, number: Int, order: Int,
                  state: Map<String, Any?>): Map<String, Any?> {
        require(name == "before-wake" || name == "after-wake")
        return mapOf("kind" to "instrumented-callback", "step" to number,
            "order" to order, "id" to id(spec), "event" to name,
            "values" to listOf(state))
    }

    fun actions(spec: CaseSpec, number: Int, firstOrder: Int,
                sleepingBefore: Boolean, precedingSecondAsleep: Boolean): List<Map<String, Any?>> {
        val descriptions = when {
            spec.id.startsWith("contacts-default-") || spec.id.startsWith("contacts-configured-") ->
                listOf("impulse=(1,0) at center; sleepingBefore=$sleepingBefore; precedingSecondAsleep=$precedingSecondAsleep")
            spec.id == "P-JINT-Pulley-slack-transition-main" && number == 201 ->
                listOf("body2.setLinearVelocity(0,10)", "body2.translate(0,.1)",
                    "setSlackEnabled(true)")
            spec.id == "P-JINT-Pulley-slack-transition-main" && number == 401 ->
                listOf("setSlackEnabled(false)")
            else -> error("unsupported frozen action at ${spec.id} step $number")
        }
        return descriptions.mapIndexed { index, description ->
            mapOf("kind" to "action", "id" to id(spec), "step" to number,
                "order" to firstOrder + index, "description" to description)
        }
    }
}
