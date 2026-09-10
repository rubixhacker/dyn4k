package probe

import dyn4k.*
import org.dyn4j.dynamics.Body
import org.dyn4j.world.World

fun journey() {
    val world = World<Body>()
    val body = body { velocity.x = 2.0 }
    val retained = body.velocity
    val snapshot = retained.copy()
    val members = world.members
    with(world) { body.attach() }
    check(members.single() === body)
    var calls = 0
    world.onBegin { seen ->
        check(seen === world && seen.getBody(0) === body)
        check(seen.getBody(0).getLinearVelocity() === retained)
        retained.x += 1.0
        if (calls++ == 0) world.step(1, 0.25)
    }
    world.step(1, 0.25)
    check(body.getTransform().getTranslationX() == 2.0)
    check(retained.x == 4.0 && snapshot.x == 2.0)
    val second = Body()
    second.attachTo(world)
    check(members.size == 2)
    val mutationRejected = try {
        (members as MutableList<Body>).add(Body())
        false
    } catch (_: UnsupportedOperationException) { true }
      catch (_: ClassCastException) { true }
    check(mutationRejected && members.size == 2)
    world.removeBody(second)
    check(members.size == 1)
    val explicit = World<Body>()
    val ordinary = Body()
    ordinary.setLinearVelocity(2.0, 0.0)
    ordinary.attachTo(explicit)
    check(ordinary.velocity.x == snapshot.x && explicit.members.single() === ordinary)
    println("kotlin.position=${body.getTransform().getTranslationX()}")
    println("kotlin.velocity=${retained.x};snapshot=${snapshot.x};callbacks=$calls")
    println("kotlin.context=explicit-equivalent;members=live;structural-mutation=rejected")
    println("KOTLIN_JOURNEY_PASS")
}
