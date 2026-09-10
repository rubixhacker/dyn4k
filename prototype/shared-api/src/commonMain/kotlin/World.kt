package org.dyn4j.world

import kotlin.jvm.JvmField
import org.dyn4j.dynamics.*
import org.dyn4j.dynamics.contact.*
import org.dyn4j.geometry.Vector2
import org.dyn4j.world.listener.StepListener
import probe.liveReadOnly

interface PhysicsWorld<T : PhysicsBody, V> {
    fun getBody(index: Int): T
    fun getBodies(): List<T>
    fun getBodyCount(): Int
    fun addBody(body: T)
    fun removeBody(body: T): Boolean
}
open class World<T : Body> : PhysicsWorld<T, Unit> {
    @JvmField protected val bodies = mutableListOf<T>()
    @JvmField protected val settings = Settings()
    @JvmField protected val gravity = Vector2(0.0, -9.8)
    @JvmField protected val timeStep = TimeStep(1.0 / 60.0)
    private val view = liveReadOnly(bodies)
    private val listeners = mutableListOf<StepListener<T>>()
    private var updateRequired = true
    private var solver: ContactConstraintSolver<T> = object : ContactConstraintSolver<T> {
        override fun initialize(contactConstraints: List<ContactConstraint<T>>, step: TimeStep, settings: Settings) = Unit
        override fun solveVelocityContraints(contactConstraints: List<ContactConstraint<T>>, step: TimeStep, settings: Settings) = Unit
        override fun solvePositionContraints(contactConstraints: List<ContactConstraint<T>>, step: TimeStep, settings: Settings) = true
    }
    override fun getBody(index: Int): T = bodies[index]
    override fun getBodies(): List<T> = view
    override fun getBodyCount(): Int = bodies.size
    override fun addBody(body: T) { require(body !in bodies); bodies.add(body); updateRequired = true }
    override fun removeBody(body: T): Boolean = bodies.remove(body).also { if (it) updateRequired = true }
    open fun removeBody(index: Int): Boolean = removeBody(bodies[index])
    open fun addStepListener(listener: StepListener<T>): Boolean = listeners.add(listener)
    open fun setContactConstraintSolver(solver: ContactConstraintSolver<T>) { this.solver = solver }
    open fun getContactConstraintSolver(): ContactConstraintSolver<T> = solver
    open fun step(steps: Int, elapsedTime: Double) {
        if (steps <= 0 || elapsedTime <= 0.0) return
        timeStep.update(elapsedTime)
        repeat(steps) { step() }
    }
    // A real restricted step: independent kinematic bodies, no contacts, joints, rotation or CCD.
    // Ordering follows AbstractPhysicsWorld.step + Island.solve at the pinned baseline.
    protected open fun step() {
        for (listener in listeners) listener.begin(timeStep, this)
        if (updateRequired) {
            for (listener in listeners) listener.updatePerformed(timeStep, this)
            updateRequired = false
        }
        for (body in bodies.asReversed()) {
            val velocity = body.getLinearVelocity()
            if (velocity.x == 0.0 && velocity.y == 0.0) continue
            body.integrateVelocity(gravity, timeStep, settings)
            val constraints = emptyList<ContactConstraint<T>>()
            solver.initialize(constraints, timeStep, settings)
            body.integratePosition(timeStep, settings)
            for (iteration in 0 until settings.getPositionConstraintSolverIterations()) {
                if (solver.solvePositionContraints(constraints, timeStep, settings)) break
            }
        }
        for (listener in listeners) listener.postSolve(timeStep, this)
        for (listener in listeners) listener.end(timeStep, this)
    }
    open fun getBodyIterator(): MutableIterator<T> = object : MutableIterator<T> {
        private var index = -1
        private var removed = false
        override fun hasNext(): Boolean = index + 1 < bodies.size
        override fun next(): T {
            if (!hasNext()) throw IndexOutOfBoundsException()
            index++
            removed = false
            return bodies[index]
        }
        override fun remove() {
            if (index < 0 || removed) throw IllegalStateException()
            if (index >= bodies.size) throw IndexOutOfBoundsException()
            removeBody(index)
            index--
            removed = true
        }
    }
}
