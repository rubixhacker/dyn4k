package org.dyn4j.exception

actual open class CopyException actual constructor(sourceName: String, copyName: String) :
    ClassCastException(copyExceptionMessage(sourceName, copyName)) {
    constructor(source: Class<*>, copy: Class<*>) : this(source.name, copy.name)

    private companion object {
        private const val serialVersionUID = 2434249738746680073L
    }
}
