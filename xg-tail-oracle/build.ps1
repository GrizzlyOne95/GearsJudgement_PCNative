<#
    Builds the Win32 XG packed-mip-tail oracle.

    The Xenon console-tools DLLs (XeTools.dll, Xbox360Tools.dll) are 32-bit, so
    this host must be 32-bit too.  package-probe stays x64 and dependency-free;
    this tool is only a measurement device.
#>
[CmdletBinding()]
param(
    [string] $Gears3SourceRoot = 'C:\Games\Gears 3 Files\gears_of_war_3_2011-09-14',
    [string] $OutputDirectory = (Join-Path $PSScriptRoot 'build'),
    [switch] $Clean
)

$ErrorActionPreference = 'Stop'

$includeDir = Join-Path $Gears3SourceRoot 'Development\Src\Engine\Inc'
$header = Join-Path $includeDir 'UnConsoleTools.h'
if (-not (Test-Path -LiteralPath $header)) {
    throw "UnConsoleTools.h was not found under '$includeDir'. Pass -Gears3SourceRoot."
}

if ($Clean -and (Test-Path -LiteralPath $OutputDirectory)) {
    Remove-Item -LiteralPath $OutputDirectory -Recurse -Force
}
if (-not (Test-Path -LiteralPath $OutputDirectory)) {
    New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
}

# Locate a 32-bit MSVC toolset.
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (-not (Test-Path -LiteralPath $vswhere)) { throw 'vswhere.exe was not found.' }
$vsPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vsPath) { throw 'No Visual Studio installation with the C++ toolset was found.' }

$vcvars = Join-Path $vsPath 'VC\Auxiliary\Build\vcvarsall.bat'
if (-not (Test-Path -LiteralPath $vcvars)) { throw "vcvarsall.bat was not found at '$vcvars'." }

$source = Join-Path $PSScriptRoot 'src\xg_tail_oracle.cpp'
$exe = Join-Path $OutputDirectory 'xg-tail-oracle.exe'

# vcvarsall x86 sets up the 32-bit target; /MT avoids a CRT redistributable
# dependency for a throwaway measurement tool.
$callLine = 'call "{0}" x86' -f $vcvars
# The doubled trailing backslash keeps cmd from treating it as an escape for
# the closing quote, which would swallow the /link arguments into /Fo.
$compileLine = 'cl /nologo /EHsc /W4 /O2 /MT /std:c++17 /I "{0}" "{1}" /Fe:"{2}" /Fo:"{3}\\" /link /SUBSYSTEM:CONSOLE' -f @(
    $includeDir, $source, $exe, $OutputDirectory)
$command = '{0} && {1}' -f $callLine, $compileLine

Write-Host "Building $exe (Win32)..."
& cmd.exe /c $command
if ($LASTEXITCODE -ne 0) { throw "Build failed with exit code $LASTEXITCODE." }

Write-Host "Built: $exe"
