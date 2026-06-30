"""Job-source fetchers: France Travail (Offres d'emploi v2) and Adzuna.

Pure stdlib (urllib). Returns normalized dicts:
  {id, source, title, company, location, contract, url, date, description}

Credentials come from environment variables (never hard-code):
  FT_CLIENT_ID, FT_CLIENT_SECRET          -> France Travail
  ADZUNA_APP_ID, ADZUNA_APP_KEY           -> Adzuna

Each fetcher returns [] (and logs to stderr) on any error or missing creds,
so one broken source never sinks the whole run.
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.parse
import urllib.request

_TIMEOUT = 30


def _ssl_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    bundle = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE")
    if bundle and os.path.exists(bundle):
        try:
            ctx.load_verify_locations(bundle)
        except ssl.SSLError:
            pass
    return ctx


def _log(msg: str) -> None:
    print(f"[sources] {msg}", file=sys.stderr)


def _get(url: str, headers: dict | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=_TIMEOUT, context=_ssl_ctx()) as r:
        return r.status, r.read()


def _post_form(url: str, data: dict, headers: dict | None = None) -> tuple[int, bytes]:
    body = urllib.parse.urlencode(data).encode()
    hdr = {"Content-Type": "application/x-www-form-urlencoded", **(headers or {})}
    req = urllib.request.Request(url, data=body, headers=hdr, method="POST")
    with urllib.request.urlopen(req, timeout=_TIMEOUT, context=_ssl_ctx()) as r:
        return r.status, r.read()


# ---------------------------------------------------------------- France Travail

FT_TOKEN_URL = ("https://entreprise.francetravail.fr/connexion/oauth2/access_token"
                "?realm=%2Fpartenaire")
FT_SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"


def _ft_token() -> str | None:
    cid = os.environ.get("FT_CLIENT_ID")
    secret = os.environ.get("FT_CLIENT_SECRET")
    if not (cid and secret):
        _log("France Travail: FT_CLIENT_ID / FT_CLIENT_SECRET not set, skipping.")
        return None
    try:
        status, raw = _post_form(FT_TOKEN_URL, {
            "grant_type": "client_credentials",
            "client_id": cid,
            "client_secret": secret,
            "scope": "api_offresdemploiv2 o2dsoffre",
        })
        return json.loads(raw).get("access_token") if status < 400 else None
    except Exception as exc:  # noqa: BLE001 - never let a source crash the run
        _log(f"France Travail token error: {exc}")
        return None


def fetch_francetravail(cfg: dict) -> list[dict]:
    token = _ft_token()
    if not token:
        return []
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    out, seen = [], set()
    for dept in cfg.get("departements", ["59"]):
        for mots in cfg.get("motsCles", ["développeur"]):
            params = {
                "departement": dept,
                "motsCles": mots,
                "range": cfg.get("range", "0-49"),
            }
            tc = cfg.get("typeContrat")
            if tc:
                params["typeContrat"] = ",".join(tc)
            url = FT_SEARCH_URL + "?" + urllib.parse.urlencode(params)
            try:
                status, raw = _get(url, headers)
                if status not in (200, 206) or not raw:
                    continue
                for o in json.loads(raw).get("resultats", []):
                    oid = o.get("id")
                    if not oid or oid in seen:
                        continue
                    seen.add(oid)
                    lt = o.get("lieuTravail", {}) or {}
                    out.append({
                        "id": oid,
                        "source": "francetravail",
                        "title": o.get("intitule", ""),
                        "company": (o.get("entreprise", {}) or {}).get("nom", "") or "Non précisé",
                        "location": lt.get("libelle", "") or f"Dépt {dept}",
                        "contract": o.get("typeContratLibelle") or o.get("typeContrat", ""),
                        "url": (o.get("origineOffre", {}) or {}).get("urlOrigine", "")
                               or f"https://candidat.francetravail.fr/offres/recherche/detail/{oid}",
                        "date": (o.get("dateCreation", "") or "")[:10],
                        "description": (o.get("description", "") or "")[:1200],
                    })
            except Exception as exc:  # noqa: BLE001
                _log(f"France Travail search error (dept={dept}, q='{mots}'): {exc}")
    _log(f"France Travail: {len(out)} offers.")
    return out


# ---------------------------------------------------------------- Adzuna

ADZUNA_URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/1"


def fetch_adzuna(cfg: dict) -> list[dict]:
    app_id = os.environ.get("ADZUNA_APP_ID")
    app_key = os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        _log("Adzuna: ADZUNA_APP_ID / ADZUNA_APP_KEY not set, skipping.")
        return []
    out, seen = [], set()
    where_by_country = cfg.get("where", {})
    for country in cfg.get("countries", ["fr"]):
        for what in cfg.get("what", ["full stack developer"]):
            params = {
                "app_id": app_id,
                "app_key": app_key,
                "what": what,
                "results_per_page": cfg.get("results_per_page", 25),
                "max_days_old": cfg.get("max_days_old", 14),
                "content-type": "application/json",
            }
            where = where_by_country.get(country)
            if where:
                params["where"] = where
            url = ADZUNA_URL.format(country=country) + "?" + urllib.parse.urlencode(params)
            try:
                status, raw = _get(url, {"Accept": "application/json"})
                if status >= 400 or not raw:
                    continue
                for r in json.loads(raw).get("results", []):
                    rid = str(r.get("id", ""))
                    if not rid or rid in seen:
                        continue
                    seen.add(rid)
                    out.append({
                        "id": rid,
                        "source": "adzuna",
                        "title": r.get("title", ""),
                        "company": (r.get("company", {}) or {}).get("display_name", "") or "Non précisé",
                        "location": (r.get("location", {}) or {}).get("display_name", ""),
                        "contract": r.get("contract_time", "") or r.get("contract_type", ""),
                        "url": r.get("redirect_url", ""),
                        "date": (r.get("created", "") or "")[:10],
                        "description": (r.get("description", "") or "")[:1200],
                    })
            except Exception as exc:  # noqa: BLE001
                _log(f"Adzuna error (country={country}, q='{what}'): {exc}")
    _log(f"Adzuna: {len(out)} offers.")
    return out


def fetch_all(search_cfg: dict) -> list[dict]:
    jobs = []
    jobs += fetch_francetravail(search_cfg.get("francetravail", {}))
    jobs += fetch_adzuna(search_cfg.get("adzuna", {}))
    return jobs
