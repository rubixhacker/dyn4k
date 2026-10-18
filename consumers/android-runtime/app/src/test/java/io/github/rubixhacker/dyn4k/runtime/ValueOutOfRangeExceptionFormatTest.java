package io.github.rubixhacker.dyn4k.runtime;

import org.dyn4j.exception.ValueOutOfRangeException;
import org.junit.Test;

import static org.junit.Assert.assertEquals;

public final class ValueOutOfRangeExceptionFormatTest {
    @Test public void followsJvmFormatterAtHalfMicro() {
        double boundary = 5.0e-7;
        assertEquals(0x3ea0c6f7a0b5ed8dL, Double.doubleToRawLongBits(boundary));
        String baselineMessage = String.format("radius cannot be %f", boundary);
        assertEquals("radius cannot be 0.000001", baselineMessage);
        assertEquals(baselineMessage, new ValueOutOfRangeException("radius", boundary).getMessage());
    }

    @Test public void followsJvmFormatterAtMaximumDouble() {
        String baselineMessage = String.format("radius cannot be %f", Double.MAX_VALUE);
        assertEquals(baselineMessage,
            new ValueOutOfRangeException("radius", Double.MAX_VALUE).getMessage());
    }
}
