"""Level assessment from training history.

Every session here is invented. The point of these tests is the boundaries and
the honesty properties, not the exact threshold numbers.
"""

from datetime import date, datetime, timedelta

from rapha.models import Activity, Source
from rapha.rules.level import (
    AVANCADO,
    INICIANTE,
    INTERMEDIARIO,
    assess_level,
)
from rapha.units import Seconds

TODAY = date(2026, 7, 22)


def strength_session(d: date) -> Activity:
    return Activity(
        activity_id=f"s-{d.isoformat()}",
        start=datetime(d.year, d.month, d.day, 18, 0),
        kind="strength_training",
        duration=Seconds(3600),
        source=Source.GARMIN_API,
    )


def weekly_sessions(per_week: int, weeks: int, *, end: date = TODAY) -> list[Activity]:
    out: list[Activity] = []
    for w in range(weeks):
        monday = end - timedelta(weeks=w)
        for i in range(per_week):
            out.append(strength_session(monday - timedelta(days=i)))
    return out


class TestLevelBands:
    def test_a_consistent_high_frequency_history_reads_advanced(self):
        acts = weekly_sessions(4, 40)
        result = assess_level(acts, today=TODAY)
        assert result.recommendation == AVANCADO
        assert "MÓDULO 05" in result.module

    def test_an_established_moderate_history_reads_intermediate(self):
        acts = weekly_sessions(2, 20)
        result = assess_level(acts, today=TODAY)
        assert result.recommendation == INTERMEDIARIO
        assert "MÓDULO 04" in result.module

    def test_a_light_history_reads_beginner(self):
        acts = weekly_sessions(1, 6)
        result = assess_level(acts, today=TODAY)
        assert result.recommendation == INICIANTE

    def test_no_history_reads_beginner_and_says_why(self):
        result = assess_level([], today=TODAY)
        assert result.recommendation == INICIANTE
        assert result.strength_sessions == 0


class TestItResolvesDownwardUnderAmbiguity:
    """Too-easy costs a fortnight; too-hard risks injury. Ambiguity goes down."""

    def test_a_recent_gap_pulls_a_frequent_trainer_off_advanced(self):
        # Frequent early, then an 8-week layoff: not currently advanced.
        acts = weekly_sessions(4, 40, end=TODAY - timedelta(weeks=8))
        result = assess_level(acts, today=TODAY)
        assert result.recommendation != AVANCADO

    def test_a_long_gap_is_flagged_as_readaptation_risk(self):
        acts = [strength_session(date(2026, 1, 5)), *weekly_sessions(3, 6)]
        result = assess_level(acts, today=TODAY)
        assert any("readapt" in n for n in result.notes)


class TestHonesty:
    def test_the_result_is_always_provisional_until_auto_check(self):
        result = assess_level(weekly_sessions(4, 40), today=TODAY)
        assert result.provisional
        assert any("Auto Check" in r or "Módulo 18" in r for r in result.reasoning)

    def test_the_evidence_is_shown_not_just_the_verdict(self):
        result = assess_level(weekly_sessions(3, 30), today=TODAY)
        assert result.reasoning
        assert result.sessions_per_week > 0
        assert 0 <= result.consistency <= 1

    def test_non_strength_activities_do_not_count(self):
        rides = [
            Activity(
                activity_id=f"r{i}",
                start=datetime(2026, 6, 1, 6) + timedelta(days=i),
                kind="cycling",
                duration=Seconds(3600),
                source=Source.GARMIN_API,
            )
            for i in range(40)
        ]
        result = assess_level(rides, today=TODAY)
        assert result.strength_sessions == 0
        assert result.recommendation == INICIANTE
