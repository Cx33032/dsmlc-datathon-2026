# Pitch: "Stop patching, start replacing" (Idea 1 + Idea 5)

Every number comes from a script in `data/ideas/` (Idea 1: `1/rod_replace_analysis.py`, Idea 5: `5/break_depth_mining.py`).
Price inputs are in `data/ideas/common.py`.
Full detail is in [1/idea.md](1/idea.md) and [5/idea.md](5/idea.md).

## The one-sentence version

145 Strathcona wells broke a rod 3 or more times in the last year, and crews keep patching them. A new rod string cuts the risk of the next break by about half, the crews' own notes show where the string breaks, and together that is worth about $7.4M over 2 years.

## In plain words

- A heavy-oil well has a pump at the bottom and a long steel rod that connects it to a motor on the surface.
- When the rod breaks, the well stops, and a crew has to come out.
- Today, crews usually **patch** the broken part.
- Idea 1 asks: for wells that keep breaking, is it cheaper to **replace the whole rod** once?
- Idea 5 asks: **where** does the rod break, and **why**? The crews wrote it down in their job notes.

## The 60-second talk track

1. "The failure log holds 2,186 rod failures, almost all since mid-2025. Over 2021 to 2026, downhole failures cost $250 million all-in, counting repair jobs and lost oil."
2. "That cost is concentrated. The worst 10% of wells carry 30% of it."
3. "Right now, 145 wells have had 3 or more rod repairs in 12 months. Together that is 678 repairs and $9 million. One well had 17."
4. "We compared wells that got a brand new rod string with wells that got a patch. After adjusting for failure history, flow rate, pump speed, area and year, the new string cut the risk of the next break to 0.49 times. The 95% range is 0.42 to 0.56."
5. "A new string costs $14,010 more than a patch. It pays for itself on any well that breaks more than once a year."
6. "Crews also write where the rod broke. We read those notes. Breaks on the same well repeat within 50 metres 49% of the time. Random pairing gives 17%."
7. "So for 54 of the 145 wells, a section replacement may be enough. And where crews wrote 'pitting' on a break coded as fatigue, add corrosion protection."
8. "Net value of the program: $7.4 million over two years. $5.9 million if we use the pessimistic end of our estimate."

## Slide plan (10 minutes + 3 minutes of questions)

| # | Time | Slide | Show | Say |
|---|---|---|---|---|
| 1 | 0:45 | Hook | Big number: "145 wells" | "These wells broke a rod 3 or more times this year, and we keep patching them." |
| 2 | 1:00 | The cost | `1/assets/1a_cost_concentration.png` | $250.1M all-in over 2021-26. Top 10% of wells = 30.2% of cost, top 20% = 48.3%. |
| 3 | 1:00 | Traps we avoided | A 4-row table (below) | "A naive analysis gets these wrong." |
| 4 | 1:30 | Finding 1: replace beats patch | `1/assets/1b_next_year_rate_by_history.png` and the hazard table | At every level of prior failures, wells with a new string fail less. HR 0.485 (0.422-0.559). |
| 5 | 1:30 | Finding 2: where it breaks | `5/assets/5b_same_depth_repeat.png` | 983 breaks located from crew text (45%). 48.6% repeat within 50 m vs 16.7% by chance (2.9x, p = 0.001). |
| 6 | 1:00 | The decision rule | 3-line rule box (below) | "A crew can follow this at the next pull." |
| 7 | 1:00 | The money | Sensitivity table | $7.43M central, $5.89M pessimistic. Show the price source. |
| 8 | 0:45 | What we are not claiming | 3 bullets | Observational, 45% coverage, assumptions. Propose a pilot. |
| 9 | 0:45 | How it runs day to day | Canary board (optional) | Ranked well list with alarms. |
| 10 | 0:15 | Close | One line | "Replace on the 145. Start with the worst 14." |

### Slide 3: traps we avoided

| Trap | What a naive analysis does | What we did |
|---|---|---|
| Failure log really starts in mid-2025 | Treats it as 5 years of history, but it has only 2 records before 2025 and 1,230 in 2025 | Uses repair jobs as the history, checked against the log (89-97% of rod repair jobs match a failure record) |
| $0 job costs in 2021-22 | Averages them in, so patches look free | Uses only jobs from 2023 on with cost above $0 |
| Wells are already down before the failure date | Calls that a leading signal | Drops it, because the crew already knows the rod is broken |
| Uneconomic shut-ins booked as lost oil | Overstates losses by about 27,000 m3/year | Excludes them |

### Slide 6: the decision rule

1. If a well has 3 or more rod repairs in 12 months: run a full new string at the next pull.
2. If its past breaks fall within a 150 m band: a section replacement may be enough, and add guides at that depth.
3. If crew notes mention pitting or corrosion: add an inhibitor program and a corrosion-resistant grade.

## The money, step by step

| Input | Value | Source |
|---|---|---|
| WTI | $83.45 USD/bbl (2026-11-19) | OilPriceAPI table (indicative) |
| WCS discount to WTI | -$26.20 USD/bbl (Hardisty, Dec delivery, 2026-11-13) | CalRock via Reuters, BOE Report |
| USD/CAD | 1.4325 (2026-11-20) | Bank of Canada |
| WCS in CAD per m3 | (83.45 - 26.20) x 1.4325 x 6.2898 = $515.8 | Calculation |
| Field-gate price | $515.8 x 0.85 = **$438.5/m3** | 15% haircut is **our assumption**, not verified |
| Mean rod repair job | $8,672 | Jobs with cost above $0, 2023 on |
| Mean rod replacement job | $22,683 | Jobs with cost above $0 |
| Lost oil per rod repair | 11.72 m3 = $5,140 | Downhole-coded lost oil, 7 days before to 1 day after the job |
| All-in cost per failure | $13,812 | Repair + lost oil |
| Extra cost of replacing | **$14,010** | $22,683 - $8,672 |

**Per-well rule.**
Avoided failures per year = (breaks per year) x (1 - 0.495).
Net over 2 years = 0.505 x 2 x breaks per year x $13,812 - $14,010.
Break-even is **1.0 break per year**.

**Program.**
Avoided failures over 2 years = 678 x 0.505 x 2 = 685.
Gross value = 685 x $13,812 = $9.46M.
Extra cost = 145 x $14,010 = $2.03M.
Net = **$7.43M**.

### Sensitivity (all 145 wells)

| Scenario | Net over 2 years | Wells positive |
|---|---|---|
| Central | $7.43M | 145 |
| Hazard ratio at its upper 95% bound (0.577) | $5.89M | 145 |
| Oil price -30% | $6.38M | 145 |
| Lost oil ignored (job costs only) | $3.91M | 145 |
| Replacement costs twice as much extra | $5.40M | 145 |
| 1-year horizon | $2.70M | 145 |
| Everything pessimistic at once | -$1.58M | 14 |

The program stays positive under each single stress.
When every pessimistic assumption is stacked together, it only pays on the worst 14 wells, so the rule becomes "start with the worst 14".

## What we are not claiming

- **The effect is observational.** Engineers may pick wells for new strings that were going to improve anyway. We adjusted for history, flow, speed, area and year, but we cannot remove all selection. The fix is a pilot: randomize 70 of the 145 wells to replace at the next failure, keep the rest on repair for 6 months.
- **We read 45% of the breaks, not all of them.** The depth parser is rule-based and has only been spot-checked on 15 rows so far.
- **The section-replacement saving ($0.30M) rests on one assumption:** a section job costs 40% less extra. Strathcona's real split between rig time and material would replace it.
- **The replacement cost may be understated** if rod material is booked outside `field_est_total`.
- **Oil is valued at revenue, not margin,** and the 15% field-gate haircut is our own number.

## Questions the judges will ask

**1. "Strings get replaced when something else changes too. Isn't this just selection bias?"**
We adjusted for prior failures, liquid rate, pump speed, area and year.
The effect appears in every prior-failure band, including wells with 3-4 and 5+ prior repairs.
We say the effect is of "the replacement job as practised", co-interventions included.
Even at the upper 95% bound the program nets $5.89M.
Our proposed pilot settles it.

**2. "Your replacement cost is too low, and 2021-22 repair costs are $0."**
We saw the $0 rows: 99.9% of 2021 and 60.3% of 2022 Rod Truck jobs.
Costs use 2023-onward jobs with cost above $0.
If the extra cost doubles, break-even moves to 2.0 breaks per year and the program still nets $5.40M.

**3. "The well is back on production a day after the failure. Why 11.7 m3 of lost oil?"**
From the logged failure date, yes (median 1 day).
But downtime starts earlier: mean hours down climbs from 2.9 h at day -14 to 18.1 h at day -1.
With the median lost oil (7.33 m3) the program nets $6.11M.
With lost oil ignored it still nets $3.91M.

## Still to do before Sunday 12:00

- [ ] Time-split backtest: fit on 2022 to mid-2024, test on events after.
- [ ] Hand-label 150 crew notes to measure extraction precision and recall.
- [ ] Well card: break-depth strip, band width, recommended remedy, three supporting crew quotes.
- [ ] Slides, 5-minute video, repository README with the AI-use disclosure.
- [ ] Optional: Canary board with the ranked well list and alarms.
