<#
.SYNOPSIS
    Read-only diagnostic for Scaitale's development environment. Checks what's installed and
    configured; changes NOTHING on disk, in the registry, or in any running service.

.DESCRIPTION
    Mirrors the checks docs/COLD_START_VERIFICATION.md and docs/SETUP.md already describe by
    hand, so a developer (or setup_backend.ps1 / setup_frontend.ps1, which call this first) can
    get a PASS/WARN/INFO/FAIL readout in one command instead of running each check manually.

    Every check here is read-only: Get-Command, Test-Path, version-flag invocations
    (--version, -V), and a single read-only Test-NetConnection probe for Redis/Memurai. Nothing
    is installed, created, deleted, or modified. Safe to run at any time, as many times as you
    like, on a machine you've never touched before.

.EXAMPLE
    .\scripts\check_environment.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot

# --- helpers ---------------------------------------------------------------

$script:results = New-Object System.Collections.Generic.List[object]

function Add-Result {
    param(
        [string]$Category,
        [ValidateSet('PASS', 'WARN', 'INFO', 'FAIL')][string]$Status,
        [string]$Message
    )
    $script:results.Add([pscustomobject]@{ Category = $Category; Status = $Status; Message = $Message })
}

function Get-CommandVersion {
    # Runs `<exe> <versionArg>` and returns its first non-blank output line, or $null if the exe
    # isn't found. Several tools this checks (ffmpeg/ffprobe in particular) write their version
    # banner to stderr, not stdout. Under this script's own $ErrorActionPreference = 'Stop', even
    # a *successful* native command's stderr text gets turned into a terminating error the moment
    # it's touched by any redirection -- confirmed directly against this exact ffmpeg build,
    # `2>$null` included, not just `2>&1` (a stricter case than this tool's own general PowerShell
    # 5.1 caveat about `2>&1`). Locally relaxing $ErrorActionPreference around just this one native
    # call, then restoring it, is what actually avoids that -- not a redirection change.
    param([string]$Exe, [string]$VersionArg = '--version')
    $cmd = Get-Command $Exe -ErrorAction SilentlyContinue
    if (-not $cmd) { return $null }
    $previousPref = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $combined = & $Exe $VersionArg 2>&1 | Out-String
        $firstLine = ($combined -split "`r?`n" | Where-Object { $_.Trim() -ne '' } | Select-Object -First 1)
        if ($firstLine) {
            # Strip the "ffmpeg.exe : " style prefix PowerShell adds when it wraps a native
            # command's stderr line as an ErrorRecord and it's later stringified via Out-String.
            return ($firstLine -replace '^[^:]+\.exe\s*:\s*', '').Trim()
        }
        return "(found at $($cmd.Source), version unknown)"
    } catch {
        return "(found at $($cmd.Source), $VersionArg failed to run)"
    } finally {
        $ErrorActionPreference = $previousPref
    }
}

Write-Host ""
Write-Host "Scaitale environment check" -ForegroundColor Cyan
Write-Host "Repo root: $repoRoot"
Write-Host ("=" * 70)

# --- repo sanity -------------------------------------------------------------

if (-not (Test-Path (Join-Path $repoRoot 'backend\main.py'))) {
    Add-Result 'Repo' 'FAIL' "backend\main.py not found under $repoRoot  -  is this the right directory?"
} else {
    Add-Result 'Repo' 'PASS' "Running from the repo root ($repoRoot)."
}

# --- Git -----------------------------------------------------------------

$gitVersion = Get-CommandVersion -Exe 'git'
if ($gitVersion) {
    Add-Result 'Git' 'PASS' $gitVersion
} else {
    Add-Result 'Git' 'FAIL' "git not found on PATH. Required to clone/work with this repo at all."
}

# --- Python ----------------------------------------------------------------

$pythonVersion = Get-CommandVersion -Exe 'python'
if ($pythonVersion) {
    if ($pythonVersion -match '3\.11') {
        Add-Result 'Python' 'PASS' "$pythonVersion (matches this project's known-good version, per CLAUDE.md)."
    } else {
        Add-Result 'Python' 'WARN' "$pythonVersion  -  this project was built/tested against 3.11.9. A different 3.x may still work but is unverified."
    }
} else {
    Add-Result 'Python' 'FAIL' "python not found on PATH. Required for the entire backend."
}

# --- Virtual environment ----------------------------------------------------

$venvPath = Join-Path $repoRoot '.venv'
$venvPython = Join-Path $venvPath 'Scripts\python.exe'
if (Test-Path $venvPython) {
    $venvPyVersion = & $venvPython --version 2>$null
    Add-Result 'Virtualenv' 'PASS' ".venv exists ($venvPyVersion). Run scripts\setup_backend.ps1 to (re)install dependencies into it."

    $torchCheck = & $venvPython -c "
try:
    import torch
    print('torch ' + torch.__version__ + ' | CUDA available: ' + str(torch.cuda.is_available()))
except ImportError:
    print('NOT INSTALLED')
" 2>$null
    if ($torchCheck -eq 'NOT INSTALLED') {
        Add-Result 'Virtualenv' 'INFO' "torch is not installed in .venv yet  -  run scripts\setup_backend.ps1."
    } elseif ($torchCheck) {
        Add-Result 'Virtualenv' 'INFO' "$torchCheck (see docs/MODIFICATION_COOKBOOK.md entry 24  -  this project's default torch wheel is CPU-only even on a machine with a GPU)."
    }
} else {
    Add-Result 'Virtualenv' 'INFO' ".venv not found yet  -  scripts\setup_backend.ps1 will create it."
}

# --- FFmpeg ------------------------------------------------------------------

$ffmpegVersion = Get-CommandVersion -Exe 'ffmpeg'
if ($ffmpegVersion) {
    Add-Result 'FFmpeg' 'PASS' $ffmpegVersion
} else {
    Add-Result 'FFmpeg' 'FAIL' "ffmpeg not found on PATH. REQUIRED  -  every audio-touching path in this project shells out to it. Install it and add its bin\ directory to PATH; this script/project will not install it for you."
}

$ffprobeVersion = Get-CommandVersion -Exe 'ffprobe'
if ($ffprobeVersion) {
    Add-Result 'FFmpeg' 'PASS' "ffprobe also on PATH."
} else {
    Add-Result 'FFmpeg' 'FAIL' "ffprobe not found on PATH (usually ships alongside ffmpeg  -  check the same install)."
}

# --- Flutter / Dart ----------------------------------------------------------

$flutterVersion = Get-CommandVersion -Exe 'flutter'
if ($flutterVersion) {
    Add-Result 'Flutter' 'PASS' $flutterVersion
} else {
    Add-Result 'Flutter' 'WARN' "flutter not found on PATH. Only needed if you're working on the android\ client  -  not required for backend-only work."
}

$dartVersion = Get-CommandVersion -Exe 'dart'
if ($dartVersion) {
    Add-Result 'Flutter' 'INFO' "dart: $dartVersion"
}

$localProps = Join-Path $repoRoot 'android\android\local.properties'
if (Test-Path $localProps) {
    Add-Result 'Flutter' 'PASS' "android\android\local.properties exists (Android SDK path configured)."
} else {
    Add-Result 'Flutter' 'INFO' "android\android\local.properties not found  -  Flutter/Android Studio normally generates this the first time you open/run the android\ project. Not auto-created by this check (it needs a real, machine-specific SDK path)."
}

# --- Environment file / secrets (presence only  -  never prints values) -------

$envFile = Join-Path $repoRoot '.env'
if (Test-Path $envFile) {
    Add-Result 'Config' 'PASS' ".env exists at repo root."

    $envContent = Get-Content $envFile -Raw
    $envMap = @{}
    foreach ($line in ($envContent -split "`r?`n")) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
            $envMap[$Matches[1]] = $Matches[2].Trim()
        }
    }

    if ($envMap.ContainsKey('JWT_SECRET_KEY') -and $envMap['JWT_SECRET_KEY']) {
        Add-Result 'Config' 'PASS' "JWT_SECRET_KEY is set in .env (value not shown)."
    } elseif ($env:JWT_SECRET_KEY) {
        Add-Result 'Config' 'PASS' "JWT_SECRET_KEY is set as a real environment variable (value not shown)."
    } else {
        Add-Result 'Config' 'FAIL' "JWT_SECRET_KEY is not set anywhere. The API refuses every request needing auth without it, and refuses to even start when ENVIRONMENT=production. See .env.example."
    }

    foreach ($optionalVar in @('HF_TOKEN', 'DATABASE_URL', 'CELERY_BROKER_URL', 'SENTRY_DSN')) {
        if (($envMap.ContainsKey($optionalVar) -and $envMap[$optionalVar]) -or (Get-Item "env:$optionalVar" -ErrorAction SilentlyContinue)) {
            Add-Result 'Config' 'INFO' "$optionalVar is set (value not shown)."
        } else {
            Add-Result 'Config' 'INFO' "$optionalVar is not set  -  fine, it's optional (see .env.example for what it unlocks)."
        }
    }
} else {
    Add-Result 'Config' 'WARN' ".env not found. Copy .env.example to .env (scripts\setup_backend.ps1 does this for you), or export JWT_SECRET_KEY directly as a real environment variable."
}

# --- Postgres (optional) ------------------------------------------------------

$psqlVersion = Get-CommandVersion -Exe 'psql'
if ($psqlVersion) {
    Add-Result 'Postgres' 'INFO' "psql found ($psqlVersion)  -  optional; SQLite is this project's zero-config default."
} else {
    Add-Result 'Postgres' 'INFO' "psql not found on PATH  -  fine if you're using the SQLite default. Only needed for the 'production architecture' Postgres path."
}

# --- Redis / Memurai (optional)  -  a single read-only TCP probe, no data touched --------------

try {
    $redisProbe = Test-NetConnection -ComputerName '127.0.0.1' -Port 6379 -InformationLevel Quiet -WarningAction SilentlyContinue
    if ($redisProbe) {
        Add-Result 'Redis' 'INFO' "Something is listening on 127.0.0.1:6379 (likely Redis/Memurai). Optional  -  Celery's eager mode needs no broker at all."
    } else {
        Add-Result 'Redis' 'INFO' "Nothing listening on 127.0.0.1:6379  -  fine, Celery will run in eager mode (in-process, no broker) unless CELERY_BROKER_URL is set."
    }
} catch {
    Add-Result 'Redis' 'INFO' "Could not probe 127.0.0.1:6379 (Test-NetConnection unavailable or blocked)  -  not fatal, this check is purely informational."
}

# --- GPU (informational only  -  see docs/MODIFICATION_COOKBOOK.md entry 24) --------------------

$nvidiaSmi = Get-Command 'nvidia-smi' -ErrorAction SilentlyContinue
if ($nvidiaSmi) {
    Add-Result 'GPU' 'INFO' "nvidia-smi found  -  an NVIDIA GPU/driver is present. This does NOT mean the project is using it: check the 'Virtualenv' torch line above (this project's default install is CPU-only torch)."
} else {
    Add-Result 'GPU' 'INFO' "nvidia-smi not found  -  no NVIDIA GPU/driver detected, or not on PATH. This project runs entirely on CPU by default regardless, so this is not a blocker."
}

# --- Summary -----------------------------------------------------------------

Write-Host ""
Write-Host "Results:" -ForegroundColor Cyan
Write-Host ("=" * 70)

foreach ($group in ($script:results | Group-Object Category)) {
    Write-Host ""
    Write-Host $group.Name -ForegroundColor White
    foreach ($item in $group.Group) {
        $color = switch ($item.Status) {
            'PASS' { 'Green' }
            'WARN' { 'Yellow' }
            'FAIL' { 'Red' }
            default { 'Gray' }
        }
        Write-Host ("  [{0,4}] {1}" -f $item.Status, $item.Message) -ForegroundColor $color
    }
}

$failCount = ($script:results | Where-Object { $_.Status -eq 'FAIL' }).Count
$warnCount = ($script:results | Where-Object { $_.Status -eq 'WARN' }).Count

Write-Host ""
Write-Host ("=" * 70)
if ($failCount -gt 0) {
    Write-Host "$failCount FAIL, $warnCount WARN. Fix the FAIL items above before expecting the backend to run." -ForegroundColor Red
} elseif ($warnCount -gt 0) {
    Write-Host "0 FAIL, $warnCount WARN. Should mostly work; review the WARN items above." -ForegroundColor Yellow
} else {
    Write-Host "All checks passed or informational. See docs/SETUP.md / docs/SETUP_AUTOMATION.md for what's next." -ForegroundColor Green
}
Write-Host ""
