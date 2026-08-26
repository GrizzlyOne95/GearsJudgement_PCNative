param(
    [string]$SourceRoot = 'C:\Games\Gears 3 Files\gears_of_war_3_2011-09-14',
    [string]$ToolchainRoot = 'C:\Games\Gears 3 Files\_Toolchain\PortableVC9\Layout',
    [string]$VersionTag,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$env:VS90COMNTOOLS = Join-Path $ToolchainRoot 'Microsoft Visual Studio 9.0\Common7\Tools\'
$env:UE3_WINDOWS_SDK_DIR = Join-Path $ToolchainRoot 'Microsoft SDKs\Windows\v6.0A'

$ubt = Join-Path $SourceRoot 'Development\Intermediate\UnrealBuildTool\Release\UnrealBuildTool.exe'
$devExe = Join-Path $SourceRoot 'Binaries\Win32\GearGame-JudgmentLoader-dev.exe'
if (-not (Test-Path -LiteralPath $ubt -PathType Leaf)) {
    throw "UnrealBuildTool is missing: $ubt"
}

& $ubt GearGame Win32 Release -OUTPUT $devExe
if ($LASTEXITCODE -ne 0) {
    throw "Judgment loader build failed with exit code $LASTEXITCODE"
}

$artifact = $devExe
if ($VersionTag) {
    if ($VersionTag -notmatch '^[A-Za-z0-9._-]+$') {
        throw 'VersionTag may contain only letters, digits, dot, underscore, and hyphen.'
    }
    $artifact = Join-Path $SourceRoot "Binaries\Win32\GearGame-JudgmentLoader-$VersionTag.exe"
    if ((Test-Path -LiteralPath $artifact) -and -not $Force) {
        throw "Versioned artifact already exists (use -Force to replace it): $artifact"
    }
    Copy-Item -LiteralPath $devExe -Destination $artifact -Force:$Force
}

$file = Get-Item -LiteralPath $artifact
$hash = (Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash
Write-Host "PASS: $($file.FullName)"
Write-Host "Size: $($file.Length)"
Write-Host "SHA256: $hash"
