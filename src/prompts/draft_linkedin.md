# Prompt: Draft LinkedIn messages

Goal: messages the user would actually write: short, plain, and true. Not a recruiter
template, not a pitch, and not "AI trying to sound casual".

---

## 1. Where the voice comes from (and only from)

Read `config/writing_samples.md` every time, in this order:

1. **"Learned from your edits"**: what the user actually sent after changing a draft, or wrote
   from scratch. This beats everything else. Notice what was changed: that's the lesson.
2. **"Defaults you picked"**: the connect note, first message and follow-ups the user chose.
   Start every message from the matching one and keep its fixed wording; a slot that asks for
   something written for this role (e.g. a "specific line") is written fresh every time.
3. The sent samples and the user's other templates.
4. The tone notes at the bottom.

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
- **About them:** every connect note and first message says one concrete thing about this
  role: the product, the team the JD names, what the role builds, or a technology in the JD
  that the user has really used. From the job description or the role card. A detail, not
  praise. A message that would read the same for any other company is wrong.
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
- Max `connect_note_max_chars` characters (default **200**: LinkedIn's limit on free accounts),
  counted with the name and company filled in.
- **With a default:** use it, with the intro that fits the role, and write its role-specific
  slot for this role. Add nothing else (no praise, ask, CV or links). Over the limit: shorten
  it the way the samples file says, without rewriting the rest.
- **No default yet:** who the user is, in one phrase ("Android developer, 3+ years in <their
  domain>"), why this company (one real thing), a low-pressure line. No ask, no CV, no links.
  Aim for 100 to 170 characters. Free accounts only get a few notes a month, so it has to earn
  its place.

### First message (after they accept)
- **With a default:** use it for recruiters, team leads and founders alike, with its
  role-specific slot written for this role (for a team lead, lean on the work; for HR, on the
  role). Not the same sentence as the connect note.
- **No default yet:** under 80 words, 2 to 4 short sentences. The role (name it), the one most
  relevant thing the user has done for it (a CV fact, a number if there is one), and an easy
  ask: a short call, whether the role is still open, or who the right person is. By recipient:
  - **HR / recruiter:** practical. Role, fit in one line, "happy to send my CV or jump on a call".
  - **Team lead / hiring manager:** lead with the work, not the job hunt. What in the JD matches
    something the user has built.
  - **Founder / CTO (small startup):** short and direct: the product, and why the user fits.
- **Referral (someone the user knows), default or not:** warm and easy to say no to. Mention
  how they know each other if `why` or the connection date suggests it, the role link, and ask
  if they'd be OK referring the user or sharing what the team is like. No pressure, no guilt.

### Follow-ups (drafted later by the follow-up flow)
- #1 comes about 4 work days after the first message, #2 is the last one.
- **With defaults:** use #1 and #2 as the user wrote them, one line each.
- **No defaults yet:** #1 under 40 words, with one new, useful thing (a short line on a
  relevant project, a GitHub link) or a simple question ("is the role still open?"), not
  "just bumping this". #2 under 30 words, closing the loop politely and leaving the door open.
- Same language(s) as the earlier messages in that thread.

## 5. Greeting and sign-off

- English: "Hey <first name>," (or "Hi"), like the samples. Hebrew: "היי <name_he>," when
  `name_he` is set, otherwise "היי <English first name>,".
- No greeting where the user's default has none (e.g. a first message that opens with "Thanks
  for connecting").
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
("[name]"; the one exception is `{name}` as the first name in a general message the user asked
for, see `src/prompts/find_contacts.md` §6), the same sentence you used for another company (the user's defaults are meant to
repeat). If a phrase appears in the user's own
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
Never reword the user's defaults to clear a warning.
