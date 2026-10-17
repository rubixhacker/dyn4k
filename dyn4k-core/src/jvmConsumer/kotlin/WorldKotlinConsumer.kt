import org.dyn4j.dynamics.Body
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.world.World

object WorldKotlinConsumer {
    @JvmStatic
    fun main(args: Array<String>) {
        val world = World<Body>()
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
        println("WorldKotlinConsumer OK")
    }
}
