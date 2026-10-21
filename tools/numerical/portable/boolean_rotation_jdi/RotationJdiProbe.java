import com.sun.jdi.Bootstrap;
import com.sun.jdi.DoubleValue;
import com.sun.jdi.Field;
import com.sun.jdi.Location;
import com.sun.jdi.Method;
import com.sun.jdi.ObjectReference;
import com.sun.jdi.ReferenceType;
import com.sun.jdi.StackFrame;
import com.sun.jdi.StringReference;
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

public final class RotationJdiProbe {
    private record Pending(int ordinal, long thread, ObjectReference receiver, String pre,
                           String trig, String angle, String caller, long callerIndex) { }

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

    private static String[] caller(List<StackFrame> frames) {
        for (int index = 1; index < frames.size(); index++) {
            Location location = frames.get(index).location();
            String type = location.declaringType().name();
            if (type.equals("org.dyn4j.dynamics.AbstractPhysicsBody") &&
                location.method().name().equals("integrate"))
                return new String[] {type + ".integrate", Long.toString(location.codeIndex())};
            if (type.equals("org.dyn4j.dynamics.joint.RevoluteJoint") &&
                location.method().name().equals("solvePositionConstraints"))
                return new String[] {type + ".solvePositionConstraints",
                                     Long.toString(location.codeIndex())};
            if (type.equals("ToyRotation") &&
                (location.method().name().equals("integrate") ||
                 location.method().name().equals("solvePositionConstraints")))
                return new String[] {type + "." + location.method().name(),
                                     Long.toString(location.codeIndex())};
        }
        return new String[] {"UNBOUND", "-1"};
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
                          type.classLoader().uniqueID() + "\n");
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 6 || !(args[0].equals("launch") || args[0].equals("attach")))
            throw new IllegalArgumentException("Expected mode, output, target, main-or-port, class, count");
        Path output = Path.of(args[1]);
        Files.createDirectory(output);
        int expected = Integer.parseInt(args[5]);
        if (expected <= 0) throw new IllegalArgumentException("Expected positive count");
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
        boolean dead = false;
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
            entry.enable();
            var exit = requests.createMethodExitRequest();
            exit.addClassFilter(args[4]);
            exit.setSuspendPolicy(EventRequest.SUSPEND_ALL);
            exit.enable();
            vm.resume();
            long deadline = System.nanoTime() + Duration.ofSeconds(20).toNanos();
            while (!dead && System.nanoTime() < deadline) {
                EventSet events = vm.eventQueue().remove(500);
                if (events == null) continue;
                try {
                    for (Event event : events) {
                        if (event instanceof ClassPrepareEvent preparedEvent) {
                            if (++prepared != 1) throw new IllegalStateException("Duplicate class load");
                            captureCode(preparedEvent.referenceType(), output);
                        } else if (event instanceof MethodEntryEvent methodEvent &&
                                   methodEvent.method().name().equals("rotatePivotObserved")) {
                            List<StackFrame> frames = methodEvent.thread().frames();
                            StackFrame frame = frames.get(0);
                            List<Value> values = frame.getArgumentValues();
                            if (values.size() != 5 || frame.thisObject() == null)
                                throw new IllegalStateException("Unexpected rotation signature");
                            ObjectReference receiver = frame.thisObject();
                            String[] site = caller(frames);
                            long thread = methodEvent.thread().uniqueID();
                            Pending item = new Pending(entered++, thread, receiver, pair(receiver),
                                bits(values.get(0)) + "\t" + bits(values.get(1)),
                                boxedAngle(values.get(4)), site[0], Long.parseLong(site[1]));
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
                        } else if (event instanceof VMDeathEvent || event instanceof VMDisconnectEvent) {
                            dead = true;
                        }
                    }
                } finally {
                    events.resume();
                }
            }
            if (!dead || prepared != 1 || entered != expected || exited != expected ||
                pending.values().stream().anyMatch(stack -> !stack.isEmpty()))
                throw new IllegalStateException("Incomplete target observation");
            Files.write(output.resolve("events.tsv"), rows);
            Files.writeString(output.resolve("complete.txt"), "vm-death\n" +
                              (process == null ? "unbound" : process.pid()) + "\n" +
                              expected + "\n");
        } finally {
            if (process != null && process.isAlive()) process.destroyForcibly();
            try { vm.dispose(); } catch (Exception ignored) { }
        }
    }
}
