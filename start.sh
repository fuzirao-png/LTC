#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
API_DIR="$ROOT/apps/api"
WORKER_DIR="$ROOT/apps/worker"
WEB_DIR="$ROOT/apps/web"

echo "=== 后端依赖 ==="
python -m pip install -r "$API_DIR/requirements.txt" -r "$WORKER_DIR/requirements.txt" -q

echo "=== 前端依赖 ==="
cd "$WEB_DIR"
if [ -d "node_modules" ]; then
  echo "  (已安装，跳过)"
else
  npm install --silent
fi

echo "=== 启动后端 (http://127.0.0.1:8000) ==="
cd "$API_DIR" && PYTHONPATH="src:${PYTHONPATH:-}" python -m uvicorn ltc.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!

echo "=== 启动会议 Worker ==="
(cd "$ROOT" && exec env LTC_WORKER_QUEUE_NAMES="${LTC_WORKER_QUEUE_NAMES:-media}" \
  PYTHONPATH="$WORKER_DIR/src:$API_DIR/src:${PYTHONPATH:-}" python -m ltc_worker.main) &
WORKER_PID=$!

echo "=== 启动前端 (http://localhost:5173) ==="
cd "$WEB_DIR" && npx vite --host 0.0.0.0 --port 5173 &
WEB_PID=$!

echo ""
echo "  后端:    http://127.0.0.1:8000"
echo "  前端:    http://localhost:5173"
echo "  API文档: http://127.0.0.1:8000/api/v1/docs"
echo "  Ctrl+C 停止"
echo ""

trap "kill $API_PID $WORKER_PID $WEB_PID 2>/dev/null; exit" INT TERM
wait
