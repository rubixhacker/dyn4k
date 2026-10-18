package org.dyn4j.samples.framework;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;
import javax.swing.SwingUtilities;
import org.dyn4j.collision.continuous.TimeOfImpact;
import org.dyn4j.collision.continuous.TimeOfImpactDetector;
import org.dyn4j.dynamics.BodyFixture;
import org.dyn4j.dynamics.TimeStep;
import org.dyn4j.dynamics.contact.Contact;
import org.dyn4j.dynamics.joint.Joint;
import org.dyn4j.dynamics.joint.WheelJoint;
import org.dyn4j.geometry.Convex;
import org.dyn4j.geometry.Transform;
import org.dyn4j.geometry.Vector2;
import org.dyn4j.world.ContactCollisionData;
import org.dyn4j.world.PhysicsWorld;
import org.dyn4j.world.World;
import org.dyn4j.world.listener.ContactListenerAdapter;
import org.dyn4j.world.listener.StepListenerAdapter;
import org.dyn4j.world.listener.TimeOfImpactListenerAdapter;

public final class SceneObserver {
    private static final BlockingQueue<Snapshot> snapshots = new ArrayBlockingQueue<Snapshot>(2048);
    private static volatile Thread simulationThread;
    private static volatile Throwable failure;
    private static String scene;
    private static long nextCaptureNanos;
    private static long begins;
    private static long persists;
    private static long ends;
    private static long toiCalls;
    private static long toiHits;
    private static long toiListenerHits;
    private static long steps;
    private static double stepDt;
    private static int resets;
    private static SimulationBody initialBody;

    private static final ContactListenerAdapter<SimulationBody> contacts = new ContactListenerAdapter<SimulationBody>() {
        public void begin(ContactCollisionData<SimulationBody> collision, Contact contact) { if (onSimulationThread()) begins++; }
        public void persist(ContactCollisionData<SimulationBody> collision, Contact oldContact, Contact newContact) { if (onSimulationThread()) persists++; }
        public void end(ContactCollisionData<SimulationBody> collision, Contact contact) { if (onSimulationThread()) ends++; }
    };

    private static final TimeOfImpactListenerAdapter<SimulationBody> toiListener = new TimeOfImpactListenerAdapter<SimulationBody>() {
        public boolean collision(SimulationBody body1, BodyFixture fixture1, SimulationBody body2, BodyFixture fixture2, TimeOfImpact toi) {
            if (onSimulationThread()) toiListenerHits++;
            return true;
        }
    };

    private static final StepListenerAdapter<SimulationBody> stepListener = new StepListenerAdapter<SimulationBody>() {
        public void begin(TimeStep step, PhysicsWorld<SimulationBody, ?> world) {
            if (onSimulationThread()) {
                steps++;
                stepDt = step.getDeltaTime();
            }
        }
    };

    private static final class CountingDetector implements TimeOfImpactDetector {
        private final TimeOfImpactDetector delegate;
        CountingDetector(TimeOfImpactDetector delegate) { this.delegate = delegate; }
        public boolean getTimeOfImpact(Convex a, Transform at, Vector2 ad, double aa, Convex b, Transform bt, Vector2 bd, double ba, TimeOfImpact out) {
            if (onSimulationThread()) toiCalls++;
            boolean hit = delegate.getTimeOfImpact(a, at, ad, aa, b, bt, bd, ba, out);
            if (hit && onSimulationThread()) toiHits++;
            return hit;
        }
        public boolean getTimeOfImpact(Convex a, Transform at, Vector2 ad, double aa, Convex b, Transform bt, Vector2 bd, double ba, double min, double max, TimeOfImpact out) {
            if (onSimulationThread()) toiCalls++;
            boolean hit = delegate.getTimeOfImpact(a, at, ad, aa, b, bt, bd, ba, min, max, out);
            if (hit && onSimulationThread()) toiHits++;
            return hit;
        }
    }

    private static final class BodyState {
        final int index;
        final double x;
        final double y;
        final double vx;
        final double vy;
        final boolean rest;
        BodyState(int index, double x, double y, double vx, double vy, boolean rest) {
            this.index = index; this.x = x; this.y = y; this.vx = vx; this.vy = vy; this.rest = rest;
        }
        void appendJson(StringBuilder out) {
            out.append("{\"i\":").append(index).append(",\"x\":").append(x).append(",\"y\":").append(y)
                .append(",\"vx\":").append(vx).append(",\"vy\":").append(vy).append(",\"rest\":").append(rest).append('}');
        }
    }

    private static final class JointState {
        final int index;
        final String type;
        final double motorSpeed;
        final double translation;
        JointState(int index, String type, double motorSpeed, double translation) {
            this.index = index; this.type = type; this.motorSpeed = motorSpeed; this.translation = translation;
        }
        void appendJson(StringBuilder out) {
            out.append("{\"i\":").append(index).append(",\"type\":\"").append(type)
                .append("\",\"motorSpeed\":").append(motorSpeed).append(",\"translation\":").append(translation).append('}');
        }
    }

    private static final class Snapshot {
        final String scene;
        final long threadId;
        final long nanos;
        final int bodyCount;
        final int jointCount;
        final int resets;
        final String ccdMode;
        final long begins;
        final long persists;
        final long ends;
        final long toiCalls;
        final long toiHits;
        final long toiListenerHits;
        final long steps;
        final double stepDt;
        final List<BodyState> bodies;
        final List<JointState> joints;
        Snapshot(String scene, long threadId, long nanos, int bodyCount, int jointCount, int resets,
                 String ccdMode, long begins, long persists, long ends, long toiCalls, long toiHits,
                 long toiListenerHits, long steps, double stepDt, List<BodyState> bodies, List<JointState> joints) {
            this.scene = scene; this.threadId = threadId; this.nanos = nanos; this.bodyCount = bodyCount;
            this.jointCount = jointCount; this.resets = resets; this.ccdMode = ccdMode;
            this.begins = begins; this.persists = persists; this.ends = ends; this.toiCalls = toiCalls;
            this.toiHits = toiHits; this.toiListenerHits = toiListenerHits;
            this.steps = steps; this.stepDt = stepDt;
            this.bodies = Collections.unmodifiableList(bodies);
            this.joints = Collections.unmodifiableList(joints);
        }
        String toJson() {
            StringBuilder out = new StringBuilder(512 + bodies.size() * 90);
            out.append("{\"scene\":\"").append(scene).append("\",\"threadId\":").append(threadId)
                .append(",\"nanos\":").append(nanos).append(",\"bodyCount\":").append(bodyCount)
                .append(",\"jointCount\":").append(jointCount).append(",\"resets\":").append(resets)
                .append(",\"ccdMode\":\"").append(ccdMode).append("\",\"begin\":").append(begins)
                .append(",\"persist\":").append(persists).append(",\"end\":").append(ends)
                .append(",\"toiCalls\":").append(toiCalls).append(",\"toiHits\":").append(toiHits)
                .append(",\"toiListenerHits\":").append(toiListenerHits)
                .append(",\"steps\":").append(steps).append(",\"stepDt\":").append(stepDt).append(",\"bodies\":[");
            for (int i = 0; i < bodies.size(); i++) {
                if (i != 0) out.append(',');
                bodies.get(i).appendJson(out);
            }
            out.append("],\"joints\":[");
            for (int i = 0; i < joints.size(); i++) {
                if (i != 0) out.append(',');
                joints.get(i).appendJson(out);
            }
            return out.append("]}").toString();
        }
    }

    private static boolean onSimulationThread() {
        if (Thread.currentThread() == simulationThread) return true;
        failure = new IllegalStateException("Observer accessed world outside game-loop thread");
        return false;
    }

    public static void onLoopEnter(SimulationFrame frame) {
        Thread current = Thread.currentThread();
        if (simulationThread == null) simulationThread = current;
        else if (simulationThread != current) failure = new IllegalStateException("Game loop changed thread");
    }

    public static void tick(SimulationFrame frame) {
        if (!onSimulationThread()) return;
        try {
            World<SimulationBody> world = frame.world;
            if (!(world.getTimeOfImpactDetector() instanceof CountingDetector)) {
                world.setTimeOfImpactDetector(new CountingDetector(world.getTimeOfImpactDetector()));
            }
            if (!world.getContactListeners().contains(contacts)) world.addContactListener(contacts);
            if (!world.getTimeOfImpactListeners().contains(toiListener)) world.addTimeOfImpactListener(toiListener);
            if (!world.getStepListeners().contains(stepListener)) world.addStepListener(stepListener);
            SimulationBody firstBody = world.getBodyCount() > 0 ? world.getBody(0) : null;
            if (initialBody != null && firstBody != initialBody) resets++;
            initialBody = firstBody;
            long now = System.nanoTime();
            if (now < nextCaptureNanos) return;
            nextCaptureNanos = now + TimeUnit.MILLISECONDS.toNanos(100);
            List<BodyState> bodies = new ArrayList<BodyState>(world.getBodyCount());
            for (int i = 0; i < world.getBodyCount(); i++) {
                SimulationBody body = world.getBody(i);
                Vector2 center = body.getWorldCenter();
                Vector2 velocity = body.getLinearVelocity();
                bodies.add(new BodyState(i, center.x, center.y, velocity.x, velocity.y, body.isAtRest()));
            }
            List<JointState> joints = new ArrayList<JointState>(world.getJointCount());
            for (int i = 0; i < world.getJointCount(); i++) {
                Joint<SimulationBody> joint = world.getJoint(i);
                if (joint instanceof WheelJoint) {
                    WheelJoint<?> wheel = (WheelJoint<?>) joint;
                    joints.add(new JointState(i, "WheelJoint", wheel.getMotorSpeed(), wheel.getLinearTranslation()));
                } else {
                    joints.add(new JointState(i, joint.getClass().getSimpleName(), 0.0, 0.0));
                }
            }
            Snapshot snapshot = new Snapshot(scene, Thread.currentThread().getId(), now, bodies.size(), joints.size(), resets,
                    world.getSettings().getContinuousDetectionMode().name(), begins, persists, ends,
                    toiCalls, toiHits, toiListenerHits, steps, stepDt, bodies, joints);
            if (!snapshots.offer(snapshot)) failure = new IllegalStateException("Snapshot queue full");
        } catch (Throwable error) {
            failure = error;
        }
    }

    public static void main(String[] args) throws Exception {
        scene = args[0];
        int seconds = Integer.parseInt(args[1]);
        final SimulationFrame frame = (SimulationFrame) Class.forName("org.dyn4j.samples." + scene).getDeclaredConstructor().newInstance();
        boolean joined = false;
        boolean disposed = false;
        try {
            frame.run();
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(seconds + 1L);
            while (System.nanoTime() < deadline && failure == null) {
                Snapshot snapshot = snapshots.poll(200, TimeUnit.MILLISECONDS);
                if (snapshot != null) System.out.println("OBS_JSON " + snapshot.toJson());
            }
        } finally {
            frame.stop();
            Thread thread = simulationThread;
            if (thread != null) {
                thread.interrupt();
                thread.join(5000);
                joined = !thread.isAlive();
            }
            Snapshot snapshot;
            while ((snapshot = snapshots.poll()) != null) System.out.println("OBS_JSON " + snapshot.toJson());
            if (joined) {
                SwingUtilities.invokeAndWait(new Runnable() {
                    public void run() { frame.dispose(); }
                });
                disposed = true;
            }
            System.out.println("OBSERVER_SHUTDOWN joined=" + joined + " disposed=" + disposed);
            System.out.flush();
        }
        if (failure != null) failure.printStackTrace(System.err);
        System.exit(joined && disposed && failure == null ? 0 : 1);
    }
}
