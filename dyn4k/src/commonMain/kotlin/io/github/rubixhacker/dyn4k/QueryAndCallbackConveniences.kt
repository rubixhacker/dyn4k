package io.github.rubixhacker.dyn4k

import org.dyn4j.dynamics.contact.Contact
import org.dyn4j.world.ContactCollisionData
import org.dyn4j.world.DetectFilter
import org.dyn4j.world.PhysicsWorld
import org.dyn4j.world.listener.ContactListener
import org.dyn4j.world.listener.ContactListenerAdapter
import org.dyn4j.world.listener.StepListener
import org.dyn4j.world.listener.StepListenerAdapter

fun <T : PhysicsBody, V : ContactCollisionData<T>> PhysicsWorld<T, V>.find(
    bounds: AABB,
    include: (T, BodyFixture) -> Boolean,
): List<DetectResult<T, BodyFixture>> = detect(bounds, predicateFilter(include))

fun <T : PhysicsBody, V : ContactCollisionData<T>> PhysicsWorld<T, V>.find(
    convex: Convex,
    transform: Transform,
    include: (T, BodyFixture) -> Boolean,
): List<ConvexDetectResult<T, BodyFixture>> = detect(convex, transform, predicateFilter(include))

fun <T : PhysicsBody, V : ContactCollisionData<T>> PhysicsWorld<T, V>.raycastWhere(
    ray: Ray,
    maxLength: Double,
    include: (T, BodyFixture) -> Boolean,
): List<RaycastResult<T, BodyFixture>> = raycast(ray, maxLength, predicateFilter(include))

fun <T : PhysicsBody, V : ContactCollisionData<T>> PhysicsWorld<T, V>.raycastClosestWhere(
    ray: Ray,
    maxLength: Double,
    include: (T, BodyFixture) -> Boolean,
): RaycastResult<T, BodyFixture>? = raycastClosest(ray, maxLength, predicateFilter(include))

fun <T : PhysicsBody, V : ContactCollisionData<T>> PhysicsWorld<T, V>.sweep(
    convex: Convex,
    transform: Transform,
    displacement: Vector2,
    rotation: Double = 0.0,
    include: (T, BodyFixture) -> Boolean,
): List<ConvexCastResult<T, BodyFixture>> =
    convexCast(convex, transform, displacement, rotation, predicateFilter(include))

private fun <T : PhysicsBody> predicateFilter(
    include: (T, BodyFixture) -> Boolean,
): DetectFilter<T, BodyFixture> = object : DetectFilter<T, BodyFixture>(false, false, null) {
    override fun isAllowed(body: T, fixture: BodyFixture): Boolean = include(body, fixture)
}

fun <T : PhysicsBody, V : ContactCollisionData<T>> PhysicsWorld<T, V>.onStepBegin(
    callback: (TimeStep?, PhysicsWorld<T, *>?) -> Unit,
): StepListener<T> = object : StepListenerAdapter<T>() {
    override fun begin(step: TimeStep?, world: PhysicsWorld<T, *>?) = callback(step, world)
}.also { addStepListener(it) }

fun <T : PhysicsBody, V : ContactCollisionData<T>> PhysicsWorld<T, V>.onStepEnd(
    callback: (TimeStep?, PhysicsWorld<T, *>?) -> Unit,
): StepListener<T> = object : StepListenerAdapter<T>() {
    override fun end(step: TimeStep?, world: PhysicsWorld<T, *>?) = callback(step, world)
}.also { addStepListener(it) }

fun <T : PhysicsBody, V : ContactCollisionData<T>> PhysicsWorld<T, V>.onContactBegin(
    callback: (ContactCollisionData<T>?, Contact?) -> Unit,
): ContactListener<T> = object : ContactListenerAdapter<T>() {
    override fun begin(collision: ContactCollisionData<T>?, contact: Contact?) = callback(collision, contact)
}.also { addContactListener(it) }

fun <T : PhysicsBody, V : ContactCollisionData<T>> PhysicsWorld<T, V>.onContactEnd(
    callback: (ContactCollisionData<T>?, Contact?) -> Unit,
): ContactListener<T> = object : ContactListenerAdapter<T>() {
    override fun end(collision: ContactCollisionData<T>?, contact: Contact?) = callback(collision, contact)
}.also { addContactListener(it) }
