import java.util.*;
import org.dyn4j.dynamics.*;
import org.dyn4j.dynamics.contact.*;
import org.dyn4j.geometry.*;
import org.dyn4j.world.*;
import org.dyn4j.world.listener.*;

/** Unchanged Java source compiled separately against baseline and candidate. */
public final class Consumer {
    static final List<String> events = new ArrayList<>();
    static void require(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }
    static void near(double actual, double expected) {
        require(Math.abs(actual - expected) < 1e-12, actual + " != " + expected);
    }
    public static final class CustomBody extends Body {
        public Vector2 protectedVelocity() { return this.linearVelocity; }
        public Transform protectedTransform() { return this.transform; }
        @Override public void integrateVelocity(Vector2 gravity, TimeStep step, Settings settings) {
            events.add("body.velocity");
            super.integrateVelocity(gravity, step, settings);
        }
        @Override public void integratePosition(TimeStep step, Settings settings) {
            events.add("body.position");
            require(this.linearVelocity == getLinearVelocity(), "protected alias");
            super.integratePosition(step, settings);
        }
    }
    public static final class CustomWorld extends World<CustomBody> {
        @Override protected void step() {
            events.add("world.enter");
            require(this.bodies.get(0) == getBody(0), "protected body identity");
            super.step();
            events.add("world.exit");
        }
    }
    public static void observeAndMutate(Body body, Runnable kotlinReentry) {
        Vector2 retained = body.getLinearVelocity();
        retained.x = 4.0;
        kotlinReentry.run();
        require(body.getLinearVelocity() == retained, "Java retained velocity");
        near(retained.x, 6.0);
    }
    public static void main(String[] args) {
        CustomBody body = new CustomBody();
        CustomWorld world = new CustomWorld();
        world.addBody(body);
        Vector2 retained = body.getLinearVelocity();
        Vector2 snapshot = retained.copy();
        retained.x = 1.0;
        require(retained == body.protectedVelocity(), "protected field identity");
        require(body.getTransform() == body.protectedTransform(), "protected transform identity");
        body.setLinearVelocity(2.0, 0.0);
        require(retained == body.getLinearVelocity(), "setter must retain alias");
        boolean[] nested = {false};
        world.addStepListener(new StepListenerAdapter<CustomBody>() {
            @Override public void begin(TimeStep step, PhysicsWorld<CustomBody, ?> seen) {
                events.add(nested[0] ? "listener.nested" : "listener.begin");
                require(seen == world && seen.getBody(0) == body, "listener identities");
                require(seen.getBody(0).getLinearVelocity() == retained, "listener velocity");
                if (!nested[0]) {
                    nested[0] = true;
                    retained.x = 3.0;
                    world.step(1, 0.25);
                    near(body.getTransform().getTranslationX(), 1.0);
                    retained.x = 5.0;
                }
            }
            @Override public void updatePerformed(TimeStep step, PhysicsWorld<CustomBody, ?> seen) { events.add("listener.update"); }
            @Override public void postSolve(TimeStep step, PhysicsWorld<CustomBody, ?> seen) { events.add("listener.post"); }
            @Override public void end(TimeStep step, PhysicsWorld<CustomBody, ?> seen) { events.add("listener.end"); }
        });
        ContactConstraintSolver<CustomBody> solver = new ContactConstraintSolver<CustomBody>() {
            @Override public void initialize(List<ContactConstraint<CustomBody>> constraints, TimeStep step, Settings settings) {
                events.add("solver.initialize:" + constraints.size());
                require(world.getBody(0) == body, "solver sees canonical body");
                require(world.getBody(0).getLinearVelocity() == retained, "solver alias");
                retained.x += 1.0;
            }
            @Override public void solveVelocityContraints(List<ContactConstraint<CustomBody>> constraints, TimeStep step, Settings settings) {
                throw new AssertionError("empty island must skip velocity constraints");
            }
            @Override public boolean solvePositionContraints(List<ContactConstraint<CustomBody>> constraints, TimeStep step, Settings settings) {
                events.add("solver.position:" + constraints.size());
                return true;
            }
        };
        world.setContactConstraintSolver(solver);
        require(world.getContactConstraintSolver() == solver, "solver identity");
        world.step(1, 0.25);
        near(body.getTransform().getTranslationX(), 2.5);
        near(retained.x, 6.0);
        near(snapshot.x, 0.0);
        System.out.println("step.events=" + String.join(",", events));
        System.out.println("step.position=" + body.getTransform().getTranslationX());
        System.out.println("step.velocity=" + retained.x);
        System.out.println("step.aliases=identical;snapshot=independent;solver=identical");
        collectionJourney();
        System.out.println("JAVA_JOURNEY_PASS");
    }
    static String fails(Runnable action) {
        try { action.run(); return "NO_EXCEPTION"; }
        catch (RuntimeException failure) { return failure.getClass().getSimpleName(); }
    }
    static void collectionJourney() {
        World<Body> world = new World<>();
        List<Body> view = world.getBodies();
        require(view == world.getBodies(), "stable view");
        Body first = new Body();
        Body second = new Body();
        world.addBody(first);
        require(view.size() == 1 && view.get(0) == first, "live add");
        List<Body> snapshot = new ArrayList<>(view);
        System.out.println("view.add=" + fails(() -> view.add(second)));
        System.out.println("view.set=" + fails(() -> view.set(0, second)));
        Iterator<Body> viewIterator = view.iterator();
        viewIterator.next();
        System.out.println("view.iterator.remove=" + fails(viewIterator::remove));
        Iterator<Body> iterator = world.getBodyIterator();
        System.out.println("owner.iterator.removeBeforeNext=" + fails(iterator::remove));
        require(iterator.next() == first, "iterator element");
        world.addBody(second);
        require(iterator.hasNext(), "iterator live addition");
        iterator.remove();
        require(view.size() == 1 && view.get(0) == second, "owner iterator removal");
        System.out.println("owner.iterator.doubleRemove=" + fails(iterator::remove));
        require(iterator.next() == second, "iterator shifted index");
        System.out.println("owner.iterator.exhausted=" + fails(iterator::next));
        world.removeBody(second);
        require(view.isEmpty() && snapshot.size() == 1, "live remove and snapshot");
        System.out.println("view.live=true;snapshot.size=" + snapshot.size());
    }
}
