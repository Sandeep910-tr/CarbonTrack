# CarbonTrack Logistics System — one-shot Windows setup.
# Run this from the "backend" folder in PowerShell:
#   .\setup.ps1
#
# It creates the venv, installs dependencies, trains the AI models using
# whatever library versions actually get installed on THIS machine (avoiding
# the classic "model was pickled with a different scikit-learn version"
# crash), seeds the database, then starts the server.

Write-Host "== CarbonTrack setup ==" -ForegroundColor Cyan

if (-not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    py -m venv venv
}

Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& .\venv\Scripts\Activate.ps1

Write-Host "Installing dependencies..." -ForegroundColor Yellow
pip install -q -r requirements.txt

Write-Host "Training AI models for your installed library versions (avoids pickle version mismatches)..." -ForegroundColor Yellow
Push-Location ml
python train.py
Pop-Location

Write-Host "Seeding database..." -ForegroundColor Yellow
python seed.py

Write-Host ""
Write-Host "Setup complete. Starting server at http://localhost:5000 ..." -ForegroundColor Green
python app.py
