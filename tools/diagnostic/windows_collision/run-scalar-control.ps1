param(
    [Parameter(Mandatory = $true)][string]$KonancHome,
    [Parameter(Mandatory = $true)][string]$JdkHome,
    [Parameter(Mandatory = $true)][string]$BaselineJar,
    [Parameter(Mandatory = $true)][string]$BaselineSource,
    [Parameter(Mandatory = $true)][string]$OutputDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$expectedJarSha256 = '204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e'
$expectedSourceRevision = '058bf6d982a0fb89b54050f929f6ea9dae53b714'
$jar = (Resolve-Path $BaselineJar).Path
$source = (Resolve-Path $BaselineSource).Path
$actualJarSha256 = (Get-FileHash -Algorithm SHA256 $jar).Hash.ToLowerInvariant()
if ($actualJarSha256 -ne $expectedJarSha256) { throw "Baseline JAR SHA-256 mismatch: $actualJarSha256" }
$actualSourceRevision = (& git -C $source rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $actualSourceRevision -ne $expectedSourceRevision) {
    throw "Baseline source revision mismatch: $actualSourceRevision"
}

$konanc = Join-Path $KonancHome 'bin/kotlinc-native.bat'
$javac = Join-Path $JdkHome 'bin/javac.exe'
$java = Join-Path $JdkHome 'bin/java.exe'
$version = (& $konanc -version 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $version -notmatch '(?<![\w.+-])2\.4\.20(?![\w.+-])') { throw "Kotlin/Native version mismatch: $version" }
$validator = Join-Path $PSScriptRoot 'validate-scalar-control.py'
& python $validator self-test
if ($LASTEXITCODE -ne 0) { throw "Scalar validator self-test failed: $LASTEXITCODE" }
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$env:TEMP = $OutputDirectory
$env:TMP = $OutputDirectory
$nativeBase = Join-Path $OutputDirectory 'windows-collision-scalar'
& $konanc (Join-Path $PSScriptRoot 'WindowsCollisionScalarControl.kt') -target mingw_x64 -o $nativeBase
if ($LASTEXITCODE -ne 0) { throw "konanc failed: $LASTEXITCODE" }
$nativeRaw = Join-Path $OutputDirectory 'native-scalar.tsv'
& "${nativeBase}.exe" | Tee-Object -FilePath $nativeRaw
if ($LASTEXITCODE -ne 0) { throw "Native scalar control failed: $LASTEXITCODE" }

$classes = Join-Path $OutputDirectory 'java-classes'
New-Item -ItemType Directory -Force -Path $classes | Out-Null
& $javac -Xlint:-options --release 8 -cp $jar -d $classes (Join-Path $PSScriptRoot 'WindowsCollisionScalarJavaControl.java')
if ($LASTEXITCODE -ne 0) { throw "javac failed: $LASTEXITCODE" }
$javaRaw = Join-Path $OutputDirectory 'java-scalar.tsv'
& $java -Djava.io.tmpdir=$OutputDirectory -cp "$classes;$jar" org.dyn4j.collision.narrowphase.WindowsCollisionScalarJavaControl | Tee-Object -FilePath $javaRaw
if ($LASTEXITCODE -ne 0) { throw "Java scalar control failed: $LASTEXITCODE" }

& python $validator validate --native $nativeRaw --java $javaRaw
if ($LASTEXITCODE -ne 0) { throw "Scalar output validation failed: $LASTEXITCODE" }
Write-Output "PINNED_SCALAR_CONTROL sourceRevision=$actualSourceRevision jarSha256=$actualJarSha256 konanc=$version rows=7"
Get-FileHash -Algorithm SHA256 -Path @("${nativeBase}.exe", $nativeRaw, $javaRaw)
