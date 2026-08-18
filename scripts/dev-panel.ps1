# Start the panel API against the LOCAL dev database.
#
# Why this script exists: production used to double as the test environment.
# It runs against data/dev.db - a snapshot of production, never production
# itself - and it deletes the Telegram variables from this session before
# starting, so nothing here can message a real chat even by accident.
#
# The panel could not notify anyway: manga_tracker/web never imports
# notifier.telegram, and tests/test_architecture.py fails if it ever does.
# Clearing the variables is the second layer, for the sibling commands
# (`run`, `run-job`) that DO send and that a stray terminal could launch.
#
# Usage:  .\scripts\dev-panel.ps1
# Then, in a second terminal:  cd frontend; npm run dev

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

# Deliberate: absent variables make `run` and `run-job` fail fast naming
# them, instead of sending. load_config() reads os.environ only - it never
# reads .env - so a local run starts with no Telegram credentials unless a
# shell exported them. This removes that last possibility.
Remove-Item Env:\TELEGRAM_BOT_TOKEN -ErrorAction SilentlyContinue
Remove-Item Env:\TELEGRAM_CHAT_ID -ErrorAction SilentlyContinue

$env:DB_PATH = "data/dev.db"
$env:LOG_LEVEL = "DEBUG"
if (-not $env:PANEL_PORT) { $env:PANEL_PORT = "8000" }

if (-not (Test-Path $env:DB_PATH)) {
    Write-Error "No existe $env:DB_PATH. Crealo con scripts/dev-db-refresh.ps1 (baja una copia del servidor)."
}

Write-Host "Panel de desarrollo" -ForegroundColor Cyan
Write-Host "  base   : $env:DB_PATH (copia local, no es produccion)"
Write-Host "  puerto : $env:PANEL_PORT"
Write-Host "  telegram: deshabilitado - no hay credenciales en este proceso"
Write-Host ""

& "$repoRoot\.venv\Scripts\python.exe" -m manga_tracker panel
