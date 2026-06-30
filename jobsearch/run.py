"""Orchestrator CLI: fetch -> rank -> dedup -> render -> email -> persist.

Usage:
  python -m jobsearch.run                 # live APIs, email + commit-ready report
  python -m jobsearch.run --mock          # use fixtures (no network, no creds)
  python -m jobsearch.run --no-email      # build report, skip sending
  python -m jobsearch.run --keep-seen     # don't update state (re-show same roles)

Exit code is always 0 unless something truly unexpected happens, so a cron /
GitHub Action step shows green on a normal "0 new roles" day. The compact
stdout summary is designed to be cheap for an LLM wrapper to read.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import core, notify, sources

ROOT = core.ROOT


def _load_fixture() -> list[dict]:
    path = os.path.join(ROOT, "jobsearch", "fixtures", "sample_jobs.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _load_extra() -> list[dict]:
    """Web-search supplement: roles curated outside the APIs (by the Claude
    routine or by hand) in config/extra_jobs.json, using the same normalized
    schema as the fixtures. Lets non-API sources flow through the same
    ranking + dedup + report pipeline. Missing/empty/invalid file -> []."""
    path = os.path.join(ROOT, "config", "extra_jobs.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Daily job-search pipeline")
    ap.add_argument("--mock", action="store_true", help="use bundled fixtures, no network")
    ap.add_argument("--no-email", action="store_true", help="render only, do not send")
    ap.add_argument("--keep-seen", action="store_true", help="do not update dedup state")
    ap.add_argument("--date", default=None, help="override report date (YYYY-MM-DD)")
    ap.add_argument("--out-dir", default=os.path.join(ROOT, "reports"))
    args = ap.parse_args(argv)

    profile = core.load_profile()
    run_date = args.date or core.utc_today()

    raw = _load_fixture() if args.mock else sources.fetch_all(profile["search"])
    extra = _load_extra()
    if extra:
        print(f"[run] +{len(extra)} web-search supplement offers", file=sys.stderr)
        raw += extra
    print(f"[run] fetched {len(raw)} raw offers", file=sys.stderr)

    ranked = core.rank_jobs(raw, profile)
    seen = core.load_seen()
    fresh = [j for j in ranked if core.job_key(j) not in seen]
    print(f"[run] {len(ranked)} relevant, {len(fresh)} new after dedup", file=sys.stderr)

    if not fresh:
        # Quiet success: nothing new today. Still print a one-line summary.
        print(json.dumps({"date": run_date, "new": 0, "top": []}, ensure_ascii=False))
        return 0

    os.makedirs(args.out_dir, exist_ok=True)
    md = core.render_markdown(fresh, profile, run_date)
    html = core.render_html(fresh, profile, run_date)
    md_path = os.path.join(args.out_dir, f"{run_date}-job-search.md")
    html_path = os.path.join(args.out_dir, f"{run_date}-job-search.html")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(md)
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"[run] wrote {md_path} and {html_path}", file=sys.stderr)

    email_status = "skipped"
    if not args.no_email:
        subject = f"[Job Search] {len(fresh)} new roles — {run_date}"
        ok, detail = notify.send_email(profile["candidate"]["email"], subject, html)
        email_status = detail

    if not args.keep_seen:
        for j in fresh:
            seen.add(core.job_key(j))
        core.save_seen(seen)
        print(f"[run] state updated, {len(seen)} keys tracked", file=sys.stderr)

    # Compact machine-readable summary on stdout (cheap for an LLM wrapper to read).
    print(json.dumps({
        "date": run_date,
        "new": len(fresh),
        "email": email_status,
        "report_md": os.path.relpath(md_path, ROOT),
        "top": [
            {"rank": i, "score": j["score"], "title": j["title"],
             "company": j["company"], "location": j.get("location", ""), "url": j["url"]}
            for i, j in enumerate(fresh[: profile["report"]["max_roles"]], 1)
        ],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
