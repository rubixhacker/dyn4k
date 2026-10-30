package io.github.rubixhacker.harness.qualification

import java.io.File
import java.nio.file.Files
import kotlin.system.exitProcess

/** Scans `.github/workflows` under the given root, as the Python tool did. */
fun scan(root: File): Pair<Int, List<String>> {
    val directory = File(root, ".github/workflows")
    if (!directory.isDirectory) {
        return 0 to listOf("$directory: active workflow directory is missing")
    }
    val paths = directory.listFiles()
        ?.filter { it.name.endsWith(".yml") || it.name.endsWith(".yaml") }
        ?.sortedBy { it.path }
        .orEmpty()
    if (paths.isEmpty()) {
        return 0 to listOf("$directory: no active workflows found")
    }
    val errors = paths.flatMap { path ->
        if (Files.isSymbolicLink(path.toPath()) || !path.isFile) {
            listOf("$path: active workflow must be a regular file")
        } else {
            val source = try {
                path.readText(Charsets.UTF_8)
            } catch (error: Exception) {
                return@flatMap listOf("$path: cannot read workflow: ${error.message}")
            }
            GuardHostedRunners.checkWorkflow(path.path, source)
        }
    }
    return paths.size to errors
}

fun main(args: Array<String>) {
    val root = File(args.firstOrNull() ?: System.getProperty("user.dir")).absoluteFile
    val (count, errors) = scan(root)
    for (error in errors) {
        System.err.println(error)
    }
    if (errors.isNotEmpty()) {
        exitProcess(1)
    }
    println("Checked $count active workflows: no hosted macOS labels; mac-mini self-hosted allowed")
}
