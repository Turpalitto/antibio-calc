# AntibioDB — Windows entry point for the database build.
#
# Audit 2026-10-14 (D-3): this file used to be a second, independent
# implementation of the merge + source-gate + validate pipeline next to
# `db/build_db.py`, so the two could (and did) drift. It is now a thin wrapper:
# every policy decision lives in `db/build_db.py` (merge order, the source gate
# via `calculator_source_gate.apply_source_gate`, `node db/validate_db.js`).
#
# Запуск: pwsh -File db/build_db.ps1 [любые аргументы build_db.py, например
#          --skip-validate, --block-no-cr]

$ErrorActionPreference = 'Stop'
$dbDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $dbDir
$buildPy = Join-Path $dbDir 'build_db.py'
if (-not (Test-Path -LiteralPath $buildPy)) { throw "build_db.py not found: $buildPy" }

# Interpreter: the repo venv first (uv sync creates .venv), then the launcher.
$candidates = @(
    (Join-Path $projectRoot '.venv\Scripts\python.exe'),
    (Join-Path $projectRoot '.venv\bin\python')
)
$python = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $python) {
    if (Get-Command py -ErrorAction SilentlyContinue) { $python = 'py'; $launcherArgs = @('-3') }
    elseif (Get-Command python3 -ErrorAction SilentlyContinue) { $python = 'python3' }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { $python = 'python' }
    else { throw "No Python interpreter found (expected .venv or py/python on PATH)" }
}
if (-not $launcherArgs) { $launcherArgs = @() }

Push-Location $projectRoot
try {
    & $python @launcherArgs $buildPy @args
    if ($LASTEXITCODE -ne 0) { throw "db/build_db.py failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}
