#!/bin/sh
# Стенд бэкенда для E2E/протоколов: свежая SQLite-база → детерминированный seed → uvicorn.
# Используется Playwright webServer (TC_WITH_BACKEND=1) и src10/run_platform.sh.
# Переменные: TC_PYTHON (путь к python с зависимостями backend), TC_API_PORT (по умолчанию 8000).
set -e
cd "$(dirname "$0")/.."
PY=${TC_PYTHON:-/tmp/venv/bin/python}
if ! command -v "$PY" >/dev/null 2>&1; then
  if [ -x "$PY" ]; then :; else PY=python3; fi
fi
PORT=${TC_API_PORT:-8000}

# Обязательно убираем УСТАРЕВШИЕ экземпляры стенда: старый uvicorn удерживает порт и
# удалённый файл БД; новый стенд тогда молча не стартует, а health отвечает из старого
# процесса (дефект диагностики 25.10.2026). Защита от самоубийства: не трогаем собственное
# дерево процессов (SELF + PPID) и матчим только реальные раннеры python/bash c uvicorn-cmdline.
SELF=$(cat /proc/self/stat | awk '{print $1}')
PAR=$PPID
for p in /proc/[0-9]*; do
  pid=${p#/proc/}
  [ "$pid" = "$SELF" ] && continue
  [ "$pid" = "$PAR" ] && continue
  exe=$(readlink "$p/exe" 2>/dev/null || true)
  cmd=$(tr '\0' ' ' < "$p/cmdline" 2>/dev/null || true)
  case "$cmd" in
    *"-m uvicorn app.main:app"*) ;;
    *) continue ;;
  esac
  case "$exe" in
    *python*|*bash*|*/sh*|*dash*) kill -9 "$pid" 2>/dev/null || true ;;
  esac
done
sleep 1

rm -f backend/technocontour.db backend/*.db-journal
cd backend
TC_DATABASE_URL=sqlite:///./technocontour.db TC_BUS_BACKEND=memory \
  exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
