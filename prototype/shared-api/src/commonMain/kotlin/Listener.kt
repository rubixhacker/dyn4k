package org.dyn4j.world.listener

import org.dyn4j.dynamics.PhysicsBody
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.world.PhysicsWorld

interface StepListener<T : PhysicsBody> {
    fun begin(step: TimeStep, world: PhysicsWorld<T, *>)
    fun updatePerformed(step: TimeStep, world: PhysicsWorld<T, *>)
    fun postSolve(step: TimeStep, world: PhysicsWorld<T, *>)
    fun end(step: TimeStep, world: PhysicsWorld<T, *>)
}
open class StepListenerAdapter<T : PhysicsBody> : StepListener<T> {
    override fun begin(step: TimeStep, world: PhysicsWorld<T, *>) = Unit
    override fun updatePerformed(step: TimeStep, world: PhysicsWorld<T, *>) = Unit
    override fun postSolve(step: TimeStep, world: PhysicsWorld<T, *>) = Unit
    override fun end(step: TimeStep, world: PhysicsWorld<T, *>) = Unit
}
