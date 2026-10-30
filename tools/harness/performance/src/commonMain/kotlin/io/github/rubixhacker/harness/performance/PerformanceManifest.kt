package io.github.rubixhacker.harness.performance

import io.github.rubixhacker.harness.contract.CanonicalJson
import io.github.rubixhacker.harness.contract.Sha256
import io.github.rubixhacker.harness.contract.StrictJson
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.add
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put

/**
 * The frozen performance policy: `tools/performance/manifest.py`.
 *
 * Every literal here is an approved measurement decision. Changing a value changes a frozen
 * digest that qualified evidence cites, so the values are transcribed rather than derived.
 */
object PerformanceManifest {
    const val V1_MANIFEST_SHA256: String =
        "18cca97bbf1fc939eda669efe2344bbfe06c416a735ca8cc5184d5ba2519176a"

    const val POLICY_URL: String = "https://github.com/rubixhacker/dyn4k/issues/8#issuecomment-5674480273"
    const val SOURCE_COMMIT: String = "058bf6d982a0fb89b54050f929f6ea9dae53b714"
    const val BASELINE_JAR_SHA256: String =
        "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e"
    const val BASELINE_SOURCE_ARCHIVE_SHA256: String =
        "83b47be47bdce27681139dab84937e0f586b70ab800dc494fbebed4b58893223"

    /** Target to runtime families, in the approved order. */
    val targetRows: Map<String, List<String>> = linkedMapOf(
        "jvm" to listOf("java"),
        "android" to listOf("android_jvm"),
        "js" to listOf("chromium", "firefox", "safari", "node"),
        "wasmJs" to listOf("chromium", "firefox", "safari", "node"),
        "wasmWasi" to listOf("node", "wasmtime"),
        "linuxX64" to listOf("linux_x64"),
        "linuxArm64" to listOf("linux_arm64"),
        "mingwX64" to listOf("windows_x64"),
        "macosArm64" to listOf("macos_arm64"),
        "iosArm64" to listOf("ios_device"),
        "iosSimulatorArm64" to listOf("ios_simulator_arm64"),
        "iosX64" to listOf("ios_simulator_x64"),
        "tvosArm64" to listOf("tvos_device"),
        "tvosSimulatorArm64" to listOf("tvos_simulator"),
        "watchosArm64" to listOf("watchos_ilp32_device"),
        "watchosDeviceArm64" to listOf("watchos_lp64_device"),
        "watchosSimulatorArm64" to listOf("watchos_simulator"),
        "androidNativeArm32" to listOf("android_arm32"),
        "androidNativeArm64" to listOf("android_arm64"),
        "androidNativeX86" to listOf("android_x86"),
        "androidNativeX64" to listOf("android_x64"),
    )

    val sizes: Map<String, Map<String, Int>> = linkedMapOf(
        "separated" to linkedMapOf("small" to 100, "medium" to 1000, "stress" to 10000),
        "pile" to linkedMapOf("small" to 100, "medium" to 500, "stress" to 2000),
        "joint" to linkedMapOf("small" to 50, "medium" to 250, "stress" to 1000),
        "ccd" to linkedMapOf("small" to 25, "medium" to 100, "stress" to 500),
        "lifecycle" to linkedMapOf("small" to 100, "medium" to 1000, "stress" to 5000),
    )

    val jointModes: Map<String, List<String>> = linkedMapOf(
        "Angle" to listOf("free", "limits", "ratio"),
        "Distance" to listOf("rigid", "limits", "spring", "spring_damper"),
        "Friction" to listOf("friction"),
        "Motor" to listOf("offset"),
        "Pin" to listOf("spring", "spring_damper"),
        "Prismatic" to listOf("free", "limits", "motor", "spring", "spring_damper"),
        "Pulley" to listOf("taut", "ratio", "slack"),
        "Revolute" to listOf("free", "limits", "motor"),
        "Weld" to listOf("rigid", "limits", "spring", "spring_damper"),
        "Wheel" to listOf("spring", "spring_damper", "limits", "motor"),
        "Mixed" to listOf("all_types"),
    )

    val jointParameters: JsonObject = buildJsonObject {
        put("anchor_rectangle_m", buildJsonArray { add(0.25); add(0.25) })
        put("anchor_center_m", "(3*i,3)")
        put("dynamic_center_m", "(3*i,2)")
        put("paired_anchor_m", "(3*i,2.5)")
        put("prismatic_wheel_axis", buildJsonArray { add(1.0); add(0.0) })
        put("angle_limit_rad", buildJsonArray { add(-0.5); add(0.5) })
        put("linear_limit_m", buildJsonArray { add(-0.5); add(0.5) })
        put("distance_limit_m", buildJsonArray { add(0.8); add(1.2) })
        put("ratio", 2.0)
        put("spring_frequency_hz", 4.0)
        put("spring_damping_ratio", 0.5)
        put("motor_speed_rad_or_m_per_s", 1.0)
        put("maximum_motor_force_n", 10.0)
        put("maximum_motor_torque_nm", 10.0)
        put("friction_maximum_force_n", 10.0)
        put("friction_maximum_torque_nm", 10.0)
        put("motor_linear_target_m", buildJsonArray { add(0.0); add(1.0) })
        put("motor_angular_target_rad", 0.25)
        put("periodic_angular_impulse_kg_m2_per_s", 0.01)
        put("pulley_anchors_m", "(3*i-1,5) and (3*i+1,5)")
        put(
            "mixed_default_modes",
            buildJsonObject {
                put("Angle", "free")
                put("Distance", "rigid")
                put("Friction", "friction")
                put("Motor", "offset")
                put("Pin", "spring")
                put("Prismatic", "free")
                put("Pulley", "taut")
                put("Revolute", "free")
                put("Weld", "rigid")
                put("Wheel", "spring")
            },
        )
    }

    val ratesHz: List<Int> = listOf(30, 60, 120)
    val apiSurfaces: List<String> = listOf("baseline", "direct_kotlin", "compatibility")

    const val BLOCKER: String =
        "Pin and verify a compatible host or device, runtime, ABI, and probes before measurement."

    fun buildConfig(target: String): String = when {
        target == "jvm" -> "default Kotlin bytecode optimization"
        target == "android" -> "R8-optimized consumer application from single-variant AAR"
        target in setOf("js", "wasmJs", "wasmWasi") -> "PRODUCTION linked output; Binaryen optimized for Wasm"
        else -> "Kotlin/Native -opt"
    }

    fun developmentConfig(target: String): String = when {
        target == "jvm" -> "Kotlin -Xno-optimize"
        target == "android" -> "debug consumer application from single-variant AAR"
        target in setOf("js", "wasmJs", "wasmWasi") -> "DEVELOPMENT linked output"
        else -> "Kotlin/Native -g"
    }

    fun minimumPolicy(target: String, runtime: String): String {
        if (target == "jvm") return "Java 8"
        if (target == "android" || target.startsWith("androidNative")) return "Android API 21"
        if (target == "js" || target == "wasmJs") {
            return when (runtime) {
                "chromium" -> "Chromium 119"
                "firefox" -> "Firefox 120"
                "safari" -> "Safari 18.2"
                "node" -> "Node.js 22.0.0"
                else -> throw NoSuchElementException(runtime)
            }
        }
        if (target == "wasmWasi") {
            return if (runtime == "node") {
                "Node.js 24.15.0 without experimental Wasm flags"
            } else {
                "Wasmtime 37.0.0 with -W gc=y -W exceptions=y -W function-references=y"
            }
        }
        if (target == "linuxX64") return "Linux kernel 4.9.156, glibc 2.19"
        if (target == "linuxArm64") return "Linux kernel 4.9.156, glibc 2.25"
        if (target == "mingwX64") return "Windows 10 1507, build family 10240"
        if (target == "macosArm64") return "macOS 11 with deployment override"
        if (target.startsWith("ios")) return "iOS 15"
        if (target.startsWith("tvos")) return "tvOS 15"
        if (target == "watchosDeviceArm64") return "watchOS 26"
        if (target.startsWith("watchos")) return "watchOS 8"
        throw IllegalArgumentException("no minimum policy for $target")
    }

    fun gates(target: String, runtime: String): Map<String, String> {
        val medium = !(target.startsWith("tvos") || target.startsWith("watchos"))
        return linkedMapOf(
            "small" to "absolute",
            "medium" to if (medium) "absolute" else "report_only",
            "stress" to "report_only",
        )
    }

    /** The 28 runtime rows, in the approved order. */
    fun runtimeRows(): List<JsonObject> {
        val output = mutableListOf<JsonObject>()
        for ((target, runtimes) in targetRows) {
            for (runtime in runtimes) {
                output.add(
                    buildJsonObject {
                        put("id", "$target.$runtime")
                        put("target", target)
                        put("runtime_family", runtime)
                        put("optimized_build", buildConfig(target))
                        put("development_build", developmentConfig(target))
                        put("minimum_policy", minimumPolicy(target, runtime))
                        put("minimum_tested_patch", JsonNull)
                        put("current_tested_version", JsonNull)
                        put(
                            "size_assignment",
                            buildJsonObject {
                                for ((size, gate) in gates(target, runtime)) put(size, gate)
                            },
                        )
                        put("representative_hardware", JsonNull)
                        put("runtime_version", JsonNull)
                        put("abi", JsonNull)
                        put("environment_status", "unavailable")
                        put("probe_status", "unvalidated")
                        put("blocker", BLOCKER)
                    },
                )
            }
        }
        return output
    }

    /** The 999 workload scenarios, in the approved order. */
    fun scenarios(): List<JsonObject> {
        val output = mutableListOf<JsonObject>()
        for ((family, sizeCounts) in sizes) {
            val variants = when (family) {
                "joint" -> jointModes.flatMap { (joint, modes) ->
                    modes.map { mode -> "${joint.lowercase()}_$mode" }
                }
                "lifecycle" -> listOf("settle", "wake", "replace")
                else -> listOf("default")
            }
            for (variant in variants) {
                for ((size, count) in sizeCounts) {
                    for (hz in ratesHz) {
                        for (api in apiSurfaces) {
                            output.add(
                                buildJsonObject {
                                    put("id", "$family.$variant.$size.${hz}hz.$api")
                                    put("family", family)
                                    put("variant", variant)
                                    put("size", size)
                                    put("dynamic_bodies", count)
                                    put("rate_hz", hz)
                                    put("api", api)
                                },
                            )
                        }
                    }
                }
            }
        }
        return output
    }

    private fun fixture(): JsonObject = buildJsonObject {
        put("version", "performance-v1")
        put("seed", 17017)
        put("gravity_m_per_s2", buildJsonArray { add(0.0); add(-9.8) })
        put(
            "dynamic_shape",
            "circle radius 0.25 m, one fixture per body; density 1 kg/m^2, friction 0.5, restitution 0.0",
        )
        put(
            "static_shape",
            "rectangles with density 1 kg/m^2, friction 0.5, restitution 0; floor width 200 m and " +
                "thickness 1 m centered at (0,-0.5) m for pile and lifecycle",
        )
        put(
            "separated",
            "Grid pitch 3 m, 32 columns, starting (-48,2) m; zero gravity; all bodies have velocity " +
                "(0.75,0.0) m/s; wrap by deterministic translation at x=48 m.",
        )
        put(
            "pile",
            "10 columns; circle centers at x=(column-4.5)*0.48 m and y=0.3+row*0.48 m; zero initial " +
                "velocity; floor contact and gravity active.",
        )
        put(
            "joint",
            "One dynamic circle and one static 0.25 m square anchor per mechanism at x=3*i m. Disable " +
                "at-rest detection for the dynamic circles. Mixed rotates the ten types by index. " +
                "Apply linear impulse (0.5,1.0) kg*m/s and angular impulse 0.01 kg*m^2/s to every " +
                "dynamic body once per simulated second. Mode parameters are fixed in the harness.",
        )
        put(
            "ccd",
            "Two static walls, width 0.5 m and height 20 m, centered at x=-10 and x=10 m. Bullet " +
                "circles alternate direction at 18 m/s from x=+-8 m, y=0.5+(index%20)*0.45 m. Reset at " +
                "crossing to maintain repeated CCD opportunities.",
        )
        put(
            "lifecycle",
            "10-column pile with the same floor. Every tenth dynamic body has a distance joint to the " +
                "floor at both centers. Settle has no imposed wake. Wake applies impulse (0.2,0.5) " +
                "kg*m/s to every tenth body once per simulated second. Replace removes and recreates " +
                "ceil(1% of bodies) once per simulated second, starting at (17017 + elapsed whole " +
                "seconds) modulo body count, with the same indexed positions and constant body and " +
                "joint counts. Removal includes fixture and joint cleanup.",
        )
        put("callback", "Contact begin/end counters, without logging in timed steps; record counts after each step.")
        put(
            "diagnostics",
            "After timed stepping, record aggregate absolute linear and angular speed each step. Count " +
                "full broad-phase candidate pairs using detectIterator(true), and active contact " +
                "pairs/points, on the first step of each simulated second and the final step. Use -1 " +
                "for unsampled pair counts; never interpret it as zero.",
        )
        put("solver", "dyn4j 6.0.0 defaults; do not change iteration or sleep settings")
    }

    private fun budgets(): JsonObject = buildJsonObject {
        put(
            "jvm_vs_baseline",
            buildJsonObject {
                put("median_ratio_max", 1.10)
                put("p99_ratio_max", 1.20)
                put("compute_per_simulated_second_ratio_max", 1.10)
                put("retained_heap_ratio_max", 1.10)
                put("steady_allocation_ratio_max", 1.10)
                put("construction_or_replacement_allocation_ratio_max", 1.15)
            },
        )
        put(
            "shim_vs_direct",
            buildJsonObject {
                put("median_ratio_max", 1.05)
                put("total_compute_ratio_max", 1.05)
                put("p99_ratio_max", 1.10)
                put("adaptation_allocation_bytes_max", 0)
            },
        )
        put("absolute_p99_seconds", buildJsonObject {
            put("30", "1/120")
            put("60", "1/240")
            put("120", "1/480")
        })
        put("incremental_peak_mib", buildJsonObject { put("small", 16); put("medium", 64) })
        put("mib_bytes", 1048576)
    }

    private fun sustained(): JsonObject = buildJsonObject {
        put("measured_wall_seconds", 600)
        put("fresh_process_repetitions", 3)
        put("final_window_seconds", 60)
        put("create_use_dispose_cycles", 100)
        put("equal_simulated_duration", true)
        put("paced_no_dropped_steps", true)
        put("timing_and_memory_separate_processes", true)
        put("warmup_outside_measurement", true)
    }

    private fun measurementMethod(): JsonObject = buildJsonObject {
        put(
            "warmup",
            "Pace at intended cadence for at least 120 wall seconds. Use 30-second windows. The last " +
                "three window medians must each be within 5% of their median. Reset the fixture after " +
                "warm-up in the same process. If no convergence by 600 wall seconds, mark inconclusive.",
        )
        put(
            "timer",
            "Monotonic nanoTime. Measure paired-call positive resolution and median/p99 overhead with " +
                "10,000 calls. Keep pauses inside measured step elapsed time. Do not subtract overhead " +
                "from gate samples.",
        )
        put(
            "sampling",
            "Store every step with mutation time, lateness, allocation, heap, RSS, awake bodies, " +
                "contact starts and ends, and TOI events. Keep event-only full and final-minute " +
                "latency distributions. No dropped steps or hidden invalid runs.",
        )
        put(
            "noise",
            "Before candidate runs, obtain three fresh-process pairs of unchanged baseline at each " +
                "reference environment and workload. Balance pair order. Use one-second paired blocks " +
                "and 2,000 deterministic bootstrap draws, seed 17017. Retain each pair interval and its " +
                "raw series.",
        )
        put(
            "confidence",
            "The upper bound of a two-sided 95% block-bootstrap ratio interval must be at or below each " +
                "relative limit. Evaluate each run and its final minute separately. A crossing interval " +
                "is inconclusive.",
        )
        put(
            "tail",
            "Report p99 only with its event count. If an event-only final-minute series has fewer than " +
                "100 events, use the full-run distribution for tail context and mark the final-minute " +
                "tail inconclusive.",
        )
        put(
            "plateau",
            "After warm-up, run 100 create/use/dispose cycles. Record post-collection live heap, " +
                "resident process bytes, and collection count. Compare cycles 20-39 with 80-99; drift " +
                "above 5% or absent reclamation is inconclusive or failing, pending probe attribution.",
        )
        put(
            "run_order",
            "Use three fresh matched processes per API. Rotate the order baseline/direct/compatibility, " +
                "direct/compatibility/baseline, compatibility/baseline/direct so each API occupies every " +
                "position once. Retain the order and process identity.",
        )
        put(
            "memory",
            "Profile allocation and memory in separate paced processes using the same event schedule as " +
                "timing. Record construction allocation, post-collection retained heap with the world " +
                "alive, and RSS from empty harness through construction, warm-up, and measurement. Count " +
                "managed, native, and Wasm linear storage once. A process RSS delta is a diagnostic until " +
                "attribution and reserved-memory overhead are validated.",
        )
    }

    /** The complete policy, as `manifest.py emit` writes it. */
    fun manifest(): JsonObject = buildJsonObject {
        put("version", 1)
        put("policy", POLICY_URL)
        put("source_commit", SOURCE_COMMIT)
        put("baseline_jar_sha256", BASELINE_JAR_SHA256)
        put("baseline_source_archive_sha256", BASELINE_SOURCE_ARCHIVE_SHA256)
        put("targets", buildJsonArray { for (target in targetRows.keys) add(target) })
        put("runtime_rows", buildJsonArray { for (row in runtimeRows()) add(row) })
        put("families", buildJsonObject {
            for ((family, counts) in sizes) {
                put(family, buildJsonObject { for ((size, count) in counts) put(size, count) })
            }
        })
        put("joint_modes", buildJsonObject {
            for ((joint, modes) in jointModes) put(joint, buildJsonArray { for (mode in modes) add(mode) })
        })
        put("joint_parameters", jointParameters)
        put("rates_hz", buildJsonArray { for (hz in ratesHz) add(hz) })
        put("api_surfaces", buildJsonArray { for (api in apiSurfaces) add(api) })
        put("scenarios", buildJsonArray { for (scenario in scenarios()) add(scenario) })
        put("fixture", fixture())
        put("budgets", budgets())
        put("sustained", sustained())
        put("measurement_method", measurementMethod())
        put("qualification", "unpassed")
    }

    /** The frozen CCD fixture revision, as `manifest.py emit-ccd-fixture` writes it. */
    fun ccdFixtureRevision(): JsonObject = buildJsonObject {
        put("version", "performance-ccd-v2")
        put("base_manifest_version", 1)
        put("base_manifest_sha256", V1_MANIFEST_SHA256)
        put("family", "ccd")
        put(
            "workload_ids",
            buildJsonArray { for (item in scenarios()) if (item.str("family") == "ccd") add(item.str("id")) },
        )
        put(
            "body_hash",
            buildJsonObject {
                put("algorithm", "zero_based_creation_index")
                put("counter_scope", "each_fixture")
                put("creation_order", buildJsonArray {
                    add("left_wall")
                    add("right_wall")
                    add("bullet_circles_ascending_index")
                })
                put("warmup", "fresh_fixture_resets_counter")
                put("routes", buildJsonArray {
                    add("baseline")
                    add("direct_kotlin")
                    add("compatibility")
                })
                put("other_families", "unchanged")
            },
        )
        put("qualification", "unpassed")
    }

    /**
     * `manifest.validate`: accepts a policy that matches the approved scope exactly and returns
     * the reason it rejects any other.
     */
    fun validate(value: JsonObject) {
        val version = value["version"]?.let { numberOrNull(it) }
        if (version != 1.0) throw IllegalArgumentException("unsupported manifest version")
        val expectedTargets = buildJsonArray { for (target in targetRows.keys) add(target) }
        if (value["targets"] != expectedTargets) {
            throw IllegalArgumentException("target list differs from approved scope")
        }
        val expected = runtimeRows()
        val observed = value["runtime_rows"]?.jsonArray ?: JsonArray(emptyList())
        val observedIds = observed.map { it.jsonObject["id"]?.jsonPrimitive?.content }
        if (observed.size != 28 || observedIds != expected.map { it.str("id") }) {
            throw IllegalArgumentException("runtime row list is incomplete or reordered")
        }
        val families = buildJsonObject {
            for ((family, counts) in sizes) {
                put(family, buildJsonObject { for ((size, count) in counts) put(size, count) })
            }
        }
        val jointModesValue = buildJsonObject {
            for ((joint, modes) in jointModes) put(joint, buildJsonArray { for (mode in modes) add(mode) })
        }
        if (value["families"] != families ||
            value["joint_modes"] != jointModesValue ||
            value["joint_parameters"] != jointParameters
        ) {
            throw IllegalArgumentException("workload sizes or joint modes differ")
        }
        if (value["scenarios"] != JsonArray(scenarios())) {
            throw IllegalArgumentException("workload scenario expansion differs")
        }
        if (value["budgets"] != budgets() ||
            value["sustained"] != sustained() ||
            value["measurement_method"] != measurementMethod()
        ) {
            throw IllegalArgumentException("approved budget or sustained contract differs")
        }
        for ((index, row) in observed.withIndex()) {
            val template = expected[index]
            for (field in listOf(
                "target",
                "runtime_family",
                "optimized_build",
                "development_build",
                "minimum_policy",
                "size_assignment",
            )) {
                if (row.jsonObject[field] != template[field]) {
                    throw IllegalArgumentException(
                        "runtime policy differs: ${row.jsonObject.str("id")} / $field",
                    )
                }
            }
            val status = row.jsonObject["environment_status"]?.jsonPrimitive?.content
            if (status != "available" && status != "unavailable") {
                throw IllegalArgumentException("unknown environment status: ${row.jsonObject.str("id")}")
            }
            if (status == "available") {
                val complete = listOf("representative_hardware", "runtime_version", "abi").all { field ->
                    val element = row.jsonObject[field]
                    element != null && element != JsonNull && element.jsonPrimitive.content.isNotEmpty()
                }
                if (!complete) {
                    throw IllegalArgumentException("available row lacks identity: ${row.jsonObject.str("id")}")
                }
            }
        }
    }

    /**
     * `manifest.validate_ccd_fixture_revision`. The base manifest bytes are supplied by the caller
     * so this stays free of filesystem access.
     */
    fun validateCcdFixtureRevision(baseManifestBytes: ByteArray, value: JsonElement) {
        if (Sha256.of(baseManifestBytes) != V1_MANIFEST_SHA256) {
            throw IllegalArgumentException("base manifest hash differs")
        }
        validate(StrictJson.load(baseManifestBytes.decodeToString()).jsonObject)
        if (value != ccdFixtureRevision()) {
            throw IllegalArgumentException("CCD fixture revision differs from the frozen rule")
        }
    }

    /** The canonical digest of the policy, which qualified evidence cites. */
    fun digest(value: JsonElement = manifest()): String = Sha256.of(CanonicalJson.render(value))
}

internal fun JsonObject.str(key: String): String = getValue(key).jsonPrimitive.content

internal fun JsonObject.int(key: String): Int = getValue(key).jsonPrimitive.int

internal fun JsonObject.long(key: String): Long =
    getValue(key).jsonPrimitive.longOrNull
        ?: throw IllegalArgumentException("not an integer: $key")

internal fun numberOrNull(value: JsonElement): Double? = when (value) {
    is JsonNull -> null
    is JsonPrimitive -> if (value.isString) null else value.content.toDoubleOrNull()
    else -> null
}
