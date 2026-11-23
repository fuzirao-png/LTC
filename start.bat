@echo off
setlocal

set ROOT=%~dp0
set API_DIR=%ROOT%apps\api
set WORKER_DIR=%ROOT%apps\worker
set WEB_DIR=%ROOT%apps\web

echo =========================================
echo   安装后端依赖...
echo =========================================
cd /d "%API_DIR%"
python -m pip install -r requirements.txt -r "%WORKER_DIR%\requirements.txt" -q
if %errorlevel% neq 0 (
    echo 后端依赖安装失败
    exit /b 1
)

echo.
echo =========================================
echo   安装前端依赖...
echo =========================================
cd /d "%WEB_DIR%"
call npm install --silent
if %errorlevel% neq 0 (
    echo 前端依赖安装失败
    exit /b 1
)

echo.
echo =========================================
echo   启动服务
echo   后端:  http://127.0.0.1:8000
echo   前端:  http://127.0.0.1:5173
echo   API文档: http://127.0.0.1:8000/api/v1/docs
echo   关闭后端、Worker 和前端窗口即可停止所有服务
echo =========================================

set PYTHONPATH=%API_DIR%\src;%WORKER_DIR%\src;%PYTHONPATH%
cd /d "%API_DIR%"
start "LTC-API" cmd /c "python -m uvicorn ltc.main:app --host 127.0.0.1 --port 8000 --log-level info"

if not defined LTC_WORKER_QUEUE_NAMES set LTC_WORKER_QUEUE_NAMES=media
cd /d "%ROOT%"
start "LTC-Media-Worker" cmd /c "python -m ltc_worker.main"

cd /d "%WEB_DIR%"
start "LTC-Web" cmd /c "npx vite --host 0.0.0.0 --port 5173"

echo.
echo 服务已启动。
echo.

pause
