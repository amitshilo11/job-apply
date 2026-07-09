# Job Application Agent

Automated outreach system: discovers companies, tailors a CV per role, drafts cold emails and
LinkedIn messages, and tracks every application through follow-up and outcome. Full behavior for
each flow lives in `src/flow0.md`–`src/flow3.md` — this file only routes user requests to the
right flow. Read the relevant flow file before acting; don't guess at the steps from memory.

## Routing

| User says (examples) | Read and follow |
|---|---|
| `find startups`, `find 10 cybersecurity startups`, `find companies in Netanya` | `src/flow0.md` |
| `add Wiz to queue`, `queue company Snyk`, `add these to queue: ...` | `src/flow2.md` |
| `process company Wiz`, `process next from queue`, `process the queue` | `src/flow1.md` |
| `process role <url>`, `apply for <title> at <Company>` | `src/flow3.md` |
| `show follow-ups`, `check due`, `draft follow-ups` | `src/flow1.md` (Follow-up sub-flow, near the end) |

Slash-command shortcuts for the same triggers live in `.claude/commands/` (`/find-startups`,
`/add-queue`, `/process`, `/apply-role`, `/followups`) if the user prefers those.

## Before running Flow 1 or Flow 3

Check prerequisites (see each flow's "Prerequisites check"): `config/profile.md` and
`config/writing_samples.md` must be filled in with real content (not template placeholders),
`cv/main.tex` must exist, and `config/settings.json` must have `sender_email` set. If anything is
missing, stop and tell the user which file to fill in first — don't fabricate profile details.

## State model

- `state/queue.json` — companies discovered or added, waiting to be processed.
- `state/applications.json` — companies that have been processed. Each entry has an email
  `status` (`sent` / `drafted` / `email-skipped`) and, once you know more, a pipeline `stage`
  (`applied` → `replied` → `interview` → `offer`, or `rejected` / `ghosted` / `withdrawn`).
  `rejected`, `withdrawn`, and `offer` are closed stages — `list-due` stops surfacing follow-ups
  for them automatically.
- `state/skipped.json` — companies ruled out (shut down, deal-breaker, etc.) with a reason.

All three are managed through `scripts/state.py` — never hand-edit JSON when a command exists.
Key commands beyond `add` / `skip` / `list-due`:

```bash
python3 scripts/state.py update --slug wiz --stage interview --note "phone screen Tue"
python3 scripts/state.py mark-task --slug wiz --task connected_hr
python3 scripts/state.py queue reset   # un-stick queue entries left in "processing"
```

When the user tells you what happened after the fact ("Wiz rejected me", "I connected with the
recruiter at Snyk", "got an interview at Cato") — run the corresponding `update` / `mark-task`
command yourself, then regenerate the report: `python3 scripts/generate_report.py <slug>`.

## Output per company

`output/<slug>/` holds `research.md`, `email.md`, `linkedin.md`, `tailored_cv.tex`/`.pdf`,
`meta.json` (structured version of the above, used by the report generator), and `report.html`.
`output/index.html` is the master dashboard — regenerate it with
`python3 scripts/generate_report.py --all` after any bulk state change.

## Conventions

- Slugs: always derive them via `scripts/state.py`'s `slugify()` (lowercase, non-alphanumeric
  runs collapsed to `-`) rather than hand-rolling — this keeps dedupe against
  `applications.json` / `skipped.json` / `queue.json` reliable.
- Never guess emails or LinkedIn profile URLs. If a flow step says "not found", write "not found"
  — don't fabricate a plausible-looking one.
- Email/LinkedIn tone rules are non-negotiable and live in `src/prompts/draft_email.md` and
  `src/prompts/draft_linkedin.md` — read them before drafting, every time.
