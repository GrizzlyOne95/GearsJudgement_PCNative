[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $Package,

    [Parameter(Mandatory = $true)]
    [string] $OutputDirectory,

    [ValidateRange(0, 100)]
    [int] $Quality = 40,

    [string] $VgmstreamCli
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
$xmaDirectory = Join-Path $outputRoot 'xma'
$wavDirectory = Join-Path $outputRoot 'wav'
$oggDirectory = Join-Path $outputRoot 'ogg'
$packageName = [IO.Path]::GetFileNameWithoutExtension($packagePath)
$sourceManifest = Join-Path $outputRoot "$packageName.source.manifest.json"
$convertedPackage = Join-Path $outputRoot "$packageName.pc.upk"
$convertedManifest = Join-Path $outputRoot "$packageName.pc.manifest.json"
$pipelineManifest = Join-Path $outputRoot "$packageName.pipeline.json"

$fixedTargets = @($sourceManifest, $convertedPackage, $convertedManifest, $pipelineManifest)
$collision = $fixedTargets | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if ($collision) {
    throw "Refusing to overwrite an existing pipeline artifact: $collision"
}
New-Item -ItemType Directory -Path $xmaDirectory, $wavDirectory, $oggDirectory -Force | Out-Null

Invoke-Checked $probe @('--manifest', $packagePath, $sourceManifest)
$metadata = Get-Content -LiteralPath $sourceManifest -Raw | ConvertFrom-Json
$waves = @($metadata.exports | Where-Object { $_.class_name -eq 'SoundNodeWave' })
if ($waves.Count -eq 0) {
    throw 'The source package contains no SoundNodeWave exports.'
}

$waveRecords = [Collections.Generic.List[object]]::new()
foreach ($wave in $waves) {
    $exportIndex = [int]$wave.package_index
    $xma = Join-Path $xmaDirectory "$exportIndex.xma"
    $wav = Join-Path $wavDirectory "$exportIndex.wav"
    $ogg = Join-Path $oggDirectory "$exportIndex.ogg"
    $waveCollision = @($xma, $wav, $ogg) |
        Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($waveCollision) {
        throw "Refusing to overwrite an existing wave artifact: $waveCollision"
    }

    Write-Output ("Converting export {0}/{1}: {2}" -f $exportIndex, $metadata.exports.Count, $wave.object_path)
    Invoke-Checked $probe @('--extract-xma', $packagePath, [string]$exportIndex, $xma)
    Invoke-Checked $vgmstream @('-i', '-o', $wav, $xma)
    Invoke-Checked $oggCooker @($wav, $ogg, [string]$Quality)

    $waveRecords.Add([pscustomobject][ordered]@{
        export_index = $exportIndex
        object_path = $wave.object_path
        xma = $xma
        wav = $wav
        ogg = $ogg
    })
}

Invoke-Checked $probe @('--convert-audio-package', $packagePath, $oggDirectory, $convertedPackage)
Invoke-Checked $probe @('--manifest', $convertedPackage, $convertedManifest)

$artifactPaths = @($sourceManifest, $convertedPackage, $convertedManifest)
foreach ($record in $waveRecords) {
    $artifactPaths += @($record.xma, $record.wav, $record.ogg)
}
$artifacts = foreach ($path in $artifactPaths) {
    $item = Get-Item -LiteralPath $path
    [ordered]@{
        path = $item.FullName
        bytes = $item.Length
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash
    }
}

$pipeline = [ordered]@{
    format = 'judgment-native-audio-package-pipeline-v1'
    source_package = $packagePath
    output_package = $convertedPackage
    wave_count = $waves.Count
    unreal_quality = $Quality
    package_probe = $probe
    ogg_cooker = $oggCooker
    vgmstream_cli = $vgmstream
    vgmstream_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $vgmstream).Hash
    waves = $waveRecords
    artifacts = $artifacts
}
$pipeline | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $pipelineManifest -Encoding utf8

Write-Output "Multi-wave audio package completed: $convertedPackage"
Write-Output "Converted $($waves.Count) SoundNodeWave exports."
Write-Output "Pipeline manifest: $pipelineManifest"
