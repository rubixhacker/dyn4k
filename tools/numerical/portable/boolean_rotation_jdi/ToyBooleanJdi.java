public final class ToyBooleanJdi {
    static final class Rotation {
        private double cost = 1.0;
        private double sint = 0.0;

        private void rotatePivotObserved(double c, double s, double x, double y,
                                         Double angle) {
            double oldCost = cost;
            double oldSint = sint;
            cost = c * oldCost - s * oldSint;
            sint = s * oldCost + c * oldSint;
        }
    }

    static final class Body {
        private final Rotation transform = new Rotation();
    }

    static final class Joint {
        private final Body body1;
        private final Body body2;

        private Joint(Body body1, Body body2) {
            this.body1 = body1;
            this.body2 = body2;
        }

        private void solvePositionConstraints() {
            body1.transform.rotatePivotObserved(1.0, 0.0, 0.0, 0.0, -0.0);
            body2.transform.rotatePivotObserved(1.0, 0.0, 0.0, 0.0, 0.0);
        }
    }

    private static void integratePosition$lambda$0(Body body, double angle) {
        body.transform.rotatePivotObserved(1.0, 0.0, 0.0, 0.0, angle);
    }

    public static void main(String[] args) {
        Body ground = new Body();
        Body moving = new Body();
        Joint joint = new Joint(ground, moving);
        integratePosition$lambda$0(moving, 0.0);
        joint.solvePositionConstraints();
    }
}
