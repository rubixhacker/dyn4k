package io.github.rubixhacker.harness.baseline

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull

/**
 * `type_header`, `surface`, `member_inventory`, `source_visible` and `private_nested_type` over the
 * `javap` text the Python module recorded: every type of a compiled fixture, the same types read
 * with `include_package`, and hand-written class files that reach the error branches.
 */
val SurfaceCases by testSuite {
    val signatures: Map<String, String> = Vectors.types.obj("signatures").stringMap()

    test("the recorded fixture covers the class-file shapes the readers distinguish") {
        val types = Vectors.types.strings("types")
        assertEquals(
            listOf(
                "p.Api",
                "p.Base",
                "p.Child",
                "p.Generic",
                "p.Marker",
                "p.Mode",
                "p.Outer",
                "p.Outer\$1",
                "p.Outer\$Inner",
                "p.Outer\$Nested",
                "p.Outer\$Warm",
                "p.PackagePrivate",
                "p.package-info",
            ),
            types,
        )
        assertEquals(
            Vectors.types.strings("synthetic"),
            listOf(
                "missing-descriptor",
                "missing-flags",
                "empty-descriptor",
                "incomplete-member",
                "unclosed-body",
                "static-initializer",
                "no-header",
                "generic-method",
                "package-header",
                "final-header",
            ),
        )
        assertEquals((types.size + Vectors.types.strings("synthetic").size) * 2, Vectors.types.array("surfaces").size)
        for ((name, signature) in signatures) {
            if (name in types) assertTrueText(signature.contains("Classfile"), name)
        }
    }

    test("surface reproduces the recorded header, members and declarations") {
        for (element in Vectors.types.array("surfaces")) {
            val case = element.jsonObject
            val name = case.str("name")
            val signature = signatures.getValue(name)
            val includePackage = case.bool("include_package")
            val error = case["error"]?.let { it.jsonPrimitive.content }
            if (error != null) {
                val thrown = assertFailsWith<IllegalArgumentException>("$name/$includePackage") {
                    surface(signature, includePackage)
                }
                assertEquals(error, thrown.message, "$name/$includePackage")
                continue
            }
            val recorded = case["surface"]?.takeIf { it !is kotlinx.serialization.json.JsonNull }?.jsonObject
            val observed = surface(signature, includePackage)
            if (recorded == null) {
                assertNull(observed, "$name/$includePackage")
                continue
            }
            val api = observed ?: error("no surface for $name/$includePackage")
            assertEquals(recorded.str("header"), api.header, "$name/$includePackage header")
            val expected = recorded.array("members").map { entry ->
                val values = entry.jsonArray
                MemberKey(
                    values[0].jsonPrimitive.content,
                    values[1].jsonPrimitive.content,
                ) to values[2].jsonArray.map { it.jsonPrimitive.content }
            }.toMap()
            assertEquals(expected.keys.toList(), api.members.keys.toList(), "$name/$includePackage keys")
            assertEquals(expected, api.members, "$name/$includePackage members")
        }
    }

    test("member_inventory reproduces every recorded class-file record") {
        for (element in Vectors.types.array("inventories")) {
            val case = element.jsonObject
            val name = case.str("name")
            val signature = signatures.getValue(name)
            val error = case["error"]?.let { it.jsonPrimitive.content }
            if (error != null) {
                val thrown = assertFailsWith<IllegalArgumentException>(name) {
                    memberInventory(signature)
                }
                assertEquals(error, thrown.message, name)
                continue
            }
            val (header, records) = memberInventory(signature)
            assertEquals(case.str("header"), header, name)
            assertEquals(
                case.array("records").map { memberRecordOf(it.jsonObject) },
                records,
                name,
            )
            assertEquals(case.str("json"), PythonJson.render(kotlinx.serialization.json.JsonArray(
                records.map { it.toJson() },
            )), "$name JSON")
        }
    }

    test("a varargs parameter is recorded as an array, as Java source spells it") {
        val signature = signatures.getValue("generic-method")
        val (_, records) = memberInventory(signature)
        val varargs = records.single { it.name == "names" }
        assertEquals("java.lang.String[]", varargs.sourceParameters)
        assertEquals("java.lang.String[]", varargs.returnType)
        assertEquals(true, "ACC_VARARGS" in varargs.flags)
    }

    test("source_visible reproduces the recorded visibility of every member") {
        for (element in Vectors.types.array("visibility")) {
            val case = element.jsonObject
            assertEquals(case.bool("visible"), sourceVisible(memberRecordOf(case.obj("record"))))
        }
    }

    test("private_nested_type reproduces the recorded InnerClasses reading") {
        for (element in Vectors.types.array("private_nested")) {
            val case = element.jsonObject
            assertEquals(
                case.bool("result"),
                privateNestedType(signatures.getValue(case.str("name")), case.str("name")),
                case.str("name"),
            )
        }
    }

    test("the private nested type of the fixture is the one the gate has to skip") {
        assertEquals(
            true,
            privateNestedType(signatures.getValue("p.Outer\$Warm"), "p.Outer\$Warm"),
        )
        assertEquals(
            false,
            privateNestedType(signatures.getValue("p.Outer\$Nested"), "p.Outer\$Nested"),
        )
        assertEquals(
            false,
            privateNestedType(signatures.getValue("p.Outer\$Inner"), "p.Outer\$Inner"),
        )
    }
}

private fun assertTrueText(condition: Boolean, name: String) {
    kotlin.test.assertTrue(condition, "recorded signature for $name is not javap output")
}
