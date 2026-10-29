# 1-Click Launch Script for Adhikaar Sentry Auto-Wake Watchdog (Option A)
# Runs silently in the background, consuming <20MB RAM.
# Automatically launches scripts/start_all.ps1 when a citizen starts @Adhikaar013bot.

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  Starting Adhikaar Sentry Auto-Wake Watchdog (Option A)  " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Sentry monitors @Adhikaar013bot and auto-triggers start_all.ps1"
Write-Host "when a citizen engages the bot."
Write-Host ""

$PythonExe = Join-Path $ProjectRoot "telegram_bot\.venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = Join-Path $ProjectRoot "backend\.venv\Scripts\python.exe"
}
if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python"
}

Start-Process -FilePath $PythonExe -ArgumentList "$ProjectRoot\scripts\sentry.py" -WindowStyle Minimized

Write-Host "[OK] Adhikaar Sentry is active in the background." -ForegroundColor Green
Write-Host "Whenever anyone opens or sends a message to the bot, it will automatically" -ForegroundColor Yellow
Write-Host "launch all services for you!" -ForegroundColor Yellow
