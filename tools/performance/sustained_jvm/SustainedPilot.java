import java.io.BufferedWriter;
import java.io.IOException;
import java.lang.management.ManagementFactory;
import java.lang.management.GarbageCollectorMXBean;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.locks.LockSupport;
import performance.SustainedSidecars;
import org.dyn4j.collision.continuous.TimeOfImpact;
import org.dyn4j.dynamics.Body;
import org.dyn4j.dynamics.BodyFixture;
import org.dyn4j.dynamics.contact.Contact;
import org.dyn4j.dynamics.joint.*;
import org.dyn4j.geometry.Geometry;
import org.dyn4j.geometry.MassType;
import org.dyn4j.geometry.Vector2;
import org.dyn4j.world.ContactCollisionData;
import org.dyn4j.world.World;
import org.dyn4j.world.WorldCollisionData;
import org.dyn4j.world.listener.ContactListenerAdapter;
import org.dyn4j.world.listener.TimeOfImpactListenerAdapter;

public final class SustainedPilot {
    private static final int SEED = 17017;
    private final World<Body> world = new World<>();
    private final List<Body> dynamic = new ArrayList<>();
    private Body floor;
    private final String family;
    private final String variant;
    private final int count;
    private final int hz;
    private int nextCcdBodyIndex;
    private long contactBegins;
    private long contactEnds;
    private long toiEvents;

    private SustainedPilot(String family, String variant, int count, int hz) {
        this.family = family;
        this.variant = variant;
        this.count = count;
        this.hz = hz;
        world.addContactListener(new ContactListenerAdapter<Body>() {
            @Override public void begin(ContactCollisionData<Body> collision, Contact contact) {
                contactBegins++;
            }
            @Override public void end(ContactCollisionData<Body> collision, Contact contact) {
                contactEnds++;
            }
        });
        world.addTimeOfImpactListener(new TimeOfImpactListenerAdapter<Body>() {
            @Override public boolean collision(Body a, Body b, TimeOfImpact toi) {
                toiEvents++;
                return true;
            }
        });
        if (family.equals("separated")) buildSeparated();
        else if (family.equals("pile") || family.equals("lifecycle")) buildPile();
        else if (family.equals("joint")) buildJoint();
        else if (family.equals("ccd")) buildCcd();
        else throw new IllegalArgumentException("unknown family: " + family);
        if (world.getBodyCount() < count) throw new IllegalStateException("incomplete fixture");
    }

    private static final class CcdBody extends Body {
        private final int creationIndex;

        private CcdBody(int creationIndex) {
            this.creationIndex = creationIndex;
        }

        @Override public int hashCode() {
            return creationIndex;
        }
    }

    private Body newBody() {
        return family.equals("ccd") ? new CcdBody(nextCcdBodyIndex++) : new Body();
    }

    private Body circle(double x, double y) {
        Body body = newBody();
        BodyFixture fixture = body.addFixture(Geometry.createCircle(0.25));
        fixture.setDensity(1.0);
        fixture.setFriction(0.5);
        fixture.setRestitution(0.0);
        body.setMass(MassType.NORMAL);
        body.translate(x, y);
        return body;
    }

    private Body staticRectangle(double x, double y, double width, double height) {
        Body body = newBody();
        BodyFixture fixture = body.addFixture(Geometry.createRectangle(width, height));
        fixture.setDensity(1.0);
        fixture.setFriction(0.5);
        fixture.setRestitution(0.0);
        body.setMass(MassType.INFINITE);
        body.translate(x, y);
        world.addBody(body);
        return body;
    }

    private void addDynamic(Body body) {
        dynamic.add(body);
        world.addBody(body);
    }

    private void buildSeparated() {
        world.setGravity(0.0, 0.0);
        for (int i = 0; i < count; i++) {
            Body body = circle(-48.0 + (i % 32) * 3.0, 2.0 + (i / 32) * 3.0);
            body.setLinearVelocity(0.75, 0.0);
            addDynamic(body);
        }
    }

    private void buildPile() {
        floor = staticRectangle(0.0, -0.5, 200.0, 1.0);
        for (int i = 0; i < count; i++) {
            addDynamic(circle(((i % 10) - 4.5) * 0.48, 0.3 + (i / 10) * 0.48));
        }
        if (family.equals("lifecycle")) {
            for (int i = 0; i < count; i += 10) attachLifecycleJoint(dynamic.get(i));
        }
    }

    private void attachLifecycleJoint(Body body) {
        world.addJoint(new DistanceJoint<>(floor, body, floor.getWorldCenter(), body.getWorldCenter()));
    }

    private void buildCcd() {
        world.setGravity(0.0, 0.0);
        staticRectangle(-10.0, 10.0, 0.5, 20.0);
        staticRectangle(10.0, 10.0, 0.5, 20.0);
        for (int i = 0; i < count; i++) {
            double x = i % 2 == 0 ? -8.0 : 8.0;
            Body body = circle(x, 0.5 + (i % 20) * 0.45);
            body.setBullet(true);
            body.setLinearVelocity(i % 2 == 0 ? 18.0 : -18.0, 0.0);
            addDynamic(body);
        }
    }

    private void printCcdIdentity() {
        if (!family.equals("ccd")) throw new IllegalArgumentException("CCD identity requires CCD fixture");
        System.out.println("creation_index,hash_code,world_center_x,world_center_y,bullet");
        for (int index = 0; index < world.getBodyCount(); index++) {
            Body body = world.getBody(index);
            Vector2 center = body.getWorldCenter();
            System.out.println(index + "," + body.hashCode() + "," + center.x + "," + center.y + "," + body.isBullet());
        }
    }

    private void buildJoint() {
        String kind = variant.equals("mixed_all_types") ? "mixed" : variant.split("_", 2)[0];
        String mode = variant.equals("mixed_all_types") ? "mixed" : variant.split("_", 2)[1];
        String[] kinds = {"angle", "distance", "friction", "motor", "pin", "prismatic", "pulley", "revolute", "weld", "wheel"};
        for (int i = 0; i < count; i++) {
            double x = i * 3.0;
            Body anchor = staticRectangle(x, 3.0, 0.25, 0.25);
            Body body = circle(x, 2.0);
            body.setAtRestDetectionEnabled(false);
            addDynamic(body);
            String selected = kind.equals("mixed") ? kinds[i % kinds.length] : kind;
            String selectedMode = mode.equals("mixed") ? defaultMode(selected) : mode;
            world.addJoint(makeJoint(selected, selectedMode, anchor, body, x));
        }
    }

    private static String defaultMode(String kind) {
        if (kind.equals("distance") || kind.equals("weld")) return "rigid";
        if (kind.equals("pin") || kind.equals("wheel")) return "spring";
        if (kind.equals("pulley")) return "taut";
        if (kind.equals("friction")) return "friction";
        if (kind.equals("motor")) return "offset";
        return "free";
    }

    private static Joint<Body> makeJoint(String kind, String mode, Body anchor, Body body, double x) {
        Vector2 point = new Vector2(x, 2.5);
        Vector2 axis = new Vector2(1.0, 0.0);
        switch (kind) {
            case "angle": {
                AngleJoint<Body> joint = new AngleJoint<>(anchor, body);
                if (mode.equals("limits")) joint.setLimitsEnabled(-0.5, 0.5);
                if (mode.equals("ratio")) joint.setRatio(2.0);
                return joint;
            }
            case "distance": {
                DistanceJoint<Body> joint = new DistanceJoint<>(anchor, body, anchor.getWorldCenter(), body.getWorldCenter());
                if (mode.equals("limits")) joint.setLimitsEnabled(0.8, 1.2);
                if (mode.startsWith("spring")) {
                    joint.setSpringEnabled(true);
                    joint.setSpringFrequency(4.0);
                    joint.setSpringDamperEnabled(mode.equals("spring_damper"));
                    joint.setSpringDampingRatio(0.5);
                }
                return joint;
            }
            case "friction": {
                FrictionJoint<Body> joint = new FrictionJoint<>(anchor, body, point);
                joint.setMaximumForce(10.0);
                joint.setMaximumTorque(10.0);
                return joint;
            }
            case "motor": {
                MotorJoint<Body> joint = new MotorJoint<>(anchor, body);
                joint.setLinearTarget(0.0, 1.0);
                joint.setAngularTarget(0.25);
                joint.setMaximumForce(10.0);
                joint.setMaximumTorque(10.0);
                return joint;
            }
            case "pin": {
                PinJoint<Body> joint = new PinJoint<>(body, new Vector2(x, 3.0));
                joint.setSpringEnabled(true);
                joint.setSpringFrequency(4.0);
                joint.setSpringDamperEnabled(mode.equals("spring_damper"));
                joint.setSpringDampingRatio(0.5);
                return joint;
            }
            case "prismatic": {
                PrismaticJoint<Body> joint = new PrismaticJoint<>(anchor, body, point, axis);
                if (mode.equals("limits")) joint.setLimitsEnabled(-0.5, 0.5);
                if (mode.equals("motor")) { joint.setMotorEnabled(true); joint.setMotorSpeed(1.0); joint.setMaximumMotorForce(10.0); joint.setMaximumMotorForceEnabled(true); }
                if (mode.startsWith("spring")) {
                    joint.setSpringEnabled(true); joint.setSpringFrequency(4.0);
                    joint.setSpringDamperEnabled(mode.equals("spring_damper"));
                    joint.setSpringDampingRatio(0.5);
                }
                return joint;
            }
            case "pulley": {
                PulleyJoint<Body> joint = new PulleyJoint<>(anchor, body,
                    new Vector2(x - 1.0, 5.0), new Vector2(x + 1.0, 5.0),
                    anchor.getWorldCenter(), body.getWorldCenter());
                if (mode.equals("ratio")) joint.setRatio(2.0);
                if (mode.equals("slack")) joint.setSlackEnabled(true);
                return joint;
            }
            case "revolute": {
                RevoluteJoint<Body> joint = new RevoluteJoint<>(anchor, body, point);
                if (mode.equals("limits")) joint.setLimitsEnabled(-0.5, 0.5);
                if (mode.equals("motor")) { joint.setMotorEnabled(true); joint.setMotorSpeed(1.0); joint.setMaximumMotorTorque(10.0); joint.setMaximumMotorTorqueEnabled(true); }
                return joint;
            }
            case "weld": {
                WeldJoint<Body> joint = new WeldJoint<>(anchor, body, point);
                if (mode.equals("limits")) joint.setLimitsEnabled(-0.5, 0.5);
                if (mode.startsWith("spring")) {
                    joint.setSpringEnabled(true); joint.setSpringFrequency(4.0);
                    joint.setSpringDamperEnabled(mode.equals("spring_damper"));
                    joint.setSpringDampingRatio(0.5);
                }
                return joint;
            }
            case "wheel": {
                WheelJoint<Body> joint = new WheelJoint<>(anchor, body, point, axis);
                joint.setSpringEnabled(true);
                joint.setSpringFrequency(4.0);
                if (mode.equals("spring_damper")) { joint.setSpringDamperEnabled(true); joint.setSpringDampingRatio(0.5); }
                if (mode.equals("limits")) joint.setLimitsEnabled(-0.5, 0.5);
                if (mode.equals("motor")) { joint.setMotorEnabled(true); joint.setMotorSpeed(1.0); joint.setMaximumMotorTorque(10.0); joint.setMaximumMotorTorqueEnabled(true); }
                return joint;
            }
            default: throw new IllegalArgumentException("unknown joint: " + kind);
        }
    }

    private long mutate(int step) {
        if (step == 0 || step % hz != 0) return 0;
        if (family.equals("pile") || (family.equals("lifecycle") && variant.equals("settle"))) return 0;
        long start = System.nanoTime();
        if (family.equals("ccd")) {
            for (int i = 0; i < dynamic.size(); i++) {
                Body body = dynamic.get(i);
                double desired = i % 2 == 0 ? -8.0 : 8.0;
                body.translate(desired - body.getWorldCenter().x, 0.0);
                body.setLinearVelocity(i % 2 == 0 ? 18.0 : -18.0, 0.0);
            }
        } else if (family.equals("joint")) {
            for (Body body : dynamic) {
                body.applyImpulse(new Vector2(0.5, 1.0));
                body.applyImpulse(0.01);
            }
        } else if (family.equals("lifecycle") && variant.equals("wake")) {
            for (int i = 0; i < dynamic.size(); i += 10) dynamic.get(i).applyImpulse(new Vector2(0.2, 0.5));
        } else if (family.equals("lifecycle") && variant.equals("replace")) {
            int replacements = (count + 99) / 100;
            for (int i = 0; i < replacements; i++) {
                int index = (SEED + step / hz + i) % count;
                Body prior = dynamic.get(index);
                world.removeBody(prior, true);
                Body next = circle(((index % 10) - 4.5) * 0.48, 0.3 + (index / 10) * 0.48);
                world.addBody(next);
                dynamic.set(index, next);
                if (index % 10 == 0) attachLifecycleJoint(next);
            }
        } else if (family.equals("separated")) {
            for (Body body : dynamic) {
                double x = body.getWorldCenter().x;
                if (x > 48.0) body.translate(-96.0, 0.0);
                if (x < -48.0) body.translate(96.0, 0.0);
            }
        }
        return System.nanoTime() - start;
    }

    private static long rssBytes() {
        try {
            for (String line : Files.readAllLines(Path.of("/proc/self/status"))) {
                if (line.startsWith("VmRSS:")) return Long.parseLong(line.trim().split("\\s+")[1]) * 1024L;
            }
        } catch (Exception ignored) {
        }
        return -1;
    }

    private static long collections() {
        long result = 0L;
        for (GarbageCollectorMXBean bean : ManagementFactory.getGarbageCollectorMXBeans()) {
            if (bean.getCollectionCount() >= 0) result += bean.getCollectionCount();
        }
        return result;
    }

    private static void plateau(String family, String variant, int count, int hz, int warmup)
            throws InterruptedException, IOException {
        SustainedSidecars.AllocationProbe probe = SustainedSidecars.AllocationProbe.require();
        SustainedPilot warmed = new SustainedPilot(family, variant, count, hz);
        System.err.println("warmup_step,elapsed_ns");
        long warmStart = System.nanoTime();
        try (BufferedWriter clock = SustainedSidecars.clock("DYN4K_WARMUP_CLOCK_CSV",
                "warmup_step,begin_ns,end_ns")) {
            for (int step = 0; step < warmup; step++) {
                long deadline = warmStart + (1_000_000_000L * step) / hz;
                long wait = deadline - System.nanoTime();
                if (wait > 0) LockSupport.parkNanos(wait);
                long began = System.nanoTime();
                warmed.mutate(step);
                warmed.world.step(1, 1.0 / hz);
                long ended = System.nanoTime();
                SustainedSidecars.clockRow(clock, step, began, ended);
                System.err.println(step + "," + (ended - began));
            }
        }
        warmed = null;
        System.out.println("cycle,heap_after_collection_bytes,rss_after_collection_bytes,collection_count,managed_bytes,native_bytes,wasm_linear_bytes,attributed_workload_bytes,reserved_runtime_bytes");
        for (int cycle = 0; cycle < 100; cycle++) {
            long allocatedBefore = probe.read();
            plateauCycle(family, variant, count, hz);
            long allocatedAfter = probe.read();
            try {
                SustainedSidecars.allocation("plateau", cycle, probe, allocatedBefore, allocatedAfter);
            } catch (IOException error) {
                throw new IllegalStateException("plateau allocation sidecar failed", error);
            }
            long beforeCollections = collections();
            System.gc();
            Thread.sleep(10);
            long heap = Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory();
            long rss = rssBytes();
            long collected = collections();
            try {
                SustainedSidecars.plateau(cycle, heap, rss, collected, beforeCollections);
            } catch (IOException error) {
                throw new IllegalStateException("plateau sidecar failed", error);
            }
            System.out.println(cycle + "," + heap + "," + rss + "," + collected + ",-1,-1,0,-1,-1");
        }
    }

    private static void plateauCycle(String family, String variant, int count, int hz) {
        SustainedPilot fixture = new SustainedPilot(family, variant, count, hz);
        for (int step = 0; step < 2 * hz; step++) {
            fixture.mutate(step);
            fixture.world.step(1, 1.0 / hz);
        }
    }

    private void warm(int warmup, String mode, SustainedSidecars.AllocationProbe probe) throws IOException {
        System.err.println("warmup_step,elapsed_ns,rss_bytes");
        try (BufferedWriter clock = SustainedSidecars.clock("DYN4K_WARMUP_CLOCK_CSV",
                "warmup_step,begin_ns,end_ns")) {
            long warmStart = System.nanoTime();
            for (int i = 0; i < warmup; i++) {
                long warmDeadline = warmStart + (1_000_000_000L * i) / hz;
                long warmWait = warmDeadline - System.nanoTime();
                if (warmWait > 0) LockSupport.parkNanos(warmWait);
                long allocatedBefore = probe == null ? -1 : probe.read();
                long begin = System.nanoTime();
                mutate(i);
                world.step(1, 1.0 / hz);
                long end = System.nanoTime();
                long allocatedAfter = probe == null ? -1 : probe.read();
                SustainedSidecars.clockRow(clock, i, begin, end);
                if (probe != null) SustainedSidecars.allocation("warmup", i, probe, allocatedBefore, allocatedAfter);
                long rss = mode.equals("memory") ? rssBytes() : -1;
                System.err.println(i + "," + (end - begin) + "," + rss);
                SustainedSidecars.resource("warmup", i,
                        Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory(), rss, -1);
                if (mode.equals("memory")) SustainedSidecars.memory("warmup", i,
                        Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory(), rss, -1);
            }
        }
    }

    private static long[] run(String family, String variant, int count, int hz, int steps,
                              String mode, long rssBase, SustainedSidecars.AllocationProbe probe) throws IOException {
        if (!mode.equals("timing") && !mode.equals("allocation") && !mode.equals("memory"))
            throw new IllegalArgumentException("unknown mode: " + mode);
        SustainedPilot measured = new SustainedPilot(family, variant, count, hz);
        if (mode.equals("memory")) {
            long beforeCollections = collections();
            System.gc();
            try { Thread.sleep(100); } catch (InterruptedException exc) { Thread.currentThread().interrupt(); throw new IllegalStateException(exc); }
            long collectionDelta = collections() - beforeCollections;
            System.err.println("#retained_collection_count_delta=" + collectionDelta);
            if (collectionDelta > 0)
                System.err.println("#retained_heap_world_alive_bytes=" +
                        (Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory()));
            SustainedSidecars.memory("retained", 0,
                    Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory(), rssBytes(), collectionDelta);
        } else {
            System.err.println("#retained_heap_world_alive_bytes=-1");
            System.err.println("#retained_collection_count_delta=-1");
        }
        long period = 1_000_000_000L / hz;
        System.out.println("step,elapsed_ns,mutation_ns,lateness_ns,allocation_bytes,heap_used_bytes,rss_bytes,rss_delta_bytes,body_count,joint_count,awake_count,linear_speed_sum_m_per_s,angular_speed_sum_rad_per_s,contact_begins,contact_ends,toi_events,broadphase_candidates,active_contact_pairs,active_contact_points");
        int activeSteps = 0;
        long measuredWall;
        try (BufferedWriter clock = SustainedSidecars.clock("DYN4K_CLOCK_CSV", "step,begin_ns,end_ns")) {
        long start = System.nanoTime();
        for (int i = 0; i < steps; i++) {
            long deadline = start + period * i;
            long wait = deadline - System.nanoTime();
            if (wait > 0) LockSupport.parkNanos(wait);
            long lateness = Math.max(0L, System.nanoTime() - deadline);
            long allocatedBefore = probe == null ? -1 : probe.read();
            long stepStart = System.nanoTime();
            long mutation = measured.mutate(i);
            measured.world.step(1, 1.0 / hz);
            long stepEnd = System.nanoTime();
            long elapsed = stepEnd - stepStart;
            long allocatedAfter = probe == null ? -1 : probe.read();
            long allocated = probe == null ? -1 : allocatedAfter - allocatedBefore;
            SustainedSidecars.clockRow(clock, i, stepStart, stepEnd);
            if (probe != null) SustainedSidecars.allocation("measure", i, probe, allocatedBefore, allocatedAfter);
            int awake = 0;
            double linearSpeed = 0.0;
            double angularSpeed = 0.0;
            for (Body body : measured.dynamic) {
                if (!body.isAtRest()) awake++;
                Vector2 velocity = body.getLinearVelocity();
                linearSpeed += Math.hypot(velocity.x, velocity.y);
                angularSpeed += Math.abs(body.getAngularVelocity());
            }
            if (awake > 0) activeSteps++;
            long heap = Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory();
            long rss = rssBytes();
            long delta = rss < 0 || rssBase < 0 ? -1 : rss - rssBase;
            int candidates = -1;
            int activePairs = -1;
            int activePoints = -1;
            if (i % hz == 0 || i == steps - 1) {
                candidates = 0;
                Iterator<?> broadphase = measured.world.getBroadphaseDetector().detectIterator(true);
                while (broadphase.hasNext()) { broadphase.next(); candidates++; }
                activePairs = 0;
                activePoints = 0;
                Iterator<WorldCollisionData<Body>> collisions = measured.world.getCollisionDataIterator();
                while (collisions.hasNext()) {
                    WorldCollisionData<Body> collision = collisions.next();
                    if (collision.isContactConstraintCollision() && collision.getContactConstraint() != null) {
                        activePairs++;
                        activePoints += collision.getContactConstraint().getContacts().size();
                    }
                }
            }
            System.out.println(i + "," + elapsed + "," + mutation + "," + lateness + "," + allocated + "," + heap + "," + rss + "," + delta + "," + measured.world.getBodyCount() + "," + measured.world.getJointCount() + "," + awake + "," + linearSpeed + "," + angularSpeed + "," + measured.contactBegins + "," + measured.contactEnds + "," + measured.toiEvents + "," + candidates + "," + activePairs + "," + activePoints);
            SustainedSidecars.resource("measure", i, heap, rss, allocated);
            if (mode.equals("memory")) SustainedSidecars.memory("measure", i, heap, rss, -1);
        }
        measuredWall = System.nanoTime() - start;
        }
        java.lang.ref.Reference.reachabilityFence(measured);
        return new long[] { measuredWall, activeSteps };
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 7 && args.length != 8)
            throw new IllegalArgumentException("family variant size hz steps mode warmup_steps [api]");
        String family = args[0];
        String variant = args[1];
        String size = args[2];
        int hz = Integer.parseInt(args[3]);
        int steps = Integer.parseInt(args[4]);
        String mode = args[5];
        int warmup = Integer.parseInt(args[6]);
        String api = args.length == 7 ? "baseline" : args[7];
        if (!api.equals("baseline") && !api.equals("compatibility"))
            throw new IllegalArgumentException("unsupported API route");
        if (hz != 30 && hz != 60 && hz != 120) throw new IllegalArgumentException("unsupported rate");
        if (steps <= 0 || warmup < 0) throw new IllegalArgumentException("invalid step count");
        int count;
        switch (family) {
            case "separated": count = size.equals("small") ? 100 : size.equals("medium") ? 1000 : 10000; break;
            case "pile": count = size.equals("small") ? 100 : size.equals("medium") ? 500 : 2000; break;
            case "joint": count = size.equals("small") ? 50 : size.equals("medium") ? 250 : 1000; break;
            case "ccd": count = size.equals("small") ? 25 : size.equals("medium") ? 100 : 500; break;
            case "lifecycle": count = size.equals("small") ? 100 : size.equals("medium") ? 1000 : 5000; break;
            default: throw new IllegalArgumentException("unknown family");
        }
        if (!size.equals("small") && !size.equals("medium") && !size.equals("stress")) throw new IllegalArgumentException("unknown size");
        if (family.equals("lifecycle") && !List.of("settle", "wake", "replace").contains(variant)) throw new IllegalArgumentException("unknown lifecycle variant");
        if (!family.equals("joint") && !family.equals("lifecycle") && !variant.equals("default")) throw new IllegalArgumentException("unknown variant");
        SustainedSidecars.provider(api, World.class, SustainedPilot.class, null);
        SustainedSidecars.openResource();
        SustainedSidecars.openMemory(api, mode, family, variant, size, hz, steps, warmup);
        if (mode.equals("fixture_identity")) {
            if (steps != 1 || warmup != 0) throw new IllegalArgumentException("identity requires one step and no warm-up");
            new SustainedPilot(family, variant, count, hz).printCcdIdentity();
        } else if (mode.equals("plateau")) {
            SustainedSidecars.emptyHeap(Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory());
            try {
                plateau(family, variant, count, hz, warmup);
            } catch (InterruptedException exc) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("plateau interrupted", exc);
            }
        } else {
            SustainedSidecars.AllocationProbe probe = mode.equals("timing") ? null : SustainedSidecars.AllocationProbe.require();
            long rssBase = rssBytes();
            long emptyHeap = Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory();
            SustainedSidecars.emptyHeap(emptyHeap);
            SustainedSidecars.resource("empty", 0, emptyHeap, rssBase, -1);
            if (mode.equals("memory")) SustainedSidecars.memory("empty", 0, emptyHeap, rssBase, -1);
            long beforeAllocation = probe == null ? -1 : probe.read();
            long constructionStart = System.nanoTime();
            SustainedPilot fixture = new SustainedPilot(family, variant, count, hz);
            long constructionEnd = System.nanoTime();
            long afterAllocation = probe == null ? -1 : probe.read();
            System.err.println("#construction_ns=" + (constructionEnd - constructionStart));
            System.err.println("#construction_allocated_bytes=" + (probe == null ? -1 : afterAllocation - beforeAllocation));
            if (probe != null) SustainedSidecars.allocation("construction", 0, probe, beforeAllocation, afterAllocation);
            System.err.println("#rss_empty_harness_bytes=" + rssBase);
            System.err.println("#rss_after_construction_bytes=" + rssBytes());
            SustainedSidecars.resource("construction", 0,
                    Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory(), rssBytes(),
                    probe == null ? -1 : afterAllocation - beforeAllocation);
            if (mode.equals("memory")) SustainedSidecars.memory("construction", 0,
                    Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory(), rssBytes(), -1);
            fixture.warm(warmup, mode, probe);
            fixture = null;
            System.err.println("#fixture_reset_after_warmup=1");
            long[] result = run(family, variant, count, hz, steps, mode, rssBase, probe);
            SustainedSidecars.run(api, mode, steps, warmup, result[0], (int) result[1]);
        }
        SustainedSidecars.closeResource();
    }
}
