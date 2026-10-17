package org.dyn4j.collision.broadphase;

public final class AddedPackageNodeAccessor extends DynamicAABBTreeNode {
    public String getLeft() {
        return "existing consumer method";
    }

    public static void main(String[] args) {
        if (!"existing consumer method".equals(new AddedPackageNodeAccessor().getLeft())) {
            throw new AssertionError();
        }
    }
}
