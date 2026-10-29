#!/usr/bin/env python3
"""
Manage application state in state/applications.json, state/skipped.json, and state/queue.json.

Each application tracks outreach per person in `outreach`: one thread per LinkedIn contact
(HR, team lead, referral) and one for the email. A thread moves through steps (connect sent →
accepted → message sent → follow-ups → replied), and the date of each next step is counted in
work days (Sun–Thu by default, `work_days` in config/settings.json).

Commands:
  add          -- append a new application entry (threads are built from meta.json if present)
  sync         -- rebuild an application's threads from output/<slug>/meta.json, keeping progress
  event        -- record a step for one person (connect_sent, accepted, message_sent, followup_1...)
  close-thread -- stop following up with one person (--undo reopens)
  today        -- what to do today: messages to send, follow-ups due, things to check
  stats        -- accept and reply rates by contact type, language, and note vs. no note
  show         -- one application with its threads and next steps
  update       -- set the pipeline stage (replied, interview, offer, rejected, ghosted...)
  close-all    -- close many applications at once (e.g. old ones that never answered)
  migrate      -- build threads for entries created before per-person tracking
  skip         -- log a company that was skipped (with reason + details)
  list-due     -- follow-ups due (same data as `today`, follow-ups only)
  list-all     -- show all entries
  mark-sent    -- mark the email (or its next follow-up) as sent
  mark-task    -- record a manually-completed task (applied, connected_hr, messaged_lead...)
  queue        -- manage the discovery queue (sub-commands: add, list, next, remove, reset, stats)
  slug         -- print the slug for a company name

Every command holds a lock on the state files while it runs, so the dashboard server and a
background run (scripts/runs.py) can write at the same time without losing each other's change.

Usage examples:
  python3 scripts/state.py slug "Wiz Inc."                      # -> wiz-inc

  python3 scripts/state.py add --company "Wiz" --slug "wiz" --job-title "Backend Engineer" \\
    --email-sent-to "careers@wiz.io" --status drafted

  python3 scripts/state.py event --slug wiz --key hr --event connect_sent --lang he
  python3 scripts/state.py event --slug wiz --key hr --event connect_sent --lang en --no-note
  python3 scripts/state.py event --slug wiz --key lead --event accepted
  python3 scripts/state.py event --slug wiz --key lead --event message_sent --lang he
  python3 scripts/state.py event --slug wiz --key email --event sent
  python3 scripts/state.py event --slug wiz --key hr --event replied
  python3 scripts/state.py event --slug wiz --key hr --event already_connected
  python3 scripts/state.py event --slug wiz --key hr --event accepted --undo

  python3 scripts/state.py today
  python3 scripts/state.py stats --days 30

  python3 scripts/state.py update --slug "wiz" --stage interview --note "Phone screen Tuesday"
  python3 scripts/state.py close-all --stage ghosted --before 2026-09-01 --except acme,globex

  python3 scripts/state.py skip --company "XACT Robotics" --slug "xact-robotics" \\
    --reason "Company shut down" --details "Shut down Sep 2023." --source "https://..."

  python3 scripts/state.py queue add --company "Wiz" --slug "wiz" --website "https://wiz.io"
  python3 scripts/state.py queue next --count 3
"""

import argparse
import fcntl
import json
import os
import re
import sys
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(os.environ.get("JOB_AGENT_ROOT") or Path(__file__).resolve().parent.parent)
STATE_FILE = ROOT / "state" / "applications.json"
SKIPPED_FILE = ROOT / "state" / "skipped.json"
QUEUE_FILE = ROOT / "state" / "queue.json"
SETTINGS_FILE = ROOT / "config" / "settings.json"
OUTPUT_DIR = ROOT / "output"

# Pipeline stages beyond the initial email status (sent/drafted/email-skipped).
# A closed stage means nothing more to do for that company: no actions, no follow-ups.
STAGES = ["applied", "replied", "interview", "offer", "rejected", "ghosted", "withdrawn"]
CLOSED_STAGES = {"rejected", "withdrawn", "offer", "ghosted"}

TASK_TYPES = ["applied", "connected_hr", "connected_lead", "messaged_hr", "messaged_lead"]

# Steps a thread can record. Follow-ups are numbered up to the length of
# followup_schedule_workdays; `sent` is the email channel's first step.
EVENTS = ["connect_sent", "accepted", "message_sent", "sent",
          "followup_1", "followup_2", "followup_3", "replied"]
CLOSE_REASONS = {
    "ghosted": "No reply after the follow-ups",
    "no_accept": "Never accepted the connect request",
    "closed": "Closed by you",
}
KIND_LABELS = {"hr": "HR / recruiter", "lead": "Team lead", "referral": "Referral",
               "email": "Email", "other": "Contact"}

DEFAULT_SETTINGS = {
    "followup_days": 5,
    "work_days": ["sun", "mon", "tue", "wed", "thu"],
    "followup_schedule_workdays": [4, 5],
    "ghost_after_workdays": 5,
    "no_accept_after_workdays": 10,
    "connect_note_max_chars": 200,
    "linkedin_note_monthly_limit": 5,
    "message_languages": ["en", "he"],
    "dashboard_port": 8765,
    # Background runs (scripts/runs.py): stop a run after this long, notify when one ends,
    # and the model to use (None = your Claude Code default)
    "run_timeout_minutes": 40,
    "notify_when_done": True,
    "background_model": None,
}


def slugify(name: str) -> str:
    """lowercase, non-alphanumeric runs -> '-', trim leading/trailing '-'."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "company"


_NULLISH = {"null", "none", "n/a", "not found", ""}


def _clean(value):
    """Treat CLI args like --hr-url null (literal word, not omitted) as unset."""
    if value is None:
        return None
    if str(value).strip().lower() in _NULLISH:
        return None
    return value


def _read_json(path, default):
    path = Path(path)
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path, data):
    """Write atomically so the dashboard server and the CLI never see half a file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        f.write("\n")
    os.replace(tmp, path)


@contextmanager
def state_lock(name="state"):
    """Hold an exclusive lock while reading, changing and saving state files.

    The dashboard server, this CLI and a background run's state.py calls can now run at the
    same moment; without the lock two read-modify-writes can interleave and one change is
    lost. Works across threads and processes (one flock per open). Don't nest the same name.
    """
    path = ROOT / "state" / f".{name}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def load_state():
    return _read_json(STATE_FILE, [])


def save_state(entries):
    _write_json(STATE_FILE, entries)


def load_settings():
    settings = dict(DEFAULT_SETTINGS)
    settings.update(_read_json(SETTINGS_FILE, {}) or {})
    return settings


def load_meta(slug):
    try:
        return _read_json(OUTPUT_DIR / slug / "meta.json", None)
    except json.JSONDecodeError:
        return None


def save_meta(slug, meta):
    _write_json(OUTPUT_DIR / slug / "meta.json", meta)


def today_str():
    return date.today().isoformat()


def find_entry(entries, slug):
    return next((e for e in entries if e.get("slug") == slug), None)


def _require_entry(entries, slug):
    entry = find_entry(entries, slug)
    if not entry:
        print(f"ERROR: no entry found for slug '{slug}'", file=sys.stderr)
        sys.exit(1)
    return entry


def load_skipped():
    return _read_json(SKIPPED_FILE, [])


def save_skipped(entries):
    _write_json(SKIPPED_FILE, entries)


# ---------------------------------------------------------------------------
# Work days
# ---------------------------------------------------------------------------

_DAY_INDEX = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def work_days(settings):
    names = settings.get("work_days") or DEFAULT_SETTINGS["work_days"]
    days = {_DAY_INDEX[n[:3].lower()] for n in names if n[:3].lower() in _DAY_INDEX}
    return days or {6, 0, 1, 2, 3}


def _as_date(value):
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def add_workdays(start, n, wd):
    d = _as_date(start)
    added = 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() in wd:
            added += 1
    return d.isoformat()


def workdays_between(start, end, wd):
    """Work days after `start` up to and including `end` (0 if end <= start)."""
    d, stop, count = _as_date(start), _as_date(end), 0
    while d < stop:
        d += timedelta(days=1)
        if d.weekday() in wd:
            count += 1
    return count


# ---------------------------------------------------------------------------
# Outreach threads (one per person / channel)
# ---------------------------------------------------------------------------

def contact_kind(contact):
    kind = (contact.get("kind") or "").lower()
    if kind in KIND_LABELS:
        return kind
    title = (contact.get("title") or "").lower()
    if "referral" in title or contact.get("connected"):
        return "referral"
    if "hr" in re.split(r"\W+", title) or any(w in title for w in ("recruit", "talent", "people")):
        return "hr"
    if any(w in title for w in ("lead", "manager", "cto", "r&d", "founder", "head")):
        return "lead"
    return "other"


def _has_person(contact):
    profile = _clean(contact.get("profile"))
    name = _clean(contact.get("name"))
    return bool(profile or name)


def contact_keys(contacts):
    """Thread key for each meta.json contact, in order (None for "not found" contacts)."""
    keys, used = [], set()
    for i, c in enumerate(contacts or []):
        if not _has_person(c):
            keys.append(None)
            continue
        kind = contact_kind(c)
        key = str(c.get("key") or (kind if kind in ("hr", "lead") else f"{kind}-{i}"))
        if key in used:
            key = f"{key}-{i}"
        used.add(key)
        keys.append(key)
    return keys


def sync_threads(entry, meta):
    """(Re)build entry["outreach"] from meta.json contacts and the email draft.

    Progress already recorded on a thread is kept (matched by key). A thread that
    disappears from meta.json is dropped unless it has recorded steps.
    """
    existing = {t["key"]: t for t in entry.get("outreach") or []}
    threads = []
    contacts = (meta or {}).get("contacts") or []

    def take(key, base):
        t = existing.pop(key, None) or {"key": key, "events": {}}
        t.update({k: v for k, v in base.items() if v is not None})
        t.setdefault("events", {})
        threads.append(t)
        return t

    for c, key in zip(contacts, contact_keys(contacts)):
        if key is None:
            continue
        c["key"] = key
        take(key, {"kind": contact_kind(c), "channel": "linkedin", "name": _clean(c.get("name")),
                   "title": _clean(c.get("job_title")), "profile": _clean(c.get("profile")),
                   "connected": bool(c.get("connected")) or None})

    if not contacts:
        for key, url in (("hr", entry.get("hr_url")), ("lead", entry.get("lead_url"))):
            if _clean(url):
                take(key, {"kind": key, "channel": "linkedin", "profile": url})

    draft = (meta or {}).get("email_draft") or {}
    email_to = _clean(entry.get("email_sent_to")) or _clean(draft.get("to"))
    if email_to and (draft.get("body") or draft.get("body_he") or entry.get("status") in ("sent", "drafted")):
        t = take("email", {"kind": "email", "channel": "email", "to": email_to})
        if entry.get("status") == "sent" and not t["events"].get("sent"):
            t["events"]["sent"] = entry.get("email_sent_at") or entry.get("created_at") or today_str()

    for t in existing.values():
        if t.get("events"):
            threads.append(t)

    entry["outreach"] = threads
    # Keep the older flat fields in step for anything that still reads them
    for t in threads:
        if t.get("kind") == "hr" and t.get("profile"):
            entry["hr_url"] = t["profile"]
        if t.get("kind") == "lead" and t.get("profile"):
            entry["lead_url"] = t["profile"]
    return threads


def get_thread(entry, key):
    return next((t for t in entry.get("outreach") or [] if t.get("key") == key), None)


def set_event(entry, key, event, when=None, lang=None, with_note=None, undo=False):
    """Record (or with undo, remove) one step on one thread. Returns the thread."""
    t = get_thread(entry, key)
    if t is None:
        known = ", ".join(x["key"] for x in entry.get("outreach") or []) or "none"
        raise ValueError(f"no thread '{key}' on {entry.get('slug')} (known: {known})")
    when = when or today_str()
    ev = t.setdefault("events", {})

    if event == "already_connected":
        t["connected"] = not undo
        return t
    if event not in EVENTS:
        raise ValueError(f"unknown event '{event}' (use one of: {', '.join(EVENTS)}, already_connected)")

    if undo:
        ev.pop(event, None)
        if event == "connect_sent":
            t.pop("with_note", None)
        return t

    ev[event] = when
    if t.get("channel") == "linkedin" and not t.get("connected"):
        # Messaging someone means they accepted, and accepting means a request was sent
        if event in ("message_sent", "followup_1", "followup_2", "followup_3", "replied"):
            ev.setdefault("accepted", when)
        if event != "connect_sent" and ev.get("accepted"):
            ev.setdefault("connect_sent", ev["accepted"])
    if t.get("channel") == "email" and event != "sent":
        ev.setdefault("sent", when)
    # The thread's language is the language of the first message that had text in it,
    # so a connect request sent without a note doesn't count
    if lang and not t.get("lang") and not (event == "connect_sent" and with_note is False):
        t["lang"] = lang
    if event == "connect_sent" and with_note is not None:
        t["with_note"] = bool(with_note)
    if event == "replied":
        t.pop("closed", None)
        t.pop("closed_at", None)
        if entry.get("stage") in (None, "applied", "ghosted"):
            entry["stage"] = "replied"
            entry["stage_updated_at"] = when
    return t


def close_thread(entry, key, reason="closed", undo=False):
    t = get_thread(entry, key)
    if t is None:
        raise ValueError(f"no thread '{key}' on {entry.get('slug')}")
    if undo:
        t.pop("closed", None)
        t.pop("closed_at", None)
    else:
        t["closed"] = reason if reason in CLOSE_REASONS else "closed"
        t["closed_at"] = today_str()
    return t


def action_label(kind, n=None, total=None, settings=None):
    if kind == "connect":
        return "Send the connect request"
    if kind == "message":
        return "They accepted: send your first message"
    if kind == "email":
        return "Send the email (it's still a draft)"
    if kind == "apply":
        return "Apply on the site"
    if kind == "no_accept":
        return f"Not accepted after {n} work days: try someone else, or close"
    if kind.startswith("followup"):
        last = " (last one)" if total and n == total and total > 1 else ""
        return f"Follow-up #{n}{last}"
    return kind


def _act(kind, due, today, wd, label, n=None, total=None, text=None):
    overdue = workdays_between(due, today, wd) if today > due else 0
    return {"status": "action", "label": label, "next_date": due,
            "action": {"type": kind, "due": due, "overdue": overdue,
                       "text": text or action_label(kind, n, total), "n": n}}


def _wait(label, next_date, waiting):
    return {"status": "waiting", "label": label, "next_date": next_date, "waiting": waiting, "action": None}


def thread_state(entry, t, today, settings):
    """Where one thread stands and what (if anything) to do next."""
    wd = work_days(settings)
    ev = t.get("events") or {}
    created = (entry.get("created_at") or today)[:10]

    if t.get("closed"):
        return {"status": "closed", "label": CLOSE_REASONS.get(t["closed"], "Closed"),
                "next_date": None, "action": None}
    if ev.get("replied"):
        return {"status": "replied", "label": f"Replied on {ev['replied']}", "next_date": None, "action": None}

    if t.get("channel") == "email":
        if not ev.get("sent"):
            return _act("email", created, today, wd, "Email is a draft, not sent")
        last = ev["sent"]
    else:
        if not t.get("connected"):
            if not ev.get("connect_sent"):
                return _act("connect", created, today, wd, "Not contacted yet")
            if not ev.get("accepted"):
                n = int(settings.get("no_accept_after_workdays", 10))
                check_on = add_workdays(ev["connect_sent"], n, wd)
                close_on = add_workdays(check_on, int(settings.get("ghost_after_workdays", 5)), wd)
                if today >= close_on:
                    return {"status": "closed", "label": CLOSE_REASONS["no_accept"], "next_date": None,
                            "action": None, "auto_close": "no_accept"}
                if today >= check_on:
                    return _act("no_accept", check_on, today, wd,
                                f"Connect sent {ev['connect_sent']}, not accepted", n=n)
                return _wait(f"Waiting for them to accept (sent {ev['connect_sent']})", check_on, "accept")
        if not ev.get("message_sent"):
            text = "Send your message (you're already connected)" if t.get("connected") else None
            return _act("message", ev.get("accepted") or created, today, wd, "Connected, no message yet", text=text)
        last = ev["message_sent"]

    schedule = settings.get("followup_schedule_workdays") or DEFAULT_SETTINGS["followup_schedule_workdays"]
    total = len(schedule)
    for i, gap in enumerate(schedule, start=1):
        key = f"followup_{i}"
        if not ev.get(key):
            due = add_workdays(last, int(gap), wd)
            if today >= due:
                return _act(key, due, today, wd, "No reply yet", n=i, total=total)
            return _wait(f"Waiting for a reply · follow-up #{i} on {due}", due, "reply")
        last = ev[key]
    ghost_on = add_workdays(last, int(settings.get("ghost_after_workdays", 5)), wd)
    if today >= ghost_on:
        return {"status": "closed", "label": CLOSE_REASONS["ghosted"], "next_date": None,
                "action": None, "auto_close": "ghosted"}
    return _wait(f"Last follow-up sent · closes as no answer on {ghost_on}", ghost_on, "reply")


def apply_action(entry, meta, today, settings):
    apply_url = (meta or {}).get("apply_url")
    if not apply_url or (entry.get("tasks") or {}).get("applied") or entry.get("stage") in CLOSED_STAGES:
        return None
    created = (entry.get("created_at") or today)[:10]
    return _act("apply", created, today, work_days(settings), "Not applied on the site yet")["action"]


def entry_overview(entry, meta, today, settings):
    """[(thread, state)], plus the apply action if there is one."""
    rows = [(t, thread_state(entry, t, today, settings)) for t in entry.get("outreach") or []]
    return rows, apply_action(entry, meta, today, settings)


def entry_next(entry, meta, today, settings):
    """One line for the dashboard card: the most urgent thing, or the next date."""
    if entry.get("stage") in CLOSED_STAGES:
        return None
    rows, apply = entry_overview(entry, meta, today, settings)
    actions = [s["action"] for _, s in rows if s.get("action")] + ([apply] if apply else [])
    if actions:
        a = min(actions, key=lambda x: x["due"])
        more = f" (+{len(actions) - 1} more)" if len(actions) > 1 else ""
        return {"kind": "action", "text": a["text"] + more, "due": a["due"], "overdue": a["overdue"]}
    waits = [s for _, s in rows if s.get("next_date")]
    if waits:
        w = min(waits, key=lambda s: s["next_date"])
        return {"kind": "waiting", "text": w["label"], "due": w["next_date"], "overdue": 0}
    return None


def auto_close(entries, today, settings):
    """Persist closes the schedule implies. Returns a list of human-readable changes."""
    changes = []
    for e in entries:
        if e.get("stage") in CLOSED_STAGES:
            continue
        threads = e.get("outreach") or []
        for t in threads:
            st = thread_state(e, t, today, settings)
            if st.get("auto_close"):
                t["closed"] = st["auto_close"]
                t["closed_at"] = today
                who = t.get("name") or KIND_LABELS.get(t.get("kind"), t["key"])
                changes.append(f"{e['company']}: {who} closed ({CLOSE_REASONS[st['auto_close']].lower()})")
        if threads and e.get("stage") in (None, "applied") and all(t.get("closed") for t in threads) \
                and not any((t.get("events") or {}).get("replied") for t in threads):
            e["stage"] = "ghosted"
            e["stage_updated_at"] = today
            e.setdefault("stage_notes", []).append({"date": today, "note": "auto: no reply after the follow-ups"})
            changes.append(f"{e['company']}: closed as no answer")
    return changes


def notes_this_month(entries, today):
    month = today[:7]
    return sum(1 for e in entries for t in e.get("outreach") or []
               if t.get("with_note") and str((t.get("events") or {}).get("connect_sent", "")).startswith(month))


def compute_today(entries, today, settings):
    wd = work_days(settings)
    horizon = add_workdays(today, 5, wd)
    items, upcoming = [], []
    waiting = {"accept": 0, "reply": 0}
    for e in entries:
        if e.get("stage") in CLOSED_STAGES:
            continue
        meta = load_meta(e["slug"])
        rows, apply = entry_overview(e, meta, today, settings)
        base = {"slug": e["slug"], "company": e.get("company"), "job_title": e.get("job_title")}
        if apply:
            items.append(dict(base, group="now", key=None, kind="apply", name=None,
                              apply_url=(meta or {}).get("apply_url"), action=apply))
        for t, st in rows:
            person = dict(base, key=t["key"], kind=t.get("kind"), name=t.get("name"),
                          profile=t.get("profile"), to=t.get("to"), channel=t.get("channel"))
            a = st.get("action")
            if a:
                group = ("followups" if a["type"].startswith("followup")
                         else "check" if a["type"] == "no_accept" else "now")
                items.append(dict(person, group=group, action=a))
            elif st.get("waiting"):
                waiting[st["waiting"]] += 1
                if st["next_date"] <= horizon:
                    upcoming.append(dict(person, date=st["next_date"], label=st["label"]))
    items.sort(key=lambda x: (x["action"]["due"], x["company"] or ""))
    upcoming.sort(key=lambda x: x["date"])
    return {"date": today, "items": items, "upcoming": upcoming, "waiting": waiting,
            "notes_this_month": notes_this_month(entries, today),
            "note_limit": settings.get("linkedin_note_monthly_limit")}


def compute_stats(entries, today, settings, days=None):
    since = (date.fromisoformat(today) - timedelta(days=days)).isoformat() if days else None
    rows = []
    for e in entries:
        for t in e.get("outreach") or []:
            ev = t.get("events") or {}
            first = ev.get("connect_sent") or ev.get("message_sent") or ev.get("sent")
            if not first or (since and first < since):
                continue
            linkedin = t.get("channel") == "linkedin"
            rows.append({
                "kind": t.get("kind") or "other",
                "channel": t.get("channel"),
                "lang": t.get("lang") or "language not recorded",
                "note": (("with note" if t.get("with_note") else "no note")
                         if linkedin and ev.get("connect_sent") else None),
                "connect": linkedin and bool(ev.get("connect_sent")),
                "accepted": linkedin and bool(ev.get("accepted")),
                "replied": bool(ev.get("replied")),
            })

    def summarize(subset):
        sent = len(subset)
        connects = sum(1 for r in subset if r["connect"])
        accepted = sum(1 for r in subset if r["accepted"])
        replied = sum(1 for r in subset if r["replied"])
        return {"sent": sent, "connects": connects, "accepted": accepted, "replied": replied,
                "accept_rate": round(accepted / connects, 2) if connects else None,
                "reply_rate": round(replied / sent, 2) if sent else None}

    def by(field, labels=None):
        groups = {}
        for r in rows:
            if r[field] is None:
                continue
            groups.setdefault(r[field], []).append(r)
        return {(labels or {}).get(k, k): summarize(v) for k, v in sorted(groups.items())}

    stages = {}
    for e in entries:
        stage = e.get("stage") or "active"
        stages[stage] = stages.get(stage, 0) + 1
    return {
        "window_days": days,
        "all": summarize(rows),
        "by_kind": by("kind", KIND_LABELS),
        "by_lang": by("lang", {"en": "English", "he": "Hebrew"}),
        "by_note": by("note"),
        "stages": stages,
        "applications": len(entries),
        "notes_this_month": notes_this_month(entries, today),
        "note_limit": settings.get("linkedin_note_monthly_limit"),
    }


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_slug(args):
    print(slugify(args.name))


def cmd_skip(args):
    entries = load_skipped()
    slug = args.slug or slugify(args.company)
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

    slug = args.slug or slugify(args.company)
    followup_due = (date.today() + timedelta(days=followup_days)).isoformat()

    # Don't add duplicate slug
    existing = find_entry(entries, slug)
    if existing:
        print(f"WARNING: entry for '{slug}' already exists (added {existing.get('created_at')}). Skipping.")
        print("  Use --slug with a unique name if this is a second application to the same company.")
        sys.exit(0)

    entry = {
        "company": args.company,
        "slug": slug,
        "job_title": _clean(args.job_title),
        "email_sent_to": _clean(args.email_sent_to),
        "status": args.status,
        "hr_url": _clean(args.hr_url),
        "lead_url": _clean(args.lead_url),
        "created_at": today_str(),
        "followup_due": followup_due,
        "followup_status": "pending",
    }
    if args.status == "sent":
        entry["email_sent_at"] = today_str()
    threads = sync_threads(entry, load_meta(slug))
    entries.append(entry)
    save_state(entries)
    people = ", ".join(t.get("name") or t["key"] for t in threads) or "none"
    print(f"Added: {args.company} | status={args.status} | tracking: {people}")


def cmd_sync(args):
    entries = load_state()
    entry = _require_entry(entries, args.slug)
    meta = load_meta(args.slug)
    threads = sync_threads(entry, meta)
    if meta:
        save_meta(args.slug, meta)  # contacts get their thread keys written back
    save_state(entries)
    print(f"Synced {entry['company']}: " + (", ".join(
        f"{t['key']} ({t.get('name') or t.get('profile') or t.get('to')})" for t in threads) or "no people"))


def cmd_event(args):
    entries = load_state()
    entry = _require_entry(entries, args.slug)
    try:
        t = set_event(entry, args.key, args.event, when=args.date, lang=args.lang,
                      with_note=(False if args.no_note else (True if args.event == "connect_sent" else None)),
                      undo=args.undo)
    except ValueError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)
    save_state(entries)
    st = thread_state(entry, t, today_str(), load_settings())
    verb = "Removed" if args.undo else "Recorded"
    print(f"{verb} {args.event} for {entry['company']} / {t.get('name') or t['key']} → now: {st['label']}")


def cmd_close_thread(args):
    entries = load_state()
    entry = _require_entry(entries, args.slug)
    try:
        t = close_thread(entry, args.key, args.reason, undo=args.undo)
    except ValueError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)
    save_state(entries)
    print(f"{'Reopened' if args.undo else 'Closed'} {entry['company']} / {t.get('name') or t['key']}")


def _who(item):
    if item.get("kind") == "apply":
        return ""
    label = KIND_LABELS.get(item.get("kind"), item.get("kind") or "")
    return f" — {item['name']} ({label})" if item.get("name") else f" — {label}"


def _due_text(action):
    if action.get("overdue"):
        return f"overdue {action['overdue']} work day{'s' if action['overdue'] != 1 else ''}"
    return f"due {action['due']}"


def print_today(data, settings):
    d = _as_date(data["date"])
    print(f"Today — {d.strftime('%a')} {data['date']}\n")
    groups = [("now", "DO NOW"), ("followups", "FOLLOW-UPS DUE"), ("check", "CHECK")]
    any_items = False
    for gid, title in groups:
        items = [i for i in data["items"] if i["group"] == gid]
        if not items:
            continue
        any_items = True
        print(f"{title} ({len(items)})")
        for i in items:
            a = i["action"]
            print(f"  • {i['company']}{_who(i)}: {a['text']}  [{_due_text(a)}]")
            link = i.get("profile") or i.get("apply_url") or (f"mailto:{i['to']}" if i.get("to") else None)
            if link:
                print(f"      {link}")
        print()
    if not any_items:
        print("Nothing to send today.\n")
    if data["upcoming"]:
        print("COMING UP (next 5 work days)")
        for u in data["upcoming"]:
            print(f"  • {u['date']}  {u['company']}{_who(u)}: {u['label']}")
        print()
    w = data["waiting"]
    print(f"Waiting: {w['accept']} connect request{'s' if w['accept'] != 1 else ''} to be accepted, "
          f"{w['reply']} message{'s' if w['reply'] != 1 else ''} waiting for a reply")
    if data.get("note_limit"):
        print(f"LinkedIn notes sent this month: {data['notes_this_month']} "
              f"(free accounts get about {data['note_limit']} a month)")
    print(f"Dashboard: python3 scripts/serve.py  (http://localhost:{settings.get('dashboard_port', 8765)})")


def cmd_today(args):
    entries = load_state()
    settings = load_settings()
    today = args.date or today_str()
    changes = [] if args.no_auto else auto_close(entries, today, settings)
    if changes:
        save_state(entries)
    data = compute_today(entries, today, settings)
    data["auto_closed"] = changes
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    print_today(data, settings)
    if changes:
        print("\nClosed automatically (no reply after the follow-ups):")
        for c in changes:
            print(f"  • {c}")


def _rate(n, d):
    return f"{n} ({round(100 * n / d)}%)" if d else "-"


def cmd_stats(args):
    entries = load_state()
    settings = load_settings()
    data = compute_stats(entries, today_str(), settings, args.days)
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    window = f"last {args.days} days" if args.days else "all time"
    print(f"Outreach — {window} ({data['all']['sent']} people contacted)\n")
    print(f"  {'':18s} {'contacted':>9s} {'accepted':>12s} {'replied':>12s}")

    def line(label, s):
        print(f"  {label:18s} {s['sent']:>9d} {_rate(s['accepted'], s['connects']):>12s} "
              f"{_rate(s['replied'], s['sent']):>12s}")

    line("All", data["all"])
    for section in ("by_kind", "by_lang", "by_note"):
        if data[section]:
            print()
            for label, s in data[section].items():
                line(label, s)
    stages = data["stages"]
    print(f"\nApplications: {data['applications']} — " + ", ".join(
        f"{n} {k}" for k, n in sorted(stages.items(), key=lambda kv: -kv[1])))
    if data.get("note_limit"):
        print(f"LinkedIn notes this month: {data['notes_this_month']} (free limit about {data['note_limit']})")
    if data["all"]["sent"] < 10:
        print("\n(Small numbers: wait for 10+ contacts before reading much into the rates.)")


def cmd_show(args):
    entries = load_state()
    settings = load_settings()
    entry = _require_entry(entries, args.slug)
    meta = load_meta(args.slug)
    today = today_str()
    print(f"{entry['company']} — {entry.get('job_title') or 'general'}  "
          f"[stage: {entry.get('stage') or 'active'}, added {entry.get('created_at')}]")
    rows, apply = entry_overview(entry, meta, today, settings)
    if apply:
        print(f"  Apply: {apply['text']} ({_due_text(apply)}) {(meta or {}).get('apply_url', '')}")
    for t, st in rows:
        who = t.get("name") or t.get("profile") or t.get("to") or ""
        steps = ", ".join(f"{k} {v}" for k, v in (t.get("events") or {}).items()) or "no steps yet"
        extra = []
        if t.get("lang"):
            extra.append(t["lang"])
        if t.get("with_note") is not None:
            extra.append("with note" if t["with_note"] else "no note")
        print(f"  [{t['key']}] {KIND_LABELS.get(t.get('kind'), t.get('kind'))}: {who}")
        print(f"      {steps}{(' · ' + ', '.join(extra)) if extra else ''}")
        nxt = st["action"]["text"] + f" ({_due_text(st['action'])})" if st.get("action") else st["label"]
        print(f"      → {nxt}")
    for note in entry.get("stage_notes") or []:
        print(f"  note {note['date']}: {note['note']}")


def cmd_list_due(args):
    entries = load_state()
    settings = load_settings()
    data = compute_today(entries, today_str(), settings)
    due = [i for i in data["items"] if i["group"] == "followups"]
    if not due:
        print("No follow-ups due.")
        return
    print(f"Follow-ups due ({len(due)}):\n")
    for i in due:
        a = i["action"]
        print(f"  {i['company']}{_who(i)}: {a['text']} [{_due_text(a)}]")
        print(f"    slug={i['slug']} key={i['key']} channel={i.get('channel')} "
              f"{i.get('profile') or i.get('to') or ''}")
        print()


def cmd_list_all(args):
    entries = load_state()
    settings = load_settings()
    if not entries:
        print("No applications tracked yet.")
        return
    today = today_str()
    for e in entries:
        nxt = entry_next(e, load_meta(e["slug"]), today, settings)
        status_line = e.get("stage") or "active"
        if nxt:
            status_line += f" · {nxt['text']} ({nxt['due']})"
        print(f"  {e['company']:30s} {(e.get('job_title') or 'general')[:35]:35s} {status_line}")


def cmd_mark_sent(args):
    entries = load_state()
    entry = _require_entry(entries, args.slug)
    today = today_str()
    email = get_thread(entry, "email")

    if args.type == "followup":
        entry["followup_status"] = "sent"
        entry["followup_sent_at"] = today
        if email:
            ev = email.setdefault("events", {})
            n = next((i for i in range(1, 4) if not ev.get(f"followup_{i}")), 3)
            set_event(entry, "email", f"followup_{n}")
        print(f"Marked follow-up sent for {entry['company']}")
    elif args.type == "email":
        entry["status"] = "sent"
        entry["email_sent_at"] = today
        if not email:
            sync_threads(entry, load_meta(args.slug))
            email = get_thread(entry, "email")
        if email:
            set_event(entry, "email", "sent")
        print(f"Marked email sent for {entry['company']}")
    save_state(entries)


def cmd_update(args):
    entries = load_state()
    entry = _require_entry(entries, args.slug)

    entry["stage"] = args.stage
    entry["stage_updated_at"] = today_str()
    if args.note:
        entry.setdefault("stage_notes", []).append({"date": today_str(), "note": args.note})

    save_state(entries)
    closed = " (closed — no more follow-ups)" if args.stage in CLOSED_STAGES else ""
    print(f"Updated {entry['company']}: stage={args.stage}{closed}")


# Older task names recorded by hand, mapped onto thread steps
_TASK_EVENTS = {
    "connected_hr": ("hr", "connect_sent"),
    "connected_lead": ("lead", "connect_sent"),
    "messaged_hr": ("hr", "message_sent"),
    "messaged_lead": ("lead", "message_sent"),
}


def cmd_mark_task(args):
    entries = load_state()
    entry = _require_entry(entries, args.slug)
    entry.setdefault("tasks", {})[args.task] = today_str()
    mapped = _TASK_EVENTS.get(args.task)
    if mapped and get_thread(entry, mapped[0]):
        set_event(entry, mapped[0], mapped[1])
    save_state(entries)
    print(f"Marked '{args.task}' done for {entry['company']}")


def cmd_close_all(args):
    entries = load_state()
    keep = {s.strip() for s in (args.except_slugs or "").split(",") if s.strip()}
    today = today_str()
    closed = []
    for e in entries:
        if e["slug"] in keep or e.get("stage") in CLOSED_STAGES:
            continue
        if args.before and (e.get("created_at") or "") >= args.before:
            continue
        e["stage"] = args.stage
        e["stage_updated_at"] = today
        if args.note:
            e.setdefault("stage_notes", []).append({"date": today, "note": args.note})
        closed.append(e["company"])
    save_state(entries)
    print(f"Closed {len(closed)} as {args.stage}" + (f": {', '.join(closed)}" if closed else ""))


def cmd_migrate(args):
    entries = load_state()
    migrated = 0
    for e in entries:
        if e.get("outreach") and not args.force:
            continue
        sync_threads(e, load_meta(e["slug"]))
        for task, when in (e.get("tasks") or {}).items():
            mapped = _TASK_EVENTS.get(task)
            if mapped and get_thread(e, mapped[0]):
                set_event(e, mapped[0], mapped[1], when=when)
        if e.get("followup_status") == "sent" and get_thread(e, "email"):
            set_event(e, "email", "followup_1", when=e.get("followup_sent_at") or e.get("created_at"))
        migrated += 1
    save_state(entries)
    print(f"Built outreach threads for {migrated} application{'s' if migrated != 1 else ''}.")


def load_queue():
    return _read_json(QUEUE_FILE, [])


def save_queue(entries):
    _write_json(QUEUE_FILE, entries)


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
    slug = args.slug or slugify(args.company)
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
    print(json.dumps(to_process, indent=2, default=str))


def cmd_queue_remove(args):
    entries = load_queue()
    before = len(entries)
    entries = [e for e in entries if e.get("slug") != args.slug]
    if len(entries) == before:
        print(f"WARNING: '{args.slug}' not found in queue — nothing removed.", file=sys.stderr)
        return
    save_queue(entries)
    print(f"Removed '{args.slug}' from queue.")


def cmd_queue_reset(args):
    """Un-stick queue entries left in 'processing' (e.g. an interrupted run)."""
    entries = load_queue()
    if args.slug:
        targets = [e for e in entries if e.get("slug") == args.slug and e.get("status") == "processing"]
    else:
        targets = [e for e in entries if e.get("status") == "processing"]
    if not targets:
        print("Nothing to reset.")
        return
    for e in targets:
        e["status"] = "queued"
    save_queue(entries)
    names = ", ".join(e["company"] for e in targets)
    print(f"Reset {len(targets)} entr{'y' if len(targets) == 1 else 'ies'} back to queued: {names}")


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
    elif sub == "reset":
        cmd_queue_reset(args)
    elif sub == "stats":
        cmd_queue_stats(args)
    else:
        print("Usage: state.py queue {add|list|next|remove|reset|stats}")
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

    # sync
    p_sync = sub.add_parser("sync", help="Rebuild outreach threads from output/<slug>/meta.json")
    p_sync.add_argument("--slug", required=True)

    # event
    p_event = sub.add_parser("event", help="Record a step for one person")
    p_event.add_argument("--slug", required=True)
    p_event.add_argument("--key", required=True, help="Thread key: hr, lead, email, referral-2...")
    p_event.add_argument("--event", required=True, choices=EVENTS + ["already_connected"])
    p_event.add_argument("--lang", choices=["en", "he"], help="Language of the message you sent")
    p_event.add_argument("--no-note", action="store_true", help="Connect request sent without a note")
    p_event.add_argument("--date", help="YYYY-MM-DD (default: today)")
    p_event.add_argument("--undo", action="store_true", help="Remove this step instead")

    # close-thread
    p_close = sub.add_parser("close-thread", help="Stop following up with one person")
    p_close.add_argument("--slug", required=True)
    p_close.add_argument("--key", required=True)
    p_close.add_argument("--reason", default="closed", choices=sorted(CLOSE_REASONS))
    p_close.add_argument("--undo", action="store_true", help="Reopen the thread")

    # today
    p_today = sub.add_parser("today", help="What to do today")
    p_today.add_argument("--json", action="store_true")
    p_today.add_argument("--no-auto", action="store_true", help="Don't auto-close finished threads")
    p_today.add_argument("--date", help="Pretend today is YYYY-MM-DD")

    # stats
    p_stats = sub.add_parser("stats", help="Accept and reply rates")
    p_stats.add_argument("--days", type=int, default=None, help="Only people first contacted in the last N days")
    p_stats.add_argument("--json", action="store_true")

    # show
    p_show = sub.add_parser("show", help="One application with its threads and next steps")
    p_show.add_argument("--slug", required=True)

    # list-due
    sub.add_parser("list-due", help="Show follow-ups that are due")

    # list-all
    sub.add_parser("list-all", help="Show all tracked applications")

    # mark-sent
    p_mark = sub.add_parser("mark-sent", help="Update status for an entry")
    p_mark.add_argument("--slug", required=True)
    p_mark.add_argument("--type", required=True, choices=["email", "followup"])

    # update
    p_update = sub.add_parser("update", help="Update the pipeline stage for an entry")
    p_update.add_argument("--slug", required=True)
    p_update.add_argument("--stage", required=True, choices=STAGES)
    p_update.add_argument("--note", help="Optional note (e.g. interview date, rejection reason)")

    # mark-task
    p_task = sub.add_parser("mark-task", help="Record a manually-completed task for an entry")
    p_task.add_argument("--slug", required=True)
    p_task.add_argument("--task", required=True, choices=TASK_TYPES)

    # close-all
    p_close_all = sub.add_parser("close-all", help="Close many applications at once")
    p_close_all.add_argument("--stage", default="ghosted", choices=sorted(CLOSED_STAGES))
    p_close_all.add_argument("--before", help="Only entries created before YYYY-MM-DD")
    p_close_all.add_argument("--except", dest="except_slugs", help="Comma-separated slugs to keep open")
    p_close_all.add_argument("--note", help="Note added to each closed entry")

    # migrate
    p_migrate = sub.add_parser("migrate", help="Build outreach threads for older entries")
    p_migrate.add_argument("--force", action="store_true", help="Rebuild even if threads exist")

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

    pq_reset = queue_sub.add_parser("reset", help="Reset stuck 'processing' entries back to queued")
    pq_reset.add_argument("--slug", help="Only reset this slug (default: reset all stuck entries)")

    queue_sub.add_parser("stats", help="Show queue statistics")

    # slug
    p_slug = sub.add_parser("slug", help="Print the slug for a company name")
    p_slug.add_argument("name")

    args = parser.parse_args()

    commands = {
        "skip": cmd_skip, "add": cmd_add, "sync": cmd_sync, "event": cmd_event,
        "close-thread": cmd_close_thread, "today": cmd_today, "stats": cmd_stats, "show": cmd_show,
        "list-due": cmd_list_due, "list-all": cmd_list_all, "mark-sent": cmd_mark_sent,
        "update": cmd_update, "mark-task": cmd_mark_task, "close-all": cmd_close_all,
        "migrate": cmd_migrate, "queue": cmd_queue, "slug": cmd_slug,
    }
    handler = commands.get(args.command)
    if not handler:
        parser.print_help()
        sys.exit(1)
    with state_lock():
        handler(args)


if __name__ == "__main__":
    main()
