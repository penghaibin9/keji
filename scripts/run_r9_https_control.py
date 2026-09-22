#!/usr/bin/env python3
"""R9 fresh-school HTTPS control; SQLite, not real MySQL/school acceptance."""
from pathlib import Path
from run_r7_https_control import main
if __name__=='__main__':main(Path(__file__).resolve().parents[1]/'evidence/r9/https_control',label='R9')
