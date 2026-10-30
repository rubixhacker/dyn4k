package io.github.rubixhacker.harness.qualification

import java.nio.file.Files
import java.nio.file.NoSuchFileException
import java.nio.file.Path

/**
 * `git_bash_from_git` and `bash_executable`: which shell runs `safari-launch.sh`.
 *
 * On POSIX the host `bash` is used. On Windows the bare `bash` on `PATH` is the WSL launcher,
 * which cannot run a script that expects Git Bash, so the wrapper is handed to the `bash.exe` of
 * the Git for Windows installation that owns the `git` command.
 */
object SafariGitBash {
    /**
     * `git_bash_from_git`: the `bin/bash.exe` of the installation that owns [gitCommand].
     *
     * A `Git/mingw64/bin/git.exe` (or `mingw32`, `ucrt64`) is inside the installation's
     * architecture directory; a `Git/bin/git.exe` or `Git/cmd/git.exe` is directly under it. Neither
     * executable may resolve outside the installation.
     */
    fun gitBashFromGit(gitCommand: Path): Path {
        val gitExecutable = gitCommand.toAbsolutePath()
        val directory = gitExecutable.parent ?: Path.of("")
        if (gitExecutable.fileName?.toString()?.lowercase() != "git.exe") {
            throw IllegalArgumentException("Git Bash fixture requires Git for Windows")
        }
        val directoryName = directory.fileName?.toString()?.lowercase() ?: ""
        val parentName = directory.parent?.fileName?.toString()?.lowercase() ?: ""
        val installation = when {
            directoryName == "bin" &&
                parentName in listOf("mingw64", "mingw32", "ucrt64") ->
                directory.parent?.parent
            directoryName == "cmd" || (directoryName == "bin" && parentName != "usr") ->
                directory.parent
            else -> null
        } ?: throw IllegalArgumentException("Git Bash fixture requires Git for Windows")
        val candidate = installation.resolve("bin/bash.exe")
        if (!Files.isRegularFile(gitExecutable) || !Files.isRegularFile(candidate)) {
            throw NoSuchFileException(
                candidate.toString(),
                null,
                "Git Bash fixture executable is missing",
            )
        }
        val installationReal = SafariReporterHost.resolvePath(installation)
        if (!SafariReporterHost.resolvePath(gitExecutable).startsWith(installationReal) ||
            !SafariReporterHost.resolvePath(candidate).startsWith(installationReal)
        ) {
            throw IllegalArgumentException("Git Bash fixture executable leaves Git installation")
        }
        return candidate
    }

    /**
     * `bash_executable`: the shell the wrapper runs under.
     *
     * [which] and [windows] are the seams the reference suite patches (`shutil.which`, `os.name`).
     */
    fun bashExecutable(
        which: (String) -> Path? = ::whichOnPath,
        windows: Boolean = DefaultHostEnvironment.isWindows(),
    ): String {
        if (!windows) return "bash"
        val gitCommand = which("git")
            ?: throw NoSuchFileException(
                "git",
                null,
                "Git Bash fixture requires Git for Windows",
            )
        return gitBashFromGit(gitCommand).toString()
    }

    /** `shutil.which`: the first executable named [name] on `PATH`. */
    fun whichOnPath(name: String): Path? {
        val path = System.getenv("PATH") ?: return null
        for (directory in path.split(java.io.File.pathSeparator)) {
            if (directory.isEmpty()) continue
            val candidate = Path.of(directory).resolve(name)
            if (Files.isRegularFile(candidate) && Files.isExecutable(candidate)) return candidate
        }
        return null
    }
}
