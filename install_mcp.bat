@echo off
setlocal enabledelayedexpansion

echo ========================================
echo MCP Servers Installation Script
echo ========================================

set "MCP_DIR=%~dp0mcp_servers"

if not exist "%MCP_DIR%" mkdir "%MCP_DIR%"

echo.
echo [1/3] Checking uv installation...

where uv >nul 2>nul
if errorlevel 1 (
    echo uv not found. Installing uv...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
)

echo.
echo [2/3] Installing mcp-yfinance-server (Free Yahoo Finance data)...

cd /d "%MCP_DIR%"

if exist "mcp-yfinance-server" (
    echo mcp-yfinance-server already exists, skipping clone...
) else (
    echo Cloning mcp-yfinance-server...
    git clone https://github.com/Adity-star/mcp-yfinance-server.git
)

cd mcp-yfinance-server

echo Installing Python dependencies with uv...
uv sync

echo.
echo [3/3] Verifying installation...
uv run python -c "print('Python environment is ready')"

echo.
echo ========================================
echo Installation Complete!
echo ========================================
echo.
echo MCP servers installed in: %MCP_DIR%
echo.
echo Available servers:
echo   - yfinance: Yahoo Finance stock data (free, no API key)
echo     Tools: get_stock_price, analyze_stock, compare_stocks, etc.
echo.
echo To use, run start.bat as usual.
echo The configuration is in: backend\config\mcp_servers.yaml
echo.

cd /d "%~dp0"
pause
