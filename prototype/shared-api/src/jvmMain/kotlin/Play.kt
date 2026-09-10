package probe

import dyn4k.*
import org.dyn4j.dynamics.Body
import org.dyn4j.world.World

fun main() {
    val world = World<Body>()
    val body = body { velocity.x = 2.0 }
    val alias = body.velocity
    val snapshot = alias.copy()
    val members = world.members
    body.attachTo(world)
    var callback = false
    var message = "THROWAWAY: kinematic translation only, no contacts/forces/rotation."
    world.onBegin { if (callback && it.getBodyCount() > 0) it.getBody(0).getLinearVelocity().x += 1.0 }
    while (true) {
        print("\u001b[2J\u001b[H")
        println("\u001b[1mShared mutable API prototype\u001b[0m")
        println("position.x = ${body.getTransform().getTranslationX()}")
        println("velocity.x = ${alias.x}")
        println("snapshot.x = ${snapshot.x}")
        println("same velocity object = ${alias === body.velocity}")
        println("live membership size = ${members.size}")
        println("callback +1 = $callback")
        println(message)
        println("[k] Kotlin +1  [j] shim field +1  [s] step .25  [c] callback")
        println("[a] attach  [r] remove  [q] quit (press Enter)")
        when (readlnOrNull()?.trim()) {
            "k" -> body.velocity.x += 1.0
            "j" -> body.getLinearVelocity().x += 1.0
            "s" -> world.step(1, 0.25)
            "c" -> callback = !callback
            "a" -> if (body !in members) body.attachTo(world)
            "r" -> world.removeBody(body)
            "q", null -> return
            else -> { message = "Unknown command. Use k, j, s, c, a, r, or q."; continue }
        }
        message = "State updated through the same authoritative model."
    }
}
