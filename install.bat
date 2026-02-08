@echo off
setlocal
set ROOT=%~dp0
cd /d %ROOT%

where python >nul 2>nul
if errorlevel 1 (
  echo Python not found. Install Python 3.10+ first.
  exit /b 1
)

python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e backend

where npm >nul 2>nul
if errorlevel 1 (
  echo npm not found. Install Node.js 18+ first.
  exit /b 1
)

cd /d %ROOT%\frontend
npm install
echo install complete
