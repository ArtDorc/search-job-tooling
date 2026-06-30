# 📬 Arthur's Daily Job Search

Every morning this finds developer roles around **Lille** and **Brussels** that fit
your CV, ranks them, drafts cover letters for the best ones, and **emails you the
report**. It runs on its own — you just read the email.

---

## What lands in your inbox

Each day (around **08:30**, Lille time) you get an email — *"[Job Search] N new roles"* — with:

- 📋 A **ranked table** of new roles: title, company, location, and a link to apply.
- ⭐ A **fit score** for each (higher = closer to your profile).
- 🧠 A one-line **"why it fits"**.
- ✍️ **Ready-to-send cover letters** (French) for the top 4.

You only ever see **new** roles — anything from a previous day is remembered and
never repeated. Nothing new today? No email. Simple.

---

## Reading the score

It's a quick "how well does this match Arthur?" number. Roughly:

- **Big plus** for your stack (React, Node.js, TypeScript, PowerShell) — more if it's in the job title.
- **Plus** for being close to home (Roubaix and Lille score highest), for permanent contracts (CDI), and for remote/hybrid.
- **Minus** for internships/alternance, for senior/lead roles asking more years than you have, and for off-stack roles (e.g. Java).

Only roles above a minimum bar appear, so the list is already filtered to real fits.

---

## Tweaking what you receive

Everything that decides a match is in one plain file — **`config/profile.json`** —
editable without touching code:

- **`skills`** — the keywords it looks for. Add a tech, get more of those roles.
- **`search`** — which areas (départements 59/62) and countries (FR/BE) to search.
- **`scoring`** — how much home-proximity, contract type, and seniority matter.
- **`report.top_n_cover_letters`** — how many cover letters to draft (default 4).

Found a great role the search missed? Add it to **`config/extra_jobs.json`** and it
gets ranked and included like the rest.

Edit, commit, and the next morning's run uses your new rules.

---

## Getting a report right now

Don't want to wait for tomorrow?

- **Easiest:** GitHub → **Actions** tab → **Daily Job Search** → **Run workflow**.
- **From a terminal:** `python -m jobsearch.run` (no installation needed — standard library only).

---

## If something looks off

| What you see | What it means |
|--------------|---------------|
| "0 new roles" / no email | Normal — nothing new was posted today. |
| Roles feel off-target | Tune `config/profile.json` (see above). |
| You want to re-see every role | Reset `state/seen_jobs.json` to `{"seen": []}`. |
| An email didn't arrive | Open the **Actions** tab and read the latest run's log — the last line says what happened. |

---

*Heads-up: job links come from aggregators and can lag the live posting — double-check a role is still open before applying.*

*How it's built, and how to change the email setup or API keys later: see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).*
