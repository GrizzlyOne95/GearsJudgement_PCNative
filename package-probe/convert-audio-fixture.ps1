[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $Package,

    [Parameter(Mandatory = $true)]
    [ValidateRange(1, 2147483647)]
    [int] $ExportIndex,

    [Parameter(Mandatory = $true)]
    [string] $OutputDirectory,

    [ValidateRange(0, 100)]
    [int] $Quality = 40,

    [string] $VgmstreamCli,

    [switch] $MakeEngineTestAlias
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Resolve-RequiredFile([string] $Path, [string] $Description) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Description was not found: $Path"
    }
    return (Resolve-Path -LiteralPath $Path).Path
}

function Invoke-Checked([string] $Executable, [string[]] $Arguments) {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE`: $Executable"
    }
}

$packagePath = Resolve-RequiredFile $Package 'Uncompressed Judgment package'
$probe = Resolve-RequiredFile (Join-Path $PSScriptRoot 'build\Release\judgment-package-probe.exe') 'Package probe'
$oggCooker = Resolve-RequiredFile (Join-Path $PSScriptRoot 'build\Release\judgment-wav-to-ogg.exe') 'Ogg cooker'

if ([string]::IsNullOrWhiteSpace($VgmstreamCli)) {
    $VgmstreamCli = Join-Path $PSScriptRoot 'build\tools\vgmstream\current\vgmstream-cli.exe'
}
$vgmstream = Resolve-RequiredFile $VgmstreamCli 'vgmstream CLI'

$outputRoot = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null

$baseName = '{0}.export-{1}' -f [IO.Path]::GetFileNameWithoutExtension($packagePath), $ExportIndex
$xma = Join-Path $outputRoot "$baseName.xma"
$wav = Join-Path $outputRoot "$baseName.wav"
$ogg = Join-Path $outputRoot "$baseName.ogg"
$fixture = Join-Path $outputRoot "$baseName.pc-fixture.upk"
$fixtureManifest = Join-Path $outputRoot "$baseName.pc-fixture.manifest.json"
$pipelineManifest = Join-Path $outputRoot "$baseName.pipeline.json"
$testFixture = Join-Path $outputRoot 'TestSounds.upk'
$testManifest = Join-Path $outputRoot 'TestSounds.manifest.json'

$targets = @($xma, $wav, $ogg, $fixture, $fixtureManifest, $pipelineManifest)
if ($MakeEngineTestAlias) {
    $targets += @($testFixture, $testManifest)
}
$collision = $targets | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if ($collision) {
    throw "Refusing to overwrite an existing pipeline artifact: $collision"
}

Invoke-Checked $probe @('--extract-xma', $packagePath, [string]$ExportIndex, $xma)
Invoke-Checked $vgmstream @('-i', '-o', $wav, $xma)
Invoke-Checked $oggCooker @($wav, $ogg, [string]$Quality)
Invoke-Checked $probe @('--convert-audio-fixture', $packagePath, [string]$ExportIndex, $ogg, $fixture)
Invoke-Checked $probe @('--manifest', $fixture, $fixtureManifest)

if ($MakeEngineTestAlias) {
    Invoke-Checked $probe @('--make-vorbis-time-test-fixture', $fixture, $testFixture)
    Invoke-Checked $probe @('--manifest', $testFixture, $testManifest)
}

$artifactPaths = @($xma, $wav, $ogg, $fixture, $fixtureManifest)
if ($MakeEngineTestAlias) {
    $artifactPaths += @($testFixture, $testManifest)
}
$artifacts = foreach ($path in $artifactPaths) {
    $item = Get-Item -LiteralPath $path
    $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $path
    [ordered]@{
        path = $item.FullName
        bytes = $item.Length
        sha256 = $hash.Hash
    }
}

$metadata = [ordered]@{
    format = 'judgment-native-audio-pipeline-v1'
    source_package = $packagePath
    export_index = $ExportIndex
    unreal_quality = $Quality
    package_probe = $probe
    ogg_cooker = $oggCooker
    vgmstream_cli = $vgmstream
    vgmstream_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $vgmstream).Hash
    artifacts = $artifacts
}
$metadata | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $pipelineManifest -Encoding utf8

Write-Output "Audio fixture pipeline completed: $fixture"
if ($MakeEngineTestAlias) {
    Write-Output "Engine test alias completed: $testFixture"
}
Write-Output "Pipeline manifest: $pipelineManifest"
