# Flow 3 — With Role

When the user gives a specific job they want to apply for (URL or company + job title), follow these steps.

Trigger phrases:
- `process role <url>`
- `process role at <Company>: <Job Title>`
- `apply for <Job Title> at <Company>`
- `apply to <url>`

Load `config/profile.md` and `config/writing_samples.md` at the start.

---

## Input parsing

**Job URL given** (e.g. `process role https://jobs.lever.co/acme/abc123`):
- WebFetch the URL to get the job title, team, location, and full JD.
- Extract the company name from the page or domain.

**Company + title given** (e.g. `process role at Acme: Backend Engineer`):
- WebSearch: `"<company name>" "<job title>" job posting`
- WebFetch the best result to get the full JD. If not found, proceed with just the title.

Generate slug: lowercase company name, spaces → `-`, strip non-alphanumeric except `-`.

---

## Step 1 — Research company and job

WebSearch: `"<company name>" official website`
WebFetch the homepage to confirm the right company.

Write to `output/<slug>/research.md`:
```
# Research: <Company>
Website: <url>
Careers page: <url or "not found">
Jobs found: [<job title>]
Best fit: <job title>
Apply here: <job URL if known>
Job description snippet: <first 200 words of JD>

Fit notes:
+ <strength 1 vs profile>
+ <strength 2 vs profile>
- <gap or flag 1>
```

---

## Step 2 — Extract contact email

WebFetch the company's Contact or About page.
Look for any of: `careers@`, `jobs@`, `hr@`, `hello@`, `info@` + their domain.

Do NOT guess or make up an email. If none found, write "not found" — still do the LinkedIn and message steps.

Append to `output/<slug>/research.md`:
```
Contact email: <email OR "not found">
```

---

## Step 3 — Draft email

Only if a contact email was found.

Read `config/writing_samples.md` to calibrate tone.
Read `src/prompts/draft_email.md` for tone rules.

Write to `output/<slug>/email.md`:
```
To: <contact email>
Subject: <subject line>
Body:
<email body>
Attachment: output/<slug>/tailored_cv.pdf
```

Do NOT send the email. You are generating it for the user to send manually.

---

## Step 4 — Find people on LinkedIn

Search for HR / recruiter at the company:
```
WebSearch: site:linkedin.com/in "<company name>" (HR OR recruiter OR "talent acquisition" OR "people operations")
```
Take the first result that looks like a real LinkedIn profile URL. Do not hallucinate URLs.
If nothing reliable found, write "not found".

Search for a relevant team lead:
```
WebSearch: site:linkedin.com/in "<company name>" ("engineering manager" OR "tech lead" OR "team lead")
```
Filter by relevance to the target function from `config/profile.md`. Take the first strong match.

Append to `output/<slug>/research.md`:
```
HR profile: <url OR "not found">
Team lead profile: <url OR "not found">
```

---

## Step 5 — Draft LinkedIn messages

Read `config/writing_samples.md` to calibrate tone.
Read `src/prompts/draft_linkedin.md` for tone rules.

Write to `output/<slug>/linkedin.md`:
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

## Step 6 — Log state

```bash
python3 scripts/state.py add \
  --company "<company name>" \
  --slug "<slug>" \
  --job-title "<title>" \
  --email-sent-to "<email or null>" \
  --status "drafted" \
  --hr-url "<url or null>" \
  --lead-url "<url or null>"
```

---

## Step 7 — Generate report

```bash
python3 scripts/generate_report.py <slug>
```

This creates `output/<slug>/report.html` and updates `output/index.html`.

Print a short summary:
```
✓ <Company> — <Job Title>
  Email draft: output/<slug>/email.md
  Report: output/<slug>/report.html

  LinkedIn (send manually):
  HR:        <url or not found>
  Team lead: <url or not found>
  → Drafts in output/<slug>/linkedin.md
```
