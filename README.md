# 📬 Arthur's Daily Job Search

This little tool does Arthur's IT job hunt for him, every morning, automatically.

Each day it searches for developer roles around **Lille** and **Brussels**, keeps
only the ones that fit his CV, ranks them best-first, drafts a cover letter for
the top few, and **emails him the report** — all on its own, for free.

You don't have to run anything by hand. Once it's set up, you just read the email.

---

## What you get

Every day, an email titled **"[Job Search] N new roles — YYYY-MM-DD"** containing:

- 📋 A **ranked table** of new matching roles — job title, company, location, and a link to apply.
- ⭐ A **fit score** for each (higher = closer to Arthur's profile).
- ✍️ **Ready-to-send cover letters** (in French) for the top 4 roles.
- 🧠 A one-line **"why it fits"** for each role.

You only ever see **new** roles — anything reported on a previous day is remembered
and never shown again. On a quiet day with nothing new, it stays silent (no email).

---

## How it works, in one picture

```
   Job websites' APIs          Your CV                 Your inbox
  ┌──────────────────┐   ┌──────────────────┐      ┌──────────────┐
  │  France Travail  │   │  what counts as  │      │  daily email │
  │  Adzuna (FR+BE)  │──▶│  a good match    │──▶  ─▶│  + report in │
  │  + web search    │   │ (config file)    │      │  the repo    │
  └──────────────────┘   └──────────────────┘      └──────────────┘
        find roles          score & rank            email the best,
                            skip duplicates         skip what you've seen
```

It runs on **GitHub Actions** — GitHub's free scheduler — so it works even when
your computer and Claude are off. (Curious about the internals? See
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).)

---

## Set it up once (about 10 minutes)

You need to give the tool (1) permission to read job listings and (2) a way to
send you email. Everything below is free.

### Step 1 — Get the job-search keys

| Service | What it gives you | Where |
|--------|-------------------|-------|
| **France Travail** | French job offers | [francetravail.io](https://francetravail.io) → create an app → subscribe to *Offres d'emploi v2* → copy **client ID** + **secret** |
| **Adzuna** | French + Belgian offers | [developer.adzuna.com](https://developer.adzuna.com) → register → copy **app ID** + **app key** |

> It's fine to set up only one of them — the tool simply uses whatever is available.

### Step 2 — Choose how email gets sent

Pick **one**:

- **Resend** (easiest): sign up at [resend.com](https://resend.com), create an API key. Done.
- **Gmail (or any email)**: create an [app password](https://myaccount.google.com/apppasswords) and use your mail server's address (Gmail = `smtp.gmail.com`, port `587`).

### Step 3 — Paste the keys into GitHub (as "secrets")

In the repository: **Settings → Secrets and variables → Actions → New repository secret**.
Add the ones matching your choices above:

| Secret name | Fill in if you use… |
|-------------|---------------------|
| `FT_CLIENT_ID` / `FT_CLIENT_SECRET` | France Travail |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | Adzuna |
| `RESEND_API_KEY` | Resend email |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` | Gmail/SMTP email |

🔒 Secrets are encrypted by GitHub and never appear in the code. Don't paste them
anywhere else.

### Step 4 — Turn on the daily run

The schedule only starts once this code is on the repository's **main branch**, so
**merge this branch into `main`**. After that it runs every day at **06:30 UTC**
(about 08:30 in Lille).

Want to test it right now? Go to the **Actions** tab → **Daily Job Search** →
**Run workflow**. You should get an email within a minute or two.

---

## Reading your report

The score is just a quick "how well does this match Arthur?" number. Higher is
better. Roughly:

- **Big plus** for the exact stack (React, Node.js, TypeScript, PowerShell) — even more if it's in the job *title*.
- **Plus** for being close to home (Roubaix and Lille score highest), for permanent contracts (CDI), and for remote/hybrid.
- **Minus** for internships/alternance and for senior/lead roles that ask for more years than Arthur has.

A role has to clear a minimum bar to appear at all, so the list is already filtered
down to genuine fits.

---

## Make the matches better

Don't like what's coming through? Everything that decides a match lives in one
plain file — **`config/profile.json`** — and you can edit it without touching code:

- **`skills`** — the keywords it looks for. Add a tech, get more of those roles.
- **`search`** — which areas (départements 59/62) and countries (FR/BE) to search.
- **`scoring`** — how much home-proximity, contract type, and seniority matter.
- **`report.top_n_cover_letters`** — how many cover letters to write (default 4).

Save the file, commit it, and the next run uses your new rules.

Found a great role the APIs missed? Add it to **`config/extra_jobs.json`** and it
gets ranked and included alongside everything else.

---

## Run it yourself (optional)

If you ever want to run it from a terminal instead of waiting for the schedule:

```bash
python -m jobsearch.run --mock      # offline demo using built-in sample roles
python -m jobsearch.run             # the real thing (needs the keys as env vars)
python -m jobsearch.run --no-email  # build the report but don't send it
```

No installation needed — it uses only Python's standard library.

---

## Troubleshooting

| Problem | Likely cause / fix |
|---------|--------------------|
| No email arrived | Check the **Actions** tab for a red run and read the log. Most often a missing/typo'd secret, or email keys not set. |
| The daily schedule never fires | Scheduled runs only work from the **main** branch — make sure this is merged there. |
| "0 new roles" every day | Normal if nothing new was posted. To re-see old roles, clear `state/seen_jobs.json` back to `{"seen": []}`. |
| Roles feel off-target | Tune `config/profile.json` (see above). |
| Want to test without waiting | Actions tab → Daily Job Search → **Run workflow**. |

---

## Good to know

- **Privacy**: your keys live only in GitHub's encrypted secret store; the code never contains them.
- **Cost**: France Travail, Adzuna, Resend, and GitHub Actions all have free tiers that comfortably cover a personal daily search.
- **Heads-up**: job links come from aggregators, which can lag the live posting — always double-check a role is still open before applying.

For how it's built under the hood, see **[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)**.
