# Judgment-only tests. NOHOMEDIR keeps configuration and save writes in this copy.
param(
    [string]$Exe = 'GearGame-JudgmentLoader-ws18-sequence-objectives.exe',
    [string]$Tag = ('ws18-' + (Get-Date -Format 'yyyyMMdd-HHmmssfff')),
    [int]$BootSeconds = 75,
    [switch]$PrototypeTrace = $true,
    [ValidateSet('NullRHI','D3D9')] [string]$Renderer = 'NullRHI',
    [switch]$CaptureScreenshot,
    [switch]$MaterialTrace,
    [switch]$SequenceTrace,
    [switch]$CampaignStartup,
    [switch]$RequirePlayerMesh = $true,
    [ValidateRange(0,120)] [int]$SampleStackAtSeconds = 0,
    [string]$DebuggerExe,
    [string]$StreamingPackages = 'SP_E2_01,SP_E2_02,SP_E2_W,SP_E2_01_S,SP_E2_Audio,SP_E2_02_S',
    [string]$AssetPackages = 'COG_Baird_Jack',
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
# ws16 honors the explicit option before startup loads and skips NullRHI cache saves.
$common = '-user -NOHOMEDIR -JUDGMENTPKGVER=845 -forcelogflush -unattended -nopause -nosound -NoTextureStreaming'
$common += if ($Renderer -eq 'NullRHI') { ' -nullrhi' } else { ' -d3d9 -windowed -ResX=1280 -ResY=720' }
if ($PrototypeTrace) { $common += ' -JUDGPROTOTRACE' }
if ($MaterialTrace) { $common += ' -JUDGMATERIALTRACE' }
if ($SequenceTrace -or $CampaignStartup) { $common += ' -JUDGSEQUENCETRACE' }
if ($CaptureScreenshot -and $Renderer -eq 'D3D9') { $common += ' -JUDGSHOT' }
$convertedPackages = (@($StreamingPackages, $AssetPackages) | Where-Object { $_ }) -join ','
if ($convertedPackages) {
    if ($convertedPackages -notmatch '^[A-Za-z0-9_]+(,[A-Za-z0-9_]+)*$') { throw 'Invalid converted package list.' }
    foreach ($package in $convertedPackages.Split(',')) {
        $map = Join-Path $workspace "GearGame\Content\Maps\$package.gear"
        if (-not (Test-Path -LiteralPath $map -PathType Leaf)) { throw "Missing converted streaming map: $map" }
    }
    $common += " -JUDGMENTSTREAMINGPACKAGES=$convertedPackages"
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
    $playerMeshes = [regex]::Matches($text, '\[JUDGPROTO\] player-mesh pawn=(\S+) mesh=(\S+) physics=(\S+) bones=(\d+) local-atoms=(\d+) space-bases=(\d+) animsets=(\d+) animations=(\S+) hidden=(\d+)')
    $latestPlayerMesh = if ($playerMeshes.Count) { $playerMeshes[$playerMeshes.Count - 1] } else { $null }
    $playerMeshPass = -not $RequirePlayerMesh -or ($latestPlayerMesh -and $latestPlayerMesh.Groups[2].Value -ne 'None' -and
        $latestPlayerMesh.Groups[3].Value -ne 'None' -and [int]$latestPlayerMesh.Groups[4].Value -gt 0 -and
        $latestPlayerMesh.Groups[4].Value -eq $latestPlayerMesh.Groups[5].Value -and
        $latestPlayerMesh.Groups[4].Value -eq $latestPlayerMesh.Groups[6].Value -and
        $latestPlayerMesh.Groups[8].Value -ne 'None' -and $latestPlayerMesh.Groups[9].Value -eq '0')
    $presents = [regex]::Matches($text, '(?m)^\[([0-9.]+)\].*\[JUDGPROTO\] d3d9-present frames=(\d+) width=(\d+) height=(\d+)')
    $latestPresentSeconds = if ($presents.Count) { [double]::Parse($presents[$presents.Count - 1].Groups[1].Value, [Globalization.CultureInfo]::InvariantCulture) } else { 0 }
    $presentPass = $Renderer -eq 'NullRHI' -or -not $PrototypeTrace -or ($presents.Count -ge 2 -and $latestPresentSeconds -ge ($BootSeconds - 15))
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
        $result = if ($timedOut -and $possessed -and -not $critical -and $mismatches -eq 0 -and $tickPass -and $playerMeshPass -and $presentPass) { 'PASS' } else { 'FAIL' }
    } else {
        $meshPass = $leaves.Count -ge 1402 -and $mismatches -eq 0 -and $meshLoads -eq 3 -and $basePackedLoads -eq 4 -and $possessed
        foreach ($package in $streamedLoads.Keys) { $meshPass = $meshPass -and $streamedLoads[$package] -gt 0 }
        $result = if (-not $meshPass) { 'FAIL' } elseif ($critical -or -not $tickPass -or -not $playerMeshPass -or -not $presentPass) { 'BLOCKED_AFTER_BOOT' } elseif ($timedOut) { 'PASS' } else { 'FAIL' }
    }
    $campaignPassed = $null
    $campaignReport = $null
    if ($CampaignStartup -and $definition.Name -eq 'sp_e2_p') {
        $campaignReport = $log + '.campaign.json'
        $auditOutput = & python (Join-Path $PSScriptRoot 'validate_campaign_fixture.py') $log $campaignReport --quiet 2>&1
        $campaignPassed = $LASTEXITCODE -eq 0
        $auditOutput | ForEach-Object { Write-Host $_ }
        if (-not $campaignPassed -and $result -eq 'PASS') { $result = 'BLOCKED_AFTER_BOOT' }
    }
    $row = [pscustomobject]@{
        Case = $definition.Name; Result = $result; ExactLoads = $leaves.Count - $mismatches
        SizeMismatches = $mismatches; MeshLoads = $meshLoads; PackedLoads = $packedLoads
        BasePackedLoads = $basePackedLoads; CompletedTickReports = $completedTicks.Count
        LatestCompletedTickSeconds = $latestCompletedTickSeconds; PrototypeTrace = [bool]$PrototypeTrace
        Possessed = $possessed; TimedOut = $timedOut; ExitCode = $process.ExitCode
        Critical = $critical; Log = $log
        StreamingLoads = $streamedLoads
        Renderer = $Renderer; RequirePlayerMesh = [bool]$RequirePlayerMesh; PlayerMeshPass = [bool]$playerMeshPass
        PlayerMesh = if ($latestPlayerMesh) { $latestPlayerMesh.Groups[2].Value } else { $null }
        PlayerBones = if ($latestPlayerMesh) { [int]$latestPlayerMesh.Groups[4].Value } else { 0 }
        PresentedFrames = if ($presents.Count) { [int]$presents[$presents.Count - 1].Groups[2].Value } else { 0 }
        LatestPresentSeconds = $latestPresentSeconds; PresentPass = [bool]$presentPass
        CampaignStartup = [bool]$CampaignStartup; CampaignStartupPass = $campaignPassed
        CampaignReport = $campaignReport
    }
    $row | ConvertTo-Json -Compress | Write-Host
    $row
}
$summaryPath = Join-Path $workspace "GearGame\Logs\regress-$Tag-results.json"
$results | ConvertTo-Json | Set-Content -LiteralPath $summaryPath -Encoding UTF8
if ($results.Result -contains 'FAIL') { exit 1 }
if ($results.Result -contains 'BLOCKED_AFTER_BOOT') { exit 2 }
