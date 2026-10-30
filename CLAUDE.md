# Job Application Agent

Helps the user organize their job search: they find a role, the agent sums it up (company,
pros and cons, fit), finds the right people, drafts messages in Hebrew and English that sound
like them, and tracks every person through follow-ups to an outcome. Full behavior for each
flow lives in `src/flow0.md`–`src/flow4.md` — this file only routes requests to the right
flow. Read the relevant flow file before acting; don't guess at the steps from memory.

## Routing

| User says (examples) | Read and follow |
|---|---|
| `process role <url>`, `apply for <title> at <Company>`, a pasted job page or a job screenshot | `src/flow3.md` — **the main flow** |
| `run <url> in the background`, `queue this role for the dashboard` | `python3 scripts/runs.py start --url <url>` (`--hr`/`--lead`/`--knows "Name \| URL \| email"`, `--notes`): Flow 3 headless, shown on the dashboard |
| `improve the CV for <Company>`, `add Kotlin to my CV for wiz` (in the background) | `python3 scripts/runs.py cv --slug <slug> --add <keyword> --notes "..."`: rewrites `output/<slug>/tailored_cv.tex` (`src/prompts/tailor_cv.md`), shown on the report |
| `what's today`, `show follow-ups`, `check due`, `draft follow-ups` | `src/flow1.md` (Follow-up sub-flow, near the end) |
| `find jobs`, `check job alerts`, `watch <Company>` | `src/flow4.md` |
| `import my LinkedIn export <zip>`, `catch up from LinkedIn` | `python3 scripts/linkedin_import.py <zip or folder>` (`--dry-run` first): records connect/accept/message/reply steps for tracked people, adds what they sent to the writing samples, copies `Connections.csv` |
| `got an interview at <Company>` | `src/prompts/interview_prep.md` |
| `process company Wiz`, `process next from queue`, `process the queue` | `src/flow1.md` |
| `add Wiz to queue`, `add these to queue: ...` | `src/flow2.md` |
| `find startups` | parked: say so and offer `src/flow4.md` (see `.claude/commands/find-startups.md`) |

Slash commands in `.claude/commands/`: `/apply-role`, `/today`, `/followups`, `/sent`,
`/dashboard`, `/job-alerts`, `/interview-prep`, `/stats`, `/process`, `/add-queue`, `/linkedin-import`.

## Before running Flow 1 or Flow 3

Check prerequisites (see each flow's "Prerequisites check"): `config/profile.md` and
`config/writing_samples.md` must be filled in with real content (not template placeholders),
`cv/main.tex` must exist, and `config/settings.json` must have `sender_email` set. If anything is
missing, stop and tell the user which file to fill in first — don't fabricate profile details.

## Messages: non-negotiable

- Read `src/prompts/draft_linkedin.md` and `src/prompts/draft_email.md` before drafting, every
  time. The voice comes only from `config/writing_samples.md` ("Learned from your edits" first).
- Hebrew is drafted first and written natively, never translated (`message_languages`).
- Nothing the user didn't do or that hasn't happened ("been reading up on", "I sent an email").
- Every draft passes `python3 scripts/check_messages.py <slug>` (exit 0) before it's shown as done.

## Settings that change what the flows produce

All in `config/settings.json`:

- `message_languages` (default `["en", "he"]`) — one version of every message per language. The
  first is the one used for the Gmail draft/send.
- `connect_note_max_chars` (default 200, LinkedIn's free-account limit) and
  `linkedin_note_monthly_limit` (shown in Today).
- `work_days` (Sun–Thu), `followup_schedule_workdays` (`[4, 5]`), `ghost_after_workdays`,
  `no_accept_after_workdays` — when follow-ups come due and when a thread closes as no answer.
- `cv_variants` — CV versions the user approved once; `scripts/cv_keywords.py` picks one per role.
  A version with `"approved": false` is never sent. `tailor_cv` (default `false`) — per-role
  rewriting only when true or asked for in that request; don't flip it for a one-off.
- `job_filters`, `job_ranking` — what Flow 4 keeps and how it ranks.
- `dry_run` — Gmail drafts instead of sending.
- `run_timeout_minutes` (40), `notify_when_done` (true), `background_model` (null = the CLI's
  default) — background runs started from the dashboard.

## State model

- `state/applications.json` — one entry per application. Each has `outreach`: one thread per
  person (keys `hr`, `lead`, `referral-N`, `email`) with dated steps (`connect_sent`, `accepted`,
  `message_sent`, `sent`, `followup_1`, `followup_2`, `replied`), the language used, and
  note / no note. Plus a pipeline `stage` (`applied` → `replied` → `interview` → `offer`, or
  `rejected` / `ghosted` / `withdrawn`). `rejected`, `withdrawn`, `ghosted` and `offer` are
  closed: no more actions for them.
- `state/skipped.json` — companies ruled out, with a reason. `state/queue.json` — Flow 1 queue.
- `state/sent_log.json` — every message marked sent (draft vs. what was sent).
- `state/seen_jobs.json` — jobs already shown by Flow 4.
- `state/linkedin_import.json` — which sent texts `scripts/linkedin_import.py` already turned into samples.
- `state/runs.json` — background runs (`scripts/runs.py`); each has `state/runs/<id>/` with the
  prompts sent and Claude's event stream.

All managed through scripts — never hand-edit JSON when a command exists:

```bash
python3 scripts/state.py event --slug wiz --key hr --event connect_sent --lang he   # --no-note, --undo
python3 scripts/state.py event --slug wiz --key lead --event replied
python3 scripts/state.py update --slug wiz --stage interview --note "phone screen Tue"
python3 scripts/state.py today          # what's due (also auto-closes finished threads)
python3 scripts/state.py show --slug wiz
python3 scripts/state.py person --slug wiz --key hr --name "Noa Cohen" --name-he "נועה"   # fills {name} in
python3 scripts/state.py close-thread --slug wiz --key hr --reason wrong_person --why left   # next alternate moves up
python3 scripts/samples.py add --slug wiz --key hr --field connect_note_he --text "..."   # what was really sent
```

When the user tells you what happened ("I sent the connect note to Noa", "Wiz rejected me",
"the lead at Snyk replied", "got an interview at Cato", "the HR at Wiz is Noa Cohen", "Noa at Wiz is
the wrong person, she left"), run the matching command yourself
(and `samples.py add` if they paste the text they sent), then `python3 scripts/generate_report.py <slug>`.

## Output per application

`output/<slug>/`: `jd.md` (the job description, word for word), `meta.json` (role card,
contacts, messages, email, CV, interview prep — the source of truth), `report.html`, and
optionally `research.md` (notes, sources), `interview_prep.md`, `tailored_cv.tex`/`.pdf`.
`output/index.html` is the dashboard (Today, stats, all applications). Open both through
`python3 scripts/serve.py` (http://localhost:8765) so clicks save; `--lan` adds phone access.
Regenerate after bulk changes: `python3 scripts/generate_report.py --all`.

**+ New application** on the dashboard starts a background run: `scripts/runs.py` runs
`claude -p` (the CLI's own login) on Flow 3 with the rules in `src/prompts/background_run.md`,
one run at a time, writing only under `output/` and changing state only through the scripts.
The dashboard shows each run's progress, its question when it needs the user, and the result.
A report's **Improve CV** button starts the other kind of run: the CV rewritten for that role
with the job keywords the user ticked (true for them) and their instructions.

No HR or team lead found: the slot still gets its messages, with `{name}` where the first name
goes. The user fills the person in from the report (or `state.py person`) and tracks it as usual.

## Conventions

- Slugs: always via `scripts/state.py`'s `slugify()` — keeps dedupe reliable.
- Never guess emails or LinkedIn profile URLs. "Not found" is a fine answer.
- Never automate LinkedIn (no logging in, scraping or sending). The user sends every message.
- Facts about a company come with a source URL; unknown is better than invented.
