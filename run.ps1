# run.ps1 - Direct launcher for Institutional Email Intelligence System
Set-Location -Path $PSScriptRoot

Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host " Starting Official Email Intelligence System & Institutional Cockpit..." -ForegroundColor Green
Write-Host "========================================================================" -ForegroundColor Cyan

if (Test-Path ".\.venv\Scripts\python.exe") {
    & ".\.venv\Scripts\python.exe" run.py
} else {
    python run.py
}
