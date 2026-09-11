private class Box(var value: Int)
fun main() {
 val box = Box(40)
 try { throw IllegalStateException("probe") } catch (_: IllegalStateException) { box.value += 2 }
 check(box.value == 42)
 println("WEB_FLOOR_OK ${box.value}")
}
