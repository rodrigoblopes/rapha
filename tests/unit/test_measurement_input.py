"""The measurement form parser: cm/kg → integer mm/g, validation. Invented data."""

from __future__ import annotations

from datetime import date

import pytest

from rapha.measurement_input import MeasurementError, measurement_from_form


def test_cm_and_kg_become_integer_mm_and_g():
    m = measurement_from_form(
        {"date": "2026-08-13", "waist": "93.5", "neck": "43.5", "weight": "83.9",
         "arm": "36"},
        today=date(2026, 8, 13),
    )
    assert m.on == date(2026, 8, 13)
    assert m.waist.value == 935  # 93.5 cm -> mm
    assert m.neck.value == 435
    assert m.arm.value == 360
    assert m.weight.value == 83900  # 83.9 kg -> g


def test_blank_fields_are_omitted_not_zeroed():
    m = measurement_from_form({"waist": "90", "neck": "", "chest": None},
                              today=date(2026, 8, 13))
    assert m.waist.value == 900
    assert m.neck is None
    assert m.chest is None


def test_missing_date_defaults_to_today():
    m = measurement_from_form({"waist": "90"}, today=date(2026, 8, 13))
    assert m.on == date(2026, 8, 13)


def test_a_future_date_is_rejected():
    with pytest.raises(MeasurementError, match="future"):
        measurement_from_form({"waist": "90", "date": "2026-09-01"},
                              today=date(2026, 8, 13))


def test_a_non_number_is_rejected():
    with pytest.raises(MeasurementError, match="not a number"):
        measurement_from_form({"waist": "abc"}, today=date(2026, 8, 13))


def test_an_out_of_range_value_is_rejected():
    with pytest.raises(MeasurementError, match="out of range"):
        measurement_from_form({"waist": "9000"}, today=date(2026, 8, 13))


def test_an_entirely_empty_form_is_rejected():
    with pytest.raises(MeasurementError, match="nothing to record"):
        measurement_from_form({"date": "2026-08-13"}, today=date(2026, 8, 13))


def test_notes_alone_is_enough_to_record():
    m = measurement_from_form({"notes": "felt lean today"}, today=date(2026, 8, 13))
    assert m.notes == "felt lean today"
