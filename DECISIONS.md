# Architectural Decision Records — Rapha

Append-only. Each record states the decision, the reasoning, and what we rejected.
Technical reasoning only — no personal health content.

---

## ADR-001 — Rapha writes to Garmin; the invariant becomes narrowness, not absence

**Date:** 2026-07-22

MrW's central security property was *"nothing writes to a financial institution, read-only by
construction."* Rapha cannot inherit it: pushing structured workouts to Garmin Connect so they
sync to the watch is a requested feature, not an accident.

Research settled the constraints. Garmin's [Connect Developer Program](https://developer.garmin.com/gc-developer-program/program-faq/)
is *"only for business use"* and rejects personal applications — **there is no legitimate
personal API, for read or write.** The working route is the unofficial `garminconnect` client,
which authenticates through the same mobile SSO flow as Garmin's official Android app.

**Decision:** accept the write path, and replace *absence* with *narrowness* as the invariant.

- `garmin/write.py` may **create, schedule and delete workouts. Nothing else.** Never delete an
  activity, never modify health or body-composition data, never touch account settings. A new
  write verb requires its own ADR.
- **`rapha push` is dry-run by default**, prints exactly what it would create, and requires
  explicit confirmation. The failure mode this guards is not subtle: a loop bug writes hundreds
  of workouts into a real calendar.
- **Only `garmin/auth.py` holds a credential, and it holds OAuth tokens — never a password.**
  `rapha login` is interactive once and handles MFA; everything after that refreshes.
- The portal holds no credential and must never import `rapha.garmin`.

**Accepted risks, stated plainly:** the client is unofficial and outside Garmin's ToS (low
practical risk for single-user personal polling, not zero), and it breaks whenever Garmin
changes something. The fallback ladder in `CLAUDE.md` exists for the second problem.

**Two facts found in research that shape the implementation:** you **cannot** import a workout
as a `.FIT` file — Garmin's upload endpoint takes *activities*, not workouts — and rep-based
strength steps are **contested and unverified**, so they get a spike rather than an assumption.

**Rejected:** waiting for official access (does not exist for individuals); the browser as the
*primary* transport (slower, more fragile, and needs a stored password or a persistent
profile, where the mobile SSO flow needs neither).

---

## ADR-002 — Repo holds code only: data outside OneDrive, course IP outside Git

**Date:** 2026-07-22

The project path is inside the OneDrive root, so every file in it syncs to Microsoft's cloud.
`.gitignore` does not prevent this — it governs Git, and OneDrive is not Git. This is the same
trap MrW's ADR-002 documented, and it now applies to body photos, health metrics and Garmin
tokens instead of bank transactions.

**Decision:** the repo contains source, tests and docs. Everything else lives in `%RAPHA_HOME%`
(default `C:\Users\rodri\.rapha`), outside the sync root: tokens, the database, body photos,
the rendered portal, and the virtualenv.

**The same rule resolves a second, unrelated problem: copyright.** Projeto 60 Dias is purchased
material. Encoding its protocol for the buyer's own use is fine; committing Cariani's PDFs,
transcripts or diet models into a Git repository is redistribution, and it would also bloat the
repo with 63 MB of content that is not code. So the boundary is drawn once and serves both
purposes: **the repo holds parsers and schemas; the extracted protocol is data in
`%RAPHA_HOME%\protocol\`.**

Consequence worth noting: a fresh clone of this repo does nothing useful until extraction has
run. That is correct. The repo is the machine, not the material.

**Rejected:** OneDrive per-folder sync exclusions (configured in a GUI, not version-controlled,
silently stop applying if a folder is recreated). Also rejected committing the extracted
protocol as JSON "because it's derived data" — derived from copyrighted work is still the work.

---

## ADR-003 — Tier 1, with two departures in the stricter direction

**Date:** 2026-07-22

The user declared **Tier 1 (Sandbox)** — build-to-learn, single user, risk understood. That
sets the *methodology* rigour: TDD encouraged not enforced, refactoring optional, shortcuts
allowed where flagged.

**Decision:** accept Tier 1 for rigour, and depart from two of its defaults, both stricter:

1. **Private repo**, not Tier 1's public default. It costs nothing, it is reversible in the
   safe direction, and it removes any question about health data or purchased course material
   becoming world-readable. Revisit if Rapha ever yields something generic worth publishing —
   through declassification, not a visibility toggle.
2. **The data boundary of ADR-002 applies at any tier.** "Never publish real personal data" is
   listed in the global methodology as applying *regardless of tier*, so Tier 1 does not relax
   it.

**This is the third project to hit the same methodology gap.** MrW's ADR-001 raised it: the
tier ladder ties hosting to *purpose* (learn vs. earn) rather than to *data sensitivity*, so a
build-to-learn project holding real health data has no correct slot. Rapha lands in the same
hole from the other direction — correctly Tier 1 by purpose, unacceptable Tier 1 by data.
**Proposal for the methodology repo: make `sensitivity` (public / private / restricted) an
axis orthogonal to the build-to-learn/earn tier.**

**Rejected:** Tier 3 (as MrW chose). Tier 3's full TDD enforcement and security baseline are
disproportionate to a single-user experiment, and adopting it would have bought only the
private hosting — which a two-line departure buys more honestly.

---

## ADR-004 — Local Whisper for speech, `claude-video` for movement

**Date:** 2026-07-22

The course is 173 files: 100 PDFs that extract cleanly (verified with pdfplumber — real text
layers, real tables, no OCR needed) and 59 videos totalling 6.2 GB. The split is not
cosmetic: the *fichas*, the 26 calorie-calculated diet models and the TACO food composition
table are all PDF, but **Módulo 17 *Como Progredir Cargas* — the load-progression rule, which
is arguably the method itself — exists only as video**, as do Módulo 16 (training models),
Módulo 18 (Auto Check) and Módulo 20 (nutrition).

The user proposed [`claude-video`](https://github.com/bradautomates/claude-video) for all of it.
Investigated: it fits, but it **requires a Groq or OpenAI API key for local files** — it cannot
drive a local Whisper — and its frame extraction bills image tokens (~197 per frame; ~20k for a
49-minute video).

**Decision:** split by where the information actually lives.

- **`faster-whisper` locally on the RTX 3070** for the speech modules (16, 17, 18, 20, 23, 24,
  and the rest). Free, private, no API key, no third-party upload of purchased material, and
  minutes of GPU time. Talking heads carry nothing visual, so frames would be pure cost.
- **`claude-video /watch`** for the modules where the information *is* visual — Módulo 15's 13
  exercise demonstrations and Módulo 13 mobility — where the movement must be seen to write
  form cues and map exercises to Garmin's taxonomy correctly.

**Dependency note:** `ffmpeg` and `faster-whisper` are **extraction tooling, not runtime
dependencies.** They live under `tools/` and are never imported by `src/rapha/`. The runtime
dependency list stays at `garminconnect` + `pdfplumber`.

**Rejected:** `claude-video` for all 59 videos (cost with no information gain on talking-head
modules, plus shipping ~15 hours of purchased course audio to a third party). Also rejected
skipping video entirely — it would leave Rapha applying generic double-progression to
Cariani's sheets while claiming to run his programme, which is worse than not claiming it.

---

## ADR-005 — TDEE is measured, not estimated

**Date:** 2026-07-22

Every diet calculator starts from a predictive equation — Mifflin-St Jeor, Harris-Benedict —
multiplied by a hand-waved activity factor. Those equations exist because most people have no
way to measure energy expenditure. This user wears a device that estimates it daily from heart
rate, movement and personal parameters.

**Decision:** TDEE is **Garmin's measured daily expenditure averaged over 14–28 days**, and the
deficit is a percentage of that (`DEFICIT_BPS`), not a fixed calorie number.

**Reasoning:** the activity multiplier is the largest error term in the formula approach, and
it is precisely the term the watch replaces with observation. A 14–28 day window is long enough
to average out rest days, travel and a heavy training week; a shorter window would chase noise
and whipsaw the target, and a longer one would lag a real change in training volume.

**Consequence, accepted:** the target moves as training load moves, which is the point — but it
means the menu is regenerated against a moving denominator, so Rapha must show *which* window
produced the current target rather than presenting a number with no provenance.

**Rejected:** Mifflin-St Jeor as primary (throws away the best input the system has). Kept as a
**sanity check only** — if measured TDEE and the formula disagree wildly, that indicates a data
problem (a miscalibrated device, a missing week) and Rapha should say so rather than trust
either silently.

---

## ADR-006 — Video transcription: local Whisper on the GPU, CUDA vendored into the venv

**Date:** 2026-07-22

ADR-004 chose local `faster-whisper` for the speech modules over a hosted transcriber, to keep
purchased material off third-party servers. Making that actually run surfaced two decisions
worth recording, because both are the kind of thing a future setup will hit again.

**`ffmpeg` is a local binary, not a system install.** It is downloaded to
`%RAPHA_HOME%\tools\ffmpeg.exe` and referenced by path — no PATH edit, no admin, no winget. This
matches the project's "everything mutable lives outside the repo, nothing touches the system"
posture, and it means the toolchain is reproducible by re-running one download rather than by
remembering a global install. (The first mirror, gyan.dev, throttled to a crawl; the BtbN
GitHub release served 160 MB in seconds. Prefer the latter.)

**GPU inference needs CUDA 12 DLLs, and they are vendored into the venv, not installed
system-wide.** CTranslate2 (faster-whisper's backend) fails with `cublas64_12.dll not found` on
a bare machine. Rather than a system CUDA install, the `nvidia-cublas-cu12` and
`nvidia-cudnn-cu12` pip wheels are installed into the venv and `tools/transcribe.py` adds their
`bin` directories via `os.add_dll_directory` at startup. The entire CUDA dependency then lives
inside `%RAPHA_HOME%\venv`, deletable with the venv, invisible to the rest of the machine. On
the RTX 3070 the medium model runs comfortably; it falls back to CPU int8 if CUDA is absent.

**Consequence:** transcription is resumable (already-done files are skipped) and self-contained.
The transcripts land in `%RAPHA_HOME%\protocol\transcripts`, never the repo (ADR-002).

**Payoff, concretely:** Módulo 17 (Como Progredir Cargas) transcribed cleanly, and its
load-progression rule — the linchpin CLAUDE.md flagged — is now encoded in `rules/progression.py`
from Cariani's own words rather than guessed. It is double progression autoregulated by movement
quality; the engine reports the decision and reasoning and never prescribes a specific load.

**Rejected:** a system-wide ffmpeg/CUDA install (pollutes the machine, not reproducible, needs
admin). Also rejected CPU-only transcription as the default — it works and is the fallback, but
the 3070 turns a multi-hour job into a manageable one for the full 6.2 GB.

---

## ADR-007 — Garmin first-login is rate-limited, and the "MFA" prompt is a red herring

**Date:** 2026-07-22

ADR-001 accepted the unofficial `garminconnect` client as the only personal route to Garmin.
First contact exposed how it fails, and the failure actively misleads — worth pinning so it is
not re-diagnosed from scratch.

**What happens:** the mobile SSO endpoint returns a plain `429` after a few login attempts from
one IP. The client falls back to the web *widget* flow, whose page title is the **generic**
`GARMIN Authentication Application`. `garminconnect` matches `"authentication application"` as
*email MFA* and calls the MFA prompt — asking for a code that was never sent, on an account that
(verified) **has no MFA enabled**. Searching the whole mailbox, including spam, confirmed no code
email ever arrives. The real problem is the `429`, not a missing code.

**Decision:** treat a `429`-then-"MFA" sequence as **rate limiting, not an MFA challenge**. The
correct response is to wait tens of minutes for the limit to decay and retry once, not to hunt
for a code and not to hammer the endpoint (which extends the block). `rapha login --mfa-file`
remains for genuine authenticator-app MFA; it is the wrong tool here.

**Fallback investigated:** reusing Chrome's already-authenticated Garmin session by decrypting
its cookies. It sidesteps the login entirely and stores no password. Two limits made it a
user-gated option rather than a default: the harness classifier blocks the cookie-decryption
script (it correctly pattern-matches credential theft), so it runs only if the user adds a Bash
allow-rule; and Chrome 127+ App-Bound Encryption (`v20` cookies) defeats DPAPI-only decryption,
so success is not guaranteed even with the rule. The DPAPI master key *did* decrypt in testing,
so on a pre-v20 profile the route works.

**Rejected:** driving the browser via the Claude Chrome extension — its tools are not connected
to this session, so it was not available regardless. And Playwright as a *first* resort — it is
more exposed than the mobile flow (Cloudflare bot detection, and it needs a stored password or a
persistent profile), so it stays the last rung of the ladder in CLAUDE.md.

---

## ADR-008 — Garmin data via a logged-in Chrome, attached over CDP

**Date:** 2026-08-13

ADR-007 left the automatic route (unofficial API) rate-limited and the cookie-reuse fallback
defeated by App-Bound Encryption. The data still had to arrive. This is the rung that worked, and
it is worth pinning because the *shape* of why it works is not obvious.

**What failed first, precisely:** launching Chrome *from* Playwright trips Cloudflare — the
automation flags are detectable and the session lands on the bot-check loop. Copying the user's
Chrome profile does not help: the `v20` cookies are machine-bound and do not survive the copy, so
the copied profile lands on the Garmin sign-in page. Driving the API cross-origin (`connectapi`)
is blocked by CORS; the relative `/proxy/` base returns empty.

**What works:** the user starts their *real* Chrome once with `--remote-debugging-port=9222` and a
non-default `--user-data-dir` (Chrome 136+ refuses CDP on the default profile) and logs into Garmin
**by hand** — Cloudflare trusts a human session. Playwright then *attaches* over CDP
(`connect_over_cdp`) and never launches anything, so there are no automation flags to detect. From
*inside* that authenticated page it calls Garmin's own `connect.garmin.com/gc-api/*` endpoints with
the page's session cookies and its `connect-csrf-token` header (grabbed from an intercepted
request). Read-only: it fetches, it never posts.

**Why this respects ADR-001:** the session lives in the user's browser, not here. `rapha pull`
holds no credential of its own — same invariant as `sync`, reached a different way. `playwright` is
an optional extra (`browser`), imported lazily, so the core install is unaffected.

**Endpoints, verified:** `activitylist-service` (activities), `usersummary-service` (TDEE, steps,
stress, Body Battery), `wellness-service/dailySleepData`, `hrv-service`, `metrics-service/maxmet`
(VO₂max), `weight-service/weight/range`, and — the reason to bother — `activity-service/
activity/{id}/exerciseSets`, which reports every strength set's exercise, reps and weight in
integer grams. That per-set detail is what the API summary throws away and what ADR-001's whole
point (Módulo 17 progression) needs.

**Known limitation:** exercise identity and weight are Garmin's *on-watch auto-detection*, not a
logged prescription. A machine set can be mislabelled (an 83 kg "biceps curl" was really a machine
row) and a plate weight guessed. The store records what Garmin reports faithfully; the dashboard
reads the *trend across sessions*, not any single figure, and says so. Correcting the labels would
be fabricating data.

---

## ADR-009 — The portal is one self-contained file, no network at render or view

**Date:** 2026-07-24 (retroactively recorded)

The portal renders to a single `index.html` with **all** CSS and JS inlined and no external
requests — no CDN, no web font, no analytics, no framework. `dashboard/portal.py` already builds it
this way and cites this ADR; the decision was simply never written down. Recorded now so the
reference is not dangling.

**Why:** the page displays real body metrics and is opened from `%RAPHA_HOME%\dist`. An external
request from that page is a data-exfiltration path (a referrer, a cache key, an analytics beacon
carrying the URL) and an availability dependency (a CDN that fails blanks the page). A single file
has neither. It also means the page works opened directly off disk, and `serve` only has to hand
over static bytes. Vanilla JS is enough for tab switching, a copy button, and the photo toggle;
a framework would be weight and a supply-chain surface for no gain.

**Consequence for later work:** anything added to the page inlines its assets. Charts are
hand-rolled inline SVG sparklines, not a charting library, for exactly this reason.

---

## ADR-010 — One mutating endpoint: uploading a progress photo

**Date:** 2026-08-13

ADR-009's server was `GET`-only, by design — "no mutating endpoints, not 'none for now', none." A
progress photo has to get from the phone into `%RAPHA_HOME%` somehow, and the alternatives are
worse than a narrow endpoint: making the user hand-copy HEIC files into dated folders and run a
converter, or teaching the credential-free server to reach out (which ADR-001 forbids). So the
`GET`-only stance is reversed **once**, deliberately, the same way MrW's ADR-011 reversed its own.

**Decision:** exactly one mutating route, `POST /upload/photo`. It accepts a single image
(HEIC/HEIF/JPG/PNG), converts it to an upright JPEG (`photos.py`, via Pillow + pillow-heif — iPhones
shoot HEIC and store orientation in EXIF), writes it under `data/photos/<date>/jpg/`, and
re-renders the portal. It moves no money, touches no watch, holds no token, and writes nowhere but
the photos inbox.

**Security is structural, not conventional:**
- Binds `127.0.0.1`, validates `Host` (DNS-rebinding defence) — unchanged from ADR-009.
- Refuses cross-origin POSTs on two independent signals: `Sec-Fetch-Site` must be `same-origin`,
  and `Origin` (if present) must match the portal's own port. It also *requires* a custom
  `X-Filename` header, which a cross-origin page cannot set without a CORS preflight the server
  never answers — so a malicious page cannot even reach the handler body.
- Caps the body on its declared `Content-Length` **before reading a byte**, and sanitises the
  filename to a bare stem (an upload cannot escape its folder or overwrite a sibling).
- The re-render reaches only `dashboard.build → briefing/portal/photos`, none of which import a
  Garmin token holder. A test (`test_the_upload_path_never_imports_a_garmin_token_holder`) pins
  that ADR-001 still holds with the mutating endpoint present.

**Rejected:** `multipart/form-data`. Parsing it needs `cgi` (removed in 3.13) or a hand-rolled
multipart reader; a raw body with the name in a header is smaller, and requiring that header is
itself the CSRF defence. `Pillow` + `pillow-heif` are a new dependency, justified here: HEIC is not
decodable by the standard library and the household shoots exclusively on iPhone. Both go in the
`photos` optional extra, so the core install stays at `garminconnect` + `pdfplumber`.

---

## ADR-011 — A second mutating endpoint: editing body measurements

**Date:** 2026-08-13

Measurements used to live as a single snapshot in `state.json` (read-only, one date). To make
them a first-class, editable time series that the analysis reads, they move into the SQLite
`measurements` table and gain a write path: `POST /measurement`. This is the second deliberate
exception to the server's default (ADR-010 was the first); the same structural safeguards apply,
and it is still offline and credential-free.

**Decision:** the portal's Progress tab carries an add/edit form (date, weight, and the
circumferences: waist, neck, chest, shoulders, arm, thigh, hip, calf, plus the one-off wingspan).
It POSTs JSON to `/measurement`, which validates and converts human units (cm, kg) to the store's
integer millimetres and grams — the one place that conversion lives (`measurement_input.py`, pure
and tested) — upserts, and re-renders. The endpoint reuses ADR-010's cross-origin refusal and
size cap.

**The merge is the crux.** `record_measurement` is a **field-level merge**, not a row replace: on a
date that already has a row, only the fields the new entry carries overwrite; a `None` leaves the
stored value alone. This is what lets a Garmin weigh-in (weight only) and a manual tape entry
(waist, neck, …) share a date without clobbering each other — the latent bug the old full-row
upsert had once weigh-ins started landing in this table — and it makes editing one field safe.
Blank form fields are simply omitted, so you can log one number today and another next week.

**Why cm/kg in, mm/g stored.** A tape reads centimetres and a scale kilograms; the store bans
floats on every measurement path (`0.1 + 0.2` has no place in a body-fat number). So the form
speaks human units and the boundary converts once, to integers.

**New fields, and why.** Beyond waist/neck (which the Navy body-fat formula needs), the
circumferences don't feed a formula — they *are* the recomposition evidence. Waist shrinking while
an arm or thigh holds is muscle kept through a cut, which the scale alone hides. The change is
measured from the protocol start (like the weight trend), so it doesn't blend a pre-cut bulk into
the read. Adding columns to an existing database is handled by a small `PRAGMA table_info` diff at
open time — SQLite has no `ADD COLUMN IF NOT EXISTS`.

**Schema migration on the existing DB.** Old databases gain the new columns automatically on next
open; the legacy `state.json` measurement is seeded into the table once, after which the table is
the single source and `state.json` keeps only protocol config.

---

## ADR-012 — Data Status: pull freshness, a live health dot, and a Chrome-launch button

**Date:** 2026-08-14

The CDP pull (ADR-008) only runs while a human-authenticated Chrome is open on the debug port, and
pulls are driven by an hourly scheduled task. That makes "is my data current, and if not why" a
real question the user needs answered at a glance. The Data Status tab answers it.

**Decision:** a new tab with a traffic-light dot (also mirrored beside the nav item). Green while a
pull landed within the last hour, red once it is older or never happened. The freshness is honest
because every successful pull stamps `data/cache/last_pull.json` (`pull_status.record_pull`), and
the age is computed against the clock — client-side and re-checked each minute, so the dot goes red
on its own as time passes without a page reload.

**Two new server routes, both credential-free:**

- `GET /pull-status` (read-only) returns the last-pull time, its age, whether it is fresh, the last
  pull's summary counts, and — via a cheap local TCP probe — whether the debug Chrome is reachable
  right now. The tab's JS polls it; the build embeds a first-paint snapshot (no port probe at build
  time, to keep rendering side-effect-free) so the tab still works opened from disk.
- `POST /launch-chrome` (ADR-012's mutation) opens a debug-enabled Chrome on Garmin's **sign-in**
  page with a dedicated profile. This is the first time the server spawns a process, so the bounds
  matter: the command is **fixed** — no request input reaches it, so there is no injection surface —
  it is refused cross-origin like every other POST, and the worst a same-origin trigger can do is
  open a browser window. It holds no credential: the user types the password into Chrome, and the
  pull only ever *attaches*. A plain Chrome (unlike a Playwright-launched one) sets no automation
  flags, so Cloudflare treats the human who logs in there as human.

**The hourly loop.** Two scheduled tasks, registered under the logged-on user (no stored password):
"Rapha Pull" runs `rapha-refresh.ps1` every hour (pull, then rebuild the portal, then log the
outcome), and "Rapha Portal" serves the portal at logon so it always comes back on current code —
fixing the stale-server class of bug directly. The refresh script uses `Start-Process -Wait` for
`pythonw`: PowerShell does not wait on a GUI-subsystem executable with the call operator, so the
naive version fired pull and report simultaneously and never captured the exit code.

**Why hourly still means occasional re-auth.** A pull fails cleanly when the browser session is
closed or expired — it exits non-zero, the marker is not restamped, and the dot goes red. Garmin
sign-ins last a while, so in practice the user re-authenticates every so often (one click on the
launch button), not hourly. `--metric-days 45` on the scheduled pull keeps the rich recent window
intact: the daily ingest window-replaces its whole span, so a short window would quietly shrink the
history the Performance charts draw.

**On-demand pull.** A "Pull now" button fires the *same* hourly task immediately via `POST /pull-now` (the server runs `schtasks /run /tn "Rapha Pull"`, a fixed command). It deliberately does not run the pull inside the server — that would import the pull path into the credential-free listening process, breaking ADR-001. Triggering the registered task keeps the pull in its own process; the tab then watches `/pull-status` until the last-pull timestamp advances and reports completion. Like the hourly run, it needs the debug Chrome open.

**Rejected:** launching Chrome from the page via `window.open` (opens in whatever browser is viewing
the portal, which has no debug port, so the pull could not attach); a fully headless login with a
stored password (ADR-007's rate-limit wall, and it reverses ADR-001's no-password invariant); and
computing freshness only at build time (the dot would lie the moment an hour passed with the page
open).

---

## ADR-013 — Writing workouts to Garmin over the CDP session

**Date:** 2026-08-16

Rapha's write path (`write.py`, ADR-001) needs OAuth tokens, and Garmin's rate-limited login
(ADR-007) never let us mint them — the token store is empty. But the read pull already runs over a
logged-in debug Chrome (ADR-008), and that same authenticated session can POST as well as GET. So
creating and scheduling workouts happens the same way reading does: from inside the authenticated
page, against Garmin's own `workout-service`.

**Decision:** `browser_write.py` creates, schedules and deletes **workouts** over CDP — the same
narrow surface as `write.py` (ADR-001), never an activity, never health data. It holds no credential
of its own; the session lives in the user's browser. `push()` takes built payloads plus target
dates, and `replace_prefix` deletes any existing workouts whose name starts with a given prefix
before creating, so a re-run is idempotent (no duplicates, and the old schedule entries go with the
deleted workouts).

**Two failures found and fixed while pushing Sheet 02, worth pinning:**

- **Bad exercise *category*, not name.** Garmin 400s a whole workout if a step's `category` is
  outside its taxonomy. `elevação frontal` was mapped to a `FRONT_RAISE` category, which does not
  exist — front raises live under `LATERAL_RAISE`. A wrong *name* within a valid category is
  recoverable: `push()` retries a 400 with `_strip_exercise_names` (category only, always valid; the
  specific movement is already in the step description), so a single unknown variant never sinks a
  workout. A wrong *category* is not recoverable that way and must be fixed in the mapping.
- **Console encoding.** Logging a `✓` crashed the run on the cp1252 Windows console *after* a
  workout was already created, orphaning it. Log output is now ASCII-only, and `replace_prefix`
  cleans up any orphan on the next run.

**Scheduling policy — the sheet's own rotation.** The Intermediário sheets run a **5-day rolling
cycle**: D1, D2, D3, D4, then a rest day (the empty "TREINADOR" placeholder session), then the cycle
restarts — *not* a fixed Mon–Sun week. So the training days roll through the calendar (Sheet 02
starts D1 on Thu Aug 20, rest lands Mon Aug 24, D1 restarts Tue Aug 25, and so on). The cycle is
anchored to the **sheet's** first week, not to protocol day 1, so `cycle.resolve` shows the right
session the moment a sheet goes live; and an *explicitly empty* session reads as the rest slot
(distinct from a test fixture that merely omits exercises). A first attempt placed the four sessions
on the first four days of each week — corrected once the sheet's real rotation was confirmed. Rapha
pushes only the four lifting sessions; the cardio day (Módulo 14) stays the user's to place.

**Reversibility.** Workouts and their schedule entries are deletable, and `push(replace_prefix=…)`
plus `delete_workout` make the whole operation undoable — which is what made it safe to run against
the real account.

**Workout structure — sets, reps, and rest (added later).** The first push emitted a flat list of
identical steps with lap-button ends and no break after an exercise's last set. Corrected to use
Garmin's native **repeat groups**: a run of same-rep sets (a pyramid 15,15,12,12 → two blocks, 2×15
then 2×12) is one `RepeatGroupDTO`, and the rest step lives *inside* the iteration so a break
follows every set — including the last, which is the gap before the next exercise. Two live-verified
schema facts made this work: the reps end-condition is `conditionTypeId` **10** (`3` is *distance* —
a latent bug in `workout.py` that never bit only because we had defaulted to lap-button), and a
repeat is `stepTypeId` 6 with an `iterations` (`conditionTypeId` 7) end-condition.

**Rest is `stepTypeId` 5, not 4 (corrected after an on-watch test).** The first Sheet-02 push emitted rest on `stepTypeId` 4, and we wrote here that Garmin's returning it as a `recovery` step was "expected". It was not — id 4 *is* `recovery`, an active interval; a between-sets rest is id **5** (`rest`). The mislabel made the watch run each session as an interval workout rather than a set-based strength one, with two visible symptoms the user caught in the gym: no per-set reps+weight confirmation screen, and an active-elapsed display instead of the big rest countdown (the timer still buzzed at the end). Verified live and against the reverse-engineered strength API (`n1t3k/garmin-strength-api`): warmup 1, cooldown 2, interval 3, recovery 4, rest 5, repeat 6. A test now pins the rest **id**, not just its key — the old test checked only the key, which was already `"rest"` on the wrong id. Working sets keep the reps end-condition (`conditionTypeId` 10) and carry no target weight yet; the reference also allows a `weightValue`/`weightUnit` pair, the next lever if the per-set weight prompt still needs coaxing.

## ADR-015 — Immediate progress-photo analysis via a fired subprocess

**Context.** The portal must show a physique review the moment photos are uploaded, but
the server holds no credential (ADR-001/009) and cannot run vision. Vision needs a model
call, which needs an API key.

**Decision.** Keep the server credential-free and move the credential to a **short-lived
subprocess** the upload fires — the same shape as `pull-now` firing the scheduled task and
`launch-chrome` opening a browser. `POST /analyze-photos` validates the date to
`YYYY-MM-DD`, passes it as an argv element (no shell), and `Popen`s `rapha analyze-photo
<date>`. That process reads `ANTHROPIC_API_KEY` from `%RAPHA_HOME%/.env`, calls Claude
vision on the day's JPGs (`vision.py`, the optional `vision` extra), writes `analysis.md`,
re-renders, and exits. The listening server never reads the key. The upload UI fires the
job once (after all files land), then polls the read-only `GET /photo-analysis?date=` until
the review is written and reloads.

**Consequences.** The feature is fully optional: no key or no `anthropic` SDK → analysis
stays "pending", exactly as before, nothing else changes. Cost is a couple of cents per
upload at `claude-opus-5` (the default; `RAPHA_VISION_MODEL` can pick a cheaper tier). This
adds the first outbound model call in the project and the first `anthropic` dependency —
justified by the explicit requirement and contained to the subprocess, off the server path.
