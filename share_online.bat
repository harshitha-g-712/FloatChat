@echo off
setlocal enabledelayedexpansion

echo ==============================================================
echo   ArgoLens - Share Online (Public HTTPS Link for WhatsApp)
echo ==============================================================
echo.
echo [1/2] Checking if ArgoLens server is running on port 8000...
powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 2 -UseBasicParsing; Write-Host '[OK] ArgoLens server is running!' -ForegroundColor Green } catch { Write-Host '[INFO] Please make sure run_floatchat.bat is running in another window.' -ForegroundColor Yellow }"

echo.
echo [2/2] Generating public HTTPS link...
echo Copy the generated https:// link below.
echo When you send that link on WhatsApp, it will be a real blue clickable link!
echo Keep this terminal window open while sharing.
echo.
echo ==============================================================
echo.
npx --yes localtunnel --port 8000
pause
