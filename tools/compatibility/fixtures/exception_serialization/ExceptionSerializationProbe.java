import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.ObjectStreamClass;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import org.dyn4j.exception.*;

public final class ExceptionSerializationProbe {
    private static Throwable create(String name) {
        switch (name) {
            case "ArgumentNullException": return new ArgumentNullException("sample");
            case "CopyException": return new CopyException(String.class, Object.class);
            case "EmptyCollectionException": return new EmptyCollectionException("items");
            case "SameObjectException": return new SameObjectException("first", "second", "value");
            case "InvalidIndexException": return new InvalidIndexException(-2);
            case "ObjectAlreadyExistsException": return new ObjectAlreadyExistsException("item", "value", "owner");
            case "ObjectAlreadyOwnedException": return new ObjectAlreadyOwnedException("item", "value", "owner");
            case "NullElementException-index": return new NullElementException("items", 2);
            case "NullElementException-name": return new NullElementException("items");
            case "ValueOutOfRangeException-int": return new ValueOutOfRangeException("sample", -1);
            case "ValueOutOfRangeException-double": return new ValueOutOfRangeException("sample", -1.5);
            case "ValueOutOfRangeException-bound-int": return new ValueOutOfRangeException("sample", -1, "greater than", 0);
            case "ValueOutOfRangeException-bound-double": return new ValueOutOfRangeException("sample", -1.5, "greater than", 0.5);
            case "ValueOutOfRangeException-pair-int": return new ValueOutOfRangeException("first", -1, "greater than", "second", 0);
            case "ValueOutOfRangeException-pair-double": return new ValueOutOfRangeException("first", -1.5, "greater than", "second", 0.5);
            default: throw new AssertionError(name);
        }
    }

    private static void print(Throwable failure) {
        System.out.println("TYPE=" + failure.getClass().getName());
        System.out.println("MESSAGE=" + failure.getMessage());
        System.out.println("CAUSE=" + failure.getCause().getClass().getName() + ":" + failure.getCause().getMessage());
        if (failure.getSuppressed().length != 1) throw new AssertionError("suppressed count");
        Throwable suppressed = failure.getSuppressed()[0];
        System.out.println("SUPPRESSED=" + suppressed.getClass().getName() + ":" + suppressed.getMessage());
        if (failure.getStackTrace().length != 1) throw new AssertionError("stack count");
        StackTraceElement frame = failure.getStackTrace()[0];
        System.out.println("STACK=" + frame.getClassName() + ":" + frame.getMethodName() + ":" + frame.getFileName() + ":" + frame.getLineNumber());
    }

    public static void main(String[] args) throws Exception {
        if (args[0].equals("ids")) {
            for (String name : new String[] { "ArgumentNullException", "CopyException", "EmptyCollectionException", "SameObjectException", "InvalidIndexException", "ValueOutOfRangeException", "ObjectAlreadyExistsException", "ObjectAlreadyOwnedException", "NullElementException" }) {
                Class<?> type = Class.forName("org.dyn4j.exception." + name);
                Field field = type.getDeclaredField("serialVersionUID");
                int modifiers = field.getModifiers();
                if (field.getType() != long.class || !Modifier.isPrivate(modifiers) || !Modifier.isStatic(modifiers) || !Modifier.isFinal(modifiers)) throw new AssertionError(name + " field declaration");
                field.setAccessible(true);
                long expected = field.getLong(null);
                if (expected != ObjectStreamClass.lookup(type).getSerialVersionUID()) throw new AssertionError(name + " stream ID");
                System.out.println(name + "=" + expected);
            }
        } else if (args[0].equals("write")) {
            Throwable failure = create(args[2]);
            failure.initCause(new IllegalStateException("cause"));
            failure.addSuppressed(new IllegalArgumentException("suppressed"));
            failure.setStackTrace(new StackTraceElement[] { new StackTraceElement("Example", "run", "Example.java", 12) });
            try (ObjectOutputStream output = new ObjectOutputStream(new FileOutputStream(args[1]))) { output.writeObject(failure); }
            print(failure);
        } else if (args[0].equals("read")) {
            try (ObjectInputStream input = new ObjectInputStream(new FileInputStream(args[1]))) { print((Throwable) input.readObject()); }
        } else {
            throw new AssertionError(args[0]);
        }
    }
}
