# Turns one camera recording (a "take") into the finished video.
#   powershell -ExecutionPolicy Bypass -File assemble.ps1 -Video 30s  -Take takes\take_30s.mp4
#   powershell -ExecutionPolicy Bypass -File assemble.ps1 -Video 2min -Take takes\take_2min.mp4 -Offset 6.2
# Needs base_<video>.mp4 and timeline_<video>.json (made by: node build_video.mjs) and ffmpeg/ffprobe.
# It records nothing: the take is a file you filmed yourself.
# SI disclosure: written with the help of an SI coding assistant (Claude, by Anthropic).
param(
  [Parameter(Mandatory = $true)][ValidateSet('30s', '2min')][string]$Video,
  [string]$Take,
  [Nullable[double]]$Offset = $null,          # seconds into the take where the first line starts; overrides the automatic value
  [ValidateSet('pip', 'split')][string]$Layout = 'pip',
  [string]$Out,
  [ValidateSet('tr', 'tl')][string]$Corner = 'tr',   # corner of the face window (pip layout)
  [double]$CropY = 0.5,                        # 0 = keep the top of a tall (portrait) take, 0.5 = centre, 1 = bottom
  [double]$NoiseDb = -35                       # anything quieter than this counts as silence
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$inv = [Globalization.CultureInfo]::InvariantCulture
function N([double]$v) { return $v.ToString('0.###', $inv) }
function Fail([string]$msg) { Write-Host "FAILED: $msg" -ForegroundColor Red; exit 1 }

if (-not $Take) { $Take = Join-Path $here "takes\take_$Video.mp4" }
if (-not $Out) { $Out = Join-Path $here "final_$Video.mp4" }
$base = Join-Path $here "base_$Video.mp4"
$tlFile = Join-Path $here "timeline_$Video.json"
if (-not (Test-Path -LiteralPath $Take)) { Fail "take not found: $Take" }
if (-not (Test-Path -LiteralPath $base) -or -not (Test-Path -LiteralPath $tlFile)) { Fail "base_$Video.mp4 or timeline_$Video.json is missing: run  node build_video.mjs" }
$Take = (Resolve-Path -LiteralPath $Take).Path
$Out = [IO.Path]::GetFullPath((Join-Path (Get-Location).Path $Out))
$tl = Get-Content -LiteralPath $tlFile -Raw | ConvertFrom-Json
$end = [double]$tl.end

$streams = & ffprobe -v error -show_entries stream=codec_type -of csv=p=0 $Take
if (-not ($streams -match 'audio')) { Fail "the take has no sound track: $Take" }
if (-not ($streams -match 'video')) { Fail "the take has no picture: $Take" }
$takeDur = [double]::Parse((& ffprobe -v error -show_entries format=duration -of csv=p=0 $Take), $inv)

$tmp = Join-Path $env:TEMP ("parallax_assemble_" + $PID)
New-Item -ItemType Directory -Force $tmp | Out-Null

# ---- 1. where does the speech start? ----
if ($null -ne $Offset) {
  $t0 = [double]$Offset
  Write-Host ("Offset given by hand: {0} s" -f (N $t0))
}
else {
  Push-Location $tmp
  & ffmpeg -hide_banner -loglevel error -y -i $Take -vn -af ("highpass=f=120,silencedetect=n=" + (N $NoiseDb) + "dB:d=0.25,ametadata=mode=print:file=sil.txt") -f null -
  Pop-Location
  if ($LASTEXITCODE -ne 0) { Fail 'ffmpeg could not read the sound of the take' }
  $starts = @(); $ends = @()
  foreach ($line in (Get-Content (Join-Path $tmp 'sil.txt'))) {
    if ($line -match 'silence_start=([-\d.]+)') { $starts += [Math]::Max([double]0, [double]::Parse($Matches[1], $inv)) }
    elseif ($line -match 'silence_end=([-\d.]+)') { $ends += [double]::Parse($Matches[1], $inv) }
  }
  # sound = everything between the silences
  $sound = @()
  $cursor = 0.0
  for ($i = 0; $i -lt $starts.Count; $i++) {
    if ($starts[$i] - $cursor -gt 0.03) { $sound += , @($cursor, $starts[$i]) }
    if ($i -lt $ends.Count) { $cursor = $ends[$i] } else { $cursor = $takeDur }
  }
  if ($takeDur - $cursor -gt 0.03) { $sound += , @($cursor, $takeDur) }
  # a) the teleprompter countdown, if the microphone heard it: short beeps one second apart
  $short = @($sound | Where-Object { ($_[1] - $_[0]) -le 0.45 })
  $run = 1; $lastBeep = $null
  for ($i = 1; $i -lt $short.Count; $i++) {
    if ([Math]::Abs(($short[$i][0] - $short[$i - 1][0]) - 1.0) -le 0.15) { $run++; if ($run -ge 3) { $lastBeep = $short[$i][0] } }
    elseif ($null -ne $lastBeep) { break } else { $run = 1 }
  }
  $speech = $sound | Where-Object { ($_[1] - $_[0]) -ge 0.5 } | Select-Object -First 1
  if ($null -ne $lastBeep) {
    $t0 = $lastBeep + 1.5 - [double]$tl.firstCue
    Write-Host ("Countdown beeps heard in the take; the last short beep is at {0} s, so the first line starts at {1} s" -f (N $lastBeep), (N ($lastBeep + 1.5)))
  }
  elseif ($null -ne $speech) {
    $t0 = $speech[0] - [double]$tl.firstCue
    Write-Host ("Speech starts {0} s into the take (first sound longer than half a second)" -f (N $speech[0]))
  }
  else { Fail "no speech found in the take (is it silent?). Give the start by hand with -Offset seconds" }
}
Write-Host ("OFFSET USED: {0} s  (re-run with -Offset {1} to change it; a bigger number makes the voice come earlier)" -f (N $t0), (N ($t0 + 0.3))) -ForegroundColor Cyan
if ($takeDur - $t0 -lt $end - 0.5) { Write-Host ("WARNING: the take ends {0} s before the script does; the last picture is held and the sound is silent there" -f (N ($end - ($takeDur - $t0)))) -ForegroundColor Yellow }

# ---- 2. compose ----
if ($t0 -ge 0) { $vtrim = "trim=start=$(N $t0),setpts=PTS-STARTPTS,"; $atrim = "atrim=start=$(N $t0),asetpts=PTS-STARTPTS," }
else { $vtrim = "tpad=start_mode=clone:start_duration=$(N (-$t0)),"; $atrim = "adelay=$([int](-$t0 * 1000)):all=1," }
function En($list) { return (($list | ForEach-Object { "gte(t,$(N $_[0]))*lt(t,$(N $_[1]))" }) -join '+') }
$enCam = En $tl.camFull
$enLt = En $tl.lowerThirds
$s = $tl.sub; $l = $tl.lt
if ($Corner -eq 'tr') { $pipX = 1920 - 422 - 96 } else { $pipX = 96 }
$g = @()
$g += "[1:v]${vtrim}fps=30,scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080:(iw-1920)/2:(ih-1080)*$(N $CropY),setsar=1,tpad=stop_mode=clone:stop_duration=$(N $end),trim=duration=$(N $end),setpts=PTS-STARTPTS,format=yuv420p,split=2[camf][camp]"
$g += "[0:v]split=3[b0][b1][b2]"
if ($Layout -eq 'pip') {
  $g += "[camp]scale=414:232,pad=422:240:4:4:color=0xebe7dc[pip]"
  $g += "[b0][pip]overlay=x=${pipX}:y=54[s1]"
}
else {
  $g += "[camp]crop=822:1080,scale=576:756[col]"
  $g += "[b0]scale=1344:756[bs]"
  $g += "color=c=0x10161f:s=1920x1080:r=30:d=$(N $end)[bgc]"
  $g += "[bgc][bs]overlay=x=0:y=162[x1]"
  $g += "[x1][col]overlay=x=1344:y=162[s1]"
}
$g += "[s1][camf]overlay=x=0:y=0:enable='$enCam'[s2]"
$g += "[b1]crop=$($s.w):$($s.h):$($s.x):$($s.y),format=yuva420p,colorchannelmixer=aa=0.88[subs]"
$g += "[s2][subs]overlay=x=$($s.x):y=$($s.y):enable='$enCam'[s3]"
$g += "[b2]crop=$($l.w):$($l.h):$($l.x):$($l.y),format=yuva420p,colorchannelmixer=aa=0.92[lts]"
$g += "[s3][lts]overlay=x=$($l.x):y=$($l.y):enable='$enLt',format=yuv420p[vout]"
$g += "[1:a]${atrim}highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,afade=t=in:st=0:d=0.3,afade=t=out:st=$(N ($end - 0.3)):d=0.3,apad,atrim=duration=$(N $end),aformat=channel_layouts=stereo[aout]"
$graph = Join-Path $tmp 'graph.txt'
[IO.File]::WriteAllText($graph, ($g -join ";`n"), (New-Object Text.UTF8Encoding($false)))

Write-Host "Composing $Out ($Layout layout) ..."
& ffmpeg -hide_banner -loglevel error -y -i $base -i $Take -/filter_complex $graph -map '[vout]' -map '[aout]' `
  -c:v libx264 -profile:v high -preset medium -crf 20 -pix_fmt yuv420p -r 30 -c:a aac -b:a 160k -t (N $end) -movflags +faststart -map_metadata -1 -metadata "title=ParallaX - $Video video (team ZENITH LABS)" $Out
if ($LASTEXITCODE -ne 0) { Fail 'ffmpeg could not compose the video' }

# ---- 3. check ----
$dur = [double]::Parse((& ffprobe -v error -show_entries format=duration -of csv=p=0 $Out), $inv)
$res = & ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate,codec_name,profile,pix_fmt -of csv=p=0 $Out
$size = (Get-Item -LiteralPath $Out).Length
$sheet = [IO.Path]::ChangeExtension($Out, $null).TrimEnd('.') + '_contact.jpg'
$sel = ((0..5) | ForEach-Object { "eq(n,$([int][Math]::Round(($_ + 0.5) * $dur / 6 * 30)))" }) -join '+'
& ffmpeg -hide_banner -loglevel error -y -i $Out -vf "select='$sel',scale=640:-1,tile=3x2" -fps_mode vfr -frames:v 1 $sheet
Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue

Write-Host ("Duration   : {0} s   (limit {1} s)" -f $dur.ToString('0.000', $inv), (N ([double]$tl.hardLimit)))
Write-Host "Video      : $res"
Write-Host ("Size       : {0:N1} MB" -f ($size / 1MB))
Write-Host "Contact    : $sheet"
if ($dur -gt [double]$tl.hardLimit) {
  Write-Host ("TOO LONG: {0} s is over the limit of {1} s. DO NOT SUBMIT THIS FILE." -f $dur.ToString('0.000', $inv), (N ([double]$tl.hardLimit))) -ForegroundColor Red
  exit 2
}
Write-Host "OK: $Out" -ForegroundColor Green
exit 0
