package org.dyn4j.dynamics

import kotlin.jvm.JvmField
import kotlin.math.sqrt
import org.dyn4j.collision.AbstractCollisionBody
import org.dyn4j.collision.Fixture
import org.dyn4j.geometry.Vector2

open class BodyFixture : Fixture()
interface PhysicsBody {
    fun getLinearVelocity(): Vector2
    fun integrateVelocity(gravity: Vector2, timestep: TimeStep, settings: Settings)
    fun integratePosition(timestep: TimeStep, settings: Settings)
}
open class TimeStep(private var deltaTime: Double) {
    open fun getDeltaTime(): Double = deltaTime
    open fun update(deltaTime: Double) { this.deltaTime = deltaTime }
}
open class Settings {
    open fun getMaximumTranslation(): Double = 2.0
    open fun getPositionConstraintSolverIterations(): Int = 2
}
abstract class AbstractPhysicsBody : AbstractCollisionBody<BodyFixture>(), PhysicsBody {
    @JvmField protected val linearVelocity = Vector2()
    override fun getLinearVelocity(): Vector2 = linearVelocity
    open fun setLinearVelocity(x: Double, y: Double) { linearVelocity.x = x; linearVelocity.y = y }
    // Infinite mass, no force/rotation: the baseline's default kinematic body.
    override fun integrateVelocity(gravity: Vector2, timestep: TimeStep, settings: Settings) = Unit
    override fun integratePosition(timestep: TimeStep, settings: Settings) {
        var x = linearVelocity.x * timestep.getDeltaTime()
        var y = linearVelocity.y * timestep.getDeltaTime()
        val magnitudeSquared = x * x + y * y
        val maximum = settings.getMaximumTranslation()
        if (magnitudeSquared > maximum * maximum) {
            val ratio = maximum / sqrt(magnitudeSquared)
            linearVelocity.x *= ratio
            linearVelocity.y *= ratio
            x *= ratio
            y *= ratio
        }
        translate(x, y)
    }
}
open class Body : AbstractPhysicsBody()
