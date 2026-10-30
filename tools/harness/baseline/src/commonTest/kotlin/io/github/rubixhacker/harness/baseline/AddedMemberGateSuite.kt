package io.github.rubixhacker.harness.baseline

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.test.assertEquals

/**
 * `added_member_gate` replayed without a filesystem.
 *
 * The gate reads class files through one seam, `loadSignature`. The recorded payload holds the
 * `javap` text of both archives, so the whole walk — declared members, inherited members, generic
 * substitution, the `final` and varargs exceptions, the same-package rule and the errors — runs in
 * the pure Kotlin implementation and the risks and errors must equal Python's.
 */
val AddedMemberGateCases by testSuite {
    test("the recorded cases cover declared, inherited and rejected additions") {
        assertEquals(
            listOf(
                "declared-and-inherited",
                "generated-identifiers",
                "final-type-overload",
                "field-hiding-constant",
                "package-private",
                "missing-package-private",
                "method-type-parameter",
                "private-nested",
            ),
            Vectors.gates.map { it.jsonObject.str("label") },
        )
    }

    test("the gate reproduces the recorded risks and errors") {
        for (element in Vectors.gates) {
            val recorded = element.jsonObject
            val baseline = recorded.obj("baseline_signatures").stringMap()
            val candidate = recorded.obj("candidate_signatures").stringMap()
            val extraBaseline = recorded.obj("extra_baseline").stringMap()
            val extraCandidate = recorded.obj("extra_candidate").stringMap()
            val result = MemberAddition.gate(
                selected = recorded.strings("selected").toSet(),
                baselineSignatures = baseline,
                candidateSignatures = candidate,
                baselineClasspath = "baseline",
                candidateClasspath = "candidate",
                artifactSha256 = "<sha256>",
                loadSignature = { classpath, name ->
                    when (classpath) {
                        "baseline" -> extraBaseline[name] ?: error("unrecorded baseline lookup: $name")
                        "candidate" -> extraCandidate[name] ?: error("unrecorded candidate lookup: $name")
                        else -> error("unexpected classpath: $classpath")
                    }
                },
            )
            assertEquals(
                recorded.array("risks").map { memberRiskOf(it.jsonObject) },
                result.risks,
                "${recorded.str("label")} risks",
            )
            assertEquals(recorded.strings("errors"), result.errors, "${recorded.str("label")} errors")
        }
    }

    test("a private nested type and a package-private type are recorded as the gate treats them") {
        val private = Vectors.gates.first { it.jsonObject.str("label") == "private-nested" }.jsonObject
        assertEquals(emptyList<String>(), private.strings("errors"))
        val missing = Vectors.gates.first {
            it.jsonObject.str("label") == "missing-package-private"
        }.jsonObject
        assertEquals(listOf("p.Api: missing same-package subclassable baseline type"), missing.strings("errors"))
    }

    test("the gate reports the six recorded helper additions with their declaring types") {
        val rich = Vectors.gates.first {
            it.jsonObject.str("label") == "declared-and-inherited"
        }.jsonObject
        val risks = rich.array("risks").map { memberRiskOf(it.jsonObject) }
        val declarations = risks.map { it.declaration }
        for (name in listOf(
            "maxIterationsField",
            "settingsField",
            "costValue",
            "rawForce\$io_github_rubixhacker_dyn4k_core",
            "bodyField",
        )) {
            kotlin.test.assertTrue(declarations.any { name in it }, name)
        }
        val inherited = risks.single { it.candidateType == "World" && "settingsField" in it.declaration }
        assertEquals("BaseWorld", inherited.declaringType)
        assertEquals("inherited", inherited.origin)
    }

    test("a member that is not source-visible never becomes a risk") {
        val nested = Vectors.gates.first {
            it.jsonObject.str("label") == "private-nested"
        }.jsonObject
        assertEquals(emptyList<kotlinx.serialization.json.JsonElement>(), nested.array("risks").toList())
    }

    test("generated identifiers on an enum and a class are both recorded as risks") {
        val generated = Vectors.gates.first {
            it.jsonObject.str("label") == "generated-identifiers"
        }.jsonObject
        val risks = generated.array("risks").map { memberRiskOf(it.jsonObject) }
        kotlin.test.assertTrue(risks.any { "Companion" in it.declaration })
        kotlin.test.assertTrue(risks.any { "getEntries()" in it.declaration })
        kotlin.test.assertEquals(
            listOf("p.Api", "p.Mode"),
            risks.map { it.candidateType }.distinct().sorted(),
        )
    }

    test("an empty inventory is an inventory error, not a clean comparison") {
        val result = MemberAddition.gate(
            selected = setOf("Api"),
            baselineSignatures = mapOf("Api" to ""),
            candidateSignatures = mapOf("Api" to ""),
            baselineClasspath = "baseline",
            candidateClasspath = "candidate",
            artifactSha256 = "<sha256>",
            loadSignature = { _, _ -> "" },
        )
        assertEquals(emptyList(), result.risks)
        assertEquals(listOf("Api: empty class-file inventory: Api"), result.errors)
    }
}
