#!/usr/bin/env bash
# Starts the API (port 8000) and the web app (port 5173). Ctrl-C stops both.
set -e
cd "$(dirname "$0")"

# the API reads OPENAI_API_KEY and friends from .env or your shell
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

[ -d web/node_modules ] || npm install --prefix web

pids=()
cleanup() {
  trap - INT TERM EXIT
  kill "${pids[@]}" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

uv run --directory backend uvicorn app.main:app --reload --port 8000 &
pids+=($!)
npm run dev --prefix web -- --port 5173 --strictPort &
pids+=($!)

echo
echo "API: http://localhost:8000    Web: http://localhost:5173"
echo

# exit as soon as either server dies
while kill -0 "${pids[@]}" 2>/dev/null; do
  sleep 1
done
