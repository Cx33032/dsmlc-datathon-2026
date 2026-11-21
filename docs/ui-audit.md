# UI audit (cold read, 2026-11-21)

Ranked by user impact. Format: page - fault - impact - principle broken.

1. All pages - the title is a label and a 3-step how-to sits above the answer - a new user cannot say the finding in 10 s - answer first, progressive disclosure.
2. Queue - the first well to act on is only implied by the top bar; "Open well card" is two screens down, after the facility box - the main action is hard to find - primary action most visible.
3. Program - the page shows net value but not what the program costs or saves - the user cannot answer "is it worth it" - answer first, key numbers at top.
4. Facility - no sentence says which facility or well to check first; "battery", "laggard" and "75% of peers" are defined only in a closed expander at the bottom - the user must guess the rule - explain terms on first use.
5. Evidence - no statement of where the numbers come from (files, dates, wells) - the user cannot judge the source - make provenance obvious.
6. Program - the worst-case bar label overlaps the axis labels; scenario names use "HR at upper 95% CI" - unreadable label, jargon - chart readability, plain language.
7. All pages - abbreviations unexplained on first use (UWI, HR, CI, K, WCS, bbl vs m3, C$, Cox, OR, SD) - users skip or misread the numbers - spell out abbreviations.
8. Field monitor - uses bbl where every other page uses m3, and repeats its own chart style and colour code - inconsistent units and look - one design system, same words for same thing.
9. All pages - slider, active toggle and segmented control are red, while red means loss or alarm in charts - colour meaning conflicts - one colour meaning across the app.
10. Facility - "all wells back on time" is blue, the colour used elsewhere for "act on this" - wrong emphasis - consistent colour meaning.
11. Chart titles state the subject, not the finding (for example "Facility incidents over time") - the user must work out the point - finding-style titles.
12. Filters - no one-click reset on any page; empty-filter messages do not say which filter to change - the user gets stuck - visible state, recovery.
13. Captions and help text - grey caption text may fall below WCAG AA contrast - hard to read for older eyes - contrast 4.5:1.
14. Sidebar - the app name is a slogan and "revenue, not margin" is cryptic - adds load, no decision value - reduce load.
