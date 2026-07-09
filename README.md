# Job Application Agent

Automated outreach system powered by Claude Code. Discovers companies, tailors your CV per role, drafts cold emails and LinkedIn messages, and tracks every application from first contact to follow-up.

---

## Prerequisites

- [Claude Code](https://claude.ai/code) (CLI)
- Python 3.9+
- `tectonic` or `pdflatex` for building PDFs
- Gmail MCP server (for sending/drafting emails)

---

## Getting started

### 1. Clone the repo

```bash
git clone https://github.com/amitshilo11/job-apply.git
cd job-apply
```

### 2. Create your config files

The `config/` folder is gitignored — you need to create these three files yourself.

**`config/settings.json`**

```json
{
  "sender_name": "Your Name",
  "sender_email": "you@gmail.com",
  "email_signature": "Your Name",
  "followup_days": 5,
  "dry_run": true,
  "target_function": "software engineer",
  "linkedin_search_terms": ["engineering manager", "team lead", "tech lead"]
}
```

Keep `dry_run: true` for your first few runs — emails are saved as Gmail drafts instead of sent.

**`config/profile.md`**

Describe who you are and what you're looking for. Example structure:

```markdown
# Candidate Profile

## Target roles
- Software Engineer
- Backend Engineer

## Seniority
Level: mid-level (3+ years)

## Must-have criteria
- Remote or hybrid
- Startup environment

## Nice-to-have
- Interesting technical problem

## Deal-breakers
- Pure enterprise / large corp
- No equity

## Tech stack
Strong: Python, TypeScript, ...
Familiar: Go, Rust, ...

## Location
Based in [city]. Open to remote.

## About me (2–3 sentences for Claude to use when drafting emails)
...
```

**`config/writing_samples.md`**

Paste 3–5 real messages or emails you've actually sent. This is what makes drafted emails sound like you, not a bot.

```markdown
# Writing Samples

## Sample 1 — LinkedIn connect note
Hey [name], I came across [company] and liked what you're building. Would love to connect.

## Sample 2 — Cold email
Hey,

I'm [name], [role] with X years experience. Came across you and liked the product direction.
Not sure if you're hiring but wanted to reach out. CV attached if useful.

## Sample 3 — Follow-up
Hey, just circling back on my email from last week. Still interested if timing works out.
```

### 3. Add your CV

```bash
cp /path/to/your-cv.tex cv/main.tex
```

### 4. Initialize state files

The `state/` folder is gitignored. Create it with empty state:

```bash
mkdir -p state
echo '[]' > state/queue.json
echo '[]' > state/applications.json
echo '[]' > state/skipped.json
```

### 5. Create the output folder

```bash
mkdir -p output
```

### 6. Install tectonic (LaTeX → PDF)

```bash
brew install tectonic
```

`pdflatex` (from MacTeX / BasicTeX) also works.

### 7. Set up Gmail MCP

The agent uses Gmail MCP to send or draft emails. Add it to your Claude Code MCP config:

```bash
claude mcp add gmail
```

Then authenticate when prompted on first use.

---

## Directory structure

```
CLAUDE.md      project context + routing table Claude Code loads automatically
.claude/commands/  slash-command shortcuts (/find-startups, /process, /add-queue, /apply-role, /followups)
cv/            your LaTeX CV  (you add main.tex)
config/        profile, writing samples, settings  (gitignored — you fill these)
scripts/       build_cv.sh, state.py, generate_report.py
src/           flow playbooks (flow0.md–flow3.md) + prompt modules
state/         applications.json, queue.json, skipped.json  (gitignored — auto-managed)
output/        one folder per company  (gitignored — auto-generated)
```

---

## Flows

There are four flows. You trigger them by typing natural language in Claude Code, or with the
equivalent slash command in `.claude/commands/` (`/find-startups`, `/add-queue`, `/process`,
`/apply-role`, `/followups`).

---

### Flow 0 — Discover companies

Searches the web, VC portfolio pages, and startup directories for companies that match your profile. Adds them to the queue automatically.

**Trigger:**

```
find startups
find 10 cybersecurity startups
find 15 health-tech startups
find companies in Netanya
find companies near me
```

**What it does:**

1. Runs 6–9 web searches across your target verticals (cybersecurity, health-tech, AI by default)
2. Fetches VC portfolio pages (Aleph, Pitango, Team8, Glilot, TLV Partners, etc.)
3. Deduplicates against everything already in `applications.json`, `skipped.json`, and `queue.json`
4. Pushes new companies to `state/queue.json`
5. Prints a summary table of what was added

**After Flow 0 completes**, say `process next from queue` to start working through the list.

---

### Flow 2 — Add companies manually to the queue

Adds one or more companies you already know about directly to the queue, without any web research.

**Trigger:**

```
add Wiz to queue
queue company Snyk
add to queue: Orca Security
add to queue: Wiz, website: https://wiz.io, linkedin: https://linkedin.com/company/wiz
add these to queue: Wiz, Snyk, Orca Security
```

**What it does:**

1. Parses company name + optional website / LinkedIn URL from your input
2. Checks for duplicates (queue, applications, skipped)
3. Adds each new company to `state/queue.json`
4. Prints a summary of what was added and the new queue total

**When to use this instead of Flow 0:**
- You saw a job posting on LinkedIn and want to track the company
- A friend recommended a company
- You want to add a specific list without doing discovery first

You can also edit `state/queue.json` directly — it's a plain JSON array.

---

### Flow 1 — Process a company (full outreach)

The main flow. Takes a company name (or pulls the next one from the queue) and does everything: research, CV tailoring, email draft/send, LinkedIn message drafts, and state tracking.

**Trigger — single company:**

```
process company Wiz
process Snyk
```

**Trigger — from the queue:**

```
process next from queue
process next 3 from queue
process the queue
```

**Trigger — multiple at once:**

```
process these companies: Wiz, Snyk, Orca Security
```

**What it does, step by step:**

| Step | What happens | Output |
|------|-------------|--------|
| 1. Discover | Finds the company website and careers page | `output/<slug>/research.md` |
| 2. Scan jobs | Searches careers page + LinkedIn jobs, picks best-fit role | appended to `research.md` |
| 3. Find email | Looks for `careers@`, `jobs@`, `hr@` on the site | appended to `research.md` |
| 4. Tailor CV | Rewrites `cv/main.tex` for the role, builds PDF | `output/<slug>/tailored_cv.tex` + `.pdf` |
| 5. Draft email | Writes a cold email in your voice using your writing samples | `output/<slug>/email.md` |
| 6. Send / draft | Sends via Gmail MCP, or saves as draft if `dry_run: true` | Gmail |
| 7. LinkedIn lookup | Finds HR and team lead profiles | appended to `research.md` |
| 8. LinkedIn messages | Drafts connect notes and first messages for each profile | `output/<slug>/linkedin.md` |
| 9. Log state | Records the application in `state/applications.json` | — |
| 10. Report | Generates an HTML report and updates the master dashboard | `output/<slug>/report.html` + `output/index.html` |

**LinkedIn messages are for you to send manually** — open the URLs, copy the drafted text, hit Connect.

---

### Flow 3 — Apply to a specific role

Use this when you already have a job posting in hand — a URL, or just a company + title — rather
than discovering companies through Flow 0/2.

**Trigger:**

```
process role https://jobs.lever.co/acme/abc123
process role at Acme: Backend Engineer
apply for Backend Engineer at Acme
apply to https://jobs.lever.co/acme/abc123
```

**What it does:** same shape as Flow 1 (research, tailored CV, contact email, draft email,
LinkedIn lookup and messages, state logging, report) but starting from the specific role instead
of searching a careers page — see `src/flow3.md` for the exact steps.

---

## CV tailoring

The CV tailoring prompt lives at `src/prompts/tailor_cv.md`. It instructs Claude to:

- Identify the top 3–5 skills/keywords from the job description
- Move the most relevant bullets to the top of each position
- **Remove** bullets that don't support the role
- Shorten verbose bullets
- Drop entire positions if they aren't relevant (keeping at least the 2 most recent)
- **Target output: one page**

Each change is annotated inline:
```latex
% TAILORED: moved up for backend focus
% TAILORED: removed — irrelevant to security role
% TAILORED: shortened to fit one page
```

---

## Follow-ups

Check what's due:

```bash
python3 scripts/state.py list-due
```

Then say `draft follow-ups` (or `/followups`) in Claude Code. It will draft a short follow-up for each due company and save it to `output/<slug>/followup_email.md`. Same `dry_run` logic applies. `output/index.html` also shows a "Follow-ups due" strip at the top with a pill per company overdue or due today.

`list-due` automatically skips companies whose pipeline `stage` is closed (`rejected`, `withdrawn`, `offer`) or that never had an email to follow up on (`email-skipped` with no address found) — see [Tracking outcomes](#tracking-outcomes) below.

---

## Tracking outcomes

The initial `status` (`sent` / `drafted` / `email-skipped`) only tracks whether the first email went out. To track what happens after — a reply, an interview, a rejection — update the `stage`:

```bash
python3 scripts/state.py update --slug wiz --stage replied
python3 scripts/state.py update --slug wiz --stage interview --note "phone screen booked for Tuesday"
python3 scripts/state.py update --slug wiz --stage rejected
```

Valid stages: `applied`, `replied`, `interview`, `offer`, `rejected`, `ghosted`, `withdrawn`. The last three are "closed" — once set, `list-due` stops surfacing that company and the report hides its follow-up-due date.

To record that you manually completed a LinkedIn connect/message or an ATS application (these can't be detected automatically, so tell Claude and it will log it):

```bash
python3 scripts/state.py mark-task --slug wiz --task connected_hr
python3 scripts/state.py mark-task --slug wiz --task messaged_lead
python3 scripts/state.py mark-task --slug wiz --task applied
```

After any `update` or `mark-task`, regenerate that company's report so the dashboard reflects it: `python3 scripts/generate_report.py wiz`.

---

## View all applications

```bash
python3 scripts/state.py list-all
```

Or open `output/index.html` in a browser for the full dashboard.

---

## Queue management

```bash
# See what's in the queue
python3 scripts/state.py queue list

# See counts
python3 scripts/state.py queue stats

# Add a company manually
python3 scripts/state.py queue add \
  --company "Wiz" \
  --slug "wiz" \
  --website "https://wiz.io" \
  --linkedin "https://linkedin.com/company/wiz" \
  --source "manual"

# Remove a company
python3 scripts/state.py queue remove --slug "wiz"

# Un-stick entries left in "processing" (e.g. an interrupted run)
python3 scripts/state.py queue reset
```

---

## State files

| File | What it tracks |
|------|---------------|
| `state/queue.json` | Companies discovered or added manually, waiting to be processed |
| `state/applications.json` | Companies that have been fully processed — email status, pipeline `stage`, and manually-completed `tasks` (see [Tracking outcomes](#tracking-outcomes)) |
| `state/skipped.json` | Companies that were ruled out (with reason) |

All three are plain JSON — safe to edit by hand, though prefer the `state.py` commands so slugs and dedupe stay consistent.

Each company's `output/<slug>/meta.json` (written by Flow 1/3) holds the same research/contacts/email data as the markdown files in structured form — `generate_report.py` reads it when present and only falls back to parsing the markdown for older output folders that predate it.

---

## Dry-run vs live

| Setting | Behavior |
|---------|---------|
| `dry_run: true` | Email saved as Gmail draft — nothing sent |
| `dry_run: false` | Email sent immediately via Gmail |

Start with `true`. Once you've reviewed a few drafts and they look right, switch to `false`.

---

## What you still do manually

- Send LinkedIn connect requests — open URLs from `output/<company>/linkedin.md`, copy the drafted notes
- Review Gmail drafts before switching to live mode
- Fill in `cv/main.tex`, `config/profile.md`, `config/writing_samples.md`
