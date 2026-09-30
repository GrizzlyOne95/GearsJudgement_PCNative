# Judgment-only tests. NOHOMEDIR keeps configuration and save writes in this copy.
param(
    [string]$Exe = 'GearGame-JudgmentLoader-ws14-headless-streaming-init-v2.exe',
    [string]$Tag = ('ws14-' + (Get-Date -Format 'yyyyMMdd-HHmmssfff')),
    [int]$BootSeconds = 75,
    [switch]$PrototypeTrace = $true,
    [ValidateRange(0,120)] [int]$SampleStackAtSeconds = 0,
    [string]$DebuggerExe,
    [string]$StreamingPackages = 'SP_E2_01,SP_E2_02,SP_E2_W,SP_E2_01_S,SP_E2_Audio,SP_E2_02_S',
    [ValidateSet('pkginfo','thinmap','sp_e2_p')]
    [string[]]$Cases = @('pkginfo','thinmap','sp_e2_p')
)
$ErrorActionPreference = 'Stop'
$workspace = 'C:\Games\Gears 3 Files\Judgment Port Workspace'
$binDir = Join-Path $workspace 'Binaries\Win32'
if ($Exe -ne [IO.Path]::GetFileName($Exe) -or $Exe -notlike 'GearGame-JudgmentLoader-*.exe') {
    throw 'Specify a Judgment loader filename in the isolated workspace.'
}
if ($Tag -notmatch '^[A-Za-z0-9._-]+$') { throw 'Invalid log tag.' }
if ($SampleStackAtSeconds -and ($SampleStackAtSeconds -ge $BootSeconds -or -not (Test-Path -LiteralPath $DebuggerExe -PathType Leaf))) {
    throw 'Stack sampling requires a debugger executable and a sampling time before the boot deadline.'
}
$exePath = Join-Path $binDir $Exe
if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) { throw "Missing loader: $exePath" }
# These tests exercise loading and world ticks without texture streaming. The
# ws14 helper disables streaming before startup loads and skips NullRHI cache saves.
$common = '-user -NOHOMEDIR -JUDGMENTPKGVER=845 -forcelogflush -unattended -nopause -nosound -nullrhi -NoTextureStreaming'
if ($PrototypeTrace) { $common += ' -JUDGPROTOTRACE' }
if ($StreamingPackages) {
    if ($StreamingPackages -notmatch '^[A-Za-z0-9_]+(,[A-Za-z0-9_]+)*$') { throw 'Invalid streaming package list.' }
    foreach ($package in $StreamingPackages.Split(',')) {
        $map = Join-Path $workspace "GearGame\Content\Maps\$package.gear"
        if (-not (Test-Path -LiteralPath $map -PathType Leaf)) { throw "Missing converted streaming map: $map" }
    }
    $common += " -JUDGMENTSTREAMINGPACKAGES=$StreamingPackages"
}
$definitions = @(
    @{ Name = 'pkginfo'; Args = "PkgInfo $common -JUDGMENTCDOWATCH" },
    @{ Name = 'thinmap'; Args = "Judgment_GearGame_P?game=geargamecontent.GearGameAID?listen $common -JUDGNATIVEBINDOK -JUDGLIFE -JUDGPRELOADTRACE" },
    @{ Name = 'sp_e2_p'; Args = "Judgment_SP_E2_P?game=geargamecontent.GearGameAID?listen $common -JUDGNATIVEBINDOK -JUDGLIFE -JUDGPRELOADTRACE" }
)
$results = foreach ($definition in $definitions | Where-Object { $_.Name -in $Cases }) {
    $log = Join-Path $workspace "GearGame\Logs\regress-$Tag-$($definition.Name).log"
    if (Test-Path -LiteralPath $log) { throw "Refusing to overwrite existing evidence: $log" }
    $process = Start-Process -FilePath $exePath -ArgumentList "$($definition.Args) -ABSLOG=`"$log`"" -WorkingDirectory $binDir -WindowStyle Hidden -PassThru
    try {
        $timer = [Diagnostics.Stopwatch]::StartNew()
        if ($SampleStackAtSeconds -and -not $process.WaitForExit($SampleStackAtSeconds * 1000)) {
            $commands = $log + '.stack-commands.txt'
            $stackLog = $log + '.stack.log'
            $debuggerConsole = $log + '.debugger-console.log'
            foreach ($path in @($commands, $stackLog, $debuggerConsole)) {
                if (Test-Path -LiteralPath $path) { throw "Refusing to replace diagnostic evidence: $path" }
            }
            @('~0s', 'kb 24', 'qd') | Set-Content -LiteralPath $commands -Encoding Ascii
            # Noninvasive, read-only inspection of this exact tracked helper;
            # qd detaches and leaves it running for the rest of the test.
            & $DebuggerExe -pv -p $process.Id -y $binDir -logo $stackLog -cf $commands > $debuggerConsole 2>&1
        }
        $remainingMilliseconds = [Math]::Max(0, $BootSeconds * 1000 - [int]$timer.ElapsedMilliseconds)
        $timedOut = -not $process.WaitForExit($remainingMilliseconds)
    } finally {
        if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force; $process.WaitForExit() }
    }
    $text = if (Test-Path -LiteralPath $log) { [IO.File]::ReadAllText($log) } else { '' }
    $critical = [regex]::Match($text, '(?m)^.*Critical: appError called: (.*)$').Groups[1].Value
    $leaves = [regex]::Matches($text, '\[JUDGPRELOAD\] leave exp=(\d+) obj=(\S+) consumed=(\d+) size=(\d+)')
    $mismatches = @($leaves | Where-Object { $_.Groups[3].Value -ne $_.Groups[4].Value }).Count
    $possessed = $text.Contains('[JUDGLIFE] pawn-owner-pc') -and $text.Contains('[JUDGLIFE] world-first-tick')
    $completedTicks = [regex]::Matches($text, '(?m)^\[([0-9.]+)\].*\[JUDGPROTO\] tick-end serial=(\d+) game-time=([0-9.]+) levels=(\d+)')
    $latestCompletedTickSeconds = if ($completedTicks.Count) { [double]::Parse($completedTicks[$completedTicks.Count - 1].Groups[1].Value, [Globalization.CultureInfo]::InvariantCulture) } else { 0 }
    $tickPass = -not $PrototypeTrace -or ($completedTicks.Count -ge 2 -and $latestCompletedTickSeconds -ge ($BootSeconds - 15))
    $meshNames = @('COG_Barrick', 'COG_Gus_Summer_CamSkel', 'COG_Clayton_Carmine')
    $meshLoads = [regex]::Matches($text, '\[JUDGPRELOAD\] leave exp=\d+ obj=(COG_Barrick|COG_Gus_Summer_CamSkel|COG_Clayton_Carmine) .* pkg=Judgment_SP_E2_P(?:\s|$)').Count
    $packedLoads = [regex]::Matches($text, '\[JUDGMESH\] unpacked vertices=').Count
    $basePackedLoads = 0
    foreach ($meshName in $meshNames) {
        $enterPattern = '\[JUDGPRELOAD\] enter exp=(\d+) obj=' + [regex]::Escape($meshName) + ' cls=SkeletalMesh[^\r\n]* pkg=Judgment_SP_E2_P(?:\s|$)'
        $enter = [regex]::Match($text, $enterPattern)
        if ($enter.Success) {
            $leavePattern = '\[JUDGPRELOAD\] leave exp=' + $enter.Groups[1].Value + ' obj=' + [regex]::Escape($meshName) + '[^\r\n]* pkg=Judgment_SP_E2_P(?:\s|$)'
            $leave = [regex]::Match($text.Substring($enter.Index + $enter.Length), $leavePattern)
            if ($leave.Success) {
                $basePackedLoads += [regex]::Matches($text.Substring($enter.Index + $enter.Length, $leave.Index), '\[JUDGMESH\] unpacked vertices=').Count
            }
        }
    }
    $streamedLoads = @{}
    foreach ($package in $StreamingPackages.Split(',') | Where-Object { $_ }) {
        $streamedLoads[$package] = [regex]::Matches($text, ('\[JUDGPRELOAD\] leave .* pkg=' + [regex]::Escape($package) + '(?:\s|$)')).Count
    }
    if ($definition.Name -eq 'pkginfo') {
        $result = if (-not $timedOut -and $process.ExitCode -eq 0 -and $text.Contains('Success - 0 error(s)')) { 'PASS' } else { 'FAIL' }
    } elseif ($definition.Name -eq 'thinmap') {
        $result = if ($timedOut -and $possessed -and -not $critical -and $mismatches -eq 0 -and $tickPass) { 'PASS' } else { 'FAIL' }
    } else {
        $meshPass = $leaves.Count -ge 1402 -and $mismatches -eq 0 -and $meshLoads -eq 3 -and $basePackedLoads -eq 4 -and $possessed
        foreach ($package in $streamedLoads.Keys) { $meshPass = $meshPass -and $streamedLoads[$package] -gt 0 }
        $result = if (-not $meshPass) { 'FAIL' } elseif ($critical -or -not $tickPass) { 'BLOCKED_AFTER_BOOT' } elseif ($timedOut) { 'PASS' } else { 'FAIL' }
    }
    $row = [pscustomobject]@{
        Case = $definition.Name; Result = $result; ExactLoads = $leaves.Count - $mismatches
        SizeMismatches = $mismatches; MeshLoads = $meshLoads; PackedLoads = $packedLoads
        BasePackedLoads = $basePackedLoads; CompletedTickReports = $completedTicks.Count
        LatestCompletedTickSeconds = $latestCompletedTickSeconds; PrototypeTrace = [bool]$PrototypeTrace
        Possessed = $possessed; TimedOut = $timedOut; ExitCode = $process.ExitCode
        Critical = $critical; Log = $log
        StreamingLoads = $streamedLoads
    }
    $row | ConvertTo-Json -Compress | Write-Host
    $row
}
$summaryPath = Join-Path $workspace "GearGame\Logs\regress-$Tag-results.json"
$results | ConvertTo-Json | Set-Content -LiteralPath $summaryPath -Encoding UTF8
if ($results.Result -contains 'FAIL') { exit 1 }
if ($results.Result -contains 'BLOCKED_AFTER_BOOT') { exit 2 }
