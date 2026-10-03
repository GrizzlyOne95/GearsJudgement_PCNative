# Captures only the given process's main window (not the screen) to a PNG.
param([Parameter(Mandatory)][int]$ProcessId, [Parameter(Mandatory)][string]$Out, [double]$Scale = 0.75)
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System; using System.Runtime.InteropServices;
public class CapWin {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
}
'@
$p = Get-Process -Id $ProcessId -ErrorAction Stop
$h = $p.MainWindowHandle
if ($h -eq [IntPtr]::Zero) { throw 'no main window' }
$r = New-Object CapWin+RECT
[void][CapWin]::GetClientRect($h, [ref]$r)
$w = $r.R - $r.L; $ht = $r.B - $r.T
$bmp = New-Object System.Drawing.Bitmap $w, $ht
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
# 1 = client only, 2 = render full content (needed for D3D windows under DWM)
$ok = [CapWin]::PrintWindow($h, $hdc, 3)
$g.ReleaseHdc($hdc); $g.Dispose()
if ($Scale -ne 1) {
  $sw = [int]($w * $Scale); $sh = [int]($ht * $Scale)
  $small = New-Object System.Drawing.Bitmap $sw, $sh
  $g2 = [System.Drawing.Graphics]::FromImage($small)
  $g2.InterpolationMode = 'HighQualityBicubic'
  $g2.DrawImage($bmp, 0, 0, $sw, $sh); $g2.Dispose(); $bmp.Dispose(); $bmp = $small
}
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
"printwindow=$ok client=${w}x${ht} -> $Out"
