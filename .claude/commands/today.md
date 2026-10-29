---
description: What to do today — messages to send, follow-ups due, people to check — and draft what's missing
---

1. Run `python3 scripts/state.py today` and show its output as is (it also closes threads that
   got no reply after the last follow-up; mention any it closed).
2. If any follow-up in the list isn't drafted yet ("not drafted" in the dashboard, or no
   `followups` entry for that number in meta.json), offer to draft them now: that's the
   "Follow-up sub-flow" in `src/flow1.md` (same as `/followups`).
3. End with how to act on it: `python3 scripts/serve.py` opens the dashboard, where every item
   has Copy and Sent buttons. Or the user can just say what they did ("sent the connect note
   to Noa in Hebrew") and Claude records it with `scripts/state.py event`.
