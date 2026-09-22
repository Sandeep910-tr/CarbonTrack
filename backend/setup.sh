#!/bin/bash
# CarbonTrack Logistics System — one-shot Mac/Linux setup.
# Run from the "backend" folder:  bash setup.sh
set -e

echo "== CarbonTrack setup =="

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

echo "Installing dependencies..."
pip install -q -r requirements.txt

echo "Training AI models for your installed library versions (avoids pickle version mismatches)..."
(cd ml && python3 train.py)

echo "Seeding database..."
python3 seed.py

echo ""
echo "Setup complete. Starting server at http://localhost:5000 ..."
python3 app.py
