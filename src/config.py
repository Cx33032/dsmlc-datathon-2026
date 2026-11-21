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

M3_TO_BBL = 6.28981
# ------------------------------------------------------------------ one central oil price
# Same derivation as data/ideas/common.py (sources cited there): WTI 83.45 USD/bbl, WCS Hardisty
# differential -26.20 USD/bbl, USD/CAD 1.4325, then a 15% field-gate haircut (our own assumption,
# no Strathcona netback was given). = C$69.7/bbl = C$438.5/m3. Every $ figure in the app is
# recomputed from the sidebar price slider, which defaults to this value.
WTI_USD, WCS_DIFF_USD, USDCAD, NETBACK_HAIRCUT = 83.45, -26.20, 1.4325, 0.15
WCS_CAD_BBL = (WTI_USD + WCS_DIFF_USD) * USDCAD
DEFAULT_NETBACK_CAD_PER_BBL = round(WCS_CAD_BBL * (1 - NETBACK_HAIRCUT), 2)      # 69.71
OIL_CAD_M3 = DEFAULT_NETBACK_CAD_PER_BBL * M3_TO_BBL                              # 438.5
# Price scenarios used by the original Dispatch report (C$/bbl), kept for the Evidence page
DISPATCH_PRICE_SCENARIOS = (20.0, 35.0, 50.0)

# Unit costs (CAD). Rod economics come from Idea 1's artifacts (economics.json); these are
# assumptions that are not in the data.
SECTION_COST_SAVING = 0.40      # section replacement costs 40% less than a full string (assumption)
INSPECTION_COST_CAD = 300.0     # one diagnostic visit / check (assumption)

# A well-day counts as "running" when it produced for at least this many hours.
RUNNING_HOURS = 12.0
# Prediction horizon: will a failure-driven outage start within the next H days?
HORIZON_DAYS = 14
# Time-based split (no shuffling across time).
TRAIN_END = "2023-12-31"
VALID_END = "2024-12-31"  # 2024 = early-stopping/validation year; 2025+ = test

# Dispatch queue (reconstructed from the team's "Dispatch by the Barrel" spec)
DISPATCH_TRAIN_END = "2025-12-28"
DISPATCH_TEST_START, DISPATCH_TEST_END = "2026-01-01", "2026-10-23"
DISPATCH_SHRINK = 40.0
DISPATCH_HORIZON_D = 3
HEALTHY_HOURS = 22.0            # uptime hours for a day to count toward a "healthy" rate baseline
