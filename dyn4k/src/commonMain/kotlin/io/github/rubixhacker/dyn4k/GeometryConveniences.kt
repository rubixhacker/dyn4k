package io.github.rubixhacker.dyn4k

operator fun Vector2.plus(other: Vector2): Vector2 = sum(other)
operator fun Vector2.minus(other: Vector2): Vector2 = difference(other)
operator fun Vector2.times(scalar: Double): Vector2 = product(scalar)
operator fun Double.times(vector: Vector2): Vector2 = vector.product(this)
operator fun Vector2.div(scalar: Double): Vector2 = quotient(scalar)
operator fun Vector2.unaryMinus(): Vector2 = getNegative()
infix fun Vector2.dotWith(other: Vector2): Double = dot(other)
infix fun Vector2.crossWith(other: Vector2): Double = cross(other)

val Vector2.magnitude: Double get() = getMagnitude()
val Vector2.normalized: Vector2 get() = getNormalized()

val Shape.center: Vector2 get() = getCenter()
val Shape.area: Double get() = getArea()
val Shape.radius: Double get() = getRadius()

fun circle(radius: Double): Circle = Circle(radius)
fun rectangle(width: Double, height: Double): Rectangle = Rectangle(width, height)
fun polygon(vararg vertices: Vector2): Polygon = Polygon(*vertices)
fun <T : Shape> shape(value: T, block: T.() -> Unit): T = value.apply(block)
