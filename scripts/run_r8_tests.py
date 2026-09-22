#!/usr/bin/env python3
"""R8 repeatable groups. --group r8_runtime reruns only that group after interruption."""
from pathlib import Path
from run_r7_tests import GROUPS as PREVIOUS_GROUPS, main
ROOT=Path(__file__).resolve().parents[1]
GROUPS={**PREVIOUS_GROUPS,
 'r8_sync_hr':['tests/r2/test_r8_regressions.py'],
 'r8_runtime':['tests/r2/test_r8_runtime_boundaries.py'],
 'r8_recovery':['tests/r2/test_r8_recovery_and_consistency.py'],
}
if __name__=='__main__':
    raise SystemExit(main(GROUPS,ROOT/'evidence/r8/retest'))
