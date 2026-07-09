---
description: Draft follow-ups for every application that's due (Follow-up sub-flow in Flow 1)
---

Read `src/flow1.md` and follow the "Follow-up sub-flow" section near the end.

Run `python3 scripts/state.py list-due` first, then draft a short follow-up email
(per `src/prompts/draft_email.md`, follow-up variant) for each entry due, saved to
`output/<slug>/followup_email.md`. Respect `dry_run` in `config/settings.json` exactly
as Step 6 of Flow 1 does.
