"""Parse Projeto 60 Dias training sheets (PDF) into structured sessions.

**The sheets use three different notations, and one layout is not enough.**

    A  `4 séries` + `1ª -15 rep/ 2ª -15 REP`   (Módulos 02-05, early sheets)
    B  set count and reps in separate columns: `4` | `15,15,15,15`  (Módulo 07)
    C  compressed: `5X15`, `2X12 / 2X10`, `3X10/10/10`  (later Intermediário/Avançado)

A parser written for A alone does not fail loudly on B and C — it quietly returns
one exercise per page and looks like it worked. So rather than reading fixed
column positions, each cell is *classified by its content*: which cell looks like
a name, which like a rep scheme, which like a rest interval. That survives all
three layouts and any fourth one built from the same vocabulary.

Reps are kept per set throughout. 15/15/12/12 is a pyramid, and flattening it to
4x12 would change the programme.
"""

from __future__ import annotations

import contextlib
import re
import unicodedata
from dataclasses import replace
from pathlib import Path

import pdfplumber

from ..units import Seconds
from .models import (
    Exercise,
    Programme,
    RotationEntry,
    Session,
    SetPrescription,
    SheetHeader,
)

# ── notation A: `1ª -15 rep`, `4ª - 12REP`, `5ª-12rep` ───────────────────────
_SET_REPS = re.compile(r"(\d+)\s*ª\s*-?\s*(\d+)\s*rep", re.IGNORECASE)
_SET_COUNT = re.compile(r"(\d+)\s*s[ée]ries?", re.IGNORECASE)

# ── notation B: a comma-separated list of rep counts ─────────────────────────
_COMMA_LIST = re.compile(r"^[\s\d,\n]+$")

# ── notation C: `5X15`, `2X12 / 2X10`, `3X10/10/10` ──────────────────────────
_SETS_X_REPS = re.compile(r"(\d+)\s*[xX]\s*(\d+(?:\s*/\s*\d+)*)")
_ONE_BLOCK = re.compile(r"(\d+)\s*[xX]\s*(\d+)")

_EACH_MINUTES = re.compile(r"de\s+(\d+)\s*minutos?\s*cada", re.IGNORECASE)
_BARE_MINUTES = re.compile(r"^\W*(\d+)\s*min", re.IGNORECASE)
_SECONDS = re.compile(r"(\d+)\s*(?:s\b|seg)", re.IGNORECASE)
_MINUTES = re.compile(r"(\d+)\s*(?:m\b|min)", re.IGNORECASE)

# "obs. NO final do treino CÁRDIO 30 min" — a cardio finisher, not a lifting row.
_FINISHER_CARDIO = re.compile(
    r"final\s+do\s+treino\s+c.rdio\s+(\d+)\s*min", re.IGNORECASE)

_DAY = re.compile(r"\bDIA\s+(\d+)", re.IGNORECASE)
_LEVEL = re.compile(
    r"\b(INICIANTES?|INTERMEDI[ÁA]RIOS?|AVAN[ÇC]ADOS?|ADAPTA[ÇC][ÃA]O|"
    r"TREINO\s+DE\s+1\s*HORA|TREINO\s+EM\s+CASA)\b(?:\s*(\d+))?",
    re.IGNORECASE,
)
_WEEKS = re.compile(r"SEGUIR\s+([^\n]+SEMANAS?)", re.IGNORECASE)

_BOILERPLATE = (
    "FICHA DE TREINO",
    "PARA ASSISTIR",
    "CLIQUE NO PLAY",
    "EM FRENTE AO EXERC",
    "SEGUIR",
    "MASCULINO",
    "FEMININO",
    "DESCANSO",
    "SEGUNDA-FEIRA",
    "TERÇA-FEIRA",
    "QUARTA-FEIRA",
    "QUINTA-FEIRA",
    "SEXTA-FEIRA",
    "SÁBADO",
    "DOMINGO",
)

#: Column headings, which look like exercise names but prescribe nothing.
_COLUMN_HEADINGS = {"SÉRIES", "REPETIÇÕES", "OBSERVAÇÃO", "TEMPO DE DESCANSO", "EXERCÍCIO"}

#: Below this, a "session" is a parse failure wearing a session's clothes.
MIN_PLAUSIBLE_EXERCISES = 3


def parse_sets(cell: str | None) -> list[SetPrescription]:
    """Turn any of the three notations into one SetPrescription per set."""
    if not cell:
        return []
    text = cell.strip()
    if not text:
        return []

    # A — per-set reps written out with ordinals.
    pairs = [(int(n), int(r)) for n, r in _SET_REPS.findall(text)]
    if pairs:
        return [SetPrescription(index=n, reps=r) for n, r in sorted(pairs)]

    declared = _SET_COUNT.search(text)

    # `N séries DE M MINUTO CADA` — a timed hold repeated N times.
    if each := _EACH_MINUTES.search(text):
        n = int(declared.group(1)) if declared else 1
        seconds = Seconds(int(each.group(1)) * 60)
        return [SetPrescription(index=i + 1, duration=seconds) for i in range(n)]

    # C — `5X15`, `2X12 / 2X10`, `3X10/10/10`.
    #
    # Split on `/` BEFORE matching. `2X12 / 2X10` is two blocks, but a regex that
    # allows `/`-continuation reads the first block as "2 sets of 12 and 2", which
    # is both wrong and plausible-looking.
    parts = [p.strip() for p in re.split(r"\s*/\s*", text) if p.strip()]
    reps_out: list[int] = []

    if len(parts) > 1 and all(_ONE_BLOCK.fullmatch(p) for p in parts):
        for p in parts:
            m = _ONE_BLOCK.fullmatch(p)
            reps_out += [int(m.group(2))] * int(m.group(1))
    elif m := _SETS_X_REPS.search(text):
        count = int(m.group(1))
        reps = [int(r) for r in re.findall(r"\d+", m.group(2))]
        # `3X10/10/10` spells out each set; `5X15` gives one count for all of them.
        reps_out = reps if len(reps) == count else [reps[0]] * count

    if reps_out:
        return [SetPrescription(index=i + 1, reps=r) for i, r in enumerate(reps_out)]

    # B — a bare comma list, possibly wrapped across lines.
    if "," in text and _COMMA_LIST.match(text):
        reps = [int(n) for n in re.findall(r"\d+", text)]
        return [SetPrescription(index=i + 1, reps=r) for i, r in enumerate(reps)]

    # A bare warm-up block: `5 min`.
    if (bare := _BARE_MINUTES.search(text)) and not declared:
        return [SetPrescription(index=1, duration=Seconds(int(bare.group(1)) * 60))]

    return []


def parse_rest(cell: str | None) -> Seconds | None:
    """Rest between sets. A range like `60S a 3min` yields its lower bound."""
    if not cell:
        return None
    candidates: list[int] = []
    if m := _SECONDS.search(cell):
        candidates.append(int(m.group(1)))
    if m := _MINUTES.search(cell):
        candidates.append(int(m.group(1)) * 60)
    return Seconds(min(candidates)) if candidates else None


def _looks_like_reps(text: str | None) -> bool:
    if not text or not text.strip():
        return False
    return bool(parse_sets(text))


def _looks_like_rest(text: str | None) -> bool:
    if not text or not text.strip():
        return False
    upper = text.upper()
    if "INTERVALO" in upper or "DESCANSO" in upper:
        return True
    # `60S`, `1 MIN` on their own — but not a rep scheme.
    bare_interval = re.fullmatch(r"[\s\d]*(?:S|SEG|MIN|M)[\sA-Za-z0-9]*", text.strip())
    return bool(bare_interval) and not _looks_like_reps(text)


def _looks_like_a_name(text: str | None) -> bool:
    if not text:
        return False
    stripped = text.strip()
    if not stripped or stripped.upper() in _COLUMN_HEADINGS:
        return False
    if _looks_like_reps(stripped):
        return False
    # A bare set-count line ("4 séries") is a prescription, not a name. It slips past
    # the reps check (it has no per-set scheme), and in a merged first-exercise cell it
    # would be picked as the name — dropping the real movement. Remove the set count;
    # if almost no letters remain, the line was only ever the count.
    return sum(c.isalpha() for c in _SET_COUNT.sub("", stripped)) >= 4


def parse_exercise_row(
    name: str, prescription: str | None, rest: str | None
) -> Exercise:
    sets = parse_sets(prescription)
    declared_match = _SET_COUNT.search(prescription or "")
    declared = int(declared_match.group(1)) if declared_match else None

    issues: list[str] = []
    if declared is not None and sets and len(sets) != declared:
        issues.append(
            f"sheet declares {declared} sets but {len(sets)} were listed — "
            "check the sheet before training this"
        )
    if not sets:
        issues.append("no sets could be read from the prescription")

    return Exercise(
        name=_clean(name),
        sets=sets,
        declared_sets=declared,
        rest=parse_rest(rest),
        issues=issues,
    )


def _exercise_from_cells(cells: list[str | None]) -> Exercise | None:
    """Classify a row's cells by content rather than by position.

    Layouts differ across modules; the vocabulary does not. Finding "the cell that
    looks like reps" works on all three notations, where a fixed column index works
    on exactly one.
    """
    filled = [c for c in cells if c and c.strip()]
    if not filled:
        return None

    rep_cells = [c for c in filled if _looks_like_reps(c)]
    if not rep_cells:
        return None

    prescription = max(rep_cells, key=lambda c: len(parse_sets(c)))
    remaining = [c for c in filled if c is not prescription]

    rest = next((c for c in remaining if _looks_like_rest(c)), None)
    name = next((c for c in remaining if _looks_like_a_name(c)), None)

    if name is None:
        # A merged cell: name and prescription in one string. Take the first line
        # that prescribes nothing — dropping the row would silently remove a
        # movement from the programme.
        lines = [ln.strip() for ln in prescription.splitlines() if ln.strip()]
        name = next((ln for ln in lines if _looks_like_a_name(ln)), None)
        if name is None:
            return None
        ex = parse_exercise_row(name, prescription, rest or prescription)
        return Exercise(
            ex.name,
            ex.sets,
            ex.declared_sets,
            ex.rest,
            [*ex.issues, "row was merged in the PDF; verify against the sheet"],
        )

    # Module 07 puts the set count in its own column; use it to cross-check.
    if not _SET_COUNT.search(prescription):
        for c in remaining:
            if c.strip().isdigit() and 1 <= int(c.strip()) <= 12:
                ex = parse_exercise_row(name, prescription, rest)
                declared = int(c.strip())
                issues = list(ex.issues)
                if ex.sets and len(ex.sets) != declared:
                    issues.append(
                        f"sheet declares {declared} sets but {len(ex.sets)} were listed"
                        " — check the sheet before training this"
                    )
                return Exercise(ex.name, ex.sets, declared, ex.rest, issues)

    return parse_exercise_row(name, prescription, rest)


_ROTATION_REPEAT = re.compile(
    r"DIA\s+(\d+)[^\n]*\n\s*VOLTA\s+O\s+TREINO\s+(?:DO\s+)?(?:DIA\s+)?(\d+)",
    re.IGNORECASE,
)
_ROTATION_REST = re.compile(r"DIA\s+(\d+)[^\n]*\n\s*DESCANSO\b", re.IGNORECASE)
_ROTATION_RESTART = re.compile(r"DIA\s+(\d+)[^\n]*\n\s*REINICIA\s+O\s+CICLO", re.IGNORECASE)

#: Sheet-wide instructions worth keeping: global rest, progressive load, cycle shape.
_NOTE_LINES = ("INTERVALO ENTRE", "ENTRE AS SÉRIES", "ENTRE OS EXERCÍCIOS",
               "CARGA PROGRESSIVA", "PROGRESSÃO DE CARGA", "OBS")


def parse_rotation(text: str) -> list[RotationEntry]:
    """Read the cycle page: which day repeats which, and which days are rest.

    The sheets prescribe three to five distinct training days and then rotate them
    for the rest of the block. Treating this page as a training day yields a day
    with no exercises; discarding it loses the only statement of how the programme
    actually runs across sixty days.
    """
    entries: dict[int, RotationEntry] = {}

    for day, repeats in _ROTATION_REPEAT.findall(text):
        entries[int(day)] = RotationEntry(day=int(day), repeats_day=int(repeats))
    for (day,) in (m.groups() for m in _ROTATION_REST.finditer(text)):
        entries[int(day)] = RotationEntry(day=int(day), is_rest=True)
    for (day,) in (m.groups() for m in _ROTATION_RESTART.finditer(text)):
        entries[int(day)] = RotationEntry(day=int(day), restarts_cycle=True)

    return [entries[d] for d in sorted(entries)]


def parse_notes(text: str) -> list[str]:
    seen: list[str] = []
    for line in (ln.strip() for ln in text.splitlines()):
        if line and any(k in line.upper() for k in _NOTE_LINES) and line not in seen:
            seen.append(line)
    return seen


def parse_header(header: str) -> SheetHeader:
    day = _DAY.search(header)
    if not day:
        raise ValueError(f"no 'DIA <n>' in sheet header: {header[:80]!r}")

    level_match = _LEVEL.search(header)
    level = _clean(level_match.group(1)).upper() if level_match else "DESCONHECIDO"
    sheet_number = (
        int(level_match.group(2)) if level_match and level_match.group(2) else None
    )
    weeks = _WEEKS.search(header)

    focus = ""
    for line in reversed([ln.strip() for ln in header.splitlines() if ln.strip()]):
        if any(b in line.upper() for b in _BOILERPLATE) or _DAY.search(line):
            continue
        focus = line
        break

    return SheetHeader(
        level=level,
        sheet_number=sheet_number,
        day=int(day.group(1)),
        focus=focus,
        weeks=weeks.group(1).strip() if weeks else None,
    )


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\n", " ")).strip()


def _norm(text: str) -> str:
    """Accent-stripped, punctuation-flattened key for matching a name to a link."""
    stripped = "".join(
        c for c in unicodedata.normalize("NFD", (text or "").lower())
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", stripped)).strip()


def _row_name(cells: list[str | None]) -> str:
    """The exercise name in a table row, or '' — the first real, non-prescription line."""
    for cell in cells or []:
        if not cell:
            continue
        for line in cell.split("\n"):
            if (sum(c.isalpha() for c in line) >= 4
                    and not re.search(r"s[ée]rie|\brep\b|FICHA|ASSISTIR|INTERVALO|"
                                      r"entre as s", line, re.IGNORECASE)):
                return line
    return ""


def _page_exercise_links(page) -> dict[str, str]:
    """Match each embedded video link on a page to the exercise at its height.

    The fichas carry a YouTube link per exercise (the "clique no play"). Each link
    has a vertical position; the exercise it belongs to is the table row at the
    same height. Keyed by the normalised exercise name.
    """
    links = [
        ((h["top"] + h["bottom"]) / 2, h["uri"])
        for h in (page.hyperlinks or []) if h.get("uri")
    ]
    if not links:
        return {}
    rows: list[tuple[float, str]] = []
    for table in page.find_tables():
        for row_obj, row_txt in zip(table.rows, table.extract(), strict=False):
            if not row_obj.bbox:
                continue
            name = _row_name(row_txt)
            if name:
                rows.append(((row_obj.bbox[1] + row_obj.bbox[3]) / 2, _norm(name)))
    out: dict[str, str] = {}
    for ly, uri in links:
        if rows:
            best = min(rows, key=lambda r: abs(r[0] - ly))
            out[best[1]] = uri
    return out


def parse_ficha(path: Path) -> Programme:
    """Parse one sheet PDF. Each page is one training day."""
    sessions: list[Session] = []
    warnings: list[str] = []
    rotation: list[RotationEntry] = []
    notes: list[str] = []
    level = "DESCONHECIDO"
    sheet_number: int | None = None
    weeks: str | None = None

    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            notes.extend(n for n in parse_notes(page_text) if n not in notes)

            # The cycle page lists several DIA n in a row with no exercises. It is
            # not a training day and must not be counted as one.
            if page_rotation := parse_rotation(page_text):
                rotation = page_rotation if len(page_rotation) > len(rotation) else rotation
                continue

            header: SheetHeader | None = None
            exercises: list[Exercise] = []

            for table in page.extract_tables():
                for row in table:
                    if not row:
                        continue
                    joined = "\n".join(c for c in row if c)
                    if header is None and "FICHA DE TREINO" in joined.upper():
                        with contextlib.suppress(ValueError):
                            header = parse_header(joined)
                        continue
                    if ex := _exercise_from_cells(list(row)):
                        exercises.append(ex)

            # The header sometimes sits outside any table; fall back to page text.
            if header is None:
                try:
                    header = parse_header(page_text)
                except ValueError:
                    header = None

            if header is None:
                if exercises:
                    warnings.append(
                        f"page {page_no}: {len(exercises)} exercises but no readable "
                        "'DIA <n>' header — day unknown, not imported"
                    )
                continue

            if len(exercises) < MIN_PLAUSIBLE_EXERCISES:
                # The important one. Without it, a layout this parser does not
                # understand yields one exercise per page, raises nothing, and
                # looks exactly like a successful parse.
                warnings.append(
                    f"page {page_no} (day {header.day}): only {len(exercises)} "
                    "exercises parsed — implausible for a training day, so this "
                    "sheet probably uses a layout the parser does not handle"
                )

            # Attach the demo-video link to each exercise, matched by height.
            links = _page_exercise_links(page)
            if links:
                exercises = [
                    replace(e, video_url=links.get(_norm(e.name), e.video_url))
                    for e in exercises
                ]

            level = header.level if header.level != "DESCONHECIDO" else level
            sheet_number = sheet_number or header.sheet_number
            weeks = weeks or header.weeks
            fin = _FINISHER_CARDIO.search(page_text)
            finisher = Seconds(int(fin.group(1)) * 60) if fin else None
            sessions.append(
                Session(day=header.day, focus=header.focus, exercises=exercises,
                        finisher_cardio_s=finisher)
            )

    if not sessions:
        warnings.append("no training days could be read from this sheet at all")

    return Programme(
        level=level,
        sheet_number=sheet_number,
        weeks=weeks,
        sessions=sessions,
        source_file=path.name,
        warnings=warnings,
        rotation=rotation,
        notes=notes,
    )
