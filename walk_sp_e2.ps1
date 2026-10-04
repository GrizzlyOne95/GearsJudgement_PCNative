# Drive a running -JUDGREMOTE loader through SP_E2 (Aftermath, Hanover) in the order the level
# scripts expect, up to the co-op door: first door button, the four trigger volumes of the office
# floor, every Former wave dead ("FormersAllDead" enables the door), then stand at the door handle.
# Teleporting out of order leaves the squad on an earlier GameplayRoute node and the lights off
# (the flicker Matinee starts in TriggerVolume_1), so tests of anything past the first door should
# start from here.
#   ./run_visible.ps1 -Tag <t> -Exe <loader> -KeepRunning -ExtraArgs '-JUDGREMOTE=C:\Games\_judgment-scratch\remote\cmd.txt'
#   ./walk_sp_e2.ps1                 # waits for the map, walks, returns when the door is enabled
# Trigger volume centres are the brush bounds (getall BrushComponent Bounds), not the actor pivots.
param(
    [int]$BootSeconds = 60,
    [int]$WaveTimeoutSeconds = 240,
    [switch]$NoGodMode
)
$ErrorActionPreference = 'Stop'
$remote = Join-Path $PSScriptRoot 'remote.ps1'
$log = Get-ChildItem 'C:\Games\Gears 3 Files\Judgment Port Workspace\GearGame\Logs' -Filter 'interactive-*.log' |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName

function Send([string[]]$Lines, [int]$WaitMs = 1000) { & $remote -Lines $Lines -WaitMs $WaitMs | Out-Null }

# getall output for one query, read back from the log.
function Query([string]$Command) {
    $before = (Get-Content -LiteralPath $log).Count
    Send @($Command) 900
    Get-Content -LiteralPath $log | Select-Object -Skip $before | Where-Object { $_ -match '\] Log: \d+\) ' }
}

function Wait-FormersDead([string]$Stage) {
    $deadline = [DateTime]::Now.AddSeconds($WaveTimeoutSeconds)
    while ([DateTime]::Now -lt $deadline) {
        $alive = @(Query 'getall GearPawn_LambentHuman Health').Count
        if ($alive -eq 0) { "${Stage}: all Formers dead"; return }
        Start-Sleep -Seconds 5
    }
    "${Stage}: $alive Former(s) still alive after $WaveTimeoutSeconds s (stuck behind a wall? teleport next to one and hold B)"
}

Start-Sleep -Seconds $BootSeconds
if (-not $NoGodMode) { Send 'set GearPC bGodMode true', 'set GearPawn_COGBairdJack bUnlimitedHealth true' }

# First door: button at locator 0. Completes objective 1a and streams SP_E2_03_S and the co-op door level.
Send 'teleport 3529 2463 290' 1500
Send 'ButtonPress X' 300
Send 'ButtonRelease X' 8000

# Office floor, south to north, then the big room. Each stop lets the squad's route index catch up.
Send 'teleport 5632 2880 228' 9000      # TriggerVolume_1: flickering lights Matinee, 2 Formers
Send 'teleport 5553 3520 228' 8000      # TriggerVolume_2: objective 1b, three Former groups (its centre 5632,3600 is blocked)
Send 'teleport 5632 4352 228' 8000      # TriggerVolume_4
Send 'teleport 6375 5910 380' 12000     # TriggerVolume_0: the main fight (its centre 6304,5656 is blocked: moved=0)
Send 'teleport 3712 5120 228' 10000     # TriggerVolume_3: last two waves
# Stand with the squad at the end of the route so the waves come to them.
Send 'teleport 2900 5290 228' 5000
Wait-FormersDead 'office floor'

$enabled = @(Query 'getall SeqEvt_Engage bEnabled') -match 'True'
"co-op door engage events enabled: $($enabled.Count) of 2"
Send 'teleport 2700 5290 228' 2000
"at the co-op door (Trigger_Engage_23 at 2626,5242; _24 at 2626,5002)"
