import io.github.rubixhacker.dyn4k.Body
import io.github.rubixhacker.dyn4k.Circle
import io.github.rubixhacker.dyn4k.Force
import io.github.rubixhacker.dyn4k.MassType
import io.github.rubixhacker.dyn4k.PhysicsBody
import io.github.rubixhacker.dyn4k.Vector2

object DynamicsKotlinConsumer {
    @JvmStatic
    fun main(args: Array<String>) {
        val body: Body = Body()
        check(Body(fixtureCount = 2).getFixtureCount() == 0)
        val shared: PhysicsBody = body
        val fixture = body.addFixture(Circle(1.0))
        check(shared.getFixture(0) === fixture)
        shared.setMass(MassType.NORMAL)
        val force = Force(x = 2.0, y = 0.0)
        body.applyForce(force)
        force.getForce().x = 3.0
        check(shared.getAccumulatedForce().x == 3.0)
        val velocity = body.getLinearVelocity()
        shared.applyImpulse(Vector2(1.0, 0.0))
        check(body.getLinearVelocity() === velocity && velocity.x > 0.0)
        println("DYNAMICS_KOTLIN_CONSUMER_OK")
    }
}
