package org.dyn4j.exception

actual open class CopyException actual constructor(sourceName: String, copyName: String) :
    ClassCastException(copyExceptionMessage(sourceName, copyName))
