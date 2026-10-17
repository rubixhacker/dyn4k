package org.dyn4j.world;

import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;
import java.util.RandomAccess;
import org.dyn4j.collision.BasicCollisionItem;
import org.dyn4j.collision.BasicCollisionPair;
import org.dyn4j.dynamics.Body;
import org.dyn4j.dynamics.BodyFixture;
import org.dyn4j.dynamics.contact.ContactConstraint;
import org.dyn4j.dynamics.joint.Joint;
import org.dyn4j.dynamics.joint.PinJoint;
import org.dyn4j.geometry.Circle;
import org.dyn4j.geometry.Vector2;
import org.dyn4j.world.listener.StepListener;
import org.dyn4j.world.listener.StepListenerAdapter;

public final class WorldProtectedListConsumer {
    private static final class InspectableWorld extends World<Body> {
        List<StepListener<Body>> stepBacking() { return stepListeners; }
        List<Joint<Body>> jointBacking() { return joints; }
    }

    private static void expectConcurrentModification(Runnable action, String label) {
        try { action.run(); }
        catch (ConcurrentModificationException expected) { return; }
        throw new AssertionError(label + " accepted a structural change");
    }

    private static void expectIllegalArgument(Runnable action, String label) {
        try { action.run(); }
        catch (IllegalArgumentException expected) { return; }
        throw new AssertionError(label + " accepted a reversed range");
    }

    private static void expectIndexOutOfBounds(Runnable action, String label) {
        try { action.run(); }
        catch (IndexOutOfBoundsException expected) { return; }
        throw new AssertionError(label + " accepted a negative start");
    }

    private static <T> void protectedSubList(List<T> backing, T replacement, Runnable add, String label) {
        List<T> saved = backing.subList(0, 1);
        backing.set(0, replacement);
        if (saved.get(0) != replacement) throw new AssertionError(label + " missed nonstructural set");
        add.run();
        expectConcurrentModification(() -> saved.get(0), label + " protected sublist get");
        expectConcurrentModification(saved::size, label + " protected sublist size");
    }

    private static void publicRange(List<?> view, String label) {
        expectIllegalArgument(() -> view.subList(1, 0), label);
        expectIndexOutOfBounds(() -> view.subList(-1, 0), label);
    }

    private static void randomAccess(List<?> backing, List<?> view, String label) {
        if (!(backing instanceof RandomAccess) || !(view instanceof RandomAccess) ||
                !(backing.subList(0, 1) instanceof RandomAccess) ||
                !(view.subList(0, 1) instanceof RandomAccess)) {
            throw new AssertionError(label + " missing RandomAccess marker");
        }
    }

    private static <T> void invalidatesAfterSortOrReplace(
            List<T> backing, List<T> view, boolean replace, String label) {
        Iterator<T> iterator = backing.iterator();
        List<T> sublist = backing.subList(0, 1);
        List<T> publicSublist = view.subList(0, 1);
        T original = backing.get(0);
        if (replace) backing.replaceAll(value -> value);
        else backing.sort((left, right) -> 0);
        if (backing.get(0) != original || view.get(0) != original) {
            throw new AssertionError(label + " changed an element");
        }
        expectConcurrentModification(iterator::next, label + " iterator");
        expectConcurrentModification(() -> sublist.get(0), label + " protected sublist");
        expectConcurrentModification(() -> publicSublist.get(0), label + " public sublist");
    }

    public static void main(String[] args) {
        if (args.length != 1) throw new IllegalArgumentException("protected-sublist, reversed-range, random-access, sort, replace-all");
        String mode = args[0];
        InspectableWorld world = new InspectableWorld();
        StepListener<Body> step = new StepListenerAdapter<Body>();
        world.addStepListener(step);
        Body body = new Body();
        world.addBody(body);
        Joint<Body> joint = new PinJoint<Body>(body, new Vector2());
        world.addJoint(joint);

        Body other = new Body();
        BodyFixture fixture = body.addFixture(new Circle(0.5));
        BodyFixture otherFixture = other.addFixture(new Circle(0.5));
        ContactConstraint<Body> contact = new ContactConstraint<Body>(new BasicCollisionPair<>(
            new BasicCollisionItem<>(body, fixture), new BasicCollisionItem<>(other, otherFixture)));
        ConstraintGraphNode<Body> node = new ConstraintGraphNode<Body>(body);
        node.contactConstraints.add(contact);
        node.joints.add(joint);

        if ("protected-sublist".equals(mode)) {
            protectedSubList(world.stepBacking(), step, () -> world.addStepListener(new StepListenerAdapter<Body>()), "World step");
            protectedSubList(world.jointBacking(), joint, () -> world.addJoint(new PinJoint<Body>(body, new Vector2())), "World joint");
            protectedSubList(node.contactConstraints, contact, () -> node.contactConstraints.add(contact), "graph contact");
            protectedSubList(node.joints, joint, () -> node.joints.add(joint), "graph joint");
        } else if ("reversed-range".equals(mode)) {
            publicRange(world.getStepListeners(), "World step");
            publicRange(world.getJoints(), "World joint");
            publicRange(node.getContactConstraints(), "graph contact");
            publicRange(node.getJoints(), "graph joint");
        } else if ("random-access".equals(mode)) {
            randomAccess(world.stepBacking(), world.getStepListeners(), "World step");
            randomAccess(world.jointBacking(), world.getJoints(), "World joint");
            randomAccess(node.contactConstraints, node.getContactConstraints(), "graph contact");
            randomAccess(node.joints, node.getJoints(), "graph joint");
        } else if ("sort".equals(mode) || "replace-all".equals(mode)) {
            boolean replace = "replace-all".equals(mode);
            invalidatesAfterSortOrReplace(world.stepBacking(), world.getStepListeners(), replace, "World step");
            invalidatesAfterSortOrReplace(world.jointBacking(), world.getJoints(), replace, "World joint");
            invalidatesAfterSortOrReplace(node.contactConstraints, node.getContactConstraints(), replace, "graph contact");
            invalidatesAfterSortOrReplace(node.joints, node.getJoints(), replace, "graph joint");
        } else throw new IllegalArgumentException(mode);
        System.out.println("WORLD_PROTECTED_LIST_OK," + mode);
    }
}
