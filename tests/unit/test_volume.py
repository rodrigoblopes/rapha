"""Weekly training volume — tonnage and hard sets. Invented sets, round numbers."""

from datetime import date

from rapha.rules.volume import WeekVolume, trend, weekly_volume


def _wed(week_monday: str) -> date:
    # a training day inside the week starting `week_monday` (a Monday)
    y, m, d = (int(x) for x in week_monday.split("-"))
    return date(y, m, d + 2)


class TestWeeklyVolume:
    def test_empty_history_is_empty(self):
        assert weekly_volume([]) == []

    def test_tonnage_is_reps_times_load_in_kilograms(self):
        # 10 reps @ 100 kg + 8 reps @ 100 kg = 1800 kg in one week
        sets = [(date(2026, 8, 5), 10, 100000, "SQUAT"),
                (date(2026, 8, 5), 8, 100000, "SQUAT")]
        series = weekly_volume(sets, weeks=1, today=date(2026, 8, 5))
        assert series[-1].tonnage_kg == 1800.0
        assert series[-1].hard_sets == 2
        assert series[-1].sessions == 1

    def test_bodyweight_sets_count_as_sets_but_add_no_tonnage(self):
        sets = [(date(2026, 8, 5), 12, None, "PULL_UP"),
                (date(2026, 8, 5), 12, None, "PULL_UP")]
        w = weekly_volume(sets, weeks=1, today=date(2026, 8, 5))[-1]
        assert w.tonnage_kg == 0.0
        assert w.hard_sets == 0
        assert w.total_sets == 2

    def test_sub_kilo_noise_is_not_a_hard_set(self):
        w = weekly_volume([(date(2026, 8, 5), 10, 500, "HIP_STABILITY")],
                          weeks=1, today=date(2026, 8, 5))[-1]
        assert w.hard_sets == 0
        assert w.tonnage_kg == 0.0

    def test_every_week_in_the_window_is_present_even_when_empty(self):
        sets = [(date(2026, 8, 5), 10, 100000, "SQUAT")]
        series = weekly_volume(sets, weeks=4, today=date(2026, 8, 5))
        assert len(series) == 4
        assert [w.tonnage_kg for w in series] == [0.0, 0.0, 0.0, 1000.0]

    def test_sessions_counts_distinct_days(self):
        sets = [(date(2026, 8, 4), 10, 50000, "ROW"),
                (date(2026, 8, 6), 10, 50000, "ROW")]
        w = weekly_volume(sets, weeks=1, today=date(2026, 8, 6))[-1]
        assert w.sessions == 2


class TestTrend:
    def test_trend_is_last_minus_first_trained_week(self):
        series = [
            WeekVolume(date(2026, 7, 6), 1000.0, 8, 8, 2),
            WeekVolume(date(2026, 7, 13), 0.0, 0, 0, 0),
            WeekVolume(date(2026, 7, 20), 1400.0, 9, 9, 2),
        ]
        assert trend(series) == 400.0

    def test_trend_needs_two_trained_weeks(self):
        assert trend([WeekVolume(date(2026, 7, 6), 1000.0, 8, 8, 2)]) is None
