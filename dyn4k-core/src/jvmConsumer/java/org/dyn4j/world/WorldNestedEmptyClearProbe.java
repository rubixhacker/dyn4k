package org.dyn4j.world;

import java.util.List;
import org.dyn4j.dynamics.Body;
import org.dyn4j.world.listener.StepListener;
import org.dyn4j.world.listener.StepListenerAdapter;

final class WorldNestedEmptyClearProbe {
    private static final class ProbeWorld extends World<Body> {
        List<StepListener<Body>> backing() { return stepListeners; }
    }

    private static String check(Runnable call) {
        try { call.run(); return "VALUE"; }
        catch (RuntimeException error) { return error.getClass().getSimpleName(); }
    }

    public static void main(String[] args) {
        ProbeWorld world = new ProbeWorld();
        world.addStepListener(new StepListenerAdapter<Body>());
        List<StepListener<Body>> root = world.backing();
        List<StepListener<Body>> parent = root.subList(0, 1);
        List<StepListener<Body>> child = parent.subList(0, 0);
        List<StepListener<Body>> sibling = parent.subList(0, 1);
        List<StepListener<Body>> unrelated = root.subList(0, 1);
        child.clear();
        System.out.println("root=" + root.size() + ",parent=" + check(parent::size) +
            ",child=" + check(child::size) + ",sibling=" + check(sibling::size) +
            ",unrelated=" + check(unrelated::size));
    }
}
