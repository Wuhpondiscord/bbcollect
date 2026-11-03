# API reference · v1

Base: `https://wuhp-bbconnectapi.hf.space/api/v1`

**All endpoints are public. Do not send an API key, HF token, login cookie, or Authorization header.** The deployment secret is unrelated to calling this API.

[Interactive docs](https://wuhp-bbconnectapi.hf.space/api/docs) · [OpenAPI JSON](https://wuhp-bbconnectapi.hf.space/api/openapi.json) · [Examples](EXAMPLES.md)

## List programs

`GET /programs`

| Query parameter | Default | Meaning |
| --- | --- | --- |
| `platforms` | `hackerone` | Comma-separated `hackerone`, `bugcrowd`, `intigriti`, `yeswehack`; case-insensitive |
| `search` | empty | Case-insensitive substring in name, handle, program URL, or website; not policy/asset text |
| `bounty_only` | `false` | Include only programs known to offer bounties; unknown status is excluded |
| `include_details` | `false` | Retrieve live rewards, scopes, rules, and tables for the selected page |
| `limit` | `25` | 1–1000 for summaries; 1–100 with full details |
| `offset` | `0` | 0–100000; use the returned `next_offset` |
| `currency` | unset | Three-letter currency code, case-insensitive; excludes unknown currencies |
| `reward_at_least` | unset | Require advertised directory `max_bounty` >= amount; requires `currency` |
| `sort_by` | `name` | `name`, `max_bounty`, or `min_bounty`; bounty sorting requires `currency` |
| `descending` | `false` | Reverse the selected sort; unknown bounty values always come last |

```bash
curl 'https://wuhp-bbconnectapi.hf.space/api/v1/programs?platforms=hackerone&currency=USD&reward_at_least=1000&sort_by=max_bounty&descending=true&limit=10'
```

Filtering/sorting uses directory metadata before pagination and live enrichment. It does not fetch every program's reward table to decide eligibility. Missing snapshot currencies/reward values can exclude otherwise matching programs; use individual details for current values. No currency conversion is performed.

Response shape (illustrative values):

```json
{
  "ok": true,
  "partial": false,
  "api_version": "1.0.0",
  "total": 200,
  "limit": 10,
  "offset": 0,
  "next_offset": 10,
  "include_details": false,
  "programs": [{
    "id": "hackerone:security",
    "platform": "hackerone",
    "handle": "security",
    "name": "HackerOne",
    "url": "https://hackerone.com/security",
    "offers_bounties": true,
    "min_bounty": 100,
    "max_bounty": 15000,
    "currency": "usd"
  }],
  "sources": {},
  "filters": {
    "currency": null,
    "reward_at_least": null,
    "reward_filter_source": "directory_metadata",
    "sort_by": "name",
    "descending": false
  }
}
```

The example is abbreviated; generated response models also allow native/source metadata. Optional detail fields are null in summary responses. `total` counts filtered directory programs, not only the returned page. `next_offset: null` means the crawl is finished. IDs include the platform; Intigriti uses its program UUID as `handle` because company URL slugs can repeat.

With `include_details=true`, each program also has `targets`, `rules`, `reward_table`, `field_status`, and `details_source`. Any failed/partial detail lookup makes the page `partial: true`; inspect each program rather than discarding the whole page.

## Get program details

`GET /programs/{platform}/{handle}`

```bash
curl 'https://wuhp-bbconnectapi.hf.space/api/v1/programs/hackerone/security'
```

Use handles from `/programs`. Successful responses include:

| Field | Description |
| --- | --- |
| `ok`, `partial`, `api_version` | Result status and REST contract version |
| `platform`, `handle` | Requested program identity |
| `min_bounty`, `max_bounty`, `currency` | Published numeric range and currency; null when unavailable |
| `reward_table` | Native severity/asset-tier table or grid, preserving its descriptions |
| `targets.in_scope`, `targets.out_of_scope` | Native platform records, kept separate |
| `rules` | Native policy sections; fields vary by platform, described below |
| `field_status` | Availability for scopes, rules, and ranges |
| `mode` | `live` or `public_dataset` |
| `source_url`, `fetched_at`, `source_updated_at`, `cached`, `warning` | Provenance, retrieval time, last edit if known, fallback/cache state |

HackerOne rules include policy text, scope description, structured policy, disclosure/safe-harbor declarations, and exclusions. Bugcrowd includes brief HTML, targets overview, target-group instructions, safe harbor, resources, and VRT rules. Intigriti includes the latest in/out-of-scope text, FAQs, severity assessment, and rules of engagement/testing requirements. YesWeHack includes policy text/HTML, qualifying/non-qualifying vulnerabilities, account requirements, and relevant program rule grids.

Policy HTML is data, not trusted executable markup. Referenced external documents remain links; the API does not recursively crawl them. Absence of a rule never implies permission to test.

Fallback responses have `partial: true`: dataset scopes and known rewards may remain available, while `rules` is null and its `field_status` is `unavailable`. Live fields may be marked `not_published` rather than being invented. `0` is a published zero; `null` is not zero.

A missing or unreachable program returns `503 source_unavailable` when no usable public data exists. The API cannot always distinguish an unknown program from upstream denial/outage, so it does not falsely claim a definitive program 404.

## Normalized program assets

`GET /programs/{platform}/{handle}/assets`

Optional queries: `asset_type`, `search`, `limit` (1–1000, default 100), `offset` (default 0).

Common asset types: `url`, `api`, `domain`, `wildcard`, `ip`, `ip_range`, `android`, `ios`, `device`, `other`. Unsupported native categories become `other`, with their native type retained.

```bash
curl 'https://wuhp-bbconnectapi.hf.space/api/v1/programs/hackerone/security/assets?asset_type=wildcard&limit=20'
```

Each normalized record has `identifier`, `type`, `native_type`, `instructions`, `eligible_for_bounty`, and `raw` (the complete original record). Out-of-scope prose can be a native string, retained in `raw`.

Response fields: `in_scope`, `out_of_scope`, `rules`, `source`, `field_status`, `total`, `limit`, `offset`, `next_offset`, `ok`, `partial`, `api_version`, `note`.

**Asset filtering and pagination apply only to `in_scope`. Every exclusion and the full program rules are retained.** `total` is the filtered in-scope count. A wildcard never overrides an exclusion or a restriction in the rules. Group instructions remain in the native `raw` record.

## Batch program details

`POST /programs/batch`

```bash
curl -X POST 'https://wuhp-bbconnectapi.hf.space/api/v1/programs/batch' \
  -H 'Content-Type: application/json' \
  -d '{"programs":[{"platform":"hackerone","handle":"security"},{"platform":"yeswehack","handle":"outscale"}]}'
```

Body: `programs`, an array of 1–20 objects containing `platform` and `handle`; unknown body fields are rejected. Results preserve input order (including duplicates), with individual statuses. Response: `ok`, `partial`, `api_version`, `count`, `succeeded`, `programs`.

If any lookup succeeds, HTTP status is 200, even when other items fail. If all fail, status is 503 **with the same batch result envelope**, so you can still inspect every item. A success that uses dataset fallback can itself be partial.

## Service metadata

| Endpoint | Behavior |
| --- | --- |
| `GET /health` | Application readiness/version, `authentication_required: false`, `upstream_checked: false`; no upstream calls |
| `GET /sources` | Per-platform capabilities, cache times, public-access status, and request limits; no upstream calls |
| `GET /stats?platforms=hackerone,bugcrowd` | Directory totals, known bounty counts, unknown bounty status, and source states; all four platforms by default |

Healthy application status does not guarantee that every upstream platform is reachable. Stats do not fetch individual live detail documents. Free hosted Spaces can sleep, making the first request slow.

## Errors, capacity, and retries

| HTTP status | Meaning | Action |
| --- | --- | --- |
| `200` | Successful response, possibly partial | Check `ok`, `partial`, and per-item/source states |
| `400` | Invalid filter combination/platform list | Fix the query; see error message |
| `422` | Invalid type, enum, bounds, or JSON body | Inspect `error.details` |
| `429` | Both REST collection slots are busy | Wait for `Retry-After` seconds, then retry |
| `503` | No usable upstream data, or every batch item failed | Retry with backoff; inspect fallback/field availability |

Ordinary errors use:

```json
{"ok":false,"api_version":"1.0.0","error":{"code":"invalid_filters","message":"Set currency when filtering or sorting by bounty amounts; currencies are never mixed."}}
```

Validation errors add `error.details` entries with `location`, `message`, `type`. All-failed batch responses use the batch envelope instead. Responses include `X-API-Version`. REST responses are not HTTP-cached (`Cache-Control: no-store`), while source data is shared in an in-memory cache.

REST collection capacity is two concurrent requests per application process, not a per-user key quota. Each batch/detail page uses at most four workers. Prefer summary listings, small full-detail pages, and bounded retries on 429/503. Do not run unbounded parallel crawls. There is no key to obtain or refresh.

## Freshness and pagination

Successful source requests are cached for 900 seconds; failed requests for 60. The cache is lost on restart/sleep. There is no persistent database, background schedule, refresh-bypass parameter, or atomic multi-platform snapshot. Source `fetched_at` and `source_updated_at` have different meanings. Dates may be ISO timestamps or native upstream HTTP dates.

Offset pages can shift as directories change or caches expire. Follow `next_offset` and deduplicate by `id` for long crawls. Native rule and asset fields are intentionally preserved and can evolve with platforms; common REST envelope fields use the versioned `/api/v1` path.

## Gradio compatibility

The Gradio UI and event API remain at the same host/root paths.

| Endpoint | Positional inputs | Behavior |
| --- | --- | --- |
| `/collect` | `[platforms, search, bounty_only, limit, offset]` | Exactly five values; full details |
| `/collect_options` | `[platforms, search, bounty_only, limit, offset, include_details]` | Exactly six values; optional summary mode |
| `/details` | `[platform, handle]` | Complete live detail document |
| `/scope` | `[platform, handle]` | Alias of `/details` |
| `/sources` | `[]` | Source capabilities |

Gradio `/collect` defaults to full details; REST `/api/v1/programs` defaults to summaries. This deliberate difference preserves existing clients.

For raw Gradio HTTP, POST `{"data":[["hackerone"],"",false,10,0]}` to `/gradio_api/call/collect`, read `event_id`, then GET `/gradio_api/call/collect/EVENT_ID` as an event stream. The `complete` event's JSON array contains the result at index 0; `error` events indicate processing failures. Heartbeats are not results. Python defaults cannot replace missing Gradio positional values.

New integrations should use REST unless they specifically need Gradio queue/event behavior.
