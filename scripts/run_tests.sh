#!/usr/bin/env bash
# Runs every automated test in a throwaway environment (own secrets, own data, own database, own server port).
set -euo pipefail
cd "$(dirname "$0")/.."
WORK="$(mktemp -d)"
SERVER_PID=""
cleanup() { [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null || true; rm -rf "$WORK"; }
trap cleanup EXIT

PY="${PYTHON:-python3}"
export JWT_SECRET="$($PY -c 'import secrets;print(secrets.token_urlsafe(48))')"
export SIGNING_MASTER_SECRET="$($PY -c 'import secrets;print(secrets.token_urlsafe(48))')"
export DATABASE_PATH="$WORK/app.db"
export GROUND_TRUTH_DIR="$WORK/data/ground_truth"
export DATA_DIR="$WORK/data"
DEMO_PASSWORD="Demo-$($PY -c 'import secrets;print(secrets.token_urlsafe(9))')"

echo "== 1/3 Python unit and API tests"
$PY -W ignore::ResourceWarning -m unittest discover -s tests -p "test_*.py" -v 2>&1 | tee "$WORK/unit.log" | grep -E "^(Ran|OK|FAILED)|\.\.\. (FAIL|ERROR)" || true
grep -q "^OK" "$WORK/unit.log" || { echo "Python tests failed"; exit 1; }

echo "== 2/3 Generate, validate and load a starter dataset"
$PY -m datagen.generate --scale starter --out "$WORK/data" --validate --check-reproducibility | tail -4
$PY -m app.cli seed --data-dir "$WORK/data" --reset > /dev/null
ACCOUNTS_JSON="$($PY -m app.cli demo-users --json --password "$DEMO_PASSWORD")"
PORT="$($PY -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')"
$PY -m app.cli serve --port "$PORT" > "$WORK/server.log" 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 50); do curl -s "http://127.0.0.1:$PORT/api/health" > /dev/null && break; sleep 0.2; done

echo "== 3/3 Frontend integration tests against the running server"
ACCOUNTS="$($PY -c 'import json,sys;print(json.dumps(json.loads(sys.argv[1])["accounts"]))' "$ACCOUNTS_JSON")" \
BASE_URL="http://127.0.0.1:$PORT" DEMO_PASSWORD="$DEMO_PASSWORD" node tests/frontend_smoke.mjs | tail -4
if grep -q " 500 " "$WORK/server.log"; then echo "Server logged HTTP 500 responses"; exit 1; fi
echo "All test stages passed."
