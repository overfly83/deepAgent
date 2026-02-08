@echo off
setlocal
set ROOT=%~dp0
set MODE=prod
set PY=%ROOT%\.venv\Scripts\python.exe
set PYTHONPATH=%ROOT%backend

if not exist "%PY%" (
  echo venv not found, running install.bat...
  call "%ROOT%install.bat"
)

if "%1"=="--debug" set MODE=debug
if "%1"=="-d" set MODE=debug

cd /d %ROOT%

if "%MODE%"=="debug" (
  set DEEPAGENT_ENV=dev
  set DEEPAGENT_DEBUG=1
  set VITE_DEBUG=true
  start "DeepAgent Backend" cmd /k "cd /d %ROOT%backend && set PYTHONPATH=%PYTHONPATH% && \"%PY%\" -m uvicorn deepagent.main:app --reload"
  start "DeepAgent Frontend" cmd /k "cd /d %ROOT%frontend && npm run dev"
  exit /b 0
)

cd /d %ROOT%frontend
call npm run build
cd /d %ROOT%backend
set DEEPAGENT_ENV=prod
set DEEPAGENT_DEBUG=0
call start "DeepAgent Backend" cmd /k "cd /d %ROOT%backend && set PYTHONPATH=%PYTHONPATH% && \"%PY%\" -m uvicorn deepagent.main:app"
echo started
