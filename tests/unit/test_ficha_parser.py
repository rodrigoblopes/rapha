"""Parsing Projeto 60 Dias training sheets.

Fixtures reproduce the *shape* of the sheets with invented numbers. No course
content is reproduced here — the repo holds parsers, not the material (ADR-002).
"""

import pytest

from rapha.protocol.ficha_pdf import (
    _exercise_from_cells,
    parse_exercise_row,
    parse_header,
    parse_notes,
    parse_rest,
    parse_rotation,
    parse_sets,
)
from rapha.units import Seconds


class TestSetPrescriptions:
    def test_per_set_reps_are_kept_separately(self):
        """15/15/12/12 is a pyramid. Flattening it to 4x12 changes the programme."""
        sets = parse_sets("4 séries\n1ª -15 rep/ 2ª -15 REP\n3ª -12 REP / 4ª - 12REP")

        assert [s.reps for s in sets] == [15, 15, 12, 12]

    def test_case_and_spacing_vary_across_the_sheets(self):
        # Real sheets mix `1ª -15 rep`, `4ª - 12REP` and `5ª-12rep` on one line.
        sets = parse_sets("5 séries\n1ª -20 rep/ 2ª -20 REP\n3ª -18 REP / 4ª -18 REP/ 5ª-16rep")

        assert [s.reps for s in sets] == [20, 20, 18, 18, 16]

    def test_a_time_based_exercise_has_duration_not_reps(self):
        sets = parse_sets("4 séries\nDE 1 MINUTO CADA")

        assert len(sets) == 4
        assert all(s.reps is None for s in sets)
        assert all(s.duration == Seconds(60) for s in sets)

    def test_a_warmup_is_a_single_timed_block(self):
        sets = parse_sets("5 min")

        assert len(sets) == 1
        assert sets[0].duration == Seconds(300)

    def test_reps_are_ordered_by_their_set_number_not_by_position(self):
        sets = parse_sets("3 séries\n3ª -8 REP\n1ª -12 rep/ 2ª -10 REP")

        assert [s.reps for s in sets] == [12, 10, 8]


class TestTheOtherTwoNotations:
    """The course uses three notations, not one.

    Modules 02-05's early sheets write `4 séries / 1ª -15 rep`. Module 07 puts the
    set count and a comma list in separate columns. The later Intermediário and
    Avançado sheets compress it to `5X15` or `2X12 / 2X10`. A parser that knows
    only the first silently returns one exercise per page and looks like it worked.
    """

    def test_a_comma_list_is_one_entry_per_set(self):
        assert [s.reps for s in parse_sets("15,15,15,15")] == [15, 15, 15, 15]

    def test_a_descending_comma_list(self):
        assert [s.reps for s in parse_sets("12,10,8,6,5")] == [12, 10, 8, 6, 5]

    def test_a_comma_list_wrapped_across_lines(self):
        assert [s.reps for s in parse_sets("25,25,25\n25,25,25")] == [25] * 6

    def test_sets_times_reps(self):
        assert [s.reps for s in parse_sets("5X15")] == [15] * 5

    def test_two_blocks_of_sets_times_reps(self):
        assert [s.reps for s in parse_sets("2X12 / 2X10")] == [12, 12, 10, 10]

    def test_a_drop_set_written_as_sets_times_slashed_reps(self):
        assert [s.reps for s in parse_sets("3X10/10/10")] == [10, 10, 10]

    def test_a_lone_number_is_not_a_rep_scheme(self):
        # The set-count column in module 07 is just "4". On its own it prescribes
        # nothing, and guessing 4x1 would be worse than admitting ignorance.
        assert parse_sets("4") == []


class TestRestVariants:
    def test_seconds_written_as_60S(self):
        assert parse_rest("60S") == Seconds(60)

    def test_a_range_takes_the_lower_bound(self):
        # "60S a 3min" is a range. The lower bound is the prescribed minimum;
        # inventing a midpoint would be precision the sheet does not have.
        assert parse_rest("60S a 3min") == Seconds(60)


class TestDisagreementIsReportedNotSwallowed:
    """A sheet that says 5 séries but lists 4 is a parse to distrust.

    Silently returning four sets would mean training a set short for weeks with
    nothing to indicate why. The count is checked and the discrepancy recorded.
    """

    def test_declared_and_parsed_counts_must_agree(self):
        ex = parse_exercise_row("LEG PRESS", "5 séries\n1ª -12 rep/ 2ª -12 REP", "1 MIN INTERVALO")

        assert ex.declared_sets == 5
        assert len(ex.sets) == 2
        assert ex.issues, "a 5-vs-2 mismatch must be recorded"

    def test_a_clean_row_has_no_issues(self):
        ex = parse_exercise_row(
            "LEG PRESS", "2 séries\n1ª -12 rep/ 2ª -12 REP", "1 MIN INTERVALO"
        )

        assert ex.issues == []


class TestRest:
    def test_minutes(self):
        assert parse_rest("1 MIN INTERVALO\nentre as séries") == Seconds(60)

    def test_seconds(self):
        assert parse_rest("45 SEG INTERVALO") == Seconds(45)

    def test_absent(self):
        assert parse_rest("") is None
        assert parse_rest(None) is None


class TestRotation:
    """The sheet's last page is the cycle, not a training day.

    It was originally parsed as a day with zero exercises, which produced a warning
    on literally every sheet in the course. The page is not noise — it is the only
    statement of how three or four distinct days stretch across sixty.
    """

    PAGE = (
        "DIA 5\nVOLTA O TREINO DO DIA 1\n"
        "DIA 6\nVOLTA O TREINO DO DIA 2\n"
        "DIA 7 (DOMINGO)\nDESCANSO\n"
        "DIA 8\nVOLTA O TREINO DIA 3\n"
        "DIA 10\nREINICIA O CICLO (TREINO DIA 1)\n"
    )

    def test_repeated_days_map_back_to_their_original(self):
        rot = {e.day: e for e in parse_rotation(self.PAGE)}

        assert rot[5].repeats_day == 1
        assert rot[6].repeats_day == 2
        assert rot[8].repeats_day == 3, "'VOLTA O TREINO DIA 3' omits the 'DO'"

    def test_rest_days_are_marked_rest_not_repeats(self):
        rot = {e.day: e for e in parse_rotation(self.PAGE)}

        assert rot[7].is_rest
        assert rot[7].repeats_day is None

    def test_the_restart_is_recorded(self):
        rot = {e.day: e for e in parse_rotation(self.PAGE)}
        assert rot[10].restarts_cycle

    def test_entries_come_back_in_day_order(self):
        assert [e.day for e in parse_rotation(self.PAGE)] == [5, 6, 7, 8, 10]

    def test_an_ordinary_training_page_has_no_rotation(self):
        assert parse_rotation("DIA 1\nPERNAS\nCADEIRA EXTENSORA 4X15") == []


class TestSheetWideNotes:
    def test_global_rest_and_progression_instructions_are_kept(self):
        notes = parse_notes(
            "DESCANSO:\n1 MIN ENTRE AS SÉRIES\n2 MIN ENTRE OS EXERCÍCIOS.\n"
            "OBS. CARGA PROGRESSIVA\nDIA 5\n"
        )

        assert any("ENTRE AS SÉRIES" in n for n in notes)
        assert any("CARGA PROGRESSIVA" in n.upper() for n in notes)


class TestMergedFirstExerciseCell:
    """The first exercise of a day sometimes merges into one PDF cell:
    ``"4 séries\\n<NAME>\\n1ª-15/2ª-15\\n3ª-12/4ª-12"``. The bare set-count line must
    not win as the name — that once dropped the movement entirely."""

    CELL = ("4 séries\nINVENTED MACHINE PRESS\n"
            "1ª -15 rep/ 2ª -15 REP\n3ª -12 REP / 4ª - 12 REP")

    def test_the_movement_name_is_kept_not_the_set_count(self):
        ex = _exercise_from_cells([self.CELL, None, None, "1 MIN INTERVALO"])
        assert ex is not None
        assert "INVENTED MACHINE PRESS" in ex.name
        assert "série" not in ex.name.lower()

    def test_the_per_set_reps_survive_the_merge(self):
        ex = _exercise_from_cells([self.CELL, None, None, "1 MIN INTERVALO"])
        assert [s.reps for s in ex.sets] == [15, 15, 12, 12]


class TestCardioFinisher:
    def test_a_finisher_line_is_detected_with_its_minutes(self):
        from rapha.protocol.ficha_pdf import _FINISHER_CARDIO
        m = _FINISHER_CARDIO.search("obs. NO final do treino CÁRDIO 30 min")
        assert m and m.group(1) == "30"

    def test_a_plain_day_has_no_finisher(self):
        from rapha.protocol.ficha_pdf import _FINISHER_CARDIO
        assert _FINISHER_CARDIO.search("AQUECIMENTO NA ESTEIRA. só musculação.") is None


class TestHeader:
    def test_day_number_and_muscle_groups(self):
        header = (
            "FICHA DE TREINO\nINTERMEDIÁRIO 1 / SEGUIR 1ª,2ª,3ª E 4ª SEMANAS\n"
            "PARA ASSISTIR O VÍDEO\nCLIQUE NO PLAY QUE ESTÁ\n"
            "DIA 2 EM FRENTE AO EXERCÍCIO\nPEITO/ BÍCEPS /TRÍCEPS"
        )
        parsed = parse_header(header)

        assert parsed.day == 2
        assert parsed.level == "INTERMEDIÁRIO"
        assert parsed.sheet_number == 1
        assert "PEITO" in parsed.focus

    def test_the_boilerplate_is_not_mistaken_for_the_focus(self):
        # "PARA ASSISTIR O VÍDEO / CLIQUE NO PLAY" is instructions, not a muscle group.
        header = (
            "FICHA DE TREINO\nAVANÇADO 3 / SEGUIR 1ª E 2ª SEMANAS\n"
            "PARA ASSISTIR O VÍDEO\nCLIQUE NO PLAY QUE ESTÁ\n"
            "DIA 1 EM FRENTE AO EXERCÍCIO\nPERNAS"
        )
        parsed = parse_header(header)

        assert parsed.focus == "PERNAS"
        assert "PLAY" not in parsed.focus

    def test_a_header_without_a_day_is_refused(self):
        with pytest.raises(ValueError):
            parse_header("FICHA DE TREINO\nsomething unexpected")
