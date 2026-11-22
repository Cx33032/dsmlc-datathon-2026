"""Build every artifact the app reads. The app never touches the raw data.

  python build_artifacts.py --data-dir <folder with the 3 parquets> --out-dir outputs
  python build_artifacts.py --demo                      # synthetic data -> demo_data/ + outputs_demo/

Steps
  1. run_pipeline.py      cleaning, lost-oil tables, failure early-warning model, dispatch queue + replay
  2. Idea 1               rod replace-vs-repair (Cox, program, sensitivity)        -> <out>/ideas/1
  3. Idea 5               break depths from crew text, repeat-depth permutation    -> <out>/ideas/5
  4. Whiplash             mechanical shock index + tests                           -> <out>/ideas/whiplash
  5. recommendations      decision rule per well (as of data end) and per dispatch ticket (as of ticket day)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IDEA_SCRIPTS = [("1", ROOT / "analysis/1/rod_replace_analysis.py"),
                ("5", ROOT / "analysis/5/break_depth_mining.py"),
                ("whiplash", ROOT / "analysis/whiplash/shock_index.py")]


def run(cmd: list[str], env: dict, label: str):
    t0 = time.time()
    print(f"[build] {label} ...", flush=True)
    r = subprocess.run(cmd, env=env, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(r.stdout[-3000:], r.stderr[-3000:], sep="\n")
        raise SystemExit(f"[build] {label} failed")
    print(f"[build] {label} done in {time.time() - t0:.0f}s", flush=True)


def build_recommendations(out: Path, data_end: str):
    import pandas as pd

    sys.path.insert(0, str(ROOT))
    from src.rules import evidence_for, headline, recommend
    from src.dispatch import ROD_PUMP

    ideas = out / "ideas"
    rod = pd.read_parquet(ideas / "1" / "rod_events.parquet")
    rod["s"] = pd.to_datetime(rod["s"])
    br = pd.read_csv(ideas / "5" / "located_breaks.csv", parse_dates=["fd"],
                     usecols=["uwi", "fd", "area", "cause", "depth_m", "depth_source", "kw_pitting", "kw_corrosion"])
    asof = pd.Timestamp(data_end) + pd.Timedelta(days=1)
    wells = sorted(set(rod["uwi"]) | set(br["uwi"]))
    rows = []
    for u in wells:
        acts = recommend(evidence_for(u, asof, rod, br))
        rows.append({"uwi": u, "headline": headline(acts),
                     **{f"{a.kind}_status": a.status for a in acts}, **{f"{a.kind}_text": a.text for a in acts},
                     **{f"{a.kind}_evidence": a.evidence for a in acts}})
    pd.DataFrame(rows).to_parquet(out / "recommendations.parquet", index=False)

    # dispatch tickets: chronic flag + rod repairs in 365 d as of the ticket day (strictly before it)
    t = pd.read_parquet(out / "dispatch_tickets.parquet")
    rep = rod[rod["is_replace"] == 0].groupby("uwi")["s"].apply(lambda s: s.sort_values().to_numpy()).to_dict()
    new = rod[rod["is_replace"] == 1].groupby("uwi")["s"].apply(lambda s: s.sort_values().to_numpy()).to_dict()
    import numpy as np

    def count(arr, d):
        if arr is None:
            return 0
        d = np.datetime64(d)
        return int(((arr < d) & (arr >= d - np.timedelta64(365, "D"))).sum())

    t["rod_repairs_365"] = [count(rep.get(u), d) for u, d in zip(t["uwi"], t["production_date"])]
    t["new_string_365"] = [count(new.get(u), d) > 0 for u, d in zip(t["uwi"], t["production_date"])]
    t["chronic"] = (t["rod_repairs_365"] >= 3) & ~t["new_string_365"]
    heads = []
    for r in t.itertuples():
        if r.chronic and r.loss_category in ROD_PUMP:
            heads.append(headline(recommend(evidence_for(r.uwi, r.production_date, rod, br))))
        else:
            heads.append("")
    t["pull_recommendation"] = heads
    t.to_parquet(out / "dispatch_tickets.parquet", index=False)
    print(f"[build] recommendations: {len(rows)} wells, {int(t['chronic'].sum())} chronic tickets")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default=os.environ.get("DATA_DIR", str(ROOT)))
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--demo", action="store_true", help="generate synthetic data and build the demo artifacts")
    ap.add_argument("--skip-pipeline", action="store_true")
    ap.add_argument("--only", nargs="*", help="subset of: pipeline 1 5 whiplash recs")
    a = ap.parse_args()

    if a.demo:
        from src.demo import generate
        data_dir = ROOT / "demo_data"
        generate(data_dir)
        out = Path(a.out_dir or ROOT / "outputs_demo")
    else:
        data_dir = Path(a.data_dir)
        out = Path(a.out_dir or ROOT / "outputs")
        if not (data_dir / "daily_production.parquet").exists():
            raise SystemExit(f"no daily_production.parquet in {data_dir}; pass --data-dir or use --demo")
    out.mkdir(parents=True, exist_ok=True)
    only = set(a.only or ["pipeline", "1", "5", "whiplash", "recs"])
    if a.skip_pipeline:
        only.discard("pipeline")
    env = {**os.environ, "DATA_DIR": str(data_dir), "OUT_DIR": str(out), "IDEAS_OUT": str(out / "ideas"),
           "IDEAS_NO_CHARTS": "1", "PYTHONIOENCODING": "utf-8"}
    if a.demo:
        env["DEMO_MODE"] = "1"
    py = sys.executable
    if "pipeline" in only:
        run([py, "run_pipeline.py"], env, "pipeline")
    for key, script in IDEA_SCRIPTS:
        if key in only and script.exists():
            run([py, str(script)], env, f"idea {key}")
    if "recs" in only:
        import pandas as pd
        data_end = str(pd.read_parquet(out / "risk_scores.parquet", columns=["production_date"])
                       ["production_date"].max().date())
        build_recommendations(out, data_end)
    (out / "build_info.json").write_text(json.dumps({"built": time.strftime("%Y-%m-%d %H:%M"), "demo": a.demo,
                                                     "steps": sorted(only)}, indent=2))
    print(f"[build] artifacts -> {out}")


if __name__ == "__main__":
    main()
