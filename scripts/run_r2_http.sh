#!/usr/bin/env bash
# Starts a NEW synthetic SQLite lab on loopback only. Never resets any database.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
python - <<'PY'
import socket
with socket.socket() as s:
    try:s.bind(('127.0.0.1',8768))
    except OSError:raise SystemExit('8768端口正在使用；拒绝替换现有进程。')
PY
LAB=$(mktemp -d /tmp/nd-r2-test-http-XXXXXX)
mkdir -p evidence/r2/local-run
python tests/r2/browser_lab.py "$LAB" > evidence/r2/local-run/http-server.log 2>&1 &
SERVER=$!
cleanup(){ kill -TERM "$SERVER" 2>/dev/null || true; wait "$SERVER" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
python - <<'PY'
import time,httpx
for _ in range(60):
    try:
        if httpx.get('http://127.0.0.1:8768/',timeout=1).status_code==200:break
    except httpx.RequestError:pass
    time.sleep(.25)
else:raise SystemExit('隔离服务未就绪，请查看http-server.log。')
PY
python tests/r2/http_flows.py | tee evidence/r2/local-run/http-flow.log
printf '\n隔离样本保留在%s，不是学校业务数据；不随交付包发布。\n' "$LAB"
