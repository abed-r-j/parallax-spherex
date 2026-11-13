# Exports ParallaX_ZENITH_LABS.pptx to PDF and to one PNG per slide (slides\slide-N.png, 1920x1080)
# through PowerPoint COM automation, and prints the slide count.
#   powershell -ExecutionPolicy Bypass -File export_deck.ps1
# Only the PowerPoint instance started here is closed, and only if no other presentation is open in it.
# SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$pptx = Join-Path $here 'ParallaX_ZENITH_LABS.pptx'
$pdf = Join-Path $here 'ParallaX_ZENITH_LABS.pdf'
$png = Join-Path $here 'slides'
New-Item -ItemType Directory -Force $png | Out-Null
$wasRunning = @(Get-Process POWERPNT -ErrorAction SilentlyContinue).Count -gt 0
$app = New-Object -ComObject PowerPoint.Application
try {
  $pres = $app.Presentations.Open($pptx, $true, $false, $false)   # read-only, no window
  $n = $pres.Slides.Count
  $pres.SaveAs($pdf, 32)                                           # ppSaveAsPDF
  foreach ($s in $pres.Slides) { $s.Export((Join-Path $png ("slide-{0}.png" -f $s.SlideIndex)), 'PNG', 1920, 1080) }
  $notes = 0
  foreach ($s in $pres.Slides) { if ($s.NotesPage.Shapes.Placeholders.Item(2).TextFrame.TextRange.Text.Length -gt 20) { $notes++ } }
  $pres.Close()
  Write-Output "slides: $n (limit 7); slides with speaker notes: $notes; PDF: $pdf; PNG: $png"
} finally {
  if (-not $wasRunning -and $app.Presentations.Count -eq 0) { $app.Quit() }
  [void][Runtime.InteropServices.Marshal]::ReleaseComObject($app)
}
