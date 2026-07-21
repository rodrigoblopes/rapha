"""The shape of a training programme, once extracted from the sheets."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..units import Seconds


@dataclass(frozen=True, slots=True)
class SetPrescription:
    """One set. Either a rep count or a duration — never both, never neither."""

    index: int
    reps: int | None = None
    duration: Seconds | None = None

    def __post_init__(self) -> None:
        if (self.reps is None) == (self.duration is None):
            raise ValueError(
                f"set {self.index} must prescribe either reps or a duration, not "
                f"both and not neither (got reps={self.reps}, duration={self.duration})"
            )


@dataclass(frozen=True, slots=True)
class Exercise:
    """One movement and its prescription.

    ``sets`` is a list rather than a count because the sheets pyramid: 15/15/12/12
    is four different prescriptions, and collapsing it to "4x12" would quietly
    change the programme.

    ``issues`` records anything the parser could not reconcile — most commonly a
    declared set count that disagrees with the reps actually listed. Recorded
    rather than raised, so one odd row does not abort a whole extraction, and
    rather than ignored, so it cannot silently become the prescription.
    """

    name: str
    sets: list[SetPrescription]
    declared_sets: int | None = None
    rest: Seconds | None = None
    issues: list[str] = field(default_factory=list)

    @property
    def is_timed(self) -> bool:
        return bool(self.sets) and all(s.reps is None for s in self.sets)


@dataclass(frozen=True, slots=True)
class SheetHeader:
    level: str
    sheet_number: int | None
    day: int
    focus: str
    weeks: str | None = None


@dataclass(frozen=True, slots=True)
class Session:
    """One training day: a header plus its exercises, in order."""

    day: int
    focus: str
    exercises: list[Exercise]

    @property
    def issues(self) -> list[str]:
        return [f"{e.name}: {i}" for e in self.exercises for i in e.issues]


@dataclass(frozen=True, slots=True)
class RotationEntry:
    """What happens on a given day of the cycle.

    The sheets prescribe only a handful of distinct training days and then rotate
    them: day 5 repeats day 1, Sunday is rest, day 10 restarts. Without this the
    programme looks like it runs out after four days.
    """

    day: int
    repeats_day: int | None = None
    is_rest: bool = False
    restarts_cycle: bool = False


@dataclass(frozen=True, slots=True)
class Programme:
    """One sheet — a level, a number, and the days it prescribes."""

    level: str
    sheet_number: int | None
    weeks: str | None
    sessions: list[Session]
    source_file: str = ""
    #: Structural problems with the *parse*, as opposed to a single odd row:
    #: a sheet that yielded no days, or a day with an implausibly short exercise
    #: list. These are the failures that otherwise look like success.
    warnings: list[str] = field(default_factory=list)
    #: How the training days repeat across the cycle, from the sheet's last page.
    rotation: list[RotationEntry] = field(default_factory=list)
    #: Free-text prescriptions that apply to the whole sheet — global rest
    #: intervals, progressive-load instructions, the coach's notes.
    notes: list[str] = field(default_factory=list)

    @property
    def issues(self) -> list[str]:
        return [f"day {s.day} {i}" for s in self.sessions for i in s.issues]

    @property
    def is_trustworthy(self) -> bool:
        return not self.warnings and bool(self.sessions)
