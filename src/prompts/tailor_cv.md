# Prompt: Tailor CV

Goal: adapt the candidate's LaTeX CV for a specific role (or leave as-is for general use).

Read `cv/main.tex` and this prompt, then write the tailored version directly to `output/<slug>/tailored_cv.tex` (Flow 1, Step 4).

## Rules

1. NEVER add skills or experience the candidate doesn't have.
2. NEVER change dates, company names, or titles.
3. Reorder, rephrase, or remove bullets to emphasize what's most relevant — dropping irrelevant ones is preferred over keeping filler.
4. **Target output: one page.** If the CV is longer, aggressively cut:
   - Remove entire bullet points that don't support the role.
   - Remove entire positions if they add no value for this role (keep at least the 2 most recent).
   - Shorten verbose bullets to a single concise line.
   - Remove optional sections (e.g. hobbies, unrelated certifications) if space is tight.
5. Never cut to the point where a role's work history looks like a gap — at minimum keep 1 bullet per kept position.

## For role-specific tailoring

Given a job description:
- Identify the top 3–5 skills/keywords the JD emphasizes.
- Move bullets that demonstrate those skills to the top of each position's bullet list.
- **Remove** bullets that are clearly irrelevant to the role — if a bullet doesn't support any top skill, cut it.
- If the CV has a summary/objective section, rewrite it to mention the role type (not the specific company).
- Add relevant tech stack keywords if they appear naturally in existing bullets — don't force them.
- After filtering content, if still over one page: shorten remaining bullets, then consider removing the oldest or least relevant positions entirely.

## For general (no role) tailoring

- Move the most impressive/senior-sounding bullets to the top.
- Remove filler bullets (anything vague, redundant, or low-impact) to fit one page.
- Make the summary/objective breadth-first (show range, not narrow specialization).

## What NOT to do

- Don't change the LaTeX formatting or structure.
- Don't add a new section the original CV doesn't have.
- Don't write "I'm passionate about..." anywhere.
- Don't reference the specific company name inside the CV.
- No dashes as separators in prose (`-`, `—`). Use a comma or restructure the sentence. Date ranges use "to" (e.g. "2020 to 2023"), not a hyphen.

## Output

A modified copy of the .tex source with inline comments marking each change:
```latex
% TAILORED: moved up for <reason>
% TAILORED: removed — irrelevant to <role>
% TAILORED: shortened to fit one page
```
