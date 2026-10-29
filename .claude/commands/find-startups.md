---
description: (Parked) company discovery — use /job-alerts to find real open jobs instead
argument-hint: [count] [vertical or city]
---

Company discovery (Flow 0) is parked: it found companies rather than open roles and never
searched for mobile work. Tell the user that in one line, and offer `/job-alerts` (Flow 4:
new jobs from their job-alert emails and watchlist, ranked against the profile).

Only if the user still wants company discovery after that: read `src/flow0.md` and follow it
for `find-startups $ARGUMENTS` (optional count, default 15, and an optional vertical or city;
a city uses the "City-based variant" section).
