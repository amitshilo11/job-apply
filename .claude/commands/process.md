---
description: Full outreach for a company or the queue — research, tailored CV, email, LinkedIn drafts (Flow 1)
argument-hint: <company name> | next | next N | queue | <Company A>, <Company B>, ...
---

Read `src/flow1.md` and follow it exactly, including the "Prerequisites check" at the top.

Target: `$ARGUMENTS`

- If `$ARGUMENTS` is empty or "queue" or "next" (optionally followed by a number), use the
  "Queue mode" section: pull the next N companies from `state/queue.json` via
  `python3 scripts/state.py queue next --count N`.
- If `$ARGUMENTS` contains multiple comma-separated names, use the "Batch processing" section.
- Otherwise treat `$ARGUMENTS` as a single company name.
