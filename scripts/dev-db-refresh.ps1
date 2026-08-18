# Refresh the local dev database from production.
#
# Uses SQLite's own backup API inside the container, not `cp`: the scheduler
# writes to that file while we read it, and a plain copy of a live SQLite
# database can be torn. The snapshot is removed from the server afterwards.
#
# One direction only. Nothing here ever writes to production.
#
# Usage:  .\scripts\dev-db-refresh.ps1

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$remote = "mangatracker"
$snapshot = "~/manga-tracker-data/dev-snapshot.db"

Write-Host "1/3 Tomando snapshot consistente en el servidor..." -ForegroundColor Cyan
ssh $remote "docker exec manga-tracker python -c `"
import sqlite3
src = sqlite3.connect('/app/data/manga-tracker.db')
dst = sqlite3.connect('/app/data/dev-snapshot.db')
src.backup(dst)
dst.close(); src.close()
`""
if ($LASTEXITCODE -ne 0) { Write-Error "El snapshot fallo. VPN con LAN habilitada?" }

Write-Host "2/3 Descargando a data/dev.db..." -ForegroundColor Cyan
scp "${remote}:$snapshot" "data/dev.db"
if ($LASTEXITCODE -ne 0) { Write-Error "La descarga fallo." }

Write-Host "3/3 Borrando el snapshot del servidor..." -ForegroundColor Cyan
ssh $remote "rm $snapshot"

& "$repoRoot\.venv\Scripts\python.exe" -c @"
import sqlite3
c = sqlite3.connect('data/dev.db')
n = lambda q: c.execute(q).fetchone()[0]
print()
print('  esquema     ', n('PRAGMA user_version'))
print('  mangas      ', n('SELECT COUNT(*) FROM mangas'))
print('  bookmarks   ', n('SELECT COUNT(*) FROM bookmarks'))
print('  historial   ', n('SELECT COUNT(*) FROM reading_history'), 'lecturas')
"@

Write-Host ""
Write-Host "Listo. data/dev.db es una copia; editarla no toca produccion." -ForegroundColor Green
