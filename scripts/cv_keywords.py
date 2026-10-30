#!/usr/bin/env python3
"""
cv_keywords.py — which CV to send, and which of the job's keywords it's missing.

Picks the CV version for a role from `cv_variants` in config/settings.json (for example
mobile → cv/main.tex, fullstack → cv/fullstack.tex). Only versions you've approved
("approved": true) are picked. Then it compares the job description's tech keywords with that
CV. Nothing is rewritten: you decide whether a missing keyword is true for you and worth adding.

The job description is read from output/<slug>/jd.md (Flow 3 saves it there), else meta.json's
jd_text, else the snippet in research.md.

Usage:
  python3 scripts/cv_keywords.py --slug acme                  # pick + compare, saves to meta.json
  python3 scripts/cv_keywords.py --slug acme --title "Mobile Engineer" --no-write
  python3 scripts/cv_keywords.py --slug acme --tailored     # after improving output/acme/tailored_cv.tex
  python3 scripts/cv_keywords.py --slug acme --original     # back to the original version
  python3 scripts/cv_keywords.py --jd-file jd.txt --cv cv/main.tex
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from state import OUTPUT_DIR, ROOT, load_meta, load_settings, load_state, find_entry, save_meta  # noqa: E402

# (name, pattern, case_sensitive). Ambiguous words (Go, REST, Room) only count with their usual casing.
KEYWORDS = [
    ("Android", r"\bandroid\b", False), ("iOS", r"\bios\b", False),
    ("Kotlin", r"\bkotlin\b", False), ("Java", r"\bjava\b(?!\s*script)", False),
    ("Swift", r"\bswift\b", False), ("SwiftUI", r"\bswiftui\b", False),
    ("Objective-C", r"\bobjective[- ]?c\b", False), ("Flutter", r"\bflutter\b", False), ("Dart", r"\bdart\b", False),
    ("React Native", r"\breact[- ]native\b", False), ("React", r"\breact(?:\.js|js)?\b(?![- ]native)", False),
    ("TypeScript", r"\btypescript\b", False), ("JavaScript", r"\bjavascript\b", False),
    ("Node.js", r"\bnode(?:\.js|js)\b|\bnode\b(?= ?(?:backend|server))", False), ("Python", r"\bpython\b", False),
    ("Go", r"\bGo\b|\bgolang\b", True), ("C++", r"(?<![\w])c\+\+", False), ("C#", r"(?<![\w])c#", False),
    (".NET", r"(?<![\w])\.net\b", False), ("Rust", r"\brust\b", False),
    ("Jetpack Compose", r"\bjetpack compose\b|(?<!docker )\bcompose\b(?! multiplatform)", False),
    ("Coroutines", r"\bcoroutines?\b", False), ("RxJava", r"\brx(?:java|kotlin)\b", False),
    ("MVVM", r"\bmvvm\b", False), ("MVI", r"\bmvi\b", False), ("Clean Architecture", r"\bclean architecture\b", False),
    ("Dagger/Hilt", r"\b(?:dagger|hilt)\b", False), ("Room", r"\bRoom\b", True), ("SQLite", r"\bsqlite\b", False),
    ("Retrofit", r"\bretrofit\b", False), ("OkHttp", r"\bokhttp\b", False), ("GraphQL", r"\bgraphql\b", False),
    ("REST", r"\bREST(?:ful)?\b", True), ("gRPC", r"\bgrpc\b", False), ("WebSockets", r"\bweb ?sockets?\b", False),
    ("WebRTC", r"\bwebrtc\b", False), ("Kafka", r"\bkafka\b", False), ("RabbitMQ", r"\brabbitmq\b", False),
    ("Spring Boot", r"\bspring boot\b|\bspring (?:framework|security)\b", False),
    ("Microservices", r"\bmicro-?services?\b", False), ("Docker", r"\bdocker\b", False),
    ("Kubernetes", r"\bkubernetes\b|\bk8s\b", False), ("AWS", r"\baws\b|amazon web services", False),
    ("GCP", r"\bgcp\b|google cloud", False), ("Azure", r"\bazure\b", False), ("Firebase", r"\bfirebase\b", False),
    ("CI/CD", r"\bci ?/ ?cd\b|\bcontinuous (?:integration|delivery|deployment)\b", False),
    ("GitHub Actions", r"\bgithub actions\b", False), ("Jenkins", r"\bjenkins\b", False),
    ("Gradle", r"\bgradle\b", False), ("Git", r"\bgit\b", False),
    ("Unit testing", r"\bunit[- ]test(?:s|ing)?\b", False), ("JUnit", r"\bjunit\b", False),
    ("Espresso", r"\bespresso\b", False), ("PostgreSQL", r"\bpostgres(?:ql)?\b", False),
    ("MongoDB", r"\bmongo(?:db)?\b", False), ("Redis", r"\bredis\b", False), ("SQL", r"\bsql\b", False),
    ("LLM", r"\bllms?\b|large language models?", False), ("OpenAI", r"\bopenai\b|\bgpt-?\d?\b", False),
    ("Machine learning", r"\bmachine learning\b|\bML\b", False), ("TensorFlow Lite", r"\btflite\b|tensorflow lite", False),
    ("ML Kit", r"\bml ?kit\b", False), ("Security", r"\bsecurity\b|\bcyber", False),
    ("Obfuscation", r"\bobfuscat", False), ("SSL pinning", r"\b(?:ssl|certificate) pinning\b", False),
    ("MDM", r"\bmdm\b", False), ("Kotlin Multiplatform", r"\bkmp\b|kotlin multiplatform", False),
    ("Compose Multiplatform", r"\bcompose multiplatform\b|\bcmp\b", False),
    ("Bluetooth/BLE", r"\bble\b|bluetooth", False), ("NFC", r"\bnfc\b", False), ("Linux", r"\blinux\b", False),
    ("Embedded", r"\bembedded\b", False), ("RTOS", r"\brtos\b", False), ("Agile", r"\bagile\b|\bscrum\b", False),
    ("Twilio", r"\btwilio\b", False), ("VoIP", r"\bvoip\b", False), ("Reverse engineering", r"\breverse[- ]engineer", False),
    ("Push notifications", r"\bpush notifications?\b|\bfcm\b|\bapns\b", False), ("DICOM", r"\bdicom\b", False),
]
_COMPILED = [(name, re.compile(p) if cs else re.compile(p, re.IGNORECASE)) for name, p, cs in KEYWORDS]


def keywords_in(text):
    return [name for name, rx in _COMPILED if rx.search(text or "")]


def tex_to_text(tex):
    tex = re.sub(r"(?<!\\)%.*", "", tex)  # comments
    for a, b in (("\\#", "#"), ("\\&", "&"), ("\\%", "%"), ("\\_", "_"), ("\\\\", " ")):
        tex = tex.replace(a, b)
    tex = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", " ", tex)  # commands, keep their {arguments}
    return re.sub(r"[{}]", " ", tex)


def read_jd(slug):
    out = OUTPUT_DIR / slug
    jd_file = out / "jd.md"
    if jd_file.exists():
        return jd_file.read_text(encoding="utf-8")
    meta = load_meta(slug) or {}
    if meta.get("jd_text"):
        return meta["jd_text"]
    research = out / "research.md"
    if research.exists():
        m = re.search(r"Job description snippet:\s*(.+?)(?:\n\s*\n|\nFit notes)", research.read_text(encoding="utf-8"),
                      re.DOTALL)
        if m:
            return m.group(1)
    return ""


def pick_variant(title, jd, settings):
    """(name, variant dict, note). Title words count much more than the job description."""
    variants = settings.get("cv_variants") or {}
    if not variants:
        return "base", {"tex": "cv/main.tex", "pdf": "cv/main.pdf"}, "no cv_variants configured, using cv/main"
    title_l, jd_l = (title or "").lower(), (jd or "").lower()[:1500]

    def score(v):
        words = [w.lower() for w in v.get("use_for") or []]
        return 5 * sum(1 for w in words if w in title_l) + sum(jd_l.count(w) for w in words)

    ranked = sorted(variants.items(), key=lambda kv: score(kv[1]), reverse=True)
    approved = [(n, v) for n, v in ranked if v.get("approved", True)]
    default_name = settings.get("cv_default_variant") or next(iter(variants))
    if approved and score(approved[0][1]) > 0:
        name, variant = approved[0]
    else:
        name, variant = default_name, variants[default_name]
    note = ""
    best_name, best = ranked[0]
    if best_name != name and not best.get("approved", True) and score(best) > score(variant):
        note = (f"the '{best_name}' CV would fit this role better, but it isn't approved yet "
                f"(review {best.get('tex')}, then set cv_variants.{best_name}.approved to true)")
    return name, variant, note


def main():
    parser = argparse.ArgumentParser(description="Pick a CV version and list missing job keywords")
    parser.add_argument("--slug")
    parser.add_argument("--title", help="Job title (default: from state / meta.json)")
    parser.add_argument("--jd-file", help="Read the job description from this file instead")
    parser.add_argument("--cv", help="Compare against this .tex instead of picking a variant")
    parser.add_argument("--tailored", action="store_true",
                        help="Use output/<slug>/tailored_cv.tex: this role's improved CV becomes the one to send")
    parser.add_argument("--original", action="store_true",
                        help="Go back to the original CV version for this role (undo the improved one)")
    parser.add_argument("--no-write", action="store_true", help="Don't save the result to meta.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not args.slug and not args.jd_file:
        parser.print_help()
        sys.exit(2)

    settings = load_settings()
    jd = Path(args.jd_file).read_text(encoding="utf-8") if args.jd_file else read_jd(args.slug)
    meta = load_meta(args.slug) if args.slug else None
    entry = find_entry(load_state(), args.slug) if args.slug else None
    title = args.title or (entry or {}).get("job_title") or (meta or {}).get("job_title") or (meta or {}).get("best_fit") or ""

    original = (meta or {}).get("cv_original") or {}
    if args.original and original.get("tex"):
        args.cv = original["tex"]
    if args.tailored:
        if not args.slug:
            parser.error("--tailored needs --slug")
        tex = f"output/{args.slug}/tailored_cv.tex"
        name, variant, note = "tailored", {"tex": tex, "pdf": tex[:-4] + ".pdf"}, ""
    elif args.cv:
        name, variant, note = Path(args.cv).stem, {"tex": args.cv, "pdf": str(Path(args.cv).with_suffix(".pdf"))}, ""
    else:
        name, variant, note = pick_variant(title, jd, settings)
    tex_path = ROOT / variant["tex"]
    if not tex_path.exists():
        print(f"ERROR: {variant['tex']} not found", file=sys.stderr)
        sys.exit(1)
    cv_text = tex_to_text(tex_path.read_text(encoding="utf-8"))
    in_jd = keywords_in(jd)
    in_cv = set(keywords_in(cv_text))
    result = {
        "variant": name, "tex": variant["tex"], "pdf": variant.get("pdf"),
        "matched": [k for k in in_jd if k in in_cv],
        "missing": [k for k in in_jd if k not in in_cv],
        "note": note or None,
        "jd_found": bool(jd.strip()),
    }
    if result["pdf"] and not (ROOT / result["pdf"]).exists():
        build = (args.slug if args.tailored else "--base" if result["tex"] == "cv/main.tex"
                 else f"--variant {name}")
        result["build_hint"] = f"bash scripts/build_cv.sh {build}"

    if args.slug and meta is not None and not args.no_write:
        if args.tailored and meta.get("cv") != "tailored":
            # Remember the version it replaces, for "Back to the original" and the next Improve CV
            original = {"cv": meta.get("cv") or "base", "cv_file": meta.get("cv_file"),
                        "tex": (meta.get("cv_keywords") or {}).get("tex") or "cv/main.tex"}
            if original["tex"].endswith("tailored_cv.tex"):
                original = {"cv": "base", "cv_file": "cv/main.pdf", "tex": "cv/main.tex"}
            meta["cv_original"] = original
        if args.tailored:
            meta["cv"] = "tailored"
        elif args.original and original.get("cv"):
            meta["cv"] = original["cv"]
        else:
            meta["cv"] = f"variant:{name}" if name != "base" else "base"
        meta["cv_file"] = result["pdf"]
        meta["cv_keywords"] = {k: result[k] for k in ("variant", "tex", "matched", "missing", "note")}
        save_meta(args.slug, meta)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    print(f"CV: {result['tex']} ({name})  →  attach {result['pdf']}")
    if note:
        print(f"Note: {note}")
    if not result["jd_found"]:
        print("No job description found: save it to output/<slug>/jd.md first.")
    print(f"In the job and on your CV ({len(result['matched'])}): {', '.join(result['matched']) or '-'}")
    print(f"In the job, not on your CV ({len(result['missing'])}): {', '.join(result['missing']) or '-'}")
    if result.get("build_hint"):
        print(f"PDF not built yet: {result['build_hint']}")


if __name__ == "__main__":
    main()
