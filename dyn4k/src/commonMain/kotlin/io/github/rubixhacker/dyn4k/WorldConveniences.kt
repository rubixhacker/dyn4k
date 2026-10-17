package io.github.rubixhacker.dyn4k

import org.dyn4j.dynamics.joint.DistanceJoint
import org.dyn4j.dynamics.joint.Joint
import org.dyn4j.world.ContactCollisionData
import org.dyn4j.world.PhysicsWorld

fun world(block: World<Body>.() -> Unit = {}): World<Body> = World<Body>().apply(block)

fun <T : PhysicsBody, V : ContactCollisionData<T>, W : PhysicsWorld<T, V>> world(
    instance: W,
    block: W.() -> Unit = {},
): W = instance.apply(block)

fun World<Body>.body(block: Body.() -> Unit = {}): Body =
    Body().apply(block).also(::addBody)

fun <T : PhysicsBody, V : ContactCollisionData<T>> PhysicsWorld<T, V>.add(body: T): T =
    body.also(::addBody)

fun <T : PhysicsBody, V : ContactCollisionData<T>, J : Joint<T>> PhysicsWorld<T, V>.add(joint: J): J =
    joint.also(::addJoint)

fun <T : PhysicsBody, V : ContactCollisionData<T>> PhysicsWorld<T, V>.distanceJoint(
    first: T,
    second: T,
    firstAnchor: Vector2,
    secondAnchor: Vector2,
    block: DistanceJoint<T>.() -> Unit = {},
): DistanceJoint<T> = add(DistanceJoint(first, second, firstAnchor, secondAnchor).apply(block))

val <T : PhysicsBody, V : ContactCollisionData<T>> PhysicsWorld<T, V>.bodies: List<T>
    get() = getBodies()

val <T : PhysicsBody, V : ContactCollisionData<T>> PhysicsWorld<T, V>.joints: List<Joint<T>>
    get() = getJoints()

var <T : PhysicsBody, V : ContactCollisionData<T>> PhysicsWorld<T, V>.gravity: Vector2
    get() = getGravity()
    set(value) { setGravity(value) }

var <T : PhysicsBody, V : ContactCollisionData<T>> PhysicsWorld<T, V>.settings: Settings
    get() = getSettings()
    set(value) { setSettings(value) }

var <T : PhysicsBody> Joint<T>.collisionAllowed: Boolean
    get() = isCollisionAllowed()
    set(value) { setCollisionAllowed(value) }
