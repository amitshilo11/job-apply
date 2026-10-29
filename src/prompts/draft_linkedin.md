# Prompt: Draft LinkedIn messages

Goal: messages the user would actually write: short, plain, and true. Not a recruiter
template, not a pitch, and not "AI trying to sound casual".

---

## 1. Where the voice comes from (and only from)

Read `config/writing_samples.md` every time, in this order:

1. **"Learned from your edits"**: what the user actually sent after changing a draft, or wrote
   from scratch. This beats everything else. Notice what was changed: that's the lesson.
2. The sent samples and the user's own templates (Template D is the default for HR connect notes).
3. The tone notes at the bottom.

Match the samples' openings, stock phrases (the tone notes at the bottom of that file list
them), length, capitalization and emoji habits.

Do **not** add "make it human" tricks that aren't in the samples: no lowercase "i", no "tbh",
no planted typos, no fake slang. Sounding like the user means sounding like the samples, not
sounding casual.

## 2. Hebrew first, then English

Write the Hebrew version first, from the Hebrew samples. Then the English one, from the
English samples. Neither is a translation of the other: same facts, each written the way
the user writes in that language. (Hebrew drafted from English comes out stiff, e.g. "ההתאמה
בתחום עניינה אותי".)

Write every message once per language in `message_languages` (`config/settings.json`).

## 3. The fact rule (non-negotiable)

- **About the user:** only what's in `config/profile.md`, the CV, or the samples. No stretching to
  fit a role ("the core is strong backend and systems work" when the profile says Android).
- **About them:** one concrete detail from the job description or the role card (the product,
  the team the JD names, a technology in the JD that the user has really used). A detail, not
  praise.
- **Nothing the user didn't do.** Never "I've been reading up on...", "I've been following...",
  "I've been curious about X for a while", "I saw your post/talk", "I use your product",
  "קראתי על", "עוקב אחריכם". If the user tells you it's true, it can go in.
- **Nothing that hasn't happened.** Never "I sent an email to your careers inbox" or "I applied
  on the site" in a draft. Those may never happen, or happen later. The user can add them when
  sending, if they're true by then.
- **Talk to them, not about them.** The recipient is "you". Never their name mid-message in
  third person ("שלחתי גם מייל לנועה" in a message to Noa), never their own email address.

## 4. The messages

### Connect note (not for people the user already knows)
- Max `connect_note_max_chars` characters (default **200**: LinkedIn's limit on free accounts).
  Count them. Aim for 100 to 170.
- Who the user is, in one phrase ("Android developer, 3+ years in <their domain>"), why this company
  (one real thing), a low-pressure line. No ask, no CV, no links.
- Free accounts only get a few notes a month, so it has to earn its place. A note that says
  nothing specific is worse than none.

### First message (after they accept)
- Under 80 words, 2 to 4 short sentences.
- The role (name it), the one most relevant thing the user has done for it (a CV fact, a number if
  there is one), and an easy ask: a short call, whether the role is still open, or who the
  right person is.
- **HR / recruiter:** practical. Role, fit in one line, "happy to send my CV or jump on a call".
- **Team lead / hiring manager:** lead with the work, not the job hunt. What in the JD matches
  something the user has built.
- **Founder / CTO (small startup):** short and direct: the product, and why the user fits.
- **Referral (someone the user knows):** warm and easy to say no to. Mention how they know each other
  if `why` or the connection date suggests it, the role link, and ask if they'd be OK referring
  the user or sharing what the team is like. No pressure, no guilt.

### Follow-ups (drafted later by the follow-up flow)
- #1 (about 4 work days after the first message): under 40 words. One new, useful thing (a
  short line on a relevant project, a GitHub link) or a simple question ("is the role still
  open?"). Not "just bumping this".
- #2 (the last one): under 30 words. Closes the loop politely, leaves the door open.
- Same language(s) as the earlier messages in that thread.

## 5. Greeting and sign-off

- English: "Hey <first name>," (or "Hi"), like the samples. Hebrew: "היי <name_he>," when
  `name_he` is set, otherwise "היי <English first name>,".
- Generic greetings ("Hey team") only for a company inbox, never on LinkedIn.
- No sign-off on LinkedIn messages beyond what the samples do.

## 6. Never

English: "I'm excited to", "I'd love the opportunity", "passionate", "came across your profile",
"great fit", "perfect fit", "I believe I would be", "sounds like a really interesting problem",
"unique problem space", "exactly the kind of challenge", "fun challenge", "serious team",
"impressive work", "cutting-edge", "innovative", "leverage", "I pick things up fast",
"worth a shot", "Please let me know if", "hope this message finds you well", "Best regards".

Hebrew: "אשמח מאוד להזדמנות", "נרגש", "בעל מוטיבציה גבוהה", "ניסיון עשיר", "נתקלתי בפרופיל שלך",
"מצורף בזאת", "אשמח לשמוע ממך בהקדם", "שלום רב", "בברכה", "לומד מהר", "שווה ניסיון",
"אתגר מרתק", "חדשני", "להוות חלק".

Also never: dashes as separators (" - ", "—"), semicolons, bullet lists, placeholders
("[name]"), the same sentence you used for another company. If a phrase appears in the user's own
samples, it's the user's voice and it's fine.

## 7. Save, then check

Write into `output/<slug>/meta.json`, per contact: `connect_note`, `connect_note_he`,
`first_message`, `first_message_he` (follow-ups go in `followups: [{"n": 1, "text": ...,
"text_he": ..., "drafted_at": "YYYY-MM-DD"}]`). People the user already knows get no connect note.

Then run:

```bash
python3 scripts/check_messages.py <slug>
```

Fix every ✗ error and re-run until it passes (exit code 0). Fix the ⚠ warnings when the fix is
easy, especially "also in N other companies' messages": that sentence reads like a template.
