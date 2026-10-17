package org.dyn4j.world;

import java.util.Iterator;
import java.util.List;
import org.dyn4j.dynamics.Body;

final class WorldAllListsProbe {
    private static final class ProbeWorld extends World<Body> {
        List<?> backing(int family) {
            switch (family) {
                case 0: return joints;
                case 1: return contactListeners;
                case 2: return destructionListeners;
                case 3: return timeOfImpactListeners;
                case 4: return stepListeners;
                case 5: return bodies;
                case 6: return collisionListeners;
                case 7: return boundsListeners;
                default: throw new AssertionError(family);
            }
        }
        List<?> view(int family) {
            switch (family) {
                case 0: return getJoints();
                case 1: return getContactListeners();
                case 2: return getDestructionListeners();
                case 3: return getTimeOfImpactListeners();
                case 4: return getStepListeners();
                case 5: return getBodies();
                case 6: return getCollisionListeners();
                case 7: return getBoundsListeners();
                default: throw new AssertionError(family);
            }
        }
    }

    private static final class Holder {
        final List<Object> backing;
        final List<?> view;
        final java.util.function.Supplier<List<?>> getView;
        @SuppressWarnings("unchecked")
        Holder(List<?> backing, List<?> view, java.util.function.Supplier<List<?>> getView) {
            this.backing = (List<Object>) backing;
            this.view = view;
            this.getView = getView;
            this.backing.add(null);
        }
    }

    private static Holder sample(int family) {
        if (family < 8) {
            ProbeWorld world = new ProbeWorld();
            return new Holder(world.backing(family), world.view(family), () -> world.view(family));
        }
        ConstraintGraphNode<Body> node = new ConstraintGraphNode<Body>(new Body());
        return family == 8
            ? new Holder(node.contactConstraints, node.getContactConstraints(), node::getContactConstraints)
            : new Holder(node.joints, node.getJoints(), node::getJoints);
    }

    private static String result(Runnable action) {
        try { action.run(); return "VALUE"; }
        catch (RuntimeException error) { return error.getClass().getSimpleName(); }
    }

    private static void run(int family, String mutation) {
        Holder holder = sample(family);
        List<Object> list = holder.backing;
        Iterator<Object> iterator = list.iterator();
        List<Object> sub = list.subList(0, 1);
        List<?> publicSub = holder.view.subList(0, 1);
        String operation = result(() -> {
            switch (mutation) {
                case "sort": list.sort((a, b) -> 0); break;
                case "replaceAll": list.replaceAll(x -> x); break;
                case "removeIf-false": list.removeIf(x -> false); break;
                case "empty-sub-clear": list.subList(0, 0).clear(); break;
                case "set": list.set(0, null); break;
                default: throw new AssertionError(mutation);
            }
        });
        System.out.println(family + "," + mutation + "," + operation + "," +
            result(iterator::next) + "," + result(sub::size) + "," +
            result(publicSub::size) + "," + holder.view.size() + "," +
            (holder.view == holder.getView.get()));
    }

    public static void main(String[] args) {
        for (int family = 0; family < 10; family++) {
            run(family, "sort");
            run(family, "replaceAll");
            run(family, "removeIf-false");
            run(family, "empty-sub-clear");
            run(family, "set");
        }
    }
}
