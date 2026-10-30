package io.github.rubixhacker.harness.migration

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * A JSON value with Python's types.
 *
 * The migration tools compare two implementations with `type(left) is not type(right)`, so a JSON
 * `true` must stay distinct from `1`, and `1` distinct from `1.0`. Kotlin's JSON model keeps those
 * apart only by text, and `kotlinx.serialization` renders all numbers as one primitive type. This
 * model keeps Python's five scalar types and preserves object insertion order, which is the order
 * `json.dumps` writes.
 */
sealed interface PyValue {
    data object Null : PyValue

    data class Bool(val value: Boolean) : PyValue

    data class Int(val value: Long) : PyValue

    data class Real(val value: Double) : PyValue

    data class Text(val value: String) : PyValue

    data class Seq(val items: List<PyValue>) : PyValue

    data class Map(val entries: LinkedHashMap<String, PyValue>) : PyValue

    /** Python's `type(value).__name__`. */
    val typeName: String
        get() = when (this) {
            Null -> "NoneType"
            is Bool -> "bool"
            is Int -> "int"
            is Real -> "float"
            is Text -> "str"
            is Seq -> "list"
            is Map -> "dict"
        }
}

/** Python's `KeyError` text is the quoted key. */
class PyKeyError(val key: String) : RuntimeException("'$key'")

/** Python's list index failure text. */
class PyIndexError : RuntimeException("list index out of range")

class PyTypeError(message: String) : RuntimeException(message)

fun pyMap(vararg pairs: Pair<String, PyValue>): PyValue.Map =
    PyValue.Map(linkedMapOf(*pairs))

fun pyList(vararg items: PyValue): PyValue.Seq = PyValue.Seq(items.toList())

fun pyList(items: List<PyValue>): PyValue.Seq = PyValue.Seq(items)

fun pyText(value: String): PyValue = PyValue.Text(value)

fun pyInt(value: Long): PyValue = PyValue.Int(value)

fun pyInt(value: Int): PyValue = PyValue.Int(value.toLong())

fun pyReal(value: Double): PyValue = PyValue.Real(value)

fun pyBool(value: Boolean): PyValue = PyValue.Bool(value)

/** Reads a JSON value with Python's `json.loads` types. */
fun pyFromJson(value: JsonElement): PyValue = when (value) {
    is JsonNull -> PyValue.Null
    is JsonObject -> PyValue.Map(LinkedHashMap(value.mapValues { pyFromJson(it.value) }))
    is JsonArray -> PyValue.Seq(value.map(::pyFromJson))
    is JsonPrimitive -> when {
        value.isString -> PyValue.Text(value.content)
        value.content == "true" -> PyValue.Bool(true)
        value.content == "false" -> PyValue.Bool(false)
        value.content.none { it == '.' || it == 'e' || it == 'E' } ->
            value.content.toLongOrNull()?.let(PyValue::Int)
                ?: PyValue.Real(value.content.toDouble())
        else -> PyValue.Real(value.content.toDouble())
    }
}

/** Renders this value as JSON for a `json.dumps`-compatible writer. */
fun PyValue.toJson(): JsonElement = when (this) {
    PyValue.Null -> JsonNull
    is PyValue.Bool -> JsonPrimitive(value)
    is PyValue.Int -> JsonPrimitive(value)
    is PyValue.Real -> JsonPrimitive(value)
    is PyValue.Text -> JsonPrimitive(value)
    is PyValue.Seq -> JsonArray(items.map { it.toJson() })
    is PyValue.Map -> JsonObject(LinkedHashMap(entries.mapValues { it.value.toJson() }))
}

/** Python's `value[key]`, with `KeyError` when the key is absent. */
fun PyValue.get(key: String): PyValue {
    val map = this as? PyValue.Map ?: throw PyTypeError("'${typeName}' object is not subscriptable")
    return map.entries[key] ?: throw PyKeyError(key)
}

/** Python's `value.get(key)` for a mapping. */
fun PyValue.getOrNull(key: String): PyValue? {
    val map = this as? PyValue.Map ?: throw PyTypeError("'${typeName}' object has no attribute 'get'")
    return map.entries[key]
}

/** Python's `value[index]`, with `IndexError` when the index is out of range. */
fun PyValue.at(index: Int): PyValue {
    val items = (this as? PyValue.Seq ?: throw PyTypeError("'${typeName}' object is not subscriptable")).items
    val resolved = if (index < 0) items.size + index else index
    return items.getOrNull(resolved) ?: throw PyIndexError()
}

/** Python's truth value. */
fun PyValue.truthy(): Boolean = when (this) {
    PyValue.Null -> false
    is PyValue.Bool -> value
    is PyValue.Int -> value != 0L
    is PyValue.Real -> value != 0.0
    is PyValue.Text -> value.isNotEmpty()
    is PyValue.Seq -> items.isNotEmpty()
    is PyValue.Map -> entries.isNotEmpty()
}

fun PyValue.isSeq(): Boolean = this is PyValue.Seq

fun PyValue.isMap(): Boolean = this is PyValue.Map

fun PyValue.isText(): Boolean = this is PyValue.Text

fun PyValue.isBool(): Boolean = this is PyValue.Bool

fun PyValue.isInt(): Boolean = this is PyValue.Int

fun PyValue.isReal(): Boolean = this is PyValue.Real

fun PyValue.isNumber(): Boolean = this is PyValue.Int || this is PyValue.Real

/** Python's `==` over JSON values: numbers compare numerically, and `True == 1`. */
fun pyEquals(left: PyValue, right: PyValue): Boolean {
    if (left is PyValue.Int || left is PyValue.Real || left is PyValue.Bool) {
        if (right is PyValue.Int || right is PyValue.Real || right is PyValue.Bool) {
            return pyNumber(left) == pyNumber(right)
        }
        return false
    }
    return when (left) {
        PyValue.Null -> right is PyValue.Null
        is PyValue.Text -> right is PyValue.Text && left.value == right.value
        is PyValue.Seq ->
            right is PyValue.Seq && left.items.size == right.items.size &&
                left.items.indices.all { pyEquals(left.items[it], right.items[it]) }
        is PyValue.Map ->
            right is PyValue.Map && left.entries.keys == right.entries.keys &&
                left.entries.all { (key, value) -> pyEquals(value, right.entries.getValue(key)) }
        else -> false
    }
}

private fun pyNumber(value: PyValue): Double = when (value) {
    is PyValue.Bool -> if (value.value) 1.0 else 0.0
    is PyValue.Int -> value.value.toDouble()
    is PyValue.Real -> value.value
    else -> throw PyTypeError("not a number")
}

/** Python's `len(value)`. */
fun pyLength(value: PyValue): Int = when (value) {
    is PyValue.Text -> value.value.length
    is PyValue.Seq -> value.items.size
    is PyValue.Map -> value.entries.size
    else -> throw PyTypeError("object of type '${value.typeName}' has no len()")
}

/** Python's ordered comparison between two values. */
fun pyCompare(left: PyValue, right: PyValue, operator: String): Int = when {
    left.isOrderedNumber() && right.isOrderedNumber() ->
        pyNumber(left).compareTo(pyNumber(right))
    left is PyValue.Text && right is PyValue.Text ->
        io.github.rubixhacker.harness.contract.CanonicalJson.compareCodePoints(left.value, right.value)
    else -> throw PyTypeError(
        "'$operator' not supported between instances of '${left.typeName}' and '${right.typeName}'",
    )
}

private fun PyValue.isOrderedNumber(): Boolean =
    this is PyValue.Int || this is PyValue.Real || this is PyValue.Bool

/** Python's `str(value)` for the types the migration reports carry. */
fun pythonStr(value: PyValue): String = when (value) {
    PyValue.Null -> "None"
    is PyValue.Bool -> if (value.value) "True" else "False"
    is PyValue.Int -> value.value.toString()
    is PyValue.Real -> io.github.rubixhacker.harness.contract.CanonicalJson.pythonFloat(value.value)
    is PyValue.Text -> value.value
    is PyValue.Seq -> pythonRepr(value)
    is PyValue.Map -> pythonRepr(value)
}

/** Python's `repr(value)`, as `str(dict)` and error messages render it. */
fun pythonRepr(value: PyValue): String = when (value) {
    PyValue.Null -> "None"
    is PyValue.Bool -> if (value.value) "True" else "False"
    is PyValue.Int -> value.value.toString()
    is PyValue.Real -> io.github.rubixhacker.harness.contract.CanonicalJson.pythonFloat(value.value)
    is PyValue.Text -> pythonStringRepr(value.value)
    is PyValue.Seq -> value.items.joinToString(", ", "[", "]") { pythonRepr(it) }
    is PyValue.Map -> value.entries.entries.joinToString(", ", "{", "}") { (key, item) ->
        pythonStringRepr(key) + ": " + pythonRepr(item)
    }
}

private fun pythonStringRepr(value: String): String {
    val quote = if ('\'' in value && '"' !in value) '"' else '\''
    val out = StringBuilder()
    out.append(quote)
    for (char in value) {
        when {
            char == '\\' -> out.append("\\\\")
            char == quote -> out.append('\\').append(char)
            char == '\n' -> out.append("\\n")
            char == '\r' -> out.append("\\r")
            char == '\t' -> out.append("\\t")
            char.code < 0x20 || char.code == 0x7F -> out.append("\\x").append(char.code.toString(16).padStart(2, '0'))
            char.code > 0x7E -> out.append("\\u").append(char.code.toString(16).padStart(4, '0'))
            else -> out.append(char)
        }
    }
    out.append(quote)
    return out.toString()
}

/** Python's `sorted(mapping)` over the string keys of a mapping. */
fun PyValue.sortedKeys(): PyValue.Seq {    val map = this as? PyValue.Map ?: throw PyTypeError("'${typeName}' object is not iterable")
    return PyValue.Seq(
        map.entries.keys.sortedWith(io.github.rubixhacker.harness.contract.CanonicalJson::compareCodePoints)
            .map { PyValue.Text(it) },
    )
}

/** Python's `list(range(count))`. */
fun pyRange(count: Int): PyValue.Seq = PyValue.Seq((0 until count).map { PyValue.Int(it.toLong()) })

/** Python's `int.from_bytes(data[16:20], "big")`. */
fun bigEndianInt(data: ByteArray, offset: Int): Long {
    var value = 0L
    for (index in 0 until 4) value = (value shl 8) or (data[offset + index].toLong() and 0xFF)
    return value
}

/** Python's iteration over a list, mapping (keys), or string (characters). */
fun pyIterate(value: PyValue): List<PyValue> = when (value) {
    is PyValue.Seq -> value.items
    is PyValue.Map -> value.entries.keys.map { PyValue.Text(it) }
    is PyValue.Text -> value.value.map { PyValue.Text(it.toString()) }
    else -> throw PyTypeError("'${value.typeName}' object is not iterable")
}

/**
 * A key with Python's set-membership equality: numbers compare across `int`, `float`, and `bool`,
 * while every other type keeps its identity.
 */
fun pyHashKey(value: PyValue): String = when (value) {
    is PyValue.Int -> "num:" + value.value.toDouble()
    is PyValue.Real -> "num:" + value.value
    is PyValue.Bool -> "num:" + (if (value.value) 1.0 else 0.0)
    is PyValue.Text -> "text:" + value.value
    PyValue.Null -> "none"
    else -> throw PyTypeError("unhashable type: '${value.typeName}'")
}

