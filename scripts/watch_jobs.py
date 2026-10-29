#!/usr/bin/env python3
"""
watch_jobs.py — new jobs at companies you like, straight from their job boards.

Many companies publish openings through a public job-board feed (Greenhouse, Lever, Ashby).
List the companies you'd like to work for in config/watchlist.json once; this checks them all
and shows only jobs that are new since the last check and pass your filters (`job_filters` in
config/settings.json: title words to include/exclude, locations).

Comeet (common in Israel) has no open feed, so Comeet career pages are read best-effort from
the page itself. If a page can't be read, that company is reported and skipped.

Usage:
  python3 scripts/watch_jobs.py                    # check everything, print new matches
  python3 scripts/watch_jobs.py --json             # same, as JSON (Flow 4 passes it to rank_jobs.py)
  python3 scripts/watch_jobs.py --all              # include jobs already shown before
  python3 scripts/watch_jobs.py add "Acme" https://job-boards.greenhouse.io/acme
  python3 scripts/watch_jobs.py add "Example Co" --ats ashby --token exampleco
  python3 scripts/watch_jobs.py list
  python3 scripts/watch_jobs.py remove "Acme"
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from state import ROOT, _read_json, _write_json, load_settings, today_str  # noqa: E402

WATCHLIST_FILE = ROOT / "config" / "watchlist.json"
SEEN_FILE = ROOT / "state" / "seen_jobs.json"

DEFAULT_FILTERS = {
    "title_include": ["android", "mobile", "kotlin", "react native", "flutter", "ios", "full stack", "full-stack",
                      "fullstack", "backend", "back-end", "software engineer", "software developer"],
    "title_exclude": ["staff", "principal", "director", "head of", "vp ", "manager", "intern", "student",
                      "qa ", "sales", "marketing"],
    "locations": ["israel", "tel aviv", "haifa", "yokneam", "caesarea", "herzliya", "netanya", "hadera",
                  "ra'anana", "raanana", "petah tikva", "il"],
    # A remote job only counts if it's open to people in Israel, not "Remote (US)"
    "remote_regions": ["israel", "emea", "anywhere", "worldwide", "global"],
}

URL_PATTERNS = [
    ("greenhouse", r"greenhouse\.io/(?:embed/job_board\?for=)?([\w-]+)"),
    ("lever", r"jobs\.(?:eu\.)?lever\.co/([\w-]+)"),
    ("ashby", r"jobs\.ashbyhq\.com/([\w.-]+)"),
    ("comeet", r"comeet\.com?/jobs/([\w-]+/[\w.]+)"),
]


def fetch(url, as_json=True):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (job-apply watchlist)"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    return json.loads(body) if as_json else body


def jobs_greenhouse(token):
    data = fetch(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs")
    return [{"id": str(j["id"]), "title": j.get("title"), "location": (j.get("location") or {}).get("name"),
             "url": j.get("absolute_url"), "posted": j.get("first_published") or j.get("updated_at")}
            for j in data.get("jobs", [])]


def jobs_lever(token):
    data = fetch(f"https://api.lever.co/v0/postings/{token}?mode=json")
    out = []
    for j in data:
        cat = j.get("categories") or {}
        locs = cat.get("allLocations") or [cat.get("location")]
        out.append({"id": j.get("id"), "title": j.get("text"), "location": ", ".join(x for x in locs if x),
                    "url": j.get("hostedUrl"), "posted": j.get("createdAt"), "workplace": j.get("workplaceType"),
                    "snippet": (j.get("descriptionPlain") or "")[:600]})
    return out


def jobs_ashby(token):
    data = fetch(f"https://api.ashbyhq.com/posting-api/job-board/{token}")
    out = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        locs = [j.get("location")] + [x.get("location") for x in j.get("secondaryLocations") or [] if isinstance(x, dict)]
        out.append({"id": j.get("id"), "title": j.get("title"), "location": ", ".join(x for x in locs if x),
                    "url": j.get("jobUrl"), "posted": j.get("publishedAt"),
                    "workplace": j.get("workplaceType") or ("Remote" if j.get("isRemote") else None),
                    "snippet": (j.get("descriptionPlain") or "")[:600]})
    return out


def jobs_comeet(token):
    """Best effort: Comeet career pages embed their positions as JSON in the page."""
    html = fetch(f"https://www.comeet.com/jobs/{token}", as_json=False)
    m = re.search(r"COMPANY_POSITIONS_DATA\s*=\s*(\[.*?\])\s*;", html, re.DOTALL)
    if not m:
        raise ValueError("couldn't find the positions on the Comeet page (the page layout may have changed)")
    out = []
    for j in json.loads(m.group(1)):
        loc = j.get("location") or {}
        location = loc.get("name") if isinstance(loc, dict) else str(loc or "")
        out.append({"id": str(j.get("uid") or j.get("id")), "title": j.get("name"), "location": location,
                    "url": j.get("url_comeet_hosted_page") or j.get("url_active_page") or j.get("url"),
                    "posted": j.get("time_updated"), "workplace": j.get("workplace_type")})
    return out


FETCHERS = {"greenhouse": jobs_greenhouse, "lever": jobs_lever, "ashby": jobs_ashby, "comeet": jobs_comeet}


def detect(url):
    for ats, pattern in URL_PATTERNS:
        m = re.search(pattern, url)
        if m:
            return ats, m.group(1)
    return None, None


def filters():
    merged = dict(DEFAULT_FILTERS)
    merged.update(load_settings().get("job_filters") or {})
    return merged


def passes(job, f):
    title = f" {(job.get('title') or '').lower()} "
    if not any(w.lower() in title for w in f["title_include"]):
        return False, "title"
    if any(w.lower() in title for w in f["title_exclude"]):
        return False, "title excluded"
    where = f" {(job.get('location') or '').lower()} {(job.get('workplace') or '').lower()} "

    def mentions(words):
        return any(re.search(r"(?<![a-z])" + re.escape(w.lower()) + r"(?![a-z])", where) for w in words)

    if not f.get("locations") or mentions(f["locations"]):
        return True, None
    if "remote" in where and mentions(f.get("remote_regions") or []):
        return True, None
    return False, "location"


def check(show_all=False):
    watch = _read_json(WATCHLIST_FILE, [])
    seen = _read_json(SEEN_FILE, {})
    f = filters()
    new, problems, counts = [], [], {"jobs": 0, "filtered": 0, "seen": 0}
    for company in watch:
        ats, token = company.get("ats"), company.get("token")
        fetcher = FETCHERS.get(ats)
        if not fetcher:
            problems.append(f"{company.get('company')}: unknown job board '{ats}'")
            continue
        try:
            jobs = fetcher(token)
        except (urllib.error.URLError, ValueError, KeyError, json.JSONDecodeError) as err:
            problems.append(f"{company.get('company')} ({ats}/{token}): {err}")
            continue
        for job in jobs:
            counts["jobs"] += 1
            ok, _ = passes(job, f)
            if not ok:
                counts["filtered"] += 1
                continue
            job_id = f"{ats}:{token}:{job['id']}"
            if job_id in seen and not show_all:
                counts["seen"] += 1
                continue
            new.append(dict(job, id=job_id, company=company.get("company"), source=f"{ats} watchlist"))
            seen.setdefault(job_id, {"first_seen": today_str(), "company": company.get("company"),
                                     "title": job.get("title"), "url": job.get("url")})
    _write_json(SEEN_FILE, seen)
    return new, problems, counts, len(watch)


def cmd_check(args):
    new, problems, counts, n_companies = check(args.all)
    if args.json:
        print(json.dumps(new, indent=2, ensure_ascii=False))
        for p in problems:
            print(f"WARNING: {p}", file=sys.stderr)
        return
    if not n_companies:
        print("Your watchlist is empty. Add companies with:\n"
              "  python3 scripts/watch_jobs.py add \"<Company>\" <their careers or job-board URL>")
        return
    print(f"Checked {n_companies} companies: {counts['jobs']} open jobs, {counts['filtered']} filtered out, "
          f"{counts['seen']} already shown before, {len(new)} new.\n")
    for job in new:
        where = " · ".join(x for x in (job.get("location"), job.get("workplace")) if x)
        print(f"  • {job['company']} — {job['title']} ({where})\n    {job.get('url')}")
    for p in problems:
        print(f"\n  ⚠ couldn't check {p}")


def cmd_add(args):
    ats, token = args.ats, args.token
    if args.url and not (ats and token):
        ats, token = detect(args.url)
    if not (ats and token):
        print("Couldn't tell which job board that is. Supported: Greenhouse, Lever, Ashby, Comeet.\n"
              "Open the company's careers page, click a job, and use the URL of the job board page, "
              "or pass --ats and --token.", file=sys.stderr)
        sys.exit(1)
    try:
        count = len(FETCHERS[ats](token))
    except Exception as err:  # still save it: a board can be empty or briefly down
        count = None
        print(f"Warning: couldn't read it right now ({err}). Saved anyway.")
    watch = [w for w in _read_json(WATCHLIST_FILE, []) if w.get("company", "").lower() != args.company.lower()]
    watch.append({"company": args.company, "ats": ats, "token": token, "added": today_str()})
    _write_json(WATCHLIST_FILE, watch)
    found = f", {count} open jobs right now" if count is not None else ""
    print(f"Watching {args.company} ({ats}/{token}{found}).")


def cmd_list(args):
    watch = _read_json(WATCHLIST_FILE, [])
    if not watch:
        print("Watchlist is empty.")
    for w in watch:
        print(f"  {w['company']:30s} {w['ats']:10s} {w['token']}")


def cmd_remove(args):
    watch = _read_json(WATCHLIST_FILE, [])
    kept = [w for w in watch if w.get("company", "").lower() != args.company.lower()]
    _write_json(WATCHLIST_FILE, kept)
    print("Removed." if len(kept) < len(watch) else f"{args.company} wasn't on the watchlist.")


def main():
    parser = argparse.ArgumentParser(description="New jobs at the companies you watch")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--all", action="store_true", help="Include jobs shown before")
    sub = parser.add_subparsers(dest="command")
    p_add = sub.add_parser("add", help="Watch a company")
    p_add.add_argument("company")
    p_add.add_argument("url", nargs="?")
    p_add.add_argument("--ats", choices=sorted(FETCHERS))
    p_add.add_argument("--token")
    sub.add_parser("list", help="Show the watchlist")
    p_rm = sub.add_parser("remove", help="Stop watching a company")
    p_rm.add_argument("company")
    args = parser.parse_args()
    {"add": cmd_add, "list": cmd_list, "remove": cmd_remove}.get(args.command, cmd_check)(args)


if __name__ == "__main__":
    main()
