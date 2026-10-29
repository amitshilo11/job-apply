#!/usr/bin/env python3
"""
serve.py — the dashboard, with buttons that save.

Serves the generated pages (output/) and the CV PDFs at http://localhost:8765. Every click on
a page (connect sent, they accepted, message sent, they replied, I applied, stage changes) is
written to state/applications.json, and the affected pages are rebuilt. Pages are also rebuilt
when you open them, so "overdue" counts and anything Claude changed are always current.

When you edit a message in its box before clicking Sent, the version you sent is added to
config/writing_samples.md (see scripts/samples.py), so future drafts sound more like you.

"+ New application" on the dashboard starts a background run: Claude Code does Flow 3 headless
while you do something else, and the dashboard shows its progress and the result (see
scripts/runs.py). The server runs the queue, one run at a time.

Usage:
  python3 scripts/serve.py              # opens http://localhost:8765 in your browser
  python3 scripts/serve.py --no-open
  python3 scripts/serve.py --port 9000
  python3 scripts/serve.py --lan        # also reachable from your phone on the same Wi-Fi;
                                        # prints a link with a one-time token, nothing works without it
"""

import argparse
import http.server
import json
import os
import posixpath
import secrets
import socket
import sys
import threading
import webbrowser
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate_report as gr  # noqa: E402
import runs  # noqa: E402
import state as st  # noqa: E402
from samples import record_sent  # noqa: E402

LOCK = threading.Lock()
CONFIG = {"token": None, "hosts": set()}
MAX_BODY = 512 * 1024  # a pasted job page fits easily


def _entry(entries, slug):
    entry = st.find_entry(entries, slug or "")
    if not entry:
        raise ValueError(f"no application '{slug}'")
    return entry


def act_event(p):
    entries = st.load_state()
    entry = _entry(entries, p.get("slug"))
    if not st.get_thread(entry, p.get("key")):
        st.sync_threads(entry, st.load_meta(entry["slug"]))
    undo = bool(p.get("undo"))
    st.set_event(entry, p.get("key"), p.get("event"), lang=p.get("lang"),
                 with_note=p.get("with_note"), undo=undo)
    st.save_state(entries)
    learned = None
    if not undo and p.get("text") and p.get("field"):
        result = record_sent(entry["slug"], p["key"], p["field"], p.get("lang"), p["text"])
        if result == "edited":
            learned = "Saved. Your edited version was added to your writing samples."
        elif result == "own":
            learned = "Saved. Your message was added to your writing samples."
    return {"learned": learned}


def act_close_thread(p):
    entries = st.load_state()
    entry = _entry(entries, p.get("slug"))
    st.close_thread(entry, p.get("key"), p.get("reason") or "closed", undo=bool(p.get("undo")))
    st.save_state(entries)
    return {}


def act_task(p):
    entries = st.load_state()
    entry = _entry(entries, p.get("slug"))
    task = p.get("task")
    if task not in st.TASK_TYPES:
        raise ValueError(f"unknown task '{task}'")
    tasks = entry.setdefault("tasks", {})
    if p.get("done"):
        tasks[task] = st.today_str()
        if task == "applied" and not entry.get("stage"):
            entry["stage"] = "applied"
            entry["stage_updated_at"] = st.today_str()
    else:
        tasks.pop(task, None)
        if task == "applied" and entry.get("stage") == "applied":
            entry.pop("stage", None)
    st.save_state(entries)
    return {}


def act_stage(p):
    entries = st.load_state()
    entry = _entry(entries, p.get("slug"))
    stage = p.get("stage") or None
    if stage is not None and stage not in st.STAGES:
        raise ValueError(f"unknown stage '{stage}'")
    today = st.today_str()
    if stage is None:
        entry.pop("stage", None)
        entry.setdefault("stage_notes", []).append({"date": today, "note": "reopened"})
    else:
        entry["stage"] = stage
    entry["stage_updated_at"] = today
    if p.get("note"):
        entry.setdefault("stage_notes", []).append({"date": today, "note": p["note"]})
    st.save_state(entries)
    return {}


ACTIONS = {"event": act_event, "close-thread": act_close_thread, "task": act_task, "stage": act_stage}


def refresh_index():
    entries = st.load_state()
    if st.auto_close(entries, st.today_str(), st.load_settings()):
        st.save_state(entries)
    gr.generate_index()


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(st.ROOT), **kwargs)

    def log_message(self, fmt, *args):
        # Only log saves and errors, not every page and PDF request
        if self.command == "POST" or (len(args) > 1 and str(args[1])[:1] in "45"):
            super().log_message(fmt, *args)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, location, cookie=None):
        self.send_response(302)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Location", location)
        self.end_headers()

    def _allowed(self):
        """Right Host header (blocks DNS-rebinding pages) and, in --lan mode, the token cookie."""
        if self.headers.get("Host", "") not in CONFIG["hosts"]:
            return False
        token = CONFIG["token"]
        if token is None or self.client_address[0] in ("127.0.0.1", "::1"):
            return True
        return f"ja_token={token}" in (self.headers.get("Cookie") or "")

    def do_GET(self):
        url = urlparse(self.path)
        token = CONFIG["token"]
        if token and parse_qs(url.query).get("t", [None])[0] == token \
                and self.headers.get("Host", "") in CONFIG["hosts"]:
            return self._redirect("/output/index.html",
                                  f"ja_token={token}; Path=/; SameSite=Strict; HttpOnly; Max-Age=2592000")
        if not self._allowed():
            return self.send_error(403, "Not allowed. Use the link printed by serve.py.")

        path = posixpath.normpath(unquote(url.path))
        if path in ("/", "/output", "/index.html"):
            return self._redirect("/output/index.html")
        if path == "/api/ping":
            return self._json(200, {"ok": True})
        if path == "/api/runs":
            return self._json(200, {"ok": True, "runs": runs.public(), "claude": runs.claude_status(),
                                    "root": str(st.ROOT)})
        allowed = path.startswith("/output/") or (path.startswith("/cv/") and path.endswith(".pdf"))
        if not allowed:
            return self.send_error(404)

        # Rebuild on view so dates are current and Claude's changes show up
        try:
            with LOCK, st.state_lock():
                if path == "/output/index.html":
                    refresh_index()
                elif path.endswith("/report.html"):
                    slug = path.split("/")[2]
                    if os.path.isdir(st.OUTPUT_DIR / slug):
                        gr.generate_report(slug)
        except Exception as err:  # a broken meta.json shouldn't take the dashboard down
            self.log_error("rebuild failed for %s: %s", path, err)
        self.path = path
        return super().do_GET()

    def do_POST(self):
        url = urlparse(self.path)
        if not url.path.startswith("/api/"):
            return self.send_error(404)
        # The custom header can't be sent cross-site without a CORS preflight, which this
        # server never answers, so other websites can't post here
        if self.headers.get("X-Job-Agent") != "1" or not self._allowed():
            return self._json(403, {"ok": False, "error": "forbidden"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                return self._json(413, {"ok": False, "error": "too much text"})
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._json(400, {"ok": False, "error": "bad request body"})
        if not isinstance(payload, dict):
            return self._json(400, {"ok": False, "error": "bad request body"})
        name = url.path[len("/api/"):]
        if name in runs.API:
            # Background runs keep their own lock (state/runs.json); no page to rebuild
            try:
                result = runs.API[name](payload) or {}
            except ValueError as err:
                return self._json(400, {"ok": False, "error": str(err)})
            self.log_message("%s %s", name, payload.get("id") or result.get("run") or "")
            return self._json(200, dict({"ok": True}, **result))
        handler = ACTIONS.get(name)
        if not handler:
            return self._json(404, {"ok": False, "error": "unknown action"})
        try:
            with LOCK, st.state_lock():
                result = handler(payload) or {}
                slug = payload.get("slug")
                if slug and os.path.isdir(st.OUTPUT_DIR / slug):
                    gr.generate_report(slug)
                gr.generate_index()
        except ValueError as err:
            return self._json(400, {"ok": False, "error": str(err)})
        self.log_message("saved %s %s", url.path, json.dumps({k: v for k, v in payload.items() if k != "text"}))
        return self._json(200, dict({"ok": True}, **result))


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no packet is sent; this just picks the outgoing interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    settings = st.load_settings()
    parser = argparse.ArgumentParser(description="Job search dashboard with buttons that save")
    parser.add_argument("--port", type=int, default=int(settings.get("dashboard_port", 8765)))
    parser.add_argument("--no-open", action="store_true", help="Don't open the browser")
    parser.add_argument("--lan", action="store_true", help="Also serve to your phone on the same Wi-Fi")
    args = parser.parse_args()

    port = args.port
    CONFIG["hosts"] = {f"localhost:{port}", f"127.0.0.1:{port}"}
    bind = "127.0.0.1"
    if args.lan:
        bind = "0.0.0.0"
        CONFIG["token"] = secrets.token_urlsafe(16)
        CONFIG["hosts"].add(f"{lan_ip()}:{port}")

    with LOCK, st.state_lock():
        refresh_index()
        for slug in gr.list_slugs():
            try:
                gr.generate_report(slug)
            except Exception as err:
                print(f"WARNING: couldn't build output/{slug}/report.html: {err}", file=sys.stderr)

    try:
        server = http.server.ThreadingHTTPServer((bind, port), Handler)
    except OSError:
        url = f"http://localhost:{port}/output/index.html"
        print(f"Port {port} is busy, probably the dashboard is already running: {url}")
        if not args.no_open:
            webbrowser.open(url)
        sys.exit(1)

    url = f"http://localhost:{port}/output/index.html"
    # flush: when started in the background (e.g. by /dashboard) the links must show up right away
    print(f"Dashboard: {url}", flush=True)
    if args.lan:
        print(f"Phone (same Wi-Fi): http://{lan_ip()}:{port}/?t={CONFIG['token']}", flush=True)
        print("  Anyone on this Wi-Fi with that link can see your applications. Stop with Ctrl+C when done.",
              flush=True)
    print("Clicks save to state/applications.json. Ctrl+C to stop.", flush=True)
    claude = runs.claude_status()
    if not claude["found"]:
        print("New application needs Claude Code: install it, then run `claude auth login` once.", flush=True)
    elif claude["logged_in"] is False:
        print("New application needs Claude Code logged in: run `claude auth login` once in Terminal.", flush=True)
    # The background-run queue: picks up runs still going from before a restart, starts queued ones
    threading.Thread(target=runs.loop, daemon=True, name="runs").start()
    if not args.no_open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
