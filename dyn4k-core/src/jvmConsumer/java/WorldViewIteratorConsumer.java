import java.lang.reflect.Field;
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

public final class WorldViewIteratorConsumer {
    private static final class InspectableWorld extends World<Body> {
        void replaceStep(StepListener<Body> listener) {
            stepListeners.set(0, listener);
        }

        void replaceJoint(Joint<Body> joint) {
            joints.set(0, joint);
        }
    }

    private static void failsFast(Iterator<?> iterator) {
        try {
            iterator.next();
        } catch (ConcurrentModificationException expected) {
            return;
        }
        throw new AssertionError("saved iterator did not reject a structural change");
    }

    private static void rejects(Runnable action) {
        try {
            action.run();
        } catch (UnsupportedOperationException expected) {
            return;
        }
        throw new AssertionError("view allowed a mutation");
    }

    private static <T> void unmodifiable(List<T> view) {
        T first = view.get(0);
        rejects(() -> view.add(first));
        rejects(() -> view.set(0, first));
        rejects(() -> view.remove(0));
        rejects(view::clear);
    }

    @SuppressWarnings("unchecked")
    private static <T> void setProtected(ConstraintGraphNode<Body> node, String name, T value)
            throws ReflectiveOperationException {
        Field field = ConstraintGraphNode.class.getDeclaredField(name);
        field.setAccessible(true);
        ((List<T>) field.get(node)).set(0, value);
    }

    public static void main(String[] args) throws Exception {
        InspectableWorld world = new InspectableWorld();
        StepListener<Body> first = new StepListenerAdapter<Body>();
        StepListener<Body> replacement = new StepListenerAdapter<Body>();
        world.addStepListener(first);
        List<StepListener<Body>> listeners = world.getStepListeners();
        if (listeners != world.getStepListeners()) throw new AssertionError("listener view identity");
        unmodifiable(listeners);
        Iterator<StepListener<Body>> listenerAfterSet = listeners.iterator();
        world.replaceStep(replacement);
        if (listenerAfterSet.next() != replacement) throw new AssertionError("listener set");
        Iterator<StepListener<Body>> listenerBeforeAdd = listeners.iterator();
        world.addStepListener(new StepListenerAdapter<Body>());
        if (listeners.size() != 2) throw new AssertionError("listener view is not live");
        failsFast(listenerBeforeAdd);

        Body body1 = new Body();
        Body body2 = new Body();
        InspectableWorld jointWorld = new InspectableWorld();
        jointWorld.addBody(body1);
        PinJoint<Body> firstJoint = new PinJoint<Body>(body1, new Vector2());
        jointWorld.addJoint(firstJoint);
        List<Joint<Body>> worldJoints = jointWorld.getJoints();
        if (worldJoints != jointWorld.getJoints()) throw new AssertionError("joint view identity");
        unmodifiable(worldJoints);
        Iterator<Joint<Body>> jointAfterSet = worldJoints.iterator();
        jointWorld.replaceJoint(firstJoint);
        if (jointAfterSet.next() != firstJoint) throw new AssertionError("joint set");
        Iterator<Joint<Body>> jointBeforeAdd = worldJoints.iterator();
        jointWorld.addJoint(new PinJoint<Body>(body1, new Vector2()));
        if (worldJoints.size() != 2) throw new AssertionError("joint view is not live");
        failsFast(jointBeforeAdd);

        BodyFixture fixture1 = body1.addFixture(new Circle(0.5));
        BodyFixture fixture2 = body2.addFixture(new Circle(0.5));
        ContactConstraint<Body> contact = new ContactConstraint<Body>(new BasicCollisionPair<>(
            new BasicCollisionItem<>(body1, fixture1), new BasicCollisionItem<>(body2, fixture2)));
        ConstraintGraph<Body> graph = new ConstraintGraph<Body>();
        graph.addBody(body1);
        graph.addBody(body2);
        graph.addContactConstraint(contact);
        graph.addJoint(firstJoint);
        ConstraintGraphNode<Body> node = graph.getNode(body1);
        List<ContactConstraint<Body>> contacts = node.getContactConstraints();
        List<Joint<Body>> graphJoints = node.getJoints();
        if (contacts != node.getContactConstraints() || graphJoints != node.getJoints()) {
            throw new AssertionError("graph view identity");
        }
        unmodifiable(contacts);
        unmodifiable(graphJoints);
        Iterator<ContactConstraint<Body>> contactAfterSet = contacts.iterator();
        Iterator<Joint<Body>> graphJointAfterSet = graphJoints.iterator();
        setProtected(node, "contactConstraints", contact);
        setProtected(node, "joints", firstJoint);
        if (contactAfterSet.next() != contact || graphJointAfterSet.next() != firstJoint) {
            throw new AssertionError("graph nonstructural set");
        }
        Iterator<ContactConstraint<Body>> contactBeforeAdd = contacts.iterator();
        Iterator<Joint<Body>> graphJointBeforeAdd = graphJoints.iterator();
        graph.addContactConstraint(contact);
        graph.addJoint(new PinJoint<Body>(body1, new Vector2()));
        if (contacts.size() != 2 || graphJoints.size() != 2) {
            throw new AssertionError("graph views are not live");
        }
        failsFast(contactBeforeAdd);
        failsFast(graphJointBeforeAdd);
        System.out.println("WORLD_VIEW_ITERATORS_OK,4");
    }
}
