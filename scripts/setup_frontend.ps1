<#
.SYNOPSIS
    Automates the safe, project-level parts of getting the Flutter client (android\) runnable:
    checks the Flutter SDK is present, fetches this project's own pub dependencies, and reports
    on Android SDK / device configuration it deliberately does not touch.

.DESCRIPTION
    Deliberately does NOT install Flutter, the Android SDK, Java/JDK, or any emulator/device
    tooling  -  see docs/SETUP_AUTOMATION.md for why, and what to install by hand. This script
    only ever:
      - verifies `flutter` is on PATH (fails with clear guidance if not  -  it cannot proceed
        without it, and will not attempt to install it)
      - runs `flutter pub get` inside android\ (this project's own declared pub dependencies
        only  -  pubspec.yaml is the sole source of what gets fetched, nothing is added to it)
      - reports whether android\android\local.properties exists, WITHOUT creating one itself
        (a guessed Android SDK path would be wrong on most machines  -  Flutter/Android Studio
        generates this correctly the first time you open or run the project for real)
      - reports connected devices/emulators (informational; starts nothing, installs nothing)
    Never modifies pubspec.yaml, never touches android\android\ (the native Gradle project),
    never deletes android\build\ (Flutter's own generated output  -  safe to delete by hand any
    time, but not this script's job).

.PARAMETER RunChecks
    Also run `flutter analyze` and `flutter test` at the end, to verify the fetched
    dependencies actually resolve into a working project. Off by default to keep the script
    fast; both are read-only (no code changes).

.EXAMPLE
    .\scripts\setup_frontend.ps1
.EXAMPLE
    .\scripts\setup_frontend.ps1 -RunChecks
#>

[CmdletBinding()]
param(
    [switch]$RunChecks
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$androidDir = Join-Path $repoRoot 'android'

function Write-Step($msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "    OK: $msg" -ForegroundColor Green }
function Write-Note($msg) { Write-Host "    NOTE: $msg" -ForegroundColor Yellow }

if (-not (Test-Path (Join-Path $androidDir 'pubspec.yaml'))) {
    Write-Error "android\pubspec.yaml not found under $repoRoot  -  run this script from a clone of academic-discussion-assistant."
}

# --- 1. Flutter SDK present? (cannot proceed without it  -  this script will not install it) --

Write-Step "Checking for the Flutter SDK"
$flutterCmd = Get-Command flutter -ErrorAction SilentlyContinue
if (-not $flutterCmd) {
    Write-Error "flutter not found on PATH. Install the Flutter SDK yourself (this project was built against 3.47.2 stable  -  see CLAUDE.md's Tech Stack table and docs/SETUP.md) and ensure 'flutter' runs from a fresh terminal, then re-run this script."
}
$flutterVersionOutput = & flutter --version 2>$null
Write-Ok ($flutterVersionOutput | Select-Object -First 1)

# --- 2. Fetch this project's own declared pub dependencies -----------------------------------

Write-Step "Running 'flutter pub get' in android\"
Push-Location $androidDir
try {
    flutter pub get
    if ($LASTEXITCODE -ne 0) {
        Write-Error "flutter pub get failed (exit code $LASTEXITCODE)  -  see output above."
    }
    Write-Ok "Pub dependencies fetched per android\pubspec.yaml (nothing added/changed in pubspec.yaml itself)."
} finally {
    Pop-Location
}

# --- 3. Android SDK configuration  -  report only, never guessed/created ----------------------

Write-Step "Checking android\android\local.properties"
$localProps = Join-Path $androidDir 'android\local.properties'
if (Test-Path $localProps) {
    Write-Ok "local.properties exists  -  Android SDK path already configured."
} else {
    Write-Note "local.properties not found. This file is machine-specific (it records your Android SDK path) and is NOT created by this script  -  a guessed path would likely be wrong and could point the build at a nonexistent SDK. Generate it correctly by opening android\ once in Android Studio, or by running 'flutter doctor' and 'flutter run' (from android\) with the Android SDK already installed and ANDROID_HOME/ANDROID_SDK_ROOT set."
}

# --- 4. Connected devices/emulators  -  informational only -------------------------------------

Write-Step "Checking for connected devices/emulators"
$devicesOutput = & flutter devices 2>$null
if ($devicesOutput -match 'No devices') {
    Write-Note "No devices/emulators currently detected. Start an emulator (Android Studio's Device Manager) or connect a physical device before 'flutter run'. See docs/SETUP.md and docs/MODIFICATION_COOKBOOK.md entry 8 for emulator-vs-physical-device server-URL differences."
} else {
    Write-Ok "Device(s) detected:"
    $devicesOutput | ForEach-Object { Write-Host "      $_" }
}

# --- 5. Optional verification -----------------------------------------------------------------

if ($RunChecks) {
    Write-Step "Running flutter analyze"
    Push-Location $androidDir
    try {
        flutter analyze
        if ($LASTEXITCODE -eq 0) { Write-Ok "flutter analyze: no issues found." }
        else { Write-Note "flutter analyze reported issues (exit code $LASTEXITCODE)  -  see output above." }

        Write-Step "Running flutter test"
        flutter test
        if ($LASTEXITCODE -eq 0) { Write-Ok "flutter test: all tests passed." }
        else { Write-Note "flutter test reported failures (exit code $LASTEXITCODE)  -  see output above." }
    } finally {
        Pop-Location
    }
} else {
    Write-Note "Skipped 'flutter analyze'/'flutter test' (pass -RunChecks to run them)."
}

# --- Summary: what this script did NOT do -----------------------------------------------------

Write-Host ""
Write-Host ("=" * 70)
Write-Host "Frontend setup finished. Still your responsibility (see docs/SETUP_AUTOMATION.md):" -ForegroundColor Cyan
Write-Host "  - Installing the Flutter SDK itself, the Android SDK, and a Java/JDK (this script only"
Write-Host "    checks for Flutter; it never installs any of these)."
Write-Host "  - Generating android\android\local.properties correctly (open the project in Android"
Write-Host "    Studio once, or run 'flutter doctor' with the Android SDK already set up)."
Write-Host "  - Starting/selecting a device or emulator before 'flutter run'."
Write-Host "  - Setting the server address on the app's Settings screen (10.0.2.2:8000 for the"
Write-Host "    emulator; the host's real LAN IP + 'uvicorn ... --host 0.0.0.0' for a physical device)."
Write-Host "  - Run the app: cd android; flutter run"
Write-Host ("=" * 70)
Write-Host ""
