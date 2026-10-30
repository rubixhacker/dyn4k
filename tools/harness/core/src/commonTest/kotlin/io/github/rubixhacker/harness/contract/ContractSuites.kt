package io.github.rubixhacker.harness.contract

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

private object Golden {
    private val root: JsonObject = Json.parseToJsonElement(GoldenVectors.json).jsonObject

    fun objects(key: String): List<JsonObject> = root.getValue(key).jsonArray.map { it.jsonObject }

}

val MatrixContract by testSuite {
    test("matrix matches the recorded rows") {
        val expected = Golden.objects("matrix").map {
            MatrixRow(it.str("target"), it.str("runtime"), it.str("minimum"), it.str("kind"))
        }
        assertEquals(expected, Qualification.matrix())
    }

    test("matrix holds 28 rows across 21 targets") {
        assertEquals(28, Qualification.matrix().size)
        assertEquals(21, Qualification.matrixTargets().size)
    }

    test("expand matches the recorded cases") {
        val expected = Golden.objects("expanded").map {
            MatrixCase(
                target = it.str("target"),
                runtime = it.str("runtime"),
                minimum = it.str("minimum"),
                kind = it.str("kind"),
                version = it.str("version"),
                configuration = it.str("configuration"),
                id = it.str("id"),
            )
        }
        assertEquals(expected, Qualification.expand())
    }

    test("every expanded case has a unique identity") {
        val ids = Qualification.expand().map { it.id }
        assertEquals(ids.size, ids.toSet().size)
    }
}

val PublicationContract by testSuite {
    test("publication names match the recorded names") {
        val observed = Golden.objects("publication_names").map {
            Qualification.targetPublicationName(it.str("module"), it.str("target"))
        }
        assertEquals(
            Golden.objects("publication_names").map { it.str("name") },
            observed,
        )
    }

    test("publication names spell wasm targets with a hyphen") {
        assertEquals("dyn4k-core-wasm-js", Qualification.targetPublicationName("dyn4k-core", "wasmJs"))
        assertEquals("dyn4k-wasm-wasi", Qualification.targetPublicationName("dyn4k", "wasmWasi"))
    }

    test("target binary paths match the recorded paths") {
        assertEquals(
            Golden.objects("binary_paths").map { it.str("path") },
            Golden.objects("binary_paths").map {
                Qualification.targetBinaryPath(it.str("module"), it.str("target"))
            },
        )
    }

    test("publication binary paths match the recorded paths") {
        val entries = Golden.objects("publication_binary_paths")
        assertTrue(entries.isNotEmpty())
        for (entry in entries) {
            assertEquals(
                entry.str("path"),
                Qualification.publicationBinaryPath(entry.str("module"), entry.nullable("target")),
                "${entry.str("module")}/${entry.nullable("target")}",
            )
        }
    }

    test("metadata publication path names the module jar") {
        assertEquals(
            "io/github/rubixhacker/dyn4k-core/0.1.0-alpha.1/dyn4k-core-0.1.0-alpha.1.jar",
            Qualification.publicationBinaryPath("dyn4k-core", null),
        )
    }

    test("variant attributes match the recorded attributes") {
        val expected = Golden.objects("variant_attributes").map {
            val target = if (it.getValue("target") is JsonNull) null else it.str("target")
            Triple(target, it.str("kind"), it.getValue("attributes").jsonObject.mapValues { entry -> entry.value.jsonPrimitive.content })
        }
        for ((target, kind, attributes) in expected) {
            assertEquals(attributes, Qualification.variantAttributes(target, kind), "$target/$kind")
        }
    }

    test("a duplicate provider is rejected") {
        assertFailsWith<IllegalArgumentException> {
            Qualification.checkProviders("org.dyn4j:dyn4j:6.0.0 io.github.rubixhacker:dyn4k-core:0.1.0-alpha.1")
        }
    }

    test("a single provider is accepted") {
        Qualification.checkProviders("io.github.rubixhacker:dyn4k-core:0.1.0-alpha.1")
        Qualification.checkProviders("org.dyn4j:dyn4j:6.0.0")
    }
}

val CanonicalJsonContract by testSuite {
    val recorded = Golden.objects("canonical").map {
        Triple(it.getValue("value"), it.str("text"), it.str("digest"))
    }

    test("recorded documents render to the recorded text") {
        for ((value, text, _) in recorded) {
            assertEquals(text, CanonicalJson.render(value))
        }
    }

    test("recorded documents hash to the recorded digest") {
        for ((value, _, digest) in recorded) {
            assertEquals(digest, Sha256.ofCanonical(value))
        }
    }

    test("keys sort by code point, not by UTF-16 code unit") {
        val value = buildJsonObject {
            put("\uD83D\uDE00", JsonPrimitive(2))
            put("\uE000", JsonPrimitive(1))
        }
        assertEquals("{\"\\ue000\":1,\"\\ud83d\\ude00\":2}", CanonicalJson.render(value))
    }

    test("non-finite numbers are rejected") {
        assertFailsWith<IllegalArgumentException> { CanonicalJson.pythonFloat(Double.NaN) }
        assertFailsWith<IllegalArgumentException> { CanonicalJson.pythonFloat(Double.POSITIVE_INFINITY) }
    }
}

val StrictJsonContract by testSuite {
    test("non-standard constants are rejected") {
        for (text in listOf("NaN", "Infinity", "-Infinity", "{\"a\": NaN}")) {
            assertFailsWith<Exception>(text) { StrictJson.load(text) }
        }
    }

    test("a trailing comma is rejected") {
        assertFailsWith<Exception> { StrictJson.load("{\"a\":1,}") }
    }

    test("large integers keep their exact digits") {
        val value = StrictJson.load("{\"big\":9007199254740993}")
        assertEquals("9007199254740993", value.jsonObject.getValue("big").jsonPrimitive.content)
    }

    test("infinite values are not finite") {
        assertTrue(!StrictJson.isFinite(StrictJson.load("{\"a\":1e400}")))
        assertTrue(StrictJson.isFinite(StrictJson.load("{\"a\":1.5,\"b\":[1,2]}")))
    }
}

val DigestContract by testSuite {
    test("sha256 of the standard sample matches") {
        assertEquals("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", Sha256.of("abc"))
    }

    test("streamed and in-memory digests agree") {
        val bytes = ByteArray(3 * 1024 * 1024) { (it * 31).toByte() }
        val streamed = okio.Buffer().write(bytes).let { buffer ->
            Sha256.of(buffer)
        }
        assertEquals(Sha256.of(bytes), streamed)
    }
}

private fun JsonObject.str(key: String): String = getValue(key).jsonPrimitive.content

private fun JsonObject.nullable(key: String): String? =
    if (getValue(key) is JsonNull) null else getValue(key).jsonPrimitive.content
