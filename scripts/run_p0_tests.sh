#!/usr/bin/env bash
# No production database, Docker or external school API is contacted by these tests.
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"
command -v node >/dev/null
command -v openssl >/dev/null
mkdir -p evidence/current
python3 scripts/check_assembly.py --output evidence/current/source_assembly.json > /dev/null
python3 -m pytest -q --junitxml=evidence/current/pytest.xml 2>&1 | tee evidence/current/pytest.log
node --test tests/js/scope.test.mjs 2>&1 | tee evidence/current/node-tests.tap
python3 -m compileall -q backend scripts
for script in scripts/*.sh; do bash -n "$script"; done
node --input-type=module --check < frontend/app.js
node --input-type=module --check < frontend/scope.js
printf '\n模块级测试完成；完整工程、真实MySQL、Docker、四角色浏览器和学校采购验收仍须另行验证。\n'
