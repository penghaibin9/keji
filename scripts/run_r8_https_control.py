#!/usr/bin/env python3
"""R8 fresh-school HTTPS control; SQLite only, not a production release gate."""
from pathlib import Path
from run_r7_https_control import main
if __name__=='__main__':
    main(Path(__file__).resolve().parents[1]/'evidence/r8/https_control',label='R8')
