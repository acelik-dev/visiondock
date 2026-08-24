#!/bin/bash
set -euo pipefail

cd /home/site/wwwroot

PORT="${PORT:-8000}"
WORKERS="${WEB_CONCURRENCY:-1}"

echo "[startup] cwd=$(pwd) PORT=$PORT workers=$WORKERS"
echo "[startup] python=$(command -v python3 || command -v python)"
python3 -c "import sys; print('[startup] version', sys.version)" || true

if [ -d ./antenv ]; then
  # shellcheck source=/dev/null
  source ./antenv/bin/activate
  echo "[startup] activated Oryx venv: ./antenv"
fi

# Oryx may run from a different cwd; use absolute path
STARTUP_DIR="/home/site/wwwroot"
cd "$STARTUP_DIR"

exec gunicorn main:app \
  --workers "$WORKERS" \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind "0.0.0.0:${PORT}" \
  --timeout 600 \
  --access-logfile - \
  --error-logfile - \
  --log-level info
