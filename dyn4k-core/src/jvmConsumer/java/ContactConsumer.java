import java.util.Collections;
import java.util.List;
import org.dyn4j.collision.BasicCollisionItem;
import org.dyn4j.collision.BasicCollisionPair;
import org.dyn4j.collision.CollisionItem;
import org.dyn4j.collision.CollisionPair;
import org.dyn4j.collision.continuous.TimeOfImpact;
import org.dyn4j.collision.manifold.Manifold;
import org.dyn4j.collision.manifold.ManifoldPoint;
import org.dyn4j.collision.manifold.ManifoldPointId;
import org.dyn4j.collision.narrowphase.Separation;
import org.dyn4j.dynamics.Body;
import org.dyn4j.dynamics.BodyFixture;
import org.dyn4j.dynamics.Settings;
import org.dyn4j.dynamics.TimeStep;
import org.dyn4j.dynamics.contact.Contact;
import org.dyn4j.dynamics.contact.ContactConstraint;
import org.dyn4j.dynamics.contact.ContactConstraintSolver;
import org.dyn4j.dynamics.contact.ContactUpdateHandler;
import org.dyn4j.dynamics.contact.ForceCollisionTimeOfImpactSolver;
import org.dyn4j.dynamics.contact.SequentialImpulses;
import org.dyn4j.dynamics.contact.SolvedContact;
import org.dyn4j.dynamics.contact.TimeOfImpactSolver;
import org.dyn4j.geometry.Circle;
import org.dyn4j.geometry.MassType;
import org.dyn4j.geometry.Vector2;

public final class ContactConsumer {
    private static void require(boolean condition) {
        if (!condition) throw new AssertionError();
    }

    private static final class CountingSolver extends SequentialImpulses<Body> {
        private int warmStarts;

        @Override
        protected void warmStart(List<ContactConstraint<Body>> constraints, TimeStep step, Settings settings) {
            warmStarts++;
            super.warmStart(constraints, step, settings);
        }
    }

    private static final class DelegatingSolver implements ContactConstraintSolver<Body> {
        private final SequentialImpulses<Body> delegate = new SequentialImpulses<Body>();
        public void initialize(List<ContactConstraint<Body>> contacts, TimeStep step, Settings settings) {
            delegate.initialize(contacts, step, settings);
        }
        public void solveVelocityContraints(List<ContactConstraint<Body>> contacts, TimeStep step, Settings settings) {
            delegate.solveVelocityContraints(contacts, step, settings);
        }
        public boolean solvePositionContraints(List<ContactConstraint<Body>> contacts, TimeStep step, Settings settings) {
            return delegate.solvePositionContraints(contacts, step, settings);
        }
    }

    private static final class CountingToiSolver extends ForceCollisionTimeOfImpactSolver<Body> {
        private int calls;
        @Override
        public void solve(Body first, Body second, TimeOfImpact toi, Settings settings) {
            calls++;
            super.solve(first, second, toi, settings);
        }
    }

    public static void main(String[] args) {
        Body first = new Body();
        Body second = new Body();
        BodyFixture fixture1 = first.addFixture(new Circle(0.5));
        BodyFixture fixture2 = second.addFixture(new Circle(0.5));
        first.setMass(MassType.NORMAL);
        second.setMass(MassType.NORMAL);
        first.setLinearVelocity(1.0, 0.0);
        second.translate(0.9, 0.0);
        CollisionPair<CollisionItem<Body, BodyFixture>> pair =
            new BasicCollisionPair<CollisionItem<Body, BodyFixture>>(
                new BasicCollisionItem<Body, BodyFixture>(first, fixture1),
                new BasicCollisionItem<Body, BodyFixture>(second, fixture2));
        final ContactConstraint<Body> constraint = new ContactConstraint<Body>(pair);
        final List<? extends SolvedContact> liveContacts = constraint.getContacts();
        Manifold manifold = new Manifold();
        manifold.setNormal(new Vector2(-1.0, 0.0));
        ManifoldPoint point = new ManifoldPoint(ManifoldPointId.DISTANCE);
        point.setPoint(new Vector2(0.45, 0.0));
        point.setDepth(0.1);
        manifold.getPoints().add(point);
        final int[] callbacks = new int[3];
        ContactUpdateHandler handler = new ContactUpdateHandler() {
            public double getFriction(BodyFixture a, BodyFixture b) { return 0.0; }
            public double getRestitution(BodyFixture a, BodyFixture b) { return 0.0; }
            public double getRestitutionVelocity(BodyFixture a, BodyFixture b) { return 1.0; }
            public void begin(Contact contact) {
                require(liveContacts.isEmpty());
                constraint.setTangentSpeed(0.25);
                callbacks[0]++;
            }
            public void persist(Contact oldContact, Contact newContact) {
                require(oldContact == liveContacts.get(0));
                callbacks[1]++;
            }
            public void end(Contact contact) { callbacks[2]++; }
        };
        Settings settings = new Settings();
        constraint.update(manifold, settings, handler);
        require(callbacks[0] == 1 && liveContacts.size() == 1);
        require(constraint.getTangentSpeed() == 0.25);
        boolean rejectedMutation = false;
        try {
            liveContacts.clear();
        } catch (UnsupportedOperationException expected) {
            rejectedMutation = true;
        }
        require(rejectedMutation && liveContacts.size() == 1);
        boolean rejectedFriction = false;
        try {
            constraint.setFriction(-1.0);
        } catch (org.dyn4j.exception.ValueOutOfRangeException expected) {
            rejectedFriction = true;
        }
        require(rejectedFriction);
        CountingSolver solver = new CountingSolver();
        List<ContactConstraint<Body>> constraints = Collections.singletonList(constraint);
        TimeStep step = new TimeStep(settings.getStepFrequency());
        solver.initialize(constraints, step, settings);
        solver.solveVelocityContraints(constraints, step, settings);
        require(solver.warmStarts == 1);
        require(new DelegatingSolver().solvePositionContraints(Collections.<ContactConstraint<Body>>emptyList(), step, settings));
        require(first.getLinearVelocity().x < 1.0);
        require(second.getLinearVelocity().x > 0.0);
        require(liveContacts.get(0).isSolved());
        double impulse = liveContacts.get(0).getNormalImpulse();
        constraint.update(manifold, settings, handler);
        require(callbacks[1] == 1);
        require(liveContacts.get(0).getNormalImpulse() == impulse);
        settings.setWarmStartingEnabled(false);
        constraint.update(manifold, settings, handler);
        require(liveContacts.get(0).getNormalImpulse() == 0.0);
        fixture1.setSensor(true);
        constraint.update(manifold, settings, handler);
        require(liveContacts.get(0).isIgnored());
        manifold.clear();
        constraint.update(manifold, settings, handler);
        require(callbacks[2] == 1 && liveContacts.isEmpty());

        Body moving = new Body();
        Body fixed = new Body();
        moving.addFixture(new Circle(1.0));
        fixed.addFixture(new Circle(1.0));
        moving.setMass(MassType.NORMAL);
        fixed.setMass(MassType.INFINITE);
        fixed.translate(2.5, 0.0);
        Separation separation = new Separation();
        separation.setDistance(0.5);
        separation.setNormal(new Vector2(1.0, 0.0));
        TimeOfImpact toi = new TimeOfImpact();
        toi.setSeparation(separation);
        CountingToiSolver customToi = new CountingToiSolver();
        TimeOfImpactSolver<Body> toiSeam = customToi;
        toiSeam.solve(moving, fixed, toi, settings);
        require(customToi.calls == 1);
        require(moving.getTransform().getTranslationX() == 0.2);
        require(fixed.getTransform().getTranslationX() == 2.5);

        Body block1 = new Body();
        Body block2 = new Body();
        BodyFixture blockFixture1 = block1.addFixture(new Circle(0.5));
        BodyFixture blockFixture2 = block2.addFixture(new Circle(0.5));
        block1.setMass(MassType.NORMAL);
        block2.setMass(MassType.NORMAL);
        block1.setLinearVelocity(1.0, 0.0);
        block2.translate(0.9, 0.0);
        CollisionPair<CollisionItem<Body, BodyFixture>> blockPair =
            new BasicCollisionPair<CollisionItem<Body, BodyFixture>>(
                new BasicCollisionItem<Body, BodyFixture>(block1, blockFixture1),
                new BasicCollisionItem<Body, BodyFixture>(block2, blockFixture2));
        ContactConstraint<Body> blockConstraint = new ContactConstraint<Body>(blockPair);
        Manifold blockManifold = new Manifold();
        blockManifold.setNormal(new Vector2(-1.0, 0.0));
        for (double y : new double[] {-0.25, 0.25}) {
            ManifoldPoint blockPoint = new ManifoldPoint(ManifoldPointId.DISTANCE);
            blockPoint.setPoint(new Vector2(0.45, y));
            blockPoint.setDepth(0.1);
            blockManifold.getPoints().add(blockPoint);
        }
        blockConstraint.update(blockManifold, settings, handler);
        List<ContactConstraint<Body>> blockConstraints = Collections.singletonList(blockConstraint);
        SequentialImpulses<Body> blockSolver = new SequentialImpulses<Body>();
        blockSolver.initialize(blockConstraints, step, settings);
        blockSolver.solveVelocityContraints(blockConstraints, step, settings);
        blockSolver.solvePositionContraints(blockConstraints, step, settings);
        require(blockConstraint.getContacts().size() == 2);
        require(blockConstraint.getContacts().get(0).isSolved());
        require(blockConstraint.getContacts().get(1).isSolved());
        System.out.println("contact-block: " + Double.toHexString(block1.getLinearVelocity().x) + " " +
            Double.toHexString(block2.getLinearVelocity().x) + " " +
            Double.toHexString(blockConstraint.getContacts().get(0).getNormalImpulse()) + " " +
            Double.toHexString(blockConstraint.getContacts().get(1).getNormalImpulse()) + " " +
            Double.toHexString(block1.getTransform().getTranslationX()) + " " +
            Double.toHexString(block2.getTransform().getTranslationX()));
        System.out.println("contact-consumer: passed");
    }
}
