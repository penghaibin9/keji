#!/usr/bin/env python3
"""R10 scoped regressions. Before-fix logs are historical, not release evidence."""
from pathlib import Path
from run_r9_tests import GROUPS as PREVIOUS_GROUPS
from run_r7_tests import main
ROOT=Path(__file__).resolve().parents[1]
GROUPS={**PREVIOUS_GROUPS,
 'r10_import_access':['tests/r2/test_r10_import_access.py'],
 'r10_org_evidence':['tests/r2/test_r10_org_evidence.py'],
}
if __name__=='__main__':raise SystemExit(main(GROUPS,ROOT/'evidence/r10/retest'))
