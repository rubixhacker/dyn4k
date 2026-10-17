package org.dyn4j.world;

import java.util.List;
import org.dyn4j.dynamics.Body;
import org.dyn4j.world.listener.StepListener;
import org.dyn4j.world.listener.StepListenerAdapter;

final class WorldReentryProbe {
    private static final class ProbeWorld extends World<Body> {
        List<StepListener<Body>> backing() { return stepListeners; }
    }

    private static String attempt(Runnable task) {
        try { task.run(); return "VALUE"; }
        catch (RuntimeException error) { return error.getClass().getSimpleName(); }
    }

    private static void run(String name, java.util.function.Consumer<List<StepListener<Body>>> task) {
        ProbeWorld world = new ProbeWorld();
        List<StepListener<Body>> list = world.backing();
        list.add(new StepListenerAdapter<Body>());
        list.add(new StepListenerAdapter<Body>());
        String result = attempt(() -> task.accept(list));
        System.out.println(name + "," + result + "," + list.size() + "," + world.getStepListeners().size());
    }

    public static void main(String[] args) {
        run("replaceAll-clear", list -> list.replaceAll(item -> { list.clear(); return item; }));
        run("replaceAll-removeFirst", list -> list.replaceAll(item -> { list.remove(0); return item; }));
        run("replaceAll-add", list -> list.replaceAll(item -> { list.add(item); return item; }));
        run("removeIf-clear", list -> list.removeIf(item -> { list.clear(); return false; }));
        run("removeIf-removeFirst", list -> list.removeIf(item -> { list.remove(0); return false; }));
        run("removeIf-add", list -> list.removeIf(item -> { list.add(item); return false; }));
        run("sort-clear", list -> list.sort((left, right) -> { list.clear(); return 0; }));
    }
}
