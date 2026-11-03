"""Public program metadata collection. No target scanning or private programs."""
from __future__ import annotations

import copy
import re
import threading
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

PLATFORMS = ("hackerone", "bugcrowd", "intigriti", "yeswehack")
DIRECTORY = "https://hackerone.com/opportunities/all"
DATA_ROOT = "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/main/data"
CACHE_SECONDS = 900
FAILURE_SECONDS = 60

# Only public, open programs, excluding sandbox and soft-launched entries.
PROGRAM_QUERY = """
query PublicPrograms($after: String) {
  teams(first: 100, after: $after, where: {
    submission_state: {_eq: open},
    state: {_nin: [sandboxed, soft_launched]},
    _not: {external_program: {}}
  }) {
    nodes { handle name url website offers_bounties submission_state }
    pageInfo { endCursor hasNextPage }
  }
}
"""
SCOPE_QUERY = """
query PublicScopes($handle: String!, $after: String) {
  team(handle: $handle) {
    structured_scopes(first: 100, after: $after, archived: false) {
      nodes { asset_identifier asset_type eligible_for_bounty
        eligible_for_submission instruction max_severity }
      pageInfo { endCursor hasNextPage }
    }
  }
}
"""


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class CollectionError(Exception):
    pass


class CSRFParser(HTMLParser):
    token = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and attrs.get("name") == "csrf-token":
            self.token = attrs.get("content")


def session():
    client = requests.Session()
    client.headers.update({"User-Agent": "bbcollect/1.0 (public program metadata)"})
    # Retry idempotent reads only; do not aggressively retry GraphQL requests.
    client.mount("https://", HTTPAdapter(max_retries=Retry(
        total=2, backoff_factor=1, status_forcelist=[429, 502, 503, 504],
        allowed_methods=["GET"], respect_retry_after_header=False)))
    return client


def get_json(response):
    response.raise_for_status()
    try:
        return response.json()
    except ValueError as exc:
        raise CollectionError("Upstream returned a non-JSON response") from exc


def hackerone_pages(query, field, handle=None):
    with session() as client:
        response = client.get(DIRECTORY, timeout=(10, 30))
        response.raise_for_status()
        parser = CSRFParser()
        parser.feed(response.text)
        if not parser.token:
            raise CollectionError("HackerOne did not provide a public session token")
        client.headers.update({"X-CSRF-Token": parser.token, "Referer": DIRECTORY})
        cursor, seen, nodes = None, set(), []
        for _ in range(100):
            variables = {"after": cursor}
            if handle is not None:
                variables["handle"] = handle
            payload = get_json(client.post("https://hackerone.com/graphql",
                json={"query": query, "variables": variables}, timeout=(10, 30)))
            if payload.get("errors"):
                raise CollectionError("HackerOne rejected the public GraphQL query")
            connection = payload.get("data", {}).get(field)
            if handle is not None:
                connection = connection.get("structured_scopes") if connection else None
            if not isinstance(connection, dict) or not isinstance(connection.get("nodes"), list):
                raise CollectionError("HackerOne program not found or response schema changed")
            nodes.extend(connection["nodes"])
            page = connection.get("pageInfo", {})
            if not page.get("hasNextPage"):
                return nodes
            cursor = page.get("endCursor")
            if not cursor or cursor in seen:
                raise CollectionError("HackerOne returned an invalid pagination cursor")
            seen.add(cursor)
            time.sleep(0.15)
        raise CollectionError("HackerOne exceeded the pagination safety limit")


def bounty_value(value):
    if isinstance(value, dict):
        return value.get("value")
    return value


def normalize(platform, row):
    url = row.get("url") or ""
    handle = str(row.get("handle") or row.get("id") or urlsplit(url).path.rstrip("/").split("/")[-1])
    # Intigriti handles are unique within a company, not across the platform.
    if platform == "intigriti":
        handle = str(row.get("id") or f"{row.get('company_handle', '')}--{handle}")
    if platform == "yeswehack" and not url:
        url = f"https://yeswehack.com/programs/{handle}"
    maximum = bounty_value(row.get("max_bounty", row.get("max_payout")))
    paid = row.get("offers_bounties")
    if paid is None and isinstance(maximum, (int, float)):
        paid = maximum > 0
    return {"id": f"{platform}:{handle}", "platform": platform, "handle": handle,
            "name": row.get("name", handle), "url": url,
            "website": row.get("website"), "offers_bounties": paid,
            "min_bounty": row.get("min_bounty"),
            "max_bounty": row.get("max_bounty", row.get("max_payout")),
            "submission_state": row.get("submission_state", row.get("status")),
            "targets": row.get("targets")}


class Collector:
    def __init__(self):
        self._cache = {}
        self._lock = threading.RLock()

    def _cached(self, key, loader):
        # Serialize fills so simultaneous callers do not duplicate upstream crawls.
        with self._lock:
            entry = self._cache.get(key)
            if entry and entry[0] > time.monotonic():
                result = copy.deepcopy(entry[1])
                result["cached"] = True
                return result
            try:
                result = loader()
            except (requests.RequestException, CollectionError, ValueError, KeyError, TypeError) as exc:
                # Do not include session headers, cookies, or raw upstream bodies.
                result = {"ok": False, "error": type(exc).__name__,
                          "message": "Source unavailable or response schema changed; retry later.",
                          "fetched_at": utcnow()}
            result["cached"] = False
            ttl = CACHE_SECONDS if result["ok"] else FAILURE_SECONDS
            self._cache[key] = (time.monotonic() + ttl, copy.deepcopy(result))
            return result

    def dataset(self, platform):
        def load():
            url = f"{DATA_ROOT}/{platform}_data.json"
            with session() as client:
                response = client.get(url, timeout=(10, 45))
                data = get_json(response)
            if not isinstance(data, list) or not data or not all(
                isinstance(row, dict) and row.get("name") for row in data
            ):
                raise CollectionError("Invalid program dataset")
            return {"ok": True, "mode": "public_dataset", "source_url": url,
                    "fetched_at": utcnow(), "source_updated_at": response.headers.get("Last-Modified"),
                    "programs": [normalize(platform, row) for row in data]}
        return self._cached(("dataset", platform), load)

    def programs(self, platform):
        if platform != "hackerone":
            return self.dataset(platform)

        def load():
            try:
                data = hackerone_pages(PROGRAM_QUERY, "teams")
                if not data:
                    raise CollectionError("HackerOne returned an empty directory")
                return {"ok": True, "mode": "live", "source_url": DIRECTORY,
                        "fetched_at": utcnow(), "source_updated_at": None,
                        "programs": [normalize(platform, row) for row in data]}
            except (requests.RequestException, CollectionError, ValueError, KeyError, TypeError):
                fallback = self.dataset(platform)
                fallback["warning"] = "Live HackerOne collection failed; using a public dataset snapshot."
                return fallback
        return self._cached(("programs", platform), load)

    def collect(self, platforms=None, search="", bounty_only=False, limit=100, offset=0):
        platforms = ["hackerone"] if platforms is None else platforms
        if not isinstance(platforms, list) or any(p not in PLATFORMS for p in platforms):
            raise ValueError("Choose platforms from: " + ", ".join(PLATFORMS))
        if not platforms:
            raise ValueError("Select at least one platform")
        limit, offset = int(limit), int(offset)
        if not 1 <= limit <= 1000 or not 0 <= offset <= 100000:
            raise ValueError("limit must be 1–1000; offset must be 0–100000")
        query = search.strip().casefold()
        programs, sources = {}, {}
        for platform in dict.fromkeys(platforms):
            result = self.programs(platform)
            sources[platform] = {k: v for k, v in result.items() if k != "programs"}
            for program in result.get("programs", []):
                if bounty_only and program["offers_bounties"] is not True:
                    continue
                if query and query not in " ".join(str(program.get(k) or "") for k in
                    ("name", "handle", "url", "website")).casefold():
                    continue
                programs[program["id"]] = {k: v for k, v in program.items() if k != "targets"}
        ordered = sorted(programs.values(), key=lambda p: (p["platform"], p["name"].casefold(), p["id"]))
        ok = any(s["ok"] for s in sources.values())
        return {"ok": ok, "partial": ok and any(not s["ok"] for s in sources.values()),
                "generated_at": utcnow(), "total": len(ordered), "limit": limit, "offset": offset,
                "next_offset": offset + limit if offset + limit < len(ordered) else None,
                "sources": sources, "programs": ordered[offset:offset + limit]}

    def scope(self, platform="hackerone", handle="security"):
        if platform not in PLATFORMS or not re.fullmatch(r"[A-Za-z0-9_.-]{1,200}", handle):
            raise ValueError("Provide a supported platform and a program handle returned by /collect")
        if platform == "hackerone":
            def load():
                nodes = hackerone_pages(SCOPE_QUERY, "team", handle)
                return {"ok": True, "mode": "live", "source_url": f"https://hackerone.com/{handle}",
                        "fetched_at": utcnow(), "source_updated_at": None,
                        "targets": {"in_scope": [n for n in nodes if n.get("eligible_for_submission") is True],
                                    "out_of_scope": [n for n in nodes if n.get("eligible_for_submission") is not True]}}
            live = self._cached(("scope", platform, handle), load)
            if live["ok"]:
                return {"platform": platform, "handle": handle, **live}
        result = self.dataset(platform)
        metadata = {k: v for k, v in result.items() if k != "programs"}
        if platform == "hackerone":
            metadata["warning"] = "Live scope unavailable; using a public dataset snapshot."
        for program in result.get("programs", []):
            if program["handle"] == handle:
                return {"platform": platform, "handle": handle, **metadata,
                        "targets": program["targets"]}
        return {"platform": platform, "handle": handle, **metadata, "ok": False,
                "message": "Program not found in the available public data", "targets": None}


collector = Collector()
