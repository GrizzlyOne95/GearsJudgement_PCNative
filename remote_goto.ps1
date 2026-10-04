# Walk the player of a running -JUDGREMOTE loader toward a world position: read position and
# facing from the log (getall), turn with the mouse axis, hold W, repeat. Straight-line only;
# reports "stuck" when a step makes no progress and sidesteps once.
#   ./remote_goto.ps1 -X 2563 -Y 5049 -Steps 6 -Shot goto1
param(
    [Parameter(Mandatory)][double]$X,
    [Parameter(Mandatory)][double]$Y,
    [int]$Steps = 5,
    [double]$StepSeconds = 3,
    [double]$Arrive = 250,
    [string]$Shot = '',
    [double]$Scale = 0.5,
    [string]$PawnClass = 'GearPawn_COGBairdJack',
    # Controller yaw units per mouse count, measured on ws31 (axis MouseX 400 -> 19464 units).
    [double]$YawPerCount = 48.66
)
$ErrorActionPreference = 'Stop'
$remote = Join-Path $PSScriptRoot 'remote.ps1'
$log = Get-ChildItem 'C:\Games\Gears 3 Files\Judgment Port Workspace\GearGame\Logs' -Filter 'interactive-*.log' |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
function Read-State {
    & $remote -Lines 'getall GearPC Rotation', "getall $PawnClass Location" -WaitMs 450 | Out-Null
    $tail = Get-Content -LiteralPath $log -Tail 4000
    $rot = $tail | Select-String -Pattern 'GearPC\w*_\d+\.Rotation = \(Pitch=(-?\d+),Yaw=(-?\d+)' | Select-Object -Last 1
    $loc = $tail | Select-String -Pattern "${PawnClass}_\d+\.Location = \(X=(-?[\d.]+),Y=(-?[\d.]+),Z=(-?[\d.]+)" | Select-Object -Last 1
    if (-not $rot -or -not $loc) { throw 'Could not read player state from the log.' }
    [pscustomobject]@{
        Yaw = [double]$rot.Matches[0].Groups[2].Value
        X = [double]$loc.Matches[0].Groups[1].Value
        Y = [double]$loc.Matches[0].Groups[2].Value
        Z = [double]$loc.Matches[0].Groups[3].Value
    }
}
$side = 'A'
$s = Read-State
for ($i = 0; $i -lt $Steps; $i++) {
    $dx = $X - $s.X; $dy = $Y - $s.Y
    $dist = [Math]::Sqrt($dx * $dx + $dy * $dy)
    if ($dist -lt $Arrive) { break }
    $delta = [Math]::Atan2($dy, $dx) * 32768 / [Math]::PI - $s.Yaw
    $delta = (($delta + 32768) % 65536 + 65536) % 65536 - 32768
    $counts = [Math]::Round($delta / $YawPerCount, 1)
    $walk = [Math]::Min($StepSeconds, [Math]::Max(0.5, $dist / 250))
    # axis takes a rate per second; spread the turn over 0.25 s, then walk.
    $rate = [Math]::Round($counts / 0.25, 1)
    & $remote -Lines "axis MouseX $rate 0.25" -WaitMs 400 | Out-Null
    & $remote -Lines "hold W $walk" -WaitMs ([int]($walk * 1000 + 250)) | Out-Null
    $n = Read-State
    $moved = [Math]::Sqrt(($n.X - $s.X) * ($n.X - $s.X) + ($n.Y - $s.Y) * ($n.Y - $s.Y))
    'step {0}: pos=({1:F0},{2:F0},{3:F0}) dist={4:F0} moved={5:F0}' -f $i, $n.X, $n.Y, $n.Z, $dist, $moved
    if ($moved -lt 60) {
        "stuck: sidestep $side"
        & $remote -Lines "hold $side 1.2", 'hold W 1.2' -WaitMs 1400 | Out-Null
        $side = if ($side -eq 'A') { 'D' } else { 'A' }
        $n = Read-State
    }
    $s = $n
}
'final: pos=({0:F0},{1:F0},{2:F0}) yaw={3:F0}' -f $s.X, $s.Y, $s.Z, $s.Yaw
if ($Shot) { & $remote -Shot $Shot -Scale $Scale }
