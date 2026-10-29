# Flow 3 — Apply to a role you found (the main flow)

The user finds a role and hands it over. They get back:
1. a **role card**: the company in short, the role, pros and cons, a fit score and a verdict;
2. the **right people**: someone they already know there, the job poster, the recruiter and
   team lead, each with a reason and a confidence level;
3. **messages in Hebrew and English** that sound like them, checked for AI tells and mistakes;
4. the **email** (when there's an address) and the **CV** to attach;
5. **tracking**: every person becomes a thread with follow-up dates in the dashboard.

Triggers: `process role <url>`, `apply for <title> at <Company>`, `/apply-role <url>`, or the
user pastes a job page or drops a screenshot of one.

Started from the dashboard's **+ New application** (a background run, `scripts/runs.py`)? Also
follow `src/prompts/background_run.md`: nobody is watching, and it says what to do wherever
this flow would ask.

Load `config/settings.json`, `config/profile.md` and `config/writing_samples.md` at the start.

---

## Prerequisites check

- `config/profile.md` filled in (not template text), `config/writing_samples.md` has at least
  one real sample, `cv/main.tex` exists, `config/settings.json` has `sender_email`.
- If anything is missing, stop and say which file to fill in. Don't make up profile details.

---

## Step 1 — Get the job

Best input: the **pasted job page** (Cmd+A, Cmd+C on the LinkedIn job) or a **screenshot**.
It has the job description, the hiring team ("Meet the hiring team"), the company size and
whether it's hybrid, with no searching.

- **URL**: WebFetch it. For LinkedIn use the public view `https://www.linkedin.com/jobs/view/<id>/`.
  If the page is blocked or empty, say so once and ask for the pasted page or a screenshot;
  if the user isn't around, carry on with WebSearch (`"<Company>" "<title>"`).
- **Company + title**: WebSearch for the posting, WebFetch the best result.

Slug: from `scripts/state.py`'s `slugify()`:

```bash
python3 scripts/state.py slug "<Company>"
```

If `python3 scripts/state.py show --slug <slug>` finds an existing application (another role
at the same company), use `<slug>-<short-role>` instead (e.g. `forsight-robotics-sr-swe`).

Save the **full job description, word for word**, to `output/<slug>/jd.md` (the keyword check
and interview prep read it). Then start `output/<slug>/meta.json`:

```json
{"schema": 2, "company": "...", "job_title": "...", "apply_url": "...", "job_source": "linkedin | comeet | greenhouse | site | ...",
 "website": null, "careers_url": null, "contacts": []}
```

## Step 2 — The company, in short

WebSearch and WebFetch: the website, what they make (one line), size (LinkedIn "N employees",
the pasted page, or news), stage or funding, where the R&D for this role sits, and warning
signs from the last 12 months (layoffs, freezes, shutdown). Keep the URLs you used.

If the company shut down or clearly isn't hiring: log it with `python3 scripts/state.py skip ...`
(reason + source), regenerate the index, and stop.

## Step 3 — CV and keywords

```bash
python3 scripts/cv_keywords.py --slug <slug> --title "<job title>"
```

Picks the approved CV version that fits (writes `cv`, `cv_file`, `cv_keywords` into meta.json)
and lists the job's keywords the CV doesn't have. If it says a better-fitting version isn't
approved yet, mention that in the summary. If it prints a build hint, run it.

CV tailoring (rewriting the CV for this role) only runs when `tailor_cv` is true or the user
asked for it in this request; see `src/prompts/tailor_cv.md`. A one-off ask doesn't change the
setting.

## Step 4 — Role card (then maybe stop)

Follow `src/prompts/role_card.md`: write `role_card` (and `fit_notes`) into meta.json and show
the card in chat. **Fit 1 or 2: stop and ask** whether to continue (unless the user already
said to go ahead). If not, log the skip with the verdict line as the reason and stop.

## Step 5 — People

Follow `src/prompts/find_contacts.md`: people the user named in the request first (§0), then
people they already know (`scripts/referrals.py`), then the hiring team from the job post,
then the right roles for the company's size, then verified search. Write `contacts`,
`referrals` and `alternates` into meta.json. Never guess a profile URL.

## Step 6 — Email address (second channel)

An email the user gave (for the recruiter, or in the request) or one in the job post itself
("send your CV to jobs@...") is best. Otherwise check the Careers and Contact pages for
`careers@`, `jobs@`, `hr@`, `cv@` on their domain. Never guess.
None found: no email, LinkedIn is the channel. Put it in meta.json `email`.

## Step 7 — Messages

Read `src/prompts/draft_linkedin.md` and `src/prompts/draft_email.md`, every time. Draft the
Hebrew version first, then the English. An HR or lead slot with nobody found still gets its
messages, with `{name}` for the first name (`src/prompts/find_contacts.md` §6). Write them into meta.json (`contacts[*]` message
fields, `email_draft`), then run:

```bash
python3 scripts/check_messages.py <slug>
```

Fix every ✗ and re-run until it passes (exit 0). Fix ⚠ warnings when easy.

meta.json is the only place messages live (the report reads it). Don't write `linkedin.md` or
`email.md` anymore. Notes and sources can go in `output/<slug>/research.md` if useful.

## Step 8 — Gmail draft (only with an email address)

Use the **first** language in `message_languages` for Gmail; the others stay in the report to
copy. Attach `cv_file` from meta.json (or the tailored PDF if tailoring ran).

- `dry_run: true`: create a Gmail draft (don't send). Print "Draft saved — review it in Gmail".
- `dry_run: false`: send it, then record it:
  `python3 scripts/state.py event --slug <slug> --key email --event sent --lang <lang>`.

## Step 9 — Save the state

```bash
python3 scripts/state.py add --company "<Company>" --slug "<slug>" --job-title "<title>" \
  --email-sent-to "<email>" --status "<sent|drafted|email-skipped>"
```

`add` builds one tracking thread per person (and one for the email) from meta.json. If the
entry already existed (a re-run), use `python3 scripts/state.py sync --slug <slug>` instead.
Only pass flags you have values for.

## Step 10 — Report and summary

```bash
python3 scripts/generate_report.py <slug>
```

Then print:

```
✓ <Company> — <Job title>                       Fit 3/5 · good
  <company one-liner> · <size> · <where>
  + <top pro>   + <second pro>
  − <top con>   − <second con>
  You know:  Dana Example (Senior Android Developer): ask for a referral first
  People:    Noa Example, HR (job post · high) · Dan Example, lead (medium)
  Email:     Gmail draft → jobs@company.com   (or: no address, LinkedIn only)
  CV:        cv/main.pdf (mobile) · missing from CV: Flutter, Dart
  Next:      send the connect requests from the dashboard: python3 scripts/serve.py
```

Mention once, when relevant: no `Connections.csv` yet (referrals can't be checked), or no
hiring team visible (paste the job page next time).

---

## meta.json (schema 2)

```json
{
  "schema": 2,
  "company": "Acme",
  "job_title": "AI-Native Mobile Engineer",
  "apply_url": "https://...",
  "job_source": "linkedin",
  "website": "https://...",
  "careers_url": "https://...",
  "role_card": { "...": "see src/prompts/role_card.md" },
  "fit_notes": ["+ ...", "- ..."],
  "email": "jobs@acme.com",
  "referrals": [ { "name": "...", "position": "...", "company": "...", "url": "...", "connected_on": "...", "match": "exact" } ],
  "contacts": [
    {
      "key": "hr", "kind": "hr", "title": "HR / Recruiter",
      "name": "...", "name_he": "...", "job_title": "...", "location": "...", "profile": "https://...",
      "source": "job post", "confidence": "high", "why": "...", "connected": false,
      "connect_note": "...", "connect_note_he": "...",
      "first_message": "...", "first_message_he": "...",
      "followups": [ { "n": 1, "text": "...", "text_he": "...", "drafted_at": "YYYY-MM-DD" } ],
      "alternates": [ { "name": "...", "job_title": "...", "location": "...", "profile": "...", "why": "...", "confidence": "medium" } ]
    }
  ],
  "email_draft": {
    "to": "...", "subject": "...", "body": "...", "subject_he": "...", "body_he": "...",
    "followups": [ { "n": 1, "subject": "Re: ...", "body": "...", "body_he": "..." } ]
  },
  "cv": "variant:mobile", "cv_file": "cv/main.pdf",
  "cv_keywords": { "variant": "mobile", "tex": "cv/main.tex", "matched": ["..."], "missing": ["..."], "note": null },
  "interview_prep": null
}
```

Contacts with nobody found stay in the list with `"name": null, "profile": null` and a `why`
saying what was tried. People the user already knows: `"kind": "referral", "connected": true`,
no connect note.
