# Makes clearly labelled PLACEHOLDER takes for testing assemble.ps1. They are not recordings of anyone:
# a plain colour card, 2.5 s of silence, then tone bursts standing in for speech.
#   powershell -ExecutionPolicy Bypass -File make_placeholders.ps1
# SI disclosure: written with the help of an SI coding assistant (Claude, by Anthropic).
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$dir = Join-Path $here 'placeholders'
New-Item -ItemType Directory -Force $dir | Out-Null
Push-Location $dir
$font = "fontfile='C\:/Windows/Fonts/segoeuib.ttf'"
# bursts of 0.6 s with gaps of 0.15 s, starting at 2.5 s
$aud = "sine=frequency=330:sample_rate=48000:duration=125,volume='0.4*gte(t,2.5)*lt(mod(t-2.5,0.75),0.6)':eval=frame"
foreach ($p in @(@('landscape', '1280x720', 52, '0x1f4d3a'), @('portrait', '1080x1920', 46, '0x4d1f3a'))) {
  $vf = "drawtext=${font}:text='PLACEHOLDER TAKE':fontsize=$($p[2] * 1.6):fontcolor=white:x=(w-text_w)/2:y=h*0.36," +
  "drawtext=${font}:text='replace with your own recording':fontsize=$($p[2]):fontcolor=white:x=(w-text_w)/2:y=h*0.36+$($p[2] * 2.4)," +
  "drawtext=${font}:text='%{pts\:hms}':fontsize=$($p[2]):fontcolor=yellow:x=(w-text_w)/2:y=h*0.36+$($p[2] * 4.4)"
  & ffmpeg -hide_banner -loglevel error -y -f lavfi -i "color=c=$($p[3]):s=$($p[1]):r=30:d=125" -f lavfi -i $aud -vf $vf `
    -c:v libx264 -preset veryfast -crf 28 -pix_fmt yuv420p -c:a aac -b:a 96k -shortest "placeholder_take_$($p[0]).mp4"
  if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Host 'FAILED' -ForegroundColor Red; exit 1 }
}
Pop-Location
Get-ChildItem $dir | Select-Object Name, Length
