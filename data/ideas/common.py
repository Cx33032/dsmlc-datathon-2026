"""Shared paths, cleaning rules, price assumptions and plot style for all idea scripts.

Every script does:  sys.path.insert(0, <data/ideas>); import common
"""
from pathlib import Path
import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
DAILY = (DATA / "daily_production.parquet").as_posix()
JOBS = (DATA / "well_jobs.parquet").as_posix()
FAILS = (DATA / "production_failures.parquet").as_posix()
DOCS_IDEAS = ROOT / "docs" / "ideas"

# ------------------------------------------------------------------ price assumptions (cited in idea.md)
# WTI: $83.45 USD/bbl, OilPriceAPI table for 2026-11-19 (https://www.oilpriceapi.com/live/wcs-crude-oil-price)
# WCS Hardisty Dec-26 differential: -$26.20 USD/bbl, CalRock via Reuters, 2026-11-13
#   (https://boereport.com/2026/11/13/discount-on-western-canada-select-narrows-55/)
# USD/CAD: 1.4325, Bank of Canada, 2026-11-20 (https://www.bankofcanada.ca/rates/exchange/daily-exchange-rates/)
WTI_USD = 83.45
WCS_DIFF_USD = -26.20
USDCAD = 1.4325
BBL_PER_M3 = 6.2898
WCS_USD = WTI_USD + WCS_DIFF_USD                      # 57.25 USD/bbl
WCS_CAD_BBL = WCS_USD * USDCAD                        # ~82.0 CAD/bbl
WCS_CAD_M3 = WCS_CAD_BBL * BBL_PER_M3                 # ~516 CAD/m3
# Field-gate netback haircut: wellhead heavy oil sells below Hardisty WCS (transport, blending/diluent,
# quality). We apply 15% as an explicit, adjustable assumption [unverified - no Strathcona netback given].
NETBACK_HAIRCUT = 0.15
OIL_CAD_M3 = WCS_CAD_M3 * (1 - NETBACK_HAIRCUT)       # ~438 CAD/m3 used for lost-revenue valuation

# ------------------------------------------------------------------ sensor cleaning rules (from 00_profiling)
# Applied as SQL expressions: placeholder/sentinel or physically implausible values -> NULL
CLEAN = {
    "tq": "case when pcp_pump_rod_torque_ftlb between 1 and 20000 then pcp_pump_rod_torque_ftlb end",
    "cur": "case when pcp_pump_electric_current_a between 1 and 1000 then pcp_pump_electric_current_a end",
    "rpm": "case when pcp_pump_rpm::double between 1 and 1000 then pcp_pump_rpm::double end",
    "eff": "case when pump_efficiency_pct between 0 and 3 then pump_efficiency_pct end",
    "tbg": "case when tubing_pressure_kpa between 0 and 20000 then tubing_pressure_kpa end",
    "csg": "case when casing_pressure_kpa between 0 and 20000 then casing_pressure_kpa end",
    "oil": "case when oil_produced_m3 >= 0 then oil_produced_m3 end",
    "wat": "case when water_produced_m3 >= 0 then water_produced_m3 end",
}
FAIL_LOG_START = "2025-06-01"   # failure log is complete only from Jun 2025 (see 00_data_quality.md)
DATA_END = "2026-10-27"


def con():
    c = duckdb.connect()
    c.execute("SET memory_limit='6GB'")
    return c


def style():
    plt.rcParams.update({
        "figure.figsize": (10, 5.6), "figure.dpi": 110, "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.alpha": 0.25, "axes.titlesize": 12.5, "axes.titleweight": "bold",
        "axes.labelsize": 11, "font.size": 10.5, "savefig.bbox": "tight",
    })


C1, C2, C3, C4, GREY = "#1f5f8b", "#d9822b", "#3a9d5d", "#b5443b", "#8c8c8c"


def save(fig, idea_dir, name):
    out = DOCS_IDEAS / idea_dir / "assets"
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / name)
    plt.close(fig)
    print(f"  chart -> {(out / name).relative_to(ROOT)}")
