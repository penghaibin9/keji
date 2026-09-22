#!/usr/bin/env python3
"""R9 scoped repeatable tests. Historical before-fix XML is NOT release evidence."""
from pathlib import Path
from run_r8_tests import GROUPS as PREVIOUS_GROUPS
from run_r7_tests import main
ROOT=Path(__file__).resolve().parents[1]
GROUPS={**PREVIOUS_GROUPS,
 'r9_sync_integrity':['tests/r2/test_r9_sync_integrity.py'],
 'r9_operations':['tests/r2/test_r9_operations.py'],
}
if __name__=='__main__':raise SystemExit(main(GROUPS,ROOT/'evidence/r9/retest'))
