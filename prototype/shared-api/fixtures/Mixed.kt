import dyn4k.*
import org.dyn4j.dynamics.Body
import org.dyn4j.world.World

fun main() {
    val original = body { velocity.x = 2.0 }
    val retained = original.velocity
    val world = World<Body>()
    original.attachTo(world)
    world.onBegin { seen ->
        check(seen.getBody(0) === original)
        Consumer.observeAndMutate(original) {
            check(original.velocity === retained && retained.x == 4.0)
            original.velocity.x += 2.0
            check(world.members.single() === original)
        }
    }
    world.step(1, 0.25)
    check(retained === original.velocity && retained.x == 6.0)
    check(original.getTransform().getTranslationX() == 1.5)
    println("mixed.dsl-body=java-body;velocity=shared;java-to-kotlin-reentry=immediate;position=1.5")
    println("MIXED_JOURNEY_PASS")
}
