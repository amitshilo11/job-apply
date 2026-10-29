# Flow 4 — New jobs for you (job alerts + watchlist)

Replaces company discovery (Flow 0, parked). Flow 0 found companies, not open roles, and its
searches never looked for mobile work. This flow starts from **real open jobs**, ranks them
against the profile, and lets the user pick which go to Flow 3.

Triggers: "find jobs", "check job alerts", "any new jobs?", `/job-alerts`.

---

## Step 1 — Jobs from the watchlist

Companies the user wants to work for, checked straight from their job boards:

```bash
python3 scripts/watch_jobs.py --json > <scratchpad>/watch.json
```

Only jobs that are new since the last check and pass `job_filters` (settings) come out.
Warnings on stderr mean a company's board couldn't be read; mention them.

The watchlist is `config/watchlist.json`, managed with the script:
- "watch Acme" → find their careers page, open a job to see which board hosts it (a
  `greenhouse.io`, `lever.co`, `ashbyhq.com` or `comeet.com` URL), then
  `python3 scripts/watch_jobs.py add "Acme" <that URL>`.
- `python3 scripts/watch_jobs.py list` / `remove "<Company>"`.
- Comeet boards are read from the page itself (best effort). If one fails, the company still
  shows up through job alerts.

## Step 2 — Jobs from alert emails (needs Gmail tools)

Job sites email new matches. One-time setup the user does (once per site):
- **LinkedIn Jobs**: search "Android" (and "Mobile Developer", "Kotlin"), location "Haifa
  District" / "Israel", filters hybrid + remote → turn on the alert, daily, by email.
- **AllJobs, Drushim, JobMaster**: same idea with their saved-search alerts.

Then search Gmail for the last 7 days (rank_jobs.py drops anything already shown):

```
from:jobalerts-noreply@linkedin.com newer_than:7d
from:linkedin.com subject:(job OR jobs OR משרה) newer_than:7d
from:alljobs.co.il newer_than:7d
from:drushim.co.il newer_than:7d
from:jobmaster.co.il newer_than:7d
```

From each alert email, pull out every job: `title`, `company`, `location`, `url` (the job's
own link), `source` ("linkedin alert", "alljobs alert"...). Don't open the links yet. If no
Gmail tools are available, say so and use the watchlist only.

## Step 3 — Rank

Put both lists in one JSON file (a list of jobs) and rank:

```bash
python3 scripts/rank_jobs.py <scratchpad>/jobs.json --top 10 --mark-seen
```

It drops excluded titles (staff, principal, manager...) and jobs already shown, scores the
rest (title words, location near home or remote, domain, minus points for senior titles and
experience asks above `max_years`), and flags companies already applied to or skipped.

## Step 4 — Let the user pick

Show the top list: company, title, place, score and its reasons, link. Ask which to go for.
Each pick goes to **Flow 3** with its URL. Nothing is applied to or messaged without a pick.

Tuning: if the list is full of the wrong things, adjust `job_filters` / `job_ranking` in
`config/settings.json` with the user (e.g. add "flutter" to `title_exclude`, or give
"netanya" more points).
