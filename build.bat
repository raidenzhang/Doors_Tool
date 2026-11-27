@echo off
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean --onefile --windowed --name DOORS-Importer --add-data "CHANGELOG.md:." main.py
pause
