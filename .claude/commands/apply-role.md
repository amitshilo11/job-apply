---
description: Apply to a role you found — role card (company, pros/cons, fit), the right people, EN+HE messages, tracking (Flow 3)
argument-hint: <job url> | at <Company>: <Job Title> | (or paste the job page / drop a screenshot)
---

Read `src/flow3.md` and follow it exactly.

Job: `$ARGUMENTS`

Parse `$ARGUMENTS` as a job posting URL, or `at <Company>: <Job Title>`. If the user pasted a
job page or attached a screenshot, use that: it's the best input (it shows the hiring team).

Stop and ask after the role card when the fit is 1 or 2 out of 5, unless `$ARGUMENTS` says to
go ahead anyway. CV tailoring is off unless `tailor_cv: true` or `$ARGUMENTS` asks for it; the
CV version is picked by `scripts/cv_keywords.py`. Messages are drafted Hebrew first, in every
language in `message_languages`, and must pass `scripts/check_messages.py`.
