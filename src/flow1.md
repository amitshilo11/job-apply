# Flow 1 — Company Outreach Playbook

When the user says "process company X" (or gives a list), follow these steps exactly.
Load `config/settings.json`, `config/profile.md`, and `config/writing_samples.md` at the start.

---

## Prerequisites check

Before processing any company:
- `config/profile.md` must exist and be filled (not just the template placeholder text)
- `config/writing_samples.md` must have at least 1 real sample
- `cv/main.tex` must exist
- `config/settings.json` must have sender_email set

If any of these are missing, stop and tell the user which files need to be filled first.

---

## Early stop — log as skipped

If at any point you stop processing a company (shut down, no product, deal-breaker, etc.),
run this before telling the user:

```bash
python3 scripts/state.py skip \
  --company "<company name>" \
  --slug "<company-slug>" \
  --reason "<short reason>" \
  --details "<one or two sentences>" \
  --source "<url where you found out, if any>"
```

If the company came from the queue, also clean it up:
```bash
python3 scripts/state.py queue remove --slug "<company-slug>"
```

Then regenerate the index so it appears in the "Not processed" table:
```bash
python3 scripts/generate_report.py --all
```

---

## Step 1 — Discover

Use WebSearch: `"<company name>" official website`

Pick the top result that looks like the company's own domain (not LinkedIn, Crunchbase, etc.).
Then WebFetch the homepage — confirm you have the right company.

Find the careers/jobs page:
- Try common paths: `/careers`, `/jobs`, `/about/careers`, `/work-with-us`
- Or WebSearch: `"<company name>" careers jobs site:<their-domain>`

Write findings to `output/<company-slug>/research.md`:
```
# Research: <Company>
Website: <url>
Careers page: <url or "not found">
```

The company slug is the lowercase company name with spaces replaced by dashes (e.g., "Wiz Security" → `wiz-security`).

---

## Step 2 — Scan jobs

Search for jobs in TWO places and merge the results:

**A) Company careers page** — WebFetch the careers page found in Step 1.

**B) LinkedIn jobs** — Always run this search regardless of what the careers page shows:
```
WebFetch: https://www.linkedin.com/jobs/search/?f_C=<linkedin-company-id>&geoId=92000000
```
To find the LinkedIn company ID: WebSearch `site:linkedin.com/company "<company name>"` and grab the numeric ID from the company page URL (e.g., linkedin.com/company/netafim → check their jobs tab URL for `f_C=XXXXX`). If you can't find the ID, WebSearch: `"<company name>" jobs site:linkedin.com/jobs`.

Merge all titles from both sources. LinkedIn often has roles the company's own careers page misses.

Score each job against `config/profile.md`:
- Does the role match the target function?
- Does seniority level match?
- Any deal-breakers from the profile?

Pick at most ONE best-fit role. If none fit, note "no matching role — will send general email".

Append to `output/<company-slug>/research.md`:
```
Jobs found: [list all titles]
Best fit: <title> OR "none"
Apply here: <direct job URL — LinkedIn job page or ATS link> (omit line if no specific role)
Decision: role-specific email / general email
Job description snippet: <paste the first 200 words of the JD if available>

Fit notes:
+ <strength 1 vs profile>
+ <strength 2 vs profile>
- <gap or flag 1>
- <gap or flag 2>
```

Always include `Apply here:` when a specific role was found — it drives the Apply checkbox in the report.
Always include `Fit notes:` with at least 2 `+` lines and 1 `-` line — they appear in the Research card.

---

## Step 3 — Extract contact email

WebFetch the company's Contact or About page.
Look for any of: `careers@`, `jobs@`, `hr@`, `hello@`, `info@`, `team@` + their domain.

Do NOT guess or make up an email. If none found after checking 2-3 pages, write "no email found" and skip steps 5–6 (CV tailoring + email send). Still do the LinkedIn steps.

Append to `output/<company-slug>/research.md`:
```
Contact email: <email OR "not found">
```

---

## Step 4 — Tailor CV

Always run this step whenever a matching role was found (regardless of whether a contact email exists — the CV is needed for ATS applications too).

Read `cv/main.tex` and `src/prompts/tailor_cv.md` (tailoring rules), then write the tailored `.tex` content directly to `output/<company-slug>/tailored_cv.tex`, using the job title and JD snippet from `research.md` to decide what to emphasize. Mark each changed bullet with a `% TAILORED:` comment as described in the rules.

Then compile to PDF:
```bash
bash scripts/build_cv.sh <company-slug>
```

This creates `output/<company-slug>/tailored_cv.pdf`.

If compilation fails, stop and show the error — do not proceed without a working PDF.

---

## Step 5 — Draft email

Read `config/writing_samples.md` to calibrate tone before drafting.
Read `src/prompts/draft_email.md` for the full tone rules and structure.

Write the draft to `output/<company-slug>/email.md`:
```
To: <contact email>
Subject: <subject line>
Body:
<email body>
Attachment: output/<company-slug>/tailored_cv.pdf
```

Show the draft to the user and ask: "looks good to send?" before proceeding if `dry_run: true`.

---

## Step 6 — Send email

If `dry_run: true` in settings.json:
  - Use Gmail MCP to create a draft (do NOT send)
  - Print: "Draft saved — review at Gmail before sending"

If `dry_run: false`:
  - Use Gmail MCP to send the email with the PDF attached
  - Print: "Email sent to <address>"

---

## Step 7 — LinkedIn lookup

Search for HR / recruiter at the company:
```
WebSearch: site:linkedin.com/in "<company name>" (HR OR recruiter OR "talent acquisition" OR "people operations")
```

Take the first result that looks like a real LinkedIn profile URL. Do not hallucinate profile URLs.
If nothing reliable found, write "HR profile: not found".

Search for a relevant team lead:
```
WebSearch: site:linkedin.com/in "<company name>" ("engineering manager" OR "tech lead" OR "team lead")
```

Filter by relevance to the target function from `config/profile.md`.
Take the first strong match.

---

## Step 8 — Draft LinkedIn messages

Read `src/prompts/draft_linkedin.md` for tone rules.

Write to `output/<company-slug>/linkedin.md`:
```
# LinkedIn Outreach: <Company>

## HR / Recruiter
Profile: <url OR "not found">
Connect note (≤300 chars):
<note>

First message (after accepting):
<message>

---

## Team Lead
Profile: <url OR "not found">
Connect note (≤300 chars):
<note>

First message (after accepting):
<message>
```

These are for YOU to send manually. Open each URL, copy the text, hit Connect.

---

## Step 8.5 — Write structured metadata

Write `output/<company-slug>/meta.json` capturing everything gathered in Steps 1–8, so `generate_report.py` doesn't have to regex-parse the markdown:

```json
{
  "website": "<url or null>",
  "careers_url": "<url or null>",
  "best_fit": "<job title or null>",
  "apply_url": "<url or null>",
  "fit_notes": ["+ <strength 1>", "+ <strength 2>", "- <gap 1>"],
  "email": "<contact email or null>",
  "contacts": [
    {"title": "HR / Recruiter", "profile": "<url or null>", "job_title": "<title or null>", "connect_note": "<text or null>", "first_message": "<text or null>"},
    {"title": "Team Lead", "profile": "<url or null>", "job_title": "<title or null>", "connect_note": "<text or null>", "first_message": "<text or null>"}
  ],
  "email_draft": {"to": "<email or null>", "subject": "<subject or null>", "body": "<body or null>"}
}
```

Omit `email_draft` (or set to `null`) if Step 5/6 was skipped because no contact email was found.

---

## Step 9 — Log state

Run (only include a flag if you actually have a value — `state.py` treats a missing flag or the
literal word `null` the same way, but omitting it is clearer):
```bash
python3 scripts/state.py add \
  --company "<company name>" \
  --slug "<company-slug>" \
  --job-title "<title>" \
  --email-sent-to "<email>" \
  --status "<sent|drafted|email-skipped>" \
  --hr-url "<url>" \
  --lead-url "<url>"
```

This appends an entry to `state/applications.json` with `followup_due` set to today + `followup_days` from settings.

If the company came from the queue, remove it:
```bash
python3 scripts/state.py queue remove --slug "<company-slug>"
```

---

## Step 10 — Report back

Generate the HTML report:
```bash
python3 scripts/generate_report.py <company-slug>
```

This creates `output/<slug>/report.html` (full application summary) and updates `output/index.html` (master dashboard). Tell the user: "Report ready — open output/<slug>/report.html in a browser."

Then print a short summary:

```
✓ <Company>
  Email: [sent to X / draft saved / skipped — no email found]
  CV: output/<slug>/tailored_cv.pdf
  Report: output/<slug>/report.html
  Follow-up due: <date>

  LinkedIn (send these manually):
  HR:        <url or not found>
  Team lead: <url or not found>
  → Drafts in output/<slug>/linkedin.md
```

---

## Follow-up sub-flow

When the user says "show follow-ups" or "check due":

```bash
python3 scripts/state.py list-due
```

For each entry due, draft a short follow-up email using `src/prompts/draft_email.md` (follow-up variant).
Save to `output/<slug>/followup_email.md`.
Same dry_run logic as Step 6.
After sending, run:
```bash
python3 scripts/state.py mark-sent --slug "<slug>" --type followup
```

When you learn what happened after a follow-up (reply, interview, rejection), update the pipeline stage:
```bash
python3 scripts/state.py update --slug "<slug>" --stage replied
```
`rejected`, `withdrawn`, and `offer` are closed stages — no more follow-ups will be surfaced for them.

---

## Batch processing

If the user gives multiple companies (comma-separated or one per line), process them one at a time in order. Print a summary table at the end.

---

## Queue mode

When the user says `process next from queue`, `process next N from queue`, or `process the queue`:

1. **Get companies from queue:**
   ```bash
   python3 scripts/state.py queue next --count <N>
   ```
   (Use `--count 1` for "process next", `--count N` for "process next N", or `--count 999` for "process the queue".)

2. **Parse the JSON output** — it's a list of objects with `company`, `slug`, `website`, `linkedin_url`, `source` fields.

3. **For each company** in the list, run the standard 10-step flow (Steps 1–10 above). The `website` field from the queue entry gives you a head start for Step 1 — use it directly rather than searching from scratch.

4. **After Step 9** (state logged) or after an **early-stop / skip**, always call:
   ```bash
   python3 scripts/state.py queue remove --slug "<slug>"
   ```
   This cleans the queue entry regardless of the outcome.

5. After all companies are processed, print the usual summary table.
