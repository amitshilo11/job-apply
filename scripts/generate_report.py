#!/usr/bin/env python3
"""
generate_report.py — Build the HTML pages for processed applications.

  output/<slug>/report.html   one role: role card, people + messages, email, CV, interview prep
  output/index.html           dashboard: Today list, stats, every application

Opened through the dashboard server (`python3 scripts/serve.py`, http://localhost:8765) the
buttons save straight to state/applications.json. Opened from disk the pages are read-only:
copying messages works, saving clicks doesn't.

Usage:
  python3 scripts/generate_report.py <slug>
  python3 scripts/generate_report.py --all
"""

import json
import os
import re
import sys
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import state as st  # noqa: E402
from samples import resolve_draft  # noqa: E402

ROOT = str(st.ROOT)
LINKEDIN_GEO_ISRAEL = "101620260"


def read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


def load_settings():
    return st.load_settings()


def get_state(slug):
    return st.find_entry(st.load_state(), slug) or {}


# ---------------------------------------------------------------------------
# Legacy markdown parsing (output folders written before meta.json existed)
# ---------------------------------------------------------------------------

def parse_research(content):
    result = {
        "website": None,
        "careers_url": None,
        "best_fit": None,
        "apply_url": None,
        "fit_notes": [],
        "email": None,
    }
    if not content:
        return result
    in_fit_notes = False
    for line in content.splitlines():
        s = line.strip()
        # Enter fit notes section on "Fit notes:" heading
        if re.match(r"^Fit notes", s, re.IGNORECASE):
            in_fit_notes = True
            continue
        # Exit fit notes section on next heading-like line (e.g. "Recruiter:")
        if in_fit_notes and s and not s.startswith("+") and not s.startswith("-") and not s.startswith("---"):
            if re.match(r"^[A-Z][A-Za-z ]+:", s):
                in_fit_notes = False

        if s.startswith("Website:"):
            result["website"] = s[len("Website:"):].strip()
        elif s.startswith("Careers page:"):
            result["careers_url"] = s[len("Careers page:"):].strip()
        elif s.startswith("Best fit:"):
            result["best_fit"] = s[len("Best fit:"):].strip()
        elif s.startswith("Apply here:") or s.startswith("Apply via"):
            urls = re.findall(r"https?://\S+", s)
            if urls:
                result["apply_url"] = urls[0].rstrip(")")
        elif s.startswith("Contact email:"):
            result["email"] = s[len("Contact email:"):].strip()
        elif in_fit_notes and (s.startswith("+") or s.startswith("-")) and len(s) > 2:
            result["fit_notes"].append(s)
    return result


# "Connect note (HE, ≤300 chars):" / "First message (EN, after accepting):" / legacy unlabelled
MSG_LABEL_RE = re.compile(r"^(Connect note|First message)([^\n:]*):[ \t]*$", re.MULTILINE | re.IGNORECASE)
HEBREW_LABEL_RE = re.compile(r"\b(he|heb|hebrew)\b|עברית", re.IGNORECASE)
# Section heading that starts the Hebrew half of an email draft
HEBREW_SECTION_RE = re.compile(r"^##[ \t]*(?:hebrew|he|עברית)\b.*$", re.MULTILINE | re.IGNORECASE)


def parse_msg_blocks(body):
    """Map (kind, lang) -> text for the labelled message blocks in a contact section.

    kind is "connect_note" or "first_message"; lang is "en" or "he", read from the
    parenthetical on the label line. Unlabelled blocks (older files) count as English.
    """
    blocks = {}
    matches = list(MSG_LABEL_RE.finditer(body))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        chunk = re.split(r"^[ \t]*(?:---|##)", body[m.end():end], flags=re.MULTILINE)[0].strip()
        if not chunk or chunk.lower() == "not found":
            continue
        kind = "connect_note" if m.group(1).lower().startswith("connect") else "first_message"
        lang = "he" if HEBREW_LABEL_RE.search(m.group(2)) else "en"
        blocks.setdefault((kind, lang), chunk)
    return blocks


def parse_linkedin(content):
    contacts = []
    if not content:
        return contacts
    sections = re.split(r"^## ", content, flags=re.MULTILINE)
    for section in sections[1:]:
        lines = section.strip().splitlines()
        if not lines:
            continue
        title = lines[0].strip()
        if title.lower().startswith("notes"):
            continue
        body = "\n".join(lines[1:])
        contact = {"title": title, "profile": None, "job_title": None,
                   "connect_note": None, "connect_note_he": None,
                   "first_message": None, "first_message_he": None}

        m = re.search(r"Profile:\s*(https?://\S+)", body)
        if m:
            contact["profile"] = m.group(1).rstrip(")")

        m = re.search(r"^(?:Title|Company):\s*(.+)", body, re.MULTILINE)
        if m:
            contact["job_title"] = m.group(1).strip()

        blocks = parse_msg_blocks(body)
        contact["connect_note"] = blocks.get(("connect_note", "en"))
        contact["connect_note_he"] = blocks.get(("connect_note", "he"))
        contact["first_message"] = blocks.get(("first_message", "en"))
        contact["first_message_he"] = blocks.get(("first_message", "he"))

        contacts.append(contact)
    return contacts


def parse_email_section(text):
    result = {"to": None, "subject": None, "body": None, "attachment": None}
    in_body = False
    body_lines = []
    for line in text.splitlines():
        s = line.strip()
        if not in_body:
            if s.startswith("To:"):
                result["to"] = s[3:].strip()
            elif s.startswith("Subject:"):
                result["subject"] = s[8:].strip()
            elif s == "Body:":
                in_body = True
            continue
        if s.startswith("Attachment:"):
            result["attachment"] = s[len("Attachment:"):].strip()
            continue
        body_lines.append(line)
    if in_body:
        result["body"] = "\n".join(body_lines).strip() or None
    return result


def parse_email(content):
    """Parse email.md / followup_email.md, including the optional '## Hebrew' half."""
    if not content:
        return None
    halves = HEBREW_SECTION_RE.split(content, maxsplit=1)
    result = parse_email_section(halves[0])
    result["subject_he"] = None
    result["body_he"] = None
    if len(halves) > 1:
        tail = halves[1]
        if re.search(r"^[ \t]*Body:[ \t]*$", tail, re.MULTILINE):
            hebrew = parse_email_section(tail)
        else:
            # No "Body:" marker — the whole section is the body
            hebrew = {"subject": None, "body": tail.strip() or None}
        result["subject_he"] = hebrew.get("subject")
        result["body_he"] = hebrew.get("body")
    return result


def load_report_data(slug):
    """Everything known about one application, preferring output/<slug>/meta.json."""
    out_dir = os.path.join(ROOT, "output", slug)
    meta = st.load_meta(slug)
    if meta:
        data = dict(meta)
        data.setdefault("contacts", [])
        data.setdefault("fit_notes", [])
    else:
        research = parse_research(read_file(os.path.join(out_dir, "research.md")))
        data = dict(research)
        data["contacts"] = parse_linkedin(read_file(os.path.join(out_dir, "linkedin.md")))
        data["email_draft"] = parse_email(read_file(os.path.join(out_dir, "email.md")))
        data["legacy"] = True
    # A follow-up email drafted before follow-ups moved into meta.json
    legacy_followup = parse_email(read_file(os.path.join(out_dir, "followup_email.md")))
    if legacy_followup and (legacy_followup.get("body") or legacy_followup.get("body_he")):
        data["legacy_followup_email"] = legacy_followup
    return data


# ---------------------------------------------------------------------------
# Small HTML helpers
# ---------------------------------------------------------------------------

STAGE_BADGE = {
    "applied": ("badge-blue", "Applied"),
    "replied": ("badge-indigo", "Replied"),
    "interview": ("badge-amber", "Interview"),
    "offer": ("badge-green", "Offer"),
    "rejected": ("badge-red", "Rejected"),
    "ghosted": ("badge-gray", "No answer"),
    "withdrawn": ("badge-gray", "Not interested"),
}
VERDICT_BADGE = {
    "strong": ("badge-green", "Strong fit"),
    "good": ("badge-blue", "Good fit"),
    "long shot": ("badge-amber", "Long shot"),
    "skip": ("badge-red", "Skip"),
}
CONFIDENCE_BADGE = {"high": "badge-green", "medium": "badge-amber", "low": "badge-red"}
LANG_NAMES = {"en": "EN", "he": "HE"}


def esc(text):
    if text is None:
        return ""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def attrs_html(attrs):
    return " ".join(f'{k}="{esc(v)}"' for k, v in attrs.items() if v is not None)


def button(label, attrs, cls="btn"):
    """A button that saves something: dimmed with a hint when the page isn't served."""
    return f'<button class="{cls} needs-server" {attrs_html(attrs)}>{esc(label)}</button>'


def ev_btn(label, slug, key, event, lang=None, note=None, box=None, field=None, undo=False, cls="btn"):
    return button(label, {
        "data-act": "event", "data-slug": slug, "data-key": key, "data-event": event,
        "data-lang": lang, "data-note": None if note is None else ("1" if note else "0"),
        "data-box": box, "data-field": field, "data-undo": "1" if undo else None,
    }, cls)


def badge(cls, label):
    return f'<span class="badge {cls}">{esc(label)}</span>'


def fmt_date(value):
    return esc(value) if value else ""


def languages(settings, *texts_by_lang):
    """Languages to show, in message_languages order, plus any extra that has text."""
    order = [lang for lang in settings.get("message_languages") or ["en", "he"] if lang in LANG_NAMES]
    present = set()
    for mapping in texts_by_lang:
        present.update(lang for lang, text in mapping.items() if text)
    return [lang for lang in order if lang in present] + sorted(present - set(order))


def msg_box(box_id, text, lang, buttons_html="", limit=None):
    """One editable, copyable message in one language."""
    rtl = lang == "he"
    dir_attr = ' dir="rtl"' if rtl else ""
    count = ""
    if limit:
        n = len(text or "")
        over = " over" if n > limit else ""
        count = f'<span class="count{over}" data-limit="{limit}">{n}/{limit}</span>'
    return (f'<div class="msg{" rtl" if rtl else ""}">'
            f'<div class="msg-top"><span class="lang-tag">{LANG_NAMES.get(lang, lang.upper())}</span>{count}</div>'
            f'<div class="msg-text" id="{esc(box_id)}"{dir_attr} data-editable>{esc(text)}</div>'
            f'<div class="msg-actions"><button class="btn btn-light" data-act="copy" data-box="{esc(box_id)}">Copy</button>'
            f'{buttons_html}</div></div>')


def hidden_text(box_id, text):
    return f'<div class="msg-text" id="{esc(box_id)}" hidden>{esc(text)}</div>'


def linkedin_search_links(company, settings):
    """One-click LinkedIn people searches (Israel only) to check or replace a contact."""
    def people(query):
        return ("https://www.linkedin.com/search/results/people/?keywords=" + quote(query)
                + "&geoUrn=" + quote(f'["{LINKEDIN_GEO_ISRAEL}"]'))
    terms = settings.get("linkedin_search_terms") or ["team lead", "engineering manager"]
    leads = " OR ".join(f'"{t}"' for t in terms)
    return [
        ("Recruiters", people(f'"{company}" (recruiter OR "talent acquisition" OR גיוס)')),
        ("Mobile / Android leads", people(f'"{company}" ({leads})')),
        ("Everyone there in Israel", people(f'"{company}"')),
    ]


# ---------------------------------------------------------------------------
# Shared CSS / JS
# ---------------------------------------------------------------------------

BASE_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;background:#f5f5f7;color:#1d1d1f;line-height:1.55;padding:1.5rem 1rem 4rem}
a{color:#0071e3}
.container{max-width:920px;margin:0 auto}
.card{background:#fff;border-radius:14px;padding:1.4rem 1.5rem;margin-bottom:1.25rem;box-shadow:0 1px 4px rgba(0,0,0,.07)}
h1{font-size:1.7rem;font-weight:700;line-height:1.2}
h3{font-size:1rem;font-weight:600}
h4{font-size:.78rem;font-weight:700;color:#6e6e73;text-transform:uppercase;letter-spacing:.06em;margin:.2rem 0 .4rem}
.section-title{font-size:.78rem;font-weight:700;color:#6e6e73;text-transform:uppercase;letter-spacing:.08em;margin-bottom:1rem;padding-bottom:.5rem;border-bottom:1px solid #f0f0f0;display:flex;justify-content:space-between;align-items:center;gap:.5rem}
.meta{color:#6e6e73;font-size:.88rem}
.badge{display:inline-block;padding:.18rem .6rem;border-radius:20px;font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.04em;vertical-align:middle;white-space:nowrap}
.badge-green{background:#d1fae5;color:#065f46}.badge-blue{background:#dbeafe;color:#1e40af}
.badge-indigo{background:#e0e7ff;color:#3730a3}.badge-amber{background:#fef3c7;color:#92400e}
.badge-red{background:#fee2e2;color:#991b1b}.badge-gray{background:#f3f4f6;color:#374151}
.btn{display:inline-flex;align-items:center;gap:.3rem;border:1px solid #0071e3;background:#0071e3;color:#fff;border-radius:8px;padding:.3rem .7rem;font-size:.78rem;font-weight:600;cursor:pointer;text-decoration:none;white-space:nowrap;font-family:inherit}
.btn:hover{background:#005bbf}
.btn-light{background:#fff;color:#0071e3}.btn-light:hover{background:#eef5ff}
.btn-quiet{background:#fff;color:#6e6e73;border-color:#d1d1d6}.btn-quiet:hover{background:#f5f5f7;color:#1d1d1f}
.btn-green{background:#059669;border-color:#059669}.btn-green:hover{background:#047857}
.btn.copied{background:#059669;border-color:#059669;color:#fff}
.btn-undo{background:none;border:none;color:#8e8e93;font-size:.75rem;cursor:pointer;text-decoration:underline;padding:0 .2rem;font-family:inherit}
body.offline .needs-server{opacity:.45}
.offline-banner{display:none;background:#fffbeb;border:1px solid #fde68a;color:#92400e;border-radius:12px;padding:.8rem 1rem;margin-bottom:1.25rem;font-size:.88rem}
body.offline .offline-banner{display:flex;gap:.6rem;align-items:center;flex-wrap:wrap}
.offline-banner code,code{background:#f0f0f5;color:#1d1d1f;padding:.1rem .4rem;border-radius:5px;font-size:.82rem}
.msg{background:#f5f5f7;border-radius:10px;padding:.6rem .8rem;margin-top:.5rem}
.msg-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:.25rem}
.lang-tag{font-size:.62rem;font-weight:800;letter-spacing:.06em;color:#6e6e73;background:#e5e5ea;border-radius:4px;padding:.05rem .4rem}
.count{font-size:.7rem;color:#8e8e93}.count.over{color:#dc2626;font-weight:700}
.msg-text{white-space:pre-wrap;font-size:.9rem;outline:none;border-radius:6px;padding:.1rem .15rem}
.msg-text[contenteditable]:focus{background:#fff;box-shadow:0 0 0 2px #bfdbfe}
.msg.rtl .msg-text{direction:rtl;text-align:right}
.msg-actions{display:flex;gap:.4rem;flex-wrap:wrap;margin-top:.5rem}
.skipped-note{color:#6e6e73;font-style:italic;font-size:.88rem}
.back-link{display:inline-block;text-decoration:none;font-size:.88rem;margin-bottom:1rem}
.chips{display:flex;flex-wrap:wrap;gap:.3rem;margin-top:.3rem}
.chip{font-size:.75rem;background:#f0f0f5;border-radius:6px;padding:.1rem .45rem}
.chip.have{background:#d1fae5;color:#065f46}.chip.missing{background:#fee2e2;color:#991b1b}
"""

REPORT_CSS = """
.head-top{display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;flex-wrap:wrap}
.head-badges{display:flex;gap:.35rem;flex-wrap:wrap}
.role-link{font-weight:600;text-decoration:none}
.role-link:hover{text-decoration:underline}
.links-row{display:flex;gap:.5rem;flex-wrap:wrap;margin-top:.8rem}
.next-box{background:#f5f9ff;border:1px solid #dbeafe;border-radius:10px;padding:.65rem .85rem;margin-top:.9rem;font-size:.88rem}
.next-box ul{list-style:none}.next-box li{padding:.1rem 0}
.next-box .due{color:#6e6e73;font-size:.8rem}.next-box .overdue{color:#b91c1c;font-size:.8rem;font-weight:600}
.stage-row{display:flex;gap:.4rem;flex-wrap:wrap;align-items:center;margin-top:.9rem;font-size:.82rem;color:#6e6e73}
.verdict{border-radius:10px;padding:.7rem .9rem;font-size:.95rem;margin-bottom:1rem}
.verdict strong{margin-right:.4rem}
.verdict.badge-green,.verdict.badge-blue,.verdict.badge-amber,.verdict.badge-red,.verdict.badge-gray{text-transform:none;letter-spacing:0;font-weight:500;display:block;font-size:.92rem}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:1.25rem;margin-bottom:1rem}
@media (max-width:640px){.two-col{grid-template-columns:1fr}}
.facts{display:grid;grid-template-columns:auto 1fr;gap:.15rem .7rem;font-size:.85rem;margin-top:.5rem}
.facts dt{color:#6e6e73}
.facts dd{margin:0}
.warn{color:#b45309;font-size:.85rem;margin-top:.4rem}
.list{list-style:none;display:flex;flex-direction:column;gap:.2rem;font-size:.9rem}
.list.pro li::before{content:"✓  ";color:#059669;font-weight:700}
.list.con li::before{content:"✗  ";color:#dc2626;font-weight:700}
.sources{font-size:.78rem;color:#8e8e93;margin-top:.6rem;word-break:break-all}
.contact{border:1px solid #e5e5ea;border-radius:12px;padding:1rem 1.1rem;margin-bottom:1rem}
.contact.missing{background:#fafafa}
.contact-head{display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap}
.contact-kind{font-size:.7rem;font-weight:800;color:#6e6e73;text-transform:uppercase;letter-spacing:.07em}
.contact-sub{font-size:.85rem;color:#6e6e73}
.why{font-size:.84rem;margin-top:.25rem}
.thread-status{font-size:.82rem;max-width:300px;text-align:right}
.thread-status .label{display:block;color:#1d1d1f;font-weight:600}
.thread-controls{display:flex;gap:.4rem;flex-wrap:wrap;justify-content:flex-end;margin-top:.4rem}
.step{margin-top:.9rem;border-top:1px dashed #e5e5ea;padding-top:.7rem}
.step-label{font-size:.75rem;font-weight:800;color:#6e6e73;text-transform:uppercase;letter-spacing:.05em;display:flex;align-items:center;gap:.5rem;flex-wrap:wrap}
.step.active .step-label{color:#0071e3}
.step.done .step-label{color:#059669}
.step.later{opacity:.6}
.done-line{font-size:.82rem;color:#065f46;margin-top:.3rem}
.hint{font-size:.8rem;color:#6e6e73;margin-top:.35rem}
details.alternates{margin-top:.8rem;font-size:.85rem}
details.alternates summary{cursor:pointer;color:#0071e3}
details.alternates li{margin:.35rem 0 0 1rem}
.search-links{display:flex;gap:.5rem;flex-wrap:wrap;align-items:center;font-size:.82rem;color:#6e6e73;margin-top:.5rem}
.known{font-size:.88rem;margin-bottom:1rem;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:.7rem .9rem}
.known li{margin-left:1rem}
.email-head{display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap;font-size:.86rem;color:#6e6e73}
.pdf-frame{width:100%;height:640px;border:1px solid #e5e5ea;border-radius:8px;margin-top:.75rem}
.timeline{list-style:none;font-size:.85rem}
.timeline li{padding:.2rem 0;border-bottom:1px solid #f5f5f7}
.timeline .d{color:#8e8e93;display:inline-block;width:6.5rem}
.prep-q{margin-bottom:.6rem;font-size:.9rem}
.prep-q .why{color:#6e6e73}
"""

INDEX_CSS = """
.top{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:.5rem;margin-bottom:1.25rem}
.subtitle{color:#6e6e73;font-size:.88rem}
.group-title{font-size:.72rem;font-weight:800;text-transform:uppercase;letter-spacing:.07em;color:#6e6e73;margin:1rem 0 .4rem}
.group-title:first-child{margin-top:0}
.today-item{display:flex;justify-content:space-between;gap:.75rem;flex-wrap:wrap;padding:.6rem 0;border-bottom:1px solid #f0f0f0}
.today-item:last-child{border-bottom:none}
.ti-company{font-weight:700;text-decoration:none;color:#1d1d1f}
.ti-company:hover{text-decoration:underline}
.ti-who{color:#6e6e73;font-size:.85rem}
.ti-action{font-size:.9rem}
.ti-buttons{display:flex;gap:.35rem;flex-wrap:wrap;align-items:center}
.due-pill{display:inline-block;font-size:.7rem;font-weight:700;border-radius:20px;padding:.05rem .5rem;margin-left:.3rem;background:#f3f4f6;color:#374151}
.due-pill.overdue{background:#fee2e2;color:#991b1b}
.upcoming{list-style:none;font-size:.85rem;color:#3a3a3c}
.upcoming li{padding:.15rem 0}
.upcoming .d{color:#8e8e93;display:inline-block;width:6.5rem}
.footnote{font-size:.8rem;color:#6e6e73;margin-top:.8rem}
.stats{width:100%;border-collapse:collapse;font-size:.85rem}
.stats th{text-align:right;font-size:.7rem;color:#6e6e73;text-transform:uppercase;letter-spacing:.05em;padding:.3rem .5rem;font-weight:700}
.stats th:first-child,.stats td:first-child{text-align:left}
.stats td{text-align:right;padding:.25rem .5rem;border-top:1px solid #f5f5f7}
.stats tr.sep td{border-top:2px solid #e5e5ea}
.tab-bar{display:flex;margin:1.5rem 0 1rem;border-bottom:2px solid #e5e5ea;flex-wrap:wrap}
.tab{background:none;border:none;padding:.55rem 1rem;font-size:.9rem;font-weight:600;color:#6e6e73;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-2px;font-family:inherit}
.tab.active{color:#1d1d1f;border-bottom-color:#0071e3}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:1rem}
.app-card{background:#fff;border-radius:14px;padding:1.1rem 1.15rem;text-decoration:none;color:inherit;box-shadow:0 1px 4px rgba(0,0,0,.07);display:block;position:relative;transition:box-shadow .15s,transform .15s}
.app-card:hover{box-shadow:0 4px 14px rgba(0,0,0,.12);transform:translateY(-2px)}
.app-company{font-size:1.02rem;font-weight:700;padding-right:1.5rem}
.app-role{font-size:.82rem;color:#6e6e73;margin:.1rem 0 .6rem}
.app-badges{display:flex;gap:.3rem;flex-wrap:wrap}
.app-next{font-size:.8rem;margin-top:.6rem;color:#3a3a3c}
.app-next.overdue{color:#b91c1c;font-weight:600}
.close-x{position:absolute;top:.55rem;right:.6rem;background:none;border:none;color:#c7c7cc;font-size:1rem;cursor:pointer;line-height:1}
.close-x:hover{color:#dc2626}
.table{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.07)}
.table th{background:#f5f5f7;font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#6e6e73;padding:.55rem .9rem;text-align:left}
.table td{padding:.65rem .9rem;font-size:.86rem;border-top:1px solid #f0f0f0;vertical-align:top}
.reason{color:#dc2626;font-weight:600}
.details{color:#6e6e73;font-size:.8rem}
.empty{color:#6e6e73;font-style:italic}
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.4);display:none;align-items:center;justify-content:center;z-index:50}
.modal{background:#fff;border-radius:16px;padding:1.3rem;width:92%;max-width:380px}
.modal h3{margin-bottom:.6rem}
.modal label{display:block;font-size:.88rem;margin:.3rem 0}
.modal textarea{width:100%;border:1px solid #e5e5ea;border-radius:8px;padding:.5rem;font-family:inherit;font-size:.85rem;min-height:56px;margin-top:.5rem}
.modal-actions{display:flex;gap:.5rem;justify-content:flex-end;margin-top:.8rem}
"""

JS = """
var SERVED = /^https?:$/.test(location.protocol);
function boxText(id) {
  var el = document.getElementById(id);
  if (!el) return '';
  return (el.hidden ? el.textContent : el.innerText).trim();
}
function flash(btn, label) {
  var old = btn.textContent;
  btn.textContent = label; btn.classList.add('copied');
  setTimeout(function() { btn.textContent = old; btn.classList.remove('copied'); }, 1400);
}
function copyText(text, btn) {
  navigator.clipboard.writeText(text).then(function() { flash(btn, 'Copied'); },
    function() { window.prompt('Copy this:', text); });
}
function showOffline() {
  var b = document.getElementById('offline');
  if (b) { b.scrollIntoView({behavior: 'smooth', block: 'center'}); b.style.outline = '2px solid #f59e0b';
           setTimeout(function() { b.style.outline = ''; }, 1500); }
}
function post(action, payload) {
  return fetch('/api/' + action, {method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-Job-Agent': '1'}, body: JSON.stringify(payload)})
    .then(function(r) { return r.json(); })
    .then(function(res) {
      if (!res.ok) throw new Error(res.error || 'failed');
      if (res.learned) sessionStorage.setItem('ja-toast', res.learned);
      location.reload();
    })
    .catch(function(err) { alert('Could not save: ' + err.message); });
}
document.addEventListener('click', function(e) {
  var btn = e.target.closest('[data-act]');
  if (!btn) return;
  e.preventDefault(); e.stopPropagation();
  var d = btn.dataset, act = d.act;
  if (act === 'copy') return copyText(boxText(d.box), btn);
  if (act === 'copy-text') return copyText(d.text, btn);
  if (act === 'open-close') return openCloseModal(d.slug, d.company);
  if (!SERVED) return showOffline();
  if (act === 'event') {
    var p = {slug: d.slug, key: d.key, event: d.event};
    if (d.lang) p.lang = d.lang;
    if (d.note) p.with_note = d.note === '1';
    if (d.box) { p.text = boxText(d.box); p.field = d.field; }
    if (d.undo) p.undo = true;
    return post('event', p);
  }
  if (act === 'close-thread') return post('close-thread', {slug: d.slug, key: d.key, reason: d.reason || 'closed', undo: !!d.undo});
  if (act === 'task') return post('task', {slug: d.slug, task: d.task, done: d.done === '1'});
  if (act === 'stage') {
    var note = '';
    if (d.ask) { note = window.prompt(d.ask, ''); if (note === null) return; }
    return post('stage', {slug: d.slug, stage: d.stage, note: note});
  }
});
document.addEventListener('DOMContentLoaded', function() {
  if (!SERVED) { document.body.classList.add('offline'); return; }
  document.querySelectorAll('.msg-text[data-editable]').forEach(function(el) {
    el.setAttribute('contenteditable', 'plaintext-only');
    if (el.contentEditable !== 'plaintext-only') el.setAttribute('contenteditable', 'true');
    // Keep the character count live while editing (connect notes have a hard limit)
    el.addEventListener('input', function() {
      var count = el.closest('.msg').querySelector('.count[data-limit]');
      if (!count) return;
      var n = el.innerText.trim().length, limit = +count.dataset.limit;
      count.textContent = n + '/' + limit;
      count.classList.toggle('over', n > limit);
    });
  });
  var toast = sessionStorage.getItem('ja-toast');
  if (toast) {
    sessionStorage.removeItem('ja-toast');
    var t = document.createElement('div');
    t.textContent = toast;
    t.style.cssText = 'position:fixed;bottom:1rem;left:50%;transform:translateX(-50%);background:#1d1d1f;color:#fff;padding:.6rem 1rem;border-radius:10px;font-size:.85rem;z-index:99';
    document.body.appendChild(t);
    setTimeout(function() { t.remove(); }, 3500);
  }
});
"""

INDEX_JS = """
var closeSlug = null;
function openCloseModal(slug, company) {
  closeSlug = slug;
  document.getElementById('close-company').textContent = company;
  document.getElementById('close-note').value = '';
  document.getElementById('close-modal').style.display = 'flex';
}
document.addEventListener('DOMContentLoaded', function() {
  var tabs = document.querySelectorAll('.tab');
  tabs.forEach(function(tab) {
    tab.addEventListener('click', function() {
      tabs.forEach(function(t) { t.classList.remove('active'); });
      tab.classList.add('active');
      document.querySelectorAll('.pane').forEach(function(p) { p.style.display = p.id === tab.dataset.pane ? '' : 'none'; });
    });
  });
  var modal = document.getElementById('close-modal');
  document.getElementById('close-cancel').addEventListener('click', function() { modal.style.display = 'none'; });
  modal.addEventListener('click', function(e) { if (e.target === modal) modal.style.display = 'none'; });
  document.getElementById('close-confirm').addEventListener('click', function() {
    if (!SERVED) { modal.style.display = 'none'; return showOffline(); }
    var stage = (document.querySelector('input[name=close-stage]:checked') || {}).value || 'ghosted';
    post('stage', {slug: closeSlug, stage: stage, note: document.getElementById('close-note').value});
  });
});
"""

OFFLINE_BANNER = ('<div id="offline" class="offline-banner">Read-only: this page was opened from disk, '
                  'so clicks can\'t be saved. Start the dashboard and open it from there: '
                  '<code>python3 scripts/serve.py</code>'
                  '<button class="btn btn-light" data-act="copy-text" data-text="python3 scripts/serve.py">Copy</button></div>')


def page(title, css, body, extra_js=""):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<link rel="icon" href="data:,">
<style>{BASE_CSS}{css}</style>
</head>
<body>
<div class="container">
{OFFLINE_BANNER}
{body}
</div>
<script>{JS}{extra_js}</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Report page sections
# ---------------------------------------------------------------------------

def due_html(action):
    if action.get("overdue"):
        n = action["overdue"]
        return f'<span class="overdue">overdue {n} work day{"s" if n != 1 else ""}</span>'
    return f'<span class="due">due {esc(action["due"])}</span>'


def thread_who(thread):
    return thread.get("name") or st.KIND_LABELS.get(thread.get("kind"), thread.get("key"))


def header_card(slug, entry, data, rows, apply, settings):
    company = entry.get("company") or data.get("company") or slug
    job_title = entry.get("job_title") or data.get("job_title") or data.get("best_fit") or ""
    apply_url = data.get("apply_url")
    stage = entry.get("stage")
    rc = data.get("role_card") or {}

    badges = []
    if rc.get("verdict") in VERDICT_BADGE:
        cls, label = VERDICT_BADGE[rc["verdict"]]
        score = f" · {rc['fit_score']}/5" if rc.get("fit_score") else ""
        badges.append(badge(cls, label + score))
    if stage:
        cls, label = STAGE_BADGE.get(stage, ("badge-gray", stage))
        badges.append(badge(cls, label))

    role_html = ""
    if job_title:
        role_html = (f'<a class="role-link" href="{esc(apply_url)}" target="_blank">{esc(job_title)} ↗</a>'
                     if apply_url else f"<strong>{esc(job_title)}</strong>")
    added = f' · added {esc(entry.get("created_at"))}' if entry.get("created_at") else ""

    # What to do next, across everyone
    next_items = []
    if apply:
        next_items.append(f"<li>{esc(apply['text'])} {due_html(apply)}</li>")
    for t, s in rows:
        if s.get("action"):
            next_items.append(f"<li><strong>{esc(thread_who(t))}</strong>: {esc(s['action']['text'])} "
                              f"{due_html(s['action'])}</li>")
    if next_items:
        next_html = f'<div class="next-box"><ul>{"".join(next_items)}</ul></div>'
    elif stage in st.CLOSED_STAGES:
        next_html = ""
    else:
        waits = [s for _, s in rows if s.get("next_date")]
        if waits:
            w = min(waits, key=lambda s: s["next_date"])
            next_html = f'<div class="next-box">Nothing to do now. Next: {esc(w["label"])}</div>'
        else:
            next_html = ""

    links = []
    if data.get("website"):
        links.append(f'<a class="btn btn-light" href="{esc(data["website"])}" target="_blank">Website</a>')
    if data.get("careers_url") and data.get("careers_url") != "not found":
        links.append(f'<a class="btn btn-light" href="{esc(data["careers_url"])}" target="_blank">Careers page</a>')
    if apply_url:
        links.append(f'<a class="btn" href="{esc(apply_url)}" target="_blank">Apply ↗</a>')
        applied_on = (entry.get("tasks") or {}).get("applied")
        if applied_on:
            links.append(f'<span class="badge badge-green">Applied {esc(applied_on)}</span>'
                         + button("undo", {"data-act": "task", "data-slug": slug, "data-task": "applied",
                                           "data-done": "0"}, "btn-undo"))
        else:
            links.append(button("I applied", {"data-act": "task", "data-slug": slug, "data-task": "applied",
                                              "data-done": "1"}, "btn btn-green"))

    if stage in st.CLOSED_STAGES:
        stage_html = (f'<div class="stage-row">Closed ({esc(STAGE_BADGE.get(stage, ("", stage))[1])}). '
                      + button("Reopen", {"data-act": "stage", "data-slug": slug, "data-stage": ""}, "btn btn-quiet")
                      + "</div>")
    else:
        def sb(label, value, ask=None):
            return button(label, {"data-act": "stage", "data-slug": slug, "data-stage": value, "data-ask": ask},
                          "btn btn-quiet")
        stage_html = ('<div class="stage-row">Update: '
                      + sb("Interview", "interview", "Interview details (date, with whom)? Optional.")
                      + sb("Offer", "offer", "Offer details? Optional.")
                      + sb("Rejected", "rejected", "Reason, if they gave one? Optional.")
                      + sb("No answer", "ghosted")
                      + sb("Not interested", "withdrawn", "Why not? Optional.")
                      + "</div>")

    return f"""<div class="card">
  <div class="head-top"><h1>{esc(company)}</h1><div class="head-badges">{"".join(badges)}</div></div>
  <div class="meta" style="margin-top:.35rem">{role_html}{added}</div>
  {next_html}
  <div class="links-row">{"".join(links)}</div>
  {stage_html}
</div>"""


def facts(pairs):
    rows = "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in pairs if v)
    return f'<dl class="facts">{rows}</dl>' if rows else ""


def role_card(data):
    rc = data.get("role_card")
    if not rc:
        return legacy_research_card(data)
    company = rc.get("company") or {}
    role = rc.get("role") or {}

    verdict = ""
    if rc.get("verdict") or rc.get("verdict_line"):
        cls, label = VERDICT_BADGE.get(rc.get("verdict"), ("badge-gray", rc.get("verdict") or "Verdict"))
        score = f" · fit {rc['fit_score']}/5" if rc.get("fit_score") else ""
        verdict = (f'<div class="verdict {cls}"><strong>{esc(label)}{esc(score)}</strong>'
                   f'{esc(rc.get("verdict_line") or "")}</div>')

    warnings = "".join(f'<div class="warn">⚠ {esc(w)}</div>' for w in company.get("warning_signs") or [])
    company_html = (f"<div><h4>Company</h4><p>{esc(company.get('one_liner') or '')}</p>"
                    + facts([("Size", company.get("size")), ("Stage", company.get("stage")),
                             ("Where", company.get("location"))])
                    + warnings + "</div>")
    years = ""
    if role.get("years_required") or role.get("years_yours"):
        years = f"{role.get('years_required') or '?'} asked · you have {role.get('years_yours') or '?'}"
    role_html = (f"<div><h4>Role</h4><p>{esc(role.get('summary') or '')}</p>"
                 + facts([("Work mode", role.get("work_mode")), ("Location", role.get("location")),
                          ("Commute", role.get("commute")), ("Experience", years),
                          ("Level", role.get("seniority"))])
                 + "</div>")

    pros = "".join(f"<li>{esc(p)}</li>" for p in rc.get("pros") or [])
    cons = "".join(f"<li>{esc(c)}</li>" for c in rc.get("cons") or [])
    pros_cons = (f'<div class="two-col"><div><h4>Pros</h4><ul class="list pro">{pros}</ul></div>'
                 f'<div><h4>Cons</h4><ul class="list con">{cons}</ul></div></div>') if (pros or cons) else ""

    have = role.get("stack_have") or (data.get("cv_keywords") or {}).get("matched") or []
    missing = role.get("stack_missing") or (data.get("cv_keywords") or {}).get("missing") or []
    stack = ""
    if have or missing:
        stack = ('<h4>Stack</h4><div class="chips">'
                 + "".join(f'<span class="chip have">{esc(x)}</span>' for x in have)
                 + "".join(f'<span class="chip missing">{esc(x)}</span>' for x in missing) + "</div>")
    sources = company.get("sources") or rc.get("sources") or []
    sources_html = ""
    if sources:
        def short(url):
            return re.sub(r"^https?://(www\.)?", "", url)[:60]
        sources_html = '<div class="sources">Sources: ' + " · ".join(
            f'<a href="{esc(u)}" target="_blank">{esc(short(u))}</a>' for u in sources) + "</div>"
    return f"""<div class="card">
  <div class="section-title">Role summary</div>
  {verdict}
  <div class="two-col">{company_html}{role_html}</div>
  {pros_cons}
  {stack}
  {sources_html}
</div>"""


def legacy_research_card(data):
    pros = [n[1:].strip() for n in data.get("fit_notes") or [] if n.startswith("+")]
    cons = [n[1:].strip() for n in data.get("fit_notes") or [] if n.startswith("-")]
    if not (pros or cons):
        return ""
    return f"""<div class="card">
  <div class="section-title">Fit notes</div>
  <div class="two-col">
    <div><h4>Strengths</h4><ul class="list pro">{"".join(f"<li>{esc(p)}</li>" for p in pros)}</ul></div>
    <div><h4>Gaps / flags</h4><ul class="list con">{"".join(f"<li>{esc(c)}</li>" for c in cons)}</ul></div>
  </div>
</div>"""


def thread_controls(slug, thread, tstate):
    """Status text plus the buttons that move this person along."""
    key = thread["key"]
    ev = thread.get("events") or {}
    status = tstate["status"]
    action = tstate.get("action") or {}
    label = action.get("text") if action else tstate["label"]
    sub = ""
    if action:
        sub = due_html(action)
    elif tstate.get("next_date") and status == "waiting":
        sub = f'<span class="due">{esc(tstate["label"])}</span>'
        label = "Waiting"

    buttons = []
    if status == "closed":
        buttons.append(button("Reopen", {"data-act": "close-thread", "data-slug": slug, "data-key": key,
                                         "data-undo": "1"}, "btn btn-quiet"))
    elif status == "replied":
        buttons.append(ev_btn("Undo reply", slug, key, "replied", undo=True, cls="btn btn-quiet"))
    else:
        waiting_accept = tstate.get("waiting") == "accept" or action.get("type") == "no_accept"
        if waiting_accept:
            buttons.append(ev_btn("They accepted", slug, key, "accepted", cls="btn btn-green"))
        if ev.get("message_sent") or ev.get("sent") or (thread.get("connected") and ev):
            buttons.append(ev_btn("They replied", slug, key, "replied", cls="btn btn-green"))
        buttons.append(button("Close", {"data-act": "close-thread", "data-slug": slug, "data-key": key,
                                        "data-reason": "closed"}, "btn btn-quiet"))
    return (f'<div class="thread-status"><span class="label">{esc(label)}</span>{sub}'
            f'<div class="thread-controls">{"".join(buttons)}</div></div>')


def done_line(text, slug, key, event):
    return (f'<div class="done-line">✓ {esc(text)} '
            + ev_btn("undo", slug, key, event, undo=True, cls="btn-undo") + "</div>")


def step_messages(slug, key, prefix, texts, settings, sent_event=None, note=None, limit=None, field_base=None,
                  field_for=None):
    """Message boxes for one step; with sent_event, each box gets a Sent button."""
    html = ""
    for lang in languages(settings, texts):
        text = texts.get(lang)
        if not text:
            continue
        box_id = f"{prefix}_{lang}"
        field = field_for(lang) if field_for else ((field_base or "") + ("_he" if lang == "he" else ""))
        btns = ""
        if sent_event:
            btns = ev_btn(f"Sent {LANG_NAMES.get(lang, lang)}", slug, key, sent_event, lang=lang, note=note,
                          box=box_id, field=field)
        html += msg_box(box_id, text, lang, btns, limit=limit)
    return html


def contact_block(slug, contact, key, thread, tstate, settings, idx):
    kind = st.contact_kind(contact)
    kind_label = st.KIND_LABELS.get(kind, "Contact")
    if key is None:
        return (f'<div class="contact missing"><div class="contact-kind">{esc(kind_label)}</div>'
                f'<p class="skipped-note" style="margin-top:.3rem">Nobody found. Try the LinkedIn searches '
                f'at the bottom of this card.</p></div>')

    name = contact.get("name") or ""
    sub_bits = [b for b in (contact.get("job_title"), contact.get("location")) if b]
    src = contact.get("source")
    conf = (contact.get("confidence") or "").lower()
    badges_html = ""
    if src:
        badges_html += " " + badge("badge-gray", src)
    if conf:
        badges_html += " " + badge(CONFIDENCE_BADGE.get(conf, "badge-gray"), conf + " confidence")
    profile = contact.get("profile")
    profile_html = (f'<a href="{esc(profile)}" target="_blank" style="font-size:.85rem">LinkedIn profile ↗</a>'
                    if profile else '<span class="skipped-note">No profile link</span>')
    title_html = esc(name) if name else esc(contact.get("title") or kind_label)
    why = f'<div class="why">{esc(contact.get("why"))}</div>' if contact.get("why") else ""

    ev = (thread or {}).get("events") or {}
    status = (tstate or {}).get("status")
    atype = ((tstate or {}).get("action") or {}).get("type")
    connected = (thread or {}).get("connected")
    limit = int(settings.get("connect_note_max_chars", 200))
    prefix = f"c{idx}"

    steps = []
    # 1 · Connect note (skipped for people you're already connected to)
    connect_texts = {"en": contact.get("connect_note"), "he": contact.get("connect_note_he")}
    if connected:
        steps.append('<div class="step done"><div class="step-label">1 · Connect</div>'
                     '<div class="done-line">✓ Already connected '
                     + ev_btn("undo", slug, key, "already_connected", undo=True, cls="btn-undo") + "</div></div>")
    elif ev.get("connect_sent"):
        how = []
        if thread.get("with_note") is False:
            how.append("no note")
        elif thread.get("lang"):
            how.append(f"{LANG_NAMES.get(thread['lang'], thread['lang'])} note")
        detail = f" ({', '.join(how)})" if how else ""
        steps.append('<div class="step done"><div class="step-label">1 · Connect request</div>'
                     + done_line(f"Sent {ev['connect_sent']}{detail}", slug, key, "connect_sent") + "</div>")
    else:
        active = atype == "connect"
        body = step_messages(slug, key, f"{prefix}_cn", connect_texts, settings,
                             sent_event="connect_sent" if active else None, note=True, limit=limit,
                             field_base="connect_note")
        extra = ""
        if active:
            extra = ('<div class="msg-actions">'
                     + ev_btn("Sent without a note", slug, key, "connect_sent", note=False, cls="btn btn-quiet")
                     + ev_btn("We're already connected", slug, key, "already_connected", cls="btn btn-quiet")
                     + "</div>")
            if not body:
                extra = '<div class="hint">No note drafted.</div>' + extra
        steps.append(f'<div class="step{" active" if active else ""}"><div class="step-label">1 · Connect note</div>'
                     f"{body}{extra}</div>")

    # 2 · First message
    first_texts = {"en": contact.get("first_message"), "he": contact.get("first_message_he")}
    if ev.get("message_sent"):
        steps.append('<div class="step done"><div class="step-label">2 · First message</div>'
                     + done_line(f"Sent {ev['message_sent']}", slug, key, "message_sent") + "</div>")
    elif any(first_texts.values()) or atype == "message":
        active = atype == "message"
        later = not active and status not in ("closed", "replied")
        label = "2 · First message" + ("" if active or connected else " (after they accept)")
        body = step_messages(slug, key, f"{prefix}_fm", first_texts, settings,
                             sent_event="message_sent" if active else None, field_base="first_message")
        if active and not body:
            body = ('<div class="hint">No message drafted. Write your own, then: '
                    + ev_btn("Mark sent", slug, key, "message_sent", cls="btn btn-quiet") + "</div>")
        steps.append(f'<div class="step{" active" if active else ""}{" later" if later else ""}">'
                     f'<div class="step-label">{esc(label)}</div>{body}</div>')

    # 3 · Follow-ups
    schedule = settings.get("followup_schedule_workdays") or [4, 5]
    drafts = {str(f.get("n")): f for f in contact.get("followups") or []}
    fu_html = ""
    for n in range(1, len(schedule) + 1):
        event = f"followup_{n}"
        if ev.get(event):
            fu_html += done_line(f"Follow-up #{n} sent {ev[event]}", slug, key, event)
            continue
        draft = drafts.get(str(n)) or {}
        texts = {"en": draft.get("text"), "he": draft.get("text_he")}
        active = atype == event
        if active or any(texts.values()):
            body = step_messages(slug, key, f"{prefix}_fu{n}", texts, settings,
                                 sent_event=event if active else None,
                                 field_for=lambda lang, n=n: f"followups.{n}.text" + ("_he" if lang == "he" else ""))
            if active and not body:
                body = ('<div class="hint">Not drafted yet: run <code>/followups</code> in Claude, or write your own and '
                        + ev_btn(f"mark #{n} sent", slug, key, event, cls="btn btn-quiet") + "</div>")
            fu_html += f'<div class="hint"><strong>Follow-up #{n}</strong></div>{body}'
    if fu_html:
        active = (atype or "").startswith("followup")
        steps.append(f'<div class="step{" active" if active else ""}"><div class="step-label">3 · Follow-ups</div>'
                     f"{fu_html}</div>")

    alternates = contact.get("alternates") or []
    alt_html = ""
    if alternates:
        items = ""
        for a in alternates:
            bits = " · ".join(esc(b) for b in (a.get("job_title"), a.get("location")) if b)
            conf_b = (" " + badge(CONFIDENCE_BADGE.get((a.get("confidence") or "").lower(), "badge-gray"),
                                  a.get("confidence"))) if a.get("confidence") else ""
            link = (f'<a href="{esc(a["profile"])}" target="_blank">{esc(a.get("name") or "profile")}</a>'
                    if a.get("profile") else esc(a.get("name") or ""))
            why_a = f' <span class="meta">— {esc(a.get("why"))}</span>' if a.get("why") else ""
            items += f"<li>{link} {bits}{conf_b}{why_a}</li>"
        alt_html = (f'<details class="alternates"><summary>Other people found ({len(alternates)})</summary>'
                    f'<ul>{items}</ul><div class="hint">To switch, tell Claude: "use &lt;name&gt; instead at {esc(slug)}".</div>'
                    f"</details>")

    controls = thread_controls(slug, thread, tstate) if thread else ""
    return f"""<div class="contact">
  <div class="contact-head">
    <div>
      <div class="contact-kind">{esc(kind_label)}</div>
      <h3>{title_html}{badges_html}</h3>
      {('<div class="contact-sub">' + " · ".join(esc(b) for b in sub_bits) + '</div>') if sub_bits else ''}
      {why}
      {profile_html}
    </div>
    {controls}
  </div>
  {"".join(steps)}
  {alt_html}
</div>"""


def people_card(slug, entry, data, settings, today):
    contacts = data.get("contacts") or []
    keys = st.contact_keys(contacts)
    company = entry.get("company") or data.get("company") or slug

    known = data.get("referrals") or []
    known_html = ""
    if known:
        items = "".join(
            f'<li><a href="{esc(k.get("url"))}" target="_blank">{esc(k.get("name"))}</a>'
            f' · {esc(k.get("position") or "")}'
            + (f' <span class="meta">(connected {esc(k.get("connected_on"))})</span>' if k.get("connected_on") else "")
            + "</li>" for k in known)
        known_html = (f'<div class="known"><strong>You already know {len(known)} '
                      f'{"person" if len(known) == 1 else "people"} at {esc(company)}.</strong> '
                      f'Ask them first: a referral beats a cold message.<ul>{items}</ul></div>')

    blocks = ""
    for idx, (c, key) in enumerate(zip(contacts, keys)):
        thread = st.get_thread(entry, key) if key else None
        tstate = st.thread_state(entry, thread, today, settings) if thread else None
        blocks += contact_block(slug, c, key, thread, tstate, settings, idx)
    if not blocks:
        blocks = '<p class="skipped-note">No contacts yet.</p>'

    links = " · ".join(f'<a href="{esc(url)}" target="_blank">{esc(label)}</a>'
                       for label, url in linkedin_search_links(company, settings))
    return f"""<div class="card">
  <div class="section-title">People</div>
  {known_html}
  {blocks}
  <div class="search-links">Check or find others on LinkedIn: {links}</div>
</div>"""


def email_card(slug, entry, data, settings, today):
    draft = data.get("email_draft") or {}
    thread = st.get_thread(entry, "email")
    has_body = draft.get("body") or draft.get("body_he")
    if not has_body:
        if thread and (thread.get("events") or {}).get("sent"):
            body = f'<p class="meta">Email sent to {esc(thread.get("to"))} on {esc(thread["events"]["sent"])}.</p>'
        else:
            body = ('<p class="skipped-note">No email address found, so no email. '
                    "LinkedIn is the main channel for this one.</p>")
        return f'<div class="card"><div class="section-title">Email</div>{body}</div>'

    tstate = st.thread_state(entry, thread, today, settings) if thread else None
    ev = (thread or {}).get("events") or {}
    atype = ((tstate or {}).get("action") or {}).get("type")
    subject = draft.get("subject") or ""
    subject_he = draft.get("subject_he") or ""
    head = (f'<div class="email-head"><div>To: <strong>{esc(draft.get("to") or (thread or {}).get("to"))}</strong>'
            f'<br>Subject: {esc(subject)}{(" · " + esc(subject_he)) if subject_he else ""}'
            f'<br>Attachment: {esc(data.get("cv_file") or draft.get("attachment") or "cv/main.pdf")}</div>'
            f'{thread_controls(slug, thread, tstate) if thread else ""}</div>')

    texts = {"en": draft.get("body"), "he": draft.get("body_he")}
    if ev.get("sent"):
        main = done_line(f"Sent {ev['sent']}", slug, "email", "sent")
    else:
        main = ""
    main += step_messages(slug, "email", "em", texts, settings,
                          sent_event="sent" if (thread and atype == "email") else None,
                          field_for=lambda lang: "email_draft.body" + ("_he" if lang == "he" else ""))
    if settings.get("dry_run", True) and not ev.get("sent"):
        main += '<div class="hint">dry_run is on: this is saved as a Gmail draft. Send it from Gmail, then click Sent.</div>'

    schedule = settings.get("followup_schedule_workdays") or [4, 5]
    drafts = {str(f.get("n")): f for f in draft.get("followups") or []}
    fu = ""
    for n in range(1, len(schedule) + 1):
        event = f"followup_{n}"
        if ev.get(event):
            fu += done_line(f"Follow-up #{n} sent {ev[event]}", slug, "email", event)
            continue
        d = drafts.get(str(n)) or {}
        texts = {"en": d.get("body"), "he": d.get("body_he")}
        active = atype == event
        if active or any(texts.values()):
            body = step_messages(slug, "email", f"emfu{n}", texts, settings, sent_event=event if active else None,
                                 field_for=lambda lang, n=n: f"email_draft.followups.{n}.body"
                                 + ("_he" if lang == "he" else ""))
            if active and not body:
                body = ('<div class="hint">Not drafted yet: run <code>/followups</code>, or '
                        + ev_btn(f"mark #{n} sent", slug, "email", event, cls="btn btn-quiet") + "</div>")
            fu += f'<div class="hint"><strong>Follow-up #{n}</strong></div>{body}'
    legacy = data.get("legacy_followup_email")
    if legacy:
        fu += '<div class="hint"><strong>Follow-up (older draft)</strong></div>' + step_messages(
            slug, "email", "emlegacy", {"en": legacy.get("body"), "he": legacy.get("body_he")}, settings)
    fu_html = f'<div class="step"><div class="step-label">Follow-ups</div>{fu}</div>' if fu else ""
    return f"""<div class="card">
  <div class="section-title">Email</div>
  {head}
  <div class="step{" active" if atype == "email" else ""}">{main}</div>
  {fu_html}
</div>"""


def cv_card(slug, data):
    out_dir = os.path.join(ROOT, "output", slug)
    kind = data.get("cv") or "base"
    # Older runs didn't record which CV went out; their tailored PDF is the one that was sent
    has_tailored = os.path.exists(os.path.join(out_dir, "tailored_cv.pdf"))
    if has_tailored and (kind == "tailored" or not data.get("cv")):
        href, title = "tailored_cv.pdf", "Tailored CV"
    else:
        cv_file = data.get("cv_file") or "cv/main.pdf"
        href = "../../" + cv_file
        name = kind.split(":", 1)[1] if kind.startswith("variant:") else "base"
        title = f"CV ({name})"
        if not os.path.exists(os.path.join(ROOT, cv_file)):
            return (f'<div class="card"><div class="section-title">{esc(title)}</div>'
                    f'<p class="skipped-note">{esc(cv_file)} isn\'t built yet. Run: '
                    f'<code>bash scripts/build_cv.sh --base</code></p></div>')
    kw = data.get("cv_keywords") or {}
    kw_html = ""
    if kw.get("missing") or kw.get("matched"):
        kw_html = ('<div class="hint">Keywords from the job description. Red ones aren\'t on this CV: add them only '
                   'if they\'re true for you.</div><div class="chips">'
                   + "".join(f'<span class="chip missing">{esc(x)}</span>' for x in kw.get("missing") or [])
                   + "".join(f'<span class="chip have">{esc(x)}</span>' for x in kw.get("matched") or [])
                   + "</div>")
    return f"""<div class="card">
  <div class="section-title">{esc(title)}<a class="btn btn-light" href="{esc(href)}" download>Download PDF</a></div>
  {kw_html}
  <iframe class="pdf-frame" src="{esc(href)}"></iframe>
</div>"""


def interview_card(data):
    prep = data.get("interview_prep")
    if not prep:
        return ""
    parts = []
    if prep.get("company_brief"):
        parts.append(f"<h4>Company in 30 seconds</h4><p>{esc(prep['company_brief'])}</p>")
    if prep.get("process"):
        parts.append(f"<h4 style='margin-top:1rem'>Their interview process</h4><p>{esc(prep['process'])}</p>")
    if prep.get("questions"):
        qs = "".join(
            f'<div class="prep-q"><strong>{esc(q.get("q"))}</strong>'
            + (f'<div class="why">Why they ask: {esc(q.get("why"))}</div>' if q.get("why") else "")
            + (f'<div>Your angle: {esc(q.get("angle"))}</div>' if q.get("angle") else "")
            + "</div>" for q in prep["questions"])
        parts.append(f"<h4 style='margin-top:1rem'>Likely questions</h4>{qs}")
    if prep.get("stories"):
        ss = "".join(
            f'<div class="prep-q"><strong>{esc(s.get("theme"))}</strong><div>{esc(s.get("story"))}</div>'
            + (f'<div class="why">Proof: {esc(s.get("proof"))}</div>' if s.get("proof") else "")
            + "</div>" for s in prep["stories"])
        parts.append(f"<h4 style='margin-top:1rem'>Your stories for this role</h4>{ss}")
    if prep.get("ask_them"):
        parts.append("<h4 style='margin-top:1rem'>Questions to ask them</h4><ul class='list'>"
                     + "".join(f"<li>• {esc(x)}</li>" for x in prep["ask_them"]) + "</ul>")
    if prep.get("prep"):
        parts.append("<h4 style='margin-top:1rem'>Before the interview</h4><ul class='list'>"
                     + "".join(f"<li>☐ {esc(x)}</li>" for x in prep["prep"]) + "</ul>")
    updated = f'<span class="meta">updated {esc(prep.get("updated"))}</span>' if prep.get("updated") else ""
    return f"""<div class="card">
  <div class="section-title">Interview prep {updated}</div>
  {"".join(parts)}
</div>"""


EVENT_TEXT = {
    "connect_sent": "Connect request sent", "accepted": "Accepted your request",
    "message_sent": "First message sent", "sent": "Email sent", "followup_1": "Follow-up #1 sent",
    "followup_2": "Follow-up #2 sent", "followup_3": "Follow-up #3 sent", "replied": "Replied",
}


def history_card(entry):
    items = []
    for t in entry.get("outreach") or []:
        who = thread_who(t)
        for event, when in (t.get("events") or {}).items():
            items.append((when, f"{who}: {EVENT_TEXT.get(event, event)}"))
        if t.get("closed"):
            items.append((t.get("closed_at") or "", f"{who}: {st.CLOSE_REASONS.get(t['closed'], 'closed')}"))
    for note in entry.get("stage_notes") or []:
        items.append((note.get("date") or "", note.get("note") or ""))
    applied_on = (entry.get("tasks") or {}).get("applied")
    if applied_on:
        items.append((applied_on, "Applied on the site"))
    if entry.get("created_at"):
        items.append((entry["created_at"], "Added"))
    if len(items) <= 1:
        return ""
    rows = "".join(f'<li><span class="d">{esc(d)}</span>{esc(text)}</li>'
                   for d, text in sorted(items, key=lambda x: x[0], reverse=True))
    return f'<div class="card"><div class="section-title">History</div><ul class="timeline">{rows}</ul></div>'


def generate_report(slug):
    out_dir = os.path.join(ROOT, "output", slug)
    settings = st.load_settings()
    today = st.today_str()
    data = load_report_data(slug)
    entry = get_state(slug) or {"slug": slug, "company": data.get("company") or slug}
    rows, apply = st.entry_overview(entry, data, today, settings)

    body = ['<a href="../index.html" class="back-link">← Dashboard</a>',
            header_card(slug, entry, data, rows, apply, settings),
            role_card(data),
            people_card(slug, entry, data, settings, today),
            email_card(slug, entry, data, settings, today),
            interview_card(data),
            cv_card(slug, data),
            history_card(entry)]
    html = page(f"{entry.get('company') or slug} — job application", REPORT_CSS, "\n".join(b for b in body if b))

    out_path = os.path.join(out_dir, "report.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


# ---------------------------------------------------------------------------
# Dashboard (index.html)
# ---------------------------------------------------------------------------

def action_fields(item):
    """(kind of draft, [(lang, meta field)]) for the message a Today item asks you to send."""
    a = item["action"]["type"]
    if item.get("channel") == "email" or item.get("key") == "email":
        if a == "email":
            return [("en", "email_draft.body"), ("he", "email_draft.body_he")]
        if a.startswith("followup"):
            n = item["action"].get("n")
            return [("en", f"email_draft.followups.{n}.body"), ("he", f"email_draft.followups.{n}.body_he")]
        return []
    if a == "connect":
        return [("en", "connect_note"), ("he", "connect_note_he")]
    if a == "message":
        return [("en", "first_message"), ("he", "first_message_he")]
    if a.startswith("followup"):
        n = item["action"].get("n")
        return [("en", f"followups.{n}.text"), ("he", f"followups.{n}.text_he")]
    return []


def today_item_html(item, meta, settings, idx):
    a = item["action"]
    slug, key = item["slug"], item.get("key")
    overdue = a.get("overdue")
    pill = (f'<span class="due-pill overdue">overdue {overdue} work day{"s" if overdue != 1 else ""}</span>'
            if overdue else f'<span class="due-pill">due {esc(a["due"])}</span>')
    who = ""
    if item.get("kind") != "apply":
        label = st.KIND_LABELS.get(item.get("kind"), item.get("kind") or "")
        who = f'<span class="ti-who"> · {esc(item["name"])} ({esc(label)})</span>' if item.get("name") \
            else f'<span class="ti-who"> · {esc(label)}</span>'
    report = f"{esc(slug)}/report.html"

    buttons, hidden = [], []
    if a["type"] == "apply":
        if item.get("apply_url"):
            buttons.append(f'<a class="btn btn-light" href="{esc(item["apply_url"])}" target="_blank">Open job ↗</a>')
        buttons.append(button("I applied", {"data-act": "task", "data-slug": slug, "data-task": "applied",
                                            "data-done": "1"}, "btn btn-green"))
    elif a["type"] == "no_accept":
        buttons.append(f'<a class="btn btn-light" href="{report}">Find someone else</a>')
        buttons.append(ev_btn("They accepted", slug, key, "accepted", cls="btn btn-green"))
        buttons.append(button("Close", {"data-act": "close-thread", "data-slug": slug, "data-key": key,
                                        "data-reason": "no_accept"}, "btn btn-quiet"))
    else:
        event = {"connect": "connect_sent", "message": "message_sent", "email": "sent"}.get(a["type"], a["type"])
        texts = []
        for lang, field in action_fields(item):
            text = resolve_draft(meta, key, field)
            if text:
                texts.append((lang, field, text))
        langs = languages(settings, {lang: t for lang, _, t in texts})
        texts.sort(key=lambda x: langs.index(x[0]) if x[0] in langs else 9)
        for lang, field, text in texts:
            box = f"t{idx}_{lang}"
            hidden.append(hidden_text(box, text))
            buttons.append(f'<button class="btn btn-light" data-act="copy" data-box="{box}">Copy {LANG_NAMES[lang]}</button>')
        for lang, field, text in texts:
            buttons.append(ev_btn(f"Sent {LANG_NAMES[lang]}", slug, key, event, lang=lang,
                                  note=True if a["type"] == "connect" else None, box=f"t{idx}_{lang}", field=field))
        if a["type"] == "connect":
            buttons.append(ev_btn("Sent, no note", slug, key, "connect_sent", note=False, cls="btn btn-quiet"))
        if not texts:
            if a["type"].startswith("followup"):
                buttons.append('<span class="hint">not drafted: run /followups</span>')
            buttons.append(ev_btn("Mark sent", slug, key, event, cls="btn btn-quiet"))
        if item.get("profile"):
            buttons.append(f'<a class="btn btn-quiet" href="{esc(item["profile"])}" target="_blank">Profile ↗</a>')
    return (f'<div class="today-item"><div><a class="ti-company" href="{report}">{esc(item["company"])}</a>{who}'
            f'<div class="ti-action">{esc(a["text"])} {pill}</div></div>'
            f'<div class="ti-buttons">{"".join(buttons)}</div>{"".join(hidden)}</div>')


def today_card(today_data, settings):
    metas = {}
    groups = [("now", "Do now"), ("followups", "Follow-ups due"), ("check", "Check")]
    html, idx = "", 0
    for gid, title in groups:
        items = [i for i in today_data["items"] if i["group"] == gid]
        if not items:
            continue
        html += f'<div class="group-title">{esc(title)} ({len(items)})</div>'
        for item in items:
            if item["slug"] not in metas:
                metas[item["slug"]] = st.load_meta(item["slug"])
            html += today_item_html(item, metas[item["slug"]], settings, idx)
            idx += 1
    if not html:
        html = '<p class="empty">Nothing to send today.</p>'
    if today_data["upcoming"]:
        rows = "".join(
            f'<li><span class="d">{esc(u["date"])}</span><strong>{esc(u["company"])}</strong>'
            f' · {esc(u.get("name") or st.KIND_LABELS.get(u.get("kind"), ""))}: {esc(u["label"])}</li>'
            for u in today_data["upcoming"])
        html += f'<div class="group-title">Coming up (next 5 work days)</div><ul class="upcoming">{rows}</ul>'
    w = today_data["waiting"]
    foot = (f"Waiting: {w['accept']} connect request{'s' if w['accept'] != 1 else ''} to be accepted, "
            f"{w['reply']} message{'s' if w['reply'] != 1 else ''} waiting for a reply.")
    if today_data.get("note_limit"):
        foot += (f" LinkedIn notes this month: {today_data['notes_this_month']} "
                 f"(free accounts get about {today_data['note_limit']}).")
    return f"""<div class="card">
  <div class="section-title">Today<span class="meta" style="text-transform:none;letter-spacing:0">{esc(today_data['date'])}</span></div>
  {html}
  <div class="footnote">{esc(foot)}</div>
</div>"""


def stats_card(stats):
    if not stats["all"]["sent"]:
        return ""

    def row(label, s, cls=""):
        acc = f"{s['accepted']}/{s['connects']}" if s["connects"] else "-"
        acc_pct = f" ({round(100 * s['accepted'] / s['connects'])}%)" if s["connects"] else ""
        rep_pct = f" ({round(100 * s['replied'] / s['sent'])}%)" if s["sent"] else ""
        return (f'<tr class="{cls}"><td>{esc(label)}</td><td>{s["sent"]}</td><td>{acc}{acc_pct}</td>'
                f'<td>{s["replied"]}{rep_pct}</td></tr>')

    rows = row("Everyone", stats["all"])
    for section in ("by_kind", "by_lang", "by_note"):
        first = True
        for label, s in stats[section].items():
            rows += row(label, s, "sep" if first else "")
            first = False
    small = ('<div class="footnote">Small numbers so far: wait for 10+ people before trusting the rates.</div>'
             if stats["all"]["sent"] < 10 else "")
    return f"""<div class="card">
  <div class="section-title">What's working</div>
  <table class="stats"><tr><th></th><th>contacted</th><th>accepted</th><th>replied</th></tr>{rows}</table>
  {small}
</div>"""


def generate_index(slugs=None):
    settings = st.load_settings()
    today = st.today_str()
    entries = st.load_state()
    out_root = os.path.join(ROOT, "output")
    today_data = st.compute_today(entries, today, settings)
    stats = st.compute_stats(entries, today, settings)

    active, closed = [], []
    for e in sorted(entries, key=lambda x: x.get("created_at") or "", reverse=True):
        (closed if e.get("stage") in st.CLOSED_STAGES else active).append(e)

    cards = ""
    for e in active:
        slug = e["slug"]
        meta = st.load_meta(slug) or {}
        rc = meta.get("role_card") or {}
        badges = []
        if rc.get("verdict") in VERDICT_BADGE:
            cls, label = VERDICT_BADGE[rc["verdict"]]
            badges.append(badge(cls, label))
        if e.get("stage"):
            cls, label = STAGE_BADGE.get(e["stage"], ("badge-gray", e["stage"]))
            badges.append(badge(cls, label))
        nxt = st.entry_next(e, meta, today, settings)
        next_html = ""
        if nxt:
            when = f" · overdue {nxt['overdue']}d" if nxt.get("overdue") else f" · {nxt['due']}"
            next_html = (f'<div class="app-next{" overdue" if nxt.get("overdue") else ""}">'
                         f'{"→ " if nxt["kind"] == "action" else "⏳ "}{esc(nxt["text"])}{esc(when)}</div>')
        href = f"{esc(slug)}/report.html" if os.path.isdir(os.path.join(out_root, slug)) else "#"
        cards += (f'<a class="app-card" href="{href}"><div class="app-company">{esc(e.get("company"))}</div>'
                  f'<div class="app-role">{esc(e.get("job_title") or "")}</div>'
                  f'<div class="app-badges">{"".join(badges)}</div>{next_html}'
                  f'<button class="close-x" title="Close this application" data-act="open-close" '
                  f'data-slug="{esc(slug)}" data-company="{esc(e.get("company"))}">×</button></a>')

    closed_rows = ""
    for e in sorted(closed, key=lambda x: x.get("stage_updated_at") or "", reverse=True):
        cls, label = STAGE_BADGE.get(e.get("stage"), ("badge-gray", e.get("stage")))
        notes = e.get("stage_notes") or []
        note = notes[-1]["note"] if notes else ""
        link = (f'<a href="{esc(e["slug"])}/report.html">{esc(e.get("company"))}</a>'
                if os.path.isdir(os.path.join(out_root, e["slug"])) else esc(e.get("company")))
        closed_rows += (f"<tr><td>{link}<div class='details'>{esc(e.get('job_title') or '')}</div></td>"
                        f"<td>{badge(cls, label)}<div class='details'>{esc(note)}</div></td>"
                        f"<td class='details'>{esc(e.get('stage_updated_at') or '')}</td>"
                        f"<td>{button('Reopen', {'data-act': 'stage', 'data-slug': e['slug'], 'data-stage': ''}, 'btn btn-quiet')}</td></tr>")
    closed_html = (f'<table class="table"><tr><th>Company</th><th>Outcome</th><th>Date</th><th></th></tr>{closed_rows}</table>'
                   if closed_rows else '<p class="empty">Nothing closed yet.</p>')

    skipped = st.load_skipped()
    skipped_rows = ""
    for s in skipped:
        source_html = (f'<div><a href="{esc(s["source"])}" target="_blank">Source →</a></div>' if s.get("source") else "")
        skipped_rows += (f"<tr><td><strong>{esc(s.get('company', ''))}</strong></td>"
                         f"<td><div class='reason'>{esc(s.get('reason', ''))}</div>"
                         f"<div class='details'>{esc(s.get('details', ''))}</div>{source_html}</td>"
                         f"<td class='details'>{esc(s.get('skipped_at', ''))}</td></tr>")
    skipped_html = (f'<table class="table"><tr><th>Company</th><th>Reason</th><th>Date</th></tr>{skipped_rows}</table>'
                    if skipped_rows else '<p class="empty">Nothing skipped.</p>')

    grid = f'<div class="grid">{cards}</div>' if cards else '<p class="empty">No active applications. Give Claude a role: <code>/apply-role &lt;job url&gt;</code></p>'
    body = f"""<div class="top">
  <div><h1>Job search</h1><div class="subtitle">{len(active)} active · {len(closed)} closed · {len(skipped)} not processed</div></div>
</div>
{today_card(today_data, settings)}
{stats_card(stats)}
<div class="tab-bar">
  <button class="tab active" data-pane="pane-active">Active ({len(active)})</button>
  <button class="tab" data-pane="pane-closed">Closed ({len(closed)})</button>
  <button class="tab" data-pane="pane-skipped">Not processed ({len(skipped)})</button>
</div>
<div class="pane" id="pane-active">{grid}</div>
<div class="pane" id="pane-closed" style="display:none">{closed_html}</div>
<div class="pane" id="pane-skipped" style="display:none">{skipped_html}</div>
<div id="close-modal" class="modal-overlay">
  <div class="modal">
    <h3>Close <span id="close-company"></span>?</h3>
    <label><input type="radio" name="close-stage" value="ghosted" checked> No answer</label>
    <label><input type="radio" name="close-stage" value="rejected"> Rejected</label>
    <label><input type="radio" name="close-stage" value="withdrawn"> Not interested</label>
    <textarea id="close-note" placeholder="Note (optional)"></textarea>
    <div class="modal-actions">
      <button class="btn btn-quiet" id="close-cancel">Cancel</button>
      <button class="btn" id="close-confirm">Close it</button>
    </div>
  </div>
</div>"""
    out_path = os.path.join(out_root, "index.html")
    os.makedirs(out_root, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(page("Job search", INDEX_CSS, body, INDEX_JS))
    return out_path


def list_slugs():
    out_dir = os.path.join(ROOT, "output")
    if not os.path.isdir(out_dir):
        return []
    return [d for d in os.listdir(out_dir) if os.path.isdir(os.path.join(out_dir, d))]


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: python3 scripts/generate_report.py <slug>", file=sys.stderr)
        print("       python3 scripts/generate_report.py --all", file=sys.stderr)
        sys.exit(1)

    slugs = list_slugs() if args[0] == "--all" else args

    for slug in slugs:
        out_dir = os.path.join(ROOT, "output", slug)
        if not os.path.isdir(out_dir):
            print(f"WARNING: output/{slug}/ not found, skipping", file=sys.stderr)
            continue
        path = generate_report(slug)
        print(f"Report: {path}")

    index_path = generate_index()
    print(f"Index:  {index_path}")


if __name__ == "__main__":
    main()
