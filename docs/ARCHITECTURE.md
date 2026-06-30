# Architecture & Technical Reference

Precise description of how the job-search pipeline is built. For setup and
day-to-day use, see the top-level [`README.md`](../README.md).

---

## 1. Overview

A single deterministic pipeline turns raw job listings into a ranked, deduplicated,
emailed report. It is **pure Python standard library** (no third-party packages) and
designed so that the expensive/repetitive work is code, not LLM tokens.

```
 fetch ──► supplement ──► rank ──► dedup ──► render ──► email ──► persist
   │            │           │        │         │          │          │
 APIs   config/extra_jobs  score   seen_jobs  md+html   Resend/   update state
 (FT,     .json           vs       .json      reports/  SMTP      + commit
 Adzuna)                  profile
```

Every stage is a plain function; `jobsearch/run.py` wires them together and is the
only entry point.

---

## 2. Component map

| File | Responsibility | Network |
|------|----------------|---------|
| `jobsearch/run.py` | Orchestrator CLI: fetch → supplement → rank → dedup → render → email → persist. Prints a compact JSON summary. | — |
| `jobsearch/sources.py` | `fetch_francetravail`, `fetch_adzuna`, `fetch_all`. Normalize provider JSON into the common schema. | outbound HTTPS |
| `jobsearch/core.py` | Profile/state IO, scoring, ranking, dedup key, Markdown + HTML rendering, cover-letter templates. | none |
| `jobsearch/notify.py` | `send_email` over Resend (HTTPS) or SMTP. | outbound |
| `config/profile.json` | All matching/scoring/search parameters. | — |
| `config/extra_jobs.json` | Web-search supplement (normalized job objects). | — |
| `state/seen_jobs.json` | Dedup memory. | — |
| `jobsearch/fixtures/sample_jobs.json` | Offline data for `--mock`. | — |
| `.github/workflows/daily-job-search.yml` | Daily scheduler + email + commit. | — |

---

## 3. Normalized job schema

Every source emits dicts of this exact shape; the rest of the pipeline only ever
sees this schema:

```jsonc
{
  "id":          "provider-specific id",     // string
  "source":      "francetravail|adzuna|fixture|<your label>",
  "title":       "Développeur Full Stack …",
  "company":     "Groupe SII",
  "location":    "Lille (59)",
  "contract":    "CDI",                       // free text; may be empty
  "url":         "https://…",                 // used as the dedup key
  "date":        "2026-06-30",                // YYYY-MM-DD, may be empty
  "description": "… up to ~1200 chars …"
}
```

After ranking, two fields are added: `score` (int) and `matched_skills` (list[str]).

---

## 4. Scoring algorithm

`core.score_job(job, profile) -> (score, matched_skills)`. All matching is
**lowercased** and **boundary-aware**: each skill compiles to
`(?<![a-z0-9])<escaped-skill>(?![a-z0-9])`, so `git` does not match `digital`,
`ejs` does not match `nodejs`, while punctuated skills like `node.js`, `c#`, `ci/cd`
still match. Matchers are cached in `core._SKILL_RE`.

Contributions, applied in order (weights from `profile.json → scoring`):

| Signal | Rule | Default |
|--------|------|---------|
| Skill in **title** | per skill found in the title | `+5` (`skill_in_title`) |
| Skill in **text** | per skill found in title+description+company, if not already counted in title | `+2` (`skill_in_text`) |
| **Location** | per `location_bonus` key found in location *or* text | e.g. roubaix `+7`, lille `+6`, hybride/remote `+3`, bruxelles `+3` |
| **Contract** | per `contract_bonus` key found in contract *or* title | cdi `+4`, freelance `-2`, intérim `-3` |
| **Seniority** | per `seniority_penalty` key found in title | senior `-3`, lead `-4`, principal `-6`, confirmé `-1` |
| **Negatives** | per `negative_keywords` key found in title *or* text | stage / alternance / internship `-10` |

`core.rank_jobs` scores every job, **drops anything with `score <= 0`**, and sorts
descending. `matched_skills` is de-duplicated preserving first-seen order.

The model is intentionally transparent (no ML): every point is traceable to a
keyword rule you can edit in `profile.json`.

---

## 5. Deduplication

`core.job_key(job)` returns the lowercased URL with any trailing `/` removed; if a
job has no URL it falls back to `"<source>:<id>"`. Using the URL means the same
posting is recognized as one even if it arrives from different sources on different
days.

`state/seen_jobs.json` is `{"seen": ["<key>", …]}`. `run.py` keeps only jobs whose
key is absent from that set (`fresh`), then (unless `--keep-seen`) adds every fresh
key back and saves. Reset by writing `{"seen": []}`.

---

## 6. Run modes & I/O contract

Entry point: `python -m jobsearch.run`.

| Flag | Effect |
|------|--------|
| `--mock` | Use `fixtures/sample_jobs.json` instead of calling the APIs. No network/creds. |
| `--no-email` | Render the report but don't send. |
| `--keep-seen` | Don't update `state/seen_jobs.json` (re-show the same roles). |
| `--date YYYY-MM-DD` | Override the report date (default: UTC today). |
| `--out-dir PATH` | Where to write reports (default `reports/`). |

**Outputs:** `reports/<date>-job-search.md` and `…-.html` (the HTML is the email
body). **Exit code is always `0`** on a normal run — including the "0 new roles"
case — so a cron/Action step shows green when there's simply nothing new.

**stdout** is a compact JSON summary, cheap for an LLM wrapper to read:

```json
{ "date": "2026-06-30", "new": 9, "email": "<transport detail>",
  "report_md": "reports/2026-06-30-job-search.md",
  "top": [ {"rank":1,"score":42,"title":"…","company":"…","location":"…","url":"…"}, … ] }
```

On a quiet day it collapses to `{"date":"…","new":0,"top":[]}`. Diagnostics go to
**stderr** (`[run]`, `[sources]`, `[notify]` prefixes).

---

## 7. Sources

Both fetchers are defensive: missing credentials or any exception ⇒ log to stderr
and return `[]`, so one broken source never sinks the run. HTTP via `urllib` (honors
`HTTPS_PROXY`); TLS uses `REQUESTS_CA_BUNDLE`/`SSL_CERT_FILE` if set; 30 s timeout.

### France Travail — *Offres d'emploi v2*

1. **OAuth2 (client credentials)** → `POST https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=%2Fpartenaire`
   with `grant_type=client_credentials`, `client_id`, `client_secret`,
   `scope=api_offresdemploiv2 o2dsoffre`.
2. **Search** → `GET https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search`
   looping `departements × motsCles`, with `range` and optional comma-joined
   `typeContrat`. Accepts HTTP `200` and `206` (partial). Reads `resultats[]`
   (`intitule`, `entreprise.nom`, `lieuTravail.libelle`, `typeContratLibelle`,
   `origineOffre.urlOrigine`, `dateCreation`, `description`).

### Adzuna

`GET https://api.adzuna.com/v1/api/jobs/{country}/search/1` looping
`countries × what`, with `app_id`, `app_key`, `where` (per country),
`results_per_page`, `max_days_old`. Reads `results[]` (`title`,
`company.display_name`, `location.display_name`, `contract_time`/`contract_type`,
`redirect_url`, `created`, `description`).

### Web-search supplement

`run._load_extra()` reads `config/extra_jobs.json` (a JSON array of normalized job
objects) and appends it to the fetched set **before** ranking — so roles found by
web search (by a Claude routine or by hand) are scored and deduped identically.

---

## 8. Email

`notify.send_email(to, subject, html)` selects a transport by environment:

1. `RESEND_API_KEY` set → `POST https://api.resend.com/emails` (`from` =
   `RESEND_FROM` or `onboarding@resend.dev`).
2. else `SMTP_HOST` set → `smtplib`; port `465` uses `SMTP_SSL`, otherwise
   `STARTTLS`. Sends a multipart message with the HTML report as the alternative body.
3. else → log "no transport" and skip (still exits `0`).

Returns `(ok: bool, detail: str)`; never raises into the caller.

---

## 9. Scheduling & delivery

`.github/workflows/daily-job-search.yml`:

- **Triggers**: `schedule: cron "30 6 * * *"` (06:30 UTC) and `workflow_dispatch`.
- **Why GitHub Actions**: its runners have open network; the Claude web environment's
  egress policy blocks the API and email hosts (see §11).
- **Permissions**: `contents: write` to commit results back.
- **Steps**: checkout → setup-python 3.11 → `python -m jobsearch.run` (secrets passed
  as env) → upload `reports/` as a 90-day artifact → commit `reports state` if
  changed (`[skip ci]` to avoid loops).
- **State persistence**: `state/seen_jobs.json` is committed each run, which is how
  dedup survives between days.

> ⚠️ GitHub runs `schedule:` triggers **only from the default branch**. The daily
> cron fires only once this workflow is on `main`. `workflow_dispatch` works from
> any branch.

---

## 10. Environment variables

| Variable | Used by | Required |
|----------|---------|----------|
| `FT_CLIENT_ID`, `FT_CLIENT_SECRET` | France Travail | for FT source |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Adzuna | for Adzuna source |
| `RESEND_API_KEY`, `RESEND_FROM` | Resend email | one transport |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` | SMTP email | one transport |
| `REQUESTS_CA_BUNDLE` / `SSL_CERT_FILE` | TLS trust (auto-set in some envs) | optional |
| `HTTPS_PROXY` | outbound proxy (auto-honored by `urllib`) | optional |

All optional in the sense that missing groups degrade gracefully (a source or the
email step is skipped, never a crash).

### Setup & maintenance (one-time / when rotating keys)

The values above live as **GitHub repository secrets** (Settings → Secrets and
variables → Actions). To set up or change them:

- **France Travail** — create an app at <https://francetravail.io>, subscribe to
  *Offres d'emploi v2*, and use the client ID + secret. (French offers.)
- **Adzuna** — register at <https://developer.adzuna.com> for an app ID + key.
  (French + Belgian offers; optional.)
- **Email — pick one transport:**
  - *Resend* — an API key from <https://resend.com>. On the free tier the default
    `onboarding@resend.dev` sender only delivers to the address you signed up with;
    to send elsewhere, verify a domain and set `RESEND_FROM`.
  - *SMTP* (e.g. Gmail) — enable 2-Step Verification, create an
    [app password](https://myaccount.google.com/apppasswords), and set
    `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USER`/`SMTP_FROM` = your
    address, `SMTP_PASS` = the app password.

`send_email` tries Resend first, then falls back to SMTP, so both may be set.
The daily `schedule:` trigger only fires once the workflow is on the **default
branch**; `workflow_dispatch` (Actions → *Run workflow*) works any time.

---

## 11. Design notes & constraints

- **Stdlib only.** No `pip install` step → faster Actions, no supply-chain surface.
- **Token economy.** Fetch/score/dedup/render/email are deterministic code. An
  optional Claude routine only does what needs judgment (web-search discovery,
  bespoke cover letters), keeping per-day token cost near zero.
- **Egress constraint.** In the Claude web environment, outbound calls to
  `api.francetravail.io`, `api.adzuna.com`, and email hosts return
  `403 CONNECT tunnel failed` from the policy proxy. That is why live fetching/email
  runs on GitHub Actions. To run them from the Claude environment instead, relax that
  environment's network policy to allow those hosts.
- **Failure isolation.** Each source and the email step swallow their own errors and
  report via stderr, so partial failures still produce a report from whatever worked.

---

## 12. Extending: add a new source

1. In `sources.py`, write `fetch_x(cfg) -> list[dict]` returning the §3 schema;
   read credentials from env, catch everything, return `[]` on failure.
2. Call it from `fetch_all` (or append its results in `run.py`).
3. Add any tunables under `profile.json → search.x`.

No other stage needs to change — ranking, dedup, rendering, and email are
source-agnostic.

---

## File map

```
config/profile.json        matching + search + scoring parameters
config/extra_jobs.json     web-search supplement (normalized jobs)
jobsearch/run.py           orchestrator / CLI entry point
jobsearch/sources.py       France Travail + Adzuna fetchers
jobsearch/core.py          scoring, dedup, rendering, cover letters
jobsearch/notify.py        email (Resend / SMTP)
jobsearch/fixtures/        sample roles for --mock
state/seen_jobs.json       dedup memory (committed each run)
reports/                   generated md + html reports
.github/workflows/         daily Action
docs/ARCHITECTURE.md       this document
```
