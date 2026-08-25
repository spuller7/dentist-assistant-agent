"""
FILE: src/paths.py
WHY: One place for folder locations. The working database can be pointed at a
     temp file during evals so demo bookings are not left in the seed data.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
SEED_DB = DATA_DIR / "office.seed.json"
DEFAULT_DB = DATA_DIR / "office.json"


def db_path() -> Path:
    override = os.environ.get("OFFICE_DB_PATH")
    return Path(override) if override else DEFAULT_DB
