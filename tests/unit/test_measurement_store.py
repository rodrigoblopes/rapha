"""Measurement storage: merge-upsert, the new fields, latest, and migration."""

from __future__ import annotations

import sqlite3
from datetime import date

from rapha.db import Store
from rapha.models import Measurement, Source
from rapha.units import Grams, Millimetres


def _mm(v):
    return Millimetres(v)


def test_a_weighin_and_a_tape_entry_share_a_date_without_clobbering(tmp_path):
    with Store(tmp_path / "r.db") as s:
        s.record_measurement(Measurement(on=date(2026, 8, 13), source=Source.MANUAL,
                                         waist=_mm(935), neck=_mm(435), arm=_mm(360)))
        s.record_measurement(Measurement(on=date(2026, 8, 13),
                                         source=Source.GARMIN_BROWSER, weight=Grams(83900)))
        m = s.latest_measurement()
        assert m.waist.value == 935 and m.arm.value == 360  # tape survives
        assert m.weight.value == 83900                      # weight added


def test_editing_one_field_leaves_the_others(tmp_path):
    with Store(tmp_path / "r.db") as s:
        s.record_measurement(Measurement(on=date(2026, 8, 13), waist=_mm(935),
                                         neck=_mm(435)))
        s.record_measurement(Measurement(on=date(2026, 8, 13), waist=_mm(925)))  # only waist
        m = s.latest_measurement()
        assert m.waist.value == 925  # updated
        assert m.neck.value == 435   # untouched


def test_the_new_fields_round_trip(tmp_path):
    with Store(tmp_path / "r.db") as s:
        s.record_measurement(Measurement(
            on=date(2026, 8, 13), chest=_mm(1050), thigh=_mm(600),
            shoulders=_mm(1200), calf=_mm(390), wingspan=_mm(1725), notes="ok"))
        m = s.latest_measurement()
        assert m.chest.value == 1050 and m.thigh.value == 600
        assert m.shoulders.value == 1200 and m.calf.value == 390
        assert m.wingspan.value == 1725 and m.notes == "ok"


def test_latest_measurement_is_the_most_recent_date(tmp_path):
    with Store(tmp_path / "r.db") as s:
        s.record_measurement(Measurement(on=date(2026, 8, 1), waist=_mm(940)))
        s.record_measurement(Measurement(on=date(2026, 8, 13), waist=_mm(930)))
        assert s.latest_measurement().on == date(2026, 8, 13)


def test_none_latest_when_empty(tmp_path):
    with Store(tmp_path / "r.db") as s:
        assert s.latest_measurement() is None


def test_an_old_schema_db_is_migrated_with_the_new_columns(tmp_path):
    # Build a measurements table with only the original columns, then open it.
    path = tmp_path / "r.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE measurements (on_date TEXT PRIMARY KEY, source TEXT, "
                "weight_g INTEGER, waist_mm INTEGER, neck_mm INTEGER, hip_mm INTEGER)")
    con.execute("INSERT INTO measurements VALUES ('2026-07-24','manual',NULL,935,435,NULL)")
    con.commit()
    con.close()

    with Store(path) as s:
        cols = {r["name"] for r in
                s._conn.execute("PRAGMA table_info(measurements)").fetchall()}
        assert {"chest_mm", "arm_mm", "thigh_mm", "shoulders_mm",
                "calf_mm", "wingspan_mm", "notes"} <= cols
        # the pre-existing row still reads, and a new field can be merged in
        s.record_measurement(Measurement(on=date(2026, 7, 24), chest=_mm(1050)))
        m = s.latest_measurement()
        assert m.waist.value == 935 and m.chest.value == 1050
