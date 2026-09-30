# Judgment-only tests. NOHOMEDIR keeps configuration and save writes in this copy.
param(
    [string]$Exe = 'GearGame-JudgmentLoader-ws9-skeletalmesh-verified.exe',
    [string]$Tag = 'ws9-skeletalmesh',
    [int]$BootSeconds = 75
)
$ErrorActionPreference = 'Stop'
$workspace = 'C:\Games\Gears 3 Files\Judgment Port Workspace'
$binDir = Join-Path $workspace 'Binaries\Win32'
if ($Exe -ne [IO.Path]::GetFileName($Exe) -or $Exe -notlike 'GearGame-JudgmentLoader-*.exe') {
    throw 'Specify a Judgment loader filename in the isolated workspace.'
}
if ($Tag -notmatch '^[A-Za-z0-9._-]+$') { throw 'Invalid log tag.' }
$exePath = Join-Path $binDir $Exe
if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) { throw "Missing loader: $exePath" }
$common = '-user -NOHOMEDIR -JUDGMENTPKGVER=845 -forcelogflush -unattended -nopause -nosound -nullrhi'
$definitions = @(
    @{ Name = 'pkginfo'; Args = "PkgInfo $common -JUDGMENTCDOWATCH" },
    @{ Name = 'thinmap'; Args = "Judgment_GearGame_P?game=geargamecontent.GearGameAID?listen $common -JUDGNATIVEBINDOK -JUDGLIFE -JUDGPRELOADTRACE" },
    @{ Name = 'sp_e2_p'; Args = "Judgment_SP_E2_P?game=geargamecontent.GearGameAID?listen $common -JUDGNATIVEBINDOK -JUDGLIFE -JUDGPRELOADTRACE" }
)
$results = foreach ($definition in $definitions) {
    $log = Join-Path $workspace "GearGame\Logs\regress-$Tag-$($definition.Name).log"
    if (Test-Path -LiteralPath $log) { throw "Refusing to overwrite existing evidence: $log" }
    $process = Start-Process -FilePath $exePath -ArgumentList "$($definition.Args) -ABSLOG=`"$log`"" -WorkingDirectory $binDir -WindowStyle Hidden -PassThru
    try {
        $timedOut = -not $process.WaitForExit($BootSeconds * 1000)
    } finally {
        if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force; $process.WaitForExit() }
    }
    $text = if (Test-Path -LiteralPath $log) { [IO.File]::ReadAllText($log) } else { '' }
    $critical = [regex]::Match($text, '(?m)^.*Critical: appError called: (.*)$').Groups[1].Value
    $leaves = [regex]::Matches($text, '\[JUDGPRELOAD\] leave exp=(\d+) obj=(\S+) consumed=(\d+) size=(\d+)')
    $mismatches = @($leaves | Where-Object { $_.Groups[3].Value -ne $_.Groups[4].Value }).Count
    $possessed = $text.Contains('[JUDGLIFE] pawn-owner-pc') -and $text.Contains('[JUDGLIFE] world-first-tick')
    $meshNames = @('COG_Barrick', 'COG_Gus_Summer_CamSkel', 'COG_Clayton_Carmine')
    $meshLoads = @($leaves | Where-Object { $_.Groups[2].Value -in $meshNames }).Count
    $packedLoads = [regex]::Matches($text, '\[JUDGMESH\] unpacked vertices=').Count
    if ($definition.Name -eq 'pkginfo') {
        $result = if (-not $timedOut -and $process.ExitCode -eq 0 -and $text.Contains('Success - 0 error(s)')) { 'PASS' } else { 'FAIL' }
    } elseif ($definition.Name -eq 'thinmap') {
        $result = if ($timedOut -and $possessed -and -not $critical -and $mismatches -eq 0) { 'PASS' } else { 'FAIL' }
    } else {
        $meshPass = $leaves.Count -ge 1402 -and $mismatches -eq 0 -and $meshLoads -eq 3 -and $packedLoads -eq 4 -and $possessed
        $result = if (-not $meshPass) { 'FAIL' } elseif ($critical) { 'BLOCKED_AFTER_BOOT' } elseif ($timedOut) { 'PASS' } else { 'FAIL' }
    }
    $row = [pscustomobject]@{
        Case = $definition.Name; Result = $result; ExactLoads = $leaves.Count - $mismatches
        SizeMismatches = $mismatches; MeshLoads = $meshLoads; PackedLoads = $packedLoads
        Possessed = $possessed; TimedOut = $timedOut; ExitCode = $process.ExitCode
        Critical = $critical; Log = $log
    }
    $row | ConvertTo-Json -Compress | Write-Host
    $row
}
$summaryPath = Join-Path $workspace "GearGame\Logs\regress-$Tag-results.json"
$results | ConvertTo-Json | Set-Content -LiteralPath $summaryPath -Encoding UTF8
if ($results.Result -contains 'FAIL') { exit 1 }
if ($results.Result -contains 'BLOCKED_AFTER_BOOT') { exit 2 }
