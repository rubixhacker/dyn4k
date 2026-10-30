package io.github.rubixhacker.harness.baseline

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.test.assertEquals

/**
 * The Java 8 source-compatibility rules the comparator applies: `split_top_level`, `type_contract`,
 * `source_compatible_declaration` and `constructor_list_widening`.
 *
 * `source_compatible_declaration` is recorded for every ordered pair of the declaration shapes the
 * comparison reports, under each of the three `final` policies the two call sites use. The matrix is
 * the whole decision table, not a sample.
 */
val DeclarationCases by testSuite {
    test("split_top_level matches the recorded splits") {
        for (element in Vectors.declarations.array("split_top_level")) {
            val case = element.jsonObject
            assertEquals(
                case.array("parts").map { it.jsonPrimitive.content },
                splitTopLevel(case.str("value"), case.str("separator")),
                case.str("value"),
            )
        }
    }

    test("type_contract matches the recorded declaration, superclass and interfaces") {
        for (element in Vectors.declarations.array("contracts")) {
            val case = element.jsonObject
            val contract = typeContract(case.str("header"))
            assertEquals(case.str("declaration"), contract.declaration, case.str("header"))
            assertEquals(case.nullableStr("superclass"), contract.superclass, case.str("header"))
            assertEquals(case.strings("interfaces"), sortedByCodePoint(contract.interfaces))
        }
    }

    test("source_compatible_declaration reproduces the recorded decision table") {
        val declarations = Vectors.declarations.strings("declarations")
        val flags = Vectors.declarations.array("final_flags").map { pair ->
            val values = pair.jsonArray
            values[0].jsonPrimitive.content.toBoolean() to values[1].jsonPrimitive.content.toBoolean()
        }
        var checked = 0
        for (row in Vectors.declarations.array("compatible")) {
            val values = row.jsonArray
            val expected = declarations[values[0].jsonPrimitive.content.toInt()]
            val actual = declarations[values[1].jsonPrimitive.content.toInt()]
            val (allowRemoval, allowAddition) = flags[values[2].jsonPrimitive.content.toInt()]
            assertEquals(
                values[3].jsonPrimitive.content.toBoolean(),
                sourceCompatibleDeclaration(expected, actual, allowRemoval, allowAddition),
                "$expected -> $actual ($allowRemoval, $allowAddition)",
            )
            checked++
        }
        assertEquals(declarations.size * declarations.size * flags.size, checked)
    }

    test("constructor_list_widening reproduces the recorded widening cases") {
        for (element in Vectors.declarations.array("widening")) {
            val case = element.jsonObject
            assertEquals(
                case.bool("result"),
                constructorListWidening(
                    case.str("expected"),
                    case.str("actual"),
                    case.strings("type_parameters").toSet(),
                ),
                case.str("expected"),
            )
        }
    }

    test("the widening rule only applies when every list parameter is a type parameter") {
        assertEquals(
            true,
            constructorListWidening(
                "public Api(java.util.List<T> values)",
                "public Api(java.util.List<? extends T> values)",
                setOf("T"),
            ),
        )
        assertEquals(
            false,
            constructorListWidening(
                "public Api(java.util.List<java.lang.String> values)",
                "public Api(java.util.List<? extends java.lang.String> values)",
                setOf("T"),
            ),
        )
        assertEquals(
            false,
            constructorListWidening(
                "public Api(java.util.List<T> values)",
                "public Api(java.util.List<? extends T> values)",
                emptySet(),
            ),
        )
    }
}
