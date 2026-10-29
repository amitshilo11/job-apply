# Prompt: Draft email

Goal: a short email the user would write, true in every line. Not a cover letter.

Email is the second channel: most addresses found are general inboxes (careers@, info@).
LinkedIn messages to the right person matter more. Keep the email short and useful anyway.

Everything in `draft_linkedin.md` sections 1 to 3 applies here too: the voice comes only from
`config/writing_samples.md` (the "Learned from your edits" section first), Hebrew is written
first and natively, and the fact rule is non-negotiable. Read them before drafting.

---

## Structure

```
Subject: <role title> / <first name>

Hey <first name>,            (or "Hey," / "Hi team," for a company inbox)

<1 sentence: the role, and one concrete thing from the job description that made the user write.>

<1 to 2 sentences: the most relevant thing the user has done for this role, from the CV, with a number
if there is one. No stretching to fit.>

<CV attached + an easy close, the way the samples close.>

<first name>
```

- Body 60 to 120 words. Short paragraphs, at most 2 sentences each.
- No open role: same shape, "not sure if you're hiring right now" style first line, and the
  "why this company" sentence carries more weight.
- Gaps (a missing technology, fewer years): don't apologize and don't oversell. Either leave
  it out, or one honest line about the closest thing the user has done.
- The Hebrew version: subject `<תפקיד> / <שם פרטי>`, "היי <שם>," or "היי,", spoken Israeli Hebrew,
  tech words in English (Android, backend, SDK), no `שלום רב` / `לכבוד` / `בברכה` / `מצורף בזאת`.
  Plain text, no RTL control characters.

## Follow-up emails (drafted later by the follow-up flow)

Reply in the same thread, subject `Re: <original subject>`.

- #1: under 40 words. One new, useful thing (a relevant project line, a GitHub link) or a
  simple question ("is the role still open?").
- #2 (last): under 30 words, closes the loop politely.

## Attachment

Attach `meta.json` → `cv_file` (picked by `scripts/cv_keywords.py`: the approved CV version
that fits the role, `cv/main.pdf` by default). Only a tailored CV (`output/<slug>/tailored_cv.pdf`)
replaces it, and only when tailoring was asked for in this request or `tailor_cv` is true.

## Never

The "Never" list in `draft_linkedin.md` section 6, plus: "I am writing to express my
interest", "Please find attached", "I look forward to hearing from you", "Kind regards".

## Save, then check

Write into `meta.json` → `email_draft`: `to`, `subject`, `body`, `subject_he`, `body_he`
(follow-ups: `followups: [{"n": 1, "subject": ..., "body": ..., "body_he": ...}]`). Then:

```bash
python3 scripts/check_messages.py <slug>
```

Fix every ✗ error and re-run until it passes.
