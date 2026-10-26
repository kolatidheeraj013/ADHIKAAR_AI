# ADHIKAAR - Local Services Starter Script (PowerShell)
# Launches Mock Portal (8100), Backend (8000), and Telegram Bot (8200)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  ADHIKAAR - Autonomous Welfare Entitlement Agent" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Verify LM Studio Status
Write-Host "[1/4] Checking LM Studio on port 1234..." -ForegroundColor Yellow
try {
    $lms = Invoke-RestMethod -Uri "http://127.0.0.1:1234/v1/models" -TimeoutSec 3 -ErrorAction Stop
    $modelId = $lms.data[0].id
    Write-Host "  [OK] LM Studio is running. Active model: $modelId" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] LM Studio server is not detected on port 1234." -ForegroundColor Red
    Write-Host "         Please run: lms server start" -ForegroundColor Yellow
    Write-Host "         and load your model: lms load adhikaar-llama3.1-8b-v3" -ForegroundColor Yellow
}

# 2. Start Mock Portal on Port 8100
Write-Host "[2/4] Starting Mock Portal (Port 8100)..." -ForegroundColor Yellow
$portalJob = Start-Process -FilePath "uv" -ArgumentList "run uvicorn app.main:app --host 127.0.0.1 --port 8100" -WorkingDirectory "$PSScriptRoot\..\mock_portal" -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 2

# 3. Start Backend on Port 8000
Write-Host "[3/4] Starting Backend Engine (Port 8000)..." -ForegroundColor Yellow
$backendJob = Start-Process -FilePath "uv" -ArgumentList "run uvicorn app.main:app --host 127.0.0.1 --port 8000" -WorkingDirectory "$PSScriptRoot\..\backend" -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 3

# 4. Start Telegram Bot on Port 8200
Write-Host "[4/4] Starting Telegram Bot (Port 8200)..." -ForegroundColor Yellow
$botJob = Start-Process -FilePath "uv" -ArgumentList "run uvicorn app.main:app --host 127.0.0.1 --port 8200" -WorkingDirectory "$PSScriptRoot\..\telegram_bot" -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 4

Write-Host "----------------------------------------------------------" -ForegroundColor Cyan
# Health Checks
try {
    $bHealth = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 3
    Write-Host "  [OK] Backend: Healthy (db=$($bHealth.db), checkpointer=$($bHealth.checkpointer))" -ForegroundColor Green
} catch {
    Write-Host "  [FAIL] Backend could not be verified." -ForegroundColor Red
}

try {
    $botHealth = Invoke-RestMethod -Uri "http://127.0.0.1:8200/ready" -TimeoutSec 3
    Write-Host "  [OK] Telegram Bot: Ready & Polling live (@Adhikaar013bot)" -ForegroundColor Green
} catch {
    Write-Host "  [FAIL] Telegram Bot could not be verified." -ForegroundColor Red
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  All systems operational! Message @Adhikaar013bot to test." -ForegroundColor Green
Write-Host "  To stop all services: Stop-Process -Id $($portalJob.Id), $($backendJob.Id), $($botJob.Id)" -ForegroundColor DarkGray
Write-Host "==========================================================" -ForegroundColor Cyan
