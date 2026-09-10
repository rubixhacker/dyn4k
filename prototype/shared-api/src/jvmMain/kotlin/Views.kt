package probe
internal actual fun <T> liveReadOnly(source: MutableList<T>): List<T> = java.util.Collections.unmodifiableList(source)
