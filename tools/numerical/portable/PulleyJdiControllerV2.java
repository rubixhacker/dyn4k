import com.sun.jdi.Bootstrap;
import com.sun.jdi.BooleanValue;
import com.sun.jdi.DoubleValue;
import com.sun.jdi.Field;
import com.sun.jdi.LocalVariable;
import com.sun.jdi.Location;
import com.sun.jdi.Method;
import com.sun.jdi.ObjectReference;
import com.sun.jdi.ReferenceType;
import com.sun.jdi.StackFrame;
import com.sun.jdi.VirtualMachine;
import com.sun.jdi.connect.Connector;
import com.sun.jdi.event.BreakpointEvent;
import com.sun.jdi.event.ClassPrepareEvent;
import com.sun.jdi.event.Event;
import com.sun.jdi.event.EventSet;
import com.sun.jdi.event.MethodEntryEvent;
import com.sun.jdi.event.VMDeathEvent;
import com.sun.jdi.event.VMDisconnectEvent;
import com.sun.jdi.request.EventRequest;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

public final class PulleyJdiControllerV2 {
    private static final String CLASS_NAME = "org.dyn4j.dynamics.joint.PulleyJoint";
    private static final String CASE_ID = "P-JINT-Pulley-slack-transition-preparation-0";

    private static void write(Path path, byte[] value) throws Exception {
        Files.write(path, value, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
    }

    private static void write(Path path, String value) throws Exception {
        write(path, value.getBytes(StandardCharsets.UTF_8));
    }

    private static double local(StackFrame frame, String name) throws Exception {
        LocalVariable variable = frame.visibleVariableByName(name);
        if (variable == null) throw new IllegalStateException("Pulley local is not visible: " + name);
        return ((DoubleValue) frame.getValue(variable)).value();
    }

    private static double number(ObjectReference self, String name) {
        Field field = self.referenceType().fieldByName(name);
        if (field == null) throw new IllegalStateException("Pulley field is absent: " + name);
        return ((DoubleValue) self.getValue(field)).value();
    }

    private static boolean flag(ObjectReference self, String name) {
        Field field = self.referenceType().fieldByName(name);
        if (field == null) throw new IllegalStateException("Pulley field is absent: " + name);
        return ((BooleanValue) self.getValue(field)).value();
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) throw new IllegalArgumentException("expected profile, classpath and output");
        String profile = args[0];
        int trueLine = profile.equals("baseline") ? 288 : 101;
        int falseLine = profile.equals("baseline") ? 336 : 120;
        if (!profile.equals("baseline") && !profile.equals("candidate"))
            throw new IllegalArgumentException("unknown Pulley profile");
        Path output = Path.of(args[2]).toRealPath();
        if (!Files.isDirectory(output) || Files.isSymbolicLink(output))
            throw new IllegalArgumentException("output is not a directory");
        String classpath = Files.readString(Path.of(args[1])).strip();
        if (classpath.isEmpty() || classpath.chars().anyMatch(Character::isWhitespace))
            throw new IllegalArgumentException("worker classpath is empty or needs quoting");
        String nonce = System.getenv("DYN4K_PULLEY_JDI_V1_NONCE");
        if (nonce == null || !nonce.matches("[0-9a-f]{64}"))
            throw new IllegalArgumentException("one-case nonce differs");
        if (!output.toString().equals(System.getenv("DYN4K_PULLEY_JDI_V1_OUTPUT")))
            throw new IllegalArgumentException("worker output binding differs");
        Path temporary = output.resolve("tmp");
        Files.createDirectories(temporary);
        var connector = Bootstrap.virtualMachineManager().defaultConnector();
        Map<String, Connector.Argument> options = connector.defaultArguments();
        options.get("main").setValue("org.junit.runner.JUnitCore portable.PulleyPreparationJdiV1Test");
        options.get("options").setValue("-cp " + classpath + " -Djava.io.tmpdir=" + temporary);
        options.get("suspend").setValue("true");
        VirtualMachine vm = connector.launch(options);
        Process child = vm.process();
        long controllerPid = ProcessHandle.current().pid();
        long childParentPid = child.toHandle().parent().orElseThrow().pid();
        int entries = 0;
        int breaks = 0;
        int classes = 0;
        long entryThread = -1;
        boolean died = false;
        String source = null;
        long loaderId = -1;
        String eventLine = null;
        try {
            if (!vm.canGetBytecodes() || !vm.canGetConstantPool())
                throw new IllegalStateException("JDI code inspection is unavailable");
            var prepare = vm.eventRequestManager().createClassPrepareRequest();
            prepare.addClassFilter(CLASS_NAME);
            prepare.setSuspendPolicy(EventRequest.SUSPEND_ALL);
            prepare.enable();
            vm.resume();
            long deadline = System.nanoTime() + Duration.ofSeconds(30).toNanos();
            while (!died && System.nanoTime() < deadline) {
                EventSet set = vm.eventQueue().remove(1000);
                if (set == null) continue;
                for (Event event : set) {
                    if (event instanceof ClassPrepareEvent prepared) {
                        ReferenceType type = prepared.referenceType();
                        if (++classes != 1) throw new IllegalStateException("duplicate Pulley class");
                        source = type.sourceName();
                        loaderId = type.classLoader().uniqueID();
                        write(output.resolve("constant-pool.bin"), type.constantPool());
                        StringBuilder methods = new StringBuilder();
                        int index = 0;
                        for (Method method : type.methods()) {
                            String file = "method-" + index++ + ".bin";
                            write(output.resolve(file), method.bytecodes());
                            methods.append(method.name()).append('\t').append(method.signature())
                                .append('\t').append(file).append('\n');
                        }
                        write(output.resolve("methods.tsv"), methods.toString());
                        var entry = vm.eventRequestManager().createMethodEntryRequest();
                        entry.addClassFilter(CLASS_NAME);
                        entry.setSuspendPolicy(EventRequest.SUSPEND_EVENT_THREAD);
                        entry.enable();
                        for (int line : new int[] {trueLine, falseLine}) {
                            List<Location> locations = type.locationsOfLine(line);
                            if (locations.size() != 1 ||
                                !locations.get(0).method().name().equals("initializeConstraints"))
                                throw new IllegalStateException("Pulley branch location differs");
                            var request = vm.eventRequestManager().createBreakpointRequest(locations.get(0));
                            request.setSuspendPolicy(EventRequest.SUSPEND_EVENT_THREAD);
                            request.enable();
                        }
                    } else if (event instanceof MethodEntryEvent entered &&
                               entered.method().name().equals("initializeConstraints")) {
                        entries++;
                        entryThread = entered.thread().uniqueID();
                    } else if (event instanceof BreakpointEvent hit) {
                        breaks++;
                        StackFrame frame = hit.thread().frame(0);
                        ObjectReference self = frame.thisObject();
                        int line = hit.location().lineNumber();
                        boolean branch = line == trueLine;
                        if (line != trueLine && line != falseLine)
                            throw new IllegalStateException("Pulley branch line differs");
                        eventLine = "{\"schema\":\"pulley-jdi-event/1\",\"sequence\":" + breaks +
                            ",\"pid\":" + child.pid() + ",\"case_id\":\"" + CASE_ID +
                            "\",\"step\":1,\"class_name\":\"" + CLASS_NAME +
                            "\",\"method\":\"initializeConstraints\",\"source_name\":\"" + source +
                            "\",\"line\":" + line + ",\"code_index\":" + hit.location().codeIndex() +
                            ",\"branch\":" + branch + ",\"l1\":" + local(frame, "l1") +
                            ",\"l2\":" + local(frame, "l2") + ",\"l\":" + local(frame, "l") +
                            ",\"length\":" + number(self, "length") +
                            ",\"ratio\":" + number(self, "ratio") +
                            ",\"slack_enabled\":" + flag(self, "slackEnabled") +
                            ",\"over_length\":" + flag(self, "overLength") + "}\n";
                        if (entries != breaks || hit.thread().uniqueID() != entryThread)
                            throw new IllegalStateException("Pulley entry and branch order differs");
                    } else if (event instanceof VMDeathEvent || event instanceof VMDisconnectEvent) {
                        died = true;
                    }
                }
                set.resume();
            }
            if (!died || !child.waitFor(5, TimeUnit.SECONDS))
                throw new IllegalStateException("one-case debuggee did not finish");
            write(output.resolve("target.stdout"), child.getInputStream().readAllBytes());
            write(output.resolve("target.stderr"), child.getErrorStream().readAllBytes());
            if (child.exitValue() != 0 || classes != 1 || entries != 1 || breaks != 1 ||
                eventLine == null || !source.equals(profile.equals("baseline") ?
                "PulleyJoint.java" : "PulleyJoint.kt"))
                throw new IllegalStateException("one-case Pulley observation is incomplete");
            write(output.resolve("events.jsonl"), eventLine);
            String process = "schema=pulley-jdi-process/2\ncontroller_pid=" + controllerPid +
                "\nworker_pid=" + child.pid() + "\nparent_pid=" +
                childParentPid + "\nentry_count=" + entries +
                "\nbreakpoint_count=" + breaks + "\nclass_count=" + classes +
                "\nclass_source_name=" + source + "\nclass_loader_id=" + loaderId +
                "\nexit_code=" + child.exitValue() + "\nnonce=" + nonce +
                "\njava_home=" + System.getProperty("java.home") + "\n";
            write(output.resolve("process.properties"), process);
        } finally {
            if (child.isAlive()) child.destroyForcibly();
        }
    }
}
