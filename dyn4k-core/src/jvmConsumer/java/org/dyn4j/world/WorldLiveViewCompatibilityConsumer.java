package org.dyn4j.world;

import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;
import org.dyn4j.dynamics.Body;
import org.dyn4j.dynamics.BodyFixture;
import org.dyn4j.world.listener.BoundsListenerAdapter;
import org.dyn4j.world.listener.CollisionListenerAdapter;

public final class WorldLiveViewCompatibilityConsumer {
    private static final class ProbeWorld extends World<Body> {
        String bodyBackingClass() { return bodies.getClass().getName(); }
        void sortBodies() { bodies.sort((left, right) -> 0); }
        void replaceBodies() { bodies.replaceAll(body -> body); }
    }

    private static void expectStaleChildRead(List<?> stale) {
        List<?> child = stale.subList(0, 1);
        System.out.println("childCreate=OK");
        boolean java8 = "1.8".equals(System.getProperty("java.specification.version"));
        try {
            child.get(0);
            if (!java8) throw new AssertionError("stale child read succeeded");
            System.out.println("childRead=SAME");
        } catch (ConcurrentModificationException expected) {
            if (java8) throw new AssertionError("Java 8 child read changed", expected);
            System.out.println("childRead=CME");
        }
    }

    private static void expectIteratorInvalidated(Iterator<?> iterator) {
        try {
            iterator.next();
            throw new AssertionError("view iterator was not invalidated");
        } catch (ConcurrentModificationException expected) {
        }
    }

    private static void run(String mode) {
        ProbeWorld world = new ProbeWorld();
        Body first = new Body();
        switch (mode) {
            case "backing":
                if (!"java.util.ArrayList".equals(world.bodyBackingClass())) {
                    throw new AssertionError("protected body backing: " + world.bodyBackingClass());
                }
                break;
            case "bodyAdd":
                world.addBody(first);
                List<Body> staleAfterAdd = world.getBodies().subList(0, 1);
                world.addBody(new Body());
                expectStaleChildRead(staleAfterAdd);
                break;
            case "bodySameSize":
                world.addBody(first);
                List<Body> staleAfterReplace = world.getBodies().subList(0, 1);
                world.removeBody(first);
                world.addBody(new Body());
                expectStaleChildRead(staleAfterReplace);
                break;
            case "sort":
                world.addBody(first);
                world.addBody(new Body());
                Iterator<Body> beforeSort = world.getBodies().iterator();
                world.sortBodies();
                expectIteratorInvalidated(beforeSort);
                break;
            case "replaceAll":
                world.addBody(first);
                world.addBody(new Body());
                Iterator<Body> beforeReplace = world.getBodies().iterator();
                world.replaceBodies();
                expectIteratorInvalidated(beforeReplace);
                break;
            case "boundsAdd":
                BoundsListenerAdapter<Body, BodyFixture> firstBounds = new BoundsListenerAdapter<>();
                world.addBoundsListener(firstBounds);
                List<?> staleBoundsAfterAdd = world.getBoundsListeners().subList(0, 1);
                world.addBoundsListener(new BoundsListenerAdapter<Body, BodyFixture>());
                expectStaleChildRead(staleBoundsAfterAdd);
                break;
            case "boundsSameSize":
                BoundsListenerAdapter<Body, BodyFixture> removedBounds = new BoundsListenerAdapter<>();
                world.addBoundsListener(removedBounds);
                List<?> staleBoundsAfterReplace = world.getBoundsListeners().subList(0, 1);
                world.removeBoundsListener(removedBounds);
                world.addBoundsListener(new BoundsListenerAdapter<Body, BodyFixture>());
                expectStaleChildRead(staleBoundsAfterReplace);
                break;
            case "collisionAdd":
                CollisionListenerAdapter<Body, BodyFixture> firstCollision = new CollisionListenerAdapter<>();
                world.addCollisionListener(firstCollision);
                List<?> staleCollisionAfterAdd = world.getCollisionListeners().subList(0, 1);
                world.addCollisionListener(new CollisionListenerAdapter<Body, BodyFixture>());
                expectStaleChildRead(staleCollisionAfterAdd);
                break;
            case "collisionSameSize":
                CollisionListenerAdapter<Body, BodyFixture> removedCollision = new CollisionListenerAdapter<>();
                world.addCollisionListener(removedCollision);
                List<?> staleCollisionAfterReplace = world.getCollisionListeners().subList(0, 1);
                world.removeCollisionListener(removedCollision);
                world.addCollisionListener(new CollisionListenerAdapter<Body, BodyFixture>());
                expectStaleChildRead(staleCollisionAfterReplace);
                break;
            default:
                throw new AssertionError("unknown mode: " + mode);
        }
        System.out.println(mode + "=OK");
    }

    public static void main(String[] args) {
        String[] modes = args.length == 0 ? new String[] {
            "backing", "bodyAdd", "bodySameSize", "sort", "replaceAll",
            "boundsAdd", "boundsSameSize", "collisionAdd", "collisionSameSize"
        } : args;
        for (String mode : modes) run(mode);
    }
}
