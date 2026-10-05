<#
.SYNOPSIS
    Automates the safe, project-level parts of getting the Scaitale backend runnable:
    a Python virtual environment, its pip dependencies, a starter .env file, and the
    gitignored runtime directories the app expects to exist.

.DESCRIPTION
    Deliberately does NOT install Python itself, FFmpeg, Postgres, Redis/Memurai, CUDA, or any
    other system-level software  -  see docs/SETUP_AUTOMATION.md for exactly why, and what you
    still need to install by hand. This script only ever:
      - creates .venv if it doesn't already exist (never recreates/deletes an existing one)
      - installs Python packages FROM THIS REPO'S OWN requirements files INTO that venv
      - copies .env.example to .env if, and only if, .env doesn't already exist
      - creates a handful of empty, gitignored runtime directories (recordings\, transcripts\,
        models\) with New-Item -Force, which is idempotent  -  it does nothing destructive to a
        directory that's already there with real files in it
    It never overwrites an existing .env, never touches an existing .venv's installed packages
    beyond what `pip install -r <file>` itself does (which is itself idempotent/incremental),
    and never deletes anything.

.PARAMETER Requirements
    Which requirements file to install. Defaults to 'requirements.txt' (the full local-dev
    union  -  matches CLAUDE.md's own documented quick-start). Pass 'requirements-api.txt' or
    'requirements-worker.txt' if you specifically want just one tier's lean footprint.

.PARAMETER SkipTests
    Skip the final `pytest tests/ -v` verification run. Verification runs by default because
    it's the fastest way to confirm the install actually worked  -  it makes no changes itself.

.EXAMPLE
    .\scripts\setup_backend.ps1
.EXAMPLE
    .\scripts\setup_backend.ps1 -Requirements requirements-worker.txt -SkipTests
#>

[CmdletBinding()]
param(
    [string]$Requirements = 'requirements.txt',
    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot

function Write-Step($msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "    OK: $msg" -ForegroundColor Green }
function Write-Note($msg) { Write-Host "    NOTE: $msg" -ForegroundColor Yellow }

if (-not (Test-Path (Join-Path $repoRoot 'backend\main.py'))) {
    Write-Error "backend\main.py not found under $repoRoot  -  run this script from a clone of academic-discussion-assistant."
}

Set-Location $repoRoot

# --- 0. Environment check first (read-only, catches missing Python/FFmpeg early) -----------

Write-Step "Running scripts\check_environment.ps1 first"
& (Join-Path $PSScriptRoot 'check_environment.ps1')

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Error "python not found on PATH. Install Python 3.11 first (see docs/SETUP.md)  -  this script does not install Python itself."
}

# --- 1. Virtual environment (create only if missing  -  never recreated) ---------------------

Write-Step "Python virtual environment (.venv)"
$venvPath = Join-Path $repoRoot '.venv'
$venvPython = Join-Path $venvPath 'Scripts\python.exe'

if (Test-Path $venvPython) {
    Write-Ok "Reusing existing .venv at $venvPath (not recreated  -  your installed packages/history are untouched)."
} else {
    Write-Host "    Creating .venv (this runs 'python -m venv .venv'  -  no packages installed yet)..."
    python -m venv $venvPath
    if (-not (Test-Path $venvPython)) {
        Write-Error "venv creation appears to have failed  -  $venvPython was not created."
    }
    Write-Ok "Created .venv."
}

# --- 2. pip dependencies (incremental install  -  safe to re-run) ----------------------------

Write-Step "Installing Python dependencies from $Requirements into .venv"
$requirementsPath = Join-Path $repoRoot $Requirements
if (-not (Test-Path $requirementsPath)) {
    Write-Error "$Requirements not found at $requirementsPath."
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r $requirementsPath
if ($LASTEXITCODE -ne 0) {
    Write-Error "pip install failed (exit code $LASTEXITCODE)  -  see output above. Common cause: a compiler/build-tool is missing for one of the ML packages; see docs/TROUBLESHOOTING.md."
}
Write-Ok "Dependencies installed from $Requirements."

# --- 3. .env file (created only if missing  -  never overwritten) ----------------------------

Write-Step "Environment file (.env)"
$envExamplePath = Join-Path $repoRoot '.env.example'
$envPath = Join-Path $repoRoot '.env'

if (Test-Path $envPath) {
    Write-Ok ".env already exists  -  left untouched. Compare it against .env.example by hand if you think it's missing a newer variable."
} elseif (Test-Path $envExamplePath) {
    $generatedSecret = & $venvPython -c "import secrets; print(secrets.token_hex(32))"
    # -Encoding UTF8 on BOTH read and write: .env.example contains real UTF-8 text (em dashes in
    # its comments). Get-Content's default encoding in Windows PowerShell 5.1 is the system
    # codepage, not UTF-8 -- without specifying it explicitly here, those multi-byte characters
    # get misread as separate Latin-1 bytes and come out as mojibake ("a€"" for an em dash) in the
    # .env this writes. Confirmed directly: this exact bug happened on the first version of this
    # script and was caught by actually reading the .env it produced, not assumed away.
    $envContent = Get-Content $envExamplePath -Raw -Encoding UTF8
    # Only ever fills in the JWT_SECRET_KEY= line on a FRESH copy  -  never touches an existing .env.
    $envContent = $envContent -replace '(?m)^JWT_SECRET_KEY=\s*$', "JWT_SECRET_KEY=$generatedSecret"
    Set-Content -Path $envPath -Value $envContent -Encoding UTF8 -NoNewline
    Write-Ok "Created .env from .env.example, with a freshly generated JWT_SECRET_KEY filled in (dev-only convenience  -  regenerate for anything beyond local dev)."
    Write-Note "Every other value in .env is a blank/default placeholder  -  HF_TOKEN, DATABASE_URL, CELERY_BROKER_URL, SENTRY_DSN are all OPTIONAL and can stay blank. Open .env and review it."
} else {
    Write-Note ".env.example not found  -  skipping .env creation. Set JWT_SECRET_KEY as a real environment variable instead: `$env:JWT_SECRET_KEY = (python -c \"import secrets; print(secrets.token_hex(32))\")"
}

# --- 4. Runtime directories (idempotent  -  New-Item -Force never deletes existing content) --

Write-Step "Runtime directories"
# recordings\ and models\ are already real, populated, gitignored directories on a machine
# that's been used before  -  -Force on an existing directory is a documented no-op, it does
# NOT clear or recreate it. transcripts\ is also auto-created by backend/core/config.py's own
# import-time settings.transcripts_dir.mkdir(...), so this is belt-and-suspenders, not new
# behavior.
$runtimeDirs = @('recordings', 'transcripts', 'models')
foreach ($dir in $runtimeDirs) {
    $fullPath = Join-Path $repoRoot $dir
    New-Item -ItemType Directory -Force -Path $fullPath | Out-Null
}
Write-Ok "Confirmed recordings\, transcripts\, models\ exist (created only if missing; nothing inside any of them was touched)."

# --- 5. Verification (optional, safe  -  read-only test run) ---------------------------------

if (-not $SkipTests) {
    Write-Step "Verifying with pytest tests/ -v"
    $previousJwt = $env:JWT_SECRET_KEY
    if (-not $env:JWT_SECRET_KEY) {
        $env:JWT_SECRET_KEY = 'setup-script-verification-only'
    }
    & $venvPython -m pytest (Join-Path $repoRoot 'tests') -v
    $testExit = $LASTEXITCODE
    if (-not $previousJwt) {
        Remove-Item Env:\JWT_SECRET_KEY -ErrorAction SilentlyContinue
    }
    if ($testExit -eq 0) {
        Write-Ok "pytest passed. Expect '90 passed, 1 skipped' on the SQLite default (the 1 skip is a Postgres-only concurrency test  -  see tests/test_session_service.py)."
    } else {
        Write-Note "pytest exited with code $testExit  -  review the output above. This does not mean setup failed outright; check docs/TROUBLESHOOTING.md."
    }
} else {
    Write-Note "Skipped pytest verification (-SkipTests passed)."
}

# --- Summary: what this script did NOT do ---------------------------------------------------

Write-Host ""
Write-Host ("=" * 70)
Write-Host "Backend setup finished. Still your responsibility (see docs/SETUP_AUTOMATION.md):" -ForegroundColor Cyan
Write-Host "  - FFmpeg must be installed and on PATH (this script only checks for it, never installs it)."
Write-Host "  - Postgres/Redis are optional  -  only needed for the 'production architecture' path,"
Write-Host "    not for local dev or pytest. SQLite + Celery's eager mode need nothing extra."
Write-Host "  - HF_TOKEN (optional)  -  only if you want pyannote diarization; create one at huggingface.co."
Write-Host "  - Review the .env file this script created/left in place before starting the server."
Write-Host "  - Start the API: `$venvPy = '.venv\Scripts\python.exe' ; & .venv\Scripts\uvicorn.exe backend.main:app --reload"
Write-Host ("=" * 70)
Write-Host ""
