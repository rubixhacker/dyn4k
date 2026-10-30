package io.github.rubixhacker.harness.contract

/** One entry of a variant's dependency set. */
data class VariantDependency(val group: String, val module: String, val version: String)

/** The `available-at` pointer of a metadata variant. */
data class VariantAvailableAt(
    val group: String,
    val module: String,
    val version: String,
    val url: String,
)

/** One variant of a Gradle module metadata publication. */
data class PublicationVariant(
    val name: String,
    val kind: String,
    val target: String?,
    val dependencies: Set<VariantDependency>,
    val url: String? = null,
    val fileName: String? = null,
    val availableAt: VariantAvailableAt? = null,
)

/** One dependency row of a POM file. */
data class PomDependency(
    val group: String,
    val module: String,
    val version: String,
    val scope: String,
)

/** One variant of the POM metadata contract. */
data class PomMetadata(
    val name: String,
    val description: String,
    val url: String,
    val licenseName: String,
    val licenseUrl: String,
    val developerId: String,
    val developerName: String,
    val scmUrl: String,
)

/**
 * Publication metadata contracts of `qualify.py`.
 *
 * Retained evidence records these values. A change invalidates the evidence that recorded them.
 */
object PublicationContract {
    private val descriptions = mapOf(
        "dyn4k-core" to ("dyn4k core" to "Kotlin Multiplatform dyn4j 6.0.0 compatible foundation"),
        "dyn4k" to ("dyn4k" to "Kotlin conveniences for the dyn4k core"),
    )

    private const val PROJECT_URL = "https://github.com/rubixhacker/dyn4k"
    private const val LICENSE_NAME = "BSD 3-Clause License"
    private const val LICENSE_URL = "https://opensource.org/licenses/BSD-3-Clause"
    private const val DEVELOPER_ID = "rubixhacker"
    private const val DEVELOPER_NAME = "Stewart Boling"

    /** Returns the variants of one publication, keyed by variant name in publication order. */
    fun variants(module: String, target: String?): Map<String, PublicationVariant> {
        val name = if (target == null) module else Qualification.targetPublicationName(module, target)
        val base = "$name-${Qualification.VERSION}"
        val prefix = target ?: "metadata"
        val published = if (target == null) "" else "-published"

        fun dependencyModule(dependencyTarget: String?): String =
            if (dependencyTarget == null) {
                module
            } else {
                Qualification.targetPublicationName(module, dependencyTarget)
            }

        fun variant(
            kind: String,
            url: String? = null,
            fileName: String? = null,
            library: Boolean = false,
        ): PublicationVariant {
            val dependencies = if (library) {
                buildSet {
                    add(VariantDependency("org.jetbrains.kotlin", "kotlin-stdlib", Qualification.KOTLIN_VERSION))
                    if (target == "js") {
                        add(VariantDependency("org.jetbrains.kotlin", "kotlin-dom-api-compat", Qualification.KOTLIN_VERSION))
                    }
                    if (module == "dyn4k") {
                        add(VariantDependency(Qualification.GROUP, "dyn4k-core", Qualification.VERSION))
                    }
                }
            } else {
                emptySet()
            }
            return PublicationVariant(
                name = "$prefix${kind}Elements$published",
                kind = kind,
                target = target,
                dependencies = dependencies,
                url = url,
                fileName = if (url != null) fileName ?: url else null,
            )
        }

        val binary = Qualification.publicationBinaryPath(module, target).substringAfterLast('/')
        val binaryName = when {
            target == null -> "$module-metadata-${Qualification.VERSION}.jar"
            target == "android" -> "$module.aar"
            target !in setOf("jvm", "js", "wasmJs", "wasmWasi") ->
                "$module-${target}Main-${Qualification.VERSION}.klib"
            else -> binary
        }
        val sources = "$base-sources.jar"
        val sourceName = if (target == null) "$module-kotlin-${Qualification.VERSION}-sources.jar" else sources

        val variants = mutableListOf(
            variant("Api", binary, binaryName, library = true),
            variant("Sources", sources, sourceName),
        )
        if (target in setOf("jvm", "android", "js", "wasmJs", "wasmWasi")) {
            variants.add(1, variant("Runtime", binary, binaryName, library = true))
        }
        if (target != null && Qualification.isAppleTarget(target)) {
            val metadata = "$base-metadata.jar"
            variants.add(variant("Metadata", metadata, metadata, library = true))
        }
        if (target == null) {
            for (mapped in Qualification.matrixTargets()) {
                val mappedName = Qualification.targetPublicationName(module, mapped)
                val available = VariantAvailableAt(
                    group = Qualification.GROUP,
                    module = mappedName,
                    version = Qualification.VERSION,
                    url = "../../$mappedName/${Qualification.VERSION}/$mappedName-${Qualification.VERSION}.module",
                )
                val kinds = buildList {
                    add("Api")
                    add("Sources")
                    if (mapped in setOf("jvm", "android", "js", "wasmJs", "wasmWasi")) add("Runtime")
                    if (Qualification.isAppleTarget(mapped)) add("Metadata")
                }
                for (kind in kinds) {
                    val entry = PublicationVariant(
                        name = "${mapped}${kind}Elements-published",
                        kind = kind,
                        target = mapped,
                        dependencies = emptySet(),
                        availableAt = available,
                    )
                    variants.add(entry)
                }
            }
        }
        return LinkedHashMap<String, PublicationVariant>().apply {
            for (entry in variants) put(entry.name, entry)
        }
    }

    /** Returns the POM dependency rows of one publication. */
    fun pomDependencies(module: String, target: String?): Set<PomDependency> {
        val stdlib = when (target) {
            "js" -> "kotlin-stdlib-js"
            "wasmJs" -> "kotlin-stdlib-wasm-js"
            "wasmWasi" -> "kotlin-stdlib-wasm-wasi"
            else -> "kotlin-stdlib"
        }
        val scope = if (target == null) "runtime" else "compile"
        val dependencies = linkedSetOf(
            PomDependency("org.jetbrains.kotlin", stdlib, Qualification.KOTLIN_VERSION, scope),
        )
        if (target == "js") {
            dependencies.add(
                PomDependency("org.jetbrains.kotlin", "kotlin-dom-api-compat", Qualification.KOTLIN_VERSION, scope),
            )
        }
        if (module == "dyn4k") {
            val core = if (target == null) "dyn4k-core" else Qualification.targetPublicationName("dyn4k-core", target)
            dependencies.add(PomDependency(Qualification.GROUP, core, Qualification.VERSION, scope))
        }
        return dependencies
    }

    /** Returns the POM metadata values of one module. */
    fun pomMetadata(module: String): PomMetadata {
        val (title, description) = descriptions.getValue(module)
        return PomMetadata(
            name = title,
            description = description,
            url = PROJECT_URL,
            licenseName = LICENSE_NAME,
            licenseUrl = LICENSE_URL,
            developerId = DEVELOPER_ID,
            developerName = DEVELOPER_NAME,
            scmUrl = PROJECT_URL,
        )
    }
}
