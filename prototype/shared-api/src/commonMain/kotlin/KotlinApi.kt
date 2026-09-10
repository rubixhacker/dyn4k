package dyn4k

import org.dyn4j.dynamics.Body
import org.dyn4j.geometry.Vector2
import org.dyn4j.world.World
import org.dyn4j.world.PhysicsWorld
import org.dyn4j.world.listener.StepListenerAdapter
import org.dyn4j.dynamics.TimeStep

// No wrapping, copied state, caches, synchronization, or independent physics.
val Body.velocity: Vector2 get() = getLinearVelocity()
val <T : Body> World<T>.members: List<T> get() = getBodies()
fun body(configure: Body.() -> Unit = {}): Body = Body().apply(configure)
fun <T : Body> T.attachTo(world: World<T>) = world.addBody(this)
context(world: World<Body>)
fun Body.attach() = attachTo(world)
fun <T : Body> World<T>.onBegin(callback: (PhysicsWorld<T, *>) -> Unit) {
    addStepListener(object : StepListenerAdapter<T>() {
        override fun begin(step: TimeStep, world: PhysicsWorld<T, *>) = callback(world)
    })
}
