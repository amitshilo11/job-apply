---
description: Catch up the tracking from your LinkedIn data export — who accepted, who replied, what you sent
argument-hint: <path to the export zip or folder>
---

The user downloaded their LinkedIn data (Connections, Messages, Invitations). Export: `$ARGUMENTS`

1. If no path was given, look for the newest `*LinkedInDataExport*.zip` in `~/Downloads` and ask
   before using it. No export yet: give the steps (LinkedIn → Settings & Privacy → Data privacy →
   Get a copy of your data → Connections, Messages, Invitations → Request archive) and stop.
2. `python3 scripts/linkedin_import.py <path> --dry-run` and show what it would record.
3. If it looks right (or the user already said to go ahead), run it without `--dry-run`.
4. Show what changed in a few lines: replies found, people who accepted, how many sent messages
   became writing samples. Then `python3 scripts/state.py stats` if 10+ people now have steps.
   Mention anything it printed about missing files or people it couldn't match.
