---
description: Full outreach for a company or the queue — find the best role, then role card, people, EN+HE messages (Flow 1)
argument-hint: <company name> | next | next N | queue | <Company A>, <Company B>, ...
---

Read `src/flow1.md` and follow it exactly, including the "Prerequisites check" at the top.

Target: `$ARGUMENTS`

- If `$ARGUMENTS` is empty or "queue" or "next" (optionally followed by a number), use the
  "Queue mode" section: pull the next N companies from `state/queue.json` via
  `python3 scripts/state.py queue next --count N`.
- If `$ARGUMENTS` contains multiple comma-separated names, use the "Batch processing" section.
- Otherwise treat `$ARGUMENTS` as a single company name.

Once a role is picked, the steps are Flow 3's (`src/flow3.md`): role card (stop and ask at fit
1 or 2), people, messages Hebrew first, `scripts/check_messages.py`, tracking, report. CV
tailoring is off unless `tailor_cv: true` or `$ARGUMENTS` asks for it ("with a tailored cv").
