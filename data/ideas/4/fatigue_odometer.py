"""Idea 4 - reference implementation of the on-device "rod-string fatigue odometer" + regime classifier.

Run:  python data/ideas/4/fatigue_odometer.py
Outputs: data/ideas/4/out/odometer_results.txt, charts 4d-4e in docs/ideas/4/assets/

This is the algorithm that would run on the nRF52832 (Cortex-M4F, 64 KB RAM).
It is written in plain Python with fixed-size buffers so it ports line-for-line to C.

  1. Streaming rainflow counting (4-point rule, bounded stack) on a torque signal.
     Verified here against a textbook batch rainflow (ASTM E1049 3-point) on the same signal.
  2. Miner's-rule damage with a Goodman mean-stress correction and a Basquin slope m.
     Output is a RELATIVE damage index (normal operation = 1.0 per hour). Absolute life needs rod-grade S-N data.
  3. A depth-4 decision tree on 10-second window features classifying the operating regime
     (normal / stick-slip / sand-slug overload / parted rod), small enough to emit as C if-else code.

IMPORTANT: the signals below are SYNTHETIC. Their mean torque (625 ft-lb) and speed (200 RPM) are the
dataset medians (00_profiling); every other shape parameter is an assumption to be replaced by
measurements from the 3D-printed test rig and, later, VFD torque data from a pilot well.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common as cm
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.tree import DecisionTreeClassifier, export_text
from sklearn.metrics import confusion_matrix, classification_report

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)
IDEA = "4"
cm.style()
lines = []
rng = np.random.default_rng(11)


def emit(t, obj):
    s = f"\n### {t}\n{obj if isinstance(obj, str) else obj.to_string()}\n"
    print(s)
    lines.append(s)


FS = 50.0            # Hz sample rate on the device (assumption; SAADC can go far higher)
T_MEAN = 625.0       # ft-lb, dataset median rod torque
RPM = 200.0          # dataset median pump speed
M_BASQUIN = 5.0      # S-N slope (assumption, typical order for notched/corroded steel)
S_ULT = 3.0 * T_MEAN  # normalising "ultimate" torque for the Goodman correction (assumption)
HYST = 0.02 * T_MEAN  # dead-band so sensor noise does not create cycles


# ------------------------------------------------------------------ 1. synthetic torque regimes
def make_signal(regime, seconds):
    """Each call draws its own intensity so regimes overlap (mild stick-slip looks like noisy normal, etc.)."""
    t = np.arange(0, seconds, 1 / FS)
    f_rot = RPM / 60 * rng.uniform(0.6, 1.5)                  # wells run ~120-300 RPM
    level = T_MEAN * rng.uniform(0.7, 1.3)                     # well-to-well torque level
    ripple, noise = rng.uniform(0.03, 0.10), rng.uniform(0.01, 0.04)
    base = level * (1 + ripple * np.sin(2 * np.pi * f_rot * t)) + rng.normal(0, noise * level, t.size)
    if regime == "normal":
        return base
    if regime == "stick_slip":       # torque winds up then releases, period 2-8 s, amplitude 10-45% (assumption)
        period, amp = rng.uniform(2, 8), rng.uniform(0.10, 0.45)
        saw = (t % period) / period
        return base + amp * level * (saw - 0.5)
    if regime == "sand_slug":        # elevated load 10-35% with heavier ripple (assumption)
        k = rng.uniform(1.10, 1.35)
        return base * k + rng.uniform(0.04, 0.12) * level * np.sin(2 * np.pi * 2 * f_rot * t) + rng.normal(0, 0.03 * level, t.size)
    if regime == "parted_rod":       # only the upper string + drive friction left: 8-25% of normal torque
        return rng.uniform(0.08, 0.25) * level * (1 + 0.02 * np.sin(2 * np.pi * f_rot * t)) + rng.normal(0, noise * 0.2 * level, t.size)
    raise ValueError(regime)


# ------------------------------------------------------------------ 2. streaming rainflow (4-point, bounded stack)
class StreamingRainflow:
    """Peak/valley extraction with hysteresis + 4-point rainflow. Memory: STACK_MAX floats."""
    STACK_MAX = 64

    def __init__(self, hyst):
        self.hyst, self.stack, self.last_ext, self.cand, self.dir = hyst, [], None, None, 0
        self.cycles = []          # (range, mean, count) ; on-device this would go straight into a histogram
        self.overflow = 0

    def _push_extremum(self, v):
        s = self.stack
        s.append(v)
        while len(s) >= 4:
            a, b, c, d = s[-4], s[-3], s[-2], s[-1]
            if abs(c - b) <= abs(b - a) and abs(c - b) <= abs(d - c):
                self.cycles.append((abs(c - b), (b + c) / 2, 1.0))
                del s[-3:-1]
            else:
                break
        if len(s) > self.STACK_MAX:      # bounded memory: close the oldest half-cycle
            self.cycles.append((abs(s[1] - s[0]), (s[0] + s[1]) / 2, 0.5))
            del s[0]
            self.overflow += 1

    def update(self, x):
        if self.cand is None:
            self.cand = x
            return
        if self.dir >= 0 and x > self.cand or self.dir <= 0 and x < self.cand:
            if self.dir == 0:
                self.dir = 1 if x > self.cand else -1
            self.cand = x
        elif abs(x - self.cand) > self.hyst:          # reversal confirmed
            self._push_extremum(self.cand)
            self.dir = -self.dir if self.dir else (1 if x > self.cand else -1)
            self.cand = x

    def finish(self):
        self._push_extremum(self.cand)
        s = self.stack
        for i in range(len(s) - 1):                    # residue counted as half cycles
            self.cycles.append((abs(s[i + 1] - s[i]), (s[i] + s[i + 1]) / 2, 0.5))
        self.stack = []
        return self.cycles


def batch_rainflow(x, hyst):
    """ASTM E1049-85 three-point rainflow on hysteresis-filtered extrema (reference)."""
    ext, cand, d = [], x[0], 0
    for v in x[1:]:
        if d >= 0 and v > cand or d <= 0 and v < cand:
            if d == 0:
                d = 1 if v > cand else -1
            cand = v
        elif abs(v - cand) > hyst:
            ext.append(cand)
            d = -d if d else (1 if v > cand else -1)
            cand = v
    ext.append(cand)
    out, s = [], []
    for p in ext:
        s.append(p)
        while len(s) >= 3:
            X, Y = abs(s[-1] - s[-2]), abs(s[-2] - s[-3])
            if X < Y:
                break
            if len(s) == 3:
                out.append((Y, (s[-2] + s[-3]) / 2, 0.5))
                del s[0]
            else:
                out.append((Y, (s[-2] + s[-3]) / 2, 1.0))
                del s[-3:-1]
    for i in range(len(s) - 1):
        out.append((abs(s[i + 1] - s[i]), (s[i] + s[i + 1]) / 2, 0.5))
    return out


def damage(cycles):
    """Miner sum with Goodman correction; relative units (S_ref = T_MEAN)."""
    if not cycles:
        return 0.0
    c = np.array(cycles)
    amp, mean, n = c[:, 0] / 2, c[:, 1], c[:, 2]
    amp_eq = amp / np.clip(1 - mean / S_ULT, 0.05, None)
    return float(np.sum(n * (amp_eq / T_MEAN) ** M_BASQUIN))


# ------------------------------------------------------------------ verify streaming == batch
ver = []
for reg in ["normal", "stick_slip", "sand_slug"]:
    x = make_signal(reg, 600)
    srf = StreamingRainflow(HYST)
    for v in x:
        srf.update(v)
    sc = srf.finish()
    bc = batch_rainflow(x, HYST)
    ver.append(dict(regime=reg, samples=len(x), stream_cycles=sum(c[2] for c in sc), batch_cycles=sum(c[2] for c in bc),
                    stream_damage=damage(sc), batch_damage=damage(bc), stack_overflows=srf.overflow))
ver = pd.DataFrame(ver)
ver["damage_rel_diff_pct"] = 100 * (ver.stream_damage - ver.batch_damage) / ver.batch_damage
emit("Streaming 4-point rainflow vs batch ASTM 3-point rainflow (same 600 s signal)", ver.round(4).to_string(index=False))

# ------------------------------------------------------------------ damage rate per regime (relative to normal)
rates = {}
for reg in ["normal", "stick_slip", "sand_slug", "parted_rod"]:
    vals = []
    for _ in range(20):
        x = make_signal(reg, 600)
        srf = StreamingRainflow(HYST)
        for v in x:
            srf.update(v)
        vals.append(damage(srf.finish()) * 6)   # per hour
    rates[reg] = np.mean(vals)
rel = pd.Series({k: v / rates["normal"] for k, v in rates.items()})
emit("Relative damage rate per hour (normal = 1.0)  [synthetic signals, assumed S-N slope m=5]", rel.round(2))

# day in the life: 20 h normal + 2 h stick-slip + 2 h sand slug vs a clean day
day_mix = (20 * rates["normal"] + 2 * rates["stick_slip"] + 2 * rates["sand_slug"]) / (24 * rates["normal"])
emit("Damage of a day with 2 h stick-slip + 2 h sand slug, relative to a clean day", f"{day_mix:.2f}x")

# ------------------------------------------------------------------ 3. regime classifier on 10-s windows
def window_feats(x):
    d = np.diff(x)
    srf = StreamingRainflow(HYST)
    for v in x:
        srf.update(v)
    cyc = srf.finish()
    rngs = np.array([c[0] for c in cyc]) if cyc else np.array([0.0])
    return dict(mean_norm=x.mean() / T_MEAN, std_norm=x.std() / T_MEAN, p2p_norm=np.ptp(x) / T_MEAN,
                max_cycle_range_norm=rngs.max() / T_MEAN, n_big_cycles=int((rngs > 0.2 * T_MEAN).sum()),
                mean_abs_slope=np.abs(d).mean() / T_MEAN)


rows = []
for reg in ["normal", "stick_slip", "sand_slug", "parted_rod"]:
    for _ in range(400):
        rows.append({**window_feats(make_signal(reg, 10)), "regime": reg})
W = pd.DataFrame(rows).sample(frac=1, random_state=0)
tr, te = W.iloc[: int(0.7 * len(W))], W.iloc[int(0.7 * len(W)):]
FEATS = [c for c in W.columns if c != "regime"]
clf = DecisionTreeClassifier(max_depth=4, random_state=0).fit(tr[FEATS], tr.regime)
pred = clf.predict(te[FEATS])
emit("Regime classifier (depth-4 tree) on held-out synthetic 10-s windows",
     classification_report(te.regime, pred, digits=3))
emit("Confusion matrix (rows = true)", pd.DataFrame(confusion_matrix(te.regime, pred, labels=clf.classes_),
                                                    index=clf.classes_, columns=clf.classes_))
emit("Tree as rules (ports to C if-else)", export_text(clf, feature_names=FEATS))

# ------------------------------------------------------------------ on-device budget
n_nodes = clf.tree_.node_count
budget = pd.Series({
    "rainflow_stack_bytes (64 x float32)": 64 * 4,
    "damage_histogram_bytes (32 range x 16 mean bins x uint16)": 32 * 16 * 2,
    "window_buffer_bytes (10 s x 50 Hz x int16)": int(10 * FS * 2),
    "tree_bytes (nodes x 12 B)": n_nodes * 12,
    "total_bytes": 64 * 4 + 32 * 16 * 2 + int(10 * FS * 2) + n_nodes * 12,
    "nRF52832_RAM_bytes": 64 * 1024,
    "raw_stream_bytes_per_min (50 Hz int16)": int(FS * 2 * 60),
    "summary_bytes_per_min (damage, regime, mean, p2p, 4 x float32 + ts)": 20,
})
budget["ram_share_pct"] = 100 * budget["total_bytes"] / budget["nRF52832_RAM_bytes"]
budget["radio_reduction_x"] = budget["raw_stream_bytes_per_min (50 Hz int16)"] / budget["summary_bytes_per_min (damage, regime, mean, p2p, 4 x float32 + ts)"]
emit("On-device memory and radio budget", budget.round(2))

# ------------------------------------------------------------------ charts
fig, axes = plt.subplots(2, 1, figsize=(10, 6.5), sharex=False)
segs = [("normal", 30), ("stick_slip", 30), ("sand_slug", 30), ("parted_rod", 15)]
xs, labs, t0 = [], [], 0
for reg, sec in segs:
    x = make_signal(reg, sec)
    xs.append(x)
    labs.append((t0, t0 + sec, reg))
    t0 += sec
x = np.concatenate(xs)
t = np.arange(x.size) / FS
axes[0].plot(t, x, color=cm.C1, lw=0.7)
colors = {"normal": cm.C3, "stick_slip": cm.C4, "sand_slug": cm.C2, "parted_rod": cm.GREY}
for a, b, reg in labs:
    axes[0].axvspan(a, b, color=colors[reg], alpha=0.12)
    axes[0].text((a + b) / 2, x.max() * 1.02, reg.replace("_", " "), ha="center", fontsize=9)
axes[0].set_ylabel("Rod torque (ft-lb)")
axes[0].set_xlabel("Time (s) - synthetic 50 Hz signal")
axes[0].set_title("What a 50 Hz torque sensor sees that a once-a-month historian value cannot")
reg_names = ["normal", "stick_slip", "sand_slug", "parted_rod"]
axes[1].bar([r.replace("_", " ") for r in reg_names], [rel[r] for r in reg_names],
            color=[colors[r] for r in reg_names])
axes[1].set_yscale("log")
axes[1].set_ylim(0.1, max(rel.values) * 4)
axes[1].set_ylabel("Relative damage / hour\n(normal = 1, log scale)")
axes[1].set_title("Assumption-driven (S-N slope m=5): rare large cycles dominate damage", fontsize=10.5)
axes[1].set_xlabel("Operating regime")
for i, r in enumerate(reg_names):
    axes[1].text(i, max(rel[r], 0.1) * 1.15, f"{rel[r]:.2g}x" if rel[r] >= 0.01 else "~0 (no load)", ha="center", fontsize=9)
fig.tight_layout()
cm.save(fig, IDEA, "4d_odometer_regimes.png")

fig, ax = plt.subplots()
hours = np.arange(0, 24 * 30 + 1)
plan = {"clean operation": np.ones_like(hours, dtype=float),
        "2 h stick-slip + 2 h sand / day": np.full_like(hours, day_mix, dtype=float)}
for (lab, rate), col in zip(plan.items(), [cm.C3, cm.C4]):
    ax.plot(hours / 24, np.cumsum(rate) / 24, color=col, lw=2.4, label=f"{lab} ({rate[0]:.1f}x)")
ax.set_xlabel("Days in service")
ax.set_ylabel("Accumulated damage index (clean-day units)")
ax.set_title("The odometer turns hidden load events into 'clean days of life used'\n"
             "(synthetic; magnitudes depend on the assumed S-N slope)")
ax.legend(frameon=False)
cm.save(fig, IDEA, "4e_odometer_accumulation.png")

(OUT / "odometer_results.txt").write_text("".join(lines), encoding="utf-8")
