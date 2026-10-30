package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.nio.file.attribute.BasicFileAttributes
import java.util.concurrent.TimeUnit
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonPrimitive

/** A handle over a real file, used by the locked-directory fakes. */
internal class SafariPathHandle(private val path: Path) : SafariHandle {
    override fun stat(): SafariHandleStat {
        val attributes = Files.readAttributes(
            path,
            BasicFileAttributes::class.java,
            LinkOption.NOFOLLOW_LINKS,
        )
        return SafariHandleStat(
            0,
            0,
            attributes.size(),
            attributes.lastModifiedTime().to(TimeUnit.NANOSECONDS),
            attributes.isRegularFile,
        )
    }

    override fun read(count: Int): ByteArray =
        Files.newInputStream(path).use { it.readNBytes(count) }

    override fun close() {}
}

private fun safariWindowsTemp(block: (Path) -> Unit) {
    val root = Files.createTempDirectory("safari-windows")
    try {
        block(root)
    } finally {
        Files.walk(root).use { walk ->
            walk.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
        }
    }
}

/** `tools/qualification/test_safari_windows_file.py`. */
val SafariWindowsFileSuite by testSuite {
    test("source bytes accepts a root alias and rejects an aliased child escape") {
        safariWindowsTemp { root ->
            val repository = root.resolve("source")
            val source = repository.resolve("build/js/yarn.lock")
            Files.createDirectories(source.parent)
            Files.writeString(source, "approved\n")
            val alias = root.resolve("var-style-alias")
            Files.createSymbolicLink(alias, repository)
            assertEquals(
                "approved\n",
                String(SafariYarnLockHost.sourceBytes(alias, "build/js/yarn.lock")),
            )
            val archived = SafariYarnLockHost.copyFile(
                alias,
                "build/js/yarn.lock",
                root.resolve("capture"),
                "generated",
            )
            assertEquals(
                "approved\n",
                Files.readString(root.resolve("capture").resolve(Py.str(archived["path"])!!)),
            )
            val outside = root.resolve("outside")
            Files.createDirectories(outside)
            Files.writeString(outside.resolve("yarn.lock"), "hidden provider\n")
            Files.move(repository.resolve("build/js"), repository.resolve("build/js.saved"))
            Files.createSymbolicLink(repository.resolve("build/js"), outside)
            assertEquals(
                "symlink source path or ancestor: build/js/yarn.lock",
                assertFailsWith<IllegalArgumentException> {
                    SafariYarnLockHost.sourceBytes(alias, "build/js/yarn.lock")
                }.message,
            )
            assertEquals("hidden provider\n", Files.readString(outside.resolve("yarn.lock")))
        }
    }

    test("source bytes rejects a root alias swapped before the open") {
        safariWindowsTemp { root ->
            val repository = root.resolve("source")
            Files.createDirectories(repository)
            Files.writeString(repository.resolve("lock"), "approved\n")
            val outside = root.resolve("outside")
            Files.createDirectories(outside)
            Files.writeString(outside.resolve("lock"), "hidden provider\n")
            val alias = root.resolve("var-style-alias")
            Files.createSymbolicLink(alias, repository)
            val seam: (Path, String) -> Path = { sourceRoot, relative ->
                val resolved = SafariYarnLockHost.sourcePath(sourceRoot, relative)
                Files.delete(alias)
                Files.createSymbolicLink(alias, outside)
                resolved
            }
            assertEquals(
                "source path identity changed: lock",
                assertFailsWith<IllegalArgumentException> {
                    SafariYarnLockHost.sourceBytes(alias, "lock", pathSeam = seam)
                }.message,
            )
        }
    }

    test("a stable short read is rejected and a repeated read is accepted") {
        safariWindowsTemp { root ->
            val repository = root.resolve("source")
            val path = repository.resolve("build/js/yarn.lock")
            Files.createDirectories(path.parent)
            Files.writeString(path, "abcdef")
            val reads = ArrayDeque(listOf("abc", "", "abc", "def", ""))
            val factory = SafariLockedDirectoryFactory { _, relative ->
                object : SafariLockedDirectory {
                    override val path: Path = repository.resolve(relative)
                    override fun child(name: String, removable: Boolean): SafariLockedDirectory =
                        error("unused")
                    override fun openFile(name: String): SafariHandle = object : SafariHandle {
                        override fun stat(): SafariHandleStat = SafariHandleStat(
                            0, 0, 6, 0, true,
                        )
                        override fun read(count: Int): ByteArray = reads.removeFirst().toByteArray()
                        override fun close() {}
                    }
                    override fun removeEmpty() = error("unused")
                    override fun close() {}
                }
            }
            val output = root.resolve("capture")
            assertEquals(
                "incomplete diagnostic source: build/js/yarn.lock",
                assertFailsWith<IllegalArgumentException> {
                    SafariYarnLockHost.copyFile(
                        repository,
                        "build/js/yarn.lock",
                        output,
                        "generated",
                        windows = factory,
                    )
                }.message,
            )
            assertFalse(Files.exists(output.resolve("generated/build/js/yarn.lock")))
            val archived = SafariYarnLockHost.copyFile(
                repository,
                "build/js/yarn.lock",
                output,
                "generated",
                windows = factory,
            )
            assertEquals(
                "abcdef",
                Files.readString(output.resolve(Py.str(archived["path"])!!)),
            )
        }
    }

    test("a staging handle failure records a leftover instead of a clean stage") {
        safariWindowsTemp { root ->
            val repository = root.resolve("source")
            Files.createDirectories(repository.resolve("dyn4k-core"))
            val state = SafariReporterHost.StageState("x")
            val directories = SafariLockedDirectoryFactory { source, relative ->
                object : SafariLockedDirectory {
                    override val path: Path = source.resolve(relative)
                    override fun child(name: String, removable: Boolean): SafariLockedDirectory =
                        throw SafariFileError("simulated handle-open failure after mkdir")
                    override fun openFile(name: String): SafariHandle = error("unused")
                    override fun removeEmpty() = error("unused")
                    override fun close() {}
                }
            }
            val error = assertFailsWith<SafariFileError> {
                SafariReporterHost.stageWindows(
                    repository,
                    listOf("dyn4k-core"),
                    "fragment".toByteArray(),
                    root,
                    state,
                    directories,
                ) {}
            }
            assertEquals("simulated handle-open failure after mkdir", error.message)
            assertEquals("CHANGED", state.status)
            assertEquals("LEFTOVER", state.projects["dyn4k-core"])
            assertTrue(Files.isDirectory(repository.resolve("dyn4k-core/karma.config.d")))
        }
    }

    test("a normal Windows stage cleanup removes the owned directory") {
        safariWindowsTemp { root ->
            val repository = root.resolve("source")
            Files.createDirectories(repository.resolve("dyn4k-core"))
            val state = SafariReporterHost.StageState("x")
            val directories = SafariLockedDirectoryFactory { source, relative ->
                val target = source.resolve(relative)
                object : SafariLockedDirectory {
                    override val path: Path = target
                    override fun child(name: String, removable: Boolean): SafariLockedDirectory =
                        SafariDirectoryFake(target.resolve(name))
                    override fun openFile(name: String): SafariHandle =
                        error("not the root")
                    override fun removeEmpty() = error("not the root")
                    override fun close() {}
                }
            }
            SafariReporterHost.stageWindows(
                repository,
                listOf("dyn4k-core"),
                "fragment".toByteArray(),
                root,
                state,
                directories,
            ) {
                assertEquals(
                    "fragment",
                    Files.readString(
                        repository.resolve("dyn4k-core/karma.config.d")
                            .resolve(SafariReporter.STAGED_NAME),
                    ),
                )
            }
            assertEquals("CLEAN", state.status)
            assertEquals("CLEAN", state.projects["dyn4k-core"])
            assertFalse(Files.exists(repository.resolve("dyn4k-core/karma.config.d")))
        }
    }

    test("a stage close swap rejects the replacement and preserves the outside") {
        safariWindowsTemp { root ->
            val repository = root.resolve("source")
            Files.createDirectories(repository.resolve("dyn4k-core"))
            val outside = root.resolve("outside.txt")
            Files.writeString(outside, "outside sentinel")
            val state = SafariReporterHost.StageState("x")
            val directories = SafariLockedDirectoryFactory { source, relative ->
                val target = source.resolve(relative)
                object : SafariLockedDirectory {
                    override val path: Path = target
                    override fun child(name: String, removable: Boolean): SafariLockedDirectory =
                        SafariSwappingDirectory(target.resolve(name))
                    override fun openFile(name: String): SafariHandle =
                        error("not the root")
                    override fun removeEmpty() = error("not the root")
                    override fun close() {}
                }
            }
            SafariReporterHost.stageWindows(
                repository,
                listOf("dyn4k-core"),
                "fragment".toByteArray(),
                root,
                state,
                directories,
            ) {}
            assertEquals("CHANGED", state.status)
            assertEquals("LEFTOVER", state.projects["dyn4k-core"])
            assertEquals("outside sentinel", Files.readString(outside))
            assertTrue(Files.isDirectory(repository.resolve("dyn4k-core/karma.config.d")))
        }
    }

    test("the locked chain and file refuse symlinks") {
        safariWindowsTemp { root ->
            val repository = root.resolve("source")
            val packageDirectory = repository.resolve("package")
            Files.createDirectories(packageDirectory)
            Files.writeString(packageDirectory.resolve("config.js"), "approved\n")
            val outside = root.resolve("outside")
            Files.createDirectories(outside)
            val sentinel = outside.resolve("config.js")
            Files.writeString(sentinel, "outside\n")
            Files.createSymbolicLink(repository.resolve("linked"), outside)
            Files.createSymbolicLink(packageDirectory.resolve("linked.js"), sentinel)
            PosixWindowsFileKernel().use { kernel ->
                LockedDirectory(repository, Path.of("package"), kernel = kernel).use { directory ->
                    val descriptor = directory.openFile("config.js")
                    try {
                        assertEquals("approved\n", String(descriptor.read(100)))
                    } finally {
                        descriptor.close()
                    }
                    assertFailsWith<IllegalArgumentException> {
                        directory.openFile("linked.js")
                    }
                    val empty = packageDirectory.resolve("empty")
                    Files.createDirectory(empty)
                    directory.child("empty", removable = true).use { held ->
                        held.removeEmpty()
                    }
                    assertFalse(Files.exists(empty))
                }
                assertFailsWith<IllegalArgumentException> {
                    LockedDirectory(repository, Path.of("linked"), kernel = kernel)
                }
            }
            assertEquals("outside\n", Files.readString(sentinel))
        }
    }
}

/** A child locked directory whose unlink deletes the real directory. */
private class SafariDirectoryFake(override val path: Path) : SafariLockedDirectory {
    override fun child(name: String, removable: Boolean): SafariLockedDirectory =
        SafariDirectoryFake(path.resolve(name))

    override fun openFile(name: String): SafariHandle = SafariPathHandle(path.resolve(name))

    override fun removeEmpty() {
        Files.delete(path)
    }

    override fun close() {}
}

/** A child locked directory whose close swaps the directory for a fresh empty one. */
private class SafariSwappingDirectory(override val path: Path) : SafariLockedDirectory {
    override fun child(name: String, removable: Boolean): SafariLockedDirectory =
        SafariSwappingDirectory(path.resolve(name))

    override fun openFile(name: String): SafariHandle = SafariPathHandle(path.resolve(name))

    override fun removeEmpty() {
        Files.delete(path)
    }

    override fun close() {
        if (Files.exists(path)) {
            Files.move(path, path.resolveSibling("karma.config.d.moved"))
        }
        Files.createDirectory(path)
    }
}

/** The stage state is only reachable through the snapshot; keep the helper referenced. */
private val unusedPrimitive = JsonPrimitive("")
