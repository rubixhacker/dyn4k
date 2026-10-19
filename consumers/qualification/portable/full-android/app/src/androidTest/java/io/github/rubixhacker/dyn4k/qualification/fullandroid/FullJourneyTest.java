package io.github.rubixhacker.dyn4k.qualification.fullandroid;

import android.app.Instrumentation;
import android.os.Bundle;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.List;

public final class FullJourneyTest extends Instrumentation {
    @Override public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        start();
    }

    @Override public void onStart() {
        sendStatus(1, umbrella());
        try {
            List<String[]> cases = FullCorpusExecutor.runAll(getTargetContext());
            boolean failed = cases.isEmpty();
            for (String[] item : cases) {
                Bundle status = new Bundle();
                status.putString("dyn4k_case", item[0]);
                status.putString("dyn4k_status", item[1]);
                if (!item[2].isEmpty()) status.putString("dyn4k_stack", item[2]);
                sendStatus(0, status);
                if (!"PASSED".equals(item[1])) failed = true;
            }
            Bundle result = new Bundle();
            if (failed) {
                Bundle status = umbrella();
                status.putString("stack", "one or more installed cases failed");
                sendStatus(-2, status);
                result.putString("shortMsg", "installed full corpus failed");
                finish(0, result);
            } else {
                sendStatus(0, umbrella());
                result.putString("stream", "\nOK (1 test)\n");
                finish(-1, result);
            }
        } catch (Throwable failure) {
            Bundle status = umbrella();
            StringWriter stack = new StringWriter();
            failure.printStackTrace(new PrintWriter(stack));
            status.putString("stack", stack.toString());
            sendStatus(-2, status);
            Bundle result = new Bundle();
            result.putString("shortMsg", failure.toString());
            finish(0, result);
        }
    }

    private static Bundle umbrella() {
        Bundle status = new Bundle();
        status.putString("class", FullJourneyTest.class.getName());
        status.putString("test", "allInstalledCases");
        status.putInt("numtests", 1);
        return status;
    }
}
