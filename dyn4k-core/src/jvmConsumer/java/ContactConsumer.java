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
import org.dyn4j.dynamics.contact.ContactUpdateHandler;
import org.dyn4j.dynamics.contact.ForceCollisionTimeOfImpactSolver;
import org.dyn4j.dynamics.contact.SequentialImpulses;
import org.dyn4j.dynamics.contact.SolvedContact;
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
        CountingSolver solver = new CountingSolver();
        List<ContactConstraint<Body>> constraints = Collections.singletonList(constraint);
        TimeStep step = new TimeStep(settings.getStepFrequency());
        solver.initialize(constraints, step, settings);
        solver.solveVelocityContraints(constraints, step, settings);
        require(solver.warmStarts == 1);
        require(first.getLinearVelocity().x < 1.0);
        require(second.getLinearVelocity().x > 0.0);
        require(liveContacts.get(0).isSolved());
        double impulse = liveContacts.get(0).getNormalImpulse();
        constraint.update(manifold, settings, handler);
        require(callbacks[1] == 1);
        require(liveContacts.get(0).getNormalImpulse() == impulse);
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
        new ForceCollisionTimeOfImpactSolver<Body>().solve(moving, fixed, toi, settings);
        require(moving.getTransform().getTranslationX() == 0.2);
        require(fixed.getTransform().getTranslationX() == 2.5);
        System.out.println("contact-consumer: 13 checks passed");
    }
}
