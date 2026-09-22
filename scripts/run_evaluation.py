#!/usr/bin/env python
"""Standalone script to execute PlanForge research evaluation & benchmarking suite."""

import sys
from pathlib import Path

# Ensure project root is in sys.path
root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from app.evaluation.runner import main

if __name__ == "__main__":
    main()
