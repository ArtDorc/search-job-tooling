"""stdin helper: validate, fill defaults, dedup, and merge web-found roles.

Usage:
  cat /tmp/finds.json | python -m jobsearch.extra

Reads a JSON array from stdin.  Each object must have at least `title` and
`url`. Fills defaults for the rest of the normalized schema, then drops:
  - roles already in config/extra_jobs.json  (already queued)
  - roles already in state/seen_jobs.json    (already emailed / deduped)
Appends survivors to config/extra_jobs.json and prints a one-line summary.
Exit 0 always (so callers see a stable return code).
"""
from __future__ import annotations

import json
import os
import re
import sys

from . import core

ROOT = core.ROOT


def _normalize(raw: dict, today: str) -> dict | None:
    """Return a normalized job dict or None if the entry is unusable."""
    url = (raw.get("url") or "").strip()
    title = (raw.get("title") or "").strip()
    if not url or not title:
        return None
    slug = re.sub(r"[^a-z0-9]+", "-", url.lower())[:60].strip("-")
    return {
        "id":          raw.get("id") or slug,
        "source":      (raw.get("source") or "websearch").strip(),
        "title":       title,
        "company":     (raw.get("company") or "").strip() or "Non précisé",
        "location":    (raw.get("location") or "").strip(),
        "contract":    (raw.get("contract") or "").strip(),
        "url":         url,
        "date":        (raw.get("date") or today).strip()[:10],
        "description": (raw.get("description") or "").strip()[:1200],
    }


def main() -> int:
    today = core.utc_today()

    raw_input = sys.stdin.read().strip()
    if not raw_input:
        print("[extra] stdin empty — nothing to add.", file=sys.stderr)
        return 0

    try:
        candidates = json.loads(raw_input)
    except json.JSONDecodeError as exc:
        print(f"[extra] stdin is not valid JSON: {exc}", file=sys.stderr)
        return 0

    if not isinstance(candidates, list):
        print("[extra] stdin must be a JSON array.", file=sys.stderr)
        return 0

    # Normalize inputs
    normalized = []
    for item in candidates:
        n = _normalize(item, today)
        if n:
            normalized.append(n)
        else:
            print(f"[extra] skipped (missing title/url): {item}", file=sys.stderr)

    if not normalized:
        print("[extra] 0 valid entries in input.", file=sys.stderr)
        return 0

    # Load already-queued keys from extra_jobs.json
    extra_path = os.path.join(ROOT, "config", "extra_jobs.json")
    try:
        with open(extra_path, encoding="utf-8") as fh:
            queued = json.load(fh)
        queued = queued if isinstance(queued, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        queued = []
    queued_keys = {core.job_key(j) for j in queued}

    # Load already-emailed keys from seen_jobs.json
    seen_keys = core.load_seen()

    # Filter out duplicates
    fresh = []
    for job in normalized:
        k = core.job_key(job)
        if k in queued_keys:
            print(f"[extra] already queued: {job['title']} — {job['company']}", file=sys.stderr)
        elif k in seen_keys:
            print(f"[extra] already seen: {job['title']} — {job['company']}", file=sys.stderr)
        else:
            fresh.append(job)
            queued_keys.add(k)

    print(f"[extra] {len(fresh)} new / {len(normalized) - len(fresh)} duplicate(s) dropped.",
          file=sys.stderr)

    if not fresh:
        return 0

    # Append to extra_jobs.json
    queued.extend(fresh)
    os.makedirs(os.path.dirname(extra_path), exist_ok=True)
    with open(extra_path, "w", encoding="utf-8") as fh:
        json.dump(queued, fh, ensure_ascii=False, indent=2)

    # Machine-readable summary on stdout (one line per new role for easy grepping)
    for job in fresh:
        print(json.dumps({"added": True, "title": job["title"],
                          "company": job["company"], "url": job["url"]},
                         ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
