package portable

import org.dyn4j.collision.Filter
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.dynamics.joint.Joint
import org.dyn4j.dynamics.joint.PulleyJoint
import org.dyn4j.dynamics.joint.WeldJoint
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Mass
import org.dyn4j.geometry.Rectangle
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2
import org.dyn4j.world.World
import kotlin.math.PI

internal object FrozenState {
    private fun vector(value: Vector2): List<Double> = listOf(value.x, value.y)

    private fun transform(value: Transform): Map<String, Any?> = mapOf(
        "type" to "org.dyn4j.geometry.Transform",
        "getTranslation" to vector(value.getTranslation()),
        "getTranslationX" to value.getTranslationX(),
        "getTranslationY" to value.getTranslationY(),
        "getCost" to value.getCost(),
        "getSint" to value.getSint(),
        "getRotationAngle" to value.getRotationAngle(),
        "getValues" to value.getValues().toList(),
        "isIdentity" to value.isIdentity(),
    )

    private fun mass(value: Mass): Map<String, Any?> = mapOf(
        "type" to "org.dyn4j.geometry.Mass",
        "getCenter" to vector(value.getCenter()),
        "getMass" to value.getMass(),
        "getInverseMass" to value.getInverseMass(),
        "getInertia" to value.getInertia(),
        "getInverseInertia" to value.getInverseInertia(),
        "getType" to value.getType().name,
        "isInfinite" to value.isInfinite(),
    )

    private fun shape(value: Convex): Map<String, Any?> = when (value) {
        is Circle -> mapOf("type" to "org.dyn4j.geometry.Circle",
            "getArea" to value.getArea(), "getCenter" to vector(value.getCenter()),
            "getRadius" to value.getRadius())
        is Rectangle -> mapOf("type" to "org.dyn4j.geometry.Rectangle",
            "getArea" to value.getArea(), "getCenter" to vector(value.getCenter()),
            "getWidth" to value.getWidth(), "getHeight" to value.getHeight(),
            "getRadius" to value.getRadius(), "getRotationAngle" to value.getRotationAngle(),
            "getNormals" to value.getNormals().map(::vector),
            "getVertices" to value.getVertices().map(::vector))
        else -> error("unsupported frozen fixture shape: ${value::class}")
    }

    private fun fixture(value: BodyFixture, id: String): Map<String, Any?> {
        require(value.getFilter() === Filter.DEFAULT_FILTER)
        return mapOf("type" to "org.dyn4j.dynamics.BodyFixture", "id" to id,
            "getDensity" to value.getDensity(), "getFriction" to value.getFriction(),
            "getRestitution" to value.getRestitution(),
            "getRestitutionVelocity" to value.getRestitutionVelocity(),
            "isSensor" to value.isSensor(),
            "filter" to mapOf("type" to "org.dyn4j.collision.Filter\$1"),
            "shape" to shape(value.getShape()))
    }

    private fun properties(value: Body): Map<String, Any?> = mapOf(
        "type" to "org.dyn4j.dynamics.Body",
        "getAccumulatedForce" to vector(value.getAccumulatedForce()),
        "getAccumulatedTorque" to value.getAccumulatedTorque(),
        "getAngularDamping" to value.getAngularDamping(),
        "getAngularVelocity" to value.getAngularVelocity(),
        "getChangeInOrientation" to value.getChangeInOrientation(),
        "getChangeInPosition" to vector(value.getChangeInPosition()),
        "getFixtureCount" to value.getFixtureCount(),
        "getForce" to vector(value.getForce()),
        "getGravityScale" to value.getGravityScale(),
        "getLinearDamping" to value.getLinearDamping(),
        "getLinearVelocity" to vector(value.getLinearVelocity()),
        "getLocalCenter" to vector(value.getLocalCenter()),
        "getMass" to mass(value.getMass()),
        "getPreviousTransform" to transform(value.getPreviousTransform()),
        "getRotationDiscRadius" to value.getRotationDiscRadius(),
        "getTorque" to value.getTorque(),
        "getTransform" to transform(value.getTransform()),
        "getWorldCenter" to vector(value.getWorldCenter()),
        "isAtRest" to value.isAtRest(),
        "isAtRestDetectionEnabled" to value.isAtRestDetectionEnabled(),
        "isBullet" to value.isBullet(),
        "isDynamic" to value.isDynamic(),
        "isEnabled" to value.isEnabled(),
        "isKinematic" to value.isKinematic(),
        "isStatic" to value.isStatic(),
    )

    private fun joint(value: Joint<Body>, index: Int, bodies: List<Body>, dt: Double): Map<String, Any?> {
        val shared = mapOf("id" to "j$index",
            "bodies" to value.getBodies().map { body -> "b${bodies.indexOf(body)}" },
            "getBodyCount" to value.getBodyCount(),
            "isCollisionAllowed" to value.isCollisionAllowed(),
            "isEnabled" to value.isEnabled(),
            "getReactionTorque" to value.getReactionTorque(1.0 / dt),
            "reactionForce" to vector(value.getReactionForce(1.0 / dt)),
            "reactionTorque" to value.getReactionTorque(1.0 / dt))
        return shared + when (value) {
            is WeldJoint<*> -> mapOf("type" to "org.dyn4j.dynamics.joint.WeldJoint",
                "getAnchor1" to vector(value.getAnchor1()),
                "getAnchor2" to vector(value.getAnchor2()),
                "getAngularTranslation" to value.getAngularTranslation(),
                "getLimitsReferenceAngle" to value.getLimitsReferenceAngle(),
                "getLowerLimit" to value.getLowerLimit(),
                "getUpperLimit" to value.getUpperLimit(),
                "getMaximumSpringTorque" to value.getMaximumSpringTorque(),
                "getSpringDampingRatio" to value.getSpringDampingRatio(),
                "getSpringFrequency" to value.getSpringFrequency(),
                "getSpringMode" to value.getSpringMode(),
                "getSpringStiffness" to value.getSpringStiffness(),
                "getSpringTorque" to value.getSpringTorque(1.0 / dt),
                "isLimitsEnabled" to value.isLimitsEnabled(),
                "isMaximumSpringTorqueEnabled" to value.isMaximumSpringTorqueEnabled(),
                "isSpringDamperEnabled" to value.isSpringDamperEnabled(),
                "isSpringEnabled" to value.isSpringEnabled())
            is PulleyJoint<*> -> mapOf("type" to "org.dyn4j.dynamics.joint.PulleyJoint",
                "getAnchor1" to vector(value.getAnchor1()),
                "getAnchor2" to vector(value.getAnchor2()),
                "getPulleyAnchor1" to vector(value.getPulleyAnchor1()),
                "getPulleyAnchor2" to vector(value.getPulleyAnchor2()),
                "getCurrentLength" to value.getCurrentLength(),
                "getCurrentLength1" to value.getCurrentLength1(),
                "getCurrentLength2" to value.getCurrentLength2(),
                "getLength" to value.getLength(),
                "getRatio" to value.getRatio(),
                "isSlackEnabled" to value.isSlackEnabled())
            else -> error("unsupported frozen joint type: ${value::class}")
        }
    }

    fun capture(world: World<Body>, bodies: List<Body>, joints: List<Joint<Body>>,
                rotations: List<Double>, dt: Double, origin: List<Double>,
                initial: Boolean): Map<String, Any?> = mapOf(
        "bodies" to bodies.mapIndexed { index, body ->
            val center = body.getWorldCenter()
            mapOf("id" to "b$index",
                "transform" to transform(body.getTransform()),
                "previousTransform" to transform(body.getPreviousTransform()),
                "worldCenter" to vector(center),
                "fixedOriginPosition" to listOf(center.x - origin[0], center.y - origin[1]),
                "velocity" to vector(body.getLinearVelocity()),
                "angularVelocity" to body.getAngularVelocity(),
                "atRest" to body.isAtRest(),
                "force" to vector(body.getForce()),
                "torque" to body.getTorque(),
                "accumulatedForce" to vector(body.getAccumulatedForce()),
                "accumulatedTorque" to body.getAccumulatedTorque(),
                "rotationIncrementSum" to rotations[index],
                "rotationTrackingScope" to "segment-only; unrecorded transform mutations invalidate",
                "rotationStepBoundBelowPi" to (world.getSettings().getMaximumRotation() < PI)) +
                if (initial) mapOf("properties" to properties(body),
                    "fixtures" to body.getFixtures().mapIndexed { number, fixture ->
                        fixture(fixture, "b${index}f$number") }) else emptyMap()
        },
        "joints" to joints.mapIndexed { index, joint -> joint(joint, index, bodies, dt) },
    )
}
