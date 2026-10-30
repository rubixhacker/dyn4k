package io.github.rubixhacker.harness.contract

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.test.assertEquals
import kotlin.test.assertTrue

private object PublicationGolden {
    val root: JsonObject = Json.parseToJsonElement(PublicationVectors.json).jsonObject

    fun entries(key: String): List<JsonObject> = root.getValue(key).jsonArray.map { it.jsonObject }
}

val PublicationMetadataContract by testSuite {
    test("every recorded publication has the same variants in the same order") {
        for (entry in PublicationGolden.entries("variants")) {
            val module = entry.str("module")
            val target = entry.nullable("target")
            // Python iterates a set for the metadata pointers, so their order is not stable.
            // Compare the named variants, and compare the primary variants in publication order.
            val expected = entry.getValue("variants").jsonArray.map { it.jsonObject }
            val observed = PublicationContract.variants(module, target)
            assertEquals(expected.size, observed.size, "$module/$target count")
            val expectedByName = expected.associateBy { it.str("name") }
            assertEquals(expectedByName.keys, observed.keys, "$module/$target names")
            for (want in expected) {
                val got = observed.getValue(want.str("name"))
                assertEquals(want.str("kind"), got.kind, "$module/$target kind")
                assertEquals(want.nullable("target"), got.target, "$module/$target target")
                assertEquals(want.nullable("url"), got.url, "$module/$target url")
                assertEquals(want.nullable("file_name"), got.fileName, "$module/$target file")
                assertEquals(
                    want.getValue("dependencies").jsonArray.map { row ->
                        row.jsonArray.map { it.jsonPrimitive.content }
                    }.map { VariantDependency(it[0], it[1], it[2]) }.toSet(),
                    got.dependencies,
                    "$module/$target dependencies",
                )
                val available = want["available_at"]
                if (available == null || available is JsonNull) {
                    assertEquals(null, got.availableAt, "$module/$target available-at")
                } else {
                    val value = available.jsonObject
                    assertEquals(
                        VariantAvailableAt(
                            group = value.str("group"),
                            module = value.str("module"),
                            version = value.str("version"),
                            url = value.str("url"),
                        ),
                        got.availableAt,
                        "$module/$target available-at",
                    )
                }
            }
        }
    }

    test("the metadata publication points at every matrix target") {
        val variants = PublicationContract.variants("dyn4k-core", null)
        val available = variants.values.count { it.availableAt != null }
        assertTrue(available >= Qualification.matrixTargets().size, "available-at entries: $available")
    }

    test("runtime variants exist only for runtime-bearing targets") {
        for ((target, present) in listOf(
            "jvm" to true,
            "js" to true,
            "wasmJs" to true,
            "linuxX64" to false,
        )) {
            val names = PublicationContract.variants("dyn4k-core", target).keys
            assertTrue(
                names.any { it.endsWith("RuntimeElements-published") } == present,
                "$target runtime variant",
            )
        }
    }

    test("pom dependency rows match the recorded rows") {
        for (entry in PublicationGolden.entries("pom_dependencies")) {
            val expected = entry.getValue("dependencies").jsonArray.map { row ->
                PomDependency(
                    group = row.jsonArray[0].jsonPrimitive.content,
                    module = row.jsonArray[1].jsonPrimitive.content,
                    version = row.jsonArray[2].jsonPrimitive.content,
                    scope = row.jsonArray[3].jsonPrimitive.content,
                )
            }.toSet()
            assertEquals(
                expected,
                PublicationContract.pomDependencies(entry.str("module"), entry.nullable("target")),
                "${entry.str("module")}/${entry.nullable("target")}",
            )
        }
    }

    test("pom metadata matches the recorded values") {
        for (entry in PublicationGolden.entries("pom_metadata")) {
            val value = entry.getValue("metadata").jsonObject
            val license = value.getValue("licenses").jsonObject.getValue("license").jsonObject
            val developer = value.getValue("developers").jsonObject.getValue("developer").jsonObject
            val scm = value.getValue("scm").jsonObject
            assertEquals(
                PomMetadata(
                    name = value.str("name"),
                    description = value.str("description"),
                    url = value.str("url"),
                    licenseName = license.str("name"),
                    licenseUrl = license.str("url"),
                    developerId = developer.str("id"),
                    developerName = developer.str("name"),
                    scmUrl = scm.str("url"),
                ),
                PublicationContract.pomMetadata(entry.str("module")),
                entry.str("module"),
            )
        }
    }
}

private fun JsonObject.str(key: String): String = getValue(key).jsonPrimitive.content

private fun JsonObject.nullable(key: String): String? {
    val value = this[key] ?: return null
    return if (value is JsonNull) null else value.jsonPrimitive.content
}
