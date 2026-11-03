"""Public, unauthenticated REST v1 interface alongside the Gradio API."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from enum import Enum
import threading
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Path, Query, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from collector import CACHE_SECONDS, FAILURE_SECONDS, PLATFORMS, collector, utcnow

VERSION = "1.0.0"
_work_slots = threading.BoundedSemaphore(2)


class Platform(str, Enum):
    hackerone = "hackerone"
    bugcrowd = "bugcrowd"
    intigriti = "intigriti"
    yeswehack = "yeswehack"


class ProgramRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: Platform
    handle: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.-]+$",
                        description="Use the exact handle returned by the programs endpoint.")


class BatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    programs: list[ProgramRef] = Field(min_length=1, max_length=20)


class Payload(BaseModel):
    """Shared envelope; platform-native policy and reward structures remain JSON."""
    model_config = ConfigDict(extra="allow")
    ok: bool
    partial: bool = False
    api_version: str = VERSION


class ErrorInfo(BaseModel):
    code: str
    message: str
    details: list[dict[str, Any]] | None = None


class ErrorPayload(BaseModel):
    ok: Literal[False] = False
    api_version: str = VERSION
    error: ErrorInfo


class ProgramResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    platform: Platform
    handle: str
    name: str
    url: str
    offers_bounties: bool | None = None
    min_bounty: float | None = None
    max_bounty: float | None = None
    currency: str | None = None
    targets: dict[str, Any] | None = None
    rules: dict[str, Any] | None = None
    reward_table: Any = None
    details_source: dict[str, Any] | None = None
    field_status: dict[str, str] | None = None


class ProgramPage(Payload):
    total: int
    limit: int
    offset: int
    next_offset: int | None
    include_details: bool
    sources: dict[str, dict[str, Any]]
    programs: list[ProgramResult]
    filters: dict[str, Any]


class ProgramDetails(Payload):
    platform: str
    handle: str
    targets: dict[str, Any] | None = None
    rules: dict[str, Any] | None = None
    reward_table: Any = None
    min_bounty: float | None = None
    max_bounty: float | None = None
    currency: str | None = None
    field_status: dict[str, str] | None = None
    mode: str | None = None
    source_url: str | None = None
    fetched_at: str | None = None
    source_updated_at: str | None = None
    warning: str | None = None
    cached: bool = False


class BatchResult(Payload):
    count: int
    succeeded: int
    programs: list[ProgramDetails]


class Asset(BaseModel):
    identifier: str
    type: str
    native_type: str | int | None
    instructions: str | None
    eligible_for_bounty: bool | None
    raw: Any


class AssetPage(Payload):
    platform: str
    handle: str
    total: int
    limit: int
    offset: int
    next_offset: int | None
    in_scope: list[Asset]
    out_of_scope: list[Asset]
    rules: dict[str, Any] | None = None
    source: dict[str, Any]
    note: str


ERRORS = {code: {"model": ErrorPayload, "description": label} for code, label in (
    (400, "Invalid filter combination"), (422, "Invalid query or request body"),
    (429, "Collection capacity busy; retry after the Retry-After header"),
    (503, "Required upstream data is unavailable"))}


def envelope(result):
    return {"api_version": VERSION, **result}


def bad_request(message):
    raise HTTPException(400, {"code": "invalid_filters", "message": message})


def parse_platforms(value):
    selected = list(dict.fromkeys(p.strip().lower() for p in value.split(",") if p.strip()))
    if not selected or any(p not in PLATFORMS for p in selected):
        bad_request("platforms must contain comma-separated values from: " + ", ".join(PLATFORMS))
    return selected


@contextmanager
def work_slot():
    if not _work_slots.acquire(blocking=False):
        raise HTTPException(429, {"code": "busy", "message": "Collection capacity is busy; retry in a few seconds."},
                            headers={"Retry-After": "5"})
    try:
        yield
    finally:
        _work_slots.release()


def require_data(result):
    if not result.get("ok"):
        raise HTTPException(503, {"code": "source_unavailable",
                                 "message": "Public program data was not found or is temporarily unavailable."})
    return envelope(result)


def normalize_asset(asset):
    """Common identifiers/types, retaining the complete native asset record."""
    if isinstance(asset, str):
        return {"identifier": asset, "type": "other", "native_type": None,
                "instructions": None, "eligible_for_bounty": None, "raw": asset}
    identifier = next((asset[k] for k in ("asset_identifier", "scope", "endpoint", "target", "uri", "name", "ipAddress")
                       if asset.get(k)), "")
    native = asset.get("asset_type", asset.get("scope_type", asset.get("category", asset.get("type", asset.get("typeId")))))
    types = {1: "url", 2: "android", 3: "ios", 4: "ip_range", 5: "device", 6: "other", 7: "wildcard",
             "website": "url", "web-application": "url", "url": "url", "wildcard": "wildcard",
             "api": "api", "cidr": "ip_range", "iprange": "ip_range", "ip_range": "ip_range",
             "ip_address": "ip", "ip": "ip", "android": "android", "ios": "ios",
             "apple_store_app_id": "ios", "google_play_app_id": "android", "domain": "domain"}
    key = native.lower() if isinstance(native, str) else native
    kind = types.get(key, "other")
    return {"identifier": str(identifier), "type": kind, "native_type": native,
            "instructions": asset.get("instruction", asset.get("description")),
            "eligible_for_bounty": asset.get("eligible_for_bounty"), "raw": asset}


def create_api():
    app = FastAPI(title="bbconnectapi", version=VERSION,
        description="Public bug bounty program metadata, rewards, scopes and policies. "
                    "No API key, login or Authorization header required. "
                    "Directory summaries are fast; live details can take longer. "
                    "Check partial/source status before using results.",
        docs_url="/api/docs", redoc_url="/api/redoc", openapi_url="/api/openapi.json",
        servers=[{"url": "/", "description": "Current host"}],
        openapi_tags=[{"name": "Programs", "description": "Search public programs and retrieve details."},
                      {"name": "Assets", "description": "Normalized assets with native records and exclusions."},
                      {"name": "Service", "description": "Readiness, supported sources and directory statistics."}])
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST", "OPTIONS"],
                       allow_headers=["Content-Type"], allow_credentials=False,
                       expose_headers=["Retry-After", "X-API-Version"])

    @app.middleware("http")
    async def version_header(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["X-API-Version"] = VERSION
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": "http_error", "message": str(exc.detail)}
        return JSONResponse(status_code=exc.status_code, headers=exc.headers,
                            content={"ok": False, "api_version": VERSION, "error": detail})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        details = [{"location": list(e["loc"]), "message": e["msg"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"ok": False, "api_version": VERSION,
            "error": {"code": "validation_error", "message": "Check the request parameters.", "details": details}})

    @app.get("/api/v1/health", tags=["Service"], response_model=Payload,
             summary="Check application readiness without contacting platforms")
    def health():
        return {"ok": True, "api_version": VERSION, "authentication_required": False,
                "generated_at": utcnow(), "upstream_checked": False,
                "docs_url": "/api/docs", "openapi_url": "/api/openapi.json"}

    @app.get("/api/v1/sources", tags=["Service"], response_model=Payload,
             summary="Describe data sources, capabilities and cache lifetimes")
    def sources():
        return envelope({"ok": True, "authentication_required": False,
            "cache_seconds": CACHE_SECONDS, "failure_cache_seconds": FAILURE_SECONDS,
            "platforms": [{"platform": p, "directory": "live_with_dataset_fallback" if p == "hackerone" else "public_dataset",
                           "details": "live_with_dataset_fallback", "rules": "live_only"} for p in PLATFORMS],
            "limits": {"full_detail_page": 100, "summary_page": 1000, "batch_programs": 20},
            "availability": "Public programs only. Fields may be unpublished; fallbacks can be partial."})

    @app.get("/api/v1/programs", tags=["Programs"], response_model=ProgramPage, responses=ERRORS,
             summary="Search and paginate programs; summaries by default")
    def programs(
        platforms: str = Query("hackerone", description="Comma-separated platform names; use /sources for supported values."),
        search: str = Query("", max_length=300, description="Case-insensitive substring in name, handle, URL or website."),
        bounty_only: bool = False,
        limit: int = Query(25, ge=1, le=1000), offset: int = Query(0, ge=0, le=100000),
        include_details: bool = Query(False, description="Live rewards, targets and rules for this page; maximum limit 100."),
        currency: str | None = Query(None, pattern=r"^[A-Za-z]{3}$", description="ISO currency code; excludes unknown currencies."),
        reward_at_least: float | None = Query(None, ge=0, allow_inf_nan=False,
            description="Require advertised max_bounty >= this amount. Requires currency; applied to directory metadata."),
        sort_by: Literal["name", "max_bounty", "min_bounty"] = "name",
        descending: bool = False,
    ):
        selected = parse_platforms(platforms)
        if (reward_at_least is not None or sort_by != "name") and currency is None:
            bad_request("Set currency when filtering or sorting by bounty amounts; currencies are never mixed.")
        if include_details and limit > 100:
            bad_request("include_details=true supports limit <= 100; use summary pages for larger limits.")
        with work_slot():
            # Fetch the complete small directory before filtering/sorting/pagination.
            result = collector.collect(selected, search, bounty_only, 1000, 0, False)
            require_data(result)
            if result.get("next_offset") is not None:
                # A platform may grow beyond one summary page.
                items = list(result["programs"])
                cursor = result["next_offset"]
                while cursor is not None:
                    extra = collector.collect(selected, search, bounty_only, 1000, cursor, False)
                    require_data(extra)
                    items.extend(extra["programs"])
                    cursor = extra["next_offset"]
                result["programs"] = items
            rows = result["programs"]
            if currency:
                rows = [p for p in rows if (p.get("currency") or "").upper() == currency.upper()]
            if reward_at_least is not None:
                rows = [p for p in rows if isinstance(p.get("max_bounty"), (int, float)) and p["max_bounty"] >= reward_at_least]
            if sort_by == "name":
                rows.sort(key=lambda p: (p["name"].casefold(), p["id"]), reverse=descending)
            else:
                known = [p for p in rows if isinstance(p.get(sort_by), (int, float))]
                unknown = [p for p in rows if not isinstance(p.get(sort_by), (int, float))]
                known.sort(key=lambda p: (p[sort_by], p["id"]), reverse=descending)
                rows = known + sorted(unknown, key=lambda p: p["id"])
            total = len(rows)
            page = rows[offset:offset + limit]
            if include_details and page:
                def enrich(p):
                    detail = collector.details(p["platform"], p["handle"])
                    fields = ("targets", "rules", "reward_table", "field_status", "currency", "min_bounty", "max_bounty")
                    return {**p, **{k: detail[k] for k in fields if k in detail},
                            "details_source": {k: v for k, v in detail.items() if k not in fields}}
                with ThreadPoolExecutor(max_workers=4) as pool:
                    page = list(pool.map(enrich, page))
            partial = result.get("partial", False) or any(
                p.get("details_source", {}).get("partial") or p.get("details_source", {}).get("ok") is False for p in page)
        return envelope({**result, "programs": page, "total": total, "limit": limit, "offset": offset,
            "next_offset": offset + limit if offset + limit < total else None,
            "include_details": include_details, "partial": partial,
            "filters": {"currency": currency.upper() if currency else None, "reward_at_least": reward_at_least,
                        "reward_filter_source": "directory_metadata", "sort_by": sort_by, "descending": descending}})

    @app.post("/api/v1/programs/batch", tags=["Programs"], response_model=BatchResult,
              responses={**ERRORS, 503: {"model": BatchResult, "description": "All requested program lookups failed; inspect each item."}},
              summary="Retrieve details for up to 20 programs; preserve input order")
    def batch(body: BatchRequest, response: Response):
        with work_slot():
            def lookup(ref):
                return collector.details(ref.platform.value, ref.handle)
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lookup, body.programs))
        successes = sum(bool(r.get("ok")) for r in results)
        if not successes:
            response.status_code = 503
        return envelope({"ok": successes > 0, "partial": any(not r.get("ok") or r.get("partial") for r in results),
                         "count": len(results), "succeeded": successes, "programs": results})

    @app.get("/api/v1/programs/{platform}/{handle}", tags=["Programs"], response_model=ProgramDetails, responses=ERRORS,
             summary="Retrieve public program rewards, rules, scopes and exclusions")
    def program(platform: Platform, handle: str = Path(pattern=r"^[A-Za-z0-9_.-]{1,200}$")):
        with work_slot():
            return require_data(collector.details(platform.value, handle))

    @app.get("/api/v1/programs/{platform}/{handle}/assets", tags=["Assets"], response_model=AssetPage, responses=ERRORS,
             summary="Get normalized assets; all exclusions remain visible")
    def assets(platform: Platform, handle: str = Path(pattern=r"^[A-Za-z0-9_.-]{1,200}$"),
               asset_type: Literal["url", "api", "domain", "wildcard", "ip", "ip_range", "android", "ios", "device", "other"] | None = None,
               search: str = Query("", max_length=300), limit: int = Query(100, ge=1, le=1000),
               offset: int = Query(0, ge=0, le=100000)):
        with work_slot():
            detail = require_data(collector.details(platform.value, handle))
        targets = detail.get("targets")
        if not isinstance(targets, dict):
            raise HTTPException(503, {"code": "scope_unavailable", "message": "No scope data is available for this program."})
        rows = [normalize_asset(a) for a in targets.get("in_scope", [])]
        rows = [a for a in rows if (asset_type is None or a["type"] == asset_type) and search.casefold() in a["identifier"].casefold()]
        exclusions = [normalize_asset(a) for a in targets.get("out_of_scope", [])]
        return envelope({"ok": True, "partial": detail.get("partial", False), "platform": platform.value,
                         "handle": handle, "total": len(rows), "limit": limit, "offset": offset,
                         "next_offset": offset + limit if offset + limit < len(rows) else None,
                         "in_scope": rows[offset:offset + limit], "out_of_scope": exclusions,
                         "rules": detail.get("rules"), "field_status": detail.get("field_status"),
                         "source": {k: detail.get(k) for k in ("mode", "source_url", "fetched_at", "source_updated_at", "cached", "warning")},
                         "note": "Filters/pagination apply only to in_scope. All exclusions and program rules are retained."})

    @app.get("/api/v1/stats", tags=["Service"], response_model=Payload, responses=ERRORS,
             summary="Count directory programs without fetching live detail documents")
    def stats(platforms: str = "hackerone,bugcrowd,intigriti,yeswehack"):
        selected = parse_platforms(platforms)
        sources, counts = {}, {}
        with work_slot():
            for p in selected:
                result = collector.programs(p)
                rows = list({r["id"]: r for r in result.get("programs", [])}.values())
                counts[p] = {"total": len(rows),
                             "offers_bounties": sum(r.get("offers_bounties") is True for r in rows),
                             "unknown_bounty_status": sum(r.get("offers_bounties") is None for r in rows)}
                sources[p] = {k: v for k, v in result.items() if k != "programs"}
        ok = any(s.get("ok") for s in sources.values())
        result = {"ok": ok, "partial": any(not s.get("ok") for s in sources.values()), "generated_at": utcnow(),
                  "total": sum(c["total"] for c in counts.values()), "platforms": counts, "sources": sources}
        return require_data(result)

    return app
