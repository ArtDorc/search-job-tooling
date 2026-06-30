"""Ingest web-search job finds into config/extra_jobs.json.

This is the handoff between the Claude routine (which searches the open web,
beyond the France Travail / Adzuna APIs) and the deterministic pipeline. The
routine gathers roles and pipes them here as a JSON array; this validates,
normalizes, deduplicates (against the current extras AND roles already emailed),
prunes stale entries, and writes the file back. The next pipeline run then ranks,
dedups, and emails them alongside the API results — no double-sends, because
dedup is by URL across every source.

Usage:
  cat finds.json | python -m jobsearch.extra
  python -m jobsearch.extra --file finds.json
  python -m jobsearch.extra --prune-only          # just drop stale entries

Each input object needs at least a "url" (ideally also title/company/location).
Missing fields are filled with sane defaults.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

from . import core

EXTRA_PATH = f"{core.ROOT}/config/extra_jobs.json"
_FIELDS = ("id", "source", "title", "company", "location", "contract", "url", "date", "description")


def _load_extras() -> list[dict]:
    try:
        with open(EXTRA_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _normalize(obj: dict, today: str) -> dict | None:
    url = (obj.get("url") or "").strip()
    if not url:
        return None  # URL is mandatory: it's the dedup key and the apply link
    return {
        "id": obj.get("id") or url,
        "source": obj.get("source") or "websearch",
        "title": (obj.get("title") or "").strip(),
        "company": (obj.get("company") or "Non précisé").strip(),
        "location": (obj.get("location") or "").strip(),
        "contract": (obj.get("contract") or "").strip(),
        "url": url,
        "date": (obj.get("date") or today)[:10],
        "description": (obj.get("description") or "").strip()[:1200],
    }


def _too_old(entry: dict, cutoff: str) -> bool:
    d = entry.get("date") or ""
    return bool(d) and d < cutoff  # ISO dates compare lexicographically


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ingest web-search finds into extra_jobs.json")
    ap.add_argument("--file", help="read finds from this JSON file instead of stdin")
    ap.add_argument("--keep-days", type=int, default=30, help="drop extras older than N days")
    ap.add_argument("--prune-only", action="store_true", help="only prune stale entries, ingest nothing")
    args = ap.parse_args(argv)

    today = core.utc_today()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=args.keep_days)).strftime("%Y-%m-%d")

    extras = _load_extras()
    before = len(extras)
    extras = [e for e in extras if not _too_old(e, cutoff)]
    pruned = before - len(extras)

    added = skipped = 0
    if not args.prune_only:
        if args.file:
            with open(args.file, encoding="utf-8") as fh:
                raw = fh.read()
        else:
            raw = sys.stdin.read()
        try:
            payload = json.loads(raw) if raw.strip() else []
        except json.JSONDecodeError as exc:
            print(f"[extra] invalid JSON input: {exc}", file=sys.stderr)
            return 1
        if isinstance(payload, dict):
            payload = [payload]

        seen = core.load_seen()                                   # already-emailed roles
        known = {core.job_key(e) for e in extras}                 # already-queued extras
        for obj in payload:
            entry = _normalize(obj, today)
            if entry is None:
                skipped += 1
                continue
            key = core.job_key(entry)
            if key in seen or key in known:
                skipped += 1
                continue
            known.add(key)
            extras.append(entry)
            added += 1

    extras.sort(key=lambda e: e.get("date", ""), reverse=True)
    with open(EXTRA_PATH, "w", encoding="utf-8") as fh:
        json.dump(extras, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print(json.dumps({
        "added": added, "skipped_dupes_or_invalid": skipped,
        "pruned_stale": pruned, "total_queued": len(extras),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
