import org.dyn4j.collision.BasicCollisionItem
import org.dyn4j.collision.BasicCollisionPair
import org.dyn4j.collision.CollisionItem
import org.dyn4j.collision.manifold.Manifold
import org.dyn4j.collision.manifold.ManifoldPoint
import org.dyn4j.collision.manifold.ManifoldPointId
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.contact.ContactConstraint
import org.dyn4j.dynamics.contact.ContactUpdateHandler
import org.dyn4j.dynamics.contact.Contact
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.Vector2

object ContactKotlinConsumer {
    @JvmStatic fun main(args: Array<String>) {
        val first = Body()
        val second = Body()
        val fixture1 = first.addFixture(Circle(0.5))
        val fixture2 = second.addFixture(Circle(0.5))
        val pair = BasicCollisionPair<CollisionItem<Body, BodyFixture>>(
            BasicCollisionItem(first, fixture1), BasicCollisionItem(second, fixture2))
        val constraint = ContactConstraint(pair)
        val manifold = Manifold()
        manifold.setNormal(Vector2(1.0, 0.0))
        manifold.getPoints().add(ManifoldPoint(ManifoldPointId.DISTANCE).also {
            it.setPoint(Vector2(0.25, 0.0))
            it.setDepth(0.1)
        })
        val contacts = constraint.getContacts()
        var began = 0
        constraint.update(manifold, Settings(), object : ContactUpdateHandler {
            override fun getFriction(fixture1: BodyFixture, fixture2: BodyFixture) = 0.5
            override fun getRestitution(fixture1: BodyFixture, fixture2: BodyFixture) = 0.0
            override fun getRestitutionVelocity(fixture1: BodyFixture, fixture2: BodyFixture) = 1.0
            override fun begin(contact: Contact) { began++ }
            override fun persist(oldContact: Contact, newContact: Contact) {}
            override fun end(contact: Contact) {}
        })
        check(began == 1 && contacts.size == 1 && contacts[0].getDepth() == 0.1)
        println("contact-kotlin-consumer: passed")
    }
}
