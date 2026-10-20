param([string]$Python = 'python', [int]$Port = 8001, [switch]$SetupOnly)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        & $Python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required. Pass -Python with its executable path.' }
    }
    & '.\.venv\Scripts\python.exe' -m pip install -e '.[dev]' --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    if (-not $SetupOnly) {
        & '.\.venv\Scripts\python.exe' -m uvicorn maintaineros.main:app --host 127.0.0.1 --port $Port
    }
} finally { Pop-Location }
