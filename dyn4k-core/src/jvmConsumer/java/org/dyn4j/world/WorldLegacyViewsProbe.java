package org.dyn4j.world;

import java.util.Collections;
import java.util.List;
import java.util.RandomAccess;
import org.dyn4j.dynamics.Body;

final class WorldLegacyViewsProbe {
    private static String call(Runnable task) {
        try { task.run(); return "VALUE"; }
        catch (RuntimeException error) { return error.getClass().getSimpleName(); }
    }

    @SuppressWarnings("unchecked")
    private static void run(String name, List<?> raw) {
        List<Object> view = (List<Object>) raw;
        System.out.println(name + ",empty-removeIf=" + call(() -> view.removeIf(x -> false)) +
            ",randomAccess=" + (view instanceof RandomAccess) +
            ",subRandomAccess=" + (view.subList(0, 0) instanceof RandomAccess) +
            ",empty-sort=" + call(() -> view.sort((a, b) -> 0)) +
            ",empty-replaceAll=" + call(() -> view.replaceAll(x -> x)) +
            ",empty-removeAll=" + call(() -> view.removeAll(Collections.emptyList())) +
            ",empty-retainAll=" + call(() -> view.retainAll(Collections.emptyList())) +
            ",empty-clear=" + call(view::clear) +
            ",empty-sub-removeIf=" + call(() -> view.subList(0, 0).removeIf(x -> false)) +
            ",empty-sub-sort=" + call(() -> view.subList(0, 0).sort((a, b) -> 0)));
    }

    public static void main(String[] args) {
        World<Body> world = new World<Body>();
        run("bodies", world.getBodies());
        run("collision", world.getCollisionListeners());
        run("bounds", world.getBoundsListeners());
        run("joint", world.getJoints());
        run("contact", world.getContactListeners());
        run("destruction", world.getDestructionListeners());
        run("toi", world.getTimeOfImpactListeners());
        run("step", world.getStepListeners());
        ConstraintGraphNode<Body> node = new ConstraintGraphNode<Body>(new Body());
        run("graph-contact", node.getContactConstraints());
        run("graph-joint", node.getJoints());
    }
}
