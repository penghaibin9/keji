#!/usr/bin/env python3
"""R11 HTTPS full canonical empty-school control; not MySQL/browser acceptance."""
from pathlib import Path
from run_r7_https_control import main
if __name__=='__main__':main(Path(__file__).resolve().parents[1]/'evidence/r11/https_control',label='R11')
