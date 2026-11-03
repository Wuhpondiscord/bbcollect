# Usage recipes

No API key or login is needed. All examples call the public REST API. Start with summaries, then retrieve the details you need.

## Python: summary search and full details

```bash
pip install requests
```

```python
import requests

base = "https://wuhp-bbconnectapi.hf.space/api/v1"
session = requests.Session()

def get(path, **params):
    response = session.get(base + path, params=params, timeout=180)
    response.raise_for_status()
    result = response.json()
    if not result["ok"]:
        raise RuntimeError(result)
    return result

page = get("/programs", platforms="hackerone,bugcrowd", search="", limit=10)
print(page["total"], page["next_offset"])

for program in page["programs"][:2]:
    detail = get(f"/programs/{program['platform']}/{program['handle']}")
    print(program["name"], detail["min_bounty"], detail["max_bounty"], detail["currency"])
    print("partial:", detail["partial"], "fields:", detail["field_status"])
    print(detail["targets"], detail["rules"])
```

Details may use a fallback. A successful HTTP response is not proof that every field is present; inspect `partial`/`field_status` before accessing optional values.

## Crawl directory pages and export JSON/CSV

Run the [complete example](../examples/export_programs.py):

```bash
python examples/export_programs.py --platforms hackerone,bugcrowd,intigriti,yeswehack --output programs.json --csv programs.csv
```

The script follows `next_offset`, deduplicates IDs, validates statuses, and retries a bounded number of 429/503 responses. It exports directory summaries, not every policy document. To point it at a local instance, add `--base-url http://localhost:7860/api/v1`.

Equivalent pagination pattern:

```python
programs = {}
offset = 0
while True:
    page = get("/programs", platforms="hackerone,bugcrowd", limit=100, offset=offset)
    if page["partial"]:
        raise RuntimeError("A directory source is unavailable; inspect page['sources']")
    programs.update({p["id"]: p for p in page["programs"]})
    if page["next_offset"] is None:
        break
    offset = page["next_offset"]
```

For large collections, use summaries to discover IDs, then batch selected detail lookups. Offset pagination is not an atomic snapshot and can shift after cache expiration.

## Filter advertised rewards without mixing currencies

```python
page = get("/programs", platforms="hackerone", currency="USD",
           reward_at_least=1000, sort_by="max_bounty", descending=True, limit=10)
```

This uses directory `max_bounty`. Unknown amounts/currencies are excluded. It does not convert EUR to USD, infer minimums, or crawl all live tables before filtering.

## Get normalized assets while retaining exclusions

```python
assets = get("/programs/hackerone/security/assets", asset_type="wildcard", limit=100)
for asset in assets["in_scope"]:
    print(asset["identifier"], asset["type"], asset["instructions"])
print("All exclusions:", assets["out_of_scope"])
print("Program rules:", assets["rules"])
```

If `next_offset` is present, continue paging the included assets. All exclusions and rules remain in each response. Native target-group restrictions are in each asset's `raw` record; a normalized identifier alone is not sufficient authorization to test.

## Batch detail lookup

```python
response = session.post(base + "/programs/batch", json={"programs": [
    {"platform": "hackerone", "handle": "security"},
    {"platform": "yeswehack", "handle": "outscale"},
]}, timeout=180)
# Batch status 503 still contains individual results if all lookups failed.
if response.status_code not in (200, 503):
    response.raise_for_status()
batch = response.json()
if "programs" not in batch:
    raise RuntimeError(batch)
for detail in batch["programs"]:
    print(detail["platform"], detail["handle"], detail["ok"], detail.get("partial"))
```

## JavaScript / browser fetch

```javascript
const base = "https://wuhp-bbconnectapi.hf.space/api/v1";
const query = new URLSearchParams({
  platforms: "hackerone,bugcrowd", limit: "10", include_details: "false"
});
const response = await fetch(`${base}/programs?${query}`);
const page = await response.json();
if (!response.ok || !page.ok) throw new Error(JSON.stringify(page));
console.log(page.programs, page.next_offset);
```

CORS is enabled for public GET/POST requests. Do not add credentials, tokens, or an Authorization header. For batch requests use `method: "POST"`, `headers: {"Content-Type": "application/json"}`, and `body: JSON.stringify({programs: [...]})`.

## curl

```bash
# Is the application awake? (No upstream check.)
curl 'https://wuhp-bbconnectapi.hf.space/api/v1/health'

# Program counts and source status
curl 'https://wuhp-bbconnectapi.hf.space/api/v1/stats'

# A small page with full scopes and rules
curl 'https://wuhp-bbconnectapi.hf.space/api/v1/programs?platforms=hackerone&include_details=true&limit=5'

# Save a complete policy/scope response
curl 'https://wuhp-bbconnectapi.hf.space/api/v1/programs/yeswehack/outscale' -o outscale.json
```

In Windows PowerShell, use `curl.exe` if `curl` is an alias in your shell. For JSON POSTs, Python or a saved request-body file avoids shell-specific quote escaping.

## Existing Gradio integrations

```python
from gradio_client import Client
client = Client("wuhp/bbconnectapi")

# Original contract: exactly five positional values, always full details.
page = client.predict(["hackerone"], "", False, 10, 0, api_name="/collect")

# Six values only on collect_options; False selects summaries.
summary = client.predict(["hackerone"], "", False, 10, 0, False, api_name="/collect_options")
```

For direct REST examples, `requests` is the only client dependency. `gradio_client` is needed only for Gradio calls.
