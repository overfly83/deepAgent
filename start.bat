@echo off
setlocal EnableDelayedExpansion

set "ROOT=%~dp0"
set "MODE=prod"
set "VENV_DIR=%ROOT%.venv"
set "PY=%VENV_DIR%\Scripts\python.exe"
set "PYTHONPATH=%ROOT%backend"
set "MCP_SERVERS_DIR=%ROOT%mcp_servers"

:: --- 1. Check & Kill Port 8000 ---
echo [INFO] Checking port 8000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000') do (
    set "PID=%%a"
    echo [WARN] Port 8000 is occupied by PID !PID!. Killing...
    taskkill /F /PID !PID! >nul 2>nul
)

:: --- 2. Auto-Activate Virtual Environment ---
if not exist "%PY%" (
    echo [WARN] Virtual environment not found. Running install.bat...
    call "%ROOT%install.bat"
    if errorlevel 1 exit /b 1
)

:: Activate venv for this session
call "%VENV_DIR%\Scripts\activate.bat"
echo [INFO] Virtual environment activated.

:: --- 3. Parse Arguments ---
if "%1"=="--debug" set MODE=debug
if "%1"=="-d" set MODE=debug

cd /d "%ROOT%"

:: --- 4. Run Application ---
if "%MODE%"=="debug" (
    echo [INFO] Starting in DEBUG mode...
    
    :: Environment Variables
    set DEEPAGENT_ENV=dev
    set DEEPAGENT_DEBUG=1
    set VITE_DEBUG=true
    set PYTHONPATH=%ROOT%backend
    set DEEPAGENT_MCP_SERVERS_DIR=%MCP_SERVERS_DIR%
    
    :: Load vars from backend/.env manually if needed, or rely on python-dotenv in app
    :: But for start /b, we need to make sure the environment is right.
    :: Let's just set the key if we find it in .env to be safe, though python-dotenv should handle it.
    :: Actually, the issue is likely that python-dotenv isn't loading before the model is initialized or
    :: the Zhipu adapter isn't finding it.
    :: We'll add a helper to read .env into current session.
    
    for /f "usebackq tokens=*" %%a in ("%ROOT%backend\.env") do set "%%a"

    :: Start Backend in background (same window)
    echo [INFO] Launching Backend...
    start "DeepAgent Backend" /min "%PY%" -m uvicorn deepagent.api.main:app --host 0.0.0.0 --port 8000 --reload
    
    :: Start Frontend in background (same window)
    echo [INFO] Launching Frontend...
    cd /d "%ROOT%frontend"
    start "DeepAgent Frontend" /min npm run dev
    
    echo [INFO] Services started in background windows.
    echo [INFO] Press any key to stop all services...
    pause >nul
    
    echo [INFO] Stopping services...
    taskkill /F /IM python.exe /FI "WINDOWTITLE eq DeepAgent Backend*" >nul 2>nul
    taskkill /F /IM node.exe >nul 2>nul
    
    :: Fallback port kill just in case
    for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000') do taskkill /F /PID %%a >nul 2>nul
    for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5173') do taskkill /F /PID %%a >nul 2>nul
    
    exit /b 0
)

:: PROD MODE
echo [INFO] Starting in PRODUCTION mode...
echo [INFO] Building frontend...
cd /d "%ROOT%frontend"
call npm run build

echo [INFO] Starting Backend...
cd /d "%ROOT%backend"
set DEEPAGENT_ENV=prod
set DEEPAGENT_DEBUG=0
set PYTHONPATH=%ROOT%backend
set DEEPAGENT_MCP_SERVERS_DIR=%MCP_SERVERS_DIR%

:: Load env vars for prod as well
for /f "usebackq tokens=*" %%a in ("%ROOT%backend\.env") do set "%%a"

"%PY%" -m uvicorn deepagent.api.main:app --host 0.0.0.0 --port 8000 --reload
echo [INFO] Server stopped.
