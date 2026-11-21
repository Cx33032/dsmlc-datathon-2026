# Canary integration

Canary is the **operator surface** of this project. The Python pipeline does the analysis and
the model. Canary stores the raw tags alongside the model outputs, so an operator sees the
failure risk next to the well's own trends and can act on it.

```
parquet ──► run_pipeline.py ──► export_to_canary.py ──► CSV Collector ──► Canary Historian
                (model, losses)      (tags + quality codes)                     │
                                                                  Views (asset tree: Area › Well)
                                                                                │
                                                     Axiom screens (field → area → watchlist → well)
```

## 1. Install

1. Request licenses in `#canary-request` (team name + members), then install Canary from the link
   in the briefing document: **Historian**, **Views**, **Axiom** and the **CSV Collector**.
2. Copy `csv_collector_config.json` to
   `%ProgramData%\Canary\CsvCollector\Directories\Strathcona.json`. Edit `DirectoryPath` if you
   use a folder other than `C:\CanaryImport\Strathcona`.
3. Restart the **Canary CSV Collector** service whenever you change the config. Errors show up
   in the Canary Admin **Messages** tile.

> The config keys come from Canary's *How to Configure the CSV Collector (v26)* help article.
> Import one small file first, e.g. `--start 2026-10-01 --areas Winter`, and confirm the timestamps
> parse before loading everything.

## 2. Load data

```powershell
python run_pipeline.py
python canary/export_to_canary.py --out C:/CanaryImport/Strathcona          # 2026 YTD, all areas
python canary/export_to_canary.py --start 2025-01-01 --out C:/CanaryImport/Strathcona   # full test period
```

**Live demo:** replay days into the watched folder so tags and alarms update in front of the judges:

```powershell
python canary/export_to_canary.py --start 2026-08-01 --replay-dir C:/CanaryImport/Strathcona --replay-from 2026-09-15 --seconds 5
```

## 3. Tag model

Dataset `Strathcona`. Tag path = `Area.UWI.Measure` (area names use `_` instead of spaces).

| Measure | Source | Notes |
|---|---|---|
| `Oil_m3d`, `Water_m3d`, `Gas_e3m3d`, `HoursOn`, `PumpEfficiency` | daily data | quality 192, or 0 for implausible raw values |
| `PumpRPM`, `RodTorque_ftlb`, `MotorCurrent_A`, `CasingPressure_kPa`, `TubingPressure_kPa` | daily data | **quality 64 (Uncertain) when identical to the previous day**: these are carried-forward manual readings |
| `BaselineOil_m3d` | pipeline | trailing 30-day median oil rate |
| `EstLostOil_m3`, `Downtime`, `LossCategoryCode` | pipeline | code lookup in `LossCategoryCode_lookup.csv` |
| `FailureRisk14d` | model | probability that a failure outage starts within 14 days |
| `RiskRank` | model | 1 = highest risk in the field that day |
| `RiskAlert` | model | 0 normal · 1 watch (top 5%) · 2 alarm (top 2%) |
| `FailureEvent`, `RepairCost_CAD` | jobs | pulse of 1 on the outage-onset day, use as trend markers |
| `Area._Area.*`, `_Field._Total.*` | roll-ups | `Oil_m3d`, `EstLostOil_m3`, `AvoidableLostOil_m3`, `RunningWells`, `WellsOnWatch`, `WellsInAlarm`, `MeanRisk` |

## 4. Views - asset model

Create a **Virtual View** over dataset `Strathcona` that splits the tag path on `.`:
Level 1 = Area, Level 2 = Well (UWI), Level 3 = Measure. Every well then becomes an asset with
the same measure names, so one Axiom template works for all 2,240 producers.

## 5. Axiom screens to build

1. **Field overview.** Tiles show `_Field._Total.Oil_m3d`, `AvoidableLostOil_m3` and
   `WellsInAlarm`, with one trend per area (`*._Area.EstLostOil_m3`). Answers: "where is oil going
   today?"
2. **Watchlist.** A table of wells sorted by `RiskRank` showing `FailureRisk14d`, `RiskAlert`
   (conditional colour: 2 = red, 1 = amber), `Oil_m3d` vs `BaselineOil_m3d` and `PumpEfficiency`.
   Answers: "which wells do I send a rod truck or diagnostic to?"
3. **Well detail (asset template).** Trends of `Oil_m3d` + `BaselineOil_m3d`, `PumpEfficiency` and
   `FailureRisk14d`, with `FailureEvent` as markers. Uncertain-quality points on manual tags appear
   greyed out, which shows operators which readings are stale.
4. **Data quality.** Count of Uncertain/Bad values per area, which makes the case for automating
   the manual tags.

**Alarms:** if the license includes Canary's calculation/event features, define an event
`RiskAlert >= 2` per well asset. Otherwise use Axiom conditional formatting on `RiskAlert`.
Confirm which modules your license covers in `#canary-request`.

## 6. Closing the loop

Pull data back into Python through **Historian ODBC** to retrain the model on new data. The
training features only need `Oil_m3d`, `Water_m3d`, `HoursOn`, `PumpEfficiency`, the pump tags
and the event history, all of which are already in the historian.
