# The Claude routine — web-search sweep

This is the companion to the daily GitHub Action. The Action covers the
**APIs** (France Travail, Adzuna) every day. This routine covers the **open web**
the APIs miss — and hands its finds to the same pipeline so they arrive in the
normal daily email, ranked and deduplicated alongside everything else.

## How it fits together

- The routine **only queues finds** into `config/extra_jobs.json` (via
  `python -m jobsearch.extra`) and pushes. It does **not** email or write a report.
- The next Action run ranks + dedups + emails them. Dedup is by URL across all
  sources, so a web find and an API hit for the same role never both send.
- Run it on the **`main`** branch (the Action runs there).

## Cadence

The APIs already give daily freshness, so this sweep is for **breadth**, not
recency. **Weekly (or twice a week) is plenty** — and keeps token cost low.
A good slot is a weekday morning a little before the Action's 06:30 UTC run,
e.g. **Mondays at 06:05 UTC**. (Or run it any time and let the next daily Action
pick the finds up.)

## Routine prompt (paste this into the routine)

> You are running Arthur Dorchies' weekly job-search web sweep. Arthur is a
> full-stack developer (React, Node.js, TypeScript, JavaScript; also
> PowerShell/DevOps/Cloud) based in Roubaix, open to roles in the Lille metro
> area and Brussels, hybrid or on-site, ideally CDI.
>
> 1. Use web search to find **current** developer openings that the France
>    Travail and Adzuna APIs are unlikely to surface — focus on Welcome to the
>    Jungle, LinkedIn, AngelList/Wellfound, company career pages, and niche/tech
>    job boards. Aim for 5–15 genuinely relevant roles. Skip internships,
>    alternance, and pure-Java roles.
> 2. For each, capture: `title`, `company`, `location`, `url` (the real posting,
>    not a search page), `contract` if known, and a one-line `description`.
> 3. Write them as a JSON array to `/tmp/finds.json`, then run:
>    `cat /tmp/finds.json | python -m jobsearch.extra`
>    (It validates, fills defaults, and drops anything already queued or already
>    emailed — so re-runs are safe.)
> 4. If it added at least one role, commit and push `config/extra_jobs.json` to
>    `main` with a message like `web sweep: N new roles`. Then, to deliver
>    immediately rather than waiting for the daily cron, trigger the
>    `daily-job-search.yml` workflow on `main` (GitHub Actions → Run workflow).
> 5. If it added nothing new, do not commit and do not notify — just stop.
>
> Keep it lightweight: do not generate a report or send email yourself; the
> GitHub Action does that. Your only output is queued finds in `extra_jobs.json`.

## Input format `jobsearch.extra` expects

A JSON array; only `url` is required (it's the dedup key and the apply link):

```json
[
  {
    "title": "Développeur Full Stack React/Node",
    "company": "Decathlon Digital",
    "location": "Lille (59)",
    "url": "https://www.welcometothejungle.com/fr/companies/decathlon/jobs/...",
    "contract": "CDI",
    "description": "React + Node.js, hybride, équipe produit."
  }
]
```
