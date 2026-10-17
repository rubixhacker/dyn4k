package org.dyn4j.world;

import java.util.Arrays;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.function.Consumer;
import org.dyn4j.dynamics.Body;
import org.dyn4j.world.listener.StepListener;
import org.dyn4j.world.listener.StepListenerAdapter;

public final class WorldArrayListMutationAuditConsumer {
    private static final class InspectableWorld extends World<Body> {
        List<StepListener<Body>> backing() { return stepListeners; }
    }

    private static String result(Runnable action) {
        try { action.run(); return "VALUE"; }
        catch (RuntimeException error) { return error.getClass().getSimpleName(); }
    }

    private static <T> void check(String name, boolean empty, Consumer<List<T>> mutation, T value) {
        InspectableWorld world = new InspectableWorld();
        @SuppressWarnings("unchecked")
        List<T> list = (List<T>) world.backing();
        if (!empty) list.add(value);
        Iterator<T> iterator = list.iterator();
        List<T> sublist = list.subList(0, list.size());
        String mutationResult = result(() -> mutation.accept(list));
        String iteratorResult = result(iterator::next);
        String sublistResult = result(sublist::size);
        System.out.println(name + "," + mutationResult + "," + iteratorResult + "," + sublistResult + "," + list.size());
    }

    private static void checkRemoveIfThrowsAfterMatch() {
        InspectableWorld world = new InspectableWorld();
        List<StepListener<Body>> list = world.backing();
        list.add(new StepListenerAdapter<Body>());
        list.add(new StepListenerAdapter<Body>());
        Iterator<StepListener<Body>> iterator = list.iterator();
        List<StepListener<Body>> sublist = list.subList(0, 2);
        int[] visited = {0};
        String mutationResult = result(() -> list.removeIf(item -> {
            if (visited[0]++ == 1) throw new IllegalStateException();
            return true;
        }));
        System.out.println("removeIf-throw-after-match," + mutationResult + "," +
            result(iterator::next) + "," + result(sublist::size) + "," + list.size());
    }

    public static void main(String[] args) {
        StepListener<Body> value = new StepListenerAdapter<Body>();
        check("set-same", false, list -> list.set(0, value), value);
        check("addAll-empty", false, list -> list.addAll(Collections.emptyList()), value);
        check("addAll-index-empty", false, list -> list.addAll(0, Collections.emptyList()), value);
        check("remove-absent", false, list -> list.remove(new StepListenerAdapter<Body>()), value);
        check("removeIf-false", false, list -> list.removeIf(item -> false), value);
        check("removeIf-true", false, list -> list.removeIf(item -> true), value);
        check("removeAll-empty", false, list -> list.removeAll(Collections.emptyList()), value);
        check("retainAll-same", false, list -> list.retainAll(Arrays.asList(value)), value);
        check("clear-empty", true, List::clear, value);
        check("sort-empty", true, list -> list.sort((a, b) -> 0), value);
        check("replaceAll-empty", true, list -> list.replaceAll(item -> item), value);
        check("collections-sort", false, list -> Collections.sort(list, (a, b) -> 0), value);
        check("collections-replaceAll", false, list -> Collections.replaceAll(list, value, value), value);
        check("sublist-sort", false, list -> list.subList(0, 1).sort((a, b) -> 0), value);
        check("sublist-replaceAll", false, list -> list.subList(0, 1).replaceAll(item -> item), value);
        checkRemoveIfThrowsAfterMatch();
    }
}
