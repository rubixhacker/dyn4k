package qualification

import io.github.rubixhacker.dyn4k.Body
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.dynamics.contact.Contact
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.MassType
import org.dyn4j.world.ContactCollisionData
import org.dyn4j.world.World
import org.dyn4j.world.listener.ContactListenerAdapter

class StagedWorldTest {
    @Test
    fun stagedModulesShareBodiesAndDeliverCollisionCallbacks() {
        val world = World<Body>()
        world.setGravity(0.0, 0.0)
        val moving = Body()
        moving.addFixture(Circle(1.0))
        moving.setMass(MassType.NORMAL)
        val fixed = Body()
        fixed.addFixture(Circle(1.0))
        val same: org.dyn4j.dynamics.Body = moving
        assertSame(moving, same)

        world.addBody(moving)
        world.addBody(fixed)
        assertSame(moving, world.getBody(0))
        assertEquals(2, world.getBodyCount())

        var collisions = 0
        var began = 0
        world.addContactListener(object : ContactListenerAdapter<Body>() {
            override fun collision(collision: ContactCollisionData<Body>?) {
                assertTrue(collision != null)
                collisions++
            }

            override fun begin(collision: ContactCollisionData<Body>?, contact: Contact?) {
                assertTrue(collision != null)
                assertTrue(contact != null)
                began++
            }
        })
        world.step(1)
        assertTrue(collisions > 0, "a collision callback must execute")
        assertTrue(began > 0, "a contact callback must execute")
    }
}
