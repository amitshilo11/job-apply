# Flow 0 — Startup Discovery

When the user says `find startups` (or `find N startups`, `find N <domain> startups`, e.g. `find 10 cybersecurity startups`, or `find N startups in <city>` / `find startups in <city>`), follow these steps.

---

## Setup

Load at start:
- `config/profile.md` — location preferences, target functions, tech-stack domains
- `state/applications.json`, `state/skipped.json`, `state/queue.json` (may not exist yet)

Default count: **15** companies unless the user specifies N.
Domain focus: **cybersecurity, medical/health-tech, and AI** — these are the three verticals of interest. If the user specifies a domain (e.g. `find 10 fintech startups`), honour it; otherwise rotate across all three.

---

## Step 1 — Generic web search

Run 6–9 WebSearch queries, two or three per vertical. Use different angles per vertical to maximise variety.

**Cybersecurity:**
- `Israeli cybersecurity startup hiring backend engineer 2026`
- `Israel cyber startup series A OR B 2026 careers software engineer`
- `"Israeli cybersecurity" startup careers site:linkedin.com/company`

**Medical / health-tech:**
- `Israeli medtech OR healthtech startup hiring software engineer 2026`
- `Israel medical device software startup careers backend OR full-stack`
- `Israeli digital health startup series A 2026 hiring engineers`

**AI / ML:**
- `Israeli AI startup hiring backend OR full-stack engineer 2026`
- `Israel LLM OR "machine learning" startup careers software engineer`
- `Israeli generative AI startup series A OR B 2026 hiring`

For each result:
- Extract company name + official website or LinkedIn company page URL
- Skip pure news aggregators (TechCrunch, Globes, Calcalist articles) — take the company itself, not the article
- Skip companies you've already seen in earlier queries this run (in-run dedupe)

---

## Step 2 — Startup directories

Try to WebFetch one or two of these. These pages often gate behind login or JavaScript — if the page fails or returns no useful company list, note it and move on; do not retry.

- `https://finder.startupnationcentral.org/` — Israel-focused, filter by tech sector
- `https://www.calcalist.co.il/startup/` — Calcalist startup tracker (Hebrew; extract company names from headlines)
- WebSearch fallback: `site:crunchbase.com/organization Israeli startup backend OR security` and extract company slugs from the result URLs

Extract `<company name, website>` pairs.

---

## Step 3 — VC portfolio pages

WebFetch each page below. Extract every portfolio company name + website (or LinkedIn company page if website link not shown). These are pre-vetted product companies — high signal.

Try all of these (annotated by their vertical strength — prioritise accordingly):

**Cybersecurity-focused:**
- `https://www.team8.vc/companies/` — cyber, data, fintech
- `https://www.glilot.com/portfolio/` — cyber, enterprise software

**Broad Israeli (all three verticals):**
- `https://aleph.vc/portfolio` — AI, enterprise, consumer
- `https://www.pitango.com/portfolio/` — AI, medtech, deep tech
- `https://www.tlv.partners/portfolio` — AI, SaaS, enterprise

**Health-tech / medtech:**
- `https://www.carestarfund.com/portfolio` — digital health, medtech
- WebSearch fallback: `site:linkedin.com/company "Israeli medtech startup"` if direct page fetch fails

If a page returns no useful content (login wall, JS-only), skip it silently.

---

## Step 4 — Normalize & dedupe

For each candidate collected from Steps 1–3:

1. Generate slug: lowercase company name, spaces → `-`, strip non-alphanumeric except `-`
   - Example: "Wiz Security" → `wiz-security`
2. Discard if the slug already exists in any of these:
   - `applications.json` — any status (drafted, sent, applied, archived, email-skipped, etc.)
   - `skipped.json`
   - `queue.json`
3. Discard if there is no website AND no LinkedIn URL — Flow 1 cannot proceed without at least one
4. Stop once you have reached the requested count (default 15)

---

## Step 5 — Push to queue

For each surviving candidate, run:

```bash
python3 scripts/state.py queue add \
  --company "<company name>" \
  --slug "<slug>" \
  --website "<website url or empty string>" \
  --linkedin "<linkedin company page url or empty string>" \
  --source "<short source label, e.g. 'Aleph portfolio' or 'web search'>" \
  --source-url "<url of the page where you found it>"
```

The command prints whether each entry was queued or skipped (duplicate). Collect the counts.

---

## Step 6 — Report back

After all additions, run:

```bash
python3 scripts/state.py queue stats
```

Then print a summary table:

```
Flow 0 complete — discovery run 2026-05-19

Added to queue (N):
  Company Name           Website / LinkedIn                   Source
  ────────────────────────────────────────────────────────────────────
  <company>              <url>                                <source>
  ...

Skipped (already known): X
Queue total now: N queued

Next step:
  → Review the queue: process next from queue
  → Drain everything:  process the queue
```

---

## Notes

- Flow 0 is intentionally shallow — it does NOT visit careers pages or check for open roles. That's Flow 1's job.
- Run Flow 0 as often as you like; the dedupe logic prevents duplicates.
- Default verticals: **cybersecurity, medical/health-tech, AI**. To narrow to one, say e.g. `find 10 cybersecurity startups`.

---

## City-based variant

**Trigger phrases:**
- `find N startups in <city>`
- `find startups in <city>`
- `find companies in <city>`
- `find companies near me` → default city list: Netanya, Caesarea, Yokneam

When triggered, replace Steps 1–3 with Steps A–C below. Steps 4–6 (normalize/dedupe, push to queue, report) run identically.

Default count: **15** unless the user specifies N.

---

**Step A — Web searches for the city**

Run 5–7 WebSearch queries targeting the specified city:

```
"<city>" startup software engineer hiring 2025 OR 2026
"<city>" tech company backend engineer careers
"<city>" Israel "software startup" OR "tech company" careers
site:linkedin.com/jobs "software engineer" "<city>" Israel
site:linkedin.com/company "<city>" startup software
"<city>" Israel startup series A OR B backend platform
```

For each result: extract company name + website or LinkedIn URL. Skip news articles — take the company itself.

---

**Step B — Directory & LinkedIn searches**

WebSearch for companies registered or headquartered in the city:

```
site:crunchbase.com "<city>" Israel software startup
site:linkedin.com/company "<city>" Israel "software" employees
```

If the city is Yokneam, also try:
```
WebFetch: https://www.startupvillageyokneam.org/jobs
```

---

**Step C — Filter**

Apply the same profile deal-breakers as the vertical flow:
- Skip outsourcing / body shops, pure hardware, defense-embedded only, on-site only
- Deprioritize large multinationals (keep at lower priority)
- Prioritize product companies, 20–500 employees, software/backend/platform/security/AI/medtech

**Priority guidance:**
- High: startup product company, active engineering hiring, 20–300 employees
- Medium: mid-size product company or large tech with active SWE roles
- Low: large multinational or no confirmed open roles (cold outreach only)

After filtering, continue with **Step 4** (normalize & dedupe) and **Step 5** (push to queue) as defined above, then print the **Step 6** report with city noted in the header line.
