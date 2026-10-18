package org.dyn4j.world

internal actual fun worldNestedViewOutcome(operation: WorldViewOperation): WorldViewOutcome =
    when (operation) {
        WorldViewOperation.CHILD_AFTER_ADD,
        WorldViewOperation.GRANDCHILD_AFTER_ADD,
        WorldViewOperation.CHILD_AFTER_REPLACE,
        WorldViewOperation.EMPTY_CLEAR_CHILD_SIZE,
        WorldViewOperation.EMPTY_CLEAR_PARENT_READ -> WorldViewOutcome.VALUE
        WorldViewOperation.READ_AFTER_ADD,
        WorldViewOperation.GRANDCHILD_READ_AFTER_ADD,
        WorldViewOperation.READ_AFTER_REPLACE,
        WorldViewOperation.SAVED_NESTED_SIZE,
        WorldViewOperation.EMPTY_CLEAR_ROOT_ITERATOR,
        WorldViewOperation.EMPTY_CLEAR_SIBLING_READ,
        WorldViewOperation.EMPTY_CLEAR_PUBLIC_READ -> WorldViewOutcome.CONCURRENT_MODIFICATION
        WorldViewOperation.NEGATIVE_RANGE,
        WorldViewOperation.OVERSIZED_RANGE -> WorldViewOutcome.INDEX_OUT_OF_BOUNDS
        WorldViewOperation.REVERSED_RANGE -> WorldViewOutcome.ILLEGAL_ARGUMENT
    }
