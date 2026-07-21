# Rapha

A local-first personal health portal. It ingests Garmin Connect, holds you to the
**Projeto 60 Dias** training protocol and a **macro-first recomposition** diet, renders a
portal you can open in a browser, and pushes structured workouts back to Garmin so they
reach your watch.

Private, single-user, runs on one machine. Nothing is hosted.

> **Not medical advice.** Rapha reports observations against a named protocol and published
> nutrition science, shows its reasoning, and leaves every decision to you.

---

## The data boundary — read this first

**The repository holds code only.** Its path is inside OneDrive, so everything in it syncs
to Microsoft's cloud, and `.gitignore` does not stop that — it governs Git, and OneDrive is
not Git.

Everything real lives in **`%RAPHA_HOME%`** (default `C:\Users\<you>\.rapha`), outside the
sync root: Garmin tokens, the database, body photos, the rendered portal, and all
course-derived material. See `DECISIONS.md` ADR-002.

Never commit a real body metric, a health figure, a photo, a token, or an excerpt of course
material. Test fixtures use invented people and invented numbers.

---

## Setup

```powershell
# 1. Virtualenv, outside OneDrive
python -m venv $env:USERPROFILE\.rapha\venv
& $env:USERPROFILE\.rapha\venv\Scripts\Activate.ps1

# 2. Install
pip install -e ".[dev]"

# 3. Configure — copy the contract, fill it in THERE, not in the repo
copy .env.example $env:USERPROFILE\.rapha\.env

# 4. Log in to Garmin once (prompts for password + MFA, stores tokens only)
rapha login
```

## Commands

| Command | Does |
|---|---|
| `rapha login` | Interactive Garmin login. Stores OAuth tokens, **never a password**. |
| `rapha sync` | Pulls Garmin data into SQLite. Idempotent — re-running a window is a no-op. |
| `rapha extract` | Parses the course into `%RAPHA_HOME%\protocol\`. One-time. |
| `rapha assess` | Decides your Projeto 60 Dias level from real training history, with evidence. |
| `rapha plan` | Next week's fichas and menu — foods, amounts, timing. |
| `rapha push` | Creates workouts in Garmin Connect. **Dry-run by default.** |
| `rapha report` | Renders the portal to `%RAPHA_HOME%\dist`. |
| `rapha serve` | Serves the portal on `127.0.0.1`. Holds no credential. |

## The Garmin write path

Rapha writes to Garmin, which is unusual for a tool like this, so the safety property is
**narrowness**: `garmin/write.py` may create, schedule and delete **workouts and nothing
else** — never an activity, never health data, never account settings. `rapha push` is
dry-run by default and requires explicit confirmation.

There is no legitimate personal Garmin API; the client is unofficial and outside Garmin's
ToS. That trade is documented and accepted in ADR-001, along with the fallback ladder for
when it breaks.

## Development

```powershell
pytest          # tests use invented fixtures only
ruff check .
```

`CLAUDE.md` is the living technical spec — architecture, domain rules, and the traps worth
knowing before changing anything. `DECISIONS.md` records why the significant choices were
made. Read both before contributing.
