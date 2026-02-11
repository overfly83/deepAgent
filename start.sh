#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="prod"
VENV_DIR="$ROOT/.venv"
PY="$VENV_DIR/bin/python"
export PYTHONPATH="$ROOT/backend"

# --- 1. Check & Kill Port 8000 ---
echo "[INFO] Checking port 8000..."
PID=$(lsof -t -i:8000 || true)
if [[ -n "$PID" ]]; then
    echo "[WARN] Port 8000 is occupied by PID $PID. Killing..."
    kill -9 "$PID"
fi

# --- 2. Auto-Activate Virtual Environment ---
if [[ ! -x "$PY" ]]; then
  echo "[WARN] Virtual environment not found. Running install.sh..."
  bash "$ROOT/install.sh"
  if [[ $? -ne 0 ]]; then exit 1; fi
fi

source "$VENV_DIR/bin/activate"
echo "[INFO] Virtual environment activated."

# --- 3. Parse Arguments ---
if [[ "${1:-}" == "--debug" || "${1:-}" == "-d" ]]; then
  MODE="debug"
fi

# --- 4. Run Application ---
if [[ "$MODE" == "debug" ]]; then
  echo "[INFO] Starting in DEBUG mode..."
  export DEEPAGENT_ENV=dev
  export DEEPAGENT_DEBUG=1
  export VITE_DEBUG=true

  echo "[INFO] Launching Backend..."
  (cd "$ROOT/backend" && "$PY" -m uvicorn deepagent.api.main:app --host 0.0.0.0 --port 8000 --reload) &
  
  echo "[INFO] Launching Frontend..."
  (cd "$ROOT/frontend" && npm run dev) &
  
  echo "[INFO] Services started. Press Ctrl+C to stop."
  wait
  exit 0
fi

# PROD MODE
echo "[INFO] Starting in PRODUCTION mode..."
echo "[INFO] Building frontend..."
cd "$ROOT/frontend"
npm run build

echo "[INFO] Starting Backend..."
cd "$ROOT/backend"
export DEEPAGENT_ENV=prod
export DEEPAGENT_DEBUG=0

"$PY" -m uvicorn deepagent.api.main:app --host 0.0.0.0 --port 8000 &
echo "[INFO] Server started in background."
