"""Edge cases of the at-the-pull decision rule (src/rules.py)."""
import pandas as pd

from src.rules import Evidence, evidence_for, headline, recommend


def by_kind(actions):
    return {a.kind: a for a in actions}


def test_chronic_well_gets_full_string():
    a = by_kind(recommend(Evidence(repairs_365=3, rod_failures_logged=1)))
    assert a["string"].status == "recommend"
    assert "3 rod repairs" in a["string"].evidence


def test_two_repairs_is_below_threshold():
    assert by_kind(recommend(Evidence(repairs_365=2)))["string"].status == "not indicated"


def test_recent_new_string_overrides_repair_count():
    a = by_kind(recommend(Evidence(repairs_365=6, new_string_365=True)))
    assert a["string"].status == "not indicated"


def test_zero_located_breaks_is_insufficient():
    assert by_kind(recommend(Evidence(repairs_365=4)))["section"].status == "insufficient data"


def test_one_located_break_is_insufficient():
    a = by_kind(recommend(Evidence(repairs_365=4, break_depths=[300.0])))
    assert a["section"].status == "insufficient data"
    assert "1 located break" in a["section"].evidence


def test_band_exactly_150_m_qualifies():
    a = by_kind(recommend(Evidence(break_depths=[400.0, 550.0])))
    assert a["section"].status == "recommend"
    assert "400-550 m" in a["section"].text


def test_band_just_over_150_m_does_not_qualify():
    assert by_kind(recommend(Evidence(break_depths=[400.0, 550.5])))["section"].status == "not indicated"


def test_nan_depths_are_ignored():
    a = by_kind(recommend(Evidence(break_depths=[float("nan"), 220.0])))
    assert a["section"].status == "insufficient data"


def test_mixed_causes_any_corrosion_evidence_triggers_inhibitor():
    a = by_kind(recommend(Evidence(rod_failures_logged=5, coded_corrosion=0, text_corrosion=1)))
    assert a["corrosion"].status == "recommend"
    assert "1 with pitting/corrosion" in a["corrosion"].evidence


def test_no_failures_logged_is_insufficient_for_corrosion():
    assert by_kind(recommend(Evidence(repairs_365=5)))["corrosion"].status == "insufficient data"


def test_fatigue_only_has_no_corrosion_action():
    assert by_kind(recommend(Evidence(rod_failures_logged=4)))["corrosion"].status == "not indicated"


def test_headline_lists_every_recommended_action():
    h = headline(recommend(Evidence(repairs_365=4, break_depths=[200, 260, 300], rod_failures_logged=3,
                                    coded_corrosion=1)))
    assert h.startswith("Recommended at this pull:")
    assert "full new rod string" in h and "200-300 m" in h and "inhibitor" in h


def test_headline_when_nothing_recommended():
    assert headline(recommend(Evidence())) == "No change to the standard repair indicated."


def test_evidence_uses_only_records_strictly_before_asof():
    asof = pd.Timestamp("2026-03-01")
    rod = pd.DataFrame({"uwi": ["W"] * 5, "is_replace": [0, 0, 0, 0, 1],
                        "s": pd.to_datetime(["2025-01-01", "2025-05-01", "2025-09-01", "2026-03-01", "2026-04-01"])})
    br = pd.DataFrame({"uwi": ["W", "W", "W"], "fd": pd.to_datetime(["2025-05-01", "2026-02-27", "2026-03-01"]),
                       "depth_m": [300.0, 320.0, 900.0], "cause": ["Fatigue", "Fatigue", "Corrosion"],
                       "kw_pitting": [False, False, True], "kw_corrosion": [False, False, True]})
    ev = evidence_for("W", asof, rod, br)
    assert ev.repairs_365 == 2            # 2025-05 and 2025-09; 2025-01 is outside 365 d, 2026-03-01 is not before asof
    assert not ev.new_string_365          # the 2026-04 replacement is in the future
    assert ev.break_depths == [300.0, 320.0]
    assert ev.coded_corrosion == 0 and ev.text_corrosion == 0
