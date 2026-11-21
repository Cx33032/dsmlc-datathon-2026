"""Paths and shared constants for the pipeline."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The raw parquet files are NOT committed (dataset may not be redistributed).
# Point DATA_DIR at the folder that holds them; defaults to the repo root.
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT))
OUT = Path(os.environ.get("OUT_DIR", ROOT / "outputs"))
OUT.mkdir(parents=True, exist_ok=True)

DAILY = DATA_DIR / "daily_production.parquet"
JOBS = DATA_DIR / "well_jobs.parquet"
FAILURES = DATA_DIR / "production_failures.parquet"

M3_TO_BBL = 6.2898
# ASSUMPTION: heavy-oil netback in CAD per barrel. Not taken from the data;
# adjust to current WCS-based netback. The dashboard exposes this as a slider.
DEFAULT_NETBACK_CAD_PER_BBL = 50.0

# A well-day counts as "running" when it produced for at least this many hours.
RUNNING_HOURS = 12.0
# Prediction horizon: will a failure-driven outage start within the next H days?
HORIZON_DAYS = 14
# Time-based split (no shuffling across time).
TRAIN_END = "2023-12-31"
VALID_END = "2024-12-31"  # 2024 = early-stopping/validation year; 2025+ = test
