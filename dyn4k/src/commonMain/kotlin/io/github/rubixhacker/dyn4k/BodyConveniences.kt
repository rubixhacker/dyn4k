package io.github.rubixhacker.dyn4k

fun body(block: Body.() -> Unit = {}): Body = Body().apply(block)

fun PhysicsBody.fixture(shape: Convex, block: BodyFixture.() -> Unit = {}): BodyFixture =
    addFixture(shape).apply(block)

val PhysicsBody.fixtures: List<BodyFixture> get() = getFixtures()
val PhysicsBody.transform: Transform get() = getTransform()
val PhysicsBody.worldCenter: Vector2 get() = getWorldCenter()

var PhysicsBody.massType: MassType
    get() = getMass().getType()
    set(value) { setMass(value) }

var PhysicsBody.linearVelocity: Vector2
    get() = getLinearVelocity()
    set(value) { setLinearVelocity(value) }

var PhysicsBody.angularVelocity: Double
    get() = getAngularVelocity()
    set(value) { setAngularVelocity(value) }

var PhysicsBody.enabled: Boolean
    get() = isEnabled()
    set(value) { setEnabled(value) }

var PhysicsBody.bullet: Boolean
    get() = isBullet()
    set(value) { setBullet(value) }

var BodyFixture.density: Double
    get() = getDensity()
    set(value) { setDensity(value) }

var BodyFixture.friction: Double
    get() = getFriction()
    set(value) { setFriction(value) }

var BodyFixture.restitution: Double
    get() = getRestitution()
    set(value) { setRestitution(value) }
