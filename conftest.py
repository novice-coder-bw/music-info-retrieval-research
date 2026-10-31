import sys
from pathlib import Path

# Add repository root to sys.path so tests can import backend, shared, db, etc.
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
