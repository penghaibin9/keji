#!/usr/bin/env bash
set -euo pipefail
[[ $# -ge 3 ]] || { echo '用法: bash scripts/run_performance_acceptance.sh https://学校预发布地址 /安全路径/perf-users.csv /证据/performance.json [额外参数...]'; exit 2; }
BASE=$1; USERS=$2; OUT=$3; shift 3
[[ -f "$USERS" ]] || { echo '找不到测试账号CSV'; exit 2; }
python3 scripts/performance_acceptance.py --base-url "$BASE" --users-csv "$USERS" --output "$OUT" "$@"
