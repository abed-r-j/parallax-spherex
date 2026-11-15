# Builds final_30s.mp4 from a take that was cut by hand, so that it no longer follows the
# teleprompter clock. Stretches each script line of the prepared picture (base_30s.mp4) to the
# moment that line is actually spoken in the take (same method as retime_2min.ps1).
#   powershell -ExecutionPolicy Bypass -File retime_30s.ps1
# $Spoken = second in the take at which each script line of timeline_30s.json starts
# (found from the pauses in the sound). The lower-third banner is shown during the opening
# (project, team and member name) and again at the end (link and data credits). The caption
# of the greeting line is left out: its exact spoken words were not checked.
# SI disclosure: written with the help of an SI coding assistant (Claude, by Anthropic).
param(
  [string]$Take = 'takes\take_30s.mp4',
  [string]$Out = 'final_30s.mp4',
  [double[]]$Spoken = @(1.77, 4.04, 8.29, 12.73, 16.60, 21.95, 26.29),
  [double]$SpeechEnd = 28.09,    # last word ends here in the take
  [double]$Skip = 1.47,          # silence cut from the start of the take
  [double]$Tail = 1.0            # kept after the last word
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here
$inv = [Globalization.CultureInfo]::InvariantCulture
function N([double]$v) { return $v.ToString('0.###', $inv) }
$tl = Get-Content timeline_30s.json -Raw | ConvertFrom-Json
$a = @($tl.lines | ForEach-Object { [double]$_.a }) + @([double]$tl.end)          # script clock
$o = @(0.0) + @($Spoken[1..($Spoken.Count - 1)] | ForEach-Object { $_ - $Skip }) + @($SpeechEnd - $Skip + $Tail)   # output clock
if ($a.Count -ne $o.Count) { throw "need one spoken time per script line ($($a.Count - 1))" }
$end = $o[-1]
$n = $a.Count - 1
$g = @()
$g += "[0:v]split=$n" + ((0..($n - 1) | ForEach-Object { "[i$_]" }) -join '')
for ($i = 0; $i -lt $n; $i++) {
  $f = ($o[$i + 1] - $o[$i]) / ($a[$i + 1] - $a[$i])
  $g += "[i$i]trim=start=$(N $a[$i]):end=$(N $a[$i + 1]),setpts=(PTS-STARTPTS)*$($f.ToString('0.######', $inv))[r$i]"
}
$g += ((0..($n - 1) | ForEach-Object { "[r$_]" }) -join '') + "concat=n=${n}:v=1:a=0,fps=30,tpad=stop_mode=clone:stop_duration=2,trim=duration=$(N $end),setpts=PTS-STARTPTS,split=3[b0][b1][b2]"
$camA = $o[1]; $camB = $o[$n - 1]                   # camera fills the frame before $camA and from $camB
$enCam = "lt(t,$(N $camA))+gte(t,$(N $camB))"
$enSub = "gte(t,$(N $camB))"                        # captions over the camera: closing line only
$enLt = "lt(t,$(N $camA))+gte(t,$(N $camB))"        # opening banner (project, team, member) and closing banner (link and data credits)
$s = $tl.sub; $l = $tl.lt
$g += "[1:v]trim=start=$(N $Skip),setpts=PTS-STARTPTS,fps=30,scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,tpad=stop_mode=clone:stop_duration=2,trim=duration=$(N $end),setpts=PTS-STARTPTS,format=yuv420p,split=2[camf][camp]"
$g += "[camp]scale=414:232,pad=422:240:4:4:color=0xebe7dc[pip]"
$g += "[b0][pip]overlay=x=$(1920 - 422 - 96):y=54[s1]"
$g += "[s1][camf]overlay=x=0:y=0:enable='$enCam'[s2]"
$g += "[b1]crop=$($s.w):$($s.h):$($s.x):$($s.y),format=yuva420p,colorchannelmixer=aa=0.88[subs]"
$g += "[s2][subs]overlay=x=$($s.x):y=$($s.y):enable='$enSub'[s3]"
$g += "[b2]crop=$($l.w):$($l.h):$($l.x):$($l.y),format=yuva420p,colorchannelmixer=aa=0.92[lts]"
$g += "[s3][lts]overlay=x=$($l.x):y=$($l.y):enable='$enLt',format=yuv420p[vout]"
$g += "[1:a]atrim=start=$(N $Skip),asetpts=PTS-STARTPTS,highpass=f=80,afftdn=nr=8,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,afade=t=in:d=0.15,afade=t=out:st=$(N ($end - 0.3)):d=0.3,apad,atrim=duration=$(N $end),aformat=channel_layouts=stereo[aout]"
$graph = Join-Path $env:TEMP "parallax_retime30_$PID.txt"
[IO.File]::WriteAllText($graph, ($g -join ";`n"), (New-Object Text.UTF8Encoding($false)))
& ffmpeg -hide_banner -loglevel error -y -i base_30s.mp4 -i $Take -/filter_complex $graph -map '[vout]' -map '[aout]' `
  -c:v libx264 -profile:v high -preset medium -crf 21 -pix_fmt yuv420p -r 30 -c:a aac -b:a 160k -t (N $end) -movflags +faststart `
  -map_metadata -1 -metadata "title=ParallaX - 30-second demo (team ZENITH LABS)" `
  -metadata "comment=SPHEREx data: NASA/IPAC IRSA. Not affiliated with or endorsed by NASA. Made with the help of an SI coding assistant (Claude, Anthropic)." $Out
$code = $LASTEXITCODE
Remove-Item $graph -ErrorAction SilentlyContinue
if ($code -ne 0) { Write-Host 'FAILED: ffmpeg could not compose the video' -ForegroundColor Red; exit 1 }
$dur = [double]::Parse((& ffprobe -v error -show_entries format=duration -of csv=p=0 $Out), $inv)
Write-Host ("Duration {0} s (limit {1} s), {2:N1} MB" -f $dur.ToString('0.000', $inv), $tl.hardLimit, ((Get-Item $Out).Length / 1MB))
Write-Host ("Line starts in the finished video: " + (($o[0..($n - 1)] | ForEach-Object { N $_ }) -join ', '))
if ($dur -gt [double]$tl.hardLimit) { Write-Host 'TOO LONG. DO NOT SUBMIT THIS FILE.' -ForegroundColor Red; exit 2 }
