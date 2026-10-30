#!/usr/bin/env python3
"""
referrals.py — who do you already know at a company?

Reads your LinkedIn connections export (config/Connections.csv) and lists the 1st-degree
connections whose current company matches. Ask them first: a referred candidate gets hired
far more often than a cold applicant.

Get the file (once a month is plenty): LinkedIn → Settings & Privacy → Data privacy →
Get a copy of your data → pick "Connections" → Request archive. LinkedIn emails you a link;
unzip it and put Connections.csv in config/. The export can't be made from the phone app.

Usage:
  python3 scripts/referrals.py "Acme"
  python3 scripts/referrals.py "Acme Robotics (Beta by Gamma)" --json
  python3 scripts/referrals.py --all         # every active application
"""

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from state import CLOSED_STAGES, ROOT, load_settings, load_state  # noqa: E402

LEGAL = {"ltd", "inc", "llc", "corp", "corporation", "co", "company", "israel", "il", "the", "plc", "gmbh", "sa"}
GENERIC = LEGAL | {"group", "technologies", "technology", "tech", "labs", "lab", "software", "systems",
                   "solutions", "networks", "ai", "io", "global", "international", "health", "healthcare",
                   "robotics", "security", "medical", "medtech"}
HOW_TO = ("No connections file yet. Export it from LinkedIn: Settings & Privacy → Data privacy → "
          "Get a copy of your data → Connections (plus Messages and Invitations) → Request archive, then "
          "run python3 scripts/linkedin_import.py <the zip>. Or save Connections.csv in config/.")


def csv_path():
    configured = load_settings().get("connections_csv") or "config/Connections.csv"
    path = Path(configured)
    return path if path.is_absolute() else ROOT / path


def load_connections(path):
    """Rows from LinkedIn's export, which starts with a few 'Notes:' lines before the header."""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("First Name")), None)
    if start is None:
        return []
    return list(csv.DictReader(io.StringIO("\n".join(lines[start:]))))


def _words(name, drop):
    name = name.lower().replace("&", " and ")
    return [w for w in re.findall(r"[a-z0-9֐-׿]+", name) if w not in drop]


def name_variants(company):
    """'Acme Robotics (Beta by Gamma)' → ['Acme Robotics (Beta by Gamma)', 'Acme Robotics', 'Beta', 'Gamma']."""
    parts = [company] + [p.strip() for p in re.split(r"[()/|,]| by | - ", company) if p.strip()]
    seen, out = set(), []
    for p in parts:
        if p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
    return out


def match_quality(target, other):
    """'exact', 'likely', or None for two company names."""
    t_strict, o_strict = " ".join(_words(target, LEGAL)), " ".join(_words(other, LEGAL))
    if not t_strict or not o_strict:
        return None
    if t_strict == o_strict:
        return "exact"
    t_loose, o_loose = " ".join(_words(target, GENERIC)), " ".join(_words(other, GENERIC))
    if t_loose and t_loose == o_loose and len(t_loose) >= 4:
        return "likely"
    short, long_ = sorted((t_strict, o_strict), key=len)
    if len(short) >= 5 and re.search(r"(?<![a-z0-9])" + re.escape(short) + r"(?![a-z0-9])", long_):
        return "likely"
    return None


def find(company, rows):
    matches = []
    for row in rows:
        other = (row.get("Company") or "").strip()
        if not other:
            continue
        quality = None
        for variant in name_variants(company):
            q = match_quality(variant, other)
            if q == "exact":
                quality = "exact"
                break
            quality = quality or q
        if quality:
            matches.append({
                "name": f"{row.get('First Name', '').strip()} {row.get('Last Name', '').strip()}".strip(),
                "position": (row.get("Position") or "").strip(),
                "company": other,
                "url": (row.get("URL") or "").strip() or None,
                "connected_on": (row.get("Connected On") or "").strip() or None,
                "match": quality,
            })
    matches.sort(key=lambda m: (m["match"] != "exact", m["name"]))
    return matches


def print_matches(company, matches):
    if not matches:
        print(f"No connections at {company}.")
        return
    print(f"You know {len(matches)} {'person' if len(matches) == 1 else 'people'} at {company}:")
    for m in matches:
        guess = "" if m["match"] == "exact" else f"  (company listed as \"{m['company']}\", check it's the same)"
        since = f" · connected {m['connected_on']}" if m.get("connected_on") else ""
        print(f"  • {m['name']} — {m['position'] or 'no title'}{since}{guess}")
        if m.get("url"):
            print(f"    {m['url']}")


def main():
    parser = argparse.ArgumentParser(description="Find people you already know at a company")
    parser.add_argument("company", nargs="?")
    parser.add_argument("--all", action="store_true", help="Check every active application")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not args.company and not args.all:
        parser.print_help()
        sys.exit(2)

    path = csv_path()
    if not path.exists():
        if args.json:
            print(json.dumps({"file": str(path), "found": False, "matches": [], "how_to": HOW_TO}, ensure_ascii=False))
        else:
            print(HOW_TO)
        return
    rows = load_connections(path)

    if args.all:
        result = {}
        for e in load_state():
            if e.get("stage") in CLOSED_STAGES:
                continue
            result[e["slug"]] = {"company": e["company"], "matches": find(e["company"], rows)}
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            for item in result.values():
                if item["matches"]:
                    print_matches(item["company"], item["matches"])
                    print()
            if not any(item["matches"] for item in result.values()):
                print("No connections at any active application.")
        return

    matches = find(args.company, rows)
    if args.json:
        print(json.dumps({"file": str(path), "found": True, "matches": matches}, indent=2, ensure_ascii=False))
    else:
        print_matches(args.company, matches)


if __name__ == "__main__":
    main()
