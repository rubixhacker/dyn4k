param(
    [Parameter(Mandatory = $true)][string]$OutputDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$versionToken = '(?<![-A-Za-z0-9_~+/])2\.4\.20(?![-A-Za-z0-9_~+/]|\.[A-Za-z0-9])'
$source = Join-Path $PSScriptRoot 'WindowsCollisionScalarControl.kt'
$konanHome = Join-Path $env:USERPROFILE '.konan/kotlin-native-prebuilt-windows-x86_64-2.4.20'
$konanc = Join-Path $konanHome 'bin/kotlinc-native.bat'
$modes = @(
    @{ Name = 'debug-g'; Flags = @('-g') }
    @{ Name = 'default'; Flags = @() }
    @{ Name = 'optimized-opt'; Flags = @('-opt') }
)
$failures = [System.Collections.Generic.List[string]]::new()
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

try {
    if (-not (Test-Path -LiteralPath $konanc -PathType Leaf)) { throw "Kotlin/Native compiler is missing: $konanc" }
    $version = (& $konanc -version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $version -notmatch $versionToken) {
        throw "Kotlin/Native version check failed: $version"
    }
    Set-Content -Path (Join-Path $OutputDirectory 'kotlin-native-version.txt') -Value $version
    $sourceSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash.ToLowerInvariant()
    Set-Content -Path (Join-Path $OutputDirectory 'source-sha256.txt') -Value "$sourceSha256  tools/diagnostic/windows_collision/WindowsCollisionScalarControl.kt"
} catch {
    Set-Content -Path (Join-Path $OutputDirectory 'setup-status.txt') -Value "FAILED: $($_.ToString())"
    exit 1
}

foreach ($mode in $modes) {
    $modeDirectory = Join-Path $OutputDirectory $mode.Name
    New-Item -ItemType Directory -Force -Path $modeDirectory | Out-Null
    $outputBase = Join-Path $modeDirectory 'windows-collision-scalar'
    $executable = "${outputBase}.exe"
    $compilerArguments = @($source, '-target', 'mingw_x64') + $mode.Flags + @('-o', $outputBase)
    [pscustomobject]@{
        mode = $mode.Name
        executable = $konanc
        arguments = $compilerArguments
        sourceSha256 = $sourceSha256
    } | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $modeDirectory 'compiler-command.json')

    $compilerExit = 1
    $compilerStdout = Join-Path $modeDirectory 'compiler-stdout.log'
    $compilerStderr = Join-Path $modeDirectory 'compiler-stderr.log'
    try {
        & $konanc @compilerArguments 1> $compilerStdout 2> $compilerStderr
        $compilerExit = $LASTEXITCODE
        if ($null -eq $compilerExit) { $compilerExit = 1 }
    } catch {
        $_ | Out-String | Set-Content -Path (Join-Path $modeDirectory 'compiler-error.log')
    }
    Set-Content -Path (Join-Path $modeDirectory 'compiler-exit-code.txt') -Value $compilerExit
    if (Test-Path -LiteralPath $executable -PathType Leaf) {
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $executable).Hash.ToLowerInvariant()
        Set-Content -Path (Join-Path $modeDirectory 'executable-sha256.txt') -Value "$hash  windows-collision-scalar.exe"
    } else {
        Set-Content -Path (Join-Path $modeDirectory 'executable-status.txt') -Value 'UNAVAILABLE: compiler did not produce a PE'
    }
    if ($compilerExit -ne 0 -or -not (Test-Path -LiteralPath $executable -PathType Leaf)) {
        $failures.Add("$($mode.Name): compiler exit $compilerExit or PE unavailable")
        Set-Content -Path (Join-Path $modeDirectory 'run-exit-code.txt') -Value 'NOT_RUN'
        continue
    }

    $runExit = 1
    $runOutput = Join-Path $modeDirectory 'native-scalar.tsv'
    $runStderr = Join-Path $modeDirectory 'run-stderr.log'
    try {
        & $executable 1> $runOutput 2> $runStderr
        $runExit = $LASTEXITCODE
        if ($null -eq $runExit) { $runExit = 1 }
    } catch {
        $_ | Out-String | Set-Content -Path (Join-Path $modeDirectory 'run-error.log')
    }
    Set-Content -Path (Join-Path $modeDirectory 'run-exit-code.txt') -Value $runExit
    if ($runExit -ne 0) { $failures.Add("$($mode.Name): executable exit $runExit") }
}

if ($failures.Count -gt 0) {
    $failures | Set-Content -Path (Join-Path $OutputDirectory 'mode-errors.txt')
    Set-Content -Path (Join-Path $OutputDirectory 'mode-status.txt') -Value 'FAILED'
    exit 1
}
Set-Content -Path (Join-Path $OutputDirectory 'mode-status.txt') -Value 'OK'
exit 0
