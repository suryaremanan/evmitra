"""Vercel entrypoint for EV Mitra FastAPI backend."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

# src/backend.py uses top-level imports like `from core.config import ...`.
# Add src/ to import path so those imports resolve in Vercel runtime.
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import app  # noqa: E402,F401
