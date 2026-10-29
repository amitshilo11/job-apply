#!/usr/bin/env python3
"""
check_messages.py — catch what makes a drafted message sound like AI, or just wrong.

Checks every message for an application (LinkedIn connect notes, first messages, follow-ups,
the email and its follow-ups) in every language it was drafted in.

Errors (fix before saving or sending):
  - connect note over the limit (connect_note_max_chars in config/settings.json, default 200)
  - generic AI phrases ("exactly the kind of challenge", "I'm excited to", "אשמח מאוד להזדמנות")
  - claims you never made ("been reading up on your research", "I've been following", "קראתי על")
  - saying an email or application was already sent when the state says it wasn't
  - the recipient's own email address in a message to them
  - talking about the recipient in third person (a message to Noa that says "I emailed Noa")
  - greeting a different name than the contact's, placeholders left in ([name], <company>)
  - dashes used as separators (" - ", "—"), bullet lists
  - a Hebrew field that isn't Hebrew, or an English field with Hebrew in it
Warnings (worth a look): long first messages and emails, lowercase "i" / "tbh" (not in your
samples), semicolons, a 5-word phrase that's also in 3+ other companies' messages.

Anything that appears in config/writing_samples.md is never flagged: if you wrote it, it's
your voice.

Usage:
  python3 scripts/check_messages.py <slug> [<slug> ...]
  python3 scripts/check_messages.py --all
  python3 scripts/check_messages.py <slug> --json
Exit code 1 when any message has an error.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import state as st  # noqa: E402
from generate_report import list_slugs, load_report_data  # noqa: E402

SAMPLES_FILE = st.ROOT / "config" / "writing_samples.md"

AI_PHRASES_EN = [
    "i'm excited", "i am excited", "excited to", "thrilled", "i'd love the opportunity", "love the opportunity",
    "i am writing to", "express my interest", "passionate", "please find attached", "look forward to hearing",
    "best regards", "kind regards", "came across your profile", "highly motivated", "great fit", "perfect fit",
    "please let me know if", "sounds like a really interesting", "really interesting problem",
    "interesting problem to work on", "unique problem space", "serious team", "exactly the kind of",
    "pick things up fast", "pick things up quickly", "fast learner", "quick learner", "worth a shot",
    "deep engineering problem", "fun challenge", "resonate", "impressed by", "impressive work", "amazing work",
    "cutting-edge", "cutting edge", "innovative", "game-changer", "game changer", "leverage", "delve", "synergy",
    "hope this message finds you", "hope you're doing well", "hope you are doing well", "dynamic team",
    "fast-paced", "thrive", "spearhead", "a testament to", "would be a great addition", "aligns perfectly",
    "align perfectly", "perfectly aligned", "eager to", "keen to learn", "i believe i would",
]
INVENTED_EN = [
    "been reading", "reading up on", "i read about", "i've been following", "been following", "i follow your",
    "been curious", "keeping an eye on", "kept an eye on", "your recent post", "your post about", "your talk",
    "saw your talk", "your podcast", "listened to your", "i've used your", "i use your product", "big fan of",
    "long-time fan", "for a while now",
]
AI_PHRASES_HE = [
    "אשמח מאוד להזדמנות", "נרגש", "נרגשת", "מוטיבציה גבוהה", "מצורף בזאת", "מצורפים בזאת",
    "אשמח לשמוע ממך בהקדם", "בברכה", "שלום רב", "לכבוד", "הריני", "מכובדיי", "נתקלתי בפרופיל שלך",
    "ניסיון עשיר", "תשוקה", "מלהיב", "מרתק", "בדיוק האתגר", "לומד מהר", "שווה ניסיון", "צוות רציני",
    "מעניינת במיוחד", "חדשני", "חדשנית", "פורץ דרך", "ההתאמה בתחום", "אוכל לתרום", "להוות חלק",
]
INVENTED_HE = [
    "קראתי על", "קראתי את", "עוקב אחרי", "עוקב אחריכם", "עקבתי אחרי", "סקרן אותי כבר", "כבר זמן מה",
    "ראיתי את ההרצאה", "שמעתי את הפודקאסט", "הפוסט שלך", "הפוסט האחרון", "אני משתמש במוצר",
]
FAKE_CASUAL = ["tbh", "honestly", "ngl", "lol"]
GENERIC_GREETINGS = {"team", "there", "all", "everyone", "folks", "צוות", "כולם", "לכולם", "חברים"}

HEB = re.compile(r"[֐-׿]")
LATIN = re.compile(r"[A-Za-z]")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
URL_RE = re.compile(r"https?://\S+")
GREETING_EN = re.compile(r"^\s*(?:hey|hi|hello|dear)[\s,]+([A-Za-z][\w'-]*)", re.IGNORECASE)
GREETING_HE = re.compile(r"^\s*(?:היי|הי|שלום|אהלן)[\s,]+([֐-׿][֐-׿'\"-]*)")
CLAIM_EN = re.compile(
    r"\b(?:sent|emailed|dropped|shot)\b[^.!?\n]{0,40}\b(?:email|e-mail|mail|note|cv|resume|application|inbox)\b"
    r"|\bapplied\b[^.!?\n]{0,30}\b(?:through|via|on|online)\b"
    r"|\byour (?:careers|jobs|hr) (?:email|inbox|address)\b", re.IGNORECASE)
CLAIM_HE = re.compile(r"(?:שלחתי|הגשתי|שלחנו)[^.!?\n]{0,30}(?:מייל|מועמדות|קו\"ח|קו״ח|קורות חיים)|הגשתי מועמדות")
PLACEHOLDER_RE = re.compile(r"\[[^\]\n]{1,40}\]|<[^>\n]{1,40}>|\{[^}\n]{1,40}\}|\bTODO\b|\bXXX\b|\bnot found\b",
                            re.IGNORECASE)
LOWER_I = re.compile(r"(?<![\w'’])i(?=[\s,.!?'’]|$)")


def load_samples_text():
    """Your writing samples as written (case matters for the lowercase-"i" check)."""
    try:
        return SAMPLES_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def iter_messages(data):
    """Every drafted message as dicts: key, field, kind, lang, text, contact."""
    contacts = data.get("contacts") or []
    for c, key in zip(contacts, st.contact_keys(contacts)):
        if key is None:
            continue
        for base in ("connect_note", "first_message"):
            for lang, suffix in (("en", ""), ("he", "_he")):
                text = c.get(base + suffix)
                if text and text.strip().lower() != "not found":
                    yield {"key": key, "field": base + suffix, "kind": base, "lang": lang, "text": text, "contact": c}
        for f in c.get("followups") or []:
            for lang, fld in (("en", "text"), ("he", "text_he")):
                if f.get(fld):
                    yield {"key": key, "field": f"followups.{f.get('n')}.{fld}", "kind": "followup",
                           "lang": lang, "text": f[fld], "contact": c}
    draft = data.get("email_draft") or {}
    for lang, fld in (("en", "body"), ("he", "body_he")):
        if draft.get(fld):
            yield {"key": "email", "field": f"email_draft.{fld}", "kind": "email", "lang": lang,
                   "text": draft[fld], "contact": None}
    for f in draft.get("followups") or []:
        for lang, fld in (("en", "body"), ("he", "body_he")):
            if f.get(fld):
                yield {"key": "email", "field": f"email_draft.followups.{f.get('n')}.{fld}", "kind": "email_followup",
                       "lang": lang, "text": f[fld], "contact": None}


def snippet(text, start, end, pad=28):
    a, b = max(0, start - pad), min(len(text), end + pad)
    return ("…" if a else "") + text[a:b].replace("\n", " ") + ("…" if b < len(text) else "")


def _words(text):
    return re.findall(r"[\w'’֐-׿]+", text.lower())


def shingles(text, n=5):
    w = _words(text)
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


def repeated_spans(text, counts, skip, n=5):
    """Longest runs of words whose every 5-word window shows up in 3+ other companies' messages."""
    w = _words(text)
    hits = [i for i in range(len(w) - n + 1)
            if counts.get(" ".join(w[i:i + n]), 0) >= 3 and not skip(" ".join(w[i:i + n]))]
    spans, start, prev = [], None, None
    for i in hits:
        if start is None:
            start = prev = i
        elif i == prev + 1:
            prev = i
        else:
            spans.append((start, prev))
            start = prev = i
    if start is not None:
        spans.append((start, prev))
    return [(" ".join(w[a:b + n]), max(counts[" ".join(w[j:j + n])] for j in range(a, b + 1))) for a, b in spans]


def phrase_counts(exclude_slug):
    """For each 5-word phrase, how many other companies' messages use it."""
    counts = {}
    for slug in list_slugs():
        if slug == exclude_slug:
            continue
        try:
            data = load_report_data(slug)
        except Exception:
            continue
        seen = set()
        for m in iter_messages(data):
            seen |= shingles(m["text"])
        for s in seen:
            counts[s] = counts.get(s, 0) + 1
    return counts


def _name_pattern(name, hebrew):
    if hebrew:
        return re.compile(r"(?<![֐-׿])[להבשומכ]?" + re.escape(name) + r"(?![֐-׿])")
    return re.compile(r"(?<![\w])" + re.escape(name) + r"(?![\w])", re.IGNORECASE)


def check_message(m, ctx, settings, samples_raw, counts):
    issues = []
    text, lang, kind = m["text"], m["lang"], m["kind"]
    low = text.lower()
    samples = samples_raw.lower()

    def add(level, msg):
        issues.append({"level": level, "message": msg})

    # Language of the field
    heb, lat = len(HEB.findall(text)), len(LATIN.findall(text))
    if lang == "he" and heb < 0.5 * (heb + lat):
        add("error", "the Hebrew version is mostly not Hebrew")
    if lang == "en" and heb:
        add("error", "the English version has Hebrew in it")

    # Length
    limit = int(settings.get("connect_note_max_chars", 200))
    words = len(_words(text))
    if kind == "connect_note" and len(text) > limit:
        add("error", f"connect note is {len(text)} characters, the limit is {limit}")
    elif kind == "first_message" and words > 120:
        add("error", f"first message is {words} words, keep it under 80")
    elif kind == "first_message" and words > 80:
        add("warning", f"first message is {words} words, aim for under 80")
    elif kind in ("followup", "email_followup") and words > 60:
        add("warning", f"follow-up is {words} words, keep follow-ups short")
    elif kind == "email" and words > 220:
        add("error", f"email is {words} words, keep it under 150")
    elif kind == "email" and words > 150:
        add("warning", f"email is {words} words, aim for under 150")

    # Text with the job title and links taken out, for the punctuation checks
    stripped = URL_RE.sub(" ", text)
    for title in ctx["titles"]:
        stripped = stripped.replace(title, " ")
    for match in re.finditer(r"[—–]| - ", stripped):
        add("error", f"dash used as a separator: \"{snippet(stripped, match.start(), match.end())}\"")
        break
    if re.search(r"^\s*[-•*]\s", text, flags=re.MULTILINE):
        add("error", "bullet list in a message")
    if ";" in stripped:
        add("warning", "semicolon: use a comma or a new sentence")

    for match in PLACEHOLDER_RE.finditer(text):
        add("error", f"placeholder left in: \"{match.group(0)}\"")

    # Phrases
    phrase_lists = ((AI_PHRASES_EN, "generic AI phrase"), (INVENTED_EN, "claims something you didn't do")) \
        if lang == "en" else ((AI_PHRASES_HE, "generic AI phrase"), (INVENTED_HE, "claims something you didn't do"))
    flagged = []  # spans already reported, so overlapping phrases give one error
    for phrases, label in phrase_lists:
        for p in phrases:
            idx = low.find(p)
            if idx == -1 or p in samples:
                continue
            end = idx + len(p)
            if any(idx < b and end > a for a, b in flagged):
                continue
            flagged.append((idx, end))
            add("error", f"{label}: \"{snippet(text, idx, end)}\"")
    if lang == "en":
        if LOWER_I.search(text) and not LOWER_I.search(samples_raw):
            add("warning", "lowercase \"i\": your own messages write \"I\"")
        for p in FAKE_CASUAL:
            if re.search(r"\b" + p + r"\b", low) and not re.search(r"\b" + p + r"\b", samples):
                add("warning", f"\"{p}\" isn't something you write")

    # Claims that something was already sent
    claim = (CLAIM_EN if lang == "en" else CLAIM_HE).search(text)
    if claim and kind not in ("email", "email_followup"):
        if not (ctx["email_sent"] or ctx["applied"]):
            add("error", f"says something was already sent, but it wasn't: \"{snippet(text, claim.start(), claim.end())}\"")

    # Email addresses in LinkedIn messages
    contact = m.get("contact") or {}
    name = (contact.get("name") or "").strip()
    first_en = name.split()[0] if name else ""
    last_en = name.split()[-1] if len(name.split()) > 1 else ""
    if kind not in ("email", "email_followup"):
        for addr in EMAIL_RE.findall(text):
            local = addr.split("@")[0].lower()
            if any(part and len(part) > 2 and part.lower() in local for part in (first_en, last_en)):
                add("error", f"mentions {addr}, which is the recipient's own email")
            else:
                add("warning", f"has an email address ({addr}); LinkedIn messages rarely need one")

    # Greeting and third person
    greet = (GREETING_EN if lang == "en" else GREETING_HE).match(text)
    greeted = greet.group(1).strip("!,.:") if greet else ""
    expected = contact.get("name_he") if lang == "he" else first_en
    if greeted and greeted.lower() not in GENERIC_GREETINGS:
        if expected and greeted.lower() != expected.lower():
            add("error", f"greets \"{greeted}\" but the contact is {name or expected}")
        rest = text[greet.end():]
        if _name_pattern(greeted, lang == "he").search(rest):
            hit = _name_pattern(greeted, lang == "he").search(rest)
            add("error", f"talks about {greeted} in third person in a message to them: "
                         f"\"{snippet(rest, hit.start(), hit.end())}\"")
    elif expected and kind != "email":
        hit = _name_pattern(expected, lang == "he").search(text)
        if hit and hit.start() > 15:
            add("error", f"mentions {expected} by name mid-message; is it written to them? "
                         f"\"{snippet(text, hit.start(), hit.end())}\"")

    # The same phrase across many companies reads like a template
    if counts:
        def skip(s):
            return s in samples or any(s in t.lower() for t in ctx["titles"])
        for phrase, n in repeated_spans(text, counts, skip)[:2]:
            add("warning", f"\"{phrase}\" is also in {n} other companies' messages (reads like a template)")
    return issues


def check_slug(slug, settings, samples, with_repeats=True):
    data = load_report_data(slug)
    entry = st.find_entry(st.load_state(), slug) or {}
    email = st.get_thread(entry, "email") or {}
    ctx = {
        "email_sent": bool((email.get("events") or {}).get("sent")) or entry.get("status") == "sent",
        "applied": bool((entry.get("tasks") or {}).get("applied")),
        "titles": [t for t in {entry.get("job_title"), data.get("job_title"), data.get("best_fit")} if t],
    }
    counts = phrase_counts(slug) if with_repeats else {}
    results = []
    for m in iter_messages(data):
        for issue in check_message(m, ctx, settings, samples, counts):
            results.append(dict(issue, key=m["key"], field=m["field"], lang=m["lang"]))
    return entry.get("company") or data.get("company") or slug, results


FIELD_LABELS = {"connect_note": "connect note", "first_message": "first message"}


def field_label(field):
    base = field.split(".")[0].replace("_he", "")
    if field.startswith("email_draft.followups"):
        return "email follow-up #" + field.split(".")[2]
    if field.startswith("email_draft"):
        return "email"
    if base == "followups":
        return "follow-up #" + field.split(".")[1]
    return FIELD_LABELS.get(base, base)


def main():
    parser = argparse.ArgumentParser(description="Check drafted messages for AI tells and mistakes")
    parser.add_argument("slugs", nargs="*")
    parser.add_argument("--all", action="store_true", help="Check every application")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-repeats", action="store_true", help="Skip the cross-company repeated-phrase check")
    args = parser.parse_args()
    slugs = list_slugs() if args.all else args.slugs
    if not slugs:
        parser.print_help()
        sys.exit(2)

    settings = st.load_settings()
    samples = load_samples_text()
    report, total_errors = {}, 0
    for slug in sorted(slugs):
        company, results = check_slug(slug, settings, samples, with_repeats=not args.no_repeats)
        report[slug] = {"company": company, "issues": results}
        total_errors += sum(1 for r in results if r["level"] == "error")

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        for slug, item in report.items():
            issues = item["issues"]
            errors = sum(1 for r in issues if r["level"] == "error")
            if not issues:
                print(f"✓ {item['company']} ({slug}): no problems")
                continue
            print(f"{item['company']} ({slug}): {errors} error{'s' if errors != 1 else ''}, "
                  f"{len(issues) - errors} warning{'s' if len(issues) - errors != 1 else ''}")
            for r in issues:
                mark = "✗" if r["level"] == "error" else "⚠"
                print(f"  {mark} {r['key']} · {field_label(r['field'])} ({r['lang'].upper()}): {r['message']}")
    sys.exit(1 if total_errors else 0)


if __name__ == "__main__":
    main()
