# Prompt: Find the right people

Goal: one to three people per role who are **really** the right ones (still at the company,
in Israel, connected to this role), each with a reason and an honest confidence level.
Wrong people are worse than no people: a message to someone who left, or to an HR partner in
another country, wastes one of the user's few LinkedIn notes.

Never use automation on LinkedIn: no logging in, no scraping, no sending, no clicking for the
user. Search engines (WebSearch) and public pages (WebFetch) only. The user sends everything.

---

## 0. People the user named (before anything else)

The user may name people in the request ("the recruiter is Dana Cohen", a LinkedIn link, an
email) or in the dashboard form (HR / recruiter, team lead, someone they know there). They're
true: don't second-guess them.

- Each one fills their slot: HR / recruiter → `hr`, team lead → `lead`, someone they know →
  `referral` (`"connected": true`, the referral ask, no connect note), anyone else → `other`.
  `"source": "you"`, `"confidence": "high"`, and `why` says the user named them.
- Keep their LinkedIn URL and email exactly as given. Fill in what's missing (job title,
  location, `name_he`) from search, but don't swap the person for someone else.
- Only a name: find the profile with search (step 4) and check it's them (step 5). Not found:
  keep the name with `"profile": null` and say what you tried in `why`. Never build a URL.
- An email for a person goes in their contact as `email`. For the HR / recruiter it's also the
  email channel's address (Flow 3 Step 6).
- A slot they filled is done: don't search for someone else for it. Still run steps 1 to 5
  for the other slots.

## 1. People the user already knows (always, right after §0)

```bash
python3 scripts/referrals.py "<Company>" --json
```

- Matches go into `meta.json` → `referrals` (the whole list, as returned).
- The best one (closest to the role: same team > engineering > anyone) also becomes a contact
  with `"kind": "referral"`, `"connected": true`, `"source": "your connection"`,
  `"confidence": "high"`. It gets no connect note, only a first message: the referral ask
  (see `draft_linkedin.md`).
- No file (`"found": false`): say once in the summary that exporting `Connections.csv` lets
  the agent find referrals (how-to is in the script output). Don't nag on every run.
- A "likely" match (company name differs slightly) needs a word of caution in `why`.

## 2. The hiring team from the job post

The best contact is whoever posted the job. LinkedIn job pages often show **"Meet the hiring
team"** with the poster's name and title (usually a recruiter, sometimes the hiring manager).

- If the user pasted the job page or a screenshot: read the hiring team from it. A recruiter
  goes in as `hr`, a manager or lead as `lead`. `"source": "job post"`, `"confidence": "high"`.
- If you only have a LinkedIn URL: WebFetch `https://www.linkedin.com/jobs/view/<id>/`. The public
  view usually has no hiring team. Find the profile with search (step 4) using the name if
  you have one.
- No hiring team visible: continue, and add a tip to the summary once: "Paste the job page
  (Cmd+A, Cmd+C) or a screenshot next time and I'll get the hiring team from it."

## 2b. The company's LinkedIn page

Search `site:linkedin.com/company "<Company>"` and take the company page whose name (and
website or location, when shown) matches. Write its exact URL to `meta.json` →
`linkedin_company_url` (e.g. `https://www.linkedin.com/company/acme/`). Never build it from the
company name: a wrong page is worse than none, so `null` when unsure. The report turns it into
links to the company's **People tab** filtered by recruiter / team lead, which only lists
people who work there now: the quickest way for the user to check or replace a contact.

## 3. Who to target, by company size

| Size | HR / recruiter slot | Lead slot |
|---|---|---|
| Under ~50 people | Often no HR. Use a people/ops person only if one clearly exists, else "not found" | Founder, CTO or VP R&D |
| 50 to 500 | Technical recruiter / talent acquisition for R&D, in Israel | The mobile/Android team lead, or the lead of the team the JD names |
| 500+ | Only the job poster or a recruiter for this exact role or group in Israel | The manager of the team the JD names. If the JD doesn't name one, a mobile/Android group lead in the Israeli site |

Big companies have hundreds of HR people. A random one is a wrong one.

## 4. Search (when steps 1 to 3 didn't fill a slot)

Use `target_function` and `linkedin_search_terms` from `config/settings.json`. Run several
queries, Hebrew titles included (many Israeli profiles are in Hebrew):

```
site:linkedin.com/in "<Company>" ("talent acquisition" OR recruiter OR "technical recruiter") Israel
site:il.linkedin.com/in "<Company>" (recruiter OR "talent acquisition" OR "רכזת גיוס" OR "רכז גיוס" OR "גיוס")
site:linkedin.com/in "<Company>" ("<term 1>" OR "<term 2>" OR ...) (Android OR mobile) Israel
site:il.linkedin.com/in "<Company>" ("team lead" OR "tech lead" OR "ראש צוות") (android OR mobile OR אנדרואיד)
"<Company>" "<team name from the JD>" ("team lead" OR manager) site:linkedin.com/in
```

## 5. Check every candidate before using them

From the search result's title and snippet (don't guess beyond them):

1. **Still there.** The company is in the current headline or title ("... at <Company>",
   "<Company> | ..."). Reject "ex-", "former", "previously", or when the company only shows up
   in past experience.
2. **In Israel.** An `il.linkedin.com` URL, or an Israeli city in the snippet. Reject other
   countries unless the role itself is remote-global.
3. **Connected to the role.** Recruiter: R&D or technical, not sales or HR-business-partner
   for another division. Lead: mobile/Android, or the JD's team.

Confidence: **high** = the job poster, or all three confirmed. **medium** = two of three.
**low** = only one. Use a low one only if there's nothing better, and say why in `why`.

Keep the best as the contact; up to two others go in `alternates` (same fields), best first.
When the user marks a contact as the **wrong person** in the report (left, another team,
another country), the first alternate takes the slot and its first name goes into the
messages, so put the one you'd pick next first. A contact's `wrong_people` lists who was
already ruled out: never suggest them again for this application.

## 6. What to write

For each contact in `meta.json` → `contacts`:

```json
{
  "key": "hr",
  "kind": "hr",
  "title": "HR / Recruiter",
  "name": "Noa Example",
  "name_he": "נועה",
  "job_title": "Co-Founder & CEO",
  "location": "Haifa, Israel",
  "profile": "<the exact URL from the search result>",
  "source": "job post",
  "confidence": "high",
  "why": "Posted the job; small startup with no recruiter on LinkedIn.",
  "connected": false,
  "alternates": [ { "name": "...", "job_title": "...", "location": "...", "profile": "...", "why": "...", "confidence": "medium" } ]
}
```

- `kind`: `hr`, `lead`, `referral`, or `other`. `key` must be unique: `hr`, `lead`, `referral-1`...
- `name_he`: the first name in Hebrew letters, only when you're sure of the spelling (Noa → נועה,
  Dan → דן). Otherwise `null`; the Hebrew message then greets with the English spelling.
- `profile`: the exact URL from the search result. **Never build or guess a profile URL.**
- Nobody good found for a slot: still add the slot with `"profile": null, "name": null` and
  `"why": "not found: <what you tried>"`. The report shows the company's People tab
  (from `linkedin_company_url`) and LinkedIn search links so the user can find someone in seconds.
- A slot with nobody found gets **no messages**: leave its message fields empty. The report
  gives the user two buttons there: **+ Add** (they found the person; a background run drafts
  messages for them) and **Write a general message** (a background run drafts one with
  `{name}` where the first name goes, `Hi {name},` / `היי {name},`, which they fill in from the
  report or with `python3 scripts/state.py person --slug <slug> --key hr --name "..."`).
