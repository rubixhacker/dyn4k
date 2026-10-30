package io.github.rubixhacker.harness.migration

import kotlinx.serialization.json.Json

/** The recorded Python outputs, parsed with Python's JSON types. */
internal object VectorData {
    private val json = Json { allowSpecialFloatingPointValues = true }

    val root: PyValue.Map = pyFromJson(json.parseToJsonElement(MigrationVectors.json)) as PyValue.Map

    fun section(name: String): PyValue = root.get(name)
}
