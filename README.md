# Job Application Agent

A job-search assistant powered by Claude Code. You find a role you like; it tells you in a
minute whether it's worth it (company, role, pros and cons, fit score), finds the right people
to contact (people you already know first), drafts LinkedIn messages and an email in Hebrew
and English that sound like you, and tracks every person through follow-ups with a daily
to-do list.

---

## A normal day

```
/today                         what to send today, what's due, what to check
python3 scripts/serve.py       the dashboard: copy a message, send it on LinkedIn, click Sent
/apply-role <job url>          a new role (or paste the job page / drop a screenshot)
/followups                     draft the follow-ups that are due
```

Optional: a 9:00 reminder on work days that runs `/today` and drafts due follow-ups (a Claude
scheduled task; it runs while the Claude app is open).

---

## Setup

### Prerequisites

- [Claude Code](https://claude.ai/code), Python 3.9+
- `tectonic` (`brew install tectonic`) or `pdflatex` to build the CV PDFs
- Gmail MCP (`claude mcp add gmail`) for email drafts, job-alert emails and reply checks.
  Everything else works without it.

### Files you fill in (`config/` and `cv/` are gitignored)

| File | What it is |
|---|---|
| `config/profile.md` | Target roles, seniority, must-haves, deal-breakers, stack, location, a short "about me" |
| `config/writing_samples.md` | 3 to 5 messages you really sent. This is where your voice comes from. It grows by itself: see [Learning your style](#learning-your-style) |
| `config/settings.json` | Settings (below) |
| `cv/main.tex` | Your CV (LaTeX). Build it: `bash scripts/build_cv.sh --base` |
| `config/stories.md` | Optional: short work stories for interview prep (a template is included) |
| `config/Connections.csv` | Optional but valuable: your LinkedIn connections, for referrals (see [People](#the-right-people)) |
| `config/watchlist.json` | Optional: companies whose job boards to watch (managed by `scripts/watch_jobs.py`) |

`state/` and `output/` are created automatically (`mkdir -p state output` on a fresh clone).

### `config/settings.json`

```json
{
  "sender_name": "Your Name",
  "sender_email": "you@gmail.com",
  "dry_run": true,
  "target_function": "mobile developer",
  "linkedin_search_terms": ["team lead", "tech lead", "mobile lead", "android lead"],
  "message_languages": ["en", "he"],
  "tailor_cv": false,

  "home_location": "<your city>, Israel",
  "connect_note_max_chars": 200,
  "linkedin_note_monthly_limit": 5,
  "work_days": ["sun", "mon", "tue", "wed", "thu"],
  "followup_schedule_workdays": [4, 5],
  "ghost_after_workdays": 5,
  "no_accept_after_workdays": 10,
  "dashboard_port": 8765,

  "cv_default_variant": "mobile",
  "cv_variants": {
    "mobile":    {"tex": "cv/main.tex",      "pdf": "cv/main.pdf",      "approved": true,  "use_for": ["android", "mobile", "kotlin"]},
    "fullstack": {"tex": "cv/fullstack.tex", "pdf": "cv/fullstack.pdf", "approved": false, "use_for": ["full stack", "backend", "web"]}
  },

  "job_filters": {"title_include": ["android", "mobile", "kotlin"], "title_exclude": ["staff", "principal", "manager"],
                  "locations": ["israel", "haifa", "yokneam", "tel aviv"], "remote_regions": ["israel", "emea", "anywhere"]},
  "job_ranking": {"title_points": {"android": 4, "kotlin": 3}, "location_points": {"haifa": 3, "remote": 3}, "max_years": 5}
}
```

- `dry_run: true` saves Gmail drafts instead of sending.
- `message_languages`: every message is written once per language. Hebrew is written first and
  natively, never translated. The first language is used for the Gmail draft.
- `connect_note_max_chars`: LinkedIn free accounts allow about 200 characters per connect note
  and only a few notes a month. Premium allows 300.
- Follow-up timing is in work days (Sun–Thu): follow-up #1 four work days after your message,
  #2 five work days later, then the thread closes as "no answer" five work days after that.
  A connect request not accepted after 10 work days shows up under "Check".

---

## Applying to a role (Flow 3, the main flow)

```
/apply-role https://www.linkedin.com/jobs/view/<job id>/
apply for Android Developer at Acme
```

Best input: **paste the whole LinkedIn job page** (Cmd+A, Cmd+C) or drop a screenshot. That
gives the agent the "Meet the hiring team" box, the company size and the work mode.

What you get:

1. **Role card**: the company in short (what they make, size, stage, warning signs like
   layoffs, with sources), the role (what you'd build, work mode, commute from home, years asked
   vs. yours, stack you have / don't have), pros and cons, a fit score out of 5 and a verdict.
   At 1 or 2 out of 5 it stops and asks before writing anything.
2. **People**: anyone you already know there (from `Connections.csv`), the job poster, then a
   recruiter and team lead that fit the company's size. Each is checked (still there, in
   Israel, linked to this role) and comes with a reason, a confidence level, and alternates.
3. **Messages**, Hebrew and English: connect note, first message after they accept, and the email.
   Every one passes the [message checker](#the-message-checker).
4. **CV**: the approved CV version that fits the role, and the job keywords your CV is missing
   (you decide whether to add them; nothing is rewritten for you).
5. **Tracking**: each person becomes a thread on the dashboard with its next step and date.

---

## The dashboard

```bash
python3 scripts/serve.py          # http://localhost:8765, opens your browser
python3 scripts/serve.py --lan    # also on your phone (same Wi-Fi, link with a token)
```

- **Today**: what to send now (connect requests, first messages, emails, applying on the site),
  follow-ups due, and things to check, each with Copy and Sent buttons. Plus what's coming up
  in the next 5 work days, and how many LinkedIn notes you've used this month.
- **What's working**: accept and reply rates by recruiter vs. lead, Hebrew vs. English, note vs.
  no note.
- **Each role's page**: the role card, every person with their steps (connect note → first
  message → follow-ups) and buttons (Sent, They accepted, They replied, Close), the email, the
  CV with missing keywords, interview prep, and a history.

Every click saves to `state/applications.json`. Pages opened straight from disk are read-only.
The server only listens on your machine (unless `--lan`), only serves the dashboard pages and
CV PDFs, and ignores requests from other websites.

You can also just tell Claude: "sent the connect note to Noa in Hebrew", "Dan accepted",
"Acme rejected me" (or `/sent ...`), and it records it.

---

## Learning your style

Edit a message in its box on the dashboard, then click Sent: the version you sent is added to
`config/writing_samples.md` under "Learned from your edits", and the next drafts follow it.
Edited it inside LinkedIn instead? Paste what you sent:

```bash
pbpaste | python3 scripts/samples.py add --slug acme --key lead --field first_message_he
python3 scripts/samples.py list
```

---

## The message checker

```bash
python3 scripts/check_messages.py acme
python3 scripts/check_messages.py --all
```

Errors (the agent fixes these before showing you a draft): connect note over the limit,
generic AI phrases ("exactly the kind of challenge", "אשמח מאוד להזדמנות"), claims you never
made ("been reading up on your research"), saying an email was sent when it wasn't, the
recipient's own email in a message to them, talking about them in third person, a wrong name,
leftover placeholders, dashes as separators. Warnings: long messages, lowercase "i", and a
phrase that's in 3+ other companies' messages (reads like a template). Anything in your own
writing samples is never flagged.

---

## The right people

- **Referrals first.** Export your connections once a month: LinkedIn → Settings & Privacy →
  Data privacy → Get a copy of your data → Connections. Save `Connections.csv` in `config/`.
  `python3 scripts/referrals.py "Acme"` (or `--all` for every open application).
- The report has one-click LinkedIn searches (recruiters, mobile/Android leads, everyone there
  in Israel) to check or replace a contact.
- Nothing on LinkedIn is automated. You send everything.

---

## Follow-ups and reminders

```
/today            python3 scripts/state.py today
/followups        drafts every follow-up that's due, Hebrew + English, checked
/stats            python3 scripts/state.py stats --days 30
```

LinkedIn follow-ups are drafted for you to send. Email follow-ups go to Gmail as drafts
(or are sent when `dry_run` is false). If Gmail is connected, replies are picked up.

---

## Finding jobs (Flow 4)

```
/job-alerts                                   new jobs from your alert emails + watchlist, ranked
/job-alerts watch Acme <job-board url>      watch a company's job board
python3 scripts/watch_jobs.py                 check the watchlist yourself
```

- Set up job alerts once (LinkedIn Jobs, AllJobs, Drushim: "Android" / "Mobile" in your area,
  hybrid + remote). The agent reads them from Gmail, ranks them with `job_ranking`, and you pick.
- Watchlist: companies on Greenhouse, Lever and Ashby are read from their public job feeds.
  Comeet pages are read best-effort.
- The old company discovery (`/find-startups`, Flow 0) is parked: it found companies, not open roles.

---

## CV versions

- `cv/main.tex`: your main (mobile) CV. `cv/fullstack.tex`: a full-stack version with the same
  facts, reordered. Review it, then set `cv_variants.fullstack.approved` to `true` and build it:
  `bash scripts/build_cv.sh --variant fullstack`.
- `python3 scripts/cv_keywords.py --slug <slug>` picks the version per role and lists missing
  keywords. Per-role rewriting (`src/prompts/tailor_cv.md`) only runs when you ask for it.

---

## Interview prep

```
/interview-prep acme Tuesday with the mobile lead
```

Company brief, how they interview, 8 to 12 likely questions with the story or CV fact to answer
each, questions to ask them, and a short prep list. It uses `config/stories.md`; empty stories
fall back to your CV bullets, marked "fill in".

---

## Other flows

- `/process <Company>` / `process next from queue` (Flow 1): find the best role at a company,
  then the same steps as Flow 3.
- `/add-queue <Company>` (Flow 2): add companies to the queue without research.

---

## Scripts

| Script | What it does |
|---|---|
| `state.py` | Applications, per-person threads, `today`, `stats`, `event`, `update`, `show`, queue |
| `serve.py` | The dashboard server (buttons that save) |
| `generate_report.py` | Builds `output/<slug>/report.html` and `output/index.html` |
| `check_messages.py` | The message checker |
| `samples.py` | Records what you sent and learns from your edits |
| `referrals.py` | People you know at a company (from `Connections.csv`) |
| `cv_keywords.py` | Picks the CV version, lists missing job keywords |
| `watch_jobs.py` | Watchlist: new jobs from company job boards |
| `rank_jobs.py` | Ranks a list of jobs against your preferences |
| `build_cv.sh` | Builds CV PDFs (`--base`, `--variant <name>`, or a tailored one) |

## Directory structure

```
CLAUDE.md          routing: which flow handles which request
.claude/commands/  slash commands (/apply-role, /today, /followups, /sent, /dashboard, ...)
src/               flows (flow0–flow4) and prompt modules (role card, people, drafting, interview prep)
scripts/           the Python tools above
cv/                CV versions (gitignored) + resume.cls
config/            profile, writing samples, settings, stories, watchlist, connections (gitignored)
state/             applications, skipped, queue, sent log, seen jobs (gitignored, auto-managed)
output/            one folder per application + the dashboard (gitignored)
```
