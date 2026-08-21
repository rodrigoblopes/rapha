# Project — `Rapha`

> This file is the living **technical** spec for this project. It is loaded by Claude Code at
> every session and read before each significant action. Keep it current. When something
> changes, update this file as part of that change.
>
> **What does NOT belong here:** real body metrics, real health data, photos, tokens, or any
> excerpt of purchased course material. This file describes *how the system is built*, never
> *what the numbers are*.

---

## Project tier

**Tier:** `1 — Sandbox`

Build-to-learn, single user, no deployment target. TDD encouraged, not enforced. Shortcuts
allowed where flagged. Refactoring optional.

**Two departures from Tier 1's defaults, both stricter, both deliberate** (ADR-003):

1. **The repo is private**, not Tier 1's public default. It costs nothing and removes any
   question about health data, body photos or course material ending up world-readable.
2. **The repo holds code only.** See the data boundary below — this is not negotiable at any
   tier, because the repo path is inside OneDrive.

---

## Repository hosting

**Host:** private repo, personal account
**Visibility:** private
**Owner identity:** rodrigoblopes (personal)

If Rapha ever yields something generic worth publishing (a Garmin adapter, a PDF ficha
parser), it goes through the declassification process in the global `CLAUDE.md`: extracted to
a fresh repo with no shared history, sanitised, declared Tier 1 from creation.

---

## One-line description

A local-first personal health portal that ingests Garmin Connect, holds the user to the
**Projeto 60 Dias** training protocol and a **macro-first recomposition** diet, renders a
portal, and pushes structured workouts back to Garmin so they reach the watch.

---

## Goals and non-goals

**Goals:**
- One view of training, recovery and body-composition trend, from Garmin plus manual inputs.
- Projeto 60 Dias encoded faithfully — its sheets, its progression rule, its assessment.
- A weekly menu with foods, amounts and timing, hitting macro targets derived from
  *measured* energy expenditure rather than a formula.
- Structured workouts created in Garmin Connect so they sync to the watch over the air.
- A briefing rich enough for Claude to coach against, with every number traceable.

**Non-goals:**
- **Not medical advice.** The system produces observations against a named protocol and
  published nutrition science. Every decision is the user's.
- Not a food-logging app, not a social fitness platform, not multi-user, not hosted.
- Does not modify Garmin health data, activities, or account settings. The only write is
  workouts.

---

## Architecture overview

Adapters normalise sources into canonical records; a **pure** rules engine reads only the
store; the coaching narrative is Claude's job, not the code's. Rapha computes what is
deterministic and hands Claude a briefing to reason over.

```
  SOURCES              INGEST              STORE        RULES              OUTPUT
  ───────              ──────              ─────        ─────              ──────
  Garmin Connect ────► garmin/read    ┐
  Course PDFs ───────► protocol/*     ├──►  SQLite  ──► level          ──► portal
  Course video ──────► tools/         │   (canonical)  progression         + briefing
  Tape + photos ─────► manual entry   ┘                energy/menu     ──► garmin/write
                                                       cycle (day N)       (workouts only)
```

The seam that matters: **the rules engine must never be able to tell how a number arrived.**
Garmin's API, a `.FIT` export and a browser-retrieved file all land in the same tables with
a `source` tag. That is what lets a fallback rung swap in without touching anything
downstream.

---

## Tech stack

**Language:** Python 3.12
**Frameworks:** none (stdlib-first, deliberate constraint)
**Data store:** SQLite (single file, in `%RAPHA_HOME%`)
**Testing:** pytest · **Lint/format:** ruff
**Garmin client:** `garminconnect` (which brings `curl_cffi`)
**PDF parsing:** `pdfplumber`
**HTTP server:** stdlib `http.server`

Runtime dependencies stay tiny: `garminconnect`, `pdfplumber`. Adding to that list requires
justification in `DECISIONS.md`.

**Extraction tooling is not a runtime dependency.** `ffmpeg` and `faster-whisper` exist to
transcribe the course once, under `tools/`. They are never imported by `src/rapha/`.

---

## Security posture — read this before touching any file path

**The repository lives inside OneDrive** (`C:\Users\rodri\OneDrive\Claude\Projects\Rapha`).
Everything in it syncs to Microsoft's cloud. `.gitignore` does **not** prevent this — it only
stops Git. A gitignored folder in a synced directory is still a synced folder.

Therefore the repo holds **code only**. Everything real lives in `%RAPHA_HOME%` (default
`C:\Users\rodri\.rapha`), **outside** the OneDrive root:

| Path | Contents | Synced? |
|---|---|---|
| `...\OneDrive\...\Rapha\` | source, tests, docs | yes — fine, it's just code |
| `%RAPHA_HOME%\.env` | config; never a password | **no** |
| `%RAPHA_HOME%\garmin_tokens.json` | Garmin OAuth tokens | **no** |
| `%RAPHA_HOME%\rapha.db` | every metric, every session | **no** |
| `%RAPHA_HOME%\data\photos\` | body photos | **no** |
| `%RAPHA_HOME%\protocol\` | course-derived content + transcripts | **no** |
| `%RAPHA_HOME%\dist\` | the rendered portal | **no** |
| `%RAPHA_HOME%\venv\` | virtualenv | **no** (also spares OneDrive 1000s of files) |

⚠️ **Rule for the agent: never write a real body metric, a health figure, a photo, a token,
or an excerpt of course material into any file under the repo — including test fixtures,
comments, commit messages, and this file.** Test fixtures use invented people and invented
numbers.

**Course material is purchased IP** (ADR-002). Encoding the protocol for the user's own use
is fine; committing Cariani's PDFs, transcripts or diet models to Git is not. The repo holds
parsers and schemas; the extracted protocol is data in `%RAPHA_HOME%\protocol\`.

---

## The Garmin write path — read this before touching `garmin/`

Rapha writes to Garmin. That inverts MrW's *"nothing writes to a financial institution"*, so
the invariant becomes **narrowness instead of absence** (ADR-001):

- ⚠️ **`garmin/write.py` may create, schedule and delete WORKOUTS. Nothing else.** Never
  delete an activity, never modify health or body-composition data, never touch account
  settings, never change devices. If a new write is proposed, it needs an ADR.
- **`rapha push` is dry-run by default.** It prints exactly what it would create and requires
  explicit confirmation. A loop bug here spams your calendar with hundreds of workouts.
- **Only `garmin/auth.py` holds a credential**, and it holds **OAuth tokens, never a
  password.** `rapha login` is interactive once (handles MFA); everything afterwards refreshes.
- **The portal holds no credential** and must never import `rapha.garmin`.

---

## Environment variables

| Variable | Purpose | Required? | Example / default |
|---|---|---|---|
| `RAPHA_HOME` | Root for all data. Must be outside OneDrive. | No | `C:\Users\<you>\.rapha` |
| `GARMIN_EMAIL` | Garmin Connect login, for `rapha login` only | Yes | — |
| `GARMIN_TOKEN_STORE` | Where OAuth tokens live | No | `%RAPHA_HOME%` |
| `ATHLETE_*` | Height, birth year, sex — inputs to Navy body-fat and energy maths | Yes | see `.env.example` |
| `PROTOCOL_DIR` | Extracted Projeto 60 Dias data | No | `%RAPHA_HOME%\protocol` |
| `COURSE_DIR` | Source course material, read-only, for extraction | No | — |
| `DEFICIT_BPS` | Energy deficit vs measured TDEE, in basis points | No | `1750` (17.5%) |
| `PROTEIN_G_PER_KG_X10` | Protein target ×10 to stay integer | No | `19` (1.9 g/kg) |
| `PORTAL_PORT` | Local portal bind port | No | `8766` |

⚠️ **No password is ever stored.** `GARMIN_EMAIL` identifies the account; the password is
typed once at `rapha login` and never written to disk.

---

## Domain rules — the part that is easy to get wrong

### Projeto 60 Dias (governs training)

- The protocol is **60 days**, structured as numbered *fichas* that rotate on a schedule.
  Rapha tracks day N of 60 and which ficha is live. Rotating early or late breaks the method.
- ⚠️ **The load-progression rule is the method** (Módulo 17, video only, now transcribed and
  encoded in `rules/progression.py`). It is **double progression**: the ficha fixes the reps;
  you find the load that hits that rep target with cadenced form; you progress the load *only*
  when the target comes with facility, and you *hold* it when form breaks before the target.
  Increments are the smallest plate (2.5 → 5 kg) or the next dumbbell. The engine reports the
  decision and its reasoning; it **never prescribes a specific kilo** — only the lifter, feeling
  the set, chooses that. Do not "helpfully" turn this into a fixed-percentage scheme.
- Level (Iniciante / Intermediário / Avançado) is decided by Módulo 18's Auto Check **plus**
  the user's real Garmin training history — never guessed, never asked as a preference.
- ⚠️ **Exercise names are Portuguese and Garmin's workout API uses a fixed enum.** Mapping is
  an explicit table in `mapping/exercises.py`. An unmapped exercise **stops the push with a
  named error**. It must never silently substitute a similar lift — that means doing the
  wrong movement for eight weeks and never finding out.
- Rep-based strength steps in Garmin's workout API are **unverified** (see below). Until a
  spike settles it, assume nothing.

### Macro-first recomposition (governs nutrition)

- ⚠️ **TDEE comes from Garmin's measured daily expenditure, averaged over 14–28 days — not
  from Mifflin-St Jeor.** The watch measures what a formula estimates. Using the formula when
  measured data exists is throwing away the best input the system has.
- Deficit is a percentage of that measured TDEE (`DEFICIT_BPS`), not a fixed calorie number.
- Protein anchors at 1.6–2.2 g/kg bodyweight. Carbohydrate positioned around training; fat
  fills the remainder.
- Cariani's 26 diet models are **calorie-bucketed**. Rapha selects the model nearest the
  computed target and adapts it — his framework, selected by measured data. It does not
  invent a diet from scratch.
- Menu constraints are hard, not preferences: **household-compatible, batch-cooked,
  Brazilian staples where possible**, sourced from Australian supermarkets.
- ⚠️ **The cut-vs-bulk gate (Módulo 18, now transcribed).** Cariani's own rule: a man above
  **~15% body fat cuts first** (definition, calorie deficit, carbohydrate cycling); only at
  **≤15%** does he switch to a surplus for mass. So `DEFICIT_BPS` being a *deficit* is correct
  *only while* estimated body fat is above ~15% — which is almost certainly the case at the
  starting point. When the measurement series (below) shows ~15%, the direction flips to
  maintenance/surplus, and Rapha must surface that rather than keep cutting on autopilot.

### Módulo 18 Auto Check — the measurement ritual (video, transcribed)

Auto Check is an **anthropometric self-assessment repeated every 15 days**, not a one-off level
quiz. Log with a tape: **chest, arm (relaxed; plus *contracted* if intermediate/advanced),
waist at the navel relaxed, hip, thigh (both), calf (both), height, and wingspan**. Two
classifications follow: **build** from height-vs-wingspan (brevilíneo < normolíneo < longilíneo)
and **somatotype** (ecto/meso/endo), with **body-fat % read off Cariani's photo reference chart**
(men 8/12/15/20/25/30/35). The level split is by *training history and existing muscle*, which is
what makes it a shared human-plus-data call — the contracted measurements exist precisely because
an intermediate/advanced trainee already has muscle to contract. Rapha's `rules/level.py` supplies
the **objective Garmin-history half**; the person supplies the Auto Check half. This is why the
`Measurement` model carries waist/neck for the Navy estimate and why photos go to
`%RAPHA_HOME%\data\photos\<date>\` on a 15-day cadence.

### Body composition without a scale

- ⚠️ **Scale weight and photos cannot separate fat loss from muscle loss.** Rapha must never
  report a body-fat figure as if measured. Weekly waist + neck tape measurements through the
  **Navy formula** are the trend line; photos and strength progression corroborate.
- If a Garmin Index scale ever appears, `garmin/read.py` already pulls body composition and
  it becomes the primary series with no new code.

### Ordering between training and nutrition

Training prescribes; nutrition supports. When Garmin's recovery signals (HRV status, resting
HR, sleep, Body Battery) contradict the ficha's prescription, Rapha **says so and shows both**
— it does not silently deload, and it does not silently push through.

---

## Source-specific facts (verified 2026-07-22)

### Garmin Connect — the only automatic source

- ⚠️ **There is no legitimate personal API.** The Connect Developer Program is *"only for
  business use"* and rejects personal applications. Both read and write run on the unofficial
  `garminconnect` client, which uses the **same mobile SSO flow as the official Android app**.
  This is outside Garmin's ToS. Accepted knowingly (ADR-001).
- Reads: activities, sleep, HRV status, VO2max, resting HR, stress, Body Battery, training
  status/readiness, weight, body composition.
- Writes: workouts via Connect's **JSON workout API** (`upload_*_workout`, `schedule_workout`,
  `delete_workout`).
- ⚠️ **You cannot import a workout as a `.FIT` file.** Garmin's upload endpoint accepts
  *activities*, not workouts. Do not attempt it; it looks like it should work and does not.
- ⚠️ **Rep-based strength steps are contested and UNVERIFIED.** Garmin's own builder
  historically allowed only time-based steps; some third-party tools claim rep support.
  Settle empirically before relying on it; record the result here.
- **Workouts reach the watch over the air** once they exist in Connect (Connect → phone →
  watch). No cable is ever involved.
- Tokens auto-refresh; full re-login only when the refresh token expires.
- ⚠️ **First login is fragile, and the failure mode is misleading.** The mobile SSO endpoint
  rate-limits an IP with a plain `429` after a few attempts, and the client then falls back to
  the web *widget* flow. That widget's page title is `GARMIN Authentication Application` — a
  **generic** SSO title — and `garminconnect` reads "authentication application" as *email MFA*
  and asks for a code that was never sent. Verified 2026-07-22: **this account has no MFA**, no
  code email ever arrives, and the real problem is the `429`. Do **not** chase an MFA code in
  this situation. Wait for the rate limit to decay (tens of minutes) and retry; hammering it
  extends the block. `rapha login --mfa-file` exists for genuine authenticator-app MFA, not for
  this.
- **Cookie-reuse fallback exists but is permission-gated.** Chrome holds a logged-in Garmin
  session; decrypting its cookies to reuse it sidesteps the rate-limited login entirely. The
  harness classifier blocks the decryption script by default (it pattern-matches credential
  theft), so it runs only if the user adds a Bash allow-rule for the venv Python. Chrome 127+
  App-Bound Encryption (`v20` cookies) defeats DPAPI-only decryption, so this route is not
  guaranteed even with permission.

### Fallback ladder — the data is the requirement, the transport is negotiable

The unofficial client tracks a moving target and will break. Take whichever rung works, log
which one was used, land every record in the same tables.

1. **`garminconnect`** — first response to a break is `pip install --upgrade garminconnect`.
2. **Playwright against Connect using the existing Chrome profile** — already authenticated,
   so no password on disk. Handles read and write, including creating workouts through the UI.
3. **Chrome + the Claude extension, user-driven** — one-off retrieval and verification.
4. **Garmin's official account data export** — slow, manual, sanctioned; good bulk backfill.

---

## Design patterns used in this project

- **Integer units, always.** Grams, kilocalories, millimetres, seconds, basis points — all
  `int`. Floats are banned in every measurement path, exactly as `Money` is in MrW.
- **Every source emits canonical records** with a `source` tag. The rules engine cannot tell
  an API row from an export row.
- **Ingest replaces a window.** One source, one metric, one closed date range: delete the
  window, insert the batch, commit. Re-syncing is a no-op without row comparison.
- **The rules engine is pure.** State in, observations out. No I/O, no clock reads, no DB.
- **The write surface is one verb.** Workouts. Everything else is read-only by construction.

---

## Pipeline / schedule

| Trigger | Runs | Notes |
|---|---|---|
| daily | `rapha sync` | Pulls new Garmin data into SQLite |
| weekly | `rapha plan` | Next week's fichas + menu; `rapha push` sends workouts after confirmation |
| at logon | `rapha serve` | Portal on `127.0.0.1` by default; `PORTAL_HOST=0.0.0.0` exposes it to the LAN with NO auth (ADR-016) |
| weekly, by hand | the review | Claude reads the briefing and coaches |

---

## Common hurdles and their solutions

> Append-only. Future-you and Claude both consult this before re-debugging.

### The repo is inside OneDrive
**Symptom:** health data, photos or tokens sync to Microsoft's cloud.
**Cause:** the project path is inside the OneDrive root.
**Solution:** everything mutable lives in `%RAPHA_HOME%`, outside OneDrive.
**Why this isn't obvious:** `.gitignore` feels like protection. It governs Git, and OneDrive
is not Git.

---

## Post-implementation checklist

- [ ] Tests pass locally; `ruff check` clean.
- [ ] No real body metric, health figure, photo, token or course excerpt anywhere in the repo.
- [ ] No float in any measurement path.
- [ ] Idempotency verified — sync the same window twice, assert no duplicates.
- [ ] Error paths handled — Garmin 401/429, a malformed PDF, a missing transcript.
- [ ] Any new Garmin write justified by an ADR.
- [ ] Commits small and telling a coherent story.
- [ ] `CLAUDE.md` updated if architecture, stack, env or domain rules changed.
- [ ] `DECISIONS.md` updated if a significant choice was made.

---

## Notes for the agent

- The user is **new to TDD** and has asked to be taught it. Tier 1 does not enforce it, but
  where logic is worth testing (parsers, progression, energy maths, exercise mapping),
  propose the failing test first and explain why it is the right test.
- You are not a doctor and the user is not your patient. Frame every output as an observation
  against Projeto 60 Dias or published nutrition science, show the reasoning, leave the
  decision to the user. Avoid imperative health language.
- Where Garmin data suggests something clinical — resting HR trending sharply up, HRV
  collapse, sustained sleep disruption — say so plainly and suggest a doctor. Do not diagnose,
  and do not stay silent.
- When the protocol and the recovery data conflict, say so explicitly. That conflict is the
  interesting part of this system, not a bug to smooth over.
