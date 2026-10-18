package io.github.rubixhacker.dyn4k.optimized;

import android.app.Activity;
import android.os.Bundle;

public final class OptimizedActivity extends Activity {
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        String result;
        try {
            result = OptimizedConsumer.run();
        } catch (Throwable failure) {
            result = "FAIL:" + failure.getClass().getName() + ":" + failure.getMessage();
        }
        getSharedPreferences("journey", MODE_PRIVATE).edit().putString("result", result).commit();
    }
}
