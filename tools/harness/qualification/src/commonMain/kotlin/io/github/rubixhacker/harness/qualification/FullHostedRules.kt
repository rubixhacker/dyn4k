package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.StrictJson
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** One Safari product selection: the compiler product, its Karma input, and both build roots. */
data class SafariProductPaths(
    val expected: String,
    val karmaInput: String,
    val buildRoot: String,
    val karmaPackage: String,
)

/**
 * One `safari_v2_integer` value: the canonical literal, compared exactly.
 *
 * Python integers are unbounded, and the grammar accepts up to twenty characters, so a literal can
 * exceed `Long`. Comparison is on the decimal digits, which keeps the range check of the recorded
 * bits exact without an arbitrary precision library on `commonMain`.
 */
class SafariInteger(val literal: String) {
    private val negative: Boolean = literal.startsWith("-")
    private val digits: String = literal.removePrefix("-")

    fun isZero(): Boolean = digits == "0"

    /** `int(literal)` when the value fits in a Java `long`. */
    fun toLongOrNull(): Long? = literal.toLongOrNull()

    fun equalsLong(value: Long): Boolean = toLongOrNull() == value

    fun compareTo(other: SafariInteger): Int {
        if (negative != other.negative) return if (negative) -1 else 1
        var comparison = digits.length.compareTo(other.digits.length)
        if (comparison == 0) comparison = digits.compareTo(other.digits)
        return if (negative) -comparison else comparison
    }

    companion object {
        fun of(value: Long): SafariInteger = SafariInteger(value.toString())
        val ZERO = SafariInteger("0")
        val ONE = SafariInteger("1")
        val MAX_LONG = SafariInteger(Long.MAX_VALUE.toString())
        val MIN_LONG = SafariInteger(Long.MIN_VALUE.toString())
    }
}

/** One report check: the case inventory read from archived XML and the reports it came from. */
class HostedReportCheck(
    val expected: Int,
    val executed: Int,
    val caseIds: List<String>,
    val reports: MutableList<JsonObject>,
) {
    /** The report group as it is stored in a lane and in the receipt. */
    fun toJson(module: String): JsonObject = JsonObject(
        linkedMapOf(
            "module" to JsonPrimitive(module),
            "expected" to JsonPrimitive(expected),
            "executed" to JsonPrimitive(executed),
            "case_ids" to JsonArray(caseIds.map { JsonPrimitive(it) }),
            "reports" to JsonArray(reports),
        ),
    )
}

/**
 * The pure half of `full_hosted.py`: the Safari diagnostic value grammar, the generated Gradle
 * scripts, the Safari product paths, the mode arguments, and the report-group comparison.
 *
 * Nothing here touches a file. The grammar is a validator, so every branch either returns the
 * parsed count the reference returns or throws with the reference message.
 */
object FullHostedRules {
    /** `NATIVE`: the hosted native targets, keyed exactly as `hosted.NATIVE_TARGETS` is. */
    val NATIVE: Set<String> = Hosted.NATIVE_TARGETS.keys

    /** `CONFIGS`: the two configurations every hosted target is run in. */
    val CONFIGS: Map<String, List<String>> = linkedMapOf<String, List<String>>().apply {
        for (target in NATIVE) put(target, listOf("debug-g", "optimized-opt"))
        put("jsSafari", listOf("development", "production"))
    }

    /** `SOURCE_TASK`: the Gradle task that produces one target's source test reports. */
    val SOURCE_TASK: Map<String, String> = linkedMapOf<String, String>().apply {
        for (target in NATIVE) put(target, "${'$'}{target}Test")
        put("jsSafari", "jsBrowserTest")
    }

    val SAFARI_DIAGNOSTIC_SHAPES: Map<String, Pair<String, String>> = linkedMapOf(
        "CapsuleSlice" to ("Capsule" to "Slice"),
        "CirclePolygon" to ("Circle" to "Polygon"),
        "CircleSegment" to ("Circle" to "Segment"),
        "CircleSlice" to ("Circle" to "Slice"),
        "PolygonCapsule" to ("Polygon" to "Capsule"),
        "PolygonPolygon" to ("Polygon" to "Polygon"),
    )

    val SAFARI_DIAGNOSTIC_PREFIX_KEYS: List<String> = listOf(
        "provider", "fixture", "method", "phase", "order", "step", "algorithm",
        "a.transform", "b.transform", "a.center.local", "b.center.local",
        "a.center.world", "b.center.world", "hit", "booleanHit",
        "penetration.normal", "penetration.depth", "selection", "clipped",
        "manifold.normal", "manifold.count",
    )

    val SAFARI_DIAGNOSTIC_TRACE_KEYS: List<String> =
        listOf(
            "a.shape.local", "b.shape.local", "a.polygon.edgeArithmetic",
            "b.polygon.edgeArithmetic", "a.foci.world", "b.foci.world",
            "a.axes.withB", "b.axes.withA", "gjk.initial.centerDirection",
            "gjk.initial.effectiveDirection", "clip.probe.feature.a",
            "clip.probe.feature.b",
        ) + (0 until 6).flatMap { index ->
            listOf("direction", "a", "b.negated", "minkowski").map { field ->
                "support.$index.$field"
            }
        }

    val SAFARI_DIAGNOSTIC_SAT_KEYS: List<String> = listOf(
        "sat.replay.hit", "sat.replay.matchesResult", "sat.candidates",
        "sat.winner.source", "sat.winner.index", "sat.winner.preOrientation",
        "sat.winner.centerDot", "sat.winner.orientationFlip", "sat.winner.finalAxis",
        "sat.winner.depth",
    )

    val SAFARI_DIAGNOSTIC_EPA_KEYS: List<String> = listOf(
        "epa.replay.identity", "epa.replay.simplex", "epa.replay.iteration",
        "epa.replay.stop", "epa.replay.epsilon", "epa.replay.maxIterations",
        "epa.iteration.schema", "epa.iteration.records", "epa.queue.reconstructedMatches",
        "epa.edge.a", "epa.edge.b", "epa.edge.normal", "epa.edge.distance",
        "epa.terminal.support", "epa.terminal.projection", "epa.terminal.delta",
        "epa.replay.normalMatchesResult", "epa.replay.depthMatchesResult",
    )

    /**
     * `relative_path` as a name: one archive member that cannot escape the archive.
     *
     * The JVM port resolves the name to a `Path` in [FullHosted.relativePath]; this form only
     * validates it, so the pure report comparison can use it from `commonMain`.
     */
    fun archiveName(value: String?): String {
        if (value.isNullOrEmpty() || "\\" in value) {
            throw IllegalArgumentException("unsafe archive path")
        }
        if (value.startsWith("/") || value.split('/').any { it in setOf("", ".", "..") } ||
            ":" in value.split('/').first()
        ) {
            throw IllegalArgumentException("unsafe archive path")
        }
        return value
    }

    /** `safari_v2_require`. */
    fun safariV2Require(condition: Boolean, field: String) {
        if (!condition) {
            throw IllegalArgumentException(
                "Safari diagnostic $field value is incomplete or malformed",
            )
        }
    }

    /** `safari_v2_integer`: a canonical integer literal, optionally with a floor. */
    fun safariV2Integer(value: String, field: String, minimum: Long? = null): SafariInteger {
        safariV2Require(
            value.length <= 20 && Regex("(?:0|-?[1-9]\\d*)").matches(value),
            field,
        )
        val number = SafariInteger(value)
        safariV2Require(
            minimum == null || number.compareTo(SafariInteger.of(minimum)) >= 0,
            field,
        )
        return number
    }

    /** `safari_v2_number`: `value@bits`, where the bits must be the double's own encoding. */
    fun safariV2Number(value: String, field: String) {
        val parts = value.split('@')
        safariV2Require(
            parts.size == 2 && parts[0].length <= 32 &&
                Regex(
                    "(?:NaN|-?Infinity|-?(?:0|[1-9]\\d*)(?:\\.\\d+)?(?:[eE][+-]?\\d+)?)",
                ).matches(parts[0]),
            field,
        )
        val bits = safariV2Integer(parts[1], field)
        safariV2Require(
            bits.compareTo(SafariInteger.MIN_LONG) >= 0 &&
                bits.compareTo(SafariInteger.MAX_LONG) <= 0,
            field,
        )
        val bitsValue = bits.toLongOrNull()!!
        val number = pythonFloat(parts[0])!!
        if (number.isNaN()) {
            val raw = bitsValue
            safariV2Require(
                (raw and 0x7ff0000000000000L) == 0x7ff0000000000000L &&
                    (raw and 0x000fffffffffffffL) != 0L,
                field,
            )
        } else {
            safariV2Require(
                !number.isInfinite() || parts[0] == "Infinity" || parts[0] == "-Infinity",
                field,
            )
            if (number == 0.0) {
                safariV2Require(parts[0] == "0" || parts[0] == "-0", field)
            }
            val encoded = number.toRawBits()
            safariV2Require(
                bitsValue == encoded ||
                    (number == 0.0 && !parts[0].startsWith("-") && bitsValue == -(1L shl 63)),
                field,
            )
        }
    }

    /** `safari_v2_vector`: two numbers separated by a comma. */
    fun safariV2Vector(value: String, field: String) {
        val parts = value.split(',')
        safariV2Require(parts.size == 2, field)
        for (part in parts) safariV2Number(part, field)
    }

    /** `safari_v2_numbers`: an exact count of comma separated numbers. */
    fun safariV2Numbers(value: String, field: String, count: Int) {
        val parts = value.split(',')
        safariV2Require(parts.size == count, field)
        for (part in parts) safariV2Number(part, field)
    }

    /** `safari_v2_vectors`: `null`, empty, or semicolon separated vectors; returns the count. */
    fun safariV2Vectors(value: String, field: String, allowNull: Boolean = true, allowEmpty: Boolean = true): Int? {
        if (value == "null") {
            safariV2Require(allowNull, field)
            return null
        }
        if (value.isEmpty()) {
            safariV2Require(allowEmpty, field)
            return 0
        }
        val parts = value.split(';')
        for (part in parts) safariV2Vector(part, field)
        return parts.size
    }

    /** `safari_v2_feature`: a point, an edge, or the explicit `unknown:index` form. */
    fun safariV2Feature(value: String, field: String) {
        val parts = value.split(':')
        when {
            parts[0] == "point" -> {
                safariV2Require(parts.size == 3, field)
                safariV2Integer(parts[1], field)
                safariV2Vector(parts[2], field)
            }
            parts[0] == "edge" -> {
                safariV2Require(parts.size == 9, field)
                for (index in listOf(1, 2, 4, 6)) safariV2Integer(parts[index], field)
                for (index in listOf(3, 5, 7, 8)) safariV2Vector(parts[index], field)
            }
            else -> {
                safariV2Require(parts.size == 2 && parts[0] == "unknown", field)
                safariV2Integer(parts[1], field)
            }
        }
    }

    /** `safari_v2_shape`: the ordered shape fields and, for polygon kinds, the vertex count. */
    fun safariV2Shape(value: String, field: String): Pair<String, Int?> {
        val parts = value.split('|').map { part -> part.split('=', limit = 2) }
        safariV2Require(parts.all { it.size == 2 }, field)
        val fields = LinkedHashMap<String, String>()
        for (part in parts) fields[part[0]] = part[1]
        val kind = fields["kind"]
        val suffixes = linkedMapOf(
            "Circle" to listOf("circle.radius"),
            "Capsule" to listOf(
                "capsule.length", "capsule.capRadius", "capsule.localFoci", "capsule.localAxis",
            ),
            "Slice" to listOf(
                "slice.radius", "slice.theta", "slice.circleCenter", "slice.rotation",
                "slice.upperEdge", "slice.lowerEdge",
            ),
            "Segment" to listOf("segment.length", "vertices", "normals"),
            "Polygon" to listOf("vertices", "normals"),
        )
        safariV2Require(
            kind != null && kind in suffixes &&
                parts.map { it[0] } == listOf("kind", "center", "radius") + suffixes.getValue(kind),
            field,
        )
        safariV2Vector(fields.getValue("center"), field)
        safariV2Number(fields.getValue("radius"), field)
        for (name in listOf(
            "circle.radius", "capsule.length", "capsule.capRadius",
            "slice.radius", "slice.theta", "segment.length",
        )) {
            if (name in fields) safariV2Number(fields.getValue(name), field)
        }
        if (kind == "Capsule") {
            safariV2Vectors(fields.getValue("capsule.localFoci"), field)
            safariV2Vector(fields.getValue("capsule.localAxis"), field)
        }
        if (kind == "Slice") {
            safariV2Vector(fields.getValue("slice.circleCenter"), field)
            safariV2Vector(fields.getValue("slice.rotation"), field)
            safariV2Feature(fields.getValue("slice.upperEdge"), field)
            safariV2Feature(fields.getValue("slice.lowerEdge"), field)
        }
        val resolvedKind = kind!!
        var count: Int? = null
        if (resolvedKind == "Polygon" || resolvedKind == "Segment") {
            count = safariV2Vectors(fields.getValue("vertices"), field, false, false)
            safariV2Require(
                safariV2Vectors(fields.getValue("normals"), field, false, false) == count,
                field,
            )
        }
        return resolvedKind to count
    }

    /** `safari_v2_polygon_edges`: one twelve field record per polygon edge, or `na`. */
    fun safariV2PolygonEdges(value: String, field: String, kind: String, vertices: Int?) {
        if (kind != "Polygon") {
            safariV2Require(value == "na", field)
            return
        }
        val edges = value.split(';')
        safariV2Require(edges.size == vertices, field)
        for ((index, edge) in edges.withIndex()) {
            val parts = edge.split(':')
            safariV2Require(parts.size == 12 && parts[0] == index.toString(), field)
            for (part in parts.subList(1, 8)) safariV2Number(part, field)
            safariV2Vector(parts[8], field)
            safariV2Number(parts[9], field)
            safariV2Vector(parts[10], field)
            safariV2Vector(parts[11], field)
        }
    }

    /** `safari_v2_sat_candidates`: every candidate record; returns whether one separated. */
    fun safariV2SatCandidates(value: String, field: String): Boolean {
        safariV2Require(value.isNotEmpty(), field)
        val candidates = value.split(';')
        var separated = false
        for ((index, candidate) in candidates.withIndex()) {
            val parts = candidate.split(':')
            safariV2Require(parts.size in setOf(4, 6, 13), field)
            safariV2Require(parts[0] == "0" || parts[0] == "1", field)
            safariV2Integer(parts[1], field, 0)
            when (parts.size) {
                4 -> {
                    safariV2Require(parts[2] == "zero", field)
                    safariV2Vector(parts[3], field)
                }
                6 -> {
                    safariV2Require(
                        parts[2] == "separated" && index == candidates.size - 1,
                        field,
                    )
                    safariV2Vector(parts[3], field)
                    safariV2Vector(parts[4], field)
                    safariV2Vector(parts[5], field)
                    separated = true
                }
                else -> {
                    safariV2Vector(parts[2], field)
                    safariV2Vector(parts[3], field)
                    safariV2Vector(parts[4], field)
                    safariV2Number(parts[5], field)
                    safariV2Require(
                        listOf(parts[6], parts[7], parts[12]).all { it == "true" || it == "false" },
                        field,
                    )
                    for (part in listOf(parts[8], parts[9])) {
                        if (part != "na") safariV2Number(part, field)
                    }
                    safariV2Number(parts[10], field)
                    safariV2Vector(parts[11], field)
                }
            }
        }
        return separated
    }

    /** `safari_v2_epa_records`: one thirteen field record per EPA iteration. */
    fun safariV2EpaRecords(value: String, field: String, iteration: SafariInteger) {
        val records = if (value.isEmpty()) emptyList() else value.split(';')
        safariV2Require(iteration.equalsLong(records.size.toLong()), field)
        for ((index, record) in records.withIndex()) {
            val parts = record.split(':')
            safariV2Require(parts.size == 13 && parts[0] == (index + 1).toString(), field)
            if (parts[1] != "na") safariV2Integer(parts[1], field, 0)
            for (part in parts.subList(2, 6)) safariV2Vector(part, field)
            safariV2Number(parts[6], field)
            safariV2Vector(parts[7], field)
            for (part in parts.subList(8, 10)) safariV2Number(part, field)
            safariV2Require(
                parts[10] in setOf("continue", "epsilon", "iterationLimit"),
                field,
            )
            if (parts[11] != "na" && parts[11] != "") {
                for (edgeId in parts[11].split(',')) safariV2Integer(edgeId, field, 0)
            }
            safariV2Require(parts[12] == "true" || parts[12] == "false", field)
        }
    }

    /** `safari_v2_check_values`: the cross-field invariants of one diagnostic row. */
    fun safariV2CheckValues(values: Map<String, String>, step: Int, points: Int) {
        for (field in listOf("a.transform", "b.transform")) {
            safariV2Numbers(values.getValue(field), field, 6)
        }
        for (field in listOf(
            "a.center.local", "b.center.local", "a.center.world", "b.center.world",
            "penetration.normal", "gjk.initial.centerDirection",
            "gjk.initial.effectiveDirection",
        )) {
            safariV2Vector(values.getValue(field), field)
        }
        safariV2Number(values.getValue("penetration.depth"), "penetration.depth")
        val shapes = linkedMapOf<String, Pair<String, Int?>>()
        for (side in listOf("a", "b")) {
            val field = "$side.shape.local"
            shapes[side] = safariV2Shape(values.getValue(field), field)
        }
        var expectedShapes = SAFARI_DIAGNOSTIC_SHAPES.getValue(values.getValue("fixture"))
        if (values.getValue("order") == "reverse") expectedShapes = expectedShapes.second to expectedShapes.first
        safariV2Require(
            listOf(shapes.getValue("a").first, shapes.getValue("b").first) ==
                listOf(expectedShapes.first, expectedShapes.second),
            "fixture shapes",
        )
        for (side in listOf("a", "b")) {
            val (kind, vertices) = shapes.getValue(side)
            val field = "$side.polygon.edgeArithmetic"
            safariV2PolygonEdges(values.getValue(field), field, kind, vertices)
            for (suffix in listOf("foci.world", if (side == "a") "axes.withB" else "axes.withA")) {
                val name = "$side.$suffix"
                safariV2Vectors(values.getValue(name), name)
            }
            val feature = values.getValue("clip.probe.feature.$side")
            safariV2Require(
                (feature == "na") == (values.getValue("hit") == "false"),
                "clip.probe.feature.$side",
            )
            if (feature != "na") safariV2Feature(feature, "clip.probe.feature.$side")
        }
        for (index in 0 until 6) {
            for (suffix in listOf("direction", "a", "b.negated", "minkowski")) {
                val field = "support.$index.$suffix"
                safariV2Vector(values.getValue(field), field)
            }
        }
        if (step < 4) {
            safariV2Require(values.getValue("manifold.normal") == "na", "manifold.normal")
        } else {
            safariV2Vector(values.getValue("manifold.normal"), "manifold.normal")
        }
        for (index in 0 until points) {
            safariV2Vector(
                values.getValue("manifold.point.$index.position"),
                "manifold.point.$index.position",
            )
            safariV2Number(
                values.getValue("manifold.point.$index.depth"),
                "manifold.point.$index.depth",
            )
        }
        if (values.getValue("algorithm") == "sat") {
            safariV2Require(
                values.getValue("sat.replay.hit") in setOf("true", "false") &&
                    values.getValue("sat.replay.matchesResult") in setOf("true", "false"),
                "sat.replay",
            )
            val separated = safariV2SatCandidates(
                values.getValue("sat.candidates"),
                "sat.candidates",
            )
            safariV2Require(
                (values.getValue("sat.replay.hit") == "false") == separated,
                "sat.candidates",
            )
            safariV2Integer(values.getValue("sat.winner.index"), "sat.winner.index", 0)
            if (separated) {
                safariV2Require(
                    values.getValue("sat.winner.source") in setOf("0", "1"),
                    "sat.winner.source",
                )
            } else {
                safariV2Require(
                    values.getValue("sat.winner.source") in setOf("a", "b"),
                    "sat.winner.source",
                )
                for (field in listOf("sat.winner.preOrientation", "sat.winner.finalAxis")) {
                    safariV2Vector(values.getValue(field), field)
                }
                for (field in listOf("sat.winner.centerDot", "sat.winner.depth")) {
                    safariV2Number(values.getValue(field), field)
                }
                safariV2Require(
                    values.getValue("sat.winner.orientationFlip") in setOf("true", "false"),
                    "sat.winner.orientationFlip",
                )
            }
        }
        safariV2Require(
            values.getValue("epa.replay.identity") == "unobserved",
            "epa.replay.identity",
        )
        val simplex = safariV2Vectors(
            values.getValue("epa.replay.simplex"),
            "epa.replay.simplex",
            false,
            true,
        )
        val iteration = safariV2Integer(
            values.getValue("epa.replay.iteration"),
            "epa.replay.iteration",
            0,
        )
        if (values.getValue("algorithm") == "sat") {
            safariV2Require(iteration.isZero(), "epa.replay.iteration")
        }
        val maximum = safariV2Integer(
            values.getValue("epa.replay.maxIterations"),
            "epa.replay.maxIterations",
            1,
        )
        safariV2Require(iteration.compareTo(maximum) <= 0, "epa.replay.iteration")
        safariV2Require(
            values.getValue("epa.replay.stop") in
                setOf("notRun", "epsilon", "iterationLimit"),
            "epa.replay.stop",
        )
        safariV2Require(
            iteration.isZero() == (values.getValue("epa.replay.stop") == "notRun"),
            "epa.replay.stop",
        )
        safariV2Require(
            values.getValue("epa.replay.stop") != "iterationLimit" ||
                iteration.compareTo(maximum) == 0,
            "epa.replay.stop",
        )
        safariV2Require(
            if (iteration.isZero()) simplex == 0 else simplex!! > 0,
            "epa.replay.simplex",
        )
        safariV2Number(values.getValue("epa.replay.epsilon"), "epa.replay.epsilon")
        safariV2Require(
            values.getValue("epa.iteration.schema") ==
                "index:edgeId:edgeA:edgeB:normalBefore:normalAfter:distance:" +
                "support:projection:delta:stop:equalDistanceEdgeIds:mirrorMatches",
            "epa.iteration.schema",
        )
        safariV2EpaRecords(
            values.getValue("epa.iteration.records"),
            "epa.iteration.records",
            iteration,
        )
        safariV2Require(
            values.getValue("epa.queue.reconstructedMatches") in setOf("true", "false"),
            "epa.queue.reconstructedMatches",
        )
        val edgePresent = values.getValue("epa.edge.a") != "na"
        safariV2Require(edgePresent == (iteration.compareTo(SafariInteger.ZERO) > 0), "epa.edge.a")
        for (field in listOf(
            "epa.edge.a", "epa.edge.b", "epa.edge.normal", "epa.terminal.support",
        )) {
            val value = values.getValue(field)
            if (edgePresent) safariV2Vector(value, field) else safariV2Require(value == "na", field)
        }
        for (field in listOf(
            "epa.edge.distance", "epa.terminal.projection", "epa.terminal.delta",
        )) {
            val value = values.getValue(field)
            if (edgePresent) safariV2Number(value, field) else safariV2Require(value == "na", field)
        }
        for (field in listOf(
            "epa.replay.normalMatchesResult", "epa.replay.depthMatchesResult",
        )) {
            safariV2Require(
                values.getValue(field) in
                    (if (edgePresent) setOf("true", "false") else setOf("na")),
                field,
            )
        }
        val expectedSelection = when {
            values.getValue("algorithm") == "sat" -> "satSourceReplay"
            edgePresent -> "epaSourceReplay"
            else -> "unavailable"
        }
        safariV2Require(values.getValue("selection") == expectedSelection, "selection")
    }

    /**
     * `init_script`: the generated Gradle init script that binds the test task to the reviewed
     * configuration, mode, and simulator.
     */
    fun initScript(target: String, configuration: String, simulatorUdid: String? = null): String {
        if (target == "jsSafari") {
            val production = configuration == "production"
            val source = listOf(
                "gradle.beforeProject { project ->",
                "  project.plugins.withId('org.jetbrains.kotlin.multiplatform') {",
                "    project.afterEvaluate {",
                "      project.tasks.named('jsBrowserTest').configure { task ->",
                "        task.useKarma { useSafari() }",
                "        if (PRODUCTION) {",
                "          task.dependsOn('jsTestTestProductionExecutableCompileSync')",
                "          def testFileName = project.name + '-test.js'",
                "          if (project != project.rootProject) {",
                "            testFileName = project.rootProject.name + '-' + testFileName",
                "          }",
                "          task.inputFileProperty.set(project.layout.buildDirectory.file(",
                "            'compileSync/js/test/testProductionExecutable/kotlin/' + testFileName))",
                "        }",
                "      }",
                "    }",
                "  }",
                "}",
                "",
            ).joinToString("\n")
            return source.replace("PRODUCTION", if (production) "true" else "false")
        }
        val lines = mutableListOf(
            "gradle.beforeProject { project ->",
            "  project.plugins.withId('org.jetbrains.kotlin.multiplatform') {",
            "    project.afterEvaluate {",
        )
        if (configuration == "optimized-opt") {
            lines.addAll(
                listOf(
                    "    def nativeTarget = project.kotlin.targets.findByName('TARGET')",
                    "    if (nativeTarget != null) {",
                    "      def kind = nativeTarget.binaries.getTest('DEBUG').buildType",
                    "      nativeTarget.binaries.test([kind.class.valueOf('RELEASE')])",
                    "      def release = nativeTarget.binaries.getTest('RELEASE')",
                    "      project.tasks.matching { it.name == 'TARGETTest' }.configureEach { task ->",
                    "        task.dependsOn('linkReleaseTest' + 'TARGET'.capitalize())",
                    "        task.executable(release.outputFile)",
                    "      }",
                    "    }",
                ),
            )
        }
        if (!simulatorUdid.isNullOrEmpty()) {
            if (!Regex("[0-9A-Fa-f-]{36}").matches(simulatorUdid)) {
                throw IllegalArgumentException("simulator UDID is invalid")
            }
            lines.addAll(
                listOf(
                    "    project.tasks.matching { it.name == 'TARGETTest' }.configureEach { task ->",
                    "      task.device.set('$simulatorUdid')",
                    "    }",
                ),
            )
        }
        lines.addAll(listOf("    }", "  }", "}", ""))
        return lines.joinToString("\n").replace("TARGET", target)
    }

    /** `graph_script`: the generated init script that prints the resolved consumer graph. */
    fun graphScript(target: String): String {
        val configuration = if (target == "jsSafari") "jsCompileClasspath" else "${target}CompileKlibraries"
        return listOf(
            "import groovy.json.JsonOutput",
            "import java.security.MessageDigest",
            "gradle.beforeProject { project ->",
            "  project.tasks.register('qualificationResolvedGraph') { task ->",
            "    task.doLast {",
            "      def conf = project.configurations.getByName('$configuration')",
            "      def components = conf.incoming.resolutionResult.allComponents.collect { it.id.displayName }.sort()",
            "      def artifacts = conf.resolvedConfiguration.resolvedArtifacts.collect { artifact ->",
            "        def bytes = artifact.file.bytes",
            "        [component: artifact.moduleVersion.id.toString(), file: artifact.file.absolutePath,",
            "         name: artifact.file.name, size: bytes.length,",
            "         sha256: MessageDigest.getInstance('SHA-256').digest(bytes).encodeHex().toString()]",
            "      }.sort { a, b -> a.component <=> b.component ?: a.name <=> b.name }",
            "      println('DYN4K_RESOLVED_GRAPH=' + JsonOutput.toJson([configuration: '$configuration',",
            "        gradle_user_home: gradle.gradleUserHomeDir.absolutePath,",
            "        components: components, artifacts: artifacts]))",
            "    }",
            "  }",
            "}",
            "",
        ).joinToString("\n")
    }

    /**
     * `safari_config_input`: the Karma input path the generated configuration selects.
     *
     * The reference locates the settings object with `json.JSONDecoder.raw_decode` at the pinned
     * prefix, so the scanner accepts any JSON value there and reads `files[1]`.
     */
    fun safariConfigInput(data: ByteArray): String {
        val prefix = "\nmodule.exports = function(config) {\n\nconfig.set("
        val source = SafariReporter.decodeUtf8(data)
            ?: throw IllegalArgumentException("Safari generated Karma config is not UTF-8")
        if (!source.startsWith(prefix)) {
            throw IllegalArgumentException("Safari generated Karma config shape differs")
        }
        val end = JsonValueEnd.scan(source, prefix.length)
        val settings = StrictJson.load(source.substring(prefix.length, end))
        val files = (settings as? JsonObject)?.get("files")
            ?: throw IllegalArgumentException("Safari generated Karma config has no files setting")
        // Python evaluates `settings["files"][1]` with the container's own indexing, so a string
        // setting yields its second character and a list yields its second element.
        return when (files) {
            is JsonArray -> {
                val element = files.getOrNull(1)
                    ?: throw IllegalArgumentException("list index out of range")
                Py.str(element)
                    ?: throw IllegalArgumentException(
                        "Safari generated Karma config input is not a string",
                    )
            }
            is JsonPrimitive -> {
                if (!files.isString) {
                    throw IllegalArgumentException("string indices must be integers")
                }
                if (files.content.length <= 1) {
                    throw IllegalArgumentException("string index out of range")
                }
                files.content[1].toString()
            }
            else -> throw IllegalArgumentException("string indices must be integers")
        }
    }

    /** `safari_product_paths`: the compiler product and the Karma input of one Safari project. */
    fun safariProductPaths(project: String, configuration: String, name: String): SafariProductPaths {
        val configs = CONFIGS["jsSafari"] ?: emptyList()
        if (configuration !in configs || name !in setOf("dyn4k-core", "dyn4k", "consumer")) {
            throw IllegalArgumentException("unknown Safari product selection")
        }
        val relative = if (name == "consumer") SafariReporter.CONSUMER else name
        val packageName = SafariReporter.PACKAGES[relative]
            ?: throw IllegalArgumentException("unknown Safari reporter project: $relative")
        val root = posixNormalize(project)
        val buildRoot = if (name == "consumer") root else posixParent(root)
        val mode = if (configuration == "production") "Production" else "Development"
        val expected = posixJoin(
            root, "build/compileSync/js/test", "test${mode}Executable/kotlin",
            "$packageName.js",
        )
        val karmaPackage = posixJoin(buildRoot, "build/js/packages", packageName)
        val karmaInput = if (configuration == "production") {
            expected
        } else {
            posixJoin(karmaPackage, "kotlin", "$packageName.js")
        }
        return SafariProductPaths(expected, karmaInput, buildRoot, karmaPackage)
    }

    /**
     * `verify_safari_mode_arguments`: the browser and production mode properties a command line
     * carries must be exactly the required ones, in the one spelling the reference writes.
     */
    fun verifySafariModeArguments(command: List<String?>, processName: String, config: String? = null) {
        for ((propertyName, mode, required) in listOf(
            Triple("qualificationSafari", "browser", processName == "consumer"),
            Triple(
                "qualificationProduction",
                "production",
                config == "production" && processName in setOf("source", "consumer"),
            ),
        )) {
            val prefixes = listOf(
                "-P$propertyName",
                "--project-prop=$propertyName",
                "-Dorg.gradle.project.$propertyName",
                "--system-prop=org.gradle.project.$propertyName",
                "org.gradle.project.$propertyName",
            )
            val observed = command.filterIsInstance<String>().filter { argument ->
                prefixes.any { argument.startsWith(it) } || argument == propertyName ||
                    argument.startsWith("$propertyName=")
            }
            val expected = if (required) listOf("-P$propertyName=true") else emptyList()
            if (observed != expected) {
                throw IllegalArgumentException("Safari $processName $mode mode differs")
            }
        }
    }

    /**
     * `verify_report_group`: the lane's recorded case identities and report digests must be the
     * archived ones, and every report must sit under the module's XML prefix.
     */
    fun verifyReportGroup(
        group: JsonObject?,
        checked: HostedReportCheck,
        prefix: List<String>,
    ) {
        if (group == null ||
            !Py.equalsInt(group["expected"], checked.expected.toLong()) ||
            !Py.equalsInt(group["executed"], checked.executed.toLong()) ||
            !caseIdsEqual(group["case_ids"], checked.caseIds)
        ) {
            throw IllegalArgumentException("archived case identities differ from source inventory")
        }
        val reports = group["reports"] as? JsonArray
        if (reports == null || reports.size != checked.reports.size) {
            throw IllegalArgumentException("archived XML report inventory differs")
        }
        val actual = LinkedHashMap<String, JsonObject>()
        for (item in checked.reports) {
            val path = Py.str(item["path"]) ?: continue
            actual[path] = item
        }
        if (actual.size != reports.size) {
            throw IllegalArgumentException("duplicate archived XML report")
        }
        for (element in reports) {
            val item = element as? JsonObject
                ?: throw IllegalArgumentException("archived XML path or report identity differs")
            val asPosix = archiveName(Py.str(item["path"]))
            val parts = asPosix.split('/').filter { it.isNotEmpty() }
            if (parts.take(prefix.size) != prefix || asPosix !in actual) {
                throw IllegalArgumentException("archived XML path or report identity differs")
            }
            val found = actual.getValue(asPosix)
            if (item["sha256"] != found["sha256"] || item["modified_ns"] != found["modified_ns"]) {
                throw IllegalArgumentException("archived XML differs from receipt")
            }
        }
    }

    private fun caseIdsEqual(value: kotlinx.serialization.json.JsonElement?, expected: List<String>): Boolean {
        val actual = (value as? JsonArray) ?: return false
        if (actual.size != expected.size) return false
        for ((index, item) in actual.withIndex()) {
            if (Py.str(item) != expected[index]) return false
        }
        return true
    }

    /** `float(value)` for the spellings Python accepts in a report timestamp. */
    internal fun pythonFloat(text: String): Double? {
        val trimmed = text.trim()
        return when (trimmed.lowercase()) {
            "nan", "+nan", "-nan" -> Double.NaN
            "inf", "+inf", "infinity", "+infinity" -> Double.POSITIVE_INFINITY
            "-inf", "-infinity" -> Double.NEGATIVE_INFINITY
            else -> trimmed.toDoubleOrNull()
        }
    }

    /** `str.splitlines(keepends=True)` for the line boundaries Python recognises. */
    internal fun splitLinesKeepingEnds(text: String): List<String> {
        val rows = mutableListOf<String>()
        var start = 0
        var index = 0
        while (index < text.length) {
            val char = text[index]
            val width = when {
                char == '\r' -> if (index + 1 < text.length && text[index + 1] == '\n') 2 else 1
                char == '\n' || char == '\u000B' || char == '\u000C' || char == '\u001C' ||
                    char == '\u001D' || char == '\u001E' || char == '\u0085' ||
                    char == '\u2028' || char == '\u2029' -> 1
                else -> 0
            }
            if (width == 0) {
                index++
                continue
            }
            rows.add(text.substring(start, index + width))
            index += width
            start = index
        }
        if (start < text.length) rows.add(text.substring(start))
        return rows
    }

    /** `str(Path(a) / b)` for the POSIX hosts the Safari lane runs on. */
    internal fun posixJoin(base: String, vararg parts: String): String {
        var result = base
        for (part in parts) {
            if (part.isEmpty() || part == ".") continue
            result = if (result.isEmpty()) part else result.trimEnd('/') + "/" + part
        }
        return result
    }

    /** `str(Path(text))` for a POSIX path: collapse repeated and trailing separators. */
    internal fun posixNormalize(text: String): String {
        if (text.isEmpty()) return "."
        val absolute = text.startsWith("/")
        val kept = mutableListOf<String>()
        for (part in text.split('/')) {
            when (part) {
                "", "." -> Unit
                ".." -> if (kept.isNotEmpty() && kept.last() != "..") kept.removeAt(kept.size - 1)
                else if (!absolute) kept.add("..")
                else -> kept.add(part)
            }
        }
        if (kept.isEmpty()) return if (absolute) "/" else "."
        return (if (absolute) "/" else "") + kept.joinToString("/")
    }

    /** `str(Path(text).parent)`. */
    internal fun posixParent(text: String): String {
        val normalized = posixNormalize(text)
        if (normalized == "/") return "/"
        val index = normalized.lastIndexOf('/')
        return if (index < 0) "." else if (index == 0) "/" else normalized.substring(0, index)
    }
}

/** The locating half of `json.JSONDecoder.raw_decode`, for the generated Karma configuration. */
private object JsonValueEnd {
    fun scan(text: String, start: Int): Int {
        val end = value(text, start)
        return end
    }

    private fun whitespace(text: String, index: Int): Int {
        var current = index
        while (current < text.length && text[current].let { it == ' ' || it == '\t' || it == '\n' || it == '\r' }) {
            current++
        }
        return current
    }

    private fun value(text: String, start: Int): Int {
        var index = whitespace(text, start)
        if (index >= text.length) throw IllegalArgumentException("Safari Karma config value is absent")
        return when (text[index]) {
            '{' -> obj(text, index)
            '[' -> array(text, index)
            '"' -> string(text, index)
            't' -> literal(text, index, "true")
            'f' -> literal(text, index, "false")
            'n' -> literal(text, index, "null")
            else -> number(text, index)
        }
    }

    private fun obj(text: String, start: Int): Int {
        var index = whitespace(text, start + 1)
        if (index < text.length && text[index] == '}') return index + 1
        while (true) {
            index = whitespace(text, index)
            if (index >= text.length || text[index] != '"') {
                throw IllegalArgumentException("Safari Karma config object is malformed")
            }
            index = string(text, index)
            index = whitespace(text, index)
            if (index >= text.length || text[index] != ':') {
                throw IllegalArgumentException("Safari Karma config object is malformed")
            }
            index = value(text, index + 1)
            index = whitespace(text, index)
            if (index >= text.length) throw IllegalArgumentException("Safari Karma config object is malformed")
            when (text[index]) {
                ',' -> index++
                '}' -> return index + 1
                else -> throw IllegalArgumentException("Safari Karma config object is malformed")
            }
        }
    }

    private fun array(text: String, start: Int): Int {
        var index = whitespace(text, start + 1)
        if (index < text.length && text[index] == ']') return index + 1
        while (true) {
            index = value(text, index)
            index = whitespace(text, index)
            if (index >= text.length) throw IllegalArgumentException("Safari Karma config array is malformed")
            when (text[index]) {
                ',' -> index++
                ']' -> return index + 1
                else -> throw IllegalArgumentException("Safari Karma config array is malformed")
            }
        }
    }

    private fun string(text: String, start: Int): Int {
        var index = start + 1
        while (index < text.length) {
            when (text[index]) {
                '\\' -> index += 2
                '"' -> return index + 1
                else -> index++
            }
        }
        throw IllegalArgumentException("Safari Karma config string is unterminated")
    }

    private fun literal(text: String, start: Int, literal: String): Int {
        if (!text.startsWith(literal, start)) {
            throw IllegalArgumentException("Safari Karma config value is malformed")
        }
        return start + literal.length
    }

    private fun number(text: String, start: Int): Int {
        var index = start
        if (index < text.length && text[index] == '-') index++
        while (index < text.length && text[index] in '0'..'9') index++
        if (index < text.length && text[index] == '.') {
            index++
            while (index < text.length && text[index] in '0'..'9') index++
        }
        if (index < text.length && (text[index] == 'e' || text[index] == 'E')) {
            index++
            if (index < text.length && (text[index] == '+' || text[index] == '-')) index++
            while (index < text.length && text[index] in '0'..'9') index++
        }
        if (index == start) throw IllegalArgumentException("Safari Karma config value is malformed")
        return index
    }
}
