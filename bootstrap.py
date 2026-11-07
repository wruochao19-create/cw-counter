"""Local dependency path only; no downloads and no game access."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
if sys.prefix == sys.base_prefix:
    sys.path.insert(0, str(ROOT / '.deps'))  # Compatibility with the original local installation.

