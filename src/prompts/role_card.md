# Prompt: Role card

Goal: one short, honest summary that answers "is this worth my time?" before any message is
written. It's the first thing in the report and the first thing you show in chat.

Inputs: the job description (`output/<slug>/jd.md`), the company research from this run,
`config/profile.md`, `config/settings.json` (`home_location`), and the output of
`python3 scripts/cv_keywords.py --slug <slug>` (which CV fits, and which job keywords it lacks).

---

## What goes in it

Write it into `meta.json` as `role_card` (the values below are made-up examples of the shape,
not facts about any company):

```json
"role_card": {
  "fit_score": 3,
  "verdict": "good",
  "verdict_line": "Strong Android match and close to home; the catch is Flutter, which you haven't used.",
  "company": {
    "one_liner": "Industrial AI: sensors on factory machines that predict failures.",
    "size": "~400 employees (LinkedIn)",
    "stage": "Series F, $75M (2024)",
    "location": "Haifa (R&D), New York (HQ)",
    "warning_signs": ["Laid off ~10% in early 2025 (Calcalist)"],
    "sources": ["https://...", "https://..."]
  },
  "role": {
    "summary": "Build the Flutter app field technicians use to install sensors, with AI-guided steps.",
    "work_mode": "hybrid",
    "location": "Haifa",
    "commute": "~35 min by car (approx.)",
    "years_required": "5+",
    "years_yours": "3+",
    "seniority": "senior",
    "stack_have": ["Android", "iOS", "LLM", "Firebase"],
    "stack_missing": ["Flutter", "Dart", "BLE", "NFC"]
  },
  "pros": ["...", "..."],
  "cons": ["...", "..."]
}
```

Also write `fit_notes` (`["+ pro", "- con"]`, same content) for older readers.

### Company (keep it short)
- **one_liner**: what they make, in plain words. No marketing language ("revolutionizing").
- **size**: from the LinkedIn company page ("N employees"), the pasted job page, or a news
  article. Say where it came from. Unknown is fine: write "unknown".
- **stage**: public / last funding round and year / bootstrapped / acquired. Unknown is fine.
- **location**: where the R&D team for this role sits.
- **warning_signs**: layoffs, hiring freezes, shutdown rumors, a recent acquisition, a CEO
  leaving, from the last 12 months. Search for them:
  `"<Company>" layoffs OR פיטורים 2025 OR 2026`, `"<Company>" funding OR גיוס הון`. Empty list if
  you found nothing; never invent one.
- **sources**: the URLs you actually used.

### Role
- **summary**: what you'd build, in one sentence. Not the JD's first line.
- **work_mode**: `on-site`, `hybrid`, `remote`, or `unknown`, from the JD or pasted page.
- **commute**: from `home_location` to the office, by car, marked "(approx.)". Use what you know about
  driving times between Israeli cities. Remote: "none".
- **years_required** vs **years_yours** (`3+` from the profile) and **seniority** as the JD
  states it.
- **stack_have / stack_missing**: from `cv_keywords.py`. Add the role's core tech if the script's
  word list missed it, but never move something into `stack_have` that isn't on the CV or in
  the profile.

### Pros and cons
Two to four of each, about **this person and this role**, specific enough to act on:
- Good: "Kotlin + Compose is the core stack, your strongest", "Haifa, hybrid 2 days: about 35 min",
  "Security domain, same as your current job", "Asks 5+ years, you have 3+".
- Bad: "Great company culture", "Exciting opportunity", "Competitive salary" (unless the JD
  actually states a number), anything you can't point to in the JD or research.

---

## Fit score and verdict

| Score | Verdict | When |
|---|---|---|
| 5 | `strong` | Core stack matches (Android/Kotlin/mobile, or the full-stack profile), years asked ≤ yours + 1, commute OK or hybrid/remote, no deal-breakers |
| 4 | `good` | One real gap (a secondary tech missing, 1 to 2 extra years asked, a longer commute) |
| 3 | `good` | Two gaps, still worth a message |
| 2 | `long shot` | Core stack mismatch (e.g. C#/.NET desktop, Flutter-only), or 3+ years over, or a profile nice-to-have turned into a must-have you lack |
| 1 | `skip` | A deal-breaker from `config/profile.md` (fully on-site far away, pure enterprise with no startup DNA), Staff/Principal/10+ years, or nothing in common |

`verdict_line`: one sentence, naming the one thing that decides it.

---

## Show it, then decide

Print the card in chat, short:

```
Acme Medical · Software Engineer, Imaging             Fit 2/5 · long shot
Company  Surgical imaging device, Haifa, size unknown
Role     C#/.NET desktop software for the surgical system · on-site? unknown · 2+ yrs
+ 10 min from home · real product, small startup
− C#/.NET is the core stack, not yours · no mobile work · regulated (IEC 62304) paperwork
Verdict  only if you want to switch stacks
```

If the score is 1 or 2, **stop and ask** before finding people or writing messages: "Fit is
2/5 (long shot): <verdict_line>. Still want messages for this one?" Unless the user already
said to go ahead regardless. If they say no, log it as skipped with the verdict line as the
reason (`python3 scripts/state.py skip ...`) and regenerate the index.
