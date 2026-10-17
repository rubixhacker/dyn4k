import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.dynamics.joint.DistanceJoint
import org.dyn4j.dynamics.joint.Joint
import org.dyn4j.dynamics.joint.RevoluteJoint
import org.dyn4j.dynamics.joint.WheelJoint
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2

private class KotlinDistance(a: Body, b: Body, first: Vector2, second: Vector2) :
    DistanceJoint<Body>(a, b, first, second) {
    fun rawRestDistance(): Double = restDistance
    fun rawLocalAnchor(): Vector2 = localAnchor1
    override fun getRestDistance(): Double = super.getRestDistance() + 1.0
}

object JointKotlinConsumer {
    @JvmStatic
    fun main(args: Array<String>) {
        val a = Body()
        val b = Body()
        a.addFixture(Circle(0.5))
        b.addFixture(Circle(0.5))
        a.setMass(MassType.NORMAL)
        b.setMass(MassType.NORMAL)
        b.translate(1.0, 0.0)
        val anchor = Vector2(0.0, 0.0)
        val distance = DistanceJoint(body1 = a, body2 = b, anchor1 = anchor, anchor2 = Vector2(1.0, 0.0))
        distance.setSpringFrequency(8.0)
        distance.setSpringDampingRatio(0.3)
        distance.setSpringEnabled(true)
        distance.setSpringDamperEnabled(true)
        val extended = KotlinDistance(a, b, anchor, Vector2(1.0, 0.0))
        val dispatched: DistanceJoint<Body> = extended
        check(extended.rawRestDistance() == 1.0)
        check(extended.rawLocalAnchor() == anchor)
        check(dispatched.getRestDistance() == 2.0)
        val revolute = RevoluteJoint(body1 = a, body2 = b, anchor = anchor)
        revolute.setMotorEnabled(true)
        revolute.setMotorSpeed(1.0)
        val wheel = WheelJoint(frame = a, wheel = b, anchor = anchor, axis = Vector2(1.0, 0.0))
        wheel.setSpringFrequency(8.0)
        wheel.setSpringEnabled(true)
        val joints: List<Joint<Body>> = listOf(distance, revolute, wheel)
        val step = TimeStep(1.0 / 60.0)
        val settings = Settings()
        joints.forEach { joint ->
            check(joint.getBody(0) === a)
            joint.initializeConstraints(step, settings)
            joint.solveVelocityConstraints(step, settings)
            joint.solvePositionConstraints(step, settings)
            val reaction = joint.getReactionForce(step.getInverseDeltaTime())
            check(reaction.x.isFinite() && reaction.y.isFinite())
        }
        println("JOINT_KOTLIN_CONSUMER_OK")
    }
}
