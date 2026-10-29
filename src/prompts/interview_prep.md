# Prompt: Interview prep

Trigger: the user got an interview ("got an interview at Acme", "/interview-prep acme").

Goal: one page that makes the next interview easier: the company in 30 seconds, how they
interview, the questions this role will likely bring, which of the user's real stories answers
each one, and good questions to ask them.

---

## Steps

1. Record it: `python3 scripts/state.py update --slug <slug> --stage interview --note "<when, with whom>"`
   (skip if the stage is already `interview`).
2. Read what's known: `output/<slug>/meta.json` (role card, contacts, what was sent),
   `output/<slug>/jd.md`, `config/profile.md`, `cv/main.tex` (or the CV version in `cv_file`),
   and `config/stories.md`.
3. Research (WebSearch, last 12 months where it matters):
   - the product and the team behind this role, recent news (funding, launches, layoffs);
   - how they interview: `"<Company>" interview process software engineer`, Glassdoor /
     Comparably / LinkedIn posts / their engineering blog. Say what's confirmed and what's a
     guess;
   - the interviewers, if the user named them: public LinkedIn info only (title, team, time at
     the company).
4. Write `meta.json` → `interview_prep`:

```json
"interview_prep": {
  "updated": "YYYY-MM-DD",
  "company_brief": "3 to 4 sentences: what they sell, to whom, where this team fits, one recent fact.",
  "process": "What's known about their stages (e.g. recruiter call → home task → technical → manager), with the source, or 'unknown'.",
  "questions": [
    {"q": "Walk me through how you'd structure a large Compose app.",
     "why": "The JD stresses scalable mobile architecture.",
     "angle": "The CV project that shows this best (e.g. an architecture they designed), with its result."}
  ],
  "stories": [
    {"theme": "Speeding up delivery", "story": "The CI/CD work on the CV", "proof": "the before/after numbers from the CV"}
  ],
  "ask_them": ["What does the first 3 months look like for this role?"],
  "prep": ["Read up on Flutter basics: the JD's core stack, not on your CV yet"]
}
```

- **questions**: 8 to 12. Mix technical (from the JD's stack and the role card's
  `stack_missing`, since gaps get probed) and behavioral (ownership, conflict, a mistake, why
  this company, why leaving). `angle` points at a real story or CV fact.
- **stories**: 3 to 5, from `config/stories.md` when filled in. When a story there is still
  empty, use the matching CV bullet and add "(fill in config/stories.md)" so the user knows
  it needs their details. Never invent details, numbers or outcomes.
- **ask_them**: 4 to 6 specific questions (the team, the roadmap, how success is measured,
  something from the research). No salary question in the first round unless the user wants it.
- **prep**: a short checklist of what to refresh, based on the gaps.
- If the interview is likely in Hebrew (an Israeli team, a Hebrew job post), add Hebrew wording
  for the "tell me about yourself" answer and the top 2 stories in `prep`.

5. Also save a readable copy to `output/<slug>/interview_prep.md`.
6. `python3 scripts/generate_report.py <slug>`: the report shows an "Interview prep" card.
7. Tell the user it's ready, with the 3 questions they should practice first.
