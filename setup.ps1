# FILE: setup.ps1
# WHY: Windows equivalent of `make setup` so the demo is easy on PowerShell.

python -m venv .venv
& .\.venv\Scripts\python -m pip install --upgrade pip
& .\.venv\Scripts\pip install -r requirements.txt

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env from .env.example. Add OPENAI_API_KEY and LANGSMITH_API_KEY."
} else {
    Write-Host ".env already exists. Setup is done."
}

Write-Host "Activate the venv with: .\.venv\Scripts\Activate.ps1"
Write-Host "Then run: python -m src.cli"
