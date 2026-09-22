#!/usr/bin/env python3
"""R10 real HTTPS synthetic control; SQLite, not MySQL/browser/school acceptance."""
from pathlib import Path
from run_r7_https_control import main
if __name__=='__main__':main(Path(__file__).resolve().parents[1]/'evidence/r10/https_control',label='R10')
