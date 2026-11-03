---
title: bbconnectapi
emoji: 🏆
colorFrom: indigo
colorTo: yellow
sdk: gradio
sdk_version: 6.31.0
python_version: '3.13'
app_file: app.py
pinned: false
---

# bbcollect / bbconnectapi

A Gradio UI and JSON API for public bug bounty program listings and scope.

- Space: https://huggingface.co/spaces/wuhp/bbconnectapi
- Source: https://github.com/Wuhpondiscord/bbcollect
- HackerOne: live public GraphQL requests initialized from https://hackerone.com/opportunities/all, with explicit dataset fallback.
- Bugcrowd, Intigriti, YesWeHack directories: public snapshots from [arkadiyt/bounty-targets-data](https://github.com/arkadiyt/bounty-targets-data).
- All four platforms: live program details, reward ranges/tables, scopes, exclusions and full program rules.

This collects the public open-program directory, not every promotion or feature of the Opportunities page. Private programs and authenticated account data are not collected. No platform credentials are required.

## API usage

Install `gradio_client`, then:

```python
from gradio_client import Client
client = Client("wuhp/bbconnectapi")
page = client.predict(
    platforms=["hackerone", "bugcrowd", "intigriti", "yeswehack"],
    search="", bounty_only=False, limit=10, offset=0,
    api_name="/collect",
)
print(page["programs"])
# For the next page use page["next_offset"] as offset, unless it is None.
scope = client.predict(platform="hackerone", handle="security", api_name="/scope")
print(scope["targets"]["in_scope"])
print(scope["targets"]["out_of_scope"])
print(client.predict(api_name="/sources"))
details = client.predict(platform="bugcrowd", handle="CCData-mbb-og", api_name="/details")
print(details["min_bounty"], details["max_bounty"], details["rules"])
```

Raw HTTP uses Gradio's two-step event API, not REST GET routes:

```bash
curl -X POST https://wuhp-bbconnectapi.hf.space/gradio_api/call/collect \
  -H 'Content-Type: application/json' \
  -d '{"data":[["hackerone"],"",false,10,0]}'
# Use the returned event_id:
curl -N https://wuhp-bbconnectapi.hf.space/gradio_api/call/collect/EVENT_ID
```

`/collect` accepts exactly five inputs in this order: `platforms`, `search`, `bounty_only`, `limit`, `offset`. It returns `ok`, `partial`, `total` (after filtering), `next_offset`, `sources`, and `programs`. It always includes live details: each program has `targets`, `rules`, `reward_table`, `field_status`, and `details_source`.

Use `/collect_options` for the same five inputs plus a sixth `include_details` boolean. Set it to `False` for fast summary pages. Clients using the six-value payload from the previous version should change their endpoint to `/collect_options`; original five-value `/collect` clients require no changes. Python default arguments do not make Gradio component inputs optional in raw HTTP requests.

Full-detail pages support 1–100 programs; summary pages support 1–1000. `offset` is 0–100000. Four workers fetch details with a shared 15-minute cache, so large first requests take longer.

Failures are reported per source and program. A successful empty search differs from an upstream failure. Sorting is by platform, name, then ID. Search matches name, handle, URL or website. The bounty filter excludes unknown values.

Program fields: `id`, `platform`, `handle`, `name`, `url`, `website`, `offers_bounties`, `min_bounty`, `max_bounty`, `currency`, `submission_state`. Bounty amounts are numeric with a separate currency when available. Unknown values are null; an unpublished minimum is never inferred from the maximum. Reward tables preserve severity/asset-tier ranges. Bugcrowd ranges use all published in-scope severity tiers; HackerOne ranges use its published bounty table. These are advertised rewards, not historical payouts or guarantees.

Use the exact platform and handle returned by `/collect` for `/details` or `/scope` (an alias returning the same full details). Intigriti uses its program UUID because URL slugs can repeat across companies. `targets` contains `in_scope` and `out_of_scope` arrays with native fields, group instructions, and exclusions. `rules` preserves full policy text/HTML, disclosure terms, safe-harbor information, testing requirements, FAQs, or qualifying vulnerability types where published. Intigriti uses the latest version of every section. HTML is returned as JSON strings, not executed.

If live details fail, available dataset scopes/rewards are retained, `partial` is true, and `field_status` explicitly marks missing rules. Missing policies are never represented as an empty set of permissions. Rules linked from program text remain links; the collector does not recursively crawl external documents.

Each source reports `mode` (`live` or `public_dataset`), `source_url`, `fetched_at`, `source_updated_at` (null if unavailable), and `cached`. Retrieval time is not the time the platform last changed its data. Live pages are fetched sequentially, not atomically; pagination may shift after the cache expires.

## Deployment

The GitHub Actions workflow tests pushes/PRs and deploys successful `main` builds to the existing `wuhp/bbconnectapi` Space. Manual workflow dispatch is supported. The repository Actions secret **HF_TOKEN** must have write access to that Space. The token is used only by the deployment job; the public app never receives it.

Only `app.py`, `collector.py`, `details.py`, `requirements.txt`, and `README.md` are uploaded. Existing unrelated Space files are retained. Tokens are never printed or placed in Git remote URLs.

## Local development

```bash
python -m venv .venv
# Activate the environment for your shell, then:
pip install -r requirements.txt
python -m unittest discover -s tests -v
python app.py
```

Open http://localhost:7860. Public Spaces expose their Gradio API publicly; use a private Space and an authenticated client for restricted access. Free Spaces may sleep and lose their cache. Collection runs on demand with a shared 15-minute memory cache, or 60 seconds for failures. There is no scheduled crawler or persistent database.

Check current program rules and scope at the linked platform before testing. Snapshots can lag behind changes and do not grant permission to test assets.

## Data attribution

Additional feeds and the HackerOne fallback use public data maintained by [arkadiyt/bounty-targets-data](https://github.com/arkadiyt/bounty-targets-data). The upstream Ruby collector is not bundled.
