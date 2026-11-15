# Builds final_2min.mp4 from a take that was cut by hand, so that it no longer follows the
# teleprompter clock. Instead of sliding the take, this stretches each script line of the
# prepared picture (base_2min.mp4) to the moment that line is actually spoken in the take.
#   powershell -ExecutionPolicy Bypass -File retime_2min.ps1
# $spoken = second in the take at which each script line of timeline_2min.json starts
# (found from the pauses in the sound, checked line by line with a speech recogniser).
# SI disclosure: written with the help of an SI coding assistant (Claude, by Anthropic).
param(
  [string]$Take = 'takes\take_2min.mp4',
  [string]$Out = 'final_2min.mp4',
  [double[]]$Spoken = @(0, 4.23, 10.17, 16.87, 27.58, 32.41, 39.57, 52.19, 57.94, 69.39, 75.42, 87.26, 100.73, 109.58),
  [double]$SpeechEnd = 111.17,   # last word ends here in the take
  [double]$Lead = 0.4,           # still picture and silence added before the first word
  [double]$Tail = 1.3,           # kept after the last word
  [double]$SubsFrom = 10.17      # captions over the camera start here (the two greeting lines were not checked word for word)
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here
$inv = [Globalization.CultureInfo]::InvariantCulture
function N([double]$v) { return $v.ToString('0.###', $inv) }
$tl = Get-Content timeline_2min.json -Raw | ConvertFrom-Json
$a = @($tl.lines | ForEach-Object { [double]$_.a }) + @([double]$tl.end)          # script clock
$o = @(0.0) + @($Spoken[1..($Spoken.Count - 1)] | ForEach-Object { $_ + $Lead }) + @($SpeechEnd + $Lead + $Tail)   # output clock
if ($a.Count -ne $o.Count) { throw "need one spoken time per script line ($($a.Count - 1))" }
$end = $o[-1]
function Map([double]$t) { for ($i = 0; $i -lt $a.Count - 1; $i++) { if ($t -le $a[$i + 1]) { return $o[$i] + ($t - $a[$i]) * ($o[$i + 1] - $o[$i]) / ($a[$i + 1] - $a[$i]) } }; return $end }

$n = $a.Count - 1
$g = @()
$g += "[0:v]split=$n" + ((0..($n - 1) | ForEach-Object { "[i$_]" }) -join '')
for ($i = 0; $i -lt $n; $i++) {
  $f = ($o[$i + 1] - $o[$i]) / ($a[$i + 1] - $a[$i])
  $g += "[i$i]trim=start=$(N $a[$i]):end=$(N $a[$i + 1]),setpts=(PTS-STARTPTS)*$($f.ToString('0.######', $inv))[r$i]"
}
$g += ((0..($n - 1) | ForEach-Object { "[r$_]" }) -join '') + "concat=n=${n}:v=1:a=0,fps=30,tpad=stop_mode=clone:stop_duration=2,trim=duration=$(N $end),setpts=PTS-STARTPTS,split=3[b0][b1][b2]"
$camA = $o[3]; $camB = $o[11]                       # camera fills the frame before $camA and from $camB
$enCam = "lt(t,$(N $camA))+gte(t,$(N $camB))"
$enSub = "gte(t,$(N ($SubsFrom + $Lead)))*lt(t,$(N $camA))+gte(t,$(N $camB))"
$enLt = "lt(t,$(N (Map 6)))+gte(t,$(N (Map 109)))"
$s = $tl.sub; $l = $tl.lt
$g += "[1:v]fps=30,scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,tpad=start_mode=clone:start_duration=$(N $Lead),trim=duration=$(N $end),setpts=PTS-STARTPTS,format=yuv420p,split=2[camf][camp]"
$g += "[camp]scale=414:232,pad=422:240:4:4:color=0xebe7dc[pip]"
$g += "[b0][pip]overlay=x=$(1920 - 422 - 96):y=54[s1]"
$g += "[s1][camf]overlay=x=0:y=0:enable='$enCam'[s2]"
$g += "[b1]crop=$($s.w):$($s.h):$($s.x):$($s.y),format=yuva420p,colorchannelmixer=aa=0.88[subs]"
$g += "[s2][subs]overlay=x=$($s.x):y=$($s.y):enable='$enSub'[s3]"
$g += "[b2]crop=$($l.w):$($l.h):$($l.x):$($l.y),format=yuva420p,colorchannelmixer=aa=0.92[lts]"
$g += "[s3][lts]overlay=x=$($l.x):y=$($l.y):enable='$enLt',format=yuv420p[vout]"
$g += "[1:a]adelay=$([int]($Lead * 1000)):all=1,highpass=f=80,afftdn=nr=6,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,afade=t=out:st=$(N ($end - 0.4)):d=0.4,apad,atrim=duration=$(N $end),aformat=channel_layouts=stereo[aout]"
$graph = Join-Path $env:TEMP "parallax_retime_$PID.txt"
[IO.File]::WriteAllText($graph, ($g -join ";`n"), (New-Object Text.UTF8Encoding($false)))
& ffmpeg -hide_banner -loglevel error -y -i base_2min.mp4 -i $Take -/filter_complex $graph -map '[vout]' -map '[aout]' `
  -c:v libx264 -profile:v high -preset medium -crf 21 -pix_fmt yuv420p -r 30 -c:a aac -b:a 160k -t (N $end) -movflags +faststart $Out
$code = $LASTEXITCODE
Remove-Item $graph -ErrorAction SilentlyContinue
if ($code -ne 0) { Write-Host 'FAILED: ffmpeg could not compose the video' -ForegroundColor Red; exit 1 }
$dur = [double]::Parse((& ffprobe -v error -show_entries format=duration -of csv=p=0 $Out), $inv)
Write-Host ("Duration {0} s (limit {1} s), {2:N1} MB" -f $dur.ToString('0.000', $inv), $tl.hardLimit, ((Get-Item $Out).Length / 1MB))
Write-Host ("Line starts in the finished video: " + (($o[0..($n - 1)] | ForEach-Object { N $_ }) -join ', '))
if ($dur -gt [double]$tl.hardLimit) { Write-Host 'TOO LONG. DO NOT SUBMIT THIS FILE.' -ForegroundColor Red; exit 2 }
