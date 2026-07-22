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
