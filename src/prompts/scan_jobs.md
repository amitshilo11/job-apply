# Prompt: Scan Jobs

Goal: extract open roles and decide if any fit the candidate's profile.

## Steps

1. WebFetch the careers/jobs page (or job board URL).
2. List every visible open role: title, team/department, location/remote.
3. For each role, score against `config/profile.md`:
   - Title match: does it align with target function(s)?
   - Seniority: does it match the stated level?
   - Location: remote-friendly or in acceptable location?
   - Deal-breakers: anything from the "avoid" list in profile?
4. Pick ONE best match. If multiple are close, prefer the one most specific to the candidate's strongest skills.
5. If nothing fits, conclude "no matching role".

## Scoring heuristic

- Title contains target function keywords → +2
- Seniority label matches → +2
- Remote or target location → +1
- Deal-breaker present → disqualify immediately
- Over-qualified (very senior for a junior role, or vice versa) → -2

## Output

```
All roles: [list]
Best fit: <title + URL> | none
Decision: role-specific | general
JD snippet (first 200 words): <text>
```
