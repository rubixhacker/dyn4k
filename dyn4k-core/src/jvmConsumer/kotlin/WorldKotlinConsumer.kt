import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.collision.CollisionItem
import org.dyn4j.collision.CollisionPair
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.world.World
import org.dyn4j.world.WorldCollisionData

private class ExtendedWorld : World<Body>() {
    var created = 0

    fun protectedStateMatchesPublic(): Boolean = settings === getSettings()

    protected override fun createCollisionData(
        pair: CollisionPair<CollisionItem<Body, BodyFixture>>
    ): WorldCollisionData<Body> {
        created++
        return super.createCollisionData(pair)
    }
}

object WorldKotlinConsumer {
    @JvmStatic
    fun main(args: Array<String>) {
        val world = ExtendedWorld()
        check(world.protectedStateMatchesPublic())
        val box = Body()
        box.addFixture(Geometry.createSquare(1.0))
        box.setMass(MassType.NORMAL)
        box.translate(0.0, 3.0)
        world.addBody(box)
        val view = world.getBodies()
        check(view.size == 1 && view[0] === box)
        world.step(30)
        check(box.getTransform().getTranslationY() < 3.0)
        check(world.containsBody(box))

        val contacts = ExtendedWorld()
        contacts.setGravity(0.0, 0.0)
        val moving = Body()
        moving.addFixture(Geometry.createCircle(1.0))
        moving.setMass(MassType.NORMAL)
        val fixed = Body()
        fixed.addFixture(Geometry.createCircle(1.0))
        contacts.addBody(moving)
        contacts.addBody(fixed)
        contacts.step(1)
        check(contacts.created > 0)
        check(contacts.protectedStateMatchesPublic())
        println("WorldKotlinConsumer OK")
    }
}
