#!/usr/bin/env python3
"""
rank_jobs.py — score a list of jobs against what you want and show the best ones first.

Input is a JSON list of jobs: {"title", "company", "location", "url", "source", "snippet"?,
"workplace"?}. It comes from watch_jobs.py --json, or from job-alert emails that Claude
pulled out of Gmail (Flow 4).

Dropped: titles you excluded (staff, principal, manager...), and jobs you've already seen
(unless --keep-seen). Scored with `job_ranking` in config/settings.json: points for title
words (android, kotlin, mobile...), for locations near home or remote, for domains you like,
minus points for a "senior" title and for experience asks above `max_years`.
Companies you already applied to or skipped are kept but flagged.

Usage:
  python3 scripts/rank_jobs.py jobs.json --top 10
  python3 scripts/watch_jobs.py --json | python3 scripts/rank_jobs.py - --top 5
  python3 scripts/rank_jobs.py jobs.json --json --mark-seen
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from state import ROOT, _read_json, _write_json, load_settings, load_skipped, load_state, slugify, today_str  # noqa: E402

SEEN_FILE = ROOT / "state" / "seen_jobs.json"

DEFAULT_RANKING = {
    "title_points": {"android": 4, "kotlin": 3, "mobile": 3, "react native": 2, "flutter": 1, "ios": 1,
                     "full stack": 2, "full-stack": 2, "fullstack": 2, "backend": 1, "software engineer": 1},
    "location_points": {"haifa": 3, "yokneam": 3, "caesarea": 3, "hadera": 3, "zichron": 3, "binyamina": 3,
                        "pardes hanna": 3, "or akiva": 3, "netanya": 2, "remote": 3, "hybrid": 1,
                        "herzliya": 1, "ra'anana": 1, "tel aviv": 0},
    "domain_points": {"security": 1, "cyber": 1, " ai ": 1, "llm": 1, "developer tools": 1, "sdk": 1},
    "max_years": 5,
}
EXCLUDE_DEFAULT = ["staff", "principal", "director", "head of", "vp ", "manager", "intern", "student"]


def settings_ranking():
    s = load_settings()
    ranking = dict(DEFAULT_RANKING)
    ranking.update(s.get("job_ranking") or {})
    exclude = (s.get("job_filters") or {}).get("title_exclude") or EXCLUDE_DEFAULT
    return ranking, exclude


def score_job(job, ranking, known, skipped):
    title = f" {(job.get('title') or '').lower()} "
    text = f"{title} {(job.get('snippet') or '').lower()} "
    where = f" {(job.get('location') or '').lower()} {(job.get('workplace') or '').lower()} "
    score, reasons = 0, []

    hits = [(w, p) for w, p in ranking["title_points"].items() if w in title]
    if hits:
        score += sum(p for _, p in hits)
        reasons.append("+ " + ", ".join(w for w, _ in hits) + " in the title")
    loc = [(w, p) for w, p in ranking["location_points"].items() if w in where]
    if loc:
        best = max(loc, key=lambda x: x[1])
        score += best[1]
        if best[1] > 0:
            reasons.append(f"+ {best[0].strip()}")
    dom = [w.strip() for w, p in ranking["domain_points"].items() if w in text]
    if dom:
        score += len(dom)
        reasons.append("+ " + ", ".join(dom))
    if " senior " in title or "sr." in title:
        score -= 1
        reasons.append("− senior title (often 5+ years)")
    years = [int(y) for y in re.findall(r"(\d{1,2})\s*\+?\s*(?:years|yrs)", text)]
    if years and max(years) > ranking["max_years"]:
        score -= 3
        reasons.append(f"− asks {max(years)}+ years")
    slug = slugify(job.get("company") or "")
    if slug in known:
        reasons.append(f"! you applied at {job.get('company')} before ({known[slug]})")
    if slug in skipped:
        reasons.append(f"! skipped before: {skipped[slug]}")
    return score, reasons


def main():
    parser = argparse.ArgumentParser(description="Rank jobs against your preferences")
    parser.add_argument("file", help="JSON list of jobs, or - for stdin")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--keep-seen", action="store_true", help="Don't drop jobs shown before")
    parser.add_argument("--mark-seen", action="store_true", help="Remember the shown jobs so they don't come back")
    args = parser.parse_args()

    raw = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8")
    jobs = json.loads(raw or "[]")
    ranking, exclude = settings_ranking()
    known = {e["slug"]: e.get("job_title") or "general" for e in load_state()}
    skipped = {s["slug"]: s.get("reason") or "" for s in load_skipped()}
    seen = _read_json(SEEN_FILE, {})
    seen_urls = {v.get("url") for v in seen.values() if v.get("shown")}

    ranked, dropped, dedupe = [], {"title": 0, "seen": 0, "duplicate": 0}, set()
    for job in jobs:
        key = job.get("url") or f"{job.get('company')}|{job.get('title')}"
        if key in dedupe:
            dropped["duplicate"] += 1
            continue
        dedupe.add(key)
        title = f" {(job.get('title') or '').lower()} "
        if any(w.lower() in title for w in exclude):
            dropped["title"] += 1
            continue
        if not args.keep_seen and job.get("url") in seen_urls:
            dropped["seen"] += 1
            continue
        score, reasons = score_job(job, ranking, known, skipped)
        ranked.append(dict(job, score=score, reasons=reasons))
    ranked.sort(key=lambda j: j["score"], reverse=True)
    top = ranked[:args.top]

    if args.mark_seen:
        for job in top:
            jid = job.get("id") or job.get("url")
            entry = seen.setdefault(jid, {"first_seen": today_str(), "company": job.get("company"),
                                          "title": job.get("title"), "url": job.get("url")})
            entry["shown"] = today_str()
        _write_json(SEEN_FILE, seen)

    if args.json:
        print(json.dumps({"top": top, "total": len(jobs), "dropped": dropped}, indent=2, ensure_ascii=False))
        return
    print(f"Top {len(top)} of {len(jobs)} jobs "
          f"(dropped: {dropped['title']} by title, {dropped['seen']} seen before, {dropped['duplicate']} duplicates)\n")
    for i, job in enumerate(top, 1):
        where = " · ".join(x for x in (job.get("location"), job.get("workplace")) if x)
        print(f"{i:2d}. [{job['score']:+d}] {job.get('company')} — {job.get('title')}" + (f" ({where})" if where else ""))
        if job.get("url"):
            print(f"      {job['url']}")
        if job["reasons"]:
            print("      " + " · ".join(job["reasons"]))


if __name__ == "__main__":
    main()
