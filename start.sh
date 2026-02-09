#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="prod"
PY="$ROOT/.venv/bin/python"
export PYTHONPATH="$ROOT/backend"

if [[ ! -x "$PY" ]]; then
  echo "venv not found, running install.sh..."
  bash "$ROOT/install.sh"
fi

if [[ "${1:-}" == "--debug" || "${1:-}" == "-d" ]]; then
  MODE="debug"
fi

if [[ "$MODE" == "debug" ]]; then
  export DEEPAGENT_ENV=dev
  export DEEPAGENT_DEBUG=1
  export VITE_DEBUG=true
  (cd "$ROOT/backend" && "$PY" -m uvicorn deepagent.api.main:app --reload) &
  (cd "$ROOT/frontend" && npm run dev) &
  wait
  exit 0
fi

cd "$ROOT/frontend"
npm run build
cd "$ROOT/backend"
export DEEPAGENT_ENV=prod
export DEEPAGENT_DEBUG=0
"$PY" -m uvicorn deepagent.api.main:app &
echo "started"
