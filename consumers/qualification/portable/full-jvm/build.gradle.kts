import groovy.json.JsonOutput
import java.security.MessageDigest
import javax.xml.parsers.DocumentBuilderFactory
import javax.xml.transform.OutputKeys
import javax.xml.transform.TransformerFactory
import javax.xml.transform.dom.DOMSource
import javax.xml.transform.stream.StreamResult
import org.w3c.dom.Element
import org.jetbrains.kotlin.gradle.tasks.KotlinJvmCompile
import org.gradle.api.tasks.testing.Test
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    kotlin("jvm") version "2.4.20" apply false
}

val checkout = file(providers.gradleProperty("qualificationCheckout").get())
val staging = file(providers.gradleProperty("qualificationRepository").get())
val archive = file(providers.gradleProperty("qualificationArchiveRoot").get())
val inventory = file(providers.gradleProperty("qualificationSourceInventory").get())
val coreCases = file(providers.gradleProperty("qualificationCoreCases").get())
val facadeCases = file(providers.gradleProperty("qualificationFacadeCases").get())
val laneScript = file(providers.gradleProperty("qualificationLaneScript").get())
val lane = providers.gradleProperty("qualificationLaneId").get()
val version = "0.1.0-alpha.1"
val group = "io.github.rubixhacker"

fun hash(file: File): String = MessageDigest.getInstance("SHA-256")
    .digest(file.readBytes()).joinToString("") { "%02x".format(it) }

fun targetJar(module: String): File = file(
    "$staging/io/github/rubixhacker/$module-jvm/$version/$module-jvm-$version.jar")

fun archived(relative: String): File = file("$archive/$relative").also {
    it.parentFile.mkdirs()
}

tasks.register("qualificationValidateInputs") {
    doLast {
        check(Regex("jvm:Java:(minimum|current):(no-optimize|default)").matches(lane))
        check(lane.substringAfterLast(':') == providers.gradleProperty("qualificationBuildConfiguration").get())
        val sourceLines = inventory.readLines().filter { it.isNotBlank() }
        val sources = sourceLines.map { line ->
            val parts = line.split('\t')
            check(parts.size == 2 && parts[0].startsWith("dyn4k"))
            check(Regex("[0-9a-f]{64}").matches(parts[1]))
            parts[0] to parts[1]
        }
        check(sources.size == sources.map { it.first }.toSet().size)
        val roots = listOf("dyn4k-core/src/commonTest/kotlin", "dyn4k-core/src/jvmTest/kotlin",
            "dyn4k/src/commonTest/kotlin", "dyn4k/src/jvmTest/kotlin", "dyn4k/src/jvmTest/java")
        val live = roots.flatMap { root ->
            file("$checkout/$root").walkTopDown().filter { it.isFile &&
                it.extension in setOf("kt", "java") }.map {
                it.relativeTo(checkout).invariantSeparatorsPath
            }.toList()
        }.toSet()
        check(sources.map { it.first }.toSet() == live)
        sources.forEach { (path, expected) -> check(hash(file("$checkout/$path")) == expected) }
        for (module in listOf("dyn4k-core", "dyn4k")) {
            val expected = providers.gradleProperty(
                if (module == "dyn4k-core") "qualificationCoreSha256" else "qualificationFacadeSha256"
            ).get()
            check(hash(targetJar(module)) == expected)
        }
        for (cases in listOf(coreCases, facadeCases)) {
            val lines = cases.readLines().filter { it.isNotBlank() }
            check(lines.isNotEmpty() && lines.size == lines.toSet().size)
            lines.forEach { check(it.split('\t').size == 3) }
        }
        println("QUALIFICATION_INPUT_SOURCE_COUNT=${sources.size}")
    }
}

fun configurationGraph(projectName: String, configurationName: String): Map<String, Any> {
    val configuration = project(":$projectName").configurations.getByName(configurationName)
    val components = configuration.incoming.resolutionResult.allComponents
        .map { it.id.displayName }.sorted()
    val artifacts = configuration.resolvedConfiguration.resolvedArtifacts.map { artifact ->
        mapOf("component" to artifact.moduleVersion.id.toString(),
            "file" to artifact.file.absolutePath, "name" to artifact.file.name,
            "size" to artifact.file.length(), "sha256" to hash(artifact.file))
    }.sortedWith(compareBy({ it["component"].toString() }, { it["name"].toString() }))
    return mapOf("project" to projectName, "configuration" to configurationName,
        "components" to components, "artifacts" to artifacts)
}

tasks.register("qualificationEvidence") {
    dependsOn(":core:test", ":facade:test")
    doLast {
        val selected = listOf(coreCases, facadeCases).flatMap { it.readLines() }
        val byMethod = selected.associate { line ->
            val parts = line.split('\t')
            "${parts[1]}#${parts[2]}" to parts[0]
        }
        check(byMethod.size == selected.size)
        val observed = mutableSetOf<String>()
        val parser = DocumentBuilderFactory.newInstance().apply {
            setFeature("http://apache.org/xml/features/disallow-doctype-decl", true)
            setFeature("http://xml.org/sax/features/external-general-entities", false)
            setFeature("http://xml.org/sax/features/external-parameter-entities", false)
        }.newDocumentBuilder()
        val transformer = TransformerFactory.newInstance().newTransformer().apply {
            setOutputProperty(OutputKeys.OMIT_XML_DECLARATION, "no")
        }
        val normalized = mutableListOf<File>()
        val original = mutableListOf<File>()
        for (module in listOf("core", "facade")) {
            val reports = file("${project(":$module").layout.buildDirectory.get()}/test-results/test")
                .listFiles { candidate -> candidate.name.startsWith("TEST-") &&
                    candidate.extension == "xml" }?.sortedBy { it.name } ?: emptyList()
            check(reports.isNotEmpty())
            for (report in reports) {
                val doc = parser.parse(report)
                val suite = doc.documentElement
                check(suite.tagName == "testsuite")
                val cases = suite.getElementsByTagName("testcase")
                check(suite.getAttribute("tests").toInt() == cases.length)
                check(suite.getAttribute("failures") == "0" &&
                    suite.getAttribute("errors") == "0" && suite.getAttribute("skipped") == "0")
                for (index in 0 until cases.length) {
                    val case = cases.item(index) as Element
                    check(case.getElementsByTagName("failure").length == 0 &&
                        case.getElementsByTagName("error").length == 0 &&
                        case.getElementsByTagName("skipped").length == 0)
                    val key = "${case.getAttribute("classname")}#${case.getAttribute("name")}"
                    val id = byMethod[key] ?: error("Unlisted external method: $key")
                    check(observed.add(id))
                    case.setAttribute("id", id)
                }
                val raw = archived("reports/raw/$module/${report.name}")
                report.copyTo(raw, overwrite = true)
                original.add(raw)
                val derived = archived("reports/normalized/$module/${report.name}")
                transformer.transform(DOMSource(doc), StreamResult(derived))
                normalized.add(derived)
            }
        }
        check(observed == byMethod.values.toSet())
        val graph = mapOf("compile" to listOf("core", "facade").map {
            configurationGraph(it, "testCompileClasspath")
        }, "runtime" to listOf("core", "facade").map {
            configurationGraph(it, "testRuntimeClasspath")
        }, "gradle_user_home" to gradle.gradleUserHomeDir.absolutePath)
        val graphFile = archived("provider-graph.json")
        graphFile.writeText(JsonOutput.toJson(graph))
        val copies = listOf("dyn4k-core", "dyn4k").associateWith { module ->
            val source = targetJar(module)
            val target = archived("resolved/${source.name}")
            source.copyTo(target, overwrite = true)
            target
        }
        val sourceInput = archived("inputs/source-inventory.tsv")
        inventory.copyTo(sourceInput, overwrite = true)
        val coreInput = archived("inputs/core-cases.tsv")
        coreCases.copyTo(coreInput, overwrite = true)
        val facadeInput = archived("inputs/facade-cases.tsv")
        facadeCases.copyTo(facadeInput, overwrite = true)
        val scriptInput = archived("inputs/lane-script")
        laneScript.copyTo(scriptInput, overwrite = true)
        val configuration = providers.gradleProperty("qualificationBuildConfiguration").get()
        val runtimeHome = file(providers.gradleProperty("qualificationRuntimeJavaHome").get()).canonicalFile
        val runtimeHash = providers.gradleProperty("qualificationRuntimeJavaSha256").get()
        val buildProof = listOf("core", "facade").map { module ->
            val kotlinTask = project(":$module").tasks.getByName("compileTestKotlin") as KotlinJvmCompile
            val testTask = project(":$module").tasks.getByName("test") as Test
            val javaTask = project(":$module").tasks.getByName("compileTestJava") as JavaCompile
            val launcher = testTask.javaLauncher.get()
            check(launcher.metadata.installationPath.asFile.canonicalFile == runtimeHome)
            val args = kotlinTask.compilerOptions.freeCompilerArgs.get()
            check(args.contains("-Xno-optimize") == (configuration == "no-optimize"))
            check(testTask.jvmArgs.contains("-Xint") == (configuration == "no-optimize"))
            mapOf("module" to module, "compiler_args" to args,
                "kotlin_jvm_target" to kotlinTask.compilerOptions.jvmTarget.get().target,
                "java_release" to javaTask.options.release.get(),
                "test_jvm_args" to testTask.jvmArgs,
                "test_java_executable" to launcher.executablePath.asFile.canonicalPath,
                "test_java_home" to launcher.metadata.installationPath.asFile.canonicalPath,
                "test_java_version" to launcher.metadata.languageVersion.asInt(),
                "test_java_sha256" to hash(launcher.executablePath.asFile))
        }
        check(buildProof.all { it["test_java_sha256"] == runtimeHash })
        val buildFile = archived("build-configuration.json")
        buildFile.writeText(JsonOutput.toJson(mapOf(
            "lane" to lane, "configuration" to configuration, "modules" to buildProof)))
        println("QUALIFICATION_LANE=$lane")
        println("QUALIFICATION_BUILD_CONFIGURATION=$configuration")
        println("QUALIFICATION_BUILD_CONFIGURATION_SHA256=${hash(buildFile)}")
        println("QUALIFICATION_INPUT_SOURCE_COUNT=${inventory.readLines().size}")
        println("QUALIFICATION_CASE_COUNT=${observed.size}")
        println("QUALIFICATION_PROVIDER_GRAPH_SHA256=${hash(graphFile)}")
        original.forEach { println("QUALIFICATION_RAW_XML_SHA256=${hash(it)}") }
        normalized.forEach { println("QUALIFICATION_CONSUMER_XML_SHA256=${hash(it)}") }
        println("QUALIFICATION_RESOLVED_DYN4K_CORE_SHA256=${hash(copies.getValue("dyn4k-core"))}")
        println("QUALIFICATION_RESOLVED_DYN4K_SHA256=${hash(copies.getValue("dyn4k"))}")
        println("QUALIFICATION_SOURCE_INVENTORY_SHA256=${hash(sourceInput)}")
        println("QUALIFICATION_CORE_CASES_SHA256=${hash(coreInput)}")
        println("QUALIFICATION_FACADE_CASES_SHA256=${hash(facadeInput)}")
        println("QUALIFICATION_LANE_SCRIPT_SHA256=${hash(scriptInput)}")
    }
}
