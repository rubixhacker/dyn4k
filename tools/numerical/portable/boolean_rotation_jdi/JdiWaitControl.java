public final class JdiWaitControl {
    static final class Rotation {
        private double cost = 1.0;
        private double sint;

        private void rotatePivotObserved(double c, double s, double x, double y,
                                         Double angle) {
            double oldCost = cost;
            double oldSint = sint;
            cost = c * oldCost - s * oldSint;
            sint = s * oldCost + c * oldSint;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) throw new IllegalArgumentException("Expected control mode");
        switch (args[0]) {
            case "normal" -> {
                Rotation rotation = new Rotation();
                for (int index = 0; index < 540; index++)
                    rotation.rotatePivotObserved(1.0, 0.0, 0.0, 0.0, 0.0);
            }
            case "idle" -> Thread.sleep(10_000);
            case "disconnect" -> Runtime.getRuntime().halt(0);
            default -> throw new IllegalArgumentException("Unknown control mode");
        }
    }
}
