package io.github.rubixhacker.dyn4k.optimized;

import org.dyn4j.collision.CollisionItem;
import org.dyn4j.collision.CollisionPair;
import org.dyn4j.dynamics.Body;
import org.dyn4j.dynamics.BodyFixture;
import org.dyn4j.dynamics.TimeStep;
import org.dyn4j.geometry.Geometry;
import org.dyn4j.geometry.MassType;
import org.dyn4j.geometry.Vector2;
import org.dyn4j.world.PhysicsWorld;
import org.dyn4j.world.World;
import org.dyn4j.world.WorldCollisionData;
import org.dyn4j.world.listener.StepListenerAdapter;

final class OptimizedConsumer {
    private static final class ProbeBody extends Body {
        int massCalls;

        @Override public ProbeBody setMass(MassType type) {
            massCalls++;
            super.setMass(type);
            return this;
        }
    }

    private static final class CountingWorld extends World<Body> {
        int collisionFactoryCalls;

        @Override protected WorldCollisionData<Body> createCollisionData(
                CollisionPair<CollisionItem<Body, BodyFixture>> pair) {
            collisionFactoryCalls++;
            return super.createCollisionData(pair);
        }
    }

    static String run() {
        Vector2 vector = new Vector2(3.0, 4.0);
        if (vector.getMagnitude() != 5.0 || vector.copy() == vector) {
            throw new AssertionError("vector value and identity");
        }
        vector.x = 6.0;
        if (vector.getMagnitude() != Math.sqrt(52.0)) {
            throw new AssertionError("vector mutation");
        }

        CountingWorld world = new CountingWorld();
        final int[] steps = new int[2];
        world.addStepListener(new StepListenerAdapter<Body>() {
            @Override public void begin(TimeStep step, PhysicsWorld<Body, ?> source) { steps[0]++; }
            @Override public void end(TimeStep step, PhysicsWorld<Body, ?> source) { steps[1]++; }
        });
        Body floor = new Body();
        floor.addFixture(Geometry.createRectangle(20.0, 1.0));
        floor.translate(0.0, -0.5);
        ProbeBody box = new ProbeBody();
        box.addFixture(Geometry.createSquare(1.0));
        box.translate(0.0, 3.0);
        box.setMass(MassType.NORMAL);
        world.addBody(floor);
        world.addBody(box);
        world.step(120);
        if (steps[0] != 120 || steps[1] != 120 || world.collisionFactoryCalls < 1 ||
                box.massCalls != 1 || box.getTransform().getTranslationY() >= 3.0 ||
                !world.containsBody(box)) {
            throw new AssertionError("world, body, or Java callback");
        }
        return "PASS:vector,body,world,subclass;steps=120";
    }
}
