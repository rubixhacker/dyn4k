import io.github.rubixhacker.dyn4k.Body
import io.github.rubixhacker.dyn4k.Circle
import io.github.rubixhacker.dyn4k.MassType
import org.dyn4j.dynamics.contact.Contact
import org.dyn4j.dynamics.contact.SolvedContact
import org.dyn4j.world.ContactCollisionData
import org.dyn4j.world.World
import org.dyn4j.world.listener.ContactListenerAdapter

private var assertions = 0

private fun check(label: String, condition: Boolean) {
    if (!condition) error("FAIL $label")
    println("ASSERT $label")
    assertions++
}

fun main() {
    val world = World<Body>()
    world.setGravity(0.0, 0.0)
    val moving = Body()
    moving.addFixture(Circle(1.0))
    moving.setMass(MassType.NORMAL)
    val fixed = Body()
    fixed.addFixture(Circle(1.0))
    world.addBody(moving)
    world.addBody(fixed)
    check("facade_body", world.getBody(0) === moving)
    check("body_count", world.getBodyCount() == 2)

    var began = 0
    var solved = 0
    world.addContactListener(object : ContactListenerAdapter<Body>() {
        override fun begin(collision: ContactCollisionData<Body>?, contact: Contact?) {
            began++
        }

        override fun postSolve(collision: ContactCollisionData<Body>?, contact: SolvedContact?) {
            solved++
        }
    })
    world.step(1)
    check("world_step", world.getTimeStep().getDeltaTime() > 0.0)
    check("contact_begin", began > 0)
    check("contact_solve", solved > 0)
    check("contact_present", world.getContacts(moving).isNotEmpty())
    println("NATIVE_RESULT PASS $assertions")
}
