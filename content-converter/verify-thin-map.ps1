param(
    [string]$InputPackage = 'C:\Games\_judgment-scratch\GearGame_P.decompressed.xxx',
    [string]$ArrayIndex = 'C:\Games\_judgment-scratch\array-types-v845.json',
    [string]$StagedMap = 'C:\Games\Gears 3 Files\gears_of_war_3_2011-09-14\GearGame\Content\Maps\Judgment_GearGame_P.gear'
)

$ErrorActionPreference = 'Stop'

$expectedInput = '1A45928E96678BB414B810C6D91B7F6B279BE8A718DBF35346434AA0FF02A18D'
$expectedIndex = '457E51721EF1BA039F7D2112548D4462942B5169D39879CC959331CF4B5D1A11'
$expectedOutput = '0849E7EA6E0DD73DDCECE8DB787A4B5B591C75E9EA1BF036ECA19389590D5353'
$converter = Join-Path $PSScriptRoot 'be2le.py'

function Assert-Sha256([string]$Path, [string]$Expected, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Label is missing: $Path"
    }
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    if ($actual -ne $Expected) {
        throw "$Label hash mismatch: expected $Expected, got $actual"
    }
}

Assert-Sha256 $InputPackage $expectedInput 'Judgment thin-map input'
Assert-Sha256 $ArrayIndex $expectedIndex 'v845 array index'

$tempOutput = Join-Path ([IO.Path]::GetTempPath()) ("judgment-thin-map-{0}.xxx" -f [guid]::NewGuid())
try {
    & python $converter $InputPackage $tempOutput $ArrayIndex
    if ($LASTEXITCODE -ne 0) {
        throw "Converter failed with exit code $LASTEXITCODE"
    }
    Assert-Sha256 $tempOutput $expectedOutput 'Converted thin map'
    if ($StagedMap) {
        Assert-Sha256 $StagedMap $expectedOutput 'Staged thin map'
    }
    Write-Host "PASS: deterministic Judgment thin-map conversion $expectedOutput"
}
finally {
    if (Test-Path -LiteralPath $tempOutput) {
        Remove-Item -LiteralPath $tempOutput -Force
    }
}
