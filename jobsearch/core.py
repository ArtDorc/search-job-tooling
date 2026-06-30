"""Core logic: scoring, dedup, rendering, cover letters. Pure stdlib, no network."""
from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Cache of boundary-aware matchers so "git" doesn't match "digital",
# "ejs" doesn't match "nodejs", "api" doesn't match arbitrary words, etc.
_SKILL_RE: dict[str, re.Pattern] = {}


def _skill_matcher(skill: str) -> re.Pattern:
    pat = _SKILL_RE.get(skill)
    if pat is None:
        # Match the skill only when not flanked by other alphanumerics, so its
        # own punctuation (node.js, c#, ci/cd) is preserved but substrings are not.
        pat = re.compile(rf"(?<![a-z0-9]){re.escape(skill.lower())}(?![a-z0-9])")
        _SKILL_RE[skill] = pat
    return pat


def load_profile(path: str | None = None) -> dict:
    path = path or os.path.join(ROOT, "config", "profile.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_seen(path: str | None = None) -> set[str]:
    path = path or os.path.join(ROOT, "state", "seen_jobs.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return set(data.get("seen", []))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_seen(seen: set[str], path: str | None = None) -> None:
    path = path or os.path.join(ROOT, "state", "seen_jobs.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"seen": sorted(seen)}, fh, ensure_ascii=False, indent=2)


def job_key(job: dict) -> str:
    """Stable dedup key. Prefer URL (most reliable across runs), else source:id."""
    url = (job.get("url") or "").strip().lower().rstrip("/")
    if url:
        return url
    return f"{job.get('source', '?')}:{job.get('id', '?')}"


# ---------------------------------------------------------------- scoring

def _all_skills(profile: dict) -> list[str]:
    skills = profile["skills"]
    return skills["core"] + skills["devops"] + skills["learning"]


def score_job(job: dict, profile: dict) -> tuple[int, list[str]]:
    """Return (score, matched_skills). Transparent, keyword-based."""
    sc = profile["scoring"]
    title = (job.get("title") or "").lower()
    text = " ".join(str(job.get(k) or "") for k in ("title", "description", "company")).lower()
    location = (job.get("location") or "").lower()
    contract = (job.get("contract") or "").lower()

    score = 0
    matched: list[str] = []
    for skill in _all_skills(profile):
        matcher = _skill_matcher(skill)
        if matcher.search(title):
            score += sc["skill_in_title"]
            matched.append(skill)
        elif matcher.search(text):
            score += sc["skill_in_text"]
            matched.append(skill)

    # All categories use boundary-aware matching too, so e.g. a "java" penalty
    # never fires on "javascript", and "59" never matches inside a postal code.
    for needle, bonus in sc["location_bonus"].items():
        m = _skill_matcher(needle)
        if m.search(location) or m.search(text):
            score += bonus
    for needle, bonus in sc["contract_bonus"].items():
        m = _skill_matcher(needle)
        if m.search(contract) or m.search(title):
            score += bonus
    for needle, pen in sc["seniority_penalty"].items():
        if _skill_matcher(needle).search(title):
            score += pen
    for needle, pen in sc["negative_keywords"].items():
        m = _skill_matcher(needle)
        if m.search(title) or m.search(text):
            score += pen

    # de-duplicate matched skills, keep order
    seen, uniq = set(), []
    for m in matched:
        if m.lower() not in seen:
            seen.add(m.lower())
            uniq.append(m)
    return score, uniq


def rank_jobs(jobs: list[dict], profile: dict) -> list[dict]:
    """Attach score + matched skills, sort best-first, drop clearly-irrelevant (score<=0)."""
    out = []
    for job in jobs:
        score, matched = score_job(job, profile)
        if score <= 0:
            continue
        out.append({**job, "score": score, "matched_skills": matched})
    out.sort(key=lambda j: j["score"], reverse=True)
    return out


# ---------------------------------------------------------------- cover letters

_DEVOPS_HINTS = ("devops", "cloud", "infrastructure", "sre", "système", "systeme", "ops ")


def _is_devops(job: dict) -> bool:
    t = (job.get("title") or "").lower()
    return any(h in t for h in _DEVOPS_HINTS)


def cover_letter(job: dict, profile: dict) -> str:
    """Template FR cover letter (dev or devops variant). A solid baseline an
    LLM run can later refine; on its own it is already sendable."""
    cand = profile["candidate"]
    company = job.get("company") or "votre entreprise"
    title = job.get("title") or "le poste proposé"
    skills = ", ".join(job.get("matched_skills", [])[:6]) or "React, Node.js, TypeScript"
    sig = f"{cand['name']}\n{cand['phone']} — {cand['email']}"

    if _is_devops(job):
        return (
            f"Madame, Monsieur,\n\n"
            f"Votre offre de {title} chez {company} correspond directement à l'expérience "
            f"que j'ai développée en 2024-2025 comme DevOps/Cloud Engineer chez Archimed à Lille, "
            f"où j'ai conçu des applications avec PowerShell, React et SQL, géré une infrastructure "
            f"cloud OVH et produit la documentation technique associée.\n\n"
            f"Ma pratique de PowerShell (y compris PowerShell Universal pour des portails et API "
            f"internes), de Git, des API et des bases SQL/noSQL constitue une base solide pour "
            f"m'investir sur vos environnements d'intégration continue et de déploiement, que je "
            f"suis prêt à approfondir. Mon passage antérieur en industrie pharmaceutique "
            f"réglementée (GSK Vaccine, Grade A/B) m'a par ailleurs ancré une rigueur procédurale "
            f"et une culture de l'amélioration continue directement utiles en production.\n\n"
            f"Je serais ravi d'échanger avec vous lors d'un entretien.\n\n"
            f"Cordialement,\n{sig}\n"
        )
    return (
        f"Madame, Monsieur,\n\n"
        f"Développeur Full-stack chez Archimed à Lille, je vous propose ma candidature pour le "
        f"poste de {title} au sein de {company}.\n\n"
        f"Au quotidien, j'interviens sur l'ensemble du cycle projet : analyse des besoins, "
        f"rédaction de spécifications fonctionnelles et techniques, développement front-end "
        f"(React, TypeScript, Tailwind) et back-end (Node.js, Express, SQL et noSQL), intégration "
        f"de solutions, correction d'anomalies et livraison client. Les compétences attendues "
        f"dans votre offre ({skills}) recoupent largement ma pratique actuelle.\n\n"
        f"Rigoureux, orienté solution et habitué au travail d'équipe — qualités affinées par "
        f"plusieurs années d'enseignement et par la gestion de la relation client — je suis "
        f"convaincu de pouvoir contribuer rapidement à vos projets, tout en poursuivant ma montée "
        f"en compétences (actuellement C#/.NET).\n\n"
        f"Je reste à votre disposition pour un entretien.\n\n"
        f"Cordialement,\n{sig}\n"
    )


# ---------------------------------------------------------------- rendering

def _why_fit(job: dict) -> str:
    skills = ", ".join(job.get("matched_skills", [])[:5])
    base = f"Recoupe le profil sur : {skills}." if skills else "Profil compatible."
    if _is_devops(job):
        base += " Correspond à l'expérience DevOps/Cloud (PowerShell, OVH) d'Arthur."
    return base


def render_markdown(jobs: list[dict], profile: dict, run_date: str) -> str:
    rep = profile["report"]
    top = jobs[: rep["max_roles"]]
    lines = [
        f"# Daily Job Search Report — {run_date}",
        "",
        f"Candidate: **{profile['candidate']['name']}** — {profile['candidate']['base_location']}",
        f"New matching roles found: **{len(jobs)}** (showing top {len(top)}).",
        "",
        "## Ranked roles",
        "",
        "| # | Score | Role | Company | Location | Link |",
        "|---|-------|------|---------|----------|------|",
    ]
    for i, j in enumerate(top, 1):
        lines.append(
            f"| {i} | {j['score']} | {j['title']} | {j['company']} | "
            f"{j.get('location', '')} | [offer]({j['url']}) |"
        )
    lines += ["", "## Why each fits", ""]
    for i, j in enumerate(top, 1):
        lines.append(f"{i}. **{j['title']} — {j['company']}** ({j.get('location','')}): {_why_fit(j)}")

    n = rep["top_n_cover_letters"]
    lines += ["", f"## Tailored cover letters (top {n})", ""]
    for i, j in enumerate(top[:n], 1):
        lines += [
            f"### {i}. {j['company']} — {j['title']}",
            f"Link: {j['url']}",
            "",
            "```",
            cover_letter(j, profile).rstrip(),
            "```",
            "",
        ]
    lines += [
        "---",
        "_Generated by the automated job-search pipeline. Verify each listing is still "
        "open before applying — aggregator pages can lag the live posting._",
    ]
    return "\n".join(lines)


def render_html(jobs: list[dict], profile: dict, run_date: str) -> str:
    rep = profile["report"]
    top = jobs[: rep["max_roles"]]
    e = html.escape
    rows = "".join(
        f"<tr><td>{i}</td><td style='text-align:center'>{j['score']}</td>"
        f"<td>{e(j['title'])}</td><td>{e(j['company'])}</td>"
        f"<td>{e(j.get('location',''))}</td>"
        f"<td><a href='{e(j['url'])}'>offer</a></td></tr>"
        for i, j in enumerate(top, 1)
    )
    why = "".join(
        f"<li><b>{e(j['title'])} — {e(j['company'])}</b> ({e(j.get('location',''))}): {e(_why_fit(j))}</li>"
        for j in top
    )
    letters = "".join(
        f"<h3>{i}. {e(j['company'])} — {e(j['title'])}</h3>"
        f"<p><a href='{e(j['url'])}'>{e(j['url'])}</a></p>"
        f"<pre style='white-space:pre-wrap;background:#f6f8fa;padding:12px;border-radius:6px'>"
        f"{e(cover_letter(j, profile))}</pre>"
        for i, j in enumerate(top[: rep["top_n_cover_letters"]], 1)
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:820px;margin:auto;color:#222">
<h1>Daily Job Search — {e(run_date)}</h1>
<p>Candidate: <b>{e(profile['candidate']['name'])}</b> — {e(profile['candidate']['base_location'])}<br>
New matching roles: <b>{len(jobs)}</b> (top {len(top)} shown).</p>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%">
<thead><tr><th>#</th><th>Score</th><th>Role</th><th>Company</th><th>Location</th><th>Link</th></tr></thead>
<tbody>{rows}</tbody></table>
<h2>Why each fits</h2><ul>{why}</ul>
<h2>Tailored cover letters</h2>{letters}
<hr><p style="color:#888;font-size:13px">Generated automatically. Verify each listing is still open
before applying — aggregator pages can lag the live posting.</p>
</body></html>"""


def utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
