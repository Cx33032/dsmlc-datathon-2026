"""Idea 5 - Where do strings break? Mining crew free text for break depth and corrosion evidence.

Run:  python data/ideas/5/break_depth_mining.py
Outputs: data/ideas/5/out/results.txt, data/ideas/5/out/located_breaks.csv, charts in docs/ideas/5/assets/

Sources of text:
  production_failures.failure_comments  e.g. "Broken corod @ 247m", "Broken Pin on JT #31", "Broken stick rod 48th"
  well_jobs.summary (Rod Truck / Workover jobs linked to a failure within -3..+14 d)
      e.g. "... corod to break 639m ... very little minor pitting ..."
Depth rules:
  explicit metres ("@ 247m", "at 385", "break 639m")                 -> depth_m
  joint / rod number on STICK rods ("JT #31", "48th", "joint 87")    -> joint x 7.62 m (25 ft API rod, assumption)
Only rod failures are used. Depths outside 10-1,200 m are discarded as parsing noise.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common as cm
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)
IDEA = "5"
con = cm.con()
cm.style()
lines = []
ROD_M = 7.62   # 25 ft API 11B rod length


def emit(t, obj):
    s = f"\n### {t}\n{obj if isinstance(obj, str) else obj.to_string()}\n"
    print(s)
    lines.append(s)


NOT_DEPTH = r"(?!\s*,?\d)(?!\s*(?:k\b|lbs?|#|ft|rpm|kpa|psi|\"|%|mm|in\b))"
UNIT_M = r"\s*(?:m|mtrs?|meters?|metres?)\b"
# failure_comments are short ("Broken corod @ 247m", "Parted at 385"): unit optional after @/at
DEPTH_RE = [re.compile(r"(?:@|\bat\b)\s*(?:approx\.?\s*|~\s*)?(\d{2,4}(?:\.\d+)?)" + NOT_DEPTH, re.I),
            re.compile(r"\b(\d{2,4}(?:\.\d+)?)" + UNIT_M, re.I)]
# job summaries are long and full of pull weights ("free at 15,000lbs"): require a break word AND a metre unit
SUMMARY_RE = [re.compile(r"(?:broken|break|broke|parted)\b[^.@\d]{0,30}(?:@|\bat\b)\s*(\d{2,4}(?:\.\d+)?)" + UNIT_M, re.I)]
NARR_CAUSE_RE = re.compile(r"due to\s+(?:the\s+)?(pitting|corrosion|stress|wear|fatigue|torque|sand|abrasion|erosion)", re.I)
JOINT_RE = [
    re.compile(r"\b(?:jt|jts|joint|rod)\s*#?\s*(\d{1,3})\b", re.I),
    re.compile(r"#\s*(\d{1,3})\b"),
    re.compile(r"\b(\d{1,3})(?:st|nd|rd|th)\b", re.I),
]
KEYWORDS = {
    "pitting": r"\bpit(?:s|ted|ting)?\b",
    "corrosion": r"corro|\brust",
    "wear": r"\bwor[en]\b|\bwear|\bwore\b",
    "sand": r"\bsand",
    "wax_paraffin": r"\bwax|paraffin",
    "fatigue_stress": r"fatigue|stress",
    "guides_centralizers": r"\bguide|centrali[sz]",
}


def first_num(regs, text, lo, hi):
    if not isinstance(text, str):
        return np.nan
    for r in regs:
        for m in r.finditer(text):
            v = float(m.group(1))
            if lo <= v <= hi:
                return v
    return np.nan


def is_stick(*texts):
    t = " ".join(x for x in texts if isinstance(x, str)).lower()
    return ("stick" in t or "sucker" in t) and "corod" not in t


# ------------------------------------------------------------------ load
f = con.sql(f"""select row_number() over (order by uwi, failure_start_date) fid, uwi, field_operating_area area,
  failure_start_date::date fd, failure_type, cause, failure_detail, failure_comments
  from '{cm.FAILS}' where failure_type='Rods'""").df()
con.register("f", f)
summ = con.sql(f"""select f.fid, string_agg(j.summary, ' || ') summ
  from f join '{cm.JOBS}' j on j.uwi=f.uwi and j.job_category in ('Rod Truck','Workover')
   and j.start_date between f.fd - interval 3 day and f.fd + interval 14 day and j.summary is not null
  group by 1""").df()
f = f.merge(summ, on="fid", how="left")

# ------------------------------------------------------------------ parse
f["depth_comment_m"] = f.failure_comments.apply(lambda t: first_num(DEPTH_RE, t, 10, 1200))
f["joint_comment"] = f.failure_comments.apply(lambda t: first_num(JOINT_RE, t, 1, 200))
f["depth_summary_m"] = f.summ.apply(lambda t: first_num(SUMMARY_RE, t, 10, 1200))
f["narr_cause"] = f.summ.apply(lambda t: (NARR_CAUSE_RE.search(t).group(1).lower() if isinstance(t, str) and NARR_CAUSE_RE.search(t) else None))
f["stick"] = [is_stick(a, b) for a, b in zip(f.failure_detail, f.failure_comments)]
f["depth_m"] = f.depth_comment_m
src = np.where(f.depth_m.notna(), "comment_m", None)
m = f.depth_m.isna() & f.joint_comment.notna() & f.stick
f.loc[m, "depth_m"] = f.loc[m, "joint_comment"] * ROD_M
src = np.where(m, "comment_joint_x7.62", src)
m2 = f.depth_m.isna() & f.depth_summary_m.notna()
f.loc[m2, "depth_m"] = f.loc[m2, "depth_summary_m"]
src = np.where(m2, "job_summary_m", src)
f["depth_source"] = src
for k, pat in KEYWORDS.items():
    f[f"kw_{k}"] = f.summ.fillna("").str.contains(pat, flags=re.I, regex=True)

emit("Coverage (rod failures in failure log)", pd.Series({
    "rod_failures": len(f), "with_comment": int(f.failure_comments.notna().sum()),
    "with_linked_job_summary": int(f.summ.notna().sum()),
    "located_total": int(f.depth_m.notna().sum()), "located_pct": round(100 * f.depth_m.notna().mean(), 1),
    "wells_with_located_break": int(f[f.depth_m.notna()].uwi.nunique())}))
emit("Depth source counts", f.depth_source.value_counts(dropna=False))
emit("Located break depth (m) by cause", f[f.depth_m.notna()].groupby("cause").depth_m.describe().round(0))

# ------------------------------------------------------------------ hand-check sample (for the reviewer: are we parsing right?)
samp = f[f.depth_m.notna()].sample(15, random_state=3)[["failure_comments", "depth_source", "depth_m"]]
emit("Random sample of parsed rows (manual check)", samp.to_string(index=False))

# ------------------------------------------------------------------ do breaks repeat at the same depth on a well?
loc = f[f.depth_m.notna()].sort_values(["uwi", "fd"]).copy()
loc["prev_depth"] = loc.groupby("uwi").depth_m.shift()
loc["prev_fd"] = loc.groupby("uwi").fd.shift()
# drop pairs logged < 7 days apart: those can be duplicate records of one event (profile found 9 duplicate failures)
pairs = loc[loc.prev_depth.notna() & ((pd.to_datetime(loc.fd) - pd.to_datetime(loc.prev_fd)).dt.days >= 7)].copy()
pairs["days_apart"] = (pd.to_datetime(pairs.fd) - pd.to_datetime(pairs.prev_fd)).dt.days
pairs["gap_m"] = (pairs.depth_m - pairs.prev_depth).abs()
# baseline: pair each break with a random located break from a DIFFERENT well in the same area (1,000 permutations)
rng = np.random.default_rng(42)
by_area = {a: g[["uwi", "depth_m"]].values for a, g in loc.groupby("area")}
perm_share = []
for _ in range(1000):
    gaps = []
    for r in pairs.itertuples():
        pool = by_area[r.area]
        pool = pool[pool[:, 0] != r.uwi]
        if len(pool):
            gaps.append(abs(r.prev_depth - pool[rng.integers(len(pool)), 1]))
    perm_share.append(np.mean(np.array(gaps) <= 50))
obs = (pairs.gap_m <= 50).mean()
emit("Consecutive located breaks on the same well", pd.Series({
    "pairs": len(pairs), "wells": pairs.uwi.nunique(), "median_days_apart": pairs.days_apart.median(),
    "median_gap_m": pairs.gap_m.median(),
    "share_within_50m": obs, "share_within_100m": (pairs.gap_m <= 100).mean(),
    "baseline_share_within_50m_mean": np.mean(perm_share), "baseline_p95": np.percentile(perm_share, 95),
    "lift_vs_baseline": obs / np.mean(perm_share),
    "perm_p_value": (np.sum(np.array(perm_share) >= obs) + 1) / (len(perm_share) + 1)}).round(4))

# ------------------------------------------------------------------ narrative evidence vs coded cause
lk = f[f.summ.notna() & f.cause.isin(["Fatigue", "Corrosion", "Load / Excess Stress", "Erosion"])]
kw = lk.groupby("cause")[[c for c in lk.columns if c.startswith("kw_")]].mean().mul(100).round(1)
kw["n_linked"] = lk.groupby("cause").size()
emit("% of linked crew narratives mentioning each keyword, by coded cause", kw)
fat = lk[lk.cause == "Fatigue"]
emit("Fatigue-coded rod failures whose crew narrative mentions pitting or corrosion", pd.Series({
    "fatigue_linked": len(fat), "mention_pitting_or_corrosion": int((fat.kw_pitting | fat.kw_corrosion).sum()),
    "pct": round(100 * (fat.kw_pitting | fat.kw_corrosion).mean(), 1)}))

nc = f[f.narr_cause.notna() & f.cause.notna()]
ct = pd.crosstab(nc.cause, nc.narr_cause)
ct = ct.loc[ct.sum(axis=1) >= 10]
emit("Crew-stated cause ('... due to X') vs coded cause (rod failures with both)", ct)
emit("Agreement summary", pd.Series({
    "with_narrative_cause": len(nc),
    "fatigue_coded": int((nc.cause == "Fatigue").sum()),
    "fatigue_coded_but_crew_says_pitting_or_corrosion": int(((nc.cause == "Fatigue") & nc.narr_cause.isin(["pitting", "corrosion"])).sum()),
    "corrosion_coded_but_crew_says_stress_or_fatigue": int(((nc.cause == "Corrosion") & nc.narr_cause.isin(["stress", "fatigue"])).sum()),
    "corrosion_coded": int((nc.cause == "Corrosion").sum())}))

# ------------------------------------------------------------------ chronic wells (idea 1 list) and their break bands
chronic_path = Path(__file__).resolve().parents[1] / "1" / "out" / "chronic_wells.csv"
if chronic_path.exists():
    ch = pd.read_csv(chronic_path)
    cl = loc[loc.uwi.isin(ch.uwi)]
    per = cl.groupby("uwi").depth_m.agg(["count", "min", "max", "median"])
    per["band_m"] = per["max"] - per["min"]
    per2 = per[per["count"] >= 2]
    emit("Idea-1 program wells with located breaks", pd.Series({
        "program_wells": len(ch), "with_any_located_break": int(cl.uwi.nunique()), "with_2plus": len(per2),
        "median_band_m_2plus": per2.band_m.median(), "share_band_le_150m": (per2.band_m <= 150).mean()}).round(3))
    fat_ch = f[f.uwi.isin(ch.uwi) & (f.cause == "Fatigue") & f.summ.notna()]
    emit("Program wells: Fatigue-coded failures with pitting/corrosion in narrative", pd.Series({
        "n": len(fat_ch), "pct_mention": round(100 * (fat_ch.kw_pitting | fat_ch.kw_corrosion).mean(), 1),
        "wells_with_any": int(fat_ch[fat_ch.kw_pitting | fat_ch.kw_corrosion].uwi.nunique())}))

f.drop(columns=["summ"]).to_csv(OUT / "located_breaks.csv", index=False)

# ------------------------------------------------------------------ charts
fig, ax = plt.subplots()
bins = np.arange(0, 1001, 50)
for c, col in [("Corrosion", cm.C4), ("Fatigue", cm.C1), ("Load / Excess Stress", cm.C2)]:
    d = f[(f.cause == c) & f.depth_m.notna()].depth_m
    ax.hist(d, bins=bins, histtype="step", lw=2.2, color=col, label=f"{c} (n={len(d)})")
ax.set_xlabel("Break depth (m, measured along the string)")
ax.set_ylabel("Rod failures (count)")
ax.set_title(f"{f.depth_m.notna().sum()} rod breaks located from crew free text "
             f"({100 * f.depth_m.notna().mean():.0f}% of rod failures)")
ax.legend(frameon=False)
cm.save(fig, IDEA, "5a_break_depth_by_cause.png")

fig, ax = plt.subplots()
ax.hist(perm_share, bins=30, color=cm.GREY, alpha=0.8, label="random pairing within area (1,000 permutations)")
ax.axvline(obs, color=cm.C4, lw=2.5, label=f"observed: same well, consecutive breaks ({obs:.0%})")
ax.set_xlabel("Share of consecutive break pairs within 50 m of each other")
ax.set_ylabel("Permutations (count)")
ax.set_title(f"Strings keep breaking in the same place: {obs / np.mean(perm_share):.1f}x more often than chance")
ax.legend(frameon=False)
cm.save(fig, IDEA, "5b_same_depth_repeat.png")

fig, ax = plt.subplots()
cols = ["kw_pitting", "kw_corrosion", "kw_wear", "kw_sand", "kw_wax_paraffin", "kw_guides_centralizers"]
labs = ["pitting", "corrosion/rust", "wear", "sand", "wax/paraffin", "guides/centralizers"]
x = np.arange(len(cols))
for i, (c, col) in enumerate([("Fatigue", cm.C1), ("Corrosion", cm.C4), ("Load / Excess Stress", cm.C2)]):
    if c in kw.index:
        ax.bar(x + (i - 1) * 0.27, kw.loc[c, cols], width=0.27, color=col, label=f"coded {c} (n={int(kw.loc[c, 'n_linked'])})")
ax.set_xticks(x, labs)
ax.set_ylabel("% of linked crew narratives mentioning the term")
ax.set_xlabel("Keyword family in Rod Truck / Workover job summary")
pct_fat = 100 * (fat.kw_pitting | fat.kw_corrosion).mean()
ax.set_title(f"Crew text mostly agrees with the coded cause, but {pct_fat:.0f}% of 'Fatigue' breaks mention pitting/corrosion")
ax.legend(frameon=False)
cm.save(fig, IDEA, "5c_narrative_vs_coded_cause.png")

if chronic_path.exists():
    top = ch.sort_values("repairs_last365", ascending=False).uwi.head(12).tolist()
    d = loc[loc.uwi.isin(top)]
    order = [u for u in top if u in set(d.uwi)]
    fig, ax = plt.subplots(figsize=(10, 6))
    for i, u in enumerate(order):
        g = d[d.uwi == u]
        ax.scatter(g.depth_m, [i] * len(g), s=55, color=[cm.C4 if c == "Corrosion" else cm.C1 if c == "Fatigue" else cm.C2 for c in g.cause],
                   edgecolor="white", zorder=3)
    ax.set_yticks(range(len(order)), order, fontsize=8.5)
    ax.set_xlabel("Break depth (m)")
    ax.set_ylabel("Idea-1 program well (most repairs at top)")
    ax.invert_yaxis()
    ax.set_title("Worst wells: some break in one band (replace a section), others along the string (replace all)\n"
             "red = corrosion, blue = fatigue, orange = other", fontsize=11.5)
    cm.save(fig, IDEA, "5d_chronic_well_break_bands.png")

(OUT / "results.txt").write_text("".join(lines), encoding="utf-8")
