package qualification

import io.github.rubixhacker.dyn4k.Vector2

fun main() {
    val point = Vector2(3.0, 4.0)
    check(point.getMagnitude() == 5.0) { "staged Kotlin vector magnitude" }
    point.x = 6.0
    check(point.x == 6.0) { "shared mutable core object" }
    JavaMigration.run()
    println("STAGED_CONSUMER_PASSED kotlin=2 java=1")
}
