package io.github.rubixhacker.harness.compatibility

/**
 * The method and dispatch inventories of `tools/compatibility/method_coverage.py`.
 *
 * Ported: [safePath], [analyzeOutput], and [dispatchInventoryOutput] — the parsing and inventory
 * gates `analyze` and `dispatch_inventory` apply to the helper's stdout.
 *
 * Not ported: `digest`, `tools_record`, `checked_tools`, `analyze`, `dispatch_inventory`,
 * `instrumented`, `make`, `check`, and `main`. They open the JaCoCo bundle and helper sources, run
 * `javac` and `java` on JDK 21, and replay the instrumented corpus.
 */
object MethodCoverage {
    const val HELPER = "tools/compatibility/fixtures/JacocoMethodReport.java"
    const val DISPATCH_HELPER = "tools/compatibility/fixtures/ClassfileDispatchReport.java"

    /** One row of the JaCoCo method report. */
    data class MethodRow(
        val owner: String,
        val name: String,
        val descriptor: String,
        val coveredInstructions: Int,
        val totalInstructions: Int,
    )

    data class MethodKey(val owner: String, val name: String, val descriptor: String)

    data class DispatchClass(val access: Int, val parent: String, val interfaces: List<String>)

    data class Invoke(
        val opcode: Int,
        val targetOwner: String,
        val targetName: String,
        val targetDescriptor: String,
    )

    data class DispatchInventory(
        val classes: Map<String, DispatchClass>,
        val methods: Map<MethodKey, Int>,
        val invokes: Map<MethodKey, List<Invoke>>,
        val opcodes: Map<MethodKey, List<Int>>,
    )

    /** Rejects an absolute, empty, or parent-relative receipt path. */
    fun safePath(root: String, name: String?): String {
        if (name.isNullOrEmpty() || isAbsolutePath(name) || ".." in pathParts(name)) {
            throw IllegalArgumentException("method receipt path is unsafe")
        }
        // `Path(root) / name` drops empty and `.` segments, so "a//b.json" becomes "a/b.json".
        return joinPath(root, pathParts(name).joinToString("/"))
    }

    /**
     * Parses the `JacocoMethodReport` output and enforces the complete-inventory gate: at least
     * 3000 rows, unique identities, and covered instructions within the total.
     */
    fun analyzeOutput(output: String): List<MethodRow> {
        val rows = mutableListOf<MethodRow>()
        for (line in pySplitLines(output)) {
            val fields = line.split("\t")
            if (fields.size < 5) {
                throw IllegalArgumentException(
                    "not enough values to unpack (expected 5, got ${fields.size})",
                )
            }
            if (fields.size > 5) {
                throw IllegalArgumentException(
                    "too many values to unpack (expected 5, got ${fields.size})",
                )
            }
            rows.add(
                MethodRow(
                    owner = fields[0],
                    name = fields[1],
                    descriptor = fields[2],
                    coveredInstructions = pythonInt(fields[3]),
                    totalInstructions = pythonInt(fields[4]),
                ),
            )
        }
        val identities = rows.map { Triple(it.owner, it.name, it.descriptor) }.toSet()
        if (rows.size < 3000 ||
            identities.size != rows.size ||
            rows.any { it.coveredInstructions < 0 || it.coveredInstructions > it.totalInstructions }
        ) {
            throw IllegalArgumentException("method coverage inventory is incomplete or invalid")
        }
        return rows
    }

    /**
     * Parses the `ClassfileDispatchReport` output and enforces the complete-inventory gate: at
     * least 200 classes, at least 3000 methods, and one opcode row per method.
     */
    fun dispatchInventoryOutput(output: String): DispatchInventory {
        val classes = linkedMapOf<String, DispatchClass>()
        val methods = linkedMapOf<MethodKey, Int>()
        val invokes = linkedMapOf<MethodKey, MutableList<Invoke>>()
        val opcodes = linkedMapOf<MethodKey, List<Int>>()
        for (line in pySplitLines(output)) {
            val parts = line.split("\t")
            when (parts[0]) {
                "C" -> {
                    expectFields(parts, 5)
                    classes[parts[1]] = DispatchClass(
                        access = pythonInt(parts[2]),
                        parent = parts[3],
                        interfaces = if (parts[4].isNotEmpty()) parts[4].split(",") else emptyList(),
                    )
                }
                "M" -> {
                    expectFields(parts, 5)
                    methods[MethodKey(parts[1], parts[2], parts[3])] = pythonInt(parts[4])
                }
                "I" -> {
                    expectFields(parts, 8)
                    val key = MethodKey(parts[1], parts[2], parts[3])
                    invokes.getOrPut(key) { mutableListOf() }.add(
                        Invoke(pythonInt(parts[4]), parts[5], parts[6], parts[7]),
                    )
                }
                "O" -> {
                    expectFields(parts, 5)
                    val key = MethodKey(parts[1], parts[2], parts[3])
                    if (key in opcodes) {
                        throw IllegalArgumentException("duplicate classfile opcode row")
                    }
                    opcodes[key] = parts[4].split(",").filter { it.isNotEmpty() }.map(::pythonInt)
                }
                else -> throw IllegalArgumentException("classfile dispatch inventory has an unknown row")
            }
        }
        if (classes.size < 200 || methods.size < 3000 || opcodes.keys != methods.keys) {
            throw IllegalArgumentException("classfile dispatch inventory is incomplete")
        }
        return DispatchInventory(classes, methods, invokes, opcodes)
    }

    private fun expectFields(parts: List<String>, count: Int) {
        if (parts.size < count) {
            throw IllegalArgumentException(
                "not enough values to unpack (expected $count, got ${parts.size})",
            )
        }
        if (parts.size > count) {
            throw IllegalArgumentException(
                "too many values to unpack (expected $count, got ${parts.size})",
            )
        }
    }

    /**
     * Python's `int(text)` for base ten: surrounding whitespace and `_` digit separators are
     * accepted. Radix prefixes are not, because the report never emits them.
     */
    private fun pythonInt(text: String): Int {
        val normalised = text.trim().replace("_", "")
        return normalised.toIntOrNull()
            ?: throw IllegalArgumentException("invalid literal for int() with base 10: '$text'")
    }
}
