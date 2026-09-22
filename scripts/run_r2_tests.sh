#!/usr/bin/env bash
# Development-only. Uses disposable fixture databases; no production connections.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
mkdir -p evidence/r2/local-run
PYTHONPATH="$ROOT/backend${PYTHONPATH:+:$PYTHONPATH}" python -m pytest -q \
  --junitxml=evidence/r2/local-run/pytest.xml | tee evidence/r2/local-run/pytest.log
node --test tests/js/scope.test.mjs | tee evidence/r2/local-run/node.log
python scripts/check_assembly.py --output evidence/r2/local-run/source-assembly.json
printf '\n隔离回归结束。请查看源码齐套结果；测试通过不等于生产放行。\n'
