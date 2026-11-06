"""
main.py: Main entry point for the Banker's Algorithm Resource Management Simulator.

Delegates application execution to app.main().
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure frontend directory is importable
FRONTEND_DIR = Path(__file__).resolve().parent
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from app import main

if __name__ == "__main__":
    main()

