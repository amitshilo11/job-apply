---
description: Apply to one specific job posting by URL or company + title (Flow 3)
argument-hint: <job url> | at <Company>: <Job Title>
---

Read `src/flow3.md` and follow it exactly.

Job: `$ARGUMENTS`

Parse `$ARGUMENTS` as either a direct job posting URL, or `at <Company>: <Job Title>`.
