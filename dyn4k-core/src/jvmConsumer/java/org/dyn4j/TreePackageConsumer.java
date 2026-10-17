package org.dyn4j;

public final class TreePackageConsumer {
    public static void main(String[] args) {
        BinarySearchTreeNode<Integer> node = new BinarySearchTreeNode<Integer>(3);
        if (node.getComparable() != 3 || node.isLeftChild()) throw new AssertionError("node");
        try { new BinarySearchTreeNode<Integer>(null); throw new AssertionError("node null"); }
        catch (org.dyn4j.exception.ArgumentNullException expected) {
            if (!"comparable cannot be null".equals(expected.getMessage())) throw new AssertionError("node message");
        }
        Extension extension = new Extension();
        extension.insert(2); extension.insert(1); extension.insert(3);
        if (extension.getMinimum() != 1 || extension.minimumCalls != 1) throw new AssertionError("package override");
        if (extension.root == null || extension.size != 3 || extension.get(3).getComparable() != 3)
            throw new AssertionError("package state");
        BinarySearchTreeIterator<Integer> iterator = new BinarySearchTreeIterator<Integer>(extension.root);
        if (iterator.next() != 1) throw new AssertionError("node iterator");
        System.out.println("TreePackageConsumer: 5 checks passed");
    }

    static final class Extension extends AVLTree<Integer> {
        int minimumCalls;
        @Override BinarySearchTreeNode<Integer> getMinimum(BinarySearchTreeNode<Integer> node) {
            minimumCalls++;
            return super.getMinimum(node);
        }
    }
}
