---
description: New jobs for you — from your job-alert emails and watchlist, ranked against your profile (Flow 4)
argument-hint: [watch <Company> <url>]
---

Read `src/flow4.md` and follow it.

If `$ARGUMENTS` starts with "watch", add that company to the watchlist instead
(`python3 scripts/watch_jobs.py add "<Company>" <url>`, finding the job-board URL first if only
a company name was given) and stop.

Otherwise: watchlist jobs, alert-email jobs (if Gmail tools are available), rank with
`scripts/rank_jobs.py`, show the top list, and ask which ones to run through `/apply-role`.
