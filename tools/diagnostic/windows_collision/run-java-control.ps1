param(
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

$javac = Join-Path $JdkHome 'bin/javac.exe'
$java = Join-Path $JdkHome 'bin/java.exe'
$scriptSource = Join-Path $PSScriptRoot 'WindowsCollisionJavaControl.java'
$traceSource = Join-Path $PSScriptRoot 'WindowsCollisionJavaTrace.java'
$classes = Join-Path $OutputDirectory 'classes'
New-Item -ItemType Directory -Force -Path $classes | Out-Null
& $javac -Xlint:-options --release 8 -cp $jar -d $classes $scriptSource $traceSource
if ($LASTEXITCODE -ne 0) { throw "javac failed: $LASTEXITCODE" }

$rawPath = Join-Path $OutputDirectory 'dyn4j-6.0.0-windows-control.tsv'
& $java -cp "$classes;$jar" org.dyn4j.collision.narrowphase.WindowsCollisionJavaControl | Tee-Object -FilePath $rawPath
if ($LASTEXITCODE -ne 0) { throw "Java control failed: $LASTEXITCODE" }
$records = @(Get-Content $rawPath | Where-Object { $_ -like 'DYN4K_COLLISION_DIAGNOSTIC*' })
if ($records.Count -ne 72) { throw "Expected 72 Java diagnostic records; got $($records.Count)" }
Write-Output "PINNED_DYN4J_CONTROL jarSha256=$actualJarSha256 sourceRevision=$actualSourceRevision records=$($records.Count) raw=$rawPath"
