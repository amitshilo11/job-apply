---
description: Draft every follow-up that's due (LinkedIn and email), Hebrew + English, then show today's list
---

Read `src/flow1.md` and follow the "Follow-up sub-flow" section near the end.

Start with `python3 scripts/state.py today --json`. Draft follow-up #n for every person in the
`followups` group (per `src/prompts/draft_linkedin.md` / `draft_email.md`), save them into each
application's meta.json, run `python3 scripts/check_messages.py <slug>` until clean, handle
email follow-ups per `dry_run`, regenerate the reports, and finish with the Today list.

LinkedIn messages are never sent for the user: they copy them from the dashboard
(`python3 scripts/serve.py`) and click Sent.
