import org.dyn4j.collision.broadphase.BroadphaseDetector;
import org.dyn4j.dynamics.Body;
import org.dyn4j.dynamics.BodyFixture;
import org.dyn4j.dynamics.contact.ContactConstraintSolver;
import org.dyn4j.dynamics.contact.TimeOfImpactSolver;
import org.dyn4j.world.ValueMixer;
import org.dyn4j.world.World;
import org.dyn4j.world.result.ConvexCastResult;
import org.dyn4j.world.result.ConvexDetectResult;
import org.dyn4j.world.result.RaycastResult;

public final class WorldExtraMethodsConsumer {
    private static final class Simulation extends World<Body> {
        public String settingsField() { return "settings"; }
        public String timeStepField() { return "step"; }
        public String gravityField() { return "gravity"; }
        public String valueMixerField() { return "mixer"; }
        public String setValueMixerField(ValueMixer value) { return "set mixer"; }
        public String contactConstraintSolverField() { return "contacts"; }
        public String setContactConstraintSolverField(ContactConstraintSolver<Body> value) { return "set contacts"; }
        public String timeOfImpactSolverField() { return "toi"; }
        public String setTimeOfImpactSolverField(TimeOfImpactSolver<Body> value) { return "set toi"; }
        public String ccdBroadphaseField() { return "broadphase"; }
        public String setCcdBroadphaseField(BroadphaseDetector<Body> value) { return "set broadphase"; }
        public String jointsField() { return "joints"; }
        public String jointsUnmodifiableField() { return "joint view"; }
        public String contactListenersField() { return "contact listeners"; }
        public String contactListenersUnmodifiableField() { return "contact view"; }
        public String destructionListenersField() { return "destruction listeners"; }
        public String destructionListenersUnmodifiableField() { return "destruction view"; }
        public String timeOfImpactListenersField() { return "toi listeners"; }
        public String timeOfImpactListenersUnmodifiableField() { return "toi view"; }
        public String stepListenersField() { return "step listeners"; }
        public String stepListenersUnmodifiableField() { return "step view"; }
        public String timeField() { return "time"; }
        public String setTimeField(double value) { return "set time"; }
        public String updateRequiredField() { return "update"; }
        public String setUpdateRequiredField(boolean value) { return "set update"; }
        public String constraintGraphField() { return "graph"; }
        public String contactCollisionsField() { return "collisions"; }
        public String ccdCollisionDataField() { return "ccd data"; }

        boolean baselineFieldVisible() { return settings == getSettings(); }
    }

    private static final class Cast extends ConvexCastResult<Body, BodyFixture> {
        public String timeOfImpactField() { return "cast"; }
        boolean baselineFieldVisible() { return timeOfImpact == getTimeOfImpact(); }
    }

    private static final class Detect extends ConvexDetectResult<Body, BodyFixture> {
        public String penetrationField() { return "detect"; }
        boolean baselineFieldVisible() { return penetration == getPenetration(); }
    }

    private static final class Ray extends RaycastResult<Body, BodyFixture> {
        public String raycastField() { return "ray"; }
        boolean baselineFieldVisible() { return raycast == getRaycast(); }
    }

    public static void main(String[] args) {
        Simulation world = new Simulation();
        Cast cast = new Cast();
        Detect detect = new Detect();
        Ray ray = new Ray();
        if (!world.baselineFieldVisible() || !cast.baselineFieldVisible()
                || !detect.baselineFieldVisible() || !ray.baselineFieldVisible()) {
            throw new AssertionError("protected field is missing");
        }
        if (!"settings".equals(world.settingsField()) || !"cast".equals(cast.timeOfImpactField())
                || !"detect".equals(detect.penetrationField()) || !"ray".equals(ray.raycastField())) {
            throw new AssertionError("extension helper dispatch failed");
        }
        System.out.println("World extra methods extension passed");
    }
}
