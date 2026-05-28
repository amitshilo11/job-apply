#!/usr/bin/env python3
"""
Manage application state in state/applications.json, state/skipped.json, and state/queue.json.

Commands:
  add        -- append a new application entry
  skip       -- log a company that was skipped (with reason + details)
  list-due   -- show entries where followup_due <= today and status != "follow-up-sent"
  list-all   -- show all entries
  mark-sent  -- update status for an entry
  queue      -- manage the discovery queue (sub-commands: add, list, next, remove, stats)

Usage examples:
  python scripts/state.py add --company "Wiz" --slug "wiz" --job-title "Backend Engineer" \\
    --email-sent-to "careers@wiz.io" --status sent --hr-url "https://linkedin.com/in/x" --lead-url "https://linkedin.com/in/y"

  python scripts/state.py skip --company "XACT Robotics" --slug "xact-robotics" \\
    --reason "Company shut down" --details "Shut down Sep 2023, laid off 65 employees." \\
    --source "https://en.globes.co.il/..."

  python scripts/state.py list-due

  python scripts/state.py mark-sent --slug "wiz" --type followup
  python scripts/state.py mark-sent --slug "wiz" --type email

  python scripts/state.py queue add --company "Wiz" --slug "wiz" \\
    --website "https://wiz.io" --linkedin "https://linkedin.com/company/wiz" \\
    --source "Aleph portfolio" --source-url "https://aleph.vc/portfolio"

  python scripts/state.py queue list
  python scripts/state.py queue next --count 3
  python scripts/state.py queue remove --slug "wiz"
  python scripts/state.py queue stats
"""

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
STATE_FILE = ROOT / "state" / "applications.json"
SKIPPED_FILE = ROOT / "state" / "skipped.json"
QUEUE_FILE = ROOT / "state" / "queue.json"


def load_state():
    if not STATE_FILE.exists():
        return []
    with open(STATE_FILE) as f:
        return json.load(f)


def save_state(entries):
    with open(STATE_FILE, "w") as f:
        json.dump(entries, f, indent=2, default=str)
        f.write("\n")


def load_settings():
    p = ROOT / "config" / "settings.json"
    if not p.exists():
        return {"followup_days": 5}
    with open(p) as f:
        return json.load(f)


def today_str():
    return date.today().isoformat()


def load_skipped():
    if not SKIPPED_FILE.exists():
        return []
    with open(SKIPPED_FILE) as f:
        return json.load(f)


def save_skipped(entries):
    with open(SKIPPED_FILE, "w") as f:
        json.dump(entries, f, indent=2, default=str)
        f.write("\n")


def cmd_skip(args):
    entries = load_skipped()
    slug = args.slug or args.company.lower().replace(" ", "-")
    existing = next((e for e in entries if e.get("slug") == slug), None)
    if existing:
        print(f"WARNING: '{slug}' already in skipped list. Updating.")
        entries = [e for e in entries if e.get("slug") != slug]
    entry = {
        "company": args.company,
        "slug": slug,
        "reason": args.reason,
        "details": args.details or "",
        "source": args.source or "",
        "skipped_at": today_str(),
    }
    entries.append(entry)
    save_skipped(entries)
    print(f"Skipped: {args.company} — {args.reason}")


def cmd_add(args):
    entries = load_state()
    settings = load_settings()
    followup_days = settings.get("followup_days", 5)

    slug = args.slug or args.company.lower().replace(" ", "-")
    followup_due = (date.today() + timedelta(days=followup_days)).isoformat()

    # Don't add duplicate slug
    existing = next((e for e in entries if e.get("slug") == slug), None)
    if existing:
        print(f"WARNING: entry for '{slug}' already exists (added {existing.get('created_at')}). Skipping.")
        print("  Use --slug with a unique name if this is a second application to the same company.")
        sys.exit(0)

    entry = {
        "company": args.company,
        "slug": slug,
        "job_title": args.job_title or None,
        "email_sent_to": args.email_sent_to or None,
        "status": args.status,
        "hr_url": args.hr_url or None,
        "lead_url": args.lead_url or None,
        "created_at": today_str(),
        "followup_due": followup_due,
        "followup_status": "pending",
    }
    entries.append(entry)
    save_state(entries)
    print(f"Added: {args.company} | status={args.status} | follow-up due {followup_due}")


def cmd_list_due(args):
    entries = load_state()
    today = today_str()
    due = [
        e for e in entries
        if e.get("followup_due", "9999-99-99") <= today
        and e.get("followup_status") != "sent"
    ]
    if not due:
        print("No follow-ups due.")
        return
    print(f"Follow-ups due ({len(due)}):\n")
    for e in due:
        print(f"  {e['company']}")
        print(f"    Job:          {e.get('job_title') or 'general'}")
        print(f"    Email sent:   {e.get('email_sent_to') or 'n/a'}")
        print(f"    Status:       {e.get('status')}")
        print(f"    Due:          {e.get('followup_due')}")
        print(f"    HR:           {e.get('hr_url') or 'not found'}")
        print(f"    Lead:         {e.get('lead_url') or 'not found'}")
        print()


def cmd_list_all(args):
    entries = load_state()
    if not entries:
        print("No applications tracked yet.")
        return
    for e in entries:
        status_line = f"{e.get('status')}"
        if e.get("followup_status") == "sent":
            status_line += " + follow-up sent"
        elif e.get("followup_due", "9999-99-99") <= today_str():
            status_line += " (follow-up OVERDUE)"
        print(f"  {e['company']:30s} {e.get('job_title') or 'general':35s} {status_line}")


def cmd_mark_sent(args):
    entries = load_state()
    slug = args.slug
    entry = next((e for e in entries if e.get("slug") == slug), None)
    if not entry:
        print(f"ERROR: no entry found for slug '{slug}'", file=sys.stderr)
        sys.exit(1)

    if args.type == "followup":
        entry["followup_status"] = "sent"
        entry["followup_sent_at"] = today_str()
        print(f"Marked follow-up sent for {entry['company']}")
    elif args.type == "email":
        entry["status"] = "sent"
        entry["email_sent_at"] = today_str()
        print(f"Marked email sent for {entry['company']}")
    else:
        print(f"ERROR: unknown type '{args.type}'. Use 'followup' or 'email'.", file=sys.stderr)
        sys.exit(1)

    save_state(entries)


def load_queue():
    if not QUEUE_FILE.exists():
        return []
    with open(QUEUE_FILE) as f:
        return json.load(f)


def save_queue(entries):
    with open(QUEUE_FILE, "w") as f:
        json.dump(entries, f, indent=2, default=str)
        f.write("\n")


def _known_slugs():
    slugs = set()
    for e in load_state():
        slugs.add(e.get("slug", ""))
    for e in load_skipped():
        slugs.add(e.get("slug", ""))
    for e in load_queue():
        slugs.add(e.get("slug", ""))
    return slugs


def cmd_queue_add(args):
    slug = args.slug or args.company.lower().replace(" ", "-")
    known = _known_slugs()
    if slug in known:
        print(f"SKIP: '{slug}' already known (applications, skipped, or queue).")
        return
    if not args.website and not args.linkedin:
        print(f"SKIP: '{slug}' has no website or LinkedIn URL — Flow 1 needs at least one.")
        return
    entries = load_queue()
    entry = {
        "company": args.company,
        "slug": slug,
        "website": args.website or "",
        "linkedin_url": args.linkedin or "",
        "source": args.source or "",
        "source_url": args.source_url or "",
        "discovered_at": today_str(),
        "status": "queued",
    }
    entries.append(entry)
    save_queue(entries)
    print(f"Queued: {args.company} (slug={slug}, source={args.source or 'unknown'})")


def cmd_queue_list(args):
    entries = load_queue()
    limit = getattr(args, "limit", None)
    pending = [e for e in entries if e.get("status") == "queued"]
    if not pending:
        print("Queue is empty.")
        return
    if limit:
        pending = pending[:limit]
    print(f"Queued ({len(pending)}):\n")
    for e in pending:
        print(f"  {e['company']:35s}  {e.get('website') or e.get('linkedin_url')}")
        print(f"    Source: {e.get('source') or 'unknown'}  |  Discovered: {e.get('discovered_at')}")
        print()


def cmd_queue_next(args):
    count = getattr(args, "count", 1) or 1
    entries = load_queue()
    pending = [e for e in entries if e.get("status") == "queued"]
    to_process = pending[:count]
    if not to_process:
        print("Queue is empty.")
        return
    for e in entries:
        if e["slug"] in {x["slug"] for x in to_process}:
            e["status"] = "processing"
    save_queue(entries)
    import json as _json
    print(_json.dumps(to_process, indent=2, default=str))


def cmd_queue_remove(args):
    entries = load_queue()
    before = len(entries)
    entries = [e for e in entries if e.get("slug") != args.slug]
    if len(entries) == before:
        return
    save_queue(entries)
    print(f"Removed '{args.slug}' from queue.")


def cmd_queue_stats(args):
    entries = load_queue()
    queued = sum(1 for e in entries if e.get("status") == "queued")
    processing = sum(1 for e in entries if e.get("status") == "processing")
    print(f"Queue: {queued} queued, {processing} in-progress, {len(entries)} total in file")
    print(f"Applications processed: {len(load_state())}")
    print(f"Skipped: {len(load_skipped())}")


def cmd_queue(args):
    sub = getattr(args, "queue_command", None)
    if sub == "add":
        cmd_queue_add(args)
    elif sub == "list":
        cmd_queue_list(args)
    elif sub == "next":
        cmd_queue_next(args)
    elif sub == "remove":
        cmd_queue_remove(args)
    elif sub == "stats":
        cmd_queue_stats(args)
    else:
        print("Usage: state.py queue {add|list|next|remove|stats}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Manage job application state")
    sub = parser.add_subparsers(dest="command")

    # skip
    p_skip = sub.add_parser("skip", help="Log a skipped company with reason")
    p_skip.add_argument("--company", required=True)
    p_skip.add_argument("--slug")
    p_skip.add_argument("--reason", required=True, help="Short reason (e.g. 'Company shut down')")
    p_skip.add_argument("--details", help="Longer explanation")
    p_skip.add_argument("--source", help="URL where you found the info")

    # add
    p_add = sub.add_parser("add", help="Add a new application entry")
    p_add.add_argument("--company", required=True)
    p_add.add_argument("--slug")
    p_add.add_argument("--job-title")
    p_add.add_argument("--email-sent-to")
    p_add.add_argument("--status", default="drafted", choices=["sent", "drafted", "email-skipped"])
    p_add.add_argument("--hr-url")
    p_add.add_argument("--lead-url")

    # list-due
    sub.add_parser("list-due", help="Show follow-ups that are due")

    # list-all
    sub.add_parser("list-all", help="Show all tracked applications")

    # mark-sent
    p_mark = sub.add_parser("mark-sent", help="Update status for an entry")
    p_mark.add_argument("--slug", required=True)
    p_mark.add_argument("--type", required=True, choices=["email", "followup"])

    # queue
    p_queue = sub.add_parser("queue", help="Manage the discovery queue")
    queue_sub = p_queue.add_subparsers(dest="queue_command")

    pq_add = queue_sub.add_parser("add", help="Add a company to the queue")
    pq_add.add_argument("--company", required=True)
    pq_add.add_argument("--slug")
    pq_add.add_argument("--website", default="")
    pq_add.add_argument("--linkedin", default="")
    pq_add.add_argument("--source", default="")
    pq_add.add_argument("--source-url", default="", dest="source_url")

    pq_list = queue_sub.add_parser("list", help="Show queued companies")
    pq_list.add_argument("--limit", type=int, default=None)

    pq_next = queue_sub.add_parser("next", help="Pop next N companies for processing")
    pq_next.add_argument("--count", type=int, default=1)

    pq_remove = queue_sub.add_parser("remove", help="Remove a company from the queue")
    pq_remove.add_argument("--slug", required=True)

    queue_sub.add_parser("stats", help="Show queue statistics")

    args = parser.parse_args()

    if args.command == "skip":
        cmd_skip(args)
    elif args.command == "add":
        cmd_add(args)
    elif args.command == "list-due":
        cmd_list_due(args)
    elif args.command == "list-all":
        cmd_list_all(args)
    elif args.command == "mark-sent":
        cmd_mark_sent(args)
    elif args.command == "queue":
        cmd_queue(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
