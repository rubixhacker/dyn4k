# Build a simulation with the Kotlin API

Use `io.github.rubixhacker.dyn4k` for Kotlin names and conveniences. The `org.dyn4j` types remain the compatibility API. Each Kotlin type alias names the same core class. Builders and properties call its public methods. They do not create a second simulation model.

## Create and step a world

```kotlin
import io.github.rubixhacker.dyn4k.*

val simulation = world {
    gravity = Vector2(0.0, -9.8)
    val ground = body {
        fixture(rectangle(10.0, 0.5))
        massType = MassType.INFINITE
    }
    val ball = body {
        fixture(circle(0.5)) { density = 2.0; restitution = 0.4 }
        massType = MassType.NORMAL
        translate(0.0, 3.0)
    }
    distanceJoint(ground, ball, Vector2(0.0, 0.0), Vector2(0.0, 3.0))
}
simulation.step(1)
```

`world`, `body`, `fixture`, and `distanceJoint` use the same add methods as the compatibility API. `joint(existingJoint) { ... }` adds any concrete joint type. The package also has aliases for all ten concrete joint classes. The builder block is optional: `val simulation = world()` and `simulation.add(body())` provide the same construction path.

Use `shape(existingShape) { ... }` to configure any core shape. It returns the same shape reference. `circle`, `rectangle`, and `polygon` are short constructors for common shapes. All other core shape constructors remain available through their Kotlin aliases.

## Observe state and query objects

```kotlin
val first = simulation.bodies.first()
val velocity = first.linearVelocity
velocity.x = 2.0
val snapshot = velocity.copy()

val nearby = simulation.find(AABB(-2.0, -2.0, 2.0, 2.0)) { body, fixture ->
    body.enabled && !fixture.isSensor()
}
val stepListener = simulation.onStepBegin { step, source ->
    if (step != null && source != null) println(source.bodies.size)
}
simulation.removeStepListener(stepListener)
```

`linearVelocity`, shape `center`, and world `gravity` expose live mutable vectors. Mutating a returned vector changes the object that the engine uses. Call `copy()` for an independent vector. Setting `linearVelocity` calls the core setter; the core can copy the supplied coordinates. The `bodies`, `joints`, and `fixtures` properties expose the core's live, read-only membership views. Add and remove members through the owner methods so the engine updates its bookkeeping.

`find` accepts bounds or a convex shape with a transform. `raycastWhere`, `raycastClosestWhere`, and `sweep` cover ray and moving-shape queries. Each helper passes a Kotlin predicate through a core `DetectFilter`. The predicate receives the actual body and fixture objects. `onStepBegin`, `onStepEnd`, `onContactBegin`, and `onContactEnd` register core listeners and return those listeners for removal. Callbacks run at the core's normal event stage. Avoid changing world membership while the engine iterates it unless the core operation permits that change.

## Mix Kotlin and Java use

```java
import org.dyn4j.dynamics.Body;
import org.dyn4j.geometry.Circle;
import org.dyn4j.geometry.MassType;

Body ball = new Body();
ball.addFixture(new Circle(0.5));
ball.setMass(MassType.NORMAL);
ball.getLinearVelocity().x = 2.0;
```

The Kotlin API can add this same `Body` to `World<Body>`. The Java step listener in the mixed example receives that body through the same world reference. A change through either API is visible through the other. The executable direct, Java, and mixed examples are in `dyn4k/src/commonTest/kotlin/io/github/rubixhacker/dyn4k/IdiomaticApiTest.kt`, `dyn4k/src/jvmTest/java/IdiomaticJavaExample.java`, and `dyn4k/src/jvmTest/kotlin/io/github/rubixhacker/dyn4k/IdiomaticMixedExampleTest.kt`.

## Choose units consistently

The engine does not select a length or mass unit for the application. Use one system throughout a world. For a metre and kilogram convention, positions and shape sizes use metres, velocity uses metres per second, gravity uses metres per second squared, density uses kilograms per square metre, force uses newtons, and torque uses newton metres. Time arguments use seconds. Angles and angular velocity use radians and radians per second. A call to `step(1)` advances by the configured step frequency; check `settings` when elapsed time matters.

These conveniences do not qualify the full engine or every target. See the implementation ledger and target evidence for current qualification status.
