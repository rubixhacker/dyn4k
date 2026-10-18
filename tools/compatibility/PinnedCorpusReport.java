import java.io.FileOutputStream;
import java.util.ArrayList;
import java.util.List;
import javax.xml.stream.XMLOutputFactory;
import javax.xml.stream.XMLStreamWriter;
import org.junit.runner.Description;
import org.junit.runner.JUnitCore;
import org.junit.runner.Result;
import org.junit.runner.notification.Failure;
import org.junit.runner.notification.RunListener;

public final class PinnedCorpusReport {
    private static final class Case {
        final String className;
        final String name;
        String status = "passed";
        String detail = "";

        Case(Description description) {
            className = description.getClassName() == null ? "unknown" : description.getClassName();
            name = description.getMethodName() == null ? description.getDisplayName() : description.getMethodName();
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 2) throw new IllegalArgumentException("XML path and test classes required");
        List<Case> cases = new ArrayList<Case>();
        JUnitCore core = new JUnitCore();
        core.addListener(new RunListener() {
            private Case active;

            @Override public void testStarted(Description description) {
                active = new Case(description);
                cases.add(active);
            }

            @Override public void testFailure(Failure failure) {
                if (active != null) {
                    active.status = "failure";
                    active.detail = failure.getTrace();
                }
            }

            @Override public void testAssumptionFailure(Failure failure) {
                if (active != null) {
                    active.status = "skipped";
                    active.detail = failure.getTrace();
                }
            }

            @Override public void testIgnored(Description description) {
                Case ignored = new Case(description);
                ignored.status = "skipped";
                cases.add(ignored);
            }

            @Override public void testFinished(Description description) {
                active = null;
            }
        });
        Class<?>[] classes = new Class<?>[args.length - 1];
        for (int index = 1; index < args.length; index++) classes[index - 1] = Class.forName(args[index]);
        Result result = core.run(classes);
        XMLStreamWriter xml = XMLOutputFactory.newFactory().createXMLStreamWriter(new FileOutputStream(args[0]), "UTF-8");
        xml.writeStartDocument("UTF-8", "1.0");
        xml.writeStartElement("testsuite");
        xml.writeAttribute("tests", Integer.toString(result.getRunCount()));
        xml.writeAttribute("failures", Integer.toString(result.getFailureCount()));
        xml.writeAttribute("errors", "0");
        xml.writeAttribute("skipped", Integer.toString(result.getIgnoreCount()));
        for (Case entry : cases) {
            xml.writeStartElement("testcase");
            xml.writeAttribute("classname", entry.className);
            xml.writeAttribute("name", entry.name);
            if (!entry.status.equals("passed")) {
                xml.writeStartElement(entry.status);
                xml.writeCharacters(entry.detail);
                xml.writeEndElement();
            }
            xml.writeEndElement();
        }
        xml.writeEndElement();
        xml.writeEndDocument();
        xml.close();
        System.out.println("ACTUAL_TESTS=" + result.getRunCount());
        System.out.println("FAILURES=" + result.getFailureCount());
        System.out.println("IGNORED=" + result.getIgnoreCount());
        if (!result.wasSuccessful() || result.getIgnoreCount() != 0) System.exit(1);
    }
}
