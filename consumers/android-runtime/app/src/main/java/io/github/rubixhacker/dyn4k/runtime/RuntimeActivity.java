package io.github.rubixhacker.dyn4k.runtime;

import android.app.Activity;
import android.os.Bundle;
import org.dyn4j.geometry.Vector2;

public final class RuntimeActivity extends Activity {
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        if (new Vector2(3.0, 4.0).getMagnitude() != 5.0) {
            throw new AssertionError("staged runtime vector");
        }
    }
}
