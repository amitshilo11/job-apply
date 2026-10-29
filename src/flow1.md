# Flow 1 — Company Outreach Playbook

When the user says "process company X" (or gives a list, or "process next from queue"),
follow these steps. It's Flow 3 with a first step that finds the role: once the best-fit
role is picked, the role card, people, messages, tracking and report are exactly Flow 3's
(see `src/flow3.md`).

Load `config/settings.json`, `config/profile.md`, and `config/writing_samples.md` at the start.

The **Follow-up sub-flow** at the end of this file is what `/followups` and `/today` use.

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

If at any point you stop processing a company (shut down, no product, deal-breaker, the user
declined a low-fit role, etc.), run this before telling the user:

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

Then regenerate the index so it appears in the "Not processed" tab:
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
- Note the job board if the careers page redirects to one (Greenhouse, Lever, Ashby, Comeet):
  the user can add it to the watchlist later (`scripts/watch_jobs.py add`).

Slug: always from `slugify()` in `scripts/state.py` (lowercase, non-alphanumeric runs → `-`):

```bash
python3 -c "import sys; sys.path.insert(0, 'scripts'); from state import slugify; print(slugify('<Company>'))"
```

## Step 2 — Scan jobs and pick one

Search in TWO places and merge the results:

**A) Company careers page** — WebFetch the careers page (or its job board) found in Step 1.

**B) LinkedIn jobs** — `WebSearch: "<company name>" jobs site:linkedin.com/jobs` (and the
company's LinkedIn jobs tab if you can find its id). LinkedIn often lists roles the careers
page misses.

Score each job against `config/profile.md` (target function, seniority, location, deal-breakers)
and pick at most ONE best fit. If none fit, there's no role card: decide with the user whether a
general intro is worth it, or log a skip ("no matching role").

With a role picked: save its full job description to `output/<slug>/jd.md`, start
`output/<slug>/meta.json` as in Flow 3 Step 1, and continue.

## Steps 3 to 10 — Same as Flow 3

Run Flow 3 from **Step 2 (the company, in short)** to **Step 10 (report and summary)**:
company research, CV and keywords, role card (stop and ask at fit 1 or 2), people
(`src/prompts/find_contacts.md`), email address, messages (Hebrew first, then the checker),
Gmail draft, `state.py add`, report.

If the company came from the queue, after `state.py add` (or a skip) also run:
```bash
python3 scripts/state.py queue remove --slug "<company-slug>"
```

---

## Follow-up sub-flow

Triggers: "show follow-ups", "check due", "draft follow-ups", `/followups`, `/today`, and the
morning reminder.

1. See what's due (this also closes threads that got no reply after the last follow-up):
   ```bash
   python3 scripts/state.py today --json
   ```
2. For every item in the `followups` group (and any `message` item whose first message isn't
   drafted yet):
   - Read that person's history in `output/<slug>/meta.json` (what was already sent, in which
     language: the thread's `lang` in `state.py show --slug <slug>`) and the role card.
   - Draft follow-up #n per `src/prompts/draft_linkedin.md` ("Follow-ups") or
     `src/prompts/draft_email.md` ("Follow-up emails"): Hebrew first, then English, short, with
     one new useful thing or a simple question.
   - Save it in meta.json: `contacts[k].followups` += `{"n": n, "text": ..., "text_he": ...,
     "drafted_at": "YYYY-MM-DD"}`; for the email, `email_draft.followups` += `{"n": n, "subject":
     "Re: ...", "body": ..., "body_he": ...}`.
   - `python3 scripts/check_messages.py <slug>` and fix every ✗.
   - Email follow-ups: Gmail reply in the same thread, as a draft (`dry_run: true`) or sent. If
     sent: `python3 scripts/state.py event --slug <slug> --key email --event followup_<n>`.
3. If Gmail tools are available, look for replies: for each open email thread, search Gmail
   (`from:<address or @domain> newer_than:30d`). For each real reply:
   `python3 scripts/state.py event --slug <slug> --key email --event replied`, and tell the user.
4. `python3 scripts/generate_report.py --all`
5. Show the Today list (`python3 scripts/state.py today`) and point to the dashboard
   (`python3 scripts/serve.py`), where each message has Copy and Sent buttons.

LinkedIn messages are never sent automatically. The user sends them, then clicks Sent in the
dashboard or tells Claude ("sent the follow-up to Noa"), and Claude records it:
`python3 scripts/state.py event --slug <slug> --key <key> --event followup_<n> --lang <he|en>`.

---

## Batch processing

If the user gives multiple companies (comma-separated or one per line), process them one at a
time in order. Print a summary table at the end.

---

## Queue mode

When the user says `process next from queue`, `process next N from queue`, or `process the queue`:

1. **Get companies from queue:**
   ```bash
   python3 scripts/state.py queue next --count <N>
   ```
   (Use `--count 1` for "process next", `--count N` for "process next N", or `--count 999` for "process the queue".)

2. **Parse the JSON output** — it's a list of objects with `company`, `slug`, `website`, `linkedin_url`, `source` fields.

3. **For each company** in the list, run the steps above. The `website` field from the queue
   entry gives you a head start for Step 1 — use it directly rather than searching from scratch.

4. **After `state.py add`** or after an **early-stop / skip**, always call:
   ```bash
   python3 scripts/state.py queue remove --slug "<slug>"
   ```
   This cleans the queue entry regardless of the outcome.

5. After all companies are processed, print the usual summary table.
