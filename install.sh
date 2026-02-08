#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

command -v python3 >/dev/null 2>&1 || { echo "Python3 not found. Install Python 3.10+ first."; exit 1; }
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e backend

command -v npm >/dev/null 2>&1 || { echo "npm not found. Install Node.js 18+ first."; exit 1; }
cd "$ROOT/frontend"
npm install
echo "install complete"
