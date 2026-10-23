import com.sun.jdi.Bootstrap;
import com.sun.jdi.DoubleValue;
import com.sun.jdi.Field;
import com.sun.jdi.IntegerValue;
import com.sun.jdi.Location;
import com.sun.jdi.Method;
import com.sun.jdi.ObjectReference;
import com.sun.jdi.ReferenceType;
import com.sun.jdi.StringReference;
import com.sun.jdi.StackFrame;
import com.sun.jdi.Value;
import com.sun.jdi.VirtualMachine;
import com.sun.jdi.connect.Connector;
import com.sun.jdi.event.ClassPrepareEvent;
import com.sun.jdi.event.Event;
import com.sun.jdi.event.EventSet;
import com.sun.jdi.event.MethodEntryEvent;
import com.sun.jdi.event.MethodExitEvent;
import com.sun.jdi.event.VMDeathEvent;
import com.sun.jdi.event.VMDisconnectEvent;
import com.sun.jdi.request.EventRequest;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public final class RotationJdiProbe {
    private record Pending(int ordinal, long thread, ObjectReference receiver, String pre,
                           String trig, String angle, String caller, long callerIndex) { }
    private record Site(String caller, long index, long integrated, long body1, long body2) { }

    private static String bits(Value value) {
        if (!(value instanceof DoubleValue number)) throw new IllegalStateException("Expected double");
        return String.format("%016x", Double.doubleToRawLongBits(number.value()));
    }

    private static String pair(ObjectReference object) {
        ReferenceType type = object.referenceType();
        Field cost = type.fieldByName("cost");
        Field sint = type.fieldByName("sint");
        if (cost == null || sint == null) throw new IllegalStateException("Missing rotation fields");
        return bits(object.getValue(cost)) + "\t" + bits(object.getValue(sint));
    }

    private static String boxedAngle(Value value) {
        if (!(value instanceof ObjectReference box)) throw new IllegalStateException("Missing angle");
        if (!box.referenceType().name().equals("java.lang.Double"))
            throw new IllegalStateException("Unexpected angle type");
        return bits(box.getValue(box.referenceType().fieldByName("value")));
    }

    private static ObjectReference objectField(ObjectReference object, String name) {
        Field field = object.referenceType().fieldByName(name);
        if (field == null || !(object.getValue(field) instanceof ObjectReference value))
            throw new IllegalStateException("Missing source body field");
        return value;
    }

    private static long transformId(ObjectReference body) {
        return objectField(body, "transform").uniqueID();
    }

    private static Site caller(List<StackFrame> frames) {
        for (int index = 1; index < frames.size(); index++) {
            StackFrame frame = frames.get(index);
            Location location = frame.location();
            String type = location.declaringType().name();
            String name = location.method().name();
            if ((type.equals("org.dyn4j.dynamics.AbstractPhysicsBody") &&
                 name.equals("integratePosition$lambda$0")) ||
                (type.equals("ToyBooleanJdi") && name.equals("integratePosition$lambda$0"))) {
                List<Value> arguments = frame.getArgumentValues();
                if (arguments.isEmpty() || !(arguments.get(0) instanceof ObjectReference body))
                    throw new IllegalStateException("Missing integration body");
                return new Site(type + "." + name, location.codeIndex(),
                                transformId(body), -1, -1);
            }
            if ((type.equals("org.dyn4j.dynamics.joint.RevoluteJoint") ||
                 type.equals("ToyBooleanJdi$Joint")) &&
                name.equals("solvePositionConstraints")) {
                ObjectReference joint = frame.thisObject();
                if (joint == null) throw new IllegalStateException("Missing source joint");
                return new Site(type + "." + name, location.codeIndex(), -1,
                                transformId(objectField(joint, "body1")),
                                transformId(objectField(joint, "body2")));
            }
            if (type.equals("ToyRotation") &&
                (name.equals("integrate") || name.equals("solvePositionConstraints")))
                return new Site(type + "." + name, location.codeIndex(), -1, -1, -1);
        }
        return new Site("UNBOUND", -1, -1, -1, -1);
    }

    private static void captureCode(ReferenceType type, Path output) throws Exception {
        Files.write(output.resolve("constant-pool.bin"), type.constantPool());
        ArrayList<String> methods = new ArrayList<>();
        int index = 0;
        for (Method method : type.methods()) {
            String file = "method-" + index++ + ".bin";
            Files.write(output.resolve(file), method.bytecodes());
            methods.add(method.name() + "\t" + method.signature() + "\t" + file);
        }
        Files.write(output.resolve("methods.tsv"), methods);
        Files.writeString(output.resolve("class.txt"),
                          type.name() + "\n" + type.constantPoolCount() + "\n" +
                          (type.classLoader() == null ? 0 : type.classLoader().uniqueID()) + "\n");
    }

    private static void captureLoaderBridge(VirtualMachine vm, ReferenceType transform,
                                            Path output) throws Exception {
        List<ReferenceType> agents = vm.classesByName("dyn4k.witness.NumericClassWitness");
        if (agents.size() != 1) throw new IllegalStateException("Agent type is not unique");
        ReferenceType agent = agents.get(0);
        Field loaderField = agent.fieldByName("focusedTransformLoader");
        Field labelField = agent.fieldByName("focusedTransformLabel");
        Field ordinalField = agent.fieldByName("focusedTransformOrdinal");
        if (loaderField == null || labelField == null || ordinalField == null ||
            !(agent.getValue(labelField) instanceof StringReference label) ||
            !(agent.getValue(ordinalField) instanceof IntegerValue ordinal) ||
            agent.classLoader() == null)
            throw new IllegalStateException("Agent loader bridge is missing");
        Value observed = agent.getValue(loaderField);
        long transformId = transform.classLoader() == null ? 0 :
                           transform.classLoader().uniqueID();
        long observedId = observed == null ? 0 :
                          observed instanceof ObjectReference object ? object.uniqueID() : -1;
        if (transformId != observedId || ordinal.value() < 1)
            throw new IllegalStateException("Transform loader object differs");
        Path agentCode = output.resolve("agent-code");
        Files.createDirectory(agentCode);
        captureCode(agent, agentCode);
        Files.writeString(output.resolve("loader.tsv"),
                          "transform\t" + transformId + "\n" +
                          "observed\t" + observedId + "\n" +
                          "agent\t" + agent.classLoader().uniqueID() + "\n" +
                          "label\t" + label.value() + "\n" +
                          "ordinal\t" + ordinal.value() + "\n" +
                          "provider_count\t" + agents.size() + "\n");
    }

    static String terminalEvent(Event event) {
        if (event instanceof VMDeathEvent) return "vm-death";
        if (event instanceof VMDisconnectEvent) return "vm-disconnect";
        return null;
    }

    public static void main(String[] args) throws Exception {
        boolean loaderOnly = args.length == 6 && args[0].equals("attach-loader");
        if ((args.length != 6 && args.length != 7) ||
            !(args[0].equals("launch") || args[0].equals("attach") || loaderOnly))
            throw new IllegalArgumentException("Expected mode, output, target, main-or-port, class, count");
        Path output = Path.of(args[1]);
        Files.createDirectory(output);
        int expected = Integer.parseInt(args[5]);
        if (expected < 0 || (expected == 0 && !loaderOnly) ||
            (expected > 0 && loaderOnly))
            throw new IllegalArgumentException("Expected positive count");
        int deadlineSeconds = args.length == 7 ? Integer.parseInt(args[6]) : 20;
        if (deadlineSeconds < 1 || deadlineSeconds > 600)
            throw new IllegalArgumentException("Invalid observation deadline");
        boolean requireBodyMap = args[4].equals("org.dyn4j.geometry.Transform") ||
                                 args[4].equals("ToyBooleanJdi$Rotation");
        VirtualMachine vm;
        Process process = null;
        if (args[0].equals("launch")) {
            Connector connector = Bootstrap.virtualMachineManager().defaultConnector();
            Map<String, Connector.Argument> options = connector.defaultArguments();
            options.get("main").setValue(args[3]);
            options.get("options").setValue("-cp " + args[2] + " -Djava.io.tmpdir=" + output);
            options.get("suspend").setValue("true");
            vm = ((com.sun.jdi.connect.LaunchingConnector) connector).launch(options);
            process = vm.process();
        } else {
            var connector = Bootstrap.virtualMachineManager().attachingConnectors().stream()
                .filter(item -> item.name().equals("com.sun.jdi.SocketAttach")).findFirst()
                .orElseThrow();
            Map<String, Connector.Argument> options = connector.defaultArguments();
            options.get("hostname").setValue(args[2]);
            options.get("port").setValue(args[3]);
            vm = connector.attach(options);
        }
        ArrayList<String> rows = new ArrayList<>();
        Map<Long, ArrayDeque<Pending>> pending = new HashMap<>();
        int prepared = 0;
        int entered = 0;
        int exited = 0;
        String endpoint = null;
        long body1 = -1;
        long body2 = -1;
        long integrated = -1;
        ExecutorService reader = Executors.newSingleThreadExecutor(task -> {
            Thread thread = new Thread(task, "jdi-event-reader");
            thread.setDaemon(true);
            return thread;
        });
        try {
            if (!vm.canGetBytecodes() || !vm.canGetConstantPool())
                throw new IllegalStateException("Target lacks loaded-code access");
            var requests = vm.eventRequestManager();
            var prepare = requests.createClassPrepareRequest();
            prepare.addClassFilter(args[4]);
            prepare.setSuspendPolicy(EventRequest.SUSPEND_ALL);
            prepare.enable();
            var entry = requests.createMethodEntryRequest();
            entry.addClassFilter(args[4]);
            entry.setSuspendPolicy(EventRequest.SUSPEND_ALL);
            if (!loaderOnly) entry.enable();
            var exit = requests.createMethodExitRequest();
            exit.addClassFilter(args[4]);
            exit.setSuspendPolicy(EventRequest.SUSPEND_ALL);
            if (!loaderOnly) exit.enable();
            vm.resume();
            long deadline = System.nanoTime() + Duration.ofSeconds(deadlineSeconds).toNanos();
            while (endpoint == null) {
                long remaining = deadline - System.nanoTime();
                if (remaining <= 0) break;
                Future<EventSet> waiting = reader.submit(() -> vm.eventQueue().remove());
                EventSet events;
                try {
                    events = waiting.get(remaining, TimeUnit.NANOSECONDS);
                } catch (TimeoutException error) {
                    waiting.cancel(true);
                    break;
                } catch (ExecutionException error) {
                    throw new IllegalStateException("JDI event reader failed", error.getCause());
                }
                if (events == null) continue;
                try {
                    for (Event event : events) {
                        if (event instanceof ClassPrepareEvent preparedEvent) {
                            if (++prepared != 1) throw new IllegalStateException("Duplicate class load");
                            captureCode(preparedEvent.referenceType(), output);
                            if (args[4].equals("org.dyn4j.geometry.Transform"))
                                captureLoaderBridge(vm, preparedEvent.referenceType(), output);
                            if (loaderOnly) endpoint = "loader-ready";
                        } else if (event instanceof MethodEntryEvent methodEvent &&
                                   methodEvent.method().name().equals("rotatePivotObserved")) {
                            List<StackFrame> frames = methodEvent.thread().frames();
                            StackFrame frame = frames.get(0);
                            List<Value> values = frame.getArgumentValues();
                            if (values.size() != 5 || frame.thisObject() == null)
                                throw new IllegalStateException("Unexpected rotation signature");
                            ObjectReference receiver = frame.thisObject();
                            Site site = caller(frames);
                            if (requireBodyMap && site.caller().equals("UNBOUND"))
                                throw new IllegalStateException("Source call site is unbound");
                            if (site.integrated() > 0) {
                                if ((integrated > 0 && integrated != site.integrated()) ||
                                    receiver.uniqueID() != site.integrated())
                                    throw new IllegalStateException("Integration body differs");
                                integrated = site.integrated();
                            }
                            if (site.body1() > 0) {
                                if ((body1 > 0 && body1 != site.body1()) ||
                                    (body2 > 0 && body2 != site.body2()) ||
                                    (receiver.uniqueID() != site.body1() &&
                                     receiver.uniqueID() != site.body2()))
                                    throw new IllegalStateException("Joint body relationship differs");
                                body1 = site.body1();
                                body2 = site.body2();
                            }
                            long thread = methodEvent.thread().uniqueID();
                            Pending item = new Pending(entered++, thread, receiver, pair(receiver),
                                bits(values.get(0)) + "\t" + bits(values.get(1)),
                                boxedAngle(values.get(4)), site.caller(), site.index());
                            pending.computeIfAbsent(thread, ignored -> new ArrayDeque<>()).push(item);
                        } else if (event instanceof MethodExitEvent methodEvent &&
                                   methodEvent.method().name().equals("rotatePivotObserved")) {
                            long thread = methodEvent.thread().uniqueID();
                            ArrayDeque<Pending> stack = pending.get(thread);
                            if (stack == null || stack.isEmpty())
                                throw new IllegalStateException("Unpaired method exit");
                            Pending item = stack.pop();
                            rows.add(item.ordinal() + "\t" + item.thread() + "\t" +
                                item.receiver().uniqueID() + "\t" + item.pre() + "\t" +
                                item.trig() + "\t" + pair(item.receiver()) + "\t" +
                                item.angle() + "\t" + item.caller() + "\t" +
                                item.callerIndex());
                            exited++;
                        } else {
                            String observed = terminalEvent(event);
                            if (observed != null && !"vm-death".equals(endpoint))
                                endpoint = observed;
                        }
                    }
                } finally {
                    events.resume();
                }
            }
            if (!(loaderOnly ? "loader-ready".equals(endpoint) :
                  "vm-death".equals(endpoint)) || prepared != 1 ||
                entered != expected || exited != expected ||
                pending.values().stream().anyMatch(stack -> !stack.isEmpty()))
                throw new IllegalStateException("Incomplete target observation");
            if (requireBodyMap && !loaderOnly) {
                if (body1 <= 0 || body2 <= 0 || integrated != body2 || body1 == body2)
                    throw new IllegalStateException("Source body map is incomplete");
                Files.writeString(output.resolve("body-map.tsv"), "b0\t" + body1 +
                                  "\nb1\t" + body2 + "\nintegrated\t" + integrated + "\n");
            }
            Files.write(output.resolve("events.tsv"), rows);
            Files.writeString(output.resolve("complete.txt"), endpoint + "\n" +
                              (process == null ? "unbound" : process.pid()) + "\n" +
                              expected + "\n");
        } finally {
            reader.shutdownNow();
            if (process != null && process.isAlive()) process.destroyForcibly();
            try { vm.dispose(); } catch (Exception ignored) { }
        }
    }
}
