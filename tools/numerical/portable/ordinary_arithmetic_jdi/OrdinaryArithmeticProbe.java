import com.sun.jdi.Bootstrap;
import com.sun.jdi.DoubleValue;
import com.sun.jdi.Field;
import com.sun.jdi.Method;
import com.sun.jdi.ObjectReference;
import com.sun.jdi.ReferenceType;
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
import java.nio.file.StandardOpenOption;
import java.time.Duration;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class OrdinaryArithmeticProbe {
    private static final String TARGET = "org.dyn4j.geometry.Transform";
    private static final int CAP = 64;

    private record Pending(int ordinal, long thread, ObjectReference receiver,
                           String pre, String trig, String angle, String caller,
                           long callerIndex, long callerLoader, long started) { }

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
        if (!(value instanceof ObjectReference box) ||
            !box.referenceType().name().equals("java.lang.Double"))
            throw new IllegalStateException("Missing angle");
        return bits(box.getValue(box.referenceType().fieldByName("value")));
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
        Files.writeString(output.resolve("class.txt"), type.name() + "\n" +
            type.constantPoolCount() + "\n" +
            (type.classLoader() == null ? 0 : type.classLoader().uniqueID()) + "\n");
    }

    private static Pending entry(MethodEntryEvent event, int ordinal) throws Exception {
        List<StackFrame> frames = event.thread().frames();
        StackFrame frame = frames.get(0);
        List<Value> values = frame.getArgumentValues();
        if (values.size() != 5 || frame.thisObject() == null)
            throw new IllegalStateException("Unexpected pivot signature");
        ObjectReference receiver = frame.thisObject();
        StackFrame source = null;
        for (int index = 1; index < frames.size(); index++) {
            StackFrame candidate = frames.get(index);
            if (candidate.location().declaringType().name().equals(
                    "org.dyn4j.dynamics.AbstractPhysicsBody") &&
                candidate.location().method().name().equals("integratePosition$lambda$0")) {
                if (source != null) throw new IllegalStateException("Ambiguous source caller");
                source = candidate;
            }
        }
        if (source == null) throw new IllegalStateException("Missing source caller");
        List<Value> arguments = source.getArgumentValues();
        if (arguments.isEmpty() || !(arguments.get(0) instanceof ObjectReference body))
            throw new IllegalStateException("Missing source body");
        Field transform = body.referenceType().fieldByName("transform");
        if (transform == null || !(body.getValue(transform) instanceof ObjectReference value) ||
            value.uniqueID() != receiver.uniqueID())
            throw new IllegalStateException("Source receiver differs");
        long callerLoader = source.location().declaringType().classLoader().uniqueID();
        if (callerLoader != receiver.referenceType().classLoader().uniqueID())
            throw new IllegalStateException("Source class loader differs");
        return new Pending(ordinal, event.thread().uniqueID(), receiver, pair(receiver),
            bits(values.get(0)) + "\t" + bits(values.get(1)), boxedAngle(values.get(4)),
            "org.dyn4j.dynamics.AbstractPhysicsBody.integratePosition$lambda$0",
            source.location().codeIndex(), callerLoader, System.nanoTime());
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 5 || !args[0].equals("attach") ||
            !args[2].equals("127.0.0.1"))
            throw new IllegalArgumentException("Expected attach, output, host, port, deadline");
        int port = Integer.parseInt(args[3]);
        int seconds = Integer.parseInt(args[4]);
        if (port < 1 || port > 65535 || seconds < 1 || seconds > 600)
            throw new IllegalArgumentException("Invalid port or deadline");
        Path output = Path.of(args[1]);
        Files.createDirectory(output);
        var connector = Bootstrap.virtualMachineManager().attachingConnectors().stream()
            .filter(item -> item.name().equals("com.sun.jdi.SocketAttach")).findFirst()
            .orElseThrow();
        Map<String, Connector.Argument> options = connector.defaultArguments();
        options.get("hostname").setValue(args[2]);
        options.get("port").setValue(args[3]);
        VirtualMachine vm = connector.attach(options);
        long attach = System.nanoTime();
        Files.writeString(output.resolve("attach-ready.tsv"), "attached\t" + attach + "\n");
        ArrayList<String> rows = new ArrayList<>();
        ArrayList<String> lifecycle = new ArrayList<>();
        lifecycle.add("attach\t" + attach);
        Map<Long, ArrayDeque<Pending>> pending = new HashMap<>();
        int prepared = 0;
        int entered = 0;
        int exited = 0;
        boolean disposed = false;
        try {
            if (!vm.canGetBytecodes() || !vm.canGetConstantPool())
                throw new IllegalStateException("Target lacks loaded-code access");
            var requests = vm.eventRequestManager();
            var prepare = requests.createClassPrepareRequest();
            prepare.addClassFilter(TARGET);
            prepare.setSuspendPolicy(EventRequest.SUSPEND_ALL);
            prepare.enable();
            var entry = requests.createMethodEntryRequest();
            entry.addClassFilter(TARGET);
            entry.setSuspendPolicy(EventRequest.SUSPEND_ALL);
            entry.enable();
            var exit = requests.createMethodExitRequest();
            exit.addClassFilter(TARGET);
            exit.setSuspendPolicy(EventRequest.SUSPEND_ALL);
            exit.enable();
            lifecycle.add("armed\t" + System.nanoTime());
            vm.resume();
            long deadline = System.nanoTime() + Duration.ofSeconds(seconds).toNanos();
            boolean heldForDrain = false;
            while (exited < CAP) {
                long remaining = deadline - System.nanoTime();
                if (remaining <= 0) throw new IllegalStateException("JDI deadline");
                EventSet events = vm.eventQueue().remove(Math.max(1,
                    Math.min(Duration.ofNanos(remaining).toMillis(), 1000)));
                if (events == null) continue;
                try {
                    for (Event event : events) {
                        if (event instanceof ClassPrepareEvent item) {
                            if (++prepared != 1 || entered != 0 ||
                                !item.referenceType().name().equals(TARGET))
                                throw new IllegalStateException("Late or duplicate preparation");
                            captureCode(item.referenceType(), output);
                            lifecycle.add("class-prepared\t" + System.nanoTime());
                        } else if (event instanceof MethodEntryEvent item &&
                                   item.method().name().equals("rotatePivotObserved")) {
                            if (prepared != 1 || entered >= CAP)
                                throw new IllegalStateException("Excess pivot entry");
                            Pending call = entry(item, entered++);
                            if (entered == 1)
                                lifecycle.add("first-entry\t" + call.started());
                            pending.computeIfAbsent(call.thread(), ignored -> new ArrayDeque<>())
                                .push(call);
                            if (entered == CAP) {
                                lifecycle.add("cap-entry-reached\t" + System.nanoTime());
                                Files.writeString(output.resolve("cap-reached.tsv"),
                                    "64\t" + System.nanoTime() + "\n");
                            }
                        } else if (event instanceof MethodExitEvent item &&
                                   item.method().name().equals("rotatePivotObserved")) {
                            long thread = item.thread().uniqueID();
                            ArrayDeque<Pending> stack = pending.get(thread);
                            if (stack == null || stack.isEmpty())
                                throw new IllegalStateException("Unpaired pivot exit");
                            Pending call = stack.pop();
                            rows.add(call.ordinal() + "\t" + call.thread() + "\t" +
                                call.receiver().uniqueID() + "\t" + call.pre() + "\t" +
                                call.trig() + "\t" + pair(call.receiver()) + "\t" +
                                call.angle() + "\t" + call.caller() + "\t" +
                                call.callerIndex() + "\t" +
                                call.callerLoader() + "\t" +
                                (System.nanoTime() - call.started()));
                            Files.writeString(output.resolveSibling("progress.tsv"),
                                rows.get(rows.size() - 1) + "\n",
                                StandardOpenOption.CREATE, StandardOpenOption.APPEND);
                            exited++;
                        } else if (event instanceof VMDeathEvent ||
                                   event instanceof VMDisconnectEvent) {
                            throw new IllegalStateException("Worker ended before detach");
                        }
                    }
                    if (exited == CAP) {
                        if (entered != CAP || pending.values().stream().anyMatch(
                                stack -> !stack.isEmpty()))
                            throw new IllegalStateException("Incomplete cap sequence");
                        lifecycle.add("exits-drained\t" + System.nanoTime());
                        vm.suspend();
                        heldForDrain = true;
                        entry.disable();
                        exit.disable();
                        prepare.disable();
                        lifecycle.add("requests-disabled\t" + System.nanoTime());
                    }
                } finally {
                    events.resume();
                    if (exited == CAP)
                        lifecycle.add("event-set-resumed\t" + System.nanoTime());
                }
            }
            int drained = 0;
            while (true) {
                if (System.nanoTime() >= deadline || drained > 1024)
                    throw new IllegalStateException("CAP_SEQUENCE_UNBOUND");
                EventSet queued = vm.eventQueue().remove(100);
                if (queued == null) break;
                try {
                    for (Event event : queued) {
                        if (event instanceof MethodEntryEvent item &&
                                item.method().name().equals("rotatePivotObserved"))
                            throw new IllegalStateException("Excess pivot entry");
                        if (event instanceof MethodExitEvent item &&
                                item.method().name().equals("rotatePivotObserved"))
                            throw new IllegalStateException("Unpaired pivot exit");
                        if (event instanceof ClassPrepareEvent ||
                                event instanceof VMDeathEvent ||
                                event instanceof VMDisconnectEvent)
                            throw new IllegalStateException("CAP_SEQUENCE_UNBOUND");
                    }
                    drained++;
                } finally {
                    queued.resume();
                }
            }
            if (heldForDrain) vm.resume();
            Files.write(output.resolve("events.tsv"), rows);
            vm.dispose();
            disposed = true;
            lifecycle.add("disposed\t" + System.nanoTime());
            lifecycle.add("detach-complete\t" + System.nanoTime());
            Files.write(output.resolve("lifecycle.tsv"), lifecycle);
        } finally {
            if (!disposed) {
                try { vm.dispose(); } catch (Exception ignored) { }
            }
        }
    }
}
