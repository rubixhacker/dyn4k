package org.dyn4j.samples.framework;

import java.awt.Graphics2D;
import java.awt.image.BufferedImage;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.management.ManagementFactory;
import java.lang.management.RuntimeMXBean;
import java.io.PrintStream;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;
import org.dyn4j.collision.CollisionPair;
import org.dyn4j.collision.broadphase.BroadphaseDetector;
import org.dyn4j.collision.broadphase.BroadphaseDetectorDecoratorAdapter;
import org.dyn4j.collision.continuous.TimeOfImpact;
import org.dyn4j.collision.continuous.TimeOfImpactDetector;
import org.dyn4j.dynamics.BodyFixture;
import org.dyn4j.dynamics.ContinuousDetectionMode;
import org.dyn4j.dynamics.TimeStep;
import org.dyn4j.dynamics.contact.Contact;
import org.dyn4j.geometry.Convex;
import org.dyn4j.geometry.Transform;
import org.dyn4j.geometry.Vector2;
import org.dyn4j.samples.Billiards;
import org.dyn4j.world.ContactCollisionData;
import org.dyn4j.world.AbstractPhysicsWorld;
import org.dyn4j.world.PhysicsWorld;
import org.dyn4j.world.World;
import org.dyn4j.world.listener.ContactListenerAdapter;
import org.dyn4j.world.listener.StepListenerAdapter;
import org.dyn4j.world.listener.TimeOfImpactListenerAdapter;

public final class BilliardsReplay {
    private static long begin;
    private static long persist;
    private static long end;
    private static long toiCalls;
    private static long toiHits;
    private static long toiListenerHits;
    private static final List<String> contacts = new ArrayList<String>();
    private static final List<String> toiEvents = new ArrayList<String>();
    private static final List<String> ccdPairs = new ArrayList<String>();
    private static final List<String> ccdCandidates = new ArrayList<String>();
    private static final List<String> preludePairs = new ArrayList<String>();
    private static World<SimulationBody> world;

    private static int index(SimulationBody body) {
        for (int i = 0; i < world.getBodyCount(); i++) if (world.getBody(i) == body) return i;
        throw new IllegalStateException("contact body missing from sample world");
    }

    private static void contact(String kind, ContactCollisionData<SimulationBody> collision, Contact contact) {
        Vector2 point = contact.getPoint();
        contacts.add("{\"kind\":\"" + kind + "\",\"a\":" + index(collision.getBody1())
                + ",\"b\":" + index(collision.getBody2()) + ",\"x\":" + point.x
                + ",\"y\":" + point.y + ",\"depth\":" + contact.getDepth() + "}");
    }

    private static final class CountingDetector implements TimeOfImpactDetector {
        private final TimeOfImpactDetector delegate;
        CountingDetector(TimeOfImpactDetector delegate) { this.delegate = delegate; }
        public boolean getTimeOfImpact(Convex a, Transform at, Vector2 ad, double aa, Convex b, Transform bt, Vector2 bd, double ba, TimeOfImpact out) {
            toiCalls++;
            boolean hit = delegate.getTimeOfImpact(a, at, ad, aa, b, bt, bd, ba, out);
            if (hit) toiHits++;
            return hit;
        }
        public boolean getTimeOfImpact(Convex a, Transform at, Vector2 ad, double aa, Convex b, Transform bt, Vector2 bd, double ba, double min, double max, TimeOfImpact out) {
            toiCalls++;
            boolean hit = delegate.getTimeOfImpact(a, at, ad, aa, b, bt, bd, ba, min, max, out);
            if (hit) toiHits++;
            return hit;
        }
    }

    private static Field field(Class<?> type, String name) throws Exception {
        Field result = type.getDeclaredField(name);
        result.setAccessible(true);
        return result;
    }

    private static void replaceCcdDetectorWithPairObserver() throws Exception {
        BroadphaseDetector<SimulationBody> detector = world.getContinuousCollisionDetectionBroadphaseDetector();
        BroadphaseDetectorDecoratorAdapter<SimulationBody> observer =
                new BroadphaseDetectorDecoratorAdapter<SimulationBody>(detector) {
            public Iterator<CollisionPair<SimulationBody>> detectIterator() {
                final Iterator<CollisionPair<SimulationBody>> pairs = super.detectIterator();
                return new Iterator<CollisionPair<SimulationBody>>() {
                    public boolean hasNext() { return pairs.hasNext(); }
                    public CollisionPair<SimulationBody> next() {
                        CollisionPair<SimulationBody> pair = pairs.next();
                        ccdPairs.add("[" + index(pair.getFirst()) + "," + index(pair.getSecond()) + "]");
                        return pair;
                    }
                    public void remove() { pairs.remove(); }
                };
            }
        };
        field(AbstractPhysicsWorld.class, "ccdBroadphase").set(world, observer);
    }

    private static String hashFlags(RuntimeMXBean runtime) {
        List<String> flags = new ArrayList<String>();
        for (String argument : runtime.getInputArguments()) {
            if (argument.equals("-XX:+UnlockExperimentalVMOptions") || argument.startsWith("-XX:hashCode=")) {
                flags.add(argument);
            }
        }
        if (!flags.equals(Arrays.asList("-XX:+UnlockExperimentalVMOptions", "-XX:hashCode=2"))) {
            throw new IllegalStateException("JVM identity-hash mode differs: " + flags);
        }
        if (System.identityHashCode(new Object()) != 1) {
            throw new IllegalStateException("JVM identity-hash behavior differs from mode 2");
        }
        return "[\"" + flags.get(0) + "\",\"" + flags.get(1) + "\"]";
    }

    private static String loadedArtifactSha256() throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream input = Files.newInputStream(Paths.get(
                World.class.getProtectionDomain().getCodeSource().getLocation().toURI()))) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = input.read(buffer)) != -1) digest.update(buffer, 0, count);
        }
        StringBuilder hash = new StringBuilder(64);
        for (byte value : digest.digest()) hash.append(String.format("%02x", value & 0xff));
        return hash.toString();
    }

    private static void shot(Billiards frame, double power, double angle) throws Exception {
        field(Billiards.class, "power").setDouble(frame, power);
        field(Billiards.class, "angle").setDouble(frame, angle);
        Method render = Billiards.class.getDeclaredMethod("render", Graphics2D.class, double.class);
        render.setAccessible(true);
        Graphics2D graphics = new BufferedImage(800, 600, BufferedImage.TYPE_INT_ARGB).createGraphics();
        try {
            render.invoke(frame, graphics, 0.0);
        } finally {
            graphics.dispose();
        }
        Object shoot = field(Billiards.class, "shoot").get(frame);
        field(shoot.getClass(), "active").setBoolean(shoot, true);
        field(shoot.getClass(), "hasBeenHandled").setBoolean(shoot, false);
        Method handle = Billiards.class.getDeclaredMethod("handleEvents");
        handle.setAccessible(true);
        handle.invoke(frame);
        if (!field(shoot.getClass(), "hasBeenHandled").getBoolean(shoot)) {
            throw new IllegalStateException("unchanged Billiards shot handler did not run");
        }
        field(shoot.getClass(), "active").setBoolean(shoot, false);
    }

    private static String stepRecord(int step) {
        StringBuilder out = new StringBuilder(4096);
        Vector2 gravity = world.getGravity();
        out.append("{\"kind\":\"step\",\"step\":").append(step)
                .append(",\"body_count\":").append(world.getBodyCount())
                .append(",\"joint_count\":").append(world.getJointCount())
                .append(",\"gravity\":[").append(gravity.x).append(',').append(gravity.y)
                .append("],\"bodies\":[");
        for (int i = 0; i < world.getBodyCount(); i++) {
            SimulationBody body = world.getBody(i);
            Vector2 center = body.getWorldCenter();
            Vector2 velocity = body.getLinearVelocity();
            if (i > 0) out.append(',');
            out.append("{\"i\":").append(i).append(",\"x\":").append(center.x)
                    .append(",\"y\":").append(center.y).append(",\"vx\":").append(velocity.x)
                    .append(",\"vy\":").append(velocity.y).append(",\"angle\":")
                    .append(body.getTransform().getRotationAngle()).append(",\"omega\":")
                    .append(body.getAngularVelocity()).append(",\"rest\":").append(body.isAtRest())
                    .append(",\"bullet\":").append(body.isBullet())
                    .append(",\"fixtures\":").append(body.getFixtureCount())
                    .append(",\"mass\":").append(body.getMass().getMass())
                    .append(",\"inertia\":").append(body.getMass().getInertia())
                    .append(",\"linear_damping\":").append(body.getLinearDamping())
                    .append(",\"angular_damping\":").append(body.getAngularDamping())
                    .append(",\"identity_hash\":").append(System.identityHashCode(body))
                    .append(",\"fixture_identity_hashes\":[");
            for (int fixture = 0; fixture < body.getFixtureCount(); fixture++) {
                if (fixture > 0) out.append(',');
                out.append(System.identityHashCode(body.getFixture(fixture)));
            }
            out.append(']')
                    .append('}');
        }
        out.append("],\"ccd_pairs\":[");
        for (int i = 0; i < ccdPairs.size(); i++) {
            if (i > 0) out.append(',');
            out.append(ccdPairs.get(i));
        }
        out.append("],\"ccd_candidates\":[");
        for (int i = 0; i < ccdCandidates.size(); i++) {
            if (i > 0) out.append(',');
            out.append(ccdCandidates.get(i));
        }
        out.append("],\"contacts\":[");
        for (int i = 0; i < contacts.size(); i++) {
            if (i > 0) out.append(',');
            out.append(contacts.get(i));
        }
        out.append("],\"toi_events\":[");
        for (int i = 0; i < toiEvents.size(); i++) {
            if (i > 0) out.append(',');
            out.append(toiEvents.get(i));
        }
        out.append("],\"contact_begin\":").append(begin)
                .append(",\"contact_persist\":").append(persist)
                .append(",\"contact_end\":").append(end)
                .append(",\"toi_calls\":").append(toiCalls)
                .append(",\"toi_hits\":").append(toiHits)
                .append(",\"toi_listener_hits\":").append(toiListenerHits).append('}');
        String record = out.toString();
        contacts.clear();
        toiEvents.clear();
        ccdPairs.clear();
        ccdCandidates.clear();
        return record;
    }

    private static void emit(int step) {
        System.out.println(stepRecord(step));
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 8) throw new IllegalArgumentException("provider artifact source-manifest power angle steps dt ccd required");
        String provider = args[0];
        String artifact = args[1];
        String loadedArtifact = loadedArtifactSha256();
        if (!artifact.equals(loadedArtifact))
            throw new IllegalStateException("loaded engine JAR differs from declared artifact: " + loadedArtifact);
        String manifest = args[2];
        double power = Double.parseDouble(args[3]);
        double angle = Double.parseDouble(args[4]);
        int steps = Integer.parseInt(args[5]);
        double dt = Double.parseDouble(args[6]);
        ContinuousDetectionMode ccd = ContinuousDetectionMode.valueOf(args[7]);
        RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();
        String flags = hashFlags(runtime);
        if (!Double.isFinite(power) || power <= 0 || !Double.isFinite(angle) ||
                !Double.isFinite(dt) || dt <= 0 || steps <= 0)
            throw new IllegalArgumentException("invalid fixed input");
        PrintStream stream = System.out;
        System.setOut(System.err);
        Billiards frame;
        try {
            frame = new Billiards();
        } finally {
            System.setOut(stream);
        }
        try {
            frame.reset();
            world = frame.world;
            String resetState = stepRecord(-120);
            world.getSettings().setStepFrequency(dt);
            world.getSettings().setContinuousDetectionMode(ccd);
            replaceCcdDetectorWithPairObserver();
            StepListenerAdapter<SimulationBody> preludeObserver = new StepListenerAdapter<SimulationBody>() {
                public void end(TimeStep timeStep, PhysicsWorld<SimulationBody, ?> physicsWorld) {
                    preludePairs.add("[" + String.join(",", ccdPairs) + "]");
                    ccdPairs.clear();
                }
            };
            world.addStepListener(preludeObserver);
            world.step(120, dt);
            world.removeStepListener(preludeObserver);
            if (preludePairs.size() != 120) throw new IllegalStateException("prelude step observer missed a step");
            String preludeState = stepRecord(-1);
            world.addContactListener(new ContactListenerAdapter<SimulationBody>() {
                public void begin(ContactCollisionData<SimulationBody> collision, Contact contact) { begin++; contact("begin", collision, contact); }
                public void persist(ContactCollisionData<SimulationBody> collision, Contact oldContact, Contact newContact) { persist++; contact("persist", collision, newContact); }
                public void end(ContactCollisionData<SimulationBody> collision, Contact contact) { end++; contact("end", collision, contact); }
            });
            world.addTimeOfImpactListener(new TimeOfImpactListenerAdapter<SimulationBody>() {
                public boolean collision(SimulationBody a, SimulationBody b) {
                    ccdCandidates.add("[" + index(a) + "," + index(b) + "]");
                    return true;
                }
                public boolean collision(SimulationBody a, BodyFixture af, SimulationBody b, BodyFixture bf, TimeOfImpact toi) {
                    toiListenerHits++;
                    toiEvents.add("{\"a\":" + index(a) + ",\"b\":" + index(b)
                            + ",\"time\":" + toi.getTime() + "}");
                    return true;
                }
            });
            world.setTimeOfImpactDetector(new CountingDetector(world.getTimeOfImpactDetector()));
            shot(frame, power, angle);
            SimulationBody cue = (SimulationBody) field(Billiards.class, "cueBall").get(frame);
            Vector2 velocity = cue.getLinearVelocity();
            if (Math.abs(velocity.x - Math.cos(angle) * power * 10.0) > 1e-12 ||
                    Math.abs(velocity.y - Math.sin(angle) * power * 10.0) > 1e-12)
                throw new IllegalStateException("sample cue action differs from fixed input");
            System.out.println("{\"kind\":\"input\",\"provider\":\"" + provider
                    + "\",\"artifact_sha256\":\"" + artifact
                    + "\",\"sample_revision\":\"2c6b318e929baab77e9753ae78a4965eee74a30a\""
                    + ",\"source_manifest_sha256\":\"" + manifest + "\",\"power\":" + power
                    + ",\"angle\":" + angle + ",\"dt\":" + dt + ",\"prelude_steps\":120,\"steps\":" + steps
                    + ",\"ccd\":\"" + ccd.name() + "\",\"observation_stride\":1,\"cue_velocity\":["
                    + velocity.x + "," + velocity.y + "]"
                    + ",\"jvm_identity_hash_mode\":2,\"jvm_identity_hash_probe\":1"
                    + ",\"jvm_input_arguments\":" + flags
                    + ",\"reset_state\":" + resetState
                    + ",\"prelude_state\":" + preludeState
                    + ",\"prelude_pairs\":[" + String.join(",", preludePairs) + "]"
                    + ",\"world_code_source\":\"" + World.class.getProtectionDomain().getCodeSource().getLocation() + "\""
                    + ",\"java_home\":\"" + System.getProperty("java.home") + "\""
                    + ",\"java_version\":\"" + System.getProperty("java.version") + "\"}");
            System.err.println("REPLAY_PROCESS " + runtime.getName() + " start_ms=" + runtime.getStartTime());
            emit(0);
            for (int step = 1; step <= steps; step++) {
                world.step(1, dt);
                emit(step);
            }
        } finally {
            frame.dispose();
        }
    }
}
