package org.dyn4j.dynamics.contact;

import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.util.Arrays;
import java.util.List;

import org.dyn4j.AVLTree;
import org.dyn4j.BinarySearchTree;
import org.dyn4j.Unsafe;
import org.dyn4j.collision.BasicCollisionItem;
import org.dyn4j.collision.BasicCollisionPair;
import org.dyn4j.collision.CollisionItem;
import org.dyn4j.collision.CollisionPair;
import org.dyn4j.collision.continuous.TimeOfImpact;
import org.dyn4j.collision.manifold.Manifold;
import org.dyn4j.collision.manifold.ManifoldPoint;
import org.dyn4j.collision.manifold.ManifoldPointId;
import org.dyn4j.collision.narrowphase.Containment;
import org.dyn4j.collision.narrowphase.Penetration;
import org.dyn4j.collision.narrowphase.Raycast;
import org.dyn4j.collision.narrowphase.Separation;
import org.dyn4j.dynamics.Body;
import org.dyn4j.dynamics.BodyFixture;
import org.dyn4j.dynamics.ContinuousDetectionMode;
import org.dyn4j.dynamics.Settings;
import org.dyn4j.dynamics.joint.AngleJoint;
import org.dyn4j.dynamics.joint.MotorJoint;
import org.dyn4j.dynamics.joint.WeldJoint;
import org.dyn4j.exception.CopyException;
import org.dyn4j.geometry.Circle;
import org.dyn4j.geometry.Convex;
import org.dyn4j.geometry.Geometry;
import org.dyn4j.geometry.Interval;
import org.dyn4j.geometry.MassType;
import org.dyn4j.geometry.RobustGeometry;
import org.dyn4j.geometry.Rotation;
import org.dyn4j.geometry.Shape;
import org.dyn4j.geometry.Vector2;
import org.dyn4j.geometry.decompose.Bayazit;
import org.dyn4j.geometry.decompose.Decomposer;
import org.dyn4j.geometry.hull.GrahamScan;
import org.dyn4j.geometry.hull.HullGenerator;
import org.dyn4j.world.result.ConvexCastResult;
import org.dyn4j.world.result.ConvexDetectResult;
import org.dyn4j.world.result.DetectResult;
import org.dyn4j.world.result.RaycastResult;

public final class GoverningSeams {
    private static final class CastProbe extends ConvexCastResult<Body, BodyFixture> {
        CastProbe(Body body, BodyFixture fixture, TimeOfImpact impact) {
            super(body, fixture, impact);
        }
    }

    private static final class ConvexProbe extends ConvexDetectResult<Body, BodyFixture> {
        ConvexProbe(Body body, BodyFixture fixture, Penetration penetration) {
            super(body, fixture, penetration);
        }
    }

    private static final class RayProbe extends RaycastResult<Body, BodyFixture> {
        RayProbe(Body body, BodyFixture fixture, Raycast raycast) {
            super(body, fixture, raycast);
        }
    }

    private static void require(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }

    public static void main(String[] args) throws Exception {
        BinarySearchTree<Integer> tree = new AVLTree<Integer>();
        tree.insert(2);
        tree.insert(1);
        tree.insert(3);
        require(tree.isSelfBalancing(), "AVL balancing contract");
        require("BinarySearchTree[1,2,3]".equals(tree.toString()), "AVL text contract");
        PrintStream previous = System.out;
        ByteArrayOutputStream printed = new ByteArrayOutputStream();
        try {
            System.setOut(new PrintStream(printed, true, "UTF-8"));
            tree.print();
        } finally {
            System.setOut(previous);
        }
        require(printed.toString("UTF-8").contains("2"), "AVL print contract");

        Shape shape = new Circle(2.0);
        Interval projection = shape.project(new Vector2(1.0, 0.0));
        require(projection.getMin() == -2.0 && projection.getMax() == 2.0,
                "shape projection without transform");

        List<Vector2> points = Arrays.asList(new Vector2(0.0, 0.0),
                new Vector2(2.0, 0.0), new Vector2(1.0, 1.0),
                new Vector2(2.0, 2.0), new Vector2(0.0, 2.0));
        Decomposer decomposer = new Bayazit();
        List<Convex> parts = decomposer.decompose(points);
        require(parts.size() > 1, "list-based concave decomposition");
        HullGenerator hullGenerator = new GrahamScan();
        require(hullGenerator.generate(points).size() == 4, "list-based convex hull");

        SolvableContact concrete = new SolvableContact(ManifoldPointId.DISTANCE,
                new Vector2(), 0.25, new Vector2(), new Vector2());
        Contact contract = concrete;
        require(!contract.isIgnored(), "initial contact ignore state");
        concrete.ignored = true;
        require(contract.isIgnored(), "inherited contact ignore dispatch");

        Vector2 vector = new Vector2(2.0, 3.0);
        Vector2 vectorCopy = Unsafe.copy(vector);
        require(vectorCopy != vector && vectorCopy.equals(vector), "checked copy identity");
        require(new CopyException(Vector2.class, Circle.class).getMessage().contains("Vector2"),
                "copy failure identifies the source type");

        TimeOfImpact impact = new TimeOfImpact();
        impact.setTime(0.25);
        TimeOfImpact copiedImpact = new TimeOfImpact();
        copiedImpact.copy(impact);
        require(copiedImpact.getTime() == 0.25, "time-of-impact copy");
        Manifold manifold = new Manifold();
        manifold.setNormal(new Vector2(1.0, 0.0));
        Manifold copiedManifold = new Manifold();
        copiedManifold.copy(manifold);
        require(copiedManifold.getNormal().x == 1.0, "manifold copy");
        ManifoldPoint point = new ManifoldPoint(ManifoldPointId.DISTANCE);
        point.setDepth(0.4);
        ManifoldPoint copiedPoint = new ManifoldPoint(ManifoldPointId.DISTANCE);
        copiedPoint.copy(point);
        require(copiedPoint.getDepth() == 0.4, "manifold point copy");
        Containment containment = new Containment();
        containment.setAContainedInB(true);
        Containment copiedContainment = new Containment();
        copiedContainment.copy(containment);
        require(copiedContainment.isAContainedInB(), "containment copy");
        Penetration penetration = new Penetration();
        penetration.setDepth(0.6);
        Penetration copiedPenetration = new Penetration();
        copiedPenetration.copy(penetration);
        require(copiedPenetration.getDepth() == 0.6, "penetration copy");
        Raycast raycast = new Raycast();
        raycast.setDistance(0.8);
        Raycast copiedRaycast = new Raycast();
        copiedRaycast.copy(raycast);
        require(copiedRaycast.getDistance() == 0.8, "raycast copy");
        Separation separation = new Separation();
        separation.setDistance(1.2);
        Separation copiedSeparation = new Separation();
        copiedSeparation.copy(separation);
        require(copiedSeparation.getDistance() == 1.2, "separation copy");
        Settings settings = new Settings();
        settings.setStepFrequency(1.0 / 90.0);
        Settings copiedSettings = new Settings();
        copiedSettings.copy(settings);
        require(copiedSettings.getStepFrequency() == settings.getStepFrequency(), "settings copy");

        Body body1 = new Body();
        BodyFixture fixture1 = body1.addFixture(new Circle(1.0));
        body1.setAtRest(true);
        require(body1.removeFixture(new Vector2()) == fixture1 && !body1.isAtRest(),
                "point removal wakes a resting body");
        body1.addFixture(new Circle(1.0));
        body1.addFixture(new Circle(0.5));
        body1.setAtRest(true);
        require(body1.removeFixtures(new Vector2()).size() == 2 && !body1.isAtRest(),
                "point removal of multiple fixtures wakes a resting body");
        BodyFixture contactFixture1 = body1.addFixture(new Circle(1.0));
        Body body2 = new Body();
        BodyFixture contactFixture2 = body2.addFixture(new Circle(1.0));
        CollisionItem<Body, BodyFixture> item1 = new BasicCollisionItem<Body, BodyFixture>(body1, contactFixture1);
        CollisionItem<Body, BodyFixture> item2 = new BasicCollisionItem<Body, BodyFixture>(body2, contactFixture2);
        CollisionPair<CollisionItem<Body, BodyFixture>> pair =
                new BasicCollisionPair<CollisionItem<Body, BodyFixture>>(item1, item2);
        ContactConstraint<Body> constraint = new ContactConstraint<Body>(pair);
        constraint.setFriction(0.3);
        constraint.setRestitution(0.4);
        constraint.setRestitutionVelocity(0.5);
        constraint.setSensor(true);
        require(constraint.getFriction() == 0.3 && constraint.getRestitution() == 0.4
                && constraint.getRestitutionVelocity() == 0.5 && constraint.isSensor(),
                "legacy contact setters retain values");

        AngleJoint<Body> angle = new AngleJoint<Body>(body1, body2);
        require(angle.getJointAngle() == angle.getAngularTranslation(), "legacy angle query");
        MotorJoint<Body> motor = new MotorJoint<Body>(body1, body2);
        Vector2 target = motor.getLinearTarget().copy();
        motor.shift(new Vector2(3.0, 4.0));
        require(motor.getLinearTarget().equals(target), "motor local target remains after shift");
        WeldJoint<Body> weld = new WeldJoint<Body>(body1, body2, new Vector2());
        require(weld.getAngularTranslation() == 0.0, "weld initial angular translation");

        Circle rotated = new Circle(1.0);
        rotated.translate(1.0, 0.0);
        rotated.rotate(new Rotation(Math.PI / 2.0));
        rotated.rotate(Math.PI / 2.0, new Vector2());
        rotated.rotate(new Rotation(Math.PI / 2.0), new Vector2());
        require(Double.isFinite(rotated.getCenter().x) && Double.isFinite(rotated.getCenter().y),
                "shape rotation overloads");
        require(new Geometry() != null && new RobustGeometry() != null,
                "utility constructors remain source compatible");
        require(ContinuousDetectionMode.valueOf(ContinuousDetectionMode.values()[0].name())
                == ContinuousDetectionMode.values()[0], "continuous detection enum lookup");
        require(MassType.valueOf(MassType.values()[0].name()) == MassType.values()[0],
                "mass enum lookup");
        require(Rotation.of(0.0, 1.0) != null, "rotation direction factory");

        DetectResult<Body, BodyFixture> detection = new DetectResult<Body, BodyFixture>();
        detection.setBody(body1);
        detection.setFixture(contactFixture1);
        DetectResult<Body, BodyFixture> copiedDetection = new DetectResult<Body, BodyFixture>();
        copiedDetection.copy(detection);
        require(copiedDetection.getBody() == body1 && copiedDetection.getFixture() == contactFixture1,
                "detect result copy preserves object identity");
        ConvexCastResult<Body, BodyFixture> cast = new CastProbe(body1, contactFixture1, impact);
        ConvexCastResult<Body, BodyFixture> copiedCast = new ConvexCastResult<Body, BodyFixture>();
        copiedCast.copy(cast);
        require(copiedCast.getBody() == body1 && copiedCast.getTimeOfImpact().getTime() == 0.25,
                "protected cast constructor and copy retain contact data");
        ConvexDetectResult<Body, BodyFixture> convex =
                new ConvexProbe(body1, contactFixture1, penetration);
        ConvexDetectResult<Body, BodyFixture> copiedConvex = new ConvexDetectResult<Body, BodyFixture>();
        copiedConvex.copy(convex);
        require(copiedConvex.getBody() == body1 && copiedConvex.getPenetration().getDepth() == 0.6,
                "protected detect constructor and copy retain penetration");
        RaycastResult<Body, BodyFixture> ray = new RayProbe(body1, contactFixture1, raycast);
        RaycastResult<Body, BodyFixture> copiedRay = new RaycastResult<Body, BodyFixture>();
        copiedRay.copy(ray);
        require(copiedRay.getBody() == body1 && copiedRay.getRaycast().getDistance() == 0.8,
                "protected ray constructor and copy retain raycast");

        System.out.println("governing seams passed");
    }
}
