#!/usr/bin/env python3
"""
runs.py — background runs: Flow 3 started from the dashboard, done by Claude Code headless.

The dashboard's "+ New application" form (or `runs.py start`) queues a run. One at a time, the
dashboard server (scripts/serve.py) starts `claude -p` in this repo with a prompt that says
"follow Flow 3 with these inputs, don't ask" (the rules are in src/prompts/background_run.md).
Claude's event stream goes to state/runs/<id>/events.jsonl; the server reads it for progress,
and the run's structured result says done / needs_input / skipped / failed. A run that needs
you waits with a question; your answer resumes the same Claude session where it stopped.

Runs are listed in state/runs.json. Each has a folder state/runs/<id>/ with the prompts sent,
events.jsonl and stderr.log. A run is its own process group, so it keeps going when the
dashboard stops, and the next tick (dashboard or `work`) picks it up again.

A run uses the `claude` CLI's own login (run `claude auth login` once in Terminal). It can read
the repo, write under output/, change state only through the project's scripts, and use the
web. No MCP servers (so no Gmail), no other commands, and your broader allow rules in
.claude/settings.local.json and ~/.claude/settings.json don't apply (--restricted).

Usage:
  python3 scripts/runs.py start --url https://www.linkedin.com/jobs/view/4312345678/ \\
      --hr "Dana Cohen | https://www.linkedin.com/in/dana-cohen/ | dana@acme.com" --notes "..."
  python3 scripts/runs.py start --company "Acme" --title "Android Developer" --go-ahead
  python3 scripts/runs.py start --page-file job.txt     # a job page you saved to a file
  python3 scripts/runs.py list
  python3 scripts/runs.py show <id>
  python3 scripts/runs.py reply <id> "Continue anyway"
  python3 scripts/runs.py cancel <id>
  python3 scripts/runs.py work          # run the queue here, without the dashboard
  python3 scripts/runs.py check         # is the claude CLI installed and logged in?

JOB_AGENT_CLAUDE=/path/to/claude changes which CLI is started.
"""

import argparse
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import state as st  # noqa: E402

RUNS_FILE = st.ROOT / "state" / "runs.json"
RUNS_DIR = st.ROOT / "state" / "runs"

ACTIVE = ("queued", "running")
FINISHED = ("done", "needs_input", "skipped", "failed", "cancelled", "interrupted")
RESULT_STATUSES = ("done", "needs_input", "skipped", "failed")
KEEP_FINISHED = 50
SHOW_FINISHED_DAYS = 3
TICK_SECONDS = 1.5
KILL_GRACE_SECONDS = 10
FLOW_STEPS = 10

PEOPLE_KINDS = {"hr": "HR / recruiter", "lead": "Team lead", "referral": "Someone the user knows there",
                "other": "Other contact"}
LIMITS = {"url": 2000, "page_text": 100_000, "company": 200, "job_title": 200, "notes": 4000,
          "name": 200, "profile": 500, "email": 200, "note": 500}
MAX_PEOPLE = 6

TOOLS = "Read,Glob,Grep,Write,Edit,Bash,WebFetch,WebSearch"
ALLOWED_TOOLS = [
    "Read", "Glob", "Grep", "WebSearch", "WebFetch", "Edit(./output/**)", "Write(./output/**)",
    "Bash(python3 scripts/state.py *)", "Bash(python3 scripts/cv_keywords.py *)",
    "Bash(python3 scripts/referrals.py *)", "Bash(python3 scripts/check_messages.py *)",
    "Bash(python3 scripts/generate_report.py *)", "Bash(bash scripts/build_cv.sh *)",
]
RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": list(RESULT_STATUSES)},
        "slug": {"type": ["string", "null"]},
        "company": {"type": ["string", "null"]},
        "job_title": {"type": ["string", "null"]},
        "summary": {"type": "string"},
        "question": {"type": ["string", "null"]},
        "options": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "summary"],
}
# Set by a parent Claude Code session or the Claude app, never by a plain Terminal
SESSION_MARKERS = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_DESKTOP_APP_VERSION",
                   "CLAUDE_AGENT_SDK_VERSION", "CLAUDE_PID")
RETRY_PROMPT = ("The run stopped before it finished. Check what's already in output/ for this job "
                "and continue Flow 3 from where you stopped.")

STEP_RE = re.compile(r"^[#*_\s]*step\s+(\d{1,2})(?:\s*(?:of|/)\s*\d+)?\s*[:.\-–—]\s*(.+?)[*_\s]*$", re.IGNORECASE)
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SCRIPT_ACTIVITY = {
    "cv_keywords.py": "Picking the CV version", "referrals.py": "Looking for people you know",
    "check_messages.py": "Checking the messages", "generate_report.py": "Building the report",
    "build_cv.sh": "Building the CV PDF",
}

_PROCS = {}    # run id -> Popen, for runs this process started
_OFFSETS = {}  # run id -> bytes of events.jsonl already read
_CLAUDE = {"checked": 0.0, "path": None, "logged_in": None}


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def now():
    return datetime.now().isoformat(timespec="seconds")


def _age(iso, end=None):
    """Seconds from an ISO time to `end` (an ISO time) or now."""
    try:
        start = datetime.fromisoformat(iso)
        stop = datetime.fromisoformat(end) if end else datetime.now()
    except (TypeError, ValueError):
        return 0
    return max(0, (stop - start).total_seconds())


def _short(text, limit):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def run_dir(run_id):
    return RUNS_DIR / run_id


def load_runs():
    return st._read_json(RUNS_FILE, [])


def save_runs(runs):
    """Save, keeping the newest KEEP_FINISHED finished runs (older ones lose their folder too)."""
    finished = sorted((r for r in runs if r["status"] in FINISHED), key=lambda r: r["created_at"])
    old = {r["id"] for r in finished[:-KEEP_FINISHED]} if len(finished) > KEEP_FINISHED else set()
    for run_id in old:
        shutil.rmtree(run_dir(run_id), ignore_errors=True)
    st._write_json(RUNS_FILE, [r for r in runs if r["id"] not in old])


def _lock():
    return st.state_lock("runs")


def _find(runs, run_id):
    run = next((r for r in runs if r["id"] == run_id), None)
    if not run:
        raise ValueError(f"no run '{run_id}'")
    return run


# ---------------------------------------------------------------------------
# The claude CLI
# ---------------------------------------------------------------------------

def claude_path():
    return os.environ.get("JOB_AGENT_CLAUDE") or shutil.which("claude")


def child_env():
    """The environment for `claude -p`: the one a plain Terminal would give it.

    A dashboard started from inside Claude Code or the Claude app (/dashboard, the app's preview
    pane) inherits that session's variables: CLAUDECODE, CLAUDE_CODE_* (one turns on --bare
    mode), the app's own ANTHROPIC_BASE_URL. A run must not use them, so when any session marker
    is there they're all dropped and the CLI uses its own login.
    """
    env = dict(os.environ)
    if any(k in env for k in SESSION_MARKERS):
        env = {k: v for k, v in env.items() if not k.startswith(("CLAUDE", "ANTHROPIC_", "MCP_"))}
    return env


def claude_status(max_age=60):
    """{"found": bool, "logged_in": bool or None}, checked at most once a minute."""
    if time.time() - _CLAUDE["checked"] > max_age:
        path, logged_in = claude_path(), None
        if path:
            try:
                res = subprocess.run([path, "auth", "status"], capture_output=True, text=True,
                                     timeout=15, env=child_env(), cwd=str(st.ROOT))
                logged_in = bool(json.loads(res.stdout).get("loggedIn"))
            except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
                logged_in = None
        _CLAUDE.update(checked=time.time(), path=path, logged_in=logged_in)
    return {"found": bool(_CLAUDE["path"]), "logged_in": _CLAUDE["logged_in"]}


def command(run, settings, resume):
    cmd = [claude_path(), "-p",
           "--output-format", "stream-json", "--verbose",
           "--json-schema", json.dumps(RESULT_SCHEMA),
           "--restricted", "--strict-mcp-config",
           "--permission-mode", "dontAsk", "--permission-prompts", "none",
           "--tools", TOOLS,
           "--allowedTools", *ALLOWED_TOOLS]
    if resume:
        cmd += ["--resume", run["session_id"]]
    else:
        cmd += ["--session-id", run["session_id"], "--name", f"Apply: {run['label']}"]
    if settings.get("background_model"):
        cmd += ["--model", str(settings["background_model"])]
    return cmd


# ---------------------------------------------------------------------------
# New runs
# ---------------------------------------------------------------------------

def _text(p, key):
    value = str(p.get(key) or "").strip()
    if len(value) > LIMITS[key]:
        raise ValueError(f"{key.replace('_', ' ').capitalize()} is too long (max {LIMITS[key]} characters)")
    return value


def clean_input(p):
    """The form (or CLI) input, checked and trimmed. Raises ValueError with a message for the user."""
    url = _text(p, "url")
    if url and not re.match(r"https?://\S+$", url, re.IGNORECASE):
        raise ValueError("The job link should be a web address (https://...)")
    page = _text(p, "page_text")
    company, title = _text(p, "company"), _text(p, "job_title")
    if not (url or page or (company and title)):
        raise ValueError("Give the job: a link, the pasted job page, or the company and the job title")
    people = []
    for raw in (p.get("people") or [])[:MAX_PEOPLE]:
        if not isinstance(raw, dict):
            continue
        person = {k: _text(raw, k) for k in ("name", "profile", "email", "note")}
        if not any(person.values()):
            continue
        who = person["name"] or "a person"
        if person["profile"] and not re.match(r"https?://\S+$", person["profile"], re.IGNORECASE):
            raise ValueError(f"The LinkedIn link for {who} should start with https://")
        if person["email"] and not re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+$", person["email"]):
            raise ValueError(f"'{person['email']}' doesn't look like an email address")
        kind = raw.get("kind") if raw.get("kind") in PEOPLE_KINDS else "other"
        people.append(dict(kind=kind, **person))
    return {"url": url, "page_text": page, "company": company, "job_title": title, "people": people,
            "notes": _text(p, "notes"), "go_ahead": bool(p.get("go_ahead")), "tailor_cv": bool(p.get("tailor_cv"))}


def label_for(inp):
    """What the dashboard calls a run until Claude knows the company and title."""
    if inp.get("company"):
        return f"{inp['company']} — {inp['job_title']}" if inp.get("job_title") else inp["company"]
    if inp.get("url"):
        u = urlparse(inp["url"])
        host = u.netloc[4:] if u.netloc.startswith("www.") else u.netloc
        return _short((host + u.path).rstrip("/"), 60)
    first = next((line for line in inp.get("page_text", "").splitlines() if line.strip()), "Pasted job page")
    return _short(first, 60)


def job_key(url):
    """A job link in comparable form: the LinkedIn job id, else host + path."""
    u = urlparse(str(url).strip())
    host = u.netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    if "linkedin." in host:
        m = re.search(r"/jobs/view/(?:[^/]*?-)?(\d{6,})", u.path) or re.search(r"currentJobId=(\d+)", u.query)
        if m:
            return "linkedin:" + m.group(1)
    return host + u.path.rstrip("/").lower()


def find_duplicate(inp, runs):
    """An application or an unfinished run for the same job, or None."""
    key = job_key(inp["url"]) if inp.get("url") else None
    company = st.slugify(inp["company"]) if inp.get("company") else None
    title = (inp.get("job_title") or "").lower()

    def same(url, comp, job_title):
        if key and isinstance(url, str) and url and job_key(url) == key:
            return True
        return bool(company and title and comp and st.slugify(comp) == company
                    and (job_title or "").lower() == title)

    for r in runs:
        ri = r["input"]
        if r["status"] in ("queued", "running", "needs_input") and same(ri.get("url"), ri.get("company"), ri.get("job_title")):
            return {"run": r["id"], "label": r["label"], "status": r["status"].replace("_", " ")}
    if not (key or (company and title)) or not st.OUTPUT_DIR.is_dir():
        return None
    for d in sorted(st.OUTPUT_DIR.iterdir()):
        if not d.is_dir():
            continue
        meta = st.load_meta(d.name) or {}
        if same(meta.get("apply_url"), meta.get("company"), meta.get("job_title")):
            label = " — ".join(x for x in (meta.get("company"), meta.get("job_title")) if x) or d.name
            return {"slug": d.name, "label": label}
    return None


def create(p, force=False):
    """Queue a run. Returns {"run": id}, or {"duplicate": {...}} when the job is already there."""
    inp = clean_input(p)
    with _lock():
        runs = load_runs()
        if not force:
            dup = find_duplicate(inp, runs)
            if dup:
                return {"duplicate": dup}
        run = {"id": datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2),
               "status": "queued", "label": label_for(inp), "input": inp, "created_at": now(),
               "session_id": None, "session_started": False, "turns": 0}
        runs.append(run)
        save_runs(runs)
    return {"run": run["id"]}


def build_prompt(run):
    inp = run["input"]
    lines = ["This is a background run started from the job-search dashboard. Nobody is watching this",
             "chat, and nobody can answer until the run ends.",
             "",
             "Read CLAUDE.md, src/prompts/background_run.md and src/flow3.md, then run Flow 3 for this job.",
             ""]
    if inp.get("url"):
        lines.append(f"Job link: {inp['url']}")
    if inp.get("company"):
        lines.append(f"Company: {inp['company']}")
    if inp.get("job_title"):
        lines.append(f"Job title: {inp['job_title']}")
    if inp.get("page_text"):
        lines += ["", "The job page, pasted by the user (word for word, between the markers):",
                  "<<<JOB PAGE", inp["page_text"], "JOB PAGE>>>"]
    if inp.get("people"):
        lines += ["", "People the user named (true; use them first, see src/prompts/find_contacts.md §0):"]
        for person in inp["people"]:
            parts = [x for x in (person.get("name"), person.get("profile"), person.get("email")) if x]
            note = f' — "{person["note"]}"' if person.get("note") else ""
            lines.append(f"- {PEOPLE_KINDS.get(person['kind'], 'Other contact')}: {' · '.join(parts)}{note}")
    if inp.get("notes"):
        lines += ["", "Notes from the user:", inp["notes"]]
    lines += ["",
              f"Go ahead even if the fit is low: {'yes' if inp.get('go_ahead') else 'no'}",
              f"Tailor the CV for this role: {'yes' if inp.get('tailor_cv') else 'no'}"]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------

def _start(run, settings):
    if not claude_path():
        _finish(run, "failed", error="Claude Code (the claude command) isn't installed on this Mac.")
        return
    d = run_dir(run["id"])
    d.mkdir(parents=True, exist_ok=True)
    # Resume the conversation once Claude has answered in it; before that, start a new one
    resume = bool(run.get("session_started"))
    if resume:
        prompt = run.get("next_prompt") or RETRY_PROMPT
    else:
        run["session_id"] = str(uuid.uuid4())
        prompt = build_prompt(run)
    run["turns"] = run.get("turns", 0) + 1
    prompt_file = d / f"prompt-{run['turns']}.md"
    prompt_file.write_text(prompt, encoding="utf-8")
    events, stderr = d / "events.jsonl", d / "stderr.log"
    events_start = events.stat().st_size if events.exists() else 0
    stderr_start = stderr.stat().st_size if stderr.exists() else 0
    try:
        with open(prompt_file, "rb") as stdin, open(events, "ab") as out, open(stderr, "ab") as err:
            proc = subprocess.Popen(command(run, settings, resume), cwd=str(st.ROOT), stdin=stdin,
                                    stdout=out, stderr=err, env=child_env(), start_new_session=True)
    except OSError as e:
        _finish(run, "failed", error=f"Couldn't start claude: {e}")
        return
    _PROCS[run["id"]] = proc
    _OFFSETS[run["id"]] = events_start
    run.update(status="running", pid=proc.pid, proc_tag=run["session_id"], started_at=now(), finished_at=None,
               next_prompt=None, events_start=events_start, stderr_start=stderr_start, error=None,
               kill_reason=None, kill_sent_at=None, stop_message=None,
               activity="Resuming…" if resume else "Starting Claude…")


def _alive(run):
    proc = _PROCS.get(run["id"])
    if proc is not None:
        if proc.poll() is None:
            return True
        _PROCS.pop(run["id"], None)
        return False
    pid = run.get("pid")
    if not pid:
        return False
    # Started by another process (the dashboard before a restart, or `work`): check the PID is
    # still this run's claude (its command line has the session id it was started with), not a
    # new process that got the same number
    tag = run.get("proc_tag")
    try:
        out = subprocess.run(["ps", "-ww", "-o", "stat=,command=", "-p", str(pid)],
                             capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return False
    return bool(out and tag) and not out.startswith("Z") and tag in out


def _signal(run, sig):
    try:
        os.killpg(run["pid"], sig)  # the run's own process group: claude and the commands it started
    except (ProcessLookupError, PermissionError, TypeError):
        pass


def _stop(run, reason, message=None):
    run.update(kill_reason=reason, kill_sent_at=now(), stop_message=message, activity="Stopping…")
    _signal(run, signal.SIGTERM)


def _check_limits(run, settings):
    """Stop a run that went over run_timeout_minutes; force-kill one that ignores SIGTERM."""
    if run.get("kill_reason"):
        if _age(run.get("kill_sent_at")) > KILL_GRACE_SECONDS:
            _signal(run, signal.SIGKILL)
        return False
    minutes = float(settings.get("run_timeout_minutes") or 40)
    if _age(run.get("started_at")) > minutes * 60:
        _stop(run, "timeout", f"Stopped: it was still going after {minutes:g} minutes.")
        return True
    return False


def describe(name, args):
    """One line for the dashboard about what Claude is doing."""
    if name == "WebSearch":
        return f"Searching: {_short(args.get('query'), 70)}"
    if name == "WebFetch":
        host = urlparse(str(args.get("url") or "")).netloc
        return f"Reading {host[4:] if host.startswith('www.') else host or 'a web page'}"
    if name in ("Write", "Edit", "Read"):
        path, root = str(args.get("file_path") or ""), str(st.ROOT) + os.sep
        return f"{'Reading' if name == 'Read' else 'Writing'} {path[len(root):] if path.startswith(root) else path}"
    if name in ("Glob", "Grep"):
        return "Looking through files"
    if name == "Bash":
        cmd = str(args.get("command") or "")
        if "state.py" in cmd:
            return ("Checking your applications" if re.search(r"state\.py\s+(slug|show|list-all|today)", cmd)
                    else "Updating your tracking")
        return next((text for script, text in SCRIPT_ACTIVITY.items() if script in cmd), "Running a script")
    if name == "StructuredOutput":
        return "Wrapping up"
    return name or "Working"


def slug_in(name, args):
    """The application a tool call writes to (output/<slug>/..., --slug), if any. Reads don't
    count: Claude may look at another application for reference."""
    m = None
    if name in ("Write", "Edit"):
        m = re.search(r"(?:^|/)output/([a-z0-9][a-z0-9-]*)/", str(args.get("file_path") or ""))
    elif name == "Bash":
        cmd = str(args.get("command") or "")
        m = (re.search(r"(?:check_messages|generate_report)\.py\s+\"?([a-z0-9][a-z0-9-]*)", cmd)
             or re.search(r"(?:cv_keywords\.py|state\.py\s+(?:add|sync)).*?--slug[ =]\"?([a-z0-9][a-z0-9-]*)", cmd))
    return m.group(1) if m else None


def _apply_event(run, ev):
    if ev.get("type") in ("system", "result") and ev.get("session_id"):
        run["session_id"] = ev["session_id"]  # what the CLI says it is, for --resume
    if ev.get("type") != "assistant":
        return
    run["session_started"] = True  # Claude answered, so this conversation can be resumed
    for block in (ev.get("message") or {}).get("content") or []:
        if block.get("type") == "text":
            text = (block.get("text") or "").strip()
            if text:
                run["last_text"] = text[-1500:]
            for line in text.splitlines():
                m = STEP_RE.match(line)
                if m:
                    run["step"] = {"n": int(m.group(1)), "text": _short(m.group(2), 80)}
        elif block.get("type") == "tool_use":
            name, args = block.get("name") or "", block.get("input") or {}
            run["activity"] = describe(name, args)
            slug = slug_in(name, args)
            if slug:
                run["slug"] = slug


def _read_events(run):
    """Apply the whole lines added to events.jsonl since the last read. True if there were any."""
    path = run_dir(run["id"]) / "events.jsonl"
    offset = _OFFSETS.get(run["id"], 0)
    try:
        with open(path, "rb") as f:
            f.seek(offset)
            chunk = f.read()
    except OSError:
        return False
    end = chunk.rfind(b"\n") + 1
    if not end:
        return False
    _OFFSETS[run["id"]] = offset + end
    for line in chunk[:end].splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if isinstance(ev, dict):
            _apply_event(run, ev)
    return True


def _last_result(run):
    """The `result` event of the run's latest claude call, if it got that far."""
    try:
        with open(run_dir(run["id"]) / "events.jsonl", "rb") as f:
            f.seek(run.get("events_start") or 0)
            data = f.read()
    except OSError:
        return None
    found = None
    for line in data.splitlines():
        if b'"result"' not in line:
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if isinstance(ev, dict) and ev.get("type") == "result":
            found = ev
    return found


def _stderr_tail(run):
    try:
        with open(run_dir(run["id"]) / "stderr.log", "rb") as f:
            f.seek(run.get("stderr_start") or 0)
            text = f.read()[-4000:].decode("utf-8", "replace")
    except OSError:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return _short(" ".join(lines[-3:]), 600)


def _finish(run, status, result=None, error=None):
    run.update(status=status, finished_at=now(), pid=None, activity=None, error=error,
               kill_reason=None, kill_sent_at=None, stop_message=None)
    if result is not None:
        run["result"] = result
    _PROCS.pop(run["id"], None)


def _finalize(run):
    """Set the outcome of a run whose process has ended, from its last `result` event."""
    result = _last_result(run)
    if result and result.get("total_cost_usd"):
        run["cost_usd"] = round((run.get("cost_usd") or 0) + result["total_cost_usd"], 4)
    out = (result or {}).get("structured_output")
    reason = run.get("kill_reason")
    if reason == "cancelled":
        _finish(run, "cancelled")
    elif isinstance(out, dict) and out.get("status") in RESULT_STATUSES:
        if out.get("slug") and SLUG_RE.match(str(out["slug"])):
            run["slug"] = out["slug"]
        _finish(run, out["status"], result=out,
                error=_short(out.get("summary") or "The run failed.", 600) if out["status"] == "failed" else None)
    elif reason == "timeout":
        _finish(run, "failed", error=run.get("stop_message"))
    elif result and not result.get("is_error") and run.get("slug") and st.find_entry(st.load_state(), run["slug"]):
        # No structured result, but the application was saved
        _finish(run, "done", result={"status": "done", "summary": result.get("result") or ""})
    elif result:
        _finish(run, "failed", error=_short(result.get("result") or result.get("subtype")
                                            or "Claude stopped without a result.", 600))
    else:
        err = _stderr_tail(run)
        _finish(run, "failed" if err else "interrupted", error=err or "The run stopped before it finished.")


def tick():
    """Move the runs along: read progress, finish runs whose process ended, start the next one.

    Called every ~1.5 s by the dashboard server and by `work`. The first call after a restart
    re-reads a running run's events and finishes it if its process is gone. Safe to call from
    several processes: runs.json is locked while it's changed. Returns the runs that ended.
    """
    settings = st.load_settings()
    ended = []
    with _lock():
        runs = load_runs()
        changed = False
        for run in [r for r in runs if r["status"] == "running"]:
            changed |= _read_events(run)
            if _alive(run):
                changed |= _check_limits(run, settings)
                continue
            _read_events(run)
            _finalize(run)
            ended.append(dict(run))
            changed = True
        if not any(r["status"] == "running" for r in runs):
            queued = sorted((r for r in runs if r["status"] == "queued"), key=lambda r: r["created_at"])
            if queued:
                _start(queued[0], settings)
                changed = True
        if changed:
            save_runs(runs)
    for run in ended:
        notify(run, settings)
    return ended


def loop(stop_when_idle=False, on_change=None):
    """Tick forever (the dashboard's background thread), or until nothing is left to run (`work`)."""
    while True:
        try:
            tick()
        except Exception as err:  # a broken file shouldn't stop the queue for good
            print(f"WARNING: background runs: {err}", file=sys.stderr)
        if on_change:
            on_change()
        if stop_when_idle and not any(r["status"] in ACTIVE for r in load_runs()):
            return
        time.sleep(TICK_SECONDS)


def notify(run, settings):
    """A macOS notification when a run ends: done, needs you, skipped or failed."""
    titles = {"done": "Ready", "needs_input": "Claude needs you", "skipped": "Skipped",
              "failed": "Run failed", "interrupted": "Run stopped"}
    if sys.platform != "darwin" or not settings.get("notify_when_done", True) or run["status"] not in titles:
        return
    result = run.get("result") or {}
    name = " — ".join(x for x in (result.get("company"), result.get("job_title")) if x) or run["label"]
    body = result.get("question") if run["status"] == "needs_input" else (run.get("error") or result.get("summary"))
    script = ["-e", "on run argv", "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
              "-e", "end run"]
    try:
        subprocess.Popen(["osascript", *script, f"{titles[run['status']]}: {name}",
                          _short(body, 180) or "Open the dashboard to see it."],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Actions (the dashboard's buttons and the CLI)
# ---------------------------------------------------------------------------

def reply(run_id, text):
    """Answer a run that needs you (or tell a finished one what to do next): resumes its session."""
    text = str(text or "").strip()
    if not text:
        raise ValueError("Write an answer first")
    if len(text) > LIMITS["page_text"]:
        raise ValueError("That answer is too long")
    with _lock():
        runs = load_runs()
        run = _find(runs, run_id)
        if run["status"] in ACTIVE:
            raise ValueError("This run is still going")
        if not run.get("session_started"):
            raise ValueError("Claude never got started on this run: use Retry")
        run.update(status="queued", next_prompt=text, dismissed=False, error=None)
        save_runs(runs)
    return {}


def retry(run_id):
    with _lock():
        runs = load_runs()
        run = _find(runs, run_id)
        if run["status"] in ACTIVE:
            raise ValueError("This run is still going")
        run.update(status="queued", dismissed=False, error=None,
                   next_prompt=RETRY_PROMPT if run.get("session_started") else None)
        save_runs(runs)
    return {}


def cancel(run_id):
    with _lock():
        runs = load_runs()
        run = _find(runs, run_id)
        if run["status"] == "running" and _alive(run):
            _stop(run, "cancelled")  # finished as cancelled once the process is gone
        elif run["status"] in ACTIVE:
            _finish(run, "cancelled")
        else:
            raise ValueError(f"This run is already {run['status'].replace('_', ' ')}")
        save_runs(runs)
    return {}


def dismiss(run_id):
    with _lock():
        runs = load_runs()
        run = _find(runs, run_id)
        if run["status"] in ACTIVE:
            raise ValueError("Cancel the run first")
        run["dismissed"] = True
        save_runs(runs)
    return {}


API = {
    "run-start": lambda p: create(p, force=bool(p.get("force"))),
    "run-reply": lambda p: reply(p.get("id"), p.get("text")),
    "run-retry": lambda p: retry(p.get("id")),
    "run-cancel": lambda p: cancel(p.get("id")),
    "run-dismiss": lambda p: dismiss(p.get("id")),
}


def public_run(run, queued=()):
    """A run as the dashboard shows it: no pasted page, no prompts."""
    slug = run.get("slug")
    meta = (st.load_meta(slug) or {}) if slug else {}
    card = meta.get("role_card") or {}
    result = run.get("result") or {}
    queued = list(queued)
    return {
        "id": run["id"], "status": run["status"], "label": run["label"],
        "company": result.get("company") or meta.get("company"),
        "job_title": result.get("job_title") or meta.get("job_title"),
        "fit_score": card.get("fit_score"), "verdict": card.get("verdict"),
        "step": run.get("step"), "steps": FLOW_STEPS, "activity": run.get("activity"),
        "seconds": int(_age(run["started_at"], run.get("finished_at"))) if run.get("started_at") else None,
        "slug": slug, "report": f"{slug}/report.html" if slug and (st.OUTPUT_DIR / slug).is_dir() else None,
        "summary": result.get("summary"), "question": result.get("question"),
        "options": result.get("options") or [], "error": run.get("error"),
        "session_id": run.get("session_id") if run.get("session_started") else None,
        "stopping": bool(run.get("kill_reason")),
        "position": queued.index(run["id"]) + 1 if run["id"] in queued else None,
    }


def public(limit=10):
    """The runs the dashboard shows, newest first: not hidden, and finished ones only for
    SHOW_FINISHED_DAYS (a run that needs you stays until you answer or hide it)."""
    runs = load_runs()
    queued = [r["id"] for r in sorted(runs, key=lambda r: r["created_at"]) if r["status"] == "queued"]

    def shown(r):
        if r.get("dismissed"):
            return False
        if r["status"] in ACTIVE or r["status"] == "needs_input":
            return True
        return _age(r.get("finished_at") or r["created_at"]) < SHOW_FINISHED_DAYS * 86400

    runs = sorted(filter(shown, runs), key=lambda r: r["created_at"], reverse=True)
    return [public_run(r, queued) for r in runs[:limit]]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _person(kind, value):
    """'Name | https://linkedin... | email | note' (any part optional, any order) -> a person."""
    person = {"kind": kind, "name": "", "profile": "", "email": "", "note": ""}
    plain = []
    for part in (p.strip() for p in value.split("|")):
        if re.match(r"https?://", part, re.IGNORECASE):
            person["profile"] = part
        elif re.match(r"[^@\s]+@[^@\s]+$", part):
            person["email"] = part
        elif part:
            plain.append(part)
    if plain:
        person["name"], person["note"] = plain[0], " ".join(plain[1:])
    return person


def _line(run):
    view = public_run(run)
    name = " — ".join(x for x in (view["company"], view["job_title"]) if x) or view["label"]
    text = f"{run['id']}  {run['status']:<11}  {name}"
    if run["status"] == "running":
        step = run.get("step")
        text += f"  · step {step['n']}: {step['text']}" if step else ""
        text += f"  · {run['activity']}" if run.get("activity") else ""
    elif run.get("error"):
        text += f"  · {run['error']}"
    elif view["question"]:
        text += f"  · {view['question']}"
    return text


def cmd_start(args):
    settings = st.load_settings()
    page = Path(args.page_file).read_text(encoding="utf-8") if args.page_file else ""
    people = [_person(kind, value) for kind, values in (("hr", args.hr), ("lead", args.lead), ("referral", args.knows))
              for value in values or []]
    try:
        res = create({"url": args.url, "company": args.company, "job_title": args.title, "page_text": page,
                      "people": people, "notes": args.notes, "go_ahead": args.go_ahead,
                      "tailor_cv": args.tailor_cv or bool(settings.get("tailor_cv"))}, force=args.force)
    except ValueError as err:
        sys.exit(f"ERROR: {err}")
    if res.get("duplicate"):
        d = res["duplicate"]
        where = f"run {d['run']} ({d['status']})" if d.get("run") else f"output/{d['slug']}/"
        sys.exit(f"Already there: {d['label']}, {where}. Add --force to start anyway.")
    tick()  # starts it now when nothing else is running
    print(f"Queued run {res['run']}. It runs in the background; follow it on the dashboard "
          f"(python3 scripts/serve.py) or here: python3 scripts/runs.py work")


def cmd_list(args):
    runs = sorted(load_runs(), key=lambda r: r["created_at"], reverse=True)
    if not runs:
        print("No runs yet.")
    for run in runs[:args.limit]:
        print(_line(run))


def cmd_show(args):
    run = _find(load_runs(), args.id)
    print(json.dumps(public_run(run), indent=2, ensure_ascii=False))
    print(f"\nFiles: {run_dir(run['id'])}/  (prompt-N.md, events.jsonl, stderr.log)")
    if run.get("session_started"):
        print(f"Take it over in Terminal: cd {st.ROOT} && claude --resume {run['session_id']}")


def cmd_reply(args):
    reply(args.id, args.text)
    tick()
    print("Sent. The run picks up where it stopped.")


def cmd_cancel(args):
    cancel(args.id)
    print("Cancelled.")


def cmd_work(args):
    watched = {r["id"] for r in load_runs() if r["status"] in ACTIVE}
    if not watched:
        print("Nothing queued or running.")
        return
    shown = {}

    def show():
        for run in load_runs():
            if run["status"] in ACTIVE:
                watched.add(run["id"])
            if run["id"] in watched and shown.get(run["id"]) != _line(run):
                shown[run["id"]] = _line(run)
                print(shown[run["id"]], flush=True)

    print("Running the queue. Ctrl+C stops watching; a run that's going keeps going.")
    try:
        loop(stop_when_idle=True, on_change=show)
    except KeyboardInterrupt:
        print("\nStopped watching. The dashboard picks the run up when it starts.")
        return
    for run in load_runs():
        summary = (run.get("result") or {}).get("summary")
        if run["id"] in watched and run["status"] == "done" and summary:
            print(f"\n{summary}")


def cmd_check(args):
    status = claude_status(max_age=0)
    if not status["found"]:
        sys.exit("The claude command isn't installed. See https://docs.claude.com/en/docs/claude-code")
    if not status["logged_in"]:
        sys.exit("claude is installed but not logged in. Run this once in Terminal: claude auth login")
    print(f"OK: {claude_path()} is installed and logged in.")


def main():
    parser = argparse.ArgumentParser(description="Background runs: Flow 3 started from the dashboard")
    sub = parser.add_subparsers(dest="command")

    p_start = sub.add_parser("start", help="Queue a run for a job")
    p_start.add_argument("--url", help="Job link")
    p_start.add_argument("--company")
    p_start.add_argument("--title", help="Job title")
    p_start.add_argument("--page-file", help="A file with the job page text")
    p_start.add_argument("--hr", action="append", help='"Name | LinkedIn URL | email" (any part)')
    p_start.add_argument("--lead", action="append", help='"Name | LinkedIn URL | email"')
    p_start.add_argument("--knows", action="append", help='Someone you know there: "Name | URL | how you know them"')
    p_start.add_argument("--notes", help="Anything else for Claude")
    p_start.add_argument("--go-ahead", action="store_true", help="Carry on even if the fit is low")
    p_start.add_argument("--tailor-cv", action="store_true", help="Tailor the CV for this role")
    p_start.add_argument("--force", action="store_true", help="Start even if this job is already there")

    p_list = sub.add_parser("list", help="Recent runs")
    p_list.add_argument("--limit", type=int, default=15)

    p_show = sub.add_parser("show", help="One run")
    p_show.add_argument("id")

    p_reply = sub.add_parser("reply", help="Answer a run that needs you")
    p_reply.add_argument("id")
    p_reply.add_argument("text")

    p_cancel = sub.add_parser("cancel", help="Stop a queued or running run")
    p_cancel.add_argument("id")

    sub.add_parser("work", help="Run the queue here until it's empty")
    sub.add_parser("check", help="Is the claude CLI installed and logged in?")

    args = parser.parse_args()
    commands = {"start": cmd_start, "list": cmd_list, "show": cmd_show, "reply": cmd_reply,
                "cancel": cmd_cancel, "work": cmd_work, "check": cmd_check}
    handler = commands.get(args.command)
    if not handler:
        parser.print_help()
        sys.exit(1)
    try:
        handler(args)
    except ValueError as err:
        sys.exit(f"ERROR: {err}")


if __name__ == "__main__":
    main()
