param([switch]$SkipBuild)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (git status --porcelain) {
    throw "The worktree must be clean before syncing upstream."
}
if (-not (git remote get-url upstream 2>$null)) {
    git remote add upstream https://github.com/UNfukashigi/Anima-LoRA-Factory.git
}

git fetch upstream main
if ($LASTEXITCODE -ne 0) { throw "Unable to fetch upstream/main." }

$archives = git ls-tree -r --name-only upstream/main |
    Where-Object { $_ -match '^Anima-LoRA-Factory-v([0-9]+(?:\.[0-9]+)*)\.zip$' } |
    ForEach-Object { [pscustomobject]@{ Path = $_; Version = [version]$Matches[1] } } |
    Sort-Object Version -Descending
if (-not $archives) { throw "No versioned upstream archive was found." }

$latest = $archives[0]
$branch = "upstream/v$($latest.Version)"
git show-ref --verify --quiet "refs/heads/$branch"
if ($LASTEXITCODE -eq 0) {
    throw "Branch $branch already exists. Delete it after its previous update is merged."
}

git switch -c $branch main
if ($LASTEXITCODE -ne 0) { throw "Unable to create $branch." }
git merge --no-edit upstream/main
if ($LASTEXITCODE -ne 0) { throw "Upstream merge needs manual conflict resolution on $branch." }

$lockPath = Join-Path $repoRoot "docker/upstream.lock.json"
$lock = Get-Content -LiteralPath $lockPath -Raw | ConvertFrom-Json
$oldArchive = $lock.archive
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $repoRoot $latest.Path)).Hash.ToLowerInvariant()
$lock.archive = $latest.Path
$lock.version = $latest.Version.ToString()
$lock.sha256 = $hash
$lock | ConvertTo-Json | Set-Content -LiteralPath $lockPath -Encoding utf8

foreach ($file in @("Dockerfile", "compose.yaml")) {
    $path = Join-Path $repoRoot $file
    $content = Get-Content -LiteralPath $path -Raw
    Set-Content -LiteralPath $path -Value $content.Replace($oldArchive, $latest.Path) -Encoding utf8 -NoNewline
}

if (-not $SkipBuild) {
    docker compose build
    if ($LASTEXITCODE -ne 0) { throw "Docker validation failed. Review the upstream patch on $branch." }
}

git add docker/upstream.lock.json Dockerfile compose.yaml
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git commit -m "Update Docker build to upstream v$($latest.Version)"
    if ($LASTEXITCODE -ne 0) { throw "Unable to commit the updated archive lock." }
}

Write-Output "Upstream update prepared on $branch. Review it, then push the branch and open a pull request."

