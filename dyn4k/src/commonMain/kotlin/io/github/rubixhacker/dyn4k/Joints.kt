package io.github.rubixhacker.dyn4k

import org.dyn4j.world.ContactCollisionData
import org.dyn4j.world.PhysicsWorld

typealias Joint<T> = org.dyn4j.dynamics.joint.Joint<T>
typealias AngleJoint<T> = org.dyn4j.dynamics.joint.AngleJoint<T>
typealias DistanceJoint<T> = org.dyn4j.dynamics.joint.DistanceJoint<T>
typealias FrictionJoint<T> = org.dyn4j.dynamics.joint.FrictionJoint<T>
typealias MotorJoint<T> = org.dyn4j.dynamics.joint.MotorJoint<T>
typealias PinJoint<T> = org.dyn4j.dynamics.joint.PinJoint<T>
typealias PrismaticJoint<T> = org.dyn4j.dynamics.joint.PrismaticJoint<T>
typealias PulleyJoint<T> = org.dyn4j.dynamics.joint.PulleyJoint<T>
typealias RevoluteJoint<T> = org.dyn4j.dynamics.joint.RevoluteJoint<T>
typealias WeldJoint<T> = org.dyn4j.dynamics.joint.WeldJoint<T>
typealias WheelJoint<T> = org.dyn4j.dynamics.joint.WheelJoint<T>

fun <T : PhysicsBody, V : ContactCollisionData<T>, J : Joint<T>> PhysicsWorld<T, V>.joint(
    joint: J,
    block: J.() -> Unit = {},
): J = add(joint.apply(block))
