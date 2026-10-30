package io.github.rubixhacker.harness.performance

/**
 * CSV reading with the semantics of Python's `csv.DictReader` as the performance tools use it.
 *
 * A row whose value is missing yields `null`, which is how `csv.DictReader` reports a short
 * record. Blank physical lines are skipped, and extra fields are collected under the `null` key
 * exactly as `DictReader` does with its `restkey`.
 */
class CsvTable(val fieldNames: List<String>?, val rows: List<Map<String, String?>>)

object Csv {
    /**
     * `csv.DictReader` collects a record's surplus fields under the `None` key. This constant
     * stands in for that key, which no measured channel can collide with.
     */
    const val REST_KEY: String = "\u0000rest"

    fun parse(text: String): CsvTable {
        val records = records(text)
        val header = records.firstOrNull() ?: return CsvTable(null, emptyList())
        val rows = records.drop(1).map { record ->
            val row = LinkedHashMap<String, String?>()
            for ((index, name) in header.withIndex()) {
                row[name] = record.getOrNull(index)
            }
            if (record.size > header.size) {
                row[REST_KEY] = record.drop(header.size).joinToString(",")
            }
            row
        }
        return CsvTable(header, rows)
    }

    /** Splits CSV text into records, honouring quoted fields and every line terminator Python accepts. */
    fun records(text: String): List<List<String>> {
        val output = mutableListOf<List<String>>()
        var record = mutableListOf<String>()
        val field = StringBuilder()
        var quoted = false
        var index = 0
        var fieldStarted = false
        while (index < text.length) {
            val char = text[index]
            if (quoted) {
                if (char == '"') {
                    if (index + 1 < text.length && text[index + 1] == '"') {
                        field.append('"')
                        index += 2
                        continue
                    }
                    quoted = false
                    index += 1
                    continue
                }
                field.append(char)
                index += 1
                continue
            }
            when (char) {
                '"' -> {
                    if (!fieldStarted) {
                        quoted = true
                        fieldStarted = true
                    } else {
                        field.append(char)
                    }
                    index += 1
                }
                ',' -> {
                    record.add(field.toString())
                    field.setLength(0)
                    fieldStarted = false
                    index += 1
                }
                '\r', '\n' -> {
                    record.add(field.toString())
                    field.setLength(0)
                    fieldStarted = false
                    output.add(record)
                    record = mutableListOf()
                    index += if (char == '\r' && index + 1 < text.length && text[index + 1] == '\n') 2 else 1
                }
                else -> {
                    field.append(char)
                    fieldStarted = true
                    index += 1
                }
            }
        }
        if (fieldStarted || field.isNotEmpty() || record.isNotEmpty()) {
            record.add(field.toString())
            output.add(record)
        }
        // `csv.reader` reports a blank physical line as an empty record, which `DictReader` skips.
        return output.filter { it != listOf("") }
    }
}

/** The value of a channel that the caller has already proven present. */
fun Map<String, String?>.required(field: String): String =
    this[field] ?: throw IllegalArgumentException("missing channel: $field")

/** The integer value of a channel, as `int(row[field])` reads it. */
fun Map<String, String?>.channel(field: String): Long =
    required(field).trim().toLongOrNull()
        ?: throw IllegalArgumentException("invalid integer channel $field: ${this[field]}")

/** The float value of a channel, as `float(row[field])` reads it. */
fun Map<String, String?>.floatChannel(field: String): Double =
    required(field).trim().toDoubleOrNull()
        ?: throw IllegalArgumentException("invalid numeric channel $field: ${this[field]}")
