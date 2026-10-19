package io.github.rubixhacker.dyn4k.qualification.fullandroid;

import android.content.Context;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import org.junit.runner.JUnitCore;
import org.junit.runner.Request;
import org.junit.runner.Result;
import org.junit.runner.notification.Failure;

public final class FullCorpusExecutor {
    private FullCorpusExecutor() {}

    public static List<String[]> runAll(Context context) throws Exception {
        List<String[]> observations = new ArrayList<>();
        try (BufferedReader input = new BufferedReader(new InputStreamReader(
                context.getAssets().open("cases.tsv"), StandardCharsets.UTF_8))) {
            String row;
            while ((row = input.readLine()) != null) {
                String[] fields = row.split("\\t", -1);
                if (fields.length != 3 || fields[0].isEmpty() || fields[1].isEmpty() || fields[2].isEmpty()) {
                    throw new IllegalStateException("invalid installed case list");
                }
                try {
                    Class<?> target = Class.forName(fields[1], true, context.getClassLoader());
                    Result result = new JUnitCore().run(Request.method(target, fields[2]));
                    if (result.getRunCount() != 1 || result.getIgnoreCount() != 0 ||
                            result.getAssumptionFailureCount() != 0 || !result.wasSuccessful()) {
                        StringBuilder reason = new StringBuilder("run=").append(result.getRunCount())
                                .append(" ignored=").append(result.getIgnoreCount())
                                .append(" assumptions=").append(result.getAssumptionFailureCount());
                        for (Failure failure : result.getFailures()) reason.append('\n').append(failure.getTrace());
                        throw new AssertionError(reason.toString());
                    }
                    observations.add(new String[] {fields[0], "PASSED", ""});
                } catch (Throwable failure) {
                    StringWriter stack = new StringWriter();
                    failure.printStackTrace(new PrintWriter(stack));
                    observations.add(new String[] {fields[0], "FAILED", stack.toString()});
                }
            }
        }
        return observations;
    }
}
