#!/usr/bin/env bash
# Exit immediately if a command exits with a non-zero status
set -o errexit

echo "--- Installing Python dependencies ---"
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "--- Collecting Static Files via WhiteNoise ---"
python manage.py collectstatic --noinput

echo "--- Running Database Migrations ---"
python manage.py migrate

echo "--- Build Complete! ---"
