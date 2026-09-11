@file:OptIn(org.jetbrains.kotlin.gradle.ExperimentalWasmDsl::class)
import org.jetbrains.kotlin.gradle.dsl.JsModuleKind
plugins { kotlin("multiplatform") version "2.4.20" }
repositories { mavenCentral() }
kotlin {
 js {
  nodejs()
  binaries.executable()
  compilerOptions { target.set("es5"); moduleKind.set(JsModuleKind.MODULE_UMD) }
 }
 wasmJs { nodejs(); binaries.executable(); compilerOptions { freeCompilerArgs.add("-Xwasm-use-new-exception-proposal=false") } }
 wasmWasi { nodejs(); binaries.executable(); compilations.configureEach { compileTaskProvider.configure { compilerOptions { freeCompilerArgs.add("-Xwasm-use-new-exception-proposal") } } } }
}
