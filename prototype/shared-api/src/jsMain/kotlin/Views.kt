package probe
internal actual fun <T> liveReadOnly(source: MutableList<T>): List<T> = object : AbstractList<T>() {
    override val size: Int get() = source.size
    override fun get(index: Int): T = source[index]
}
