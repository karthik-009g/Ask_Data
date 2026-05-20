$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendPath = Join-Path $repoRoot "backend"
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"

$existing = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existing) {
	Stop-Process -Id $existing.OwningProcess -Force -ErrorAction SilentlyContinue
}

Set-Location $backendPath
& $pythonPath -m uvicorn app.main:app --host 127.0.0.1 --port 8000
