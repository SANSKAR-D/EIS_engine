@echo off
title Institutional Email Intelligence System
cd /d "%~dp0"
echo ========================================================================
echo  Starting Official Email Intelligence System & Institutional Cockpit...
echo ========================================================================

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run.py
) else (
    python run.py
)

pause
