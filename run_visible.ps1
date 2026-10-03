# Visible-window Judgment loader run: optional startup console commands, window capture(s), then stop.
# Writes only into the Judgment workspace Logs dir, _judgment-scratch\exec and the given output folder.
param(
    [Parameter(Mandatory)][string]$Tag,
    [string[]]$ExecLines = @(),
    [int[]]$CaptureAt = @(55),
    [string]$Exe = 'GearGame-JudgmentLoader-ws24-resident-textures.exe',
    [string]$ExtraArgs = '',
    [double]$Scale = 0.6,
    [string]$OutDir = 'C:\Games\_judgment-scratch\captures'
)
$ErrorActionPreference = 'Stop'
$ws  = 'C:\Games\Gears 3 Files\Judgment Port Workspace'
$bin = Join-Path $ws 'Binaries\Win32'
$exePath = Join-Path $bin $Exe
if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) { throw "Missing loader: $exePath" }
if ($Tag -notmatch '^[A-Za-z0-9._-]+$') { throw 'Invalid tag.' }
$log = Join-Path $ws "GearGame\Logs\interactive-$Tag-sp_e2_p.log"
if (Test-Path -LiteralPath $log) { throw "Refusing to overwrite existing log: $log" }
$a = 'Judgment_SP_E2_P?game=geargamecontent.GearGameAID?listen -user -NOHOMEDIR -JUDGMENTPKGVER=845 -forcelogflush -unattended -nopause -nosound -NoTextureStreaming -d3d9 -windowed -ResX=1280 -ResY=720 -JUDGWINDOWRESOLUTION -JUDGPROTOTRACE -JUDGSEQUENCETRACE -JUDGAIACCESSORS -JUDGAIDIRECTORINIT -JUDGFSMCORE -JUDGFSMSELFTEST -JUDGMENTSTREAMINGPACKAGES=SP_E2_01,SP_E2_02,SP_E2_W,SP_E2_01_S,SP_E2_Audio,SP_E2_02_S,COG_Baird_Jack -JUDGNATIVEBINDOK -JUDGLIFE -JUDGPRELOADTRACE'
if ($ExecLines.Count) {
    # ULocalPlayer::ExecMacro resolves bare names to ..\..\Binaries\<name> (workspace Binaries).
    $execName = "judgexec-$Tag.txt"
    Set-Content -LiteralPath (Join-Path $ws "Binaries\$execName") -Value $ExecLines -Encoding Ascii
    $a += " -EXEC=$execName"
}
if ($ExtraArgs) { $a += " $ExtraArgs" }
$a += " -ABSLOG=`"$log`""
$p = Start-Process -FilePath $exePath -ArgumentList $a -WorkingDirectory $bin -PassThru
"launched pid=$($p.Id) tag=$Tag"
$timer = [Diagnostics.Stopwatch]::StartNew()
$shots = @()
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
try {
    foreach ($t in ($CaptureAt | Sort-Object)) {
        $wait = $t * 1000 - $timer.ElapsedMilliseconds
        if ($wait -gt 0 -and $p.WaitForExit([int]$wait)) { "process exited early, code=$($p.ExitCode)"; break }
        $out = Join-Path $OutDir "$Tag-t$t.png"
        & (Join-Path $PSScriptRoot 'capture_window.ps1') -ProcessId $p.Id -Out $out -Scale $Scale
        $shots += $out
    }
} finally {
    if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force; $p.WaitForExit() }
}
if (Test-Path -LiteralPath $log) {
    $text = [IO.File]::ReadAllText($log)
    $presents = [regex]::Matches($text, 'd3d9-present frames=(\d+)')
    'presents={0} critical={1}' -f $(if ($presents.Count) { $presents[$presents.Count-1].Groups[1].Value } else { 0 }), ([regex]::Matches($text, 'Critical: appError').Count)
}
"log=$log"
