# Prompt: Find Company

Goal: locate the company's official website and careers page.

## Steps

1. WebSearch: `"<company name>" official website`
2. Pick the result that is the company's own domain — not LinkedIn, Crunchbase, Glassdoor, or news sites.
3. WebFetch the homepage to confirm it's the right company.
4. Try careers URLs in order:
   - `<domain>/careers`
   - `<domain>/jobs`
   - `<domain>/about/careers`
   - `<domain>/work-with-us`
   - `<domain>/join-us`
5. If none of those work: WebSearch `"<company name>" jobs openings site:<their-domain>`
6. Also check if they use an external job board (Greenhouse, Lever, Workable, Ashby) — the careers page usually redirects there.

## Output

```
Website: <url>
Careers page: <url or "not found">
Job board type: own site / Greenhouse / Lever / Workable / Ashby / other
```
