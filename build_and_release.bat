@echo off
echo ============================================================
echo  Treetime - Build and Release
echo ============================================================
echo.
cd /d "%~dp0"
python release.py
echo.
pause
