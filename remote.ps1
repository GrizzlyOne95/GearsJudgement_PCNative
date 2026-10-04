# Drive a running Judgment loader started with -JUDGREMOTE=<CommandFile> (ws31+):
# send command lines, wait, then capture the game window. No desktop focus needed.
#   ./remote.ps1 -Lines 'hold W 2','axis MouseX 600 0.5' -WaitMs 2500 -Shot walk1
# Lines: key <Key> down|up | hold <Key> <seconds> | axis <Key> <rate> <seconds> | any console command.
param(
    [string[]]$Lines = @(),
    [int]$WaitMs = 0,
    [string]$Shot = '',
    [double]$Scale = 0.5,
    [string]$CommandFile = 'C:\Games\_judgment-scratch\remote\cmd.txt',
    [string]$OutDir = 'C:\Games\_judgment-scratch\captures'
)
$ErrorActionPreference = 'Stop'
$p = Get-Process | Where-Object { $_.ProcessName -like 'GearGame-JudgmentLoader*' } | Select-Object -First 1
if (-not $p) { throw 'No Judgment loader is running.' }
if ($Lines.Count) {
    New-Item -ItemType Directory -Force -Path (Split-Path $CommandFile) | Out-Null
    $deadline = [DateTime]::Now.AddSeconds(5)
    while ((Test-Path -LiteralPath $CommandFile) -and [DateTime]::Now -lt $deadline) { Start-Sleep -Milliseconds 50 }
    if (Test-Path -LiteralPath $CommandFile) { throw 'Previous command file was not consumed (loader not started with -JUDGREMOTE?).' }
    # Write beside the target and rename, so the loader never reads a half-written file.
    $tmp = "$CommandFile.tmp"
    Set-Content -LiteralPath $tmp -Value $Lines -Encoding Ascii
    Move-Item -LiteralPath $tmp -Destination $CommandFile
}
if ($WaitMs -gt 0) { Start-Sleep -Milliseconds $WaitMs }
if ($Shot) {
    if ($Shot -notmatch '^[A-Za-z0-9._-]+$') { throw 'Invalid shot name.' }
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
    $out = Join-Path $OutDir "$Shot.png"
    & (Join-Path $PSScriptRoot 'capture_window.ps1') -ProcessId $p.Id -Out $out -Scale $Scale
}
