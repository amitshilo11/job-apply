---
description: Record a message you sent (and learn from your edits) — e.g. "/sent acme hr connect he" then paste the text
argument-hint: <company or slug> <who: hr|lead|email|name> <what: connect|message|followup N|email> [he|en] [the text you sent]
---

The user sent something and wants it recorded. `$ARGUMENTS` (and any pasted text) says what.

1. Find the application: `python3 scripts/state.py show --slug <slug>` (match the company name
   to a slug with `slugify()`; if unsure, list with `python3 scripts/state.py list-all`).
2. Work out the thread key (`hr`, `lead`, `email`, `referral-N`, or the person's name → key from
   `show`), the step (`connect_sent`, `accepted`, `message_sent`, `followup_N`, `sent` for the
   email, `replied`) and the language.
3. Record the step:
   `python3 scripts/state.py event --slug <slug> --key <key> --event <step> --lang <he|en>`
   (connect request without a note: add `--no-note`).
4. If the user pasted the text they actually sent, save it so future drafts learn from it:
   `python3 scripts/samples.py add --slug <slug> --key <key> --field <field> --text "<text>"`
   where field is `connect_note[_he]`, `first_message[_he]`, `followups.N.text[_he]`, or for the
   email `email_draft.body[_he]` / `email_draft.followups.N.body[_he]`.
5. `python3 scripts/generate_report.py <slug>` and confirm in one line what's next for that
   person (from `state.py show`).

Also covers "they accepted", "they replied" (→ `replied`, and the stage moves to replied),
"got an interview" (→ `/interview-prep`), "rejected" (→ `state.py update --stage rejected`).
