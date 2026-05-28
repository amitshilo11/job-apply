# Flow 2 — Manual Queue Add

When the user says `add to queue`, `queue company`, or `add company` (followed by one or more company names), follow these steps.

---

## Trigger phrases

- `add <Company Name> to queue`
- `queue company <Company Name>`
- `add to queue: <Company Name>`
- `add to queue: <Company Name>, website: <url>, linkedin: <url>`
- Multiple at once: `add these to queue: Wiz, Snyk, Orca Security`

---

## Input parsing

Accept the following fields per company. Only `company` is required — the rest are optional:

| Field | Flag / keyword | Default |
|-------|---------------|---------|
| Company name | positional / `company:` | **required** |
| Website URL | `website:` | empty string |
| LinkedIn company URL | `linkedin:` | empty string |
| Source label | `source:` | `"manual"` |
| Source URL | `source-url:` | empty string |

If the user provides a bare URL alongside the company name, try to classify it:
- Contains `linkedin.com/company` → use as LinkedIn URL
- Otherwise → use as website URL

---

## For each company

### Step 1 — Generate slug

Lowercase company name, spaces → `-`, strip non-alphanumeric except `-`.
Examples: `"Wiz Security"` → `wiz-security`, `"JFrog"` → `jfrog`

### Step 2 — Duplicate check

Run:
```bash
python3 scripts/state.py queue stats
```

Then check the slug against all known lists by running:
```bash
python3 scripts/state.py queue add \
  --company "<company name>" \
  --slug "<slug>" \
  --website "<website url or empty string>" \
  --linkedin "<linkedin url or empty string>" \
  --source "manual" \
  --source-url "<source url or empty string>"
```

The command prints `Queued: ...` on success or `SKIP: ...` if the slug is already known. Collect both outcomes.

---

## After all additions

Run:
```bash
python3 scripts/state.py queue stats
```

Then print a summary:

```
Added to queue (N):
  Company Name           Website / LinkedIn
  ────────────────────────────────────────────────────────────────
  <company>              <url>
  ...

Already known (skipped): X
Queue total now: N queued

Next step:
  → Process next:        process next from queue
  → Process one:         process company <Company Name>
  → See full queue:      python3 scripts/state.py queue list
```

---

## Notes

- No web research is done in this flow — it's a pure data-entry step.
- If the user didn't provide a website or LinkedIn URL, that's fine — the entry will be added without them. Flow 1 will do the discovery from the company name alone (Step 1 of Flow 1).
- To add many companies at once, the user can also edit `state/queue.json` directly — it's a plain JSON array.
