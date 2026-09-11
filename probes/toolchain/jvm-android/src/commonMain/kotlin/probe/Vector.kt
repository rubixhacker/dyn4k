package probe
class Vector(var x: Double, var y: Double) {
    fun dot(other: Vector): Double = x * other.x + y * other.y
}
