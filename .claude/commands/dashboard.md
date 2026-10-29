---
description: Start the dashboard (buttons that save) at http://localhost:8765
argument-hint: [--lan to also open it on your phone]
---

Start the dashboard server in the background (it keeps running after this turn):

`python3 scripts/serve.py $ARGUMENTS`

Then tell the user the URL it printed (http://localhost:8765 by default). With `--lan`, also
give the phone link it printed and the warning: anyone on the same Wi-Fi with that link can
see the applications, so stop the server when done.

If it says the port is busy, the dashboard is probably already running: just give the URL.

Mention once that **+ New application** on the dashboard starts a role in the background. If
the server printed that Claude Code isn't installed or logged in, pass that on: the user runs
`claude auth login` once in Terminal (don't run it for them).
