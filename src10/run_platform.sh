#!/bin/sh
# Живой прогон платформы: поднимает бэкенд (свежая БД, in-process шина), выполняет
# переданную команду (по умолчанию — src10/live_protocol.py), затем останавливает стенд.
# Использование:
#   sh src10/run_platform.sh                          # протокол интеграции (LP-01…LP-17)
#   sh src10/run_platform.sh <своя команда...>        # произвольный прогон против живого API
set -e
cd "$(dirname "$0")/.."
ROOT=$(pwd)
PY=${TC_PYTHON:-/tmp/venv/bin/python}
if ! command -v "$PY" >/dev/null 2>&1; then
  if [ -x "$PY" ]; then :; else PY=python3; fi
fi
PORT=${TC_API_PORT:-8000}

rm -f backend/technocontour.db backend/*.db-journal
( cd backend && TC_DATABASE_URL=sqlite:///./technocontour.db TC_BUS_BACKEND=memory \
  "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" > /tmp/tc_uvicorn.log 2>&1 ) &
API_PID=$!
trap 'kill "$API_PID" 2>/dev/null || true' EXIT INT TERM

i=0
until "$PY" -c "import httpx,sys
try: sys.exit(0 if httpx.get('http://127.0.0.1:$PORT/api/v1/core/health',timeout=2).status_code==200 else 1)
except Exception: sys.exit(1)" 2>/dev/null; do
  i=$((i+1))
  if [ "$i" -ge 60 ]; then
    echo "[FAIL] бэкенд не поднялся за 60 с; лог:"; tail -25 /tmp/tc_uvicorn.log; exit 1
  fi
  sleep 1
done
echo "[i] бэкенд жив: http://127.0.0.1:$PORT (pid $API_PID, БД: backend/technocontour.db)"

if [ "$#" -gt 0 ]; then
  TC_API="http://127.0.0.1:$PORT" TC_DB="$ROOT/backend/technocontour.db" "$@"
else
  TC_API="http://127.0.0.1:$PORT" TC_DB="$ROOT/backend/technocontour.db" "$PY" "$ROOT/src10/live_protocol.py"
fi
