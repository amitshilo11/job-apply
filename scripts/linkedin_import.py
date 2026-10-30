#!/usr/bin/env python3
"""
linkedin_import.py — catch up the tracking from your LinkedIn data export.

LinkedIn lets you download your own data (Settings & Privacy → Data privacy → Get a copy of
your data → pick Connections, Messages and Invitations → Request archive; LinkedIn emails a
link to a zip). This script reads that zip (or the unzipped folder) and, for every person
tracked in state/applications.json, records what really happened:

  connect_sent  your invitation to them (with or without a note)   ← Invitations.csv / messages.csv
  accepted      they're in your connections, connected after you applied ← Connections.csv
                (connected before the application → "already connected")
  message_sent  your first message after that                        ← messages.csv
  followup_N    later messages of yours with no answer in between
  replied       their first message back

People are matched by their LinkedIn profile URL (the /in/<name> part). A step already
recorded is never changed. The texts you sent to tracked people become writing samples
(scripts/samples.py), so drafts learn your real voice, Hebrew and English. Nothing else from
your inbox is read into the project. Connections.csv is also copied to config/ for
scripts/referrals.py.

Run it again with each new export: what was already imported is skipped
(state/linkedin_import.json). It reads files you downloaded; nothing on LinkedIn is touched.

Usage:
  python3 scripts/linkedin_import.py ~/Downloads/Basic_LinkedInDataExport_10-30-2026.zip
  python3 scripts/linkedin_import.py <zip or folder> --dry-run     # show what it would record
  python3 scripts/linkedin_import.py <zip or folder> --no-samples  # tracking only
"""

import argparse
import csv
import io
import re
import sys
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import state as st  # noqa: E402

LEDGER_FILE = st.ROOT / "state" / "linkedin_import.json"
FILES = {"connections": "connections.csv", "invitations": "invitations.csv", "messages": "messages.csv"}
# Messages and invitations sent a little before an application was created still count
# (the application is sometimes added after the first note went out)
SLACK_DAYS = 3
HEB = re.compile(r"[֐-׿]")


# ---------------------------------------------------------------------------
# Reading the export
# ---------------------------------------------------------------------------

def read_export(path):
    """{"connections": text, "invitations": text, "messages": text} for the files found."""
    path = Path(path).expanduser()
    found = {}
    if path.is_dir():
        for f in path.rglob("*.csv"):
            for key, name in FILES.items():
                if f.name.lower() == name and key not in found:
                    found[key] = f.read_text(encoding="utf-8-sig", errors="replace")
    elif zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                base = info.filename.rsplit("/", 1)[-1].lower()
                for key, name in FILES.items():
                    if base == name and key not in found:
                        found[key] = z.read(info).decode("utf-8-sig", errors="replace")
    elif path.suffix.lower() == ".csv" and path.exists():
        for key, name in FILES.items():
            if path.name.lower() == name:
                found[key] = path.read_text(encoding="utf-8-sig", errors="replace")
    else:
        raise SystemExit(f"Not a LinkedIn export zip or folder: {path}")
    return found


def rows(text, first_column):
    """CSV rows with lowercase keys. LinkedIn puts a few 'Notes:' lines before some headers."""
    lines = (text or "").splitlines()
    start = next((i for i, line in enumerate(lines) if line.lower().lstrip('"').startswith(first_column)), None)
    if start is None:
        return []
    reader = csv.DictReader(io.StringIO("\n".join(lines[start:])))
    return [{(k or "").strip().lower(): (v or "").strip() for k, v in r.items()} for r in reader]


def col(row, *names):
    for n in names:
        if row.get(n):
            return row[n]
    return ""


_DATE_FORMATS = ["%Y-%m-%d %H:%M:%S %Z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%y, %I:%M %p",
                 "%m/%d/%Y, %I:%M %p", "%d %b %Y", "%d %B %Y", "%m/%d/%y", "%m/%d/%Y"]


def parse_date(value):
    value = (value or "").strip()
    if not value:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    m = re.match(r"(\d{4}-\d{2}-\d{2})", value)
    return m.group(1) if m else None


def handle(url):
    """'https://il.linkedin.com/in/Noa-Cohen-123/?x' → 'noa-cohen-123' (None if not a profile)."""
    m = re.search(r"linkedin\.com/in/([^/?#\s]+)", unquote(url or ""), re.IGNORECASE)
    return m.group(1).lower() if m else None


def lang_of(text):
    return "he" if HEB.search(text or "") else "en"


def _norm(text):
    return re.sub(r"\s+", " ", text or "").strip().lower()


# ---------------------------------------------------------------------------
# What happened with each person
# ---------------------------------------------------------------------------

def load_export(found, sender_name):
    connections = {}
    for r in rows(found.get("connections"), "first name"):
        h = handle(col(r, "url", "profile url"))
        if h:
            connections[h] = parse_date(col(r, "connected on"))

    invitations = {}  # handle → earliest outgoing invitation
    own = set()
    for r in rows(found.get("invitations"), "from"):
        if col(r, "direction").upper() != "OUTGOING":
            continue
        own.add(handle(col(r, "inviterprofileurl", "inviter profile url")))
        h = handle(col(r, "inviteeprofileurl", "invitee profile url"))
        when = parse_date(col(r, "sent at", "date"))
        if h and when and (h not in invitations or when < invitations[h]["date"]):
            invitations[h] = {"date": when, "text": col(r, "message")}
    own.discard(None)

    msgs = []
    for r in rows(found.get("messages"), "conversation id"):
        when = parse_date(col(r, "date"))
        if not when:
            continue
        msgs.append({"date": when, "from_name": col(r, "from"), "from": handle(col(r, "sender profile url")),
                     "to": {handle(u) for u in re.split(r"[,\s]+", col(r, "recipient profile urls"))} - {None},
                     "text": col(r, "content")})
    # Which sender is you: your invitations say so; else your name; else whoever sent most
    if not own and sender_name:
        own = {m["from"] for m in msgs if m["from"] and _norm(m["from_name"]) == _norm(sender_name)}
    if not own and msgs:
        counts = {}
        for m in msgs:
            counts[m["from"]] = counts.get(m["from"], 0) + 1
        own = {max(counts, key=counts.get)} - {None}
    msgs.sort(key=lambda m: m["date"])
    return connections, invitations, msgs, own


def person_history(h, created, connections, invitations, msgs, own, schedule_len):
    """Steps found for one person, oldest first: [(event, date, text or None, extra)]."""
    since = (date.fromisoformat(created) - timedelta(days=SLACK_DAYS)).isoformat()
    steps = []
    invite = invitations.get(h)
    if invite and invite["date"] < since:
        invite = None
    connected_on = connections.get(h)

    if connected_on and connected_on < since and not invite:
        steps.append(("already_connected", connected_on, None, {}))
        connected_on = None

    convo = [m for m in msgs if m["date"] >= since and ((m["from"] in own and h in m["to"]) or m["from"] == h)]
    mine = [m for m in convo if m["from"] in own]
    theirs = [m for m in convo if m["from"] == h]

    note_text = (invite or {}).get("text") or ""
    # An accepted invitation's note shows up as your first message in the conversation
    if not invite and connected_on and mine and mine[0]["date"] <= connected_on:
        invite = {"date": mine[0]["date"], "text": mine[0]["text"]}
        note_text = mine[0]["text"]
    if invite:
        steps.append(("connect_sent", invite["date"], note_text or None, {"with_note": bool(note_text.strip())}))
    if connected_on:
        steps.append(("accepted", connected_on, None, {}))

    # Your messages, one per day (two in a row the same day are one message), minus the note
    sent = []
    for m in mine:
        if note_text and _norm(m["text"]) == _norm(note_text):
            continue
        if invite and m["date"] <= invite["date"] and not connected_on:
            continue
        if sent and sent[-1]["date"] == m["date"]:
            sent[-1]["text"] = (sent[-1]["text"] + "\n" + m["text"]).strip()
        else:
            sent.append(dict(m))
    reply = next((m for m in theirs if m["date"] >= ((invite or {}).get("date") or (sent[0]["date"] if sent else "9"))), None)

    for i, m in enumerate(sent):
        if reply and m["date"] > reply["date"]:
            break
        if i == 0:
            steps.append(("message_sent", m["date"], m["text"], {}))
        elif i <= schedule_len:
            steps.append((f"followup_{i}", m["date"], m["text"], {}))
    if reply:
        steps.append(("replied", reply["date"], None, {}))
    return steps


SAMPLE_FIELDS = {"connect_sent": "connect_note", "message_sent": "first_message"}


def sample_field(event, lang):
    suffix = "_he" if lang == "he" else ""
    if event in SAMPLE_FIELDS:
        return SAMPLE_FIELDS[event] + suffix
    if event.startswith("followup_"):
        return f"followups.{event.split('_')[1]}.text{suffix}"
    return None


# ---------------------------------------------------------------------------
# Applying it
# ---------------------------------------------------------------------------

def run(export_path, dry_run=False, with_samples=True):
    found = read_export(export_path)
    if not found:
        raise SystemExit("No Connections.csv, Invitations.csv or messages.csv in that export.")
    settings = st.load_settings()
    schedule_len = len(settings.get("followup_schedule_workdays") or [4, 5])
    connections, invitations, msgs, own = load_export(found, settings.get("sender_name"))

    print("Export: " + ", ".join(f"{k} ({len(v.splitlines())} lines)" for k, v in sorted(found.items())))
    missing = [FILES[k] for k in FILES if k not in found]
    if missing:
        print("Not in this export: " + ", ".join(missing) + " (request it next time for the full picture)")
    if found.get("messages") and not own:
        print("Couldn't tell which messages are yours: set sender_name in config/settings.json to your LinkedIn name.")

    ledger = st._read_json(LEDGER_FILE, {"samples": []})
    done_samples = set(ledger.get("samples") or [])
    changes, samples, touched, unmatched, tracked = [], [], set(), 0, 0

    with st.state_lock():
        entries = st.load_state()
        for e in entries:
            created = (e.get("created_at") or st.today_str())[:10]
            for t in e.get("outreach") or []:
                if t.get("channel") != "linkedin":
                    continue
                h = handle(t.get("profile"))
                if not h:
                    unmatched += 1
                    continue
                tracked += 1
                who = t.get("name") or h
                ev = t.setdefault("events", {})
                for event, when, text, extra in person_history(h, created, connections, invitations, msgs,
                                                                own, schedule_len):
                    if event == "already_connected":
                        if not t.get("connected") and not ev:
                            t["connected"] = True
                            changes.append(f"{e['company']} / {who}: already connected ({when})")
                            touched.add(e["slug"])
                        continue
                    lang = lang_of(text) if text else None
                    if not ev.get(event):
                        st.set_event(e, t["key"], event, when=when, lang=lang, with_note=extra.get("with_note"))
                        bits = [x for x in (lang and lang.upper(),
                                            {True: "with note", False: "no note"}.get(extra.get("with_note"))) if x]
                        changes.append(f"{e['company']} / {who}: {event} {when}"
                                       + (f" ({', '.join(bits)})" if bits else ""))
                        touched.add(e["slug"])
                    field = sample_field(event, lang) if text else None
                    sid = f"{e['slug']}|{t['key']}|{field}|{when}"
                    if with_samples and field and text.strip() and sid not in done_samples:
                        samples.append((when, e["slug"], t["key"], field, lang, text, sid))
        if not dry_run:
            st.save_state(entries)
            if with_samples and samples:
                from samples import record_sent
                for when, slug, key, field, lang, text, sid in sorted(samples):  # oldest first: newest ends on top
                    record_sent(slug, key, field, lang, text, when=when)
                    done_samples.add(sid)
            ledger.update(samples=sorted(done_samples), last_import=st.today_str(), export=str(export_path))
            st._write_json(LEDGER_FILE, ledger)
            if found.get("connections"):
                dest = Path(settings.get("connections_csv") or "config/Connections.csv")
                dest = dest if dest.is_absolute() else st.ROOT / dest
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(found["connections"], encoding="utf-8")

    verb = "Would record" if dry_run else "Recorded"
    print(f"\nChecked {tracked} tracked people ({unmatched} more have no LinkedIn link to match by).")
    if changes:
        print(f"{verb} {len(changes)} step{'s' if len(changes) != 1 else ''}:")
        for c in changes:
            print(f"  • {c}")
    else:
        print("Nothing new for the people you're tracking.")
    if with_samples:
        print(f"{'Would add' if dry_run else 'Added'} {len(samples)} sent message{'s' if len(samples) != 1 else ''} "
              "to your writing samples (only ones that differ from the draft become new samples).")
    if found.get("connections") and not dry_run:
        print(f"Connections: {len(connections)} copied for referrals (python3 scripts/referrals.py --all).")
    if not dry_run and touched:
        import generate_report as gr
        for slug in sorted(touched):
            gr.generate_report(slug)
        gr.generate_index()
        print(f"Reports updated for {len(touched)} application{'s' if len(touched) != 1 else ''}.")
    return changes


def main():
    parser = argparse.ArgumentParser(description="Catch up the tracking from your LinkedIn data export")
    parser.add_argument("export", help="The export zip LinkedIn emailed you, or the unzipped folder")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be recorded, change nothing")
    parser.add_argument("--no-samples", action="store_true", help="Don't add your sent texts to the writing samples")
    args = parser.parse_args()
    run(args.export, dry_run=args.dry_run, with_samples=not args.no_samples)


if __name__ == "__main__":
    main()
