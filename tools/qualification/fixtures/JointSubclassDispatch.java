package org.dyn4j.dynamics.joint;

import java.util.Collections;
import java.util.Iterator;
import org.dyn4j.AVLTree;
import org.dyn4j.dynamics.Body;
import org.dyn4j.geometry.Vector2;

public class JointSubclassDispatch {
    static class Angle extends AngleJoint<Body> {
        int calls;
        Angle() { super(new Body(), new Body()); }
        public void setLimits(double lower, double upper) { calls++; }
    }
    static class Revolute extends RevoluteJoint<Body> {
        int calls;
        Revolute() { super(new Body(), new Body(), new Vector2()); }
        public void setLimits(double lower, double upper) { calls++; }
    }
    static class Weld extends WeldJoint<Body> {
        int calls;
        Weld() { super(new Body(), new Body(), new Vector2()); }
        public void setLimits(double lower, double upper) { calls++; }
    }
    static class Pulley extends PulleyJoint<Body> {
        int firstCalls;
        int secondCalls;
        Pulley() { super(new Body(), new Body(), new Vector2(0, 3), new Vector2(4, 3), new Vector2(0, 0), new Vector2(4, 0)); }
        public double getCurrentLength1() { firstCalls++; return 100; }
        public double getCurrentLength2() { secondCalls++; return 200; }
    }
    static class Tree extends AVLTree<Integer> {
        int iteratorCalls;
        int inOrderCalls;
        public Iterator<Integer> iterator() { iteratorCalls++; return Collections.singletonList(777).iterator(); }
        public Iterator<Integer> inOrderIterator() { inOrderCalls++; return Collections.singletonList(888).iterator(); }
    }
    static void out(String key, Object value) { System.out.println(key + "=" + value); }
    static String limits(double lower, double upper, int calls) { return lower + "," + upper + ",calls=" + calls; }
    static String state(double lower, double upper, double offset, double adjustedLower, double adjustedUpper,
                        double lowerImpulse, double upperImpulse) {
        return lower + "," + upper + "," + offset + "," + adjustedLower + "," + adjustedUpper
            + "," + lowerImpulse + "," + upperImpulse;
    }
    static void angle() {
        Angle joint = new Angle();
        joint.setLimits(1);
        out("angle_single", limits(joint.getLowerLimit(), joint.getUpperLimit(), joint.calls));
        joint.setLimits(1);
        out("angle_noop", limits(joint.getLowerLimit(), joint.getUpperLimit(), joint.calls));
        joint.setLimitsEnabled(2);
        out("angle_enabled_single", limits(joint.getLowerLimit(), joint.getUpperLimit(), joint.calls) + ",enabled=" + joint.isLimitsEnabled());
        joint.setLimitsEnabled(3, 4);
        out("angle_enabled_pair", limits(joint.getLowerLimit(), joint.getUpperLimit(), joint.calls));
        joint.setLimits(5);
        out("angle_enabled_direct", limits(joint.getLowerLimit(), joint.getUpperLimit(), joint.calls));
        joint.setLimits(5);
        out("angle_enabled_noop", limits(joint.getLowerLimit(), joint.getUpperLimit(), joint.calls));
    }
    static void revolute() {
        Revolute joint = new Revolute();
        joint.setLimits(1);
        out("revolute_single", limits(joint.getLowerLimit(), joint.getUpperLimit(), joint.calls));
        joint.setLimits(1);
        out("revolute_noop", limits(joint.getLowerLimit(), joint.getUpperLimit(), joint.calls));
        joint.setLimitsEnabled(2);
        out("revolute_enabled_single", limits(joint.getLowerLimit(), joint.getUpperLimit(), joint.calls) + ",enabled=" + joint.isLimitsEnabled());
        joint.setLimitsEnabled(3, 4);
        out("revolute_enabled_pair", limits(joint.getLowerLimit(), joint.getUpperLimit(), joint.calls));
        joint.setLimits(5);
        out("revolute_enabled_direct", limits(joint.getLowerLimit(), joint.getUpperLimit(), joint.calls));
        joint.setLimits(5);
        out("revolute_enabled_noop", limits(joint.getLowerLimit(), joint.getUpperLimit(), joint.calls));
    }
    static void weld() {
        Weld joint = new Weld();
        joint.setLimits(1);
        out("weld_single", limits(joint.getLowerLimit(), joint.getUpperLimit(), joint.calls));
        joint.setLimits(1);
        out("weld_noop", limits(joint.getLowerLimit(), joint.getUpperLimit(), joint.calls));
        joint.setLimitsEnabled(2);
        out("weld_enabled_single", limits(joint.getLowerLimit(), joint.getUpperLimit(), joint.calls) + ",enabled=" + joint.isLimitsEnabled());
        joint.setLimitsEnabled(3, 4);
        out("weld_enabled_pair", limits(joint.getLowerLimit(), joint.getUpperLimit(), joint.calls));
        joint.setLimits(5);
        out("weld_enabled_direct", limits(joint.getLowerLimit(), joint.getUpperLimit(), joint.calls));
        joint.setLimits(5);
        out("weld_enabled_noop", limits(joint.getLowerLimit(), joint.getUpperLimit(), joint.calls));
    }
    static void angleState() {
        AngleJoint<Body> joint = new AngleJoint<>(new Body(), new Body());
        joint.setLimits(2.8, 3.5);
        joint.lowerLimitImpulse = 7;
        joint.upperLimitImpulse = 11;
        out("angle_state_before", state(joint.lowerLimit, joint.upperLimit, joint.limitOffset,
            joint.adjustedLowerLimit, joint.adjustedUpperLimit, joint.lowerLimitImpulse, joint.upperLimitImpulse));
        double priorOffset = joint.limitOffset;
        double priorLower = joint.adjustedLowerLimit;
        double priorUpper = joint.adjustedUpperLimit;
        joint.setLimits(1.25);
        if (Boolean.getBoolean("joint.state.skipReset")) {
            joint.lowerLimitImpulse = 7;
            joint.upperLimitImpulse = 11;
        }
        if (Boolean.getBoolean("joint.state.skipRecalculation")) {
            joint.limitOffset = priorOffset;
            joint.adjustedLowerLimit = priorLower;
            joint.adjustedUpperLimit = priorUpper;
        }
        out("angle_state_changed", state(joint.lowerLimit, joint.upperLimit, joint.limitOffset,
            joint.adjustedLowerLimit, joint.adjustedUpperLimit, joint.lowerLimitImpulse, joint.upperLimitImpulse));
        joint.lowerLimitImpulse = 13;
        joint.upperLimitImpulse = 17;
        joint.setLimits(1.25);
        out("angle_state_noop", state(joint.lowerLimit, joint.upperLimit, joint.limitOffset,
            joint.adjustedLowerLimit, joint.adjustedUpperLimit, joint.lowerLimitImpulse, joint.upperLimitImpulse));
    }
    static void revoluteState() {
        RevoluteJoint<Body> joint = new RevoluteJoint<>(new Body(), new Body(), new Vector2());
        joint.setLimits(2.8, 3.5);
        joint.lowerLimitImpulse = 7;
        joint.upperLimitImpulse = 11;
        out("revolute_state_before", state(joint.lowerLimit, joint.upperLimit, joint.limitOffset,
            joint.adjustedLowerLimit, joint.adjustedUpperLimit, joint.lowerLimitImpulse, joint.upperLimitImpulse));
        double priorOffset = joint.limitOffset;
        double priorLower = joint.adjustedLowerLimit;
        double priorUpper = joint.adjustedUpperLimit;
        joint.setLimits(1.25);
        if (Boolean.getBoolean("joint.state.skipReset")) {
            joint.lowerLimitImpulse = 7;
            joint.upperLimitImpulse = 11;
        }
        if (Boolean.getBoolean("joint.state.skipRecalculation")) {
            joint.limitOffset = priorOffset;
            joint.adjustedLowerLimit = priorLower;
            joint.adjustedUpperLimit = priorUpper;
        }
        out("revolute_state_changed", state(joint.lowerLimit, joint.upperLimit, joint.limitOffset,
            joint.adjustedLowerLimit, joint.adjustedUpperLimit, joint.lowerLimitImpulse, joint.upperLimitImpulse));
        joint.lowerLimitImpulse = 13;
        joint.upperLimitImpulse = 17;
        joint.setLimits(1.25);
        out("revolute_state_noop", state(joint.lowerLimit, joint.upperLimit, joint.limitOffset,
            joint.adjustedLowerLimit, joint.adjustedUpperLimit, joint.lowerLimitImpulse, joint.upperLimitImpulse));
    }
    static void weldState() {
        WeldJoint<Body> joint = new WeldJoint<>(new Body(), new Body(), new Vector2());
        joint.setLimits(2.8, 3.5);
        joint.lowerLimitImpulse = 7;
        joint.upperLimitImpulse = 11;
        out("weld_state_before", state(joint.lowerLimit, joint.upperLimit, joint.limitOffset,
            joint.adjustedLowerLimit, joint.adjustedUpperLimit, joint.lowerLimitImpulse, joint.upperLimitImpulse));
        double priorOffset = joint.limitOffset;
        double priorLower = joint.adjustedLowerLimit;
        double priorUpper = joint.adjustedUpperLimit;
        joint.setLimits(1.25);
        if (Boolean.getBoolean("joint.state.skipReset")) {
            joint.lowerLimitImpulse = 7;
            joint.upperLimitImpulse = 11;
        }
        if (Boolean.getBoolean("joint.state.skipRecalculation")) {
            joint.limitOffset = priorOffset;
            joint.adjustedLowerLimit = priorLower;
            joint.adjustedUpperLimit = priorUpper;
        }
        out("weld_state_changed", state(joint.lowerLimit, joint.upperLimit, joint.limitOffset,
            joint.adjustedLowerLimit, joint.adjustedUpperLimit, joint.lowerLimitImpulse, joint.upperLimitImpulse));
        joint.lowerLimitImpulse = 13;
        joint.upperLimitImpulse = 17;
        joint.setLimits(1.25);
        out("weld_state_noop", state(joint.lowerLimit, joint.upperLimit, joint.limitOffset,
            joint.adjustedLowerLimit, joint.adjustedUpperLimit, joint.lowerLimitImpulse, joint.upperLimitImpulse));
    }
    public static void main(String[] args) throws Exception {
        for (Class<?> type : new Class<?>[] {AngleJoint.class, RevoluteJoint.class, WeldJoint.class, PulleyJoint.class, AVLTree.class}) {
            out("provider_" + type.getSimpleName(), type.getProtectionDomain().getCodeSource().getLocation().toURI());
        }
        angle();
        revolute();
        weld();
        angleState();
        revoluteState();
        weldState();
        Pulley pulley = new Pulley();
        out("pulley_total", pulley.getCurrentLength() + ",componentCalls=" + pulley.firstCalls + "," + pulley.secondCalls);
        out("pulley_components", pulley.getCurrentLength1() + "," + pulley.getCurrentLength2() + ",componentCalls=" + pulley.firstCalls + "," + pulley.secondCalls);
        Tree tree = new Tree();
        tree.insert(1);
        out("tree_string", tree.toString() + ",iteratorCalls=" + tree.iteratorCalls + ",inOrderCalls=" + tree.inOrderCalls);
        out("tree_iterator", tree.iterator().next() + ",iteratorCalls=" + tree.iteratorCalls);
    }
}
