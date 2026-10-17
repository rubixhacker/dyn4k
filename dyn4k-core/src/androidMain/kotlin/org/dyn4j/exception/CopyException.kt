package org.dyn4j.exception

actual open class CopyException actual constructor(sourceName: String, copyName: String) :
    ClassCastException(copyExceptionMessage(sourceName, copyName)) {
    constructor(source: Class<*>, copy: Class<*>) : this(source.name, copy.name)
}
