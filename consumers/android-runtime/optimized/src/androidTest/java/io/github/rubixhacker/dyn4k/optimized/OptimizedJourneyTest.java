package io.github.rubixhacker.dyn4k.optimized;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import java.io.PrintWriter;
import java.io.StringWriter;

public final class OptimizedJourneyTest extends Instrumentation {
    @Override public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        start();
    }

    @Override public void onStart() {
        Bundle started = caseStatus();
        sendStatus(1, started);
        try {
            appSideWorldAndSubclassCallbacks();
            sendStatus(0, caseStatus());
            Bundle result = new Bundle();
            result.putString("stream", "\nOK (1 test)\n");
            finish(-1, result);
        } catch (Throwable failure) {
            Bundle failed = caseStatus();
            StringWriter trace = new StringWriter();
            failure.printStackTrace(new PrintWriter(trace));
            failed.putString("stack", trace.toString());
            sendStatus(-2, failed);
            Bundle result = new Bundle();
            result.putString("shortMsg", failure.toString());
            finish(0, result);
        }
    }

    private static Bundle caseStatus() {
        Bundle status = new Bundle();
        status.putString("class", OptimizedJourneyTest.class.getName());
        status.putString("test", "appSideWorldAndSubclassCallbacks");
        status.putInt("numtests", 1);
        return status;
    }

    private void appSideWorldAndSubclassCallbacks() {
        Context context = getTargetContext();
        context.getSharedPreferences("journey", 0).edit().clear().commit();
        Intent intent = new Intent(context, OptimizedActivity.class);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        Activity activity = startActivitySync(intent);
        String result = context.getSharedPreferences("journey", 0).getString("result", null);
        if (!"PASS:vector,body,world,subclass;steps=120".equals(result)) {
            throw new AssertionError("installed app result: " + result);
        }
        activity.finish();
    }
}
