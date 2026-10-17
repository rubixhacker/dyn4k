import java.util.Iterator;
import org.dyn4j.AVLTree;
import org.dyn4j.BinarySearchTree;
import org.dyn4j.BinarySearchTreeSearchCriteria;
import org.dyn4j.Reference;
import org.dyn4j.Version;

public final class TreeConsumer {
    public static void main(String[] args) {
        BinarySearchTree<Integer> tree = new AVLTree<Integer>();
        for (int value : new int[] { 4, 2, 6, 1, 3, 5, 7 }) tree.insert(value);
        if (tree.size() != 7 || tree.getHeight() != 3 || !tree.isValid()) throw new AssertionError("insert");
        if (!"1,2,3,4,5,6,7".equals(join(tree.iterator()))) throw new AssertionError("order");
        if (!"3,4,5".equals(join(tree.subsetIterator(3, 5)))) throw new AssertionError("subset");
        if (!"7,6,5,4,3,2,1".equals(join(tree.reverseOrderIterator()))) throw new AssertionError("reverse");
        Iterator<Integer> iterator = tree.iterator();
        iterator.next();
        try { iterator.remove(); throw new AssertionError("iterator remove"); }
        catch (UnsupportedOperationException expected) { }
        if (!tree.remove(4) || tree.contains(4) || !tree.isValid()) throw new AssertionError("remove");
        if (tree.removeMinimum() != 1 || tree.removeMaximum() != 7) throw new AssertionError("extremes");
        Search search = tree.search(new Search());
        if (search.found != 5) throw new AssertionError("search");
        Reference<String> reference = new Reference<String>("first");
        reference.value = "second";
        if (!"second".equals(reference.toString())) throw new AssertionError("reference");
        if (!"6.0.0".equals(Version.getVersion())) throw new AssertionError("version");
        if (new AVLTree<Integer>().search(null) != null) throw new AssertionError("empty null search");
        try { tree.search(null); throw new AssertionError("occupied null search"); }
        catch (NullPointerException expected) { }
        if (!new Reference<Integer>(3).equals(new Reference<Integer>(3)) ||
            new Reference<Integer>(3).hashCode() != 3) throw new AssertionError("reference equality");
        try { new AVLTree<Integer>().iterator().next(); throw new AssertionError("iterator exhaustion"); }
        catch (java.util.NoSuchElementException expected) { }
        try { new AVLTree<Integer>().print(); throw new AssertionError("empty print"); }
        catch (ArrayIndexOutOfBoundsException expected) { }
        AVLTree<Integer> changing = new AVLTree<Integer>();
        changing.insert(2); changing.insert(1); changing.insert(3);
        Iterator<Integer> snapshotPath = changing.iterator();
        changing.insert(0);
        if (!"1,2,3".equals(join(snapshotPath))) throw new AssertionError("iterator mutation");
        if (!"0,1,2,3".equals(join(changing.iterator()))) throw new AssertionError("fresh iterator");
        BinarySearchTree<Key> keys = new AVLTree<Key>();
        keys.insert(new Key(2)); keys.insert(new Key(1));
        if (keys.getMinimum().number != 1) throw new AssertionError("generic bound");
        BinarySearchTree<Integer> override = new OverrideTree();
        override.insert(1);
        if (((OverrideTree) override).calls != 1) throw new AssertionError("subclass dispatch");
        System.out.println("TreeConsumer: 19 checks passed");
    }

    static String join(Iterator<Integer> iterator) {
        StringBuilder result = new StringBuilder();
        while (iterator.hasNext()) {
            if (result.length() > 0) result.append(',');
            result.append(iterator.next());
        }
        return result.toString();
    }

    static final class Search implements BinarySearchTreeSearchCriteria<Integer> {
        Integer found;
        public int evaluate(Integer value) {
            if (value == 5) found = value;
            return Integer.compare(5, value);
        }
    }

    static final class Key implements Comparable<Key> {
        final int number;
        Key(int number) { this.number = number; }
        public int compareTo(Key other) { return Integer.compare(number, other.number); }
    }

    static final class OverrideTree extends AVLTree<Integer> {
        int calls;
        @Override public boolean insert(Integer value) { calls++; return super.insert(value); }
    }
}
