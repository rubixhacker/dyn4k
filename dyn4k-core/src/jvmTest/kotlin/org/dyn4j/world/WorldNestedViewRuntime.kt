package org.dyn4j.world

internal actual fun worldNestedViewOutcome(operation: WorldViewOperation): WorldViewOutcome =
    try {
        val backing = java.util.ArrayList<Any>()
        backing.add(Any())
        if (operation.name.startsWith("EMPTY_CLEAR")) {
            val iterator = backing.iterator()
            val parent = backing.subList(0, 1)
            val child = parent.subList(0, 0)
            val sibling = parent.subList(0, 1)
            val publicView = java.util.Collections.unmodifiableList(backing).subList(0, 1)
            child.clear()
            when (operation) {
                WorldViewOperation.EMPTY_CLEAR_CHILD_SIZE -> child.size
                WorldViewOperation.EMPTY_CLEAR_PARENT_READ -> parent[0]
                WorldViewOperation.EMPTY_CLEAR_ROOT_ITERATOR -> iterator.next()
                WorldViewOperation.EMPTY_CLEAR_SIBLING_READ -> sibling[0]
                WorldViewOperation.EMPTY_CLEAR_PUBLIC_READ -> publicView[0]
                else -> error("Unexpected empty clear operation")
            }
        } else {
            val saved = java.util.Collections.unmodifiableList(backing).subList(0, 1)
            val nested = saved.subList(0, 1)
            if (operation == WorldViewOperation.CHILD_AFTER_REPLACE ||
                operation == WorldViewOperation.READ_AFTER_REPLACE
            ) {
                backing.removeAt(0)
                backing.add(Any())
            } else {
                backing.add(Any())
            }
            when (operation) {
                WorldViewOperation.CHILD_AFTER_ADD, WorldViewOperation.CHILD_AFTER_REPLACE -> saved.subList(0, 1)
                WorldViewOperation.GRANDCHILD_AFTER_ADD -> nested.subList(0, 1)
                WorldViewOperation.READ_AFTER_ADD, WorldViewOperation.READ_AFTER_REPLACE -> saved.subList(0, 1)[0]
                WorldViewOperation.GRANDCHILD_READ_AFTER_ADD -> nested.subList(0, 1)[0]
                WorldViewOperation.SAVED_NESTED_SIZE -> nested.size
                WorldViewOperation.NEGATIVE_RANGE -> saved.subList(-1, 1)
                WorldViewOperation.OVERSIZED_RANGE -> saved.subList(0, 2)
                WorldViewOperation.REVERSED_RANGE -> saved.subList(1, 0)
                else -> error("Unexpected nested view operation")
            }
        }
        WorldViewOutcome.VALUE
    } catch (_: ConcurrentModificationException) {
        WorldViewOutcome.CONCURRENT_MODIFICATION
    } catch (_: IndexOutOfBoundsException) {
        WorldViewOutcome.INDEX_OUT_OF_BOUNDS
    } catch (_: IllegalArgumentException) {
        WorldViewOutcome.ILLEGAL_ARGUMENT
    }
