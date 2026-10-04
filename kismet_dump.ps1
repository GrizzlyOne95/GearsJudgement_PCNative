# Ask a running -JUDGREMOTE loader for the console dumps kismet_graph.py reads. They land in the
# loader's log; pass that log to kismet_graph.py afterwards.
#   ./kismet_dump.ps1
#   python kismet_graph.py <log> events
param(
    [string[]]$ActorClasses = @('TriggerVolume', 'Trigger', 'Trigger_ButtonInteraction', 'Trigger_DoorInteraction', 'Trigger_Engage')
)
$ErrorActionPreference = 'Stop'
$remote = Join-Path $PSScriptRoot 'remote.ps1'
$lines = @(
    'getall SeqVar_Object ObjValue', 'getall SequenceOp VariableLinks', 'getall SequenceOp OutputLinks',
    'getall SequenceOp EventLinks', 'getall SequenceOp ActivateCount', 'getall SequenceObject ObjComment',
    'getall SequenceEvent Originator', 'getall SequenceEvent TriggerCount', 'getall SequenceEvent MaxTriggerCount',
    'getall SequenceEvent bEnabled', 'getall SeqEvent_RemoteEvent EventName', 'getall SeqAct_ActivateRemoteEvent EventName'
) + ($ActorClasses | ForEach-Object { "getall $_ Location" }) + @('getall BrushComponent Bounds')
# Two batches: one long command file can outrun the console in a single frame.
$half = [int][Math]::Ceiling($lines.Count / 2)
& $remote -Lines $lines[0..($half - 1)] -WaitMs 4000 | Out-Null
& $remote -Lines $lines[$half..($lines.Count - 1)] -WaitMs 4000 | Out-Null
$log = Get-ChildItem 'C:\Games\Gears 3 Files\Judgment Port Workspace\GearGame\Logs' -Filter 'interactive-*.log' |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
"dumped to $log"
