# Axiom screens: what to build, control by control

Five screens, built with the controls in Axiom's **Controls** panel. Each screen answers one question an
operator asks. Tag paths below are as Axiom shows them when you browse `localhost › Strathcona`.

| # | Screen | Question it answers |
|---|---|---|
| 1 | Field overview | Where is oil going today, and is it getting worse? |
| 2 | Areas | Which area needs attention? |
| 3 | Watchlist | Which wells do I send a truck or a diagnostic to? |
| 4 | Well detail | What is happening on this one well? |
| 5 | Data quality | Which readings can I trust? |

## Before you start

1. **Time range.** The data ends on 26 Oct 2026 (that last day is partial). Axiom's default "last 24 hours"
   shows nothing. On every screen set an **absolute** range: `2026-07-26 00:00` → `2026-10-26 00:00`
   (90 days). Value Boxes and gauges then show the value on 25 Oct, the last full day.
2. **Time zone.** Set Axiom's time zone to Saskatchewan (UTC−6). Otherwise winter-month daily points show
   at 23:00 the day before.
3. **Asset model (needed for Asset Label and Asset Template).** In Canary Views, make a virtual view over
   dataset `Strathcona` that splits the tag path on `.`: level 1 = Area, level 2 = Well, level 3 = Measure.
   Every well becomes an asset with the same measure names, so one template works for all wells. Without
   it, Screens 1 and 5 still work with plain tag paths; Screens 2–4 need it.
4. **Navigation bar.** On every screen, put a **Panel** across the top holding a **Label** with the screen
   name and five **Buttons** (Overview, Areas, Watchlist, Well, Data quality), each set to open that
   screen. Build it once and copy it.

## Tag cheat-sheet

| Level | Path | Measures |
|---|---|---|
| Field | `Strathcona._Field._Total.` | `Oil_m3d`, `Water_m3d`, `EstLostOil_m3`, `AvoidableLostOil_m3`, `RunningWells`, `WellsOnWatchlist`, `WellsOnWatch`, `WellsInAlarm`, `MeanRisk` |
| Area | `Strathcona.<Area>._Area.` | same as field |
| Well | `Strathcona.<Area>.<UWI>.` | `Oil_m3d`, `Water_m3d`, `Gas_e3m3d`, `HoursOn`, `PumpEfficiency`, `PumpRPM`, `RodTorque_ftlb`, `MotorCurrent_A`, `CasingPressure_kPa`, `TubingPressure_kPa`, `BaselineOil_m3d`, `EstLostOil_m3`, `Downtime`, `LossCategoryCode`, `FailureRisk14d`, `RiskRank`, `RiskAlert`, `FailureEvent`, `RepairCost_CAD` |

- `RiskAlert`: 0 normal, 1 watch (risk ≥ 0.184, top 5%), 2 alarm (risk ≥ 0.226, top 2%).
- `FailureRisk14d`: chance a failure outage starts within 14 days (field average about 0.06).
- `LossCategoryCode`: 0 running, 1 Rods, 2 Pump, 3 Tubing/Packer, 4 Downhole other, 5 Surface equipment,
  6 Power, 7 Pipeline/Flowline, 8 Facility capacity, 9 Facility & Turnarounds, 10 Development/planned ops,
  11 Planned maintenance, 12 Other, 13 Uncoded, 14 Uneconomic shut-in.
- Quality: 192 Good; 64 Uncertain = a manual reading copied from the day before; Bad = implausible raw value.

Colours used throughout: grey = normal, amber = watch, red = alarm. Keep red for alarms only.

---

## Screen 1. Field overview

**Layout:** a **Grid** with three rows.

**Row 1: headline numbers (5 controls side by side)**

| Control | Tag | Settings |
|---|---|---|
| Value Box "Field oil" | `_Field._Total.Oil_m3d` | unit m³/d, 0 decimals |
| Value Box "Avoidable lost oil" | `_Field._Total.AvoidableLostOil_m3` | unit m³/d; amber above 250, red above 350 |
| Value Box "Wells in alarm" | `_Field._Total.WellsInAlarm` | red text when > 0 |
| Value Box "Wells on watch" | `_Field._Total.WellsOnWatch` | amber text when > 0 |
| Donut Gauge "Running wells" | `_Field._Total.RunningWells` | min 0, max 1,100 |

Under the row, a **Paragraph**: "Avoidable lost oil = oil lost to downtime, excluding wells shut in on
purpose. Alarm = the model's top 2% failure risk."

**Row 2: the trend (full width)**

- **Trend Graph**, two bands (separate panes, not two y-axes):
  - Band 1: `_Field._Total.Oil_m3d`.
  - Band 2: `_Field._Total.AvoidableLostOil_m3` and `_Field._Total.EstLostOil_m3`.
- Time range 90 days. This shows whether losses are rising.

**Row 3: where the losses are (two controls)**

- **Bar Chart** "Avoidable lost oil by area": one bar per area, tag `<Area>._Area.AvoidableLostOil_m3`
  for all 16 areas, sorted largest first.
- **Bar Chart** "Wells in alarm by area": `<Area>._Area.WellsInAlarm`, same order.

**Demo line:** "Field oil is X; we're losing Y a day we could avoid, mostly in these two areas."

---

## Screen 2. Areas

**Layout:** one **Asset Template** filling the screen, repeated for each **Area** asset (16 tiles, 4 × 4).

Inside each tile (design it once):

| Control | Tag (relative to the area) | Settings |
|---|---|---|
| Asset Label | area name | bold, top-left |
| Symbol | `_Area.WellsInAlarm` | red when > 0, grey when 0 |
| Value Box "Oil" | `_Area.Oil_m3d` | m³/d |
| Value Box "Lost" | `_Area.AvoidableLostOil_m3` | m³/d |
| Value Box "Alarm / watch" | `_Area.WellsInAlarm`, `_Area.WellsOnWatch` | red / amber text |
| Spark Chart | `_Area.AvoidableLostOil_m3` | last 30 days, no axes |

Set clicking a tile (or a small **Button** inside it) to open the Watchlist with that area as the asset.

**Demo line:** "Red tiles have wells in alarm; the spark line shows whether losses are rising."

---

## Screen 3. Watchlist

**Layout:** a **Label** + **Paragraph** at the top, then an **Asset Template** of **Well** assets in the
selected area, shown as rows (one row per well).

- Filter to wells with `RiskAlert ≥ 1`, and sort by `RiskRank` ascending (1 = highest risk in the field),
  if the template offers filter and sort options. If it does not, filter on `RiskAlert ≥ 1` only.
- Columns in each row:

| Control | Tag | Settings |
|---|---|---|
| Asset Label | well (UWI) | |
| Symbol | `RiskAlert` | 2 red, 1 amber, 0 grey |
| Value Box "Risk 14 d" | `FailureRisk14d` | shown as a %, 0 decimals |
| Linear Gauge "Risk" | `FailureRisk14d` | 0–0.5; amber band 0.184–0.226, red band above 0.226 |
| Value Box "Rank" | `RiskRank` | |
| Value Box "Oil vs normal" | `Oil_m3d` and `BaselineOil_m3d` | two numbers side by side |
| Value Box "Pump eff." | `PumpEfficiency` | % |
| Spark Chart | `Oil_m3d` | 30 days |
| Button "Open" | | opens Screen 4 with this well |

**Paragraph text:** "Wells whose failure risk in the next 14 days is in the top 5% (amber) or top 2% (red).
A falling spark line under a red symbol is the strongest call to act."

**Fallback without an asset model:** a **Data Table** with one row per well you pick for the demo, columns
`FailureRisk14d`, `RiskAlert`, `RiskRank`, `Oil_m3d`, `BaselineOil_m3d`, `PumpEfficiency`.

---

## Screen 4. Well detail (one template for every well)

**Layout:** a **Grid**: header row, a big trend, then a bottom row.

**Header row**

| Control | Tag | Settings |
|---|---|---|
| Asset Label | well (UWI) and area | large |
| Symbol | `RiskAlert` | 2 red, 1 amber, 0 grey |
| Circular Gauge "Failure risk, 14 d" | `FailureRisk14d` | 0–0.5; grey up to 0.184, amber to 0.226, red above |
| Value Box "Oil" | `Oil_m3d` | m³/d |
| Value Box "Normal" | `BaselineOil_m3d` | m³/d (30-day median while running) |
| Value Box "Hours on" | `HoursOn` | of 24 |
| Linear Gauge "Pump efficiency" | `PumpEfficiency` | 0–100% |

**Big trend (full width): Trend Graph, four bands**

1. `Oil_m3d` (solid) with `BaselineOil_m3d` (dashed): the gap is lost oil.
2. `FailureRisk14d`, with horizontal limit lines at 0.184 (amber) and 0.226 (red).
3. `PumpRPM`, `RodTorque_ftlb`, `MotorCurrent_A`. Turn on quality display, so Uncertain (copied-forward)
   points appear greyed: flat stretches are old readings, not steady running.
4. `FailureEvent` (a 1 on the day an outage starts) and `Downtime`, as step lines. These act as event
   markers lined up with the risk curve above.

**Bottom row**

- **Scatter Plot** "Torque vs speed": x = `PumpRPM`, y = `RodTorque_ftlb`, 90 days. Points drifting up and
  to the left (more torque at the same speed) suggest rising load on the rods.
- **Bar Chart** "Lost oil, last 30 days": `EstLostOil_m3` as daily bars.
- **Events Table** (only if events are set up; see below): alarm periods and failure events for this well.
- **Paragraph** with the operator note: "Red risk + oil below normal + torque climbing = schedule a
  diagnostic before the next failure."

**Demo line:** "Here is a well that went red ten days before its rod failure (the marker on band 4)."
Pick the well for the demo from the queue or the program in the app beforehand.

### Optional: events for the Events Table

If your licence includes Canary Calculations & Events, define two events on the Well asset type:
- "Risk alarm": starts when `RiskAlert >= 2`, ends when it drops below 2.
- "Failure": starts when `FailureEvent = 1`.

The Events Table on Screens 3 and 4 then lists them with start, end and duration.

---

## Screen 5. Data quality

**Question:** which readings are real measurements, and which are copied from the last site visit?

- **Label** + **Paragraph**: "RPM, torque, current and the pressures are typed in by hand. When a value is
  identical to the day before, we store it with Uncertain quality. Long flat greyed stretches mean nobody
  re-read the gauge."
- **Trend Graph**, three bands, for one well at a time (via the asset): `PumpRPM`, `RodTorque_ftlb`,
  `CasingPressure_kPa`, with quality display on.
- **Spark Chart** grid (2 × 4) of `RodTorque_ftlb` for eight wells from different areas, to show how common
  flat stretches are.
- **Paragraph** with the recommendation: "Automating these tags (hourly) would give the failure model fresh
  inputs and make short shocks visible."

---

## Controls not used, and why

- **IFrame**: could embed the Streamlit app, but Axiom runs on https and the app on plain http, so most
  browsers block the frame. Link to the app from the navigation bar's Button instead, if it offers an
  external link.
- **Image**, **Line**, **Grid**: layout only (a logo, separators, alignment); use as needed.

## A 60-second demo path

Overview (where the oil goes) → click the worst area's bar → Areas tile → Watchlist (red wells first) →
Open the top well → Well detail (risk went red before the failure marker) → Data quality (why hourly tags
would make this better).
