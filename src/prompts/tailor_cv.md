# Prompt: Tailor CV

Goal: a version of the user's LaTeX CV that fits one role. It reads like the same CV, changed
where it matters for this job: the experience and projects tell the story the job asks for, not
only the skills line.

**Only on request.** By default an application uses the CV version the user approved
(`cv_variants` in `config/settings.json`, picked by `scripts/cv_keywords.py`), as it is: the
original comes first. Rewriting runs when the user presses **Improve CV** on the report
(`scripts/runs.py cv`), asks for it in the request, or `tailor_cv` is true.

Start from the CV the run names (the original version, or the user's last improved one) and
write the result to `output/<slug>/tailored_cv.tex`.

## Hard rules

1. NEVER add a skill, tool, project, employer, number or length of experience the user doesn't
   have. True facts come from the CV itself, `config/profile.md`, and what the user writes in
   the run's instructions or ticks as a keyword (the user saying it's true is enough).
2. NEVER change dates, company names, job titles, education or contact details.
3. **Exactly one page.** `bash scripts/build_cv.sh <slug>` fails when the PDF has more than one
   page; cut until it passes. Don't shrink fonts or margins to get there: cut words.
4. Same LaTeX layout as the CV you started from (`resume.cls`, its commands and spacing). Don't
   add a new section type the original doesn't have.

## What to change

Read the job description (`output/<slug>/jd.md`) and pick the 3 to 5 things it cares about
most. Then go section by section:

- **Objective / summary**: rewrite it for this kind of role (mobile, backend, security, ...),
  one or two lines. Never the company's name.
- **Experience**: for each job, put the bullets that show the job's top skills first. Rephrase
  a bullet so the work it already describes uses the job's words ("built the Twilio VoIP
  flow" → "built real-time VoIP calling with Twilio" when the job asks for real-time). Cut
  bullets that don't support this role, or merge two weak ones into one. Keep at least one
  bullet per job, and the job's one-line description.
- **Projects**: keep the ones that show this role's skills, cut or shorten the rest.
- **Skills**: reorder the rows and items so the job's stack comes first; add the picked
  keywords; drop items that are noise for this role when space is tight.
- **Keywords the user picked** (true for them): put each one where the work happened, not only
  in Skills. If the CV or profile has work that used it, say so in that bullet ("Kotlin" →
  "...in Kotlin"; "CI/CD" → the bullet about releases). If the user's instructions describe new
  work ("add that I built the BLE pairing flow"), add it as a new bullet under the right job.
  Only a keyword with no honest place in a bullet goes in Skills alone.
- **Adding vs. cutting**: every line added pays for itself with a line cut. Cut in this order:
  bullets that don't fit the role, the weakest project, long bullets shortened to one line,
  then noise in Skills. Never cut so much that a job looks empty.

A change of a few lines to a third of the bullets is typical: the user should still recognize
their CV. The user's instructions win over everything here except the hard rules.

## Style

- Bullets start with a past-tense verb, one line each where possible, a number when the
  original has one (never a new invented number).
- No "passionate", "results-driven", "proven track record" or other filler.
- No company name of the target job anywhere in the CV.
- No dashes as separators in prose (`-`, `—`). Use a comma or restructure. Keep the date
  ranges exactly as the original writes them.

## Output

The modified `.tex`, with a comment above each change so the user can see what moved:

```latex
% TAILORED: rephrased for the job's real-time focus
% TAILORED: moved up, the job asks for SDK work
% TAILORED: removed, not relevant to backend roles
% TAILORED: added from the user's instructions
```

Then the summary of the run says, in a few lines, what changed, which keywords went where, and
any keyword left out and why.
