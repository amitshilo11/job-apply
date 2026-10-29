#!/usr/bin/env python3
"""
samples.py — learn your writing style from what you actually send.

Every message you mark as sent is logged to state/sent_log.json. When the text you sent is
different from the draft (you edited it), or there was no draft at all, the sent version is
added to config/writing_samples.md under "## Learned from your edits". The drafting prompts
treat that section as the strongest signal of your voice.

The dashboard does this automatically: edit the text in the box, then click Sent. From the
command line (e.g. you edited the message inside LinkedIn and want to paste back what you sent):

  python3 scripts/samples.py add --slug acme --key hr --field connect_note_he --text "..."
  pbpaste | python3 scripts/samples.py add --slug acme --key lead --field first_message
  python3 scripts/samples.py list --limit 10

--field is the meta.json field the draft came from:
  connect_note, connect_note_he, first_message, first_message_he,
  followups.1.text, followups.1.text_he                (LinkedIn follow-up #1)
  email_draft.body, email_draft.body_he,
  email_draft.followups.1.body, email_draft.followups.1.body_he   (with --key email)
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from state import (ROOT, KIND_LABELS, NAME_SLOT, _read_json, _write_json, contact_keys, contact_kind,  # noqa: E402
                   find_entry, load_meta, load_settings, load_state, today_str)

SAMPLES_FILE = ROOT / "config" / "writing_samples.md"
LOG_FILE = ROOT / "state" / "sent_log.json"
LEARNED_HEADING = "## Learned from your edits"
LEARNED_INTRO = ("What you actually sent, after editing a draft or writing it yourself. Newest first.\n"
                 "These beat every other sample in this file: match their length, wording and tone.\n")


def find_contact(meta, key):
    contacts = (meta or {}).get("contacts") or []
    return next((c for c, k in zip(contacts, contact_keys(contacts)) if k == key), None)


def resolve_draft(meta, key, field):
    """The draft text behind a field path like 'followups.1.text_he', or None."""
    if not meta or not field:
        return None
    parts = field.split(".")
    if parts[0] == "email_draft":
        node, parts = meta.get("email_draft") or {}, parts[1:]
    elif key == "email":
        node = meta.get("email_draft") or {}
    else:
        node = find_contact(meta, key)
    for part in parts:
        if isinstance(node, list):
            node = next((x for x in node if str(x.get("n")) == part), None)
        elif isinstance(node, dict):
            node = node.get(part)
        else:
            return None
        if node is None:
            return None
    return node if isinstance(node, str) else None


def _norm(text):
    return re.sub(r"\s+", " ", text or "").strip()


def _same(draft, text):
    """The text is the draft as written, with a name in place of any {name}."""
    pattern = re.escape(_norm(draft)).replace(re.escape(NAME_SLOT), r"[^\s,.!?:]{1,40}(?: [^\s,.!?:]{1,40})?")
    return re.fullmatch(pattern, _norm(text)) is not None


def describe(field, key, lang, meta=None):
    base = (field or "").split(".")
    if base[0] == "email_draft" or key == "email":
        what = "email follow-up" if "followups" in base else "email"
    elif base[0].startswith("connect_note"):
        what = "connect note"
    elif base[0].startswith("first_message"):
        what = "first message"
    elif base[0] == "followups":
        what = "LinkedIn follow-up"
    else:
        what = "message"
    to = ""
    contact = find_contact(meta, key) if key != "email" else None
    if contact is not None:
        to = " · to " + KIND_LABELS.get(contact_kind(contact), "contact")
    return f"{what} ({(lang or '?').upper()}){to}"


def _split_learned(text):
    """(before, [sample blocks], after) for the learned-samples section of the file."""
    start = text.find(LEARNED_HEADING)
    if start == -1:
        return text.rstrip() + "\n\n", [], ""
    body_start = text.find("\n", start) + 1
    nxt = re.search(r"^## ", text[body_start:], flags=re.MULTILINE)
    end = body_start + nxt.start() if nxt else len(text)
    body = text[body_start:end]
    blocks = [b.strip() for b in re.split(r"^(?=### )", body, flags=re.MULTILINE) if b.strip().startswith("### ")]
    return text[:start], blocks, text[end:]


def add_learned_sample(title, text, max_samples):
    current = SAMPLES_FILE.read_text(encoding="utf-8") if SAMPLES_FILE.exists() else "# Writing Samples\n"
    before, blocks, after = _split_learned(current)
    blocks = [f"### {title}\n{text.strip()}"] + blocks
    blocks = blocks[:max_samples]
    section = LEARNED_HEADING + "\n\n" + LEARNED_INTRO + "\n" + "\n\n".join(blocks) + "\n"
    if after.strip():
        section += "\n"
    SAMPLES_FILE.parent.mkdir(parents=True, exist_ok=True)
    SAMPLES_FILE.write_text(before + section + after.lstrip("\n"), encoding="utf-8")


def record_sent(slug, key, field, lang, text, when=None):
    """Log a sent message and learn from it if it was edited.

    Returns "edited", "unchanged", "own" (no draft to compare), or None when there's no text.
    """
    text = (text or "").strip()
    if not text:
        return None
    when = when or today_str()
    meta = load_meta(slug)
    draft = resolve_draft(meta, key, field)
    if draft is None:
        result = "own"
    elif _same(draft, text):
        result = "unchanged"
    else:
        result = "edited"

    entry = find_entry(load_state(), slug) or {}
    company = entry.get("company") or (meta or {}).get("company") or slug
    log = _read_json(LOG_FILE, [])
    log.append({"date": when, "slug": slug, "company": company, "key": key, "field": field,
                "lang": lang, "result": result, "draft": draft, "sent": text})
    _write_json(LOG_FILE, log)

    if result in ("edited", "own"):
        max_samples = int(load_settings().get("learned_samples_max", 20))
        add_learned_sample(f"{when} · {company} · {describe(field, key, lang, meta)}", text, max_samples)
    return result


def cmd_add(args):
    text = args.text if args.text is not None else sys.stdin.read()
    lang = args.lang or ("he" if re.search(r"[֐-׿]", text or "") else "en")
    result = record_sent(args.slug, args.key, args.field, lang, text)
    if result is None:
        print("Nothing to record: the text is empty.", file=sys.stderr)
        sys.exit(1)
    messages = {
        "edited": "Saved. It differs from the draft, so it's now a writing sample.",
        "own": "Saved as a writing sample (no draft to compare with).",
        "unchanged": "Logged. Same as the draft, so the samples didn't change.",
    }
    print(messages[result])


def cmd_list(args):
    log = _read_json(LOG_FILE, [])
    if not log:
        print("Nothing logged yet.")
        return
    for item in log[-args.limit:]:
        mark = {"edited": "edited", "own": "own text", "unchanged": "as drafted"}.get(item.get("result"), "")
        print(f"{item['date']}  {item['company']:25s} {item.get('key', ''):10s} {item.get('field', ''):24s} "
              f"{(item.get('lang') or '').upper():3s} {mark}")


def main():
    parser = argparse.ArgumentParser(description="Learn your writing style from sent messages")
    sub = parser.add_subparsers(dest="command")
    p_add = sub.add_parser("add", help="Record a message you sent (text from --text or stdin)")
    p_add.add_argument("--slug", required=True)
    p_add.add_argument("--key", required=True, help="Thread key: hr, lead, email, referral-2...")
    p_add.add_argument("--field", required=True, help="Draft field, e.g. connect_note_he or followups.1.text")
    p_add.add_argument("--lang", choices=["en", "he"], help="Default: detected from the text")
    p_add.add_argument("--text")
    p_list = sub.add_parser("list", help="Show the sent log")
    p_list.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    if args.command == "add":
        cmd_add(args)
    elif args.command == "list":
        cmd_list(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
