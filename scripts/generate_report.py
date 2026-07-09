#!/usr/bin/env python3
"""
generate_report.py — Build HTML report for processed company applications.
Usage:
  python3 scripts/generate_report.py <slug>
  python3 scripts/generate_report.py --all
"""

import json
import os
import re
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


def get_state(slug):
    data = read_file(os.path.join(ROOT, "state", "applications.json"))
    if not data:
        return {}
    for app in json.loads(data):
        if app.get("slug") == slug:
            return app
    return {}


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
        contact = {"title": title, "profile": None, "job_title": None, "connect_note": None, "first_message": None}

        m = re.search(r"Profile:\s*(https?://\S+)", body)
        if m:
            contact["profile"] = m.group(1).rstrip(")")

        m = re.search(r"^(?:Title|Company):\s*(.+)", body, re.MULTILINE)
        if m:
            contact["job_title"] = m.group(1).strip()

        m = re.search(r"Connect note[^\n]*:\n(.*?)(?=\n---|\nFirst message|\Z)", body, re.DOTALL)
        if m:
            contact["connect_note"] = m.group(1).strip()

        m = re.search(r"First message[^\n]*:\n(.*?)(?=\n---|\n##|\Z)", body, re.DOTALL)
        if m:
            contact["first_message"] = m.group(1).strip()

        contacts.append(contact)
    return contacts


def parse_email(content):
    if not content:
        return None
    result = {"to": None, "subject": None, "body": None}
    lines = content.splitlines()
    body_start = None
    for i, line in enumerate(lines):
        if line.startswith("To:"):
            result["to"] = line[3:].strip()
        elif line.startswith("Subject:"):
            result["subject"] = line[8:].strip()
        elif line.strip() == "Body:":
            body_start = i + 1
            break
    if body_start is not None:
        result["body"] = "\n".join(lines[body_start:]).strip()
    return result


STATUS_BADGE = {
    "sent": ("badge-sent", "Sent"),
    "drafted": ("badge-drafted", "Draft Saved"),
    "email-skipped": ("badge-skipped", "Email Skipped"),
    "pending": ("badge-pending", "Pending"),
}

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f5f7;color:#1d1d1f;line-height:1.6;padding:2rem 1rem}
.container{max-width:900px;margin:0 auto}
.card{background:#fff;border-radius:12px;padding:1.75rem;margin-bottom:1.5rem;box-shadow:0 1px 4px rgba(0,0,0,.08)}
h1{font-size:1.9rem;font-weight:700;margin-bottom:.4rem}
.section-title{font-size:.78rem;font-weight:600;color:#6e6e73;text-transform:uppercase;letter-spacing:.08em;margin-bottom:1rem;border-bottom:1px solid #f0f0f0;padding-bottom:.5rem}
.badge{display:inline-block;padding:.25rem .75rem;border-radius:20px;font-size:.72rem;font-weight:600;text-transform:uppercase;letter-spacing:.05em;margin-left:.75rem;vertical-align:middle}
.badge-sent{background:#d1fae5;color:#065f46}
.badge-drafted{background:#dbeafe;color:#1e40af}
.badge-skipped{background:#f3f4f6;color:#374151}
.badge-pending{background:#fef3c7;color:#92400e}
.meta{color:#6e6e73;font-size:.9rem;margin-top:.4rem}
.links-row{display:flex;gap:1rem;flex-wrap:wrap;margin-top:.75rem}
.links-row a{color:#0071e3;font-size:.9rem;text-decoration:none;border:1px solid #0071e3;padding:.2rem .65rem;border-radius:6px}
.links-row a:hover{background:#0071e3;color:#fff}
.fit-notes{list-style:none;margin-top:.5rem;display:flex;flex-direction:column;gap:.2rem}
.fit-notes li{font-size:.95rem;padding:.15rem 0}
.fit-notes li.pro::before{content:"✓  ";color:#059669;font-weight:700}
.fit-notes li.con::before{content:"✗  ";color:#dc2626;font-weight:700}
.fit-group-label{font-size:.72rem;font-weight:600;text-transform:uppercase;letter-spacing:.06em;margin-top:1rem;margin-bottom:.3rem}
.fit-group-label.pro{color:#059669}
.fit-group-label.con{color:#dc2626}
.role-link{display:inline-flex;align-items:center;gap:.4rem;color:#0071e3;font-weight:600;font-size:.95rem;text-decoration:none;margin-bottom:.25rem}
.role-link:hover{text-decoration:underline}
.contact-block{border:1px solid #e5e5ea;border-radius:8px;padding:1.25rem;margin-bottom:1rem}
.contact-block:last-child{margin-bottom:0}
.contact-block h3{font-size:1rem;font-weight:600;margin-bottom:.2rem}
.contact-role{font-size:.82rem;color:#6e6e73;margin-bottom:.5rem}
.profile-link{font-size:.88rem;color:#0071e3;text-decoration:none}
.profile-link:hover{text-decoration:underline}
.msg-label{font-size:.72rem;font-weight:600;color:#6e6e73;text-transform:uppercase;margin-top:1rem;margin-bottom:.35rem}
.msg-box{background:#f5f5f7;border-radius:6px;padding:.75rem 1rem;font-size:.88rem;position:relative;white-space:pre-wrap;padding-right:5rem}
.copy-btn{position:absolute;top:.5rem;right:.5rem;background:#0071e3;color:#fff;border:none;border-radius:5px;padding:.25rem .65rem;font-size:.72rem;cursor:pointer}
.copy-btn:hover{background:#005bbf}
.copy-btn.copied{background:#059669}
.email-body{background:#f5f5f7;border-radius:8px;padding:1rem 1.25rem;font-size:.9rem;white-space:pre-wrap;margin-top:.75rem}
.skipped-note{color:#6e6e73;font-style:italic;font-size:.9rem}
.pdf-download{display:inline-block;background:#0071e3;color:#fff;text-decoration:none;padding:.55rem 1.1rem;border-radius:8px;font-size:.9rem;font-weight:500;margin-bottom:1rem}
.pdf-download:hover{background:#005bbf}
.pdf-missing{color:#6e6e73;font-style:italic;font-size:.9rem}
.pdf-missing code{background:#f0f0f5;padding:.1rem .35rem;border-radius:4px;font-family:monospace}
.pdf-frame{width:100%;height:720px;border:1px solid #e5e5ea;border-radius:8px;margin-top:.5rem}
.back-link{display:inline-block;color:#0071e3;text-decoration:none;font-size:.88rem;margin-bottom:1.5rem}
.back-link:hover{text-decoration:underline}
.check-pill{display:inline-flex;align-items:center;gap:.3rem;padding:.2rem .65rem;border-radius:20px;border:1px solid #d1d1d6;background:#fff;color:#8e8e93;font-size:.75rem;font-weight:600;cursor:pointer;user-select:none;transition:background .15s,color .15s,border-color .15s;white-space:nowrap}
.check-pill:hover{border-color:#059669;color:#059669}
.check-pill.done{background:#d1fae5;border-color:#059669;color:#065f46}
.check-pill.done::before{content:"✓  "}
.msg-action-row{display:flex;align-items:center;justify-content:space-between;margin-top:1rem;margin-bottom:.35rem}
.msg-action-row .msg-label{margin:0}
.tasks-row{display:flex;flex-wrap:wrap;gap:.5rem;margin-top:.75rem}
.tasks-progress{font-size:.78rem;color:#6e6e73;margin-top:.6rem}
"""

JS = """
function copyMsg(id, btn) {
  var el = document.getElementById(id);
  var text = el.innerText.replace(/Copy$/, '').replace(/Copied!$/, '').trim();
  navigator.clipboard.writeText(text).then(function() {
    btn.textContent = 'Copied!';
    btn.classList.add('copied');
    setTimeout(function() { btn.textContent = 'Copy'; btn.classList.remove('copied'); }, 2000);
  });
}
function setAllPills(key, done) {
  document.querySelectorAll('[data-ck="' + key + '"]').forEach(function(e) {
    if (done) e.classList.add('done'); else e.classList.remove('done');
  });
}
function toggleCheck(el) {
  var key = el.dataset.ck;
  var done = !el.classList.contains('done');
  localStorage.setItem(key, done ? '1' : '0');
  setAllPills(key, done);
  updateProgress();
}
function loadChecks() {
  document.querySelectorAll('[data-ck]').forEach(function(el) {
    if (localStorage.getItem(el.dataset.ck) === '1') el.classList.add('done');
  });
}
function updateProgress() {
  document.querySelectorAll('.tasks-progress').forEach(function(bar) {
    var row = bar.previousElementSibling;
    var pills = row.querySelectorAll('.check-pill');
    var done = row.querySelectorAll('.check-pill.done').length;
    bar.textContent = done + ' / ' + pills.length + ' done';
  });
}
document.addEventListener('DOMContentLoaded', function() { loadChecks(); updateProgress(); });
"""


def build_tasks_card(slug, apply_url, email, contacts):
    pills = []
    if apply_url:
        pills.append(f'<span class="check-pill" data-ck="apply_{slug}" onclick="toggleCheck(this)">Apply</span>')
    if email and email.get("body"):
        pills.append(f'<span class="check-pill" data-ck="email_{slug}" onclick="toggleCheck(this)">Send email</span>')
    for i, c in enumerate(contacts):
        title = c.get("title", f"Contact {i+1}")
        name = title.split("—")[-1].strip() if "—" in title else title.split("(")[0].strip()
        if c.get("connect_note"):
            pills.append(f'<span class="check-pill" data-ck="connect_{slug}_{i}" onclick="toggleCheck(this)">Connect · {esc(name)}</span>')
        if c.get("first_message"):
            pills.append(f'<span class="check-pill" data-ck="firstmsg_{slug}_{i}" onclick="toggleCheck(this)">Message · {esc(name)}</span>')
    if not pills:
        return ""
    pills_html = "\n    ".join(pills)
    return f"""<div class="card">
  <div class="section-title">Tasks</div>
  <div class="tasks-row">
    {pills_html}
  </div>
  <div class="tasks-progress"></div>
</div>"""


def esc(text):
    if not text:
        return ""
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def generate_report(slug):
    out_dir = os.path.join(ROOT, "output", slug)
    research = parse_research(read_file(os.path.join(out_dir, "research.md")))
    contacts = parse_linkedin(read_file(os.path.join(out_dir, "linkedin.md")))
    email = parse_email(read_file(os.path.join(out_dir, "email.md")))
    pdf_exists = os.path.exists(os.path.join(out_dir, "tailored_cv.pdf"))
    state = get_state(slug)

    company = state.get("company", slug)
    job_title = state.get("job_title") or research.get("best_fit", "")
    status = state.get("status", "pending")
    followup_due = state.get("followup_due", "")
    badge_class, badge_label = STATUS_BADGE.get(status, ("badge-pending", status))

    # apply_url: prefer research, fallback to state hr/lead urls won't help, keep None
    apply_url = research.get("apply_url")

    parts = []
    parts.append(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(company)} — Job Application</title>
<style>{CSS}</style>
</head>
<body>
<div class="container">
<a href="../index.html" class="back-link">← All applications</a>
<div class="card">
  <h1>{esc(company)}<span class="badge {badge_class}">{badge_label}</span></h1>
  <div class="meta">{('<strong>' + esc(job_title) + '</strong> &nbsp;·&nbsp; ') if job_title else ''}Follow-up due: <strong>{esc(followup_due)}</strong></div>
  <div class="links-row">
    {('<a href="' + esc(research['website']) + '" target="_blank">Website</a>') if research.get('website') else ''}
    {('<a href="' + esc(research['careers_url']) + '" target="_blank">Careers page</a>') if research.get('careers_url') else ''}
    {('<a href="' + esc(apply_url) + '" target="_blank">Apply now →</a>') if apply_url else ''}
    {('<span class="check-pill" data-ck="apply_' + slug + '" onclick="toggleCheck(this)">Applied</span>') if apply_url else ''}
  </div>
</div>""")

    # Tasks card
    tasks_card = build_tasks_card(slug, apply_url, email, contacts)
    if tasks_card:
        parts.append(tasks_card)

    # Research card
    pros = [n[1:].strip() for n in research.get("fit_notes", []) if n.startswith("+")]
    cons = [n[1:].strip() for n in research.get("fit_notes", []) if n.startswith("-")]

    role_display = job_title or research.get("best_fit", "")
    role_html = ""
    if role_display:
        if apply_url:
            role_html = f'<a class="role-link" href="{esc(apply_url)}" target="_blank">{esc(role_display)} <span style="font-size:.8rem">↗</span></a>'
        else:
            role_html = f'<p style="font-weight:600;font-size:.95rem;margin-bottom:.25rem">{esc(role_display)}</p>'

    fit_html = ""
    if pros:
        fit_html += '<div class="fit-group-label pro">Strengths</div><ul class="fit-notes">'
        for p in pros:
            fit_html += f'<li class="pro">{esc(p)}</li>'
        fit_html += "</ul>"
    if cons:
        fit_html += '<div class="fit-group-label con">Gaps / flags</div><ul class="fit-notes">'
        for c in cons:
            fit_html += f'<li class="con">{esc(c)}</li>'
        fit_html += "</ul>"

    if role_html or fit_html:
        parts.append(f"""<div class="card">
  <div class="section-title">Research</div>
  {role_html}
  {fit_html}
</div>""")

    # LinkedIn contacts card
    if contacts:
        contact_blocks = ""
        for i, c in enumerate(contacts):
            cn_id = f"cn{i}"
            fm_id = f"fm{i}"
            cn_key = f"connect_{slug}_{i}"
            fm_key = f"firstmsg_{slug}_{i}"
            cn_html = (f'<div class="msg-action-row"><div class="msg-label">Connect Note</div>'
                       f'<span class="check-pill" data-ck="{cn_key}" onclick="toggleCheck(this)">Connect sent</span></div>'
                       f'<div class="msg-box" id="{cn_id}">{esc(c["connect_note"])}'
                       f'<button class="copy-btn" onclick="copyMsg(\'{cn_id}\',this)">Copy</button></div>'
                       ) if c.get("connect_note") else ""
            fm_html = (f'<div class="msg-action-row"><div class="msg-label">First Message</div>'
                       f'<span class="check-pill" data-ck="{fm_key}" onclick="toggleCheck(this)">Message sent</span></div>'
                       f'<div class="msg-box" id="{fm_id}">{esc(c["first_message"])}'
                       f'<button class="copy-btn" onclick="copyMsg(\'{fm_id}\',this)">Copy</button></div>'
                       ) if c.get("first_message") else ""
            profile_html = (f'<a class="profile-link" href="{esc(c["profile"])}" target="_blank">LinkedIn Profile →</a>'
                            ) if c.get("profile") else '<span class="skipped-note">Profile not found</span>'
            contact_blocks += f"""<div class="contact-block">
  <h3>{esc(c['title'])}</h3>
  {('<div class="contact-role">' + esc(c['job_title']) + '</div>') if c.get('job_title') else ''}
  {profile_html}
  {cn_html}
  {fm_html}
</div>"""
        parts.append(f"""<div class="card">
  <div class="section-title">LinkedIn Contacts</div>
  {contact_blocks}
</div>""")

    # Email card
    email_inner = ""
    email_key = f"email_{slug}"
    if email and email.get("body"):
        email_inner = (f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:.75rem">'
                       f'<p class="meta" style="margin:0">To: {esc(email.get("to",""))} &nbsp;·&nbsp; Subject: {esc(email.get("subject",""))}</p>'
                       f'<span class="check-pill" data-ck="{email_key}" onclick="toggleCheck(this)">Email sent</span></div>'
                       f'<div class="email-body">{esc(email.get("body",""))}</div>')
    elif status == "email-skipped":
        email_inner = '<p class="skipped-note">Email step skipped — no public contact email found. Apply via the portal link above.</p>'
    else:
        email_inner = '<p class="skipped-note">No email draft found.</p>'
    parts.append(f"""<div class="card">
  <div class="section-title">Email</div>
  {email_inner}
</div>""")

    # CV card
    if pdf_exists:
        cv_inner = (f'<a class="pdf-download" href="tailored_cv.pdf" download>Download PDF</a>'
                    f'<iframe class="pdf-frame" src="tailored_cv.pdf"></iframe>')
    else:
        cv_inner = (f'<p class="pdf-missing">PDF not compiled yet.</p>'
                    f'<p class="meta" style="margin-top:.5rem">Run: <code>bash scripts/build_cv.sh {esc(slug)}</code>'
                    f' &nbsp;(install first if needed: <code>brew install tectonic</code>)</p>')
    parts.append(f"""<div class="card">
  <div class="section-title">Tailored CV</div>
  {cv_inner}
</div>""")

    parts.append(f"<script>{JS}</script>\n</div>\n</body>\n</html>")

    out_path = os.path.join(out_dir, "report.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    return out_path


def get_task_keys(slug):
    out_dir = os.path.join(ROOT, "output", slug)
    research = parse_research(read_file(os.path.join(out_dir, "research.md")))
    contacts = parse_linkedin(read_file(os.path.join(out_dir, "linkedin.md")))
    email = parse_email(read_file(os.path.join(out_dir, "email.md")))
    keys = []
    if research.get("apply_url"):
        keys.append(f"apply_{slug}")
    if email and email.get("body"):
        keys.append(f"email_{slug}")
    for i, c in enumerate(contacts):
        if c.get("connect_note"):
            keys.append(f"connect_{slug}_{i}")
        if c.get("first_message"):
            keys.append(f"firstmsg_{slug}_{i}")
    return keys


INDEX_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f5f7;color:#1d1d1f;line-height:1.6;padding:2rem 1rem}
.container{max-width:960px;margin:0 auto}
h1{font-size:1.8rem;font-weight:700;margin-bottom:.25rem}
.subtitle{color:#6e6e73;font-size:.9rem;margin-bottom:2rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:1rem}
.app-card{background:#fff;border-radius:12px;padding:1.25rem;text-decoration:none;color:inherit;box-shadow:0 1px 4px rgba(0,0,0,.08);transition:box-shadow .15s,transform .15s;display:block;position:relative}
.app-card:hover{box-shadow:0 4px 14px rgba(0,0,0,.12);transform:translateY(-2px)}
.app-company{font-size:1.05rem;font-weight:600;margin-bottom:.2rem}
.app-role{font-size:.82rem;color:#6e6e73;margin-bottom:.8rem}
.app-foot{display:flex;align-items:center;justify-content:space-between}
.badge{display:inline-block;padding:.2rem .6rem;border-radius:20px;font-size:.7rem;font-weight:600;text-transform:uppercase;letter-spacing:.05em}
.badge-sent{background:#d1fae5;color:#065f46}
.badge-drafted{background:#dbeafe;color:#1e40af}
.badge-skipped{background:#f3f4f6;color:#374151}
.badge-pending{background:#fef3c7;color:#92400e}
.app-due{font-size:.78rem;color:#6e6e73}
.app-progress{position:absolute;top:.75rem;right:.75rem;line-height:0}
.empty{color:#6e6e73;font-style:italic;margin-top:1rem}
.section-header{font-size:1rem;font-weight:600;color:#6e6e73;margin:2.5rem 0 1rem;padding-bottom:.5rem;border-bottom:1px solid #e5e5ea}
.skipped-table{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08)}
.skipped-table th{background:#f5f5f7;font-size:.75rem;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:#6e6e73;padding:.6rem 1rem;text-align:left;border-bottom:1px solid #e5e5ea}
.skipped-table td{padding:.75rem 1rem;font-size:.88rem;border-bottom:1px solid #f0f0f0;vertical-align:top}
.skipped-table tr:last-child td{border-bottom:none}
.skipped-company{font-weight:600}
.skipped-reason{color:#dc2626;font-weight:500}
.skipped-details{color:#6e6e73;font-size:.82rem;margin-top:.2rem}
.skipped-source a{color:#0071e3;font-size:.78rem;text-decoration:none}
.skipped-source a:hover{text-decoration:underline}
.skipped-date{color:#6e6e73;font-size:.82rem;white-space:nowrap}
.tab-bar{display:flex;gap:0;margin-bottom:1.5rem;border-bottom:2px solid #e5e5ea}
.tab{background:none;border:none;padding:.6rem 1.2rem;font-size:.9rem;font-weight:500;color:#6e6e73;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-2px;transition:color .15s,border-color .15s}
.tab.active{color:#1d1d1f;border-bottom-color:#0071e3}
.tab:hover:not(.active){color:#1d1d1f}
.archive-btn{position:absolute;top:.6rem;left:.6rem;background:none;border:none;cursor:pointer;color:#d1d1d6;font-size:.85rem;padding:.15rem .3rem;border-radius:4px;line-height:1;opacity:0;transition:opacity .15s,color .15s,background .15s}
.app-card:hover .archive-btn{opacity:1}
.archive-btn:hover{color:#dc2626;background:#fef2f2}
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center;z-index:100}
.modal{background:#fff;border-radius:16px;padding:1.5rem;width:90%;max-width:380px;box-shadow:0 20px 60px rgba(0,0,0,.2)}
.modal h3{font-size:1.05rem;margin-bottom:.4rem}
.modal p{font-size:.85rem;color:#6e6e73;margin-bottom:.8rem}
.modal textarea{width:100%;border:1px solid #e5e5ea;border-radius:8px;padding:.55rem .75rem;font-size:.85rem;font-family:inherit;resize:vertical;min-height:60px;outline:none}
.modal textarea:focus{border-color:#0071e3}
.modal-actions{display:flex;gap:.5rem;justify-content:flex-end;margin-top:.9rem}
.btn{padding:.4rem .85rem;border-radius:8px;border:none;font-size:.83rem;font-weight:500;cursor:pointer;transition:background .15s}
.btn-cancel{background:#f5f5f7;color:#1d1d1f}
.btn-cancel:hover{background:#e5e5ea}
.btn-archive{background:#dc2626;color:#fff}
.btn-archive:hover{background:#b91c1c}
.btn-restore{background:#f0fdf4;color:#065f46;font-size:.78rem}
.btn-restore:hover{background:#dcfce7}
"""


INDEX_JS = """
document.addEventListener('DOMContentLoaded', function() {
  // Progress circles
  document.querySelectorAll('.app-card[data-tasks]').forEach(function(card) {
    var keys = card.dataset.tasks.split(',').filter(Boolean);
    if (!keys.length) return;
    var done = keys.filter(function(k) { return localStorage.getItem(k) === '1'; }).length;
    var el = card.querySelector('.app-progress');
    if (!el) return;
    var r = 9, sw = 3, sz = (r + sw) * 2;
    var cx = sz / 2, cy = sz / 2;
    var circ = 2 * Math.PI * r;
    var pct = done / keys.length;
    var color = pct === 1 ? '#059669' : pct > 0 ? '#0071e3' : '#d1d1d6';
    el.innerHTML = '<svg width="' + sz + '" height="' + sz + '" viewBox="0 0 ' + sz + ' ' + sz + '">'
      + '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="none" stroke="#f0f0f0" stroke-width="' + sw + '"/>'
      + '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="none" stroke="' + color + '" stroke-width="' + sw + '"'
      + ' stroke-dasharray="' + circ.toFixed(2) + '" stroke-dashoffset="' + (circ*(1-pct)).toFixed(2) + '"'
      + ' stroke-linecap="round" transform="rotate(-90 ' + cx + ' ' + cy + ')"/>'
      + '</svg>';
  });

  // Tab switching
  var tabs = document.querySelectorAll('.tab');
  var paneActive = document.getElementById('tab-active');
  var paneArchived = document.getElementById('tab-archived');
  tabs.forEach(function(tab) {
    tab.addEventListener('click', function() {
      tabs.forEach(function(t) { t.classList.remove('active'); });
      tab.classList.add('active');
      if (tab.dataset.tab === 'active') {
        paneActive.style.display = '';
        paneArchived.style.display = 'none';
      } else {
        paneActive.style.display = 'none';
        paneArchived.style.display = '';
        renderArchivedApps();
      }
    });
  });

  // Archive modal
  var pendingSlug = null;
  var modal = document.getElementById('archive-modal');
  var textarea = document.getElementById('archive-reason');

  document.querySelectorAll('.archive-btn').forEach(function(btn) {
    btn.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();
      pendingSlug = btn.dataset.slug;
      textarea.value = '';
      modal.style.display = 'flex';
      textarea.focus();
    });
  });

  document.getElementById('modal-cancel').addEventListener('click', function() {
    modal.style.display = 'none';
    pendingSlug = null;
  });

  modal.addEventListener('click', function(e) {
    if (e.target === modal) { modal.style.display = 'none'; pendingSlug = null; }
  });

  document.getElementById('modal-confirm').addEventListener('click', function() {
    if (!pendingSlug) return;
    var reason = textarea.value.trim();
    localStorage.setItem('archive_' + pendingSlug, JSON.stringify({
      reason: reason,
      date: new Date().toISOString().slice(0, 10)
    }));
    modal.style.display = 'none';
    var card = document.querySelector('.app-card[data-slug="' + pendingSlug + '"]');
    if (card) card.style.display = 'none';
    pendingSlug = null;
    updateTabCounts();
  });

  // Restore (delegated, since archived section is dynamic)
  document.addEventListener('click', function(e) {
    if (!e.target.classList.contains('btn-restore')) return;
    var slug = e.target.dataset.slug;
    localStorage.removeItem('archive_' + slug);
    var card = document.querySelector('.app-card[data-slug="' + slug + '"]');
    if (card) card.style.display = '';
    renderArchivedApps();
    updateTabCounts();
  });

  function escHtml(s) {
    return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function getArchivedSlugs() {
    var result = [];
    for (var i = 0; i < localStorage.length; i++) {
      var key = localStorage.key(i);
      if (key && key.startsWith('archive_')) result.push(key.slice(8));
    }
    return result;
  }

  function renderArchivedApps() {
    var container = document.getElementById('archived-apps-container');
    if (!container) return;
    var slugs = getArchivedSlugs();
    if (!slugs.length) {
      container.innerHTML = '';
      return;
    }
    var rows = '';
    slugs.forEach(function(slug) {
      var data = JSON.parse(localStorage.getItem('archive_' + slug) || '{}');
      var card = document.querySelector('.app-card[data-slug="' + slug + '"]');
      var company = card ? card.dataset.company : slug;
      var role = card ? card.dataset.role : '';
      rows += '<tr>'
        + '<td><div class="skipped-company">' + escHtml(company) + '</div>'
        + (role ? '<div style="font-size:.82rem;color:#6e6e73">' + escHtml(role) + '</div>' : '')
        + '</td>'
        + '<td>' + (data.reason ? '<span class="skipped-reason">' + escHtml(data.reason) + '</span>' : '<em style="color:#d1d1d6">&#8212;</em>') + '</td>'
        + '<td class="skipped-date">' + escHtml(data.date || '') + '</td>'
        + '<td><button class="btn btn-restore" data-slug="' + escHtml(slug) + '">Restore</button></td>'
        + '</tr>';
    });
    container.innerHTML = '<h2 class="section-header">Archived (' + slugs.length + ')</h2>'
      + '<table class="skipped-table"><thead><tr><th>Company</th><th>Reason</th><th>Date</th><th></th></tr></thead>'
      + '<tbody>' + rows + '</tbody></table>';
  }

  function updateTabCounts() {
    var archived = getArchivedSlugs();
    var total = document.querySelectorAll('.app-card').length;
    var activeCount = total - archived.length;
    var tabActive = document.querySelector('.tab[data-tab="active"]');
    var tabArchived = document.querySelector('.tab[data-tab="archived"]');
    if (tabActive) tabActive.textContent = 'Active Applications (' + activeCount + ')';
    if (tabArchived) tabArchived.textContent = 'Archives & Not Processed';
  }

  // On load: hide archived cards, update counts
  var archivedOnLoad = getArchivedSlugs();
  archivedOnLoad.forEach(function(slug) {
    var card = document.querySelector('.app-card[data-slug="' + slug + '"]');
    if (card) card.style.display = 'none';
  });
  updateTabCounts();
});
"""


def generate_index(slugs):
    data = read_file(os.path.join(ROOT, "state", "applications.json"))
    apps = json.loads(data) if data else []
    by_slug = {a["slug"]: a for a in apps}

    cards = ""
    for slug in sorted(slugs, key=lambda s: by_slug.get(s, {}).get("created_at", ""), reverse=True):
        if slug not in by_slug:
            continue
        a = by_slug[slug]
        company = a.get("company", slug)
        status = a.get("status", "pending")
        job_title = a.get("job_title", "")
        followup = a.get("followup_due", "")
        badge_class, badge_label = STATUS_BADGE.get(status, ("badge-pending", status))
        task_keys = get_task_keys(slug)
        data_tasks = ",".join(task_keys)
        cards += f"""<a class="app-card" href="{esc(slug)}/report.html" data-tasks="{data_tasks}" data-slug="{esc(slug)}" data-company="{esc(company)}" data-role="{esc(job_title)}">
  <div class="app-company">{esc(company)}</div>
  <div class="app-role">{esc(job_title) or '&nbsp;'}</div>
  <div class="app-foot">
    <span class="badge {badge_class}">{badge_label}</span>
    <span class="app-due">{esc(followup)}</span>
  </div>
  {('<div class="app-progress"></div>') if task_keys else ''}
  <button class="archive-btn" data-slug="{esc(slug)}" title="Archive">&times;</button>
</a>
"""

    # Skipped companies section
    skipped_data = read_file(os.path.join(ROOT, "state", "skipped.json"))
    skipped = json.loads(skipped_data) if skipped_data else []
    skipped_rows = ""
    for s in skipped:
        source_html = (f'<div class="skipped-source"><a href="{esc(s["source"])}" target="_blank">Source →</a></div>'
                       if s.get("source") else "")
        skipped_rows += f"""<tr>
  <td><div class="skipped-company">{esc(s.get('company', ''))}</div></td>
  <td>
    <div class="skipped-reason">{esc(s.get('reason', ''))}</div>
    {('<div class="skipped-details">' + esc(s.get('details', '')) + '</div>') if s.get('details') else ''}
    {source_html}
  </td>
  <td class="skipped-date">{esc(s.get('skipped_at', ''))}</td>
</tr>"""

    skipped_section = ""
    if skipped_rows:
        skipped_section = f"""<h2 class="section-header">Not processed ({len(skipped)})</h2>
<table class="skipped-table">
  <thead><tr><th>Company</th><th>Reason</th><th>Date</th></tr></thead>
  <tbody>{skipped_rows}</tbody>
</table>"""

    count = len([s for s in slugs if s in by_slug])
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Job Applications</title>
<style>{INDEX_CSS}</style>
</head>
<body>
<div class="container">
<h1>Job Applications</h1>
<p class="subtitle">{count} application{'s' if count != 1 else ''} tracked &nbsp;·&nbsp; {date.today().isoformat()}</p>
<div class="tab-bar">
  <button class="tab active" data-tab="active">Active Applications</button>
  <button class="tab" data-tab="archived">Archives &amp; Not Processed</button>
</div>
<div id="tab-active">
{"<div class='grid'>" + cards + "</div>" if cards else "<p class='empty'>No applications yet.</p>"}
</div>
<div id="tab-archived" style="display:none">
<div id="archived-apps-container"></div>
{skipped_section}
</div>
</div>
<div id="archive-modal" class="modal-overlay" style="display:none">
  <div class="modal">
    <h3>Archive application?</h3>
    <p>Optional: add a reason for archiving.</p>
    <textarea id="archive-reason" placeholder="e.g. no response, not a good fit..."></textarea>
    <div class="modal-actions">
      <button class="btn btn-cancel" id="modal-cancel">Cancel</button>
      <button class="btn btn-archive" id="modal-confirm">Archive</button>
    </div>
  </div>
</div>
<script>{INDEX_JS}</script>
</body>
</html>"""

    out_path = os.path.join(ROOT, "output", "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
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

    index_path = generate_index(list_slugs())
    print(f"Index:  {index_path}")


if __name__ == "__main__":
    main()
