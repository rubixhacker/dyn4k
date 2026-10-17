import java.lang.reflect.Field;
import java.util.Collections;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;
import org.dyn4j.collision.BasicCollisionItem;
import org.dyn4j.collision.BasicCollisionPair;
import org.dyn4j.dynamics.Body;
import org.dyn4j.dynamics.BodyFixture;
import org.dyn4j.dynamics.contact.ContactConstraint;
import org.dyn4j.dynamics.joint.Joint;
import org.dyn4j.dynamics.joint.PinJoint;
import org.dyn4j.geometry.Circle;
import org.dyn4j.geometry.Vector2;
import org.dyn4j.world.ConstraintGraph;
import org.dyn4j.world.ConstraintGraphNode;
import org.dyn4j.world.World;
import org.dyn4j.world.listener.StepListener;
import org.dyn4j.world.listener.StepListenerAdapter;

public final class WorldListSemanticsConsumer {
    private static final class InspectableWorld extends World<Body> {
        Iterator<StepListener<Body>> stepBackingIterator() { return stepListeners.iterator(); }
        Iterator<Joint<Body>> jointBackingIterator() { return joints.iterator(); }
        void replaceStep(StepListener<Body> value) { stepListeners.set(0, value); }
        void replaceJoint(Joint<Body> value) { joints.set(0, value); }
    }

    private static void failsFast(Runnable action, String label) {
        try { action.run(); }
        catch (ConcurrentModificationException expected) { return; }
        throw new AssertionError(label + " accepted structural change");
    }

    private static void rejects(Runnable action, String label) {
        try { action.run(); }
        catch (UnsupportedOperationException expected) { return; }
        throw new AssertionError(label + " accepted mutation");
    }

    @SuppressWarnings("unchecked")
    private static <T> List<T> backing(ConstraintGraphNode<Body> node, String fieldName)
            throws ReflectiveOperationException {
        Field field = ConstraintGraphNode.class.getDeclaredField(fieldName);
        field.setAccessible(true);
        return (List<T>) field.get(node);
    }

    private static void stepCase(String mode) {
        InspectableWorld world = new InspectableWorld();
        StepListener<Body> first = new StepListenerAdapter<Body>();
        StepListener<Body> replacement = new StepListenerAdapter<Body>();
        world.addStepListener(first);
        List<StepListener<Body>> view = world.getStepListeners();
        if (view != world.getStepListeners()) throw new AssertionError("step view identity");
        Iterator<StepListener<Body>> beforeSet = world.stepBackingIterator();
        List<StepListener<Body>> subList = view.subList(0, 1);
        world.replaceStep(replacement);
        if (beforeSet.next() != replacement || subList.get(0) != replacement)
            throw new AssertionError("step nonstructural set");
        Iterator<StepListener<Body>> beforeAdd = world.stepBackingIterator();
        world.addStepListener(new StepListenerAdapter<Body>());
        if (view.size() != 2) throw new AssertionError("step view is not live");
        if ("backing".equals(mode)) failsFast(beforeAdd::next, "step backing iterator");
        if ("sublist".equals(mode)) failsFast(() -> subList.get(0), "step subList");
    }

    private static void jointCase(String mode) {
        InspectableWorld world = new InspectableWorld();
        Body body = new Body();
        world.addBody(body);
        Joint<Body> first = new PinJoint<Body>(body, new Vector2());
        world.addJoint(first);
        List<Joint<Body>> view = world.getJoints();
        if (view != world.getJoints()) throw new AssertionError("joint view identity");
        Iterator<Joint<Body>> beforeSet = world.jointBackingIterator();
        List<Joint<Body>> subList = view.subList(0, 1);
        world.replaceJoint(first);
        if (beforeSet.next() != first || subList.get(0) != first)
            throw new AssertionError("joint nonstructural set");
        Iterator<Joint<Body>> beforeAdd = world.jointBackingIterator();
        world.addJoint(new PinJoint<Body>(body, new Vector2()));
        if (view.size() != 2) throw new AssertionError("joint view is not live");
        if ("backing".equals(mode)) failsFast(beforeAdd::next, "joint backing iterator");
        if ("sublist".equals(mode)) failsFast(() -> subList.get(0), "joint subList");
    }

    private static void graphCase(String mode) throws Exception {
        Body a = new Body();
        Body b = new Body();
        BodyFixture af = a.addFixture(new Circle(0.5));
        BodyFixture bf = b.addFixture(new Circle(0.5));
        ContactConstraint<Body> contact = new ContactConstraint<Body>(new BasicCollisionPair<>(
            new BasicCollisionItem<>(a, af), new BasicCollisionItem<>(b, bf)));
        Joint<Body> joint = new PinJoint<Body>(a, new Vector2());
        ConstraintGraph<Body> graph = new ConstraintGraph<Body>();
        graph.addBody(a);
        graph.addBody(b);
        graph.addContactConstraint(contact);
        graph.addJoint(joint);
        ConstraintGraphNode<Body> node = graph.getNode(a);
        List<ContactConstraint<Body>> contacts = node.getContactConstraints();
        List<Joint<Body>> joints = node.getJoints();
        if (contacts != node.getContactConstraints() || joints != node.getJoints())
            throw new AssertionError("graph view identity");
        List<ContactConstraint<Body>> contactBacking = backing(node, "contactConstraints");
        List<Joint<Body>> jointBacking = backing(node, "joints");
        Iterator<ContactConstraint<Body>> contactBeforeSet = contactBacking.iterator();
        Iterator<Joint<Body>> jointBeforeSet = jointBacking.iterator();
        List<ContactConstraint<Body>> contactSubList = contacts.subList(0, 1);
        List<Joint<Body>> jointSubList = joints.subList(0, 1);
        contactBacking.set(0, contact);
        jointBacking.set(0, joint);
        if (contactBeforeSet.next() != contact || jointBeforeSet.next() != joint ||
                contactSubList.get(0) != contact || jointSubList.get(0) != joint)
            throw new AssertionError("graph nonstructural set");
        Iterator<ContactConstraint<Body>> contactBeforeAdd = contactBacking.iterator();
        Iterator<Joint<Body>> jointBeforeAdd = jointBacking.iterator();
        graph.addContactConstraint(contact);
        graph.addJoint(new PinJoint<Body>(a, new Vector2()));
        if (contacts.size() != 2 || joints.size() != 2) throw new AssertionError("graph views are not live");
        if ("backing".equals(mode)) {
            failsFast(contactBeforeAdd::next, "graph contact backing iterator");
            failsFast(jointBeforeAdd::next, "graph joint backing iterator");
        }
        if ("sublist".equals(mode)) {
            failsFast(() -> contactSubList.get(0), "graph contact subList");
            failsFast(() -> jointSubList.get(0), "graph joint subList");
        }
    }

    private static <T> void checkEmpty(List<T> view, String mode, String label) {
        if (!"empty-sort".equals(mode))
            rejects(() -> view.removeIf(value -> false), label + " empty removeIf(false)");
        if (!"empty-removeIf".equals(mode))
            rejects(() -> view.sort((a, b) -> 0), label + " empty sort");
        rejects(() -> view.removeAll(Collections.emptyList()), label + " empty removeAll");
    }

    private static void emptyCase(String mode) {
        InspectableWorld world = new InspectableWorld();
        checkEmpty(world.getStepListeners(), mode, "step listeners");
        checkEmpty(world.getJoints(), mode, "world joints");
        Body body = new Body();
        ConstraintGraph<Body> graph = new ConstraintGraph<Body>();
        graph.addBody(body);
        ConstraintGraphNode<Body> node = graph.getNode(body);
        checkEmpty(node.getContactConstraints(), mode, "graph contacts");
        checkEmpty(node.getJoints(), mode, "graph joints");
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) throw new IllegalArgumentException("backing, sublist, or empty");
        if (args[0].startsWith("empty")) emptyCase(args[0]);
        else if ("backing".equals(args[0]) || "sublist".equals(args[0])) {
            stepCase(args[0]);
            jointCase(args[0]);
            graphCase(args[0]);
        } else throw new IllegalArgumentException(args[0]);
        System.out.println("WORLD_LIST_SEMANTICS_OK," + args[0]);
    }
}
