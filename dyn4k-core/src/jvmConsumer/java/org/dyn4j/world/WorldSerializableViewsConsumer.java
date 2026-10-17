package org.dyn4j.world;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.ObjectStreamClass;
import java.security.MessageDigest;
import java.util.List;
import java.util.RandomAccess;
import java.util.function.Supplier;
import org.dyn4j.dynamics.Body;

public final class WorldSerializableViewsConsumer {
    private static final class ProbeWorld extends World<Body> {
        List<?> backing(int family) {
            switch (family) {
                case 0: return bodies;
                case 1: return collisionListeners;
                case 2: return boundsListeners;
                case 3: return joints;
                case 4: return contactListeners;
                case 5: return destructionListeners;
                case 6: return timeOfImpactListeners;
                case 7: return stepListeners;
                default: throw new AssertionError(family);
            }
        }

        List<?> view(int family) {
            switch (family) {
                case 0: return getBodies();
                case 1: return getCollisionListeners();
                case 2: return getBoundsListeners();
                case 3: return getJoints();
                case 4: return getContactListeners();
                case 5: return getDestructionListeners();
                case 6: return getTimeOfImpactListeners();
                case 7: return getStepListeners();
                default: throw new AssertionError(family);
            }
        }
    }

    private static String hex(byte[] bytes) {
        StringBuilder result = new StringBuilder(bytes.length * 2);
        for (byte value : bytes) result.append(String.format("%02x", value & 0xff));
        return result.toString();
    }

    private static String serialize(List<?> view) {
        try {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            ObjectOutputStream output = new ObjectOutputStream(bytes);
            output.writeObject(view);
            output.close();
            byte[] payload = bytes.toByteArray();
            ObjectInputStream input = new ObjectInputStream(new ByteArrayInputStream(payload));
            List<?> copy = (List<?>) input.readObject();
            input.close();
            String mutation;
            try { copy.clear(); mutation = "VALUE"; }
            catch (UnsupportedOperationException expected) { mutation = "UnsupportedOperationException"; }
            return "VALUE:" + payload.length + ":" +
                hex(MessageDigest.getInstance("SHA-256").digest(payload)) +
                ":" + copy.size() + ":" + (copy instanceof RandomAccess) + ":" + mutation;
        } catch (Exception error) {
            return error.getClass().getSimpleName() + ":" + error.getMessage();
        }
    }

    private static String repeatedReference(List<?> view) {
        try {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            ObjectOutputStream output = new ObjectOutputStream(bytes);
            output.writeObject(view);
            output.writeObject(view);
            output.close();
            ObjectInputStream input = new ObjectInputStream(new ByteArrayInputStream(bytes.toByteArray()));
            Object first = input.readObject();
            Object second = input.readObject();
            input.close();
            return "VALUE:" + (first == second);
        } catch (Exception error) {
            return error.getClass().getSimpleName() + ":" + error.getMessage();
        }
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    private static void inspect(String label, List<?> backing, List<?> view, Supplier<List<?>> getter) {
        String kind = view.getClass().getName();
        long serialVersion = ObjectStreamClass.lookup(view.getClass()).getSerialVersionUID();
        String empty = serialize(view);
        String emptySublist = serialize(view.subList(0, 0));
        ((List) backing).add("marker-" + label);
        System.out.println(label + ",class=" + kind + ",serialVersion=" + serialVersion +
            ",randomAccess=" + (view instanceof RandomAccess) +
            ",liveIdentity=" + (view == getter.get()) + ",liveSize=" + view.size());
        System.out.println(label + ",empty=" + empty);
        System.out.println(label + ",emptySublist=" + emptySublist);
        System.out.println(label + ",nonempty=" + serialize(view));
        System.out.println(label + ",nonemptySublist=" + serialize(view.subList(0, 1)));
        System.out.println(label + ",repeatedReference=" + repeatedReference(view));
    }

    public static void main(String[] args) {
        ProbeWorld world = new ProbeWorld();
        String[] names = {"bodies", "collision", "bounds", "joints", "contact", "destruction", "toi", "step"};
        for (int family = 0; family < names.length; family++) {
            final int index = family;
            inspect(names[index], world.backing(index), world.view(index), () -> world.view(index));
        }
        ConstraintGraphNode<Body> node = new ConstraintGraphNode<Body>(new Body());
        inspect("graph-contact", node.contactConstraints, node.getContactConstraints(), node::getContactConstraints);
        inspect("graph-joints", node.joints, node.getJoints(), node::getJoints);
    }
}
