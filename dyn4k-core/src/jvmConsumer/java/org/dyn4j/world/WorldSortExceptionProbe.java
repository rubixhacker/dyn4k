package org.dyn4j.world;

import java.util.Iterator;
import java.util.List;
import org.dyn4j.dynamics.Body;
import org.dyn4j.world.listener.StepListener;
import org.dyn4j.world.listener.StepListenerAdapter;

final class WorldSortExceptionProbe {
    private static final class InspectableWorld extends World<Body> {
        List<StepListener<Body>> backing() { return stepListeners; }
    }

    private static void run(boolean replace) {
        InspectableWorld world = new InspectableWorld();
        StepListener<Body> first = new StepListenerAdapter<Body>();
        StepListener<Body> second = new StepListenerAdapter<Body>();
        StepListener<Body> replacement = new StepListenerAdapter<Body>();
        List<StepListener<Body>> list = world.backing();
        list.add(first);
        list.add(second);
        Iterator<StepListener<Body>> iterator = list.iterator();
        List<StepListener<Body>> sublist = list.subList(0, 2);
        try {
            if (replace) {
                int[] count = {0};
                list.replaceAll(item -> {
                    if (count[0]++ == 1) throw new IllegalStateException();
                    return replacement;
                });
            } else list.sort((a, b) -> { throw new IllegalStateException(); });
        } catch (IllegalStateException expected) { }
        System.out.println((replace ? "replace" : "sort") + "," +
            (iterator.next() == replacement ? "replacement" : "first") + "," +
            (sublist.get(0) == replacement ? "replacement" : "first") + "," + list.size());
    }

    public static void main(String[] args) {
        run(false);
        run(true);
    }
}
