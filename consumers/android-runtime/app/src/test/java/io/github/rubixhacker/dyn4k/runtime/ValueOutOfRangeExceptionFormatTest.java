package io.github.rubixhacker.dyn4k.runtime;

import org.dyn4j.exception.ValueOutOfRangeException;
import org.junit.Test;
import java.util.Locale;

import static org.junit.Assert.assertEquals;

public final class ValueOutOfRangeExceptionFormatTest {
    @Test public void followsJvmFormatterAtHalfMicro() {
        Locale original = Locale.getDefault();
        try {
            Locale.setDefault(Locale.US);
            double boundary = 5.0e-7;
            assertEquals(0x3ea0c6f7a0b5ed8dL, Double.doubleToRawLongBits(boundary));
            String baselineMessage = String.format("radius cannot be %f", boundary);
            assertEquals("radius cannot be 0.000001", baselineMessage);
            assertEquals(baselineMessage, new ValueOutOfRangeException("radius", boundary).getMessage());
        } finally {
            Locale.setDefault(original);
        }
    }

    @Test public void followsJvmFormatterAtMaximumDouble() {
        String baselineMessage = String.format("radius cannot be %f", Double.MAX_VALUE);
        assertEquals(baselineMessage,
            new ValueOutOfRangeException("radius", Double.MAX_VALUE).getMessage());
    }

    @Test public void followsFrenchDoubleConstructors() {
        Locale original = Locale.getDefault();
        try {
            Locale.setDefault(Locale.FRANCE);
            assertEquals("radius cannot be 1,250000",
                new ValueOutOfRangeException("radius", 1.25).getMessage());
            assertEquals("1,250000 was supplied for radius: radius must be greater than 2,500000",
                new ValueOutOfRangeException("radius", 1.25, "greater than", 2.5).getMessage());
            assertEquals("width must be greater than height: width was 1,250000 and height was 2,500000",
                new ValueOutOfRangeException("width", 1.25, "greater than", "height", 2.5).getMessage());
        } finally {
            Locale.setDefault(original);
        }
    }

    @Test public void followsArabicEgyptianConstructors() {
        Locale original = Locale.getDefault();
        try {
            Locale.setDefault(Locale.forLanguageTag("ar-EG"));
            assertEquals(String.format("radius cannot be %f", 1.25),
                new ValueOutOfRangeException("radius", 1.25).getMessage());
            assertEquals(String.format("%f was supplied for radius: radius must be greater than %f", 1.25, 2.5),
                new ValueOutOfRangeException("radius", 1.25, "greater than", 2.5).getMessage());
            assertEquals(String.format("width must be greater than height: width was %f and height was %f", 1.25, 2.5),
                new ValueOutOfRangeException("width", 1.25, "greater than", "height", 2.5).getMessage());
            assertEquals("\u0661\u0662\u0663\u0664", String.format("%d", 1234));
            assertEquals(String.format("count cannot be %d", 1234),
                new ValueOutOfRangeException("count", 1234).getMessage());
            assertEquals(String.format("%d was supplied for count: count must be greater than %d", 1234, 2345),
                new ValueOutOfRangeException("count", 1234, "greater than", 2345).getMessage());
            assertEquals(String.format("first must be greater than second: first was %d and second was %d", 1234, 2345),
                new ValueOutOfRangeException("first", 1234, "greater than", "second", 2345).getMessage());
        } finally {
            Locale.setDefault(original);
        }
    }
}
