import probe.Vector;
public final class Consumer {
    public static void main(String[] args) {
        double result = new Vector(2.0, 3.0).dot(new Vector(4.0, 5.0));
        if (result != 23.0) throw new AssertionError(result);
        System.out.println("external Java consumer: 23.0");
    }
}
