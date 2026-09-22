#!/usr/bin/env python3
"""R11 grouped internal regression; not real MySQL or school acceptance."""
from pathlib import Path
from run_r10_tests import GROUPS as PREVIOUS_GROUPS
from run_r7_tests import main
ROOT=Path(__file__).resolve().parents[1]
GROUPS={**PREVIOUS_GROUPS,
    'r11_portal':['tests/r2/test_r11_portal_integration.py'],
    'r11_three_integrations_p2':['tests/r2/test_r11_three_adapter_layer.py','tests/r2/test_r11_three_adapter_p2.py','tests/r2/test_r11_adapter_merge_regressions.py'],
}
if __name__=='__main__':raise SystemExit(main(GROUPS,ROOT/'evidence/r11/retest'))
