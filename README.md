# Arthur's automated job search

A small, mostly-deterministic pipeline that finds matching IT roles in
Lille / Hauts-de-France and Brussels, ranks them against Arthur's CV,
drafts cover letters, and emails a fresh report **daily** — for ~zero
LLM tokens on a normal day.

## How it works

```
France Travail API ┐
Adzuna API         ├─► rank vs profile ─► dedup ─► render (md + html) ─► email ─► commit
web-search supplement ┘    (config/profile.json)   (state/)         (reports/)   (Resend/SMTP)
```

Two ways it runs:

1. **GitHub Actions (the daily engine, 0 tokens).**
   `.github/workflows/daily-job-search.yml` runs on GitHub's runners (open
   network), calls the APIs, emails the report, and commits it back. This is
   the reliable path and needs no Claude involvement.

2. **Claude routine (optional enrichment).** A scheduled Claude session can add
   a web-search pass for roles the APIs miss (drop them into
   `config/extra_jobs.json`) and rewrite the top cover letters with real
   tailoring. Because the script does all the fetching/ranking/formatting,
   Claude's job is tiny — that's the token saving you asked for.

> **Why not run the APIs from the Claude web environment?** Its egress policy
> blocks outbound calls to `api.francetravail.io`, `api.adzuna.com`, and all
> email hosts (`403 CONNECT tunnel failed`). GitHub Actions has open network,
> so that's where the API + email job lives. (Alternatively, relax this
> environment's network policy to allow those hosts — see the docs link below.)

## One-time setup

### 1. Get free API credentials

- **France Travail** (French offers): create an app at
  <https://francetravail.io>, subscribe to *Offres d'emploi v2*, copy the
  client ID + secret.
- **Adzuna** (FR + BE coverage): register at
  <https://developer.adzuna.com>, copy the app ID + app key.

Both have free tiers sufficient for a daily personal search. The pipeline runs
fine with only one of them configured — a missing source just logs and is
skipped.

### 2. Pick an email transport

- **Resend** (simplest): sign up at <https://resend.com>, create an API key.
  Free tier sends to your own verified address from `onboarding@resend.dev`.
- **or SMTP** (e.g. Gmail): create an [app password](https://myaccount.google.com/apppasswords)
  and use `smtp.gmail.com` / port `587`.

### 3. Add them as GitHub repository secrets

Repo → Settings → Secrets and variables → Actions → *New repository secret*:

| Secret | Needed for |
|--------|-----------|
| `FT_CLIENT_ID`, `FT_CLIENT_SECRET` | France Travail |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Adzuna |
| `RESEND_API_KEY` (+ optional `RESEND_FROM`) | email via Resend |
| *or* `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` (+ optional `SMTP_FROM`) | email via SMTP |

**Never commit secrets** — they live only in GitHub's encrypted store.

### 4. Enable the daily run

Scheduled workflows only fire from the **default branch**, so merge this branch
into `main`. Then it runs every day at 06:30 UTC. Trigger it any time from the
Actions tab → *Daily Job Search* → *Run workflow*.

## Run it locally / by hand

```bash
python -m jobsearch.run --mock        # offline demo with bundled sample roles
python -m jobsearch.run               # live: APIs + email (needs the env vars)
python -m jobsearch.run --no-email    # build the report, don't send
python -m jobsearch.run --keep-seen   # don't update dedup state (re-show roles)
```

Env vars for a live local run are the same names as the secrets above.

## Tuning what counts as a match

Everything is in **`config/profile.json`** — no code changes needed:

- `skills` — keywords matched against title/description (title hits score higher).
- `search` — which queries, départements (59/62), and countries (fr/be) to pull.
- `scoring` — location bonuses (Roubaix/Lille highest), CDI bonus, seniority and
  stage/alternance penalties.
- `report.top_n_cover_letters` — how many letters to draft (default 4).

## Layout

```
config/profile.json        profile + search + scoring config (edit this)
config/extra_jobs.json     web-search supplement, normalized job objects
jobsearch/sources.py       France Travail + Adzuna fetchers (stdlib only)
jobsearch/core.py          scoring, dedup, rendering, cover letters
jobsearch/notify.py        email (Resend or SMTP)
jobsearch/run.py           orchestrator CLI
jobsearch/fixtures/        sample roles for --mock
state/seen_jobs.json       dedup memory (so you only see new roles)
reports/                   generated daily reports (md + html)
.github/workflows/         the daily Action
```

No third-party Python packages — standard library only.

Docs on the Claude web environment & network policies:
<https://code.claude.com/docs/en/claude-code-on-the-web>
