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

# bbcollect · bbconnectapi

Collect public bug bounty programs, published reward ranges, scopes, exclusions, and program rules from **HackerOne, Bugcrowd, Intigriti, and YesWeHack**.

**No API key. No account. No Authorization header.** The hosted API is public and supports browser requests with CORS.

- [Interactive API documentation](https://wuhp-bbconnectapi.hf.space/api/docs) — try requests in your browser
- [API reference](https://github.com/Wuhpondiscord/bbcollect/blob/main/docs/API.md) — endpoints, parameters, responses, errors, limits
- [Usage recipes](https://github.com/Wuhpondiscord/bbcollect/blob/main/docs/EXAMPLES.md) — Python, JavaScript, curl, pagination, and exports
- [Gradio app](https://huggingface.co/spaces/wuhp/bbconnectapi) · [OpenAPI JSON](https://wuhp-bbconnectapi.hf.space/api/openapi.json)

## Quick start

Base URL: **`https://wuhp-bbconnectapi.hf.space/api/v1`**

```bash
curl 'https://wuhp-bbconnectapi.hf.space/api/v1/programs?platforms=hackerone,bugcrowd&limit=10'
```

```python
import requests

base = "https://wuhp-bbconnectapi.hf.space/api/v1"
response = requests.get(f"{base}/programs", params={
    "platforms": "hackerone,bugcrowd",
    "search": "", "bounty_only": True, "limit": 10,
}, timeout=180)
response.raise_for_status()
page = response.json()
for program in page["programs"]:
    print(program["name"], program["max_bounty"], program["currency"])

# One program's complete live document: rewards, scopes and policies.
response = requests.get(f"{base}/programs/hackerone/security", timeout=180)
response.raise_for_status()
detail = response.json()
print(detail["targets"]["in_scope"])
print(detail["targets"]["out_of_scope"])
print(detail["rules"])
```

Install the Python example dependency with `pip install requests`. REST responses are ordinary JSON; no event IDs or streaming client are required.

## What can I do?

| Endpoint | Purpose |
| --- | --- |
| `GET /programs` | Search multiple platforms, filter by bounty/currency, sort, and paginate |
| `GET /programs/{platform}/{handle}` | Live bounty tables, scopes, exclusions, and full program rules |
| `GET /programs/{platform}/{handle}/assets` | Common asset identifiers/types, with native records and all exclusions retained |
| `POST /programs/batch` | Up to 20 detail lookups in one request |
| `GET /stats` | Directory counts by platform without crawling individual policies |
| `GET /sources` | Supported sources, capabilities, and cache settings |
| `GET /health` | Cheap application readiness check |

Paths above are relative to `/api/v1`. **REST listings return summaries by default.** Add `include_details=true` to include live scopes and rules for every program on the page. Start with `limit=5` or `10`: full policies and large scopes can take much longer than summaries.

## Understand the data

| Platform | Directory | Program details |
| --- | --- | --- |
| HackerOne | Public live GraphQL, with dataset fallback | Live public policy, reward table, and paginated scope |
| Bugcrowd | Public dataset | Live public engagement brief, reward tiers, target groups, rules, safe harbor |
| Intigriti | Public dataset | Live current versions of assets, reward tables, rules, FAQs, and testing requirements |
| YesWeHack | Public dataset | Live public rules, reward grids, scopes, exclusions, and vulnerability requirements |

Directory snapshots and fallbacks come from [arkadiyt/bounty-targets-data](https://github.com/arkadiyt/bounty-targets-data). Only public metadata is collected; no target scanning or authenticated/private program data is involved. HackerOne covers the public open-program directory rather than every promotion on its Opportunities page.

- Check `ok`, `partial`, `sources`, `details_source`, and `field_status`. A partial response may retain dataset scopes while live rules are unavailable.
- `null` means unknown/unpublished/unavailable, not zero. Advertised rewards are not payout guarantees. Currency is separate; amount filters require an explicit currency.
- Most directory reward/currency fields outside HackerOne come from snapshots. Reward filters run on directory metadata **before** live detail enrichment, so values may differ from a refreshed detail document.
- Source results are cached in memory for 15 minutes; failures for 60 seconds. `fetched_at` is retrieval time, not the platform's last edit. `source_updated_at` may be unavailable.
- Always check the linked program's current rules. Asset filters retain exclusions; program rules and group instructions still apply.

## Existing Gradio clients

The Gradio API remains available without a token:

```python
from gradio_client import Client
client = Client("wuhp/bbconnectapi")
page = client.predict(["hackerone"], "", False, 10, 0, api_name="/collect")
detail = client.predict("hackerone", "security", api_name="/details")
```

`/collect` keeps exactly **five** inputs and always includes full details. `/collect_options` adds a sixth `include_details` boolean. `/scope` remains an alias for `/details`; `/sources` takes no inputs. See the [compatibility reference](https://github.com/Wuhpondiscord/bbcollect/blob/main/docs/API.md#gradio-compatibility) for raw HTTP payloads.

## Run your own instance

```bash
git clone https://github.com/Wuhpondiscord/bbcollect.git
cd bbcollect
python -m venv .venv
# Activate .venv for your shell, then:
pip install -r requirements.txt
python app.py
```

Open `http://localhost:7860`, `http://localhost:7860/api/docs`, or `http://localhost:7860/api/v1/health`. `PORT` overrides port 7860. No runtime secrets are required. [Deployment guide](https://github.com/Wuhpondiscord/bbcollect/blob/main/docs/DEPLOYMENT.md).

The hosted Space may sleep or restart; there is no uptime guarantee or persistent database. Busy REST collection requests receive `429` and a `Retry-After` header. Prefer summary pages and batch only the details you need. Cache expiration can shift offset pagination; deduplicate program IDs during long crawls.

## Contribute

Run `python -m unittest discover -s tests -v` before submitting changes. Tests cover the REST contract, filters, normalization, partial failures, and the original five-input Gradio request. New providers should preserve scopes, exclusions, native policies, and source provenance. See [CONTRIBUTING.md](https://github.com/Wuhpondiscord/bbcollect/blob/main/CONTRIBUTING.md) and [CHANGELOG.md](https://github.com/Wuhpondiscord/bbcollect/blob/main/CHANGELOG.md).

