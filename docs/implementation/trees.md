# Baseline tree port

The `dyn4k-core` common source set implements the seven root package types in
[Traverse and mutate baseline tree data structures](https://github.com/rubixhacker/dyn4k/issues/46).
The `dyn4k` module provides Kotlin type aliases for the public tree types,
`Reference`, and `Version`. The aliases share the core objects. The
fixed source is dyn4j 6.0.0 at
[`058bf6d`](https://github.com/dyn4j/dyn4j/tree/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j).

## Declaration inventory

| Type | Baseline public and protected declarations | Contract |
| --- | ---: | --- |
| `AVLTree<E extends Comparable<E>>` | 26 | Open class, tree methods, range iterators, validation, console print |
| `BinarySearchTree<E extends Comparable<E>>` | 23 | Generic iterable interface and search return type |
| `BinarySearchTreeIterator<E extends Comparable<E>>` | 10 | Package visible final class, protected traversal helpers, unsupported `remove` |
| `BinarySearchTreeNode<E extends Comparable<E>>` | 6 | Package visible final node, null exception, comparable accessor |
| `BinarySearchTreeSearchCriteria<E extends Comparable<E>>` | 1 | Generic evaluation callback |
| `Reference<T>` | 6 | Public mutable value field, constructors, value equality and hash |
| `Version` | 6 | Private constructor, six static version methods |

There are no nested baseline types in this slice. The JVM archive bridge
restores Java generic bounds, package visibility, public fields, static
methods, and direct `Iterable` declaration. The comparator checks 78
public and protected declarations and seven type signatures against the
published dyn4j 6.0.0 JAR. The unchanged upstream Java tests also exercise
package visible tree nodes, fields, and helpers.

## Observed behavior

The unchanged Java `AVLTreeTest`, `ReferenceTest`, and `VersionTest` execute
36 cases against the candidate. Java consumers execute 19 public checks and
five package extension checks against both the baseline and candidate. The
common Kotlin tree suite executes four cases on JVM, Linux x64, JS Node,
Wasm JS Node, Wasm WASI Node, and Android host. The Java consumers also run
from a separate Gradle build that
resolves staged `dyn4k-jvm` and its transitive `dyn4k-core-jvm` dependency.
That separate build also executes three Kotlin alias and identity checks.

Iterator `remove()` throws `UnsupportedOperationException`. An exhausted
iterator throws `NoSuchElementException`. A null node value throws
`ArgumentNullException`. An empty tree returns its null search criterion;
searching a populated tree with a null criterion throws `NullPointerException`.
The baseline's empty-tree `print()` exception is retained. These outcomes
were checked against the fixed JAR with the same Java consumer source.

The Android consumer and common tests here run on the host. Device execution,
other target runtimes, complete engine parity, performance, and release
qualification remain open in the full port ledger.
