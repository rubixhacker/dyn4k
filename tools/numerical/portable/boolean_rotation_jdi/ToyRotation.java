public final class ToyRotation {
    private double cost = 1.0;
    private double sint = 0.0;

    private void rotatePivotObserved(double c, double s, double x, double y, Double angle) {
        double oldCost = cost;
        double oldSint = sint;
        cost = c * oldCost - s * oldSint;
        sint = s * oldCost + c * oldSint;
    }

    private void integrate() {
        rotatePivotObserved(1.0, 0.0, 0.0, 0.0, 0.0);
    }

    private void solvePositionConstraints() {
        rotatePivotObserved(1.0, 0.0, 0.0, 0.0, -0.0);
        rotatePivotObserved(1.0, 0.0, 0.0, 0.0, 0.0);
    }

    public static void main(String[] args) {
        ToyRotation body = new ToyRotation();
        body.integrate();
        body.solvePositionConstraints();
    }
}
