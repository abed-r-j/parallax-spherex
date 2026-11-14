# Publish web/dist as the gh-pages branch (one commit on top of the previous one).
# Usage, from the repository root:   powershell -File web\scripts\publish_site.ps1 [-Push]
# SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
param([switch]$Push)

$ErrorActionPreference = 'Stop'
$root = (git rev-parse --show-toplevel)
$dist = Join-Path $root 'web/dist'
if (-not (Test-Path (Join-Path $dist 'index.html'))) { throw "web/dist is not built: run 'npm run build' in web/" }
New-Item -ItemType File -Force (Join-Path $dist '.nojekyll') | Out-Null

# A separate index file, so the working tree and the normal index are left untouched.
$env:GIT_INDEX_FILE = Join-Path $root '.git/index-gh-pages'
Remove-Item $env:GIT_INDEX_FILE -ErrorAction SilentlyContinue
git --work-tree="$dist" add -A -f .
$tree = git write-tree
$source = git rev-parse --short HEAD
$parent = git rev-parse -q --verify refs/heads/gh-pages
$msg = "Site build from $source"
if ($parent) { $commit = git commit-tree $tree -p $parent -m $msg } else { $commit = git commit-tree $tree -m $msg }
git update-ref refs/heads/gh-pages $commit
Remove-Item $env:GIT_INDEX_FILE -ErrorAction SilentlyContinue
Remove-Item Env:\GIT_INDEX_FILE
$n = (git ls-tree -r --name-only gh-pages | Measure-Object).Count
Write-Output "gh-pages -> $commit ($n files, built from $source)"
if ($Push) { git push origin gh-pages }
